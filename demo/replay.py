"""Replay the captured Nemotron repair offline. No credential or inference call."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
REQUIRED_FILES = {
    'demo/evidence/baseline.py', 'demo/evidence/candidate.py',
    'demo/evidence/candidate.patch', 'demo/evidence/request.json',
    'demo/evidence/overfit-control.py',
    'demo/evidence/response-summary.json', 'demo/evidence/recorded-run.json',
    'verifier/check.py', 'workspace/interval_union/visible_tests.json',
}


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def validate_bundle(root=ROOT):
    root = Path(root).resolve()
    manifest = json.loads((root / 'demo/manifest.json').read_text())
    if manifest.get('format') != 'nemotron-recorded-demo-v2' or set(manifest['files']) != REQUIRED_FILES:
        raise ValueError('Demo manifest does not identify the required evidence files')
    for name, expected in manifest['files'].items():
        path = (root / name).resolve()
        if not path.is_relative_to(root) or not path.is_file() or digest(path) != expected:
            raise ValueError('Evidence digest mismatch: ' + name)
    evidence = root / 'demo/evidence'
    record = json.loads((evidence / 'recorded-run.json').read_text())
    response = json.loads((evidence / 'response-summary.json').read_text())
    payload = json.loads(response['choices'][0]['message']['content'])
    if (set(payload) != {'task.py'} or not isinstance(payload['task.py'], str)
            or payload['task.py'].encode() != (evidence / 'candidate.py').read_bytes()
            or digest(evidence / 'candidate.py') != record['candidate_sha256']
            or response['model'] != record['model'] or response['id'] != record['response_id']
            or response['choices'][0]['finish_reason'] != 'stop'):
        raise ValueError('Recorded response and candidate provenance do not match')
    return record


def check(root, candidate):
    command = [sys.executable, '-I', '-B', str(root / 'verifier/check.py'), str(candidate)]
    result = subprocess.run(command, text=True, capture_output=True, timeout=15)
    report = json.loads(result.stdout)
    expected_exit = {'ACCEPT': 0, 'HOLD': 1, 'UNKNOWN': 2}[report['acceptance_state']]
    if result.returncode != expected_exit:
        raise ValueError('Verifier exit status does not match the reported decision')
    return report


def counts(report):
    return {group: {key: report[group][key] for key in ['passed', 'failed']}
            for group in ['targeted', 'regression', 'extended'] if group in report}


def original_counts(report):
    return {group: counts(report)[group] for group in ['targeted', 'regression']}


def replay(output, root=ROOT):
    root = Path(root).resolve()
    output = Path(output).resolve()
    record = validate_bundle(root)
    output.mkdir(parents=True, exist_ok=False)
    evidence = root / 'demo/evidence'
    baseline = check(root, evidence / 'baseline.py')
    if baseline['acceptance_state'] != 'HOLD' or original_counts(baseline) != record['baseline']:
        raise ValueError('Baseline no longer reproduces the recorded failures')
    control = check(root, evidence / 'overfit-control.py')
    if (control['acceptance_state'] != 'HOLD' or control['targeted']['failed']
            or not control['regression']['failed']):
        raise ValueError('Authored overfit control no longer demonstrates visible-green rejection')
    with tempfile.TemporaryDirectory(prefix='nemotron-patch-') as temporary:
        workspace = Path(temporary)
        shutil.copyfile(evidence / 'baseline.py', workspace / 'task.py')
        applied = subprocess.run(['git', 'apply', str(evidence / 'candidate.patch')],
                                 cwd=workspace, text=True, capture_output=True)
        if applied.returncode:
            raise ValueError('Captured candidate patch does not apply: ' + applied.stderr)
        if digest(workspace / 'task.py') != record['candidate_sha256']:
            raise ValueError('Replayed patch does not match the recorded candidate digest')
        candidate = check(root, workspace / 'task.py')
        if candidate['acceptance_state'] != 'ACCEPT' or original_counts(candidate) != record['candidate'] or candidate['extended']['failed']:
            raise ValueError('Candidate no longer reproduces the recorded acceptance')
        shutil.copyfile(workspace / 'task.py', output / 'replayed-task.py')
    result = {'mode': 'offline_recorded_replay', 'acceptance_state': 'ACCEPT',
              'recorded_run_id': record['run_id'], 'model': record['model'],
              'candidate_sha256': record['candidate_sha256'],
              'checker_sha256': candidate['checker_sha256'],
              'patch_matches_recorded_candidate': True,
              'baseline': counts(baseline), 'candidate': counts(candidate),
              'overfit_control': {'origin': 'authored_negative_control', 'acceptance_state': 'HOLD',
                                  'counterexample': control['illustrative_case'],
                                  **counts(control)},
              'post_run_coverage': {'longer_list_cases': 321, 'lengths': [4, 19], 'seed': 20261025}}
    counterexample = control['illustrative_case']
    transcript = '\n'.join([
        'Nemotron Repair Trial | patch review for maintainers',
        'Mode: offline replay of one real Nebius call; no new inference',
        '',
        'Visible tests can pass while a patch is wrong. Inspect all three decisions:',
        f"BASELINE: HOLD | visible {baseline['targeted']['passed']}/3 | regression {baseline['regression']['passed']}/2049",
        f"AUTHORED OVERFIT CONTROL: HOLD | visible 3/3 | regression {control['regression']['passed']}/2049",
        '  Authored negative control, not another model output.',
        '  Counterexample: ' + json.dumps(counterexample['input']),
        '  Expected: ' + json.dumps(counterexample['expected']) + ' | actual: ' + json.dumps(counterexample['actual']),
        'RECORDED NEMOTRON CANDIDATE: ACCEPT | visible 3/3 | regression 2049/2049',
        '  Saved patch applied to a fresh baseline; candidate bytes match.',
        'POST-RUN EXTENSION: 321/321 longer-list cases passed (lengths 4..19).',
        '  Additional validation of the same saved candidate; not a new inference.',
        '',
        'Recorded model: ' + record['model'],
        'Evidence and trusted checker file digests: PASS',
        'Input preservation checked on every case.',
        'Review decision: HOLD the visible-green control; ACCEPT the saved repair on these bounded checks.',
        'Scope: one synthetic task; no comparative model-quality claim.',
    ]) + '\n'
    review = '\n'.join([
        '# Patch review', '',
        'For maintainers reviewing generated changes: visible test success is not enough.', '',
        '| Candidate | Visible passed | Original regression passed | Longer-list passed | Decision |',
        '| --- | --- | --- | --- | --- |',
        f"| Unchanged baseline | {baseline['targeted']['passed']}/3 | {baseline['regression']['passed']}/2049 | {baseline['extended']['passed']}/321 | HOLD |",
        f"| Authored overfit control | 3/3 | {control['regression']['passed']}/2049 | {control['extended']['passed']}/321 | HOLD |",
        '| Recorded Nemotron repair | 3/3 | 2049/2049 | 321/321 | ACCEPT |', '',
        'The control is newly authored adversarial input, not a recorded model result.',
        'The 321 longer-list cases are post-run validation of the same captured repair.', '',
        '## Why hold the visible-green control', '',
        'Counterexample input: `' + json.dumps(counterexample['input']) + '`.',
        'Expected `' + json.dumps(counterexample['expected']) + '`, returned `' + json.dumps(counterexample['actual']) + '`.', '',
        '## Inspect and reproduce', '',
        'The saved Git patch produced exactly the model-returned file. All bundled',
        'evidence and current verifier digests matched the versioned manifest.',
        'Full reports are in baseline-verification.json, overfit-verification.json,',
        'and candidate-verification.json. Acceptance is limited to these checks.',
    ]) + '\n'
    (output / 'review.md').write_text(review)
    for name, value in [('baseline-verification.json', baseline),
                        ('candidate-verification.json', candidate), ('overfit-verification.json', control),
                        ('demo-result.json', result)]:
        (output / name).write_text(json.dumps(value, indent=2) + '\n')
    (output / 'transcript.txt').write_text(transcript)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True, help='New local directory for replay results')
    args = parser.parse_args()
    try:
        replay(args.output)
    except (ValueError, OSError, KeyError, subprocess.TimeoutExpired) as error:
        print('Demo failed: ' + str(error), file=sys.stderr)
        return 1
    print((args.output / 'transcript.txt').read_text(), end='')
    print('Replay output: ' + str(args.output.resolve()))
    return 0


if __name__ == '__main__':
    sys.exit(main())
