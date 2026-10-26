import json
from pathlib import Path
import tempfile
import hashlib
import shutil
import subprocess
from unittest.mock import patch

import agent.run_trial as trial
import unittest

from agent.run_trial import build_request, extract_candidate
from providers.nebius.client import validate_endpoint, sanitized
from verifier.check import verify_candidate

ROOT = Path(__file__).resolve().parents[1]
# This reference validates the checker only; it is never sent to the model or
# used as the trial's generated candidate.
GOOD = '''def merge_intervals(intervals):
    result = []
    for start, end in sorted(intervals):
        if start == end:
            continue
        if result and start <= result[-1][1]:
            result[-1] = (result[-1][0], max(result[-1][1], end))
        else:
            result.append((start, end))
    return result
'''


class VerifierTests(unittest.TestCase):
    def check_source(self, source):
        with tempfile.TemporaryDirectory() as temp:
            candidate = Path(temp) / 'task.py'
            candidate.write_text(source)
            return verify_candidate(candidate)

    def test_independent_checker_accepts_correct_union(self):
        report = self.check_source(GOOD)
        self.assertEqual(report['acceptance_state'], 'ACCEPT')
        self.assertGreater(report['regression']['passed'], 1000)
        self.assertEqual(report['regression']['failed'], 0)

    def test_buggy_baseline_fails_nested_case_but_smoke_cases_pass(self):
        report = verify_candidate(ROOT / 'workspace/interval_union/task.py')
        self.assertEqual(report['acceptance_state'], 'HOLD')
        cases = {c['name']: c for c in report['targeted']['cases']}
        self.assertFalse(cases['nested_interval']['passed'])
        self.assertTrue(cases['disjoint_intervals']['passed'])
        self.assertTrue(cases['empty_input']['passed'])

    def test_checker_rejects_visible_case_overfit(self):
        report = self.check_source('''def merge_intervals(intervals):
    if intervals == [(1, 10), (2, 3)]:
        return [(1, 10)]
    return intervals
''')
        self.assertEqual(report['acceptance_state'], 'HOLD')
        self.assertEqual(report['targeted']['failed'], 0)
        self.assertGreater(report['regression']['failed'], 0)

    def test_candidate_cannot_execute_module_side_effect(self):
        with tempfile.TemporaryDirectory() as temp:
            marker = Path(temp) / 'side_effect'
            report = self.check_source(f'open({str(marker)!r}, "w").write("bad")\n' + GOOD)
            self.assertEqual(report['acceptance_state'], 'HOLD')
            self.assertFalse(marker.exists())

    def test_candidate_cannot_import_or_reach_dunder_attributes(self):
        for source in ['import os\n' + GOOD,
                       'def merge_intervals(intervals):\n    return intervals.__class__\n']:
            with self.subTest(source=source):
                self.assertEqual(self.check_source(source)['acceptance_state'], 'HOLD')

    def test_checker_rejects_input_mutation(self):
        source = GOOD.replace('    result = []', '    intervals.append((0, 0))\n    result = []')
        report = self.check_source(source)
        self.assertEqual(report['acceptance_state'], 'HOLD')
        self.assertGreater(report['targeted']['failed'], 0)


class RequestTests(unittest.TestCase):
    def test_prompt_only_contains_visible_task_material(self):
        request = build_request('nvidia/Nemotron-3_5-Lightning')
        prompt = request['messages'][1]['content']
        self.assertIn('nested_interval', prompt)
        self.assertNotIn('exhaustive', prompt.lower())
        self.assertNotIn(GOOD, prompt)
        self.assertLessEqual(request['max_tokens'], 4096)

    def test_extracts_single_allowed_file(self):
        response = {'choices': [{'finish_reason': 'stop', 'message': {'content': json.dumps({'task.py': GOOD})}}]}
        self.assertEqual(extract_candidate(response), GOOD)

    def test_rejects_truncated_or_out_of_scope_candidate(self):
        for finish, payload in [('length', {'task.py': GOOD}),
                                ('stop', {'task.py': GOOD, 'verifier/check.py': 'pass'}),
                                ('stop', {'../task.py': GOOD}), ('stop', {'task.py': 123})]:
            with self.subTest(finish=finish, payload=payload):
                response = {'choices': [{'finish_reason': finish, 'message': {'content': json.dumps(payload)}}]}
                with self.assertRaises(ValueError):
                    extract_candidate(response)

    def test_rejects_non_nemotron_model(self):
        with self.assertRaises(ValueError):
            build_request('unrelated/model')

    def test_key_cannot_be_sent_to_untrusted_host_or_http(self):
        for endpoint in ['http://api.tokenfactory.nebius.com/v1', 'https://example.com/v1',
                         'https://api.tokenfactory.nebius.com.evil.example/v1',
                         'https://api.tokenfactory.nebius.com/v1?key=bad']:
            with self.subTest(endpoint=endpoint):
                with self.assertRaises(ValueError):
                    validate_endpoint(endpoint)
        self.assertEqual(validate_endpoint('https://api.tokenfactory.nebius.com/v1/'),
                         'https://api.tokenfactory.nebius.com/v1')

    def test_secret_redaction_preserves_response_structure(self):
        result = sanitized({'message': 'token SECRET', 'usage': {'total_tokens': 1}}, 'SECRET')
        self.assertEqual(result['message'], 'token [REDACTED]')
        self.assertEqual(result['usage']['total_tokens'], 1)



class TrialIntegrationTests(unittest.TestCase):
    def test_trial_records_independent_verdict_and_replayable_patch(self):
        with tempfile.TemporaryDirectory() as temp:
            repo = Path(temp) / 'repo'
            repo.mkdir()
            files = ['workspace/interval_union/task.py', 'workspace/interval_union/spec.txt',
                     'workspace/interval_union/visible_tests.json', 'verifier/check.py',
                     'providers/nebius/client.py', 'agent/run_trial.py']
            for name in files:
                destination = repo / name
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(ROOT / name, destination)
            subprocess.run(['git', 'init', '--quiet', str(repo)], check=True)
            subprocess.run(['git', '-C', str(repo), 'add', '.'], check=True)
            subprocess.run(['git', '-C', str(repo), '-c', 'user.name=Test',
                            '-c', 'user.email=test@example.invalid', 'commit', '--quiet',
                            '-m', 'test source snapshot'], check=True)
            candidate = GOOD.rstrip('\n')
            response = {'id': 'unit-test-only', 'model': trial.DEFAULT_MODEL,
                        'usage': {'prompt_tokens': 1, 'completion_tokens': 1, 'total_tokens': 2},
                        'choices': [{'finish_reason': 'stop', 'message': {
                            'content': json.dumps({'task.py': candidate})}}]}
            wire = [({'data': [{'id': trial.DEFAULT_MODEL}]}, {}),
                    (response, {'endpoint': 'test-double', 'http_status': 200})]
            output = Path(temp) / 'evidence'
            with patch.object(trial, 'ROOT', repo), patch.object(trial, 'TASK', repo / 'workspace/interval_union'), \
                    patch.object(trial, 'request_json', side_effect=wire):
                result = trial.run_trial(output, trial.DEFAULT_MODEL)
            self.assertEqual(result['acceptance_state'], 'ACCEPT')
            self.assertTrue(result['trusted_source_unchanged'])
            self.assertEqual(result['candidate_sha256'], hashlib.sha256(candidate.encode()).hexdigest())
            self.assertEqual((repo / 'workspace/interval_union/task.py').read_bytes(),
                             (ROOT / 'workspace/interval_union/task.py').read_bytes())
            # Reproduce the generated patch against a fresh baseline file.
            replay = Path(temp) / 'replay'
            replay.mkdir()
            shutil.copyfile(ROOT / 'workspace/interval_union/task.py', replay / 'task.py')
            applied = subprocess.run(['git', 'apply', str(output / 'candidate.patch')],
                                     cwd=replay, capture_output=True, text=True)
            self.assertEqual(applied.returncode, 0, applied.stderr)
            self.assertEqual((replay / 'task.py').read_text(), candidate)

if __name__ == '__main__':
    unittest.main()
