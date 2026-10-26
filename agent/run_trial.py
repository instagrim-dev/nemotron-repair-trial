"""One bounded Nebius repair attempt, with local provenance and verification."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

from providers.nebius.client import request_json
from verifier.check import verify_candidate

ROOT = Path(__file__).resolve().parents[1]
TASK = ROOT / 'workspace/interval_union'
DEFAULT_MODEL = 'nvidia/Nemotron-3_5-Lightning'


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, value):
    Path(path).write_text(json.dumps(value, indent=2) + '\n')


def build_request(model):
    if not model.lower().startswith('nvidia/') or 'nemotron' not in model.lower():
        raise ValueError('This trial requires an NVIDIA Nemotron model')
    prompt = ('SPECIFICATION\n' + (TASK / 'spec.txt').read_text()
              + '\nCURRENT task.py\n' + (TASK / 'task.py').read_text()
              + '\nVISIBLE TESTS\n' + (TASK / 'visible_tests.json').read_text())
    return {'model': model, 'temperature': 0, 'max_tokens': 4096,
            'response_format': {'type': 'json_object'}, 'messages': [
                {'role': 'system', 'content': 'Repair only the authorized task.py. Return the requested JSON object only.'},
                {'role': 'user', 'content': prompt},
            ]}


def extract_candidate(response):
    try:
        choices = response['choices']
        if len(choices) != 1 or choices[0]['finish_reason'] != 'stop':
            raise ValueError('Model response was truncated or did not finish normally')
        payload = json.loads(choices[0]['message']['content'])
        if (not isinstance(payload, dict) or set(payload) != {'task.py'}
                or not isinstance(payload['task.py'], str)
                or not payload['task.py'].strip() or len(payload['task.py'].encode()) > 20000):
            raise ValueError('Candidate must contain only the task.py source string')
        return payload['task.py']
    except (KeyError, TypeError, IndexError, json.JSONDecodeError) as error:
        raise ValueError('Invalid model candidate response') from error


def git(path, *args):
    return subprocess.check_output(['git', '-C', str(path), *args], text=True).strip()


def fixture_commit(path, message):
    subprocess.run(['git', '-C', str(path), '-c', 'user.name=Nemotron Repair Trial',
                    '-c', 'user.email=5620391+instagrim-dev@users.noreply.github.com',
                    'add', 'task.py'], check=True, capture_output=True)
    subprocess.run(['git', '-C', str(path), '-c', 'user.name=Nemotron Repair Trial',
                    '-c', 'user.email=5620391+instagrim-dev@users.noreply.github.com',
                    'commit', '--quiet', '--allow-empty', '-m', message], check=True, capture_output=True)
    return git(path, 'rev-parse', 'HEAD')


def run_trial(output, model):
    output = Path(output).resolve()
    if output.is_relative_to(ROOT):
        raise ValueError('Store raw evidence outside the public repository')
    if git(ROOT, 'status', '--porcelain'):
        raise ValueError('Commit source changes before running; evidence requires a clean source revision')
    request = build_request(model)
    output.mkdir(parents=True, exist_ok=False)
    pinned_files = ['workspace/interval_union/task.py', 'workspace/interval_union/spec.txt',
                    'workspace/interval_union/visible_tests.json', 'verifier/check.py',
                    'providers/nebius/client.py', 'agent/run_trial.py']
    pins = {name: digest(ROOT / name) for name in pinned_files}
    metadata = {'task_id': 'interval-union-v1', 'started_at_utc': datetime.now(timezone.utc).isoformat(),
                'source_revision': git(ROOT, 'rev-parse', 'HEAD'), 'trusted_source_sha256': pins,
                'python_version': sys.version,
                'requested_model': model, 'request_sha256': hashlib.sha256(json.dumps(request, sort_keys=True).encode()).hexdigest()}
    save(output / 'run-metadata.json', metadata)
    save(output / 'request.json', request)
    baseline = verify_candidate(TASK / 'task.py')
    save(output / 'baseline-verification.json', baseline)
    cases = {c['name']: c for c in baseline.get('targeted', {}).get('cases', [])}
    if (baseline['acceptance_state'] != 'HOLD' or cases.get('nested_interval', {}).get('passed') is not False
            or not cases.get('disjoint_intervals', {}).get('passed') or not cases.get('empty_input', {}).get('passed')):
        raise ValueError('Baseline did not exhibit the intended isolated visible failure')
    try:
        catalog, _ = request_json('models')
        ids = [item['id'] for item in catalog['data']]
        save(output / 'model-catalog.json', {'model_ids': ids})
        if model not in ids:
            raise ValueError('Requested model is absent from the authenticated model catalog')
        response, transport = request_json('chat/completions', request)
        save(output / 'response.json', response)
        metadata.update(transport)
        metadata.update({'served_model': response.get('model'), 'usage': response.get('usage'),
                         'response_id': response.get('id')})
        candidate = extract_candidate(response)
        workspace = output / 'candidate-workspace'
        workspace.mkdir()
        shutil.copyfile(TASK / 'task.py', workspace / 'task.py')
        subprocess.run(['git', 'init', '--quiet', '--initial-branch=main', str(workspace)], check=True)
        metadata['fixture_source_revision'] = fixture_commit(workspace, 'Unrepaired fixture baseline')
        (workspace / 'task.py').write_text(candidate)
        metadata['result_revision'] = fixture_commit(workspace, 'Nemotron generated candidate')
        (output / 'candidate.py').write_text(candidate)
        patch = git(workspace, 'diff', '--binary', metadata['fixture_source_revision'],
                    metadata['result_revision'], '--', 'task.py') + '\n'
        (output / 'candidate.patch').write_text(patch)
        metadata['candidate_sha256'] = digest(workspace / 'task.py')
        report = verify_candidate(workspace / 'task.py')
        save(output / 'candidate-verification.json', report)
        unchanged = pins == {name: digest(ROOT / name) for name in pinned_files}
        state = report['acceptance_state'] if unchanged else 'UNKNOWN'
        verdict = {'acceptance_state': state, 'trusted_source_unchanged': unchanged,
                   'source_revision': metadata['source_revision'], 'result_revision': metadata['result_revision'],
                   'candidate_sha256': metadata['candidate_sha256'], 'checker_sha256': pins['verifier/check.py'],
                   'targeted': report.get('targeted'), 'regression': report.get('regression'),
                   'guard_error': report.get('guard_error'),
                   'scope': 'One synthetic repair attempt; not comparative model evaluation'}
    except (RuntimeError, ValueError, OSError, KeyError) as error:
        # No retry or manufactured candidate. Preserve the actual failed attempt.
        verdict = {'acceptance_state': 'UNKNOWN', 'error': str(error),
                   'source_revision': metadata['source_revision'], 'requested_model': model}
    metadata['finished_at_utc'] = datetime.now(timezone.utc).isoformat()
    save(output / 'run-metadata.json', metadata)
    save(output / 'trial-result.json', verdict)
    return verdict


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--model', default=os.environ.get('NEBIUS_MODEL', DEFAULT_MODEL))
    args = parser.parse_args()
    result = run_trial(args.output, args.model)
    print(json.dumps(result, indent=2))
    return 0 if result['acceptance_state'] == 'ACCEPT' else 1


if __name__ == '__main__':
    sys.exit(main())
