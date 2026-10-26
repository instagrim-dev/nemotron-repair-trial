"""Trusted checker. Candidate receives no verifier source or held-out cases."""
import ast
import hashlib
import itertools
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
VISIBLE = ROOT / 'workspace/interval_union/visible_tests.json'
ALLOWED_CALLS = {'sorted': sorted, 'max': max, 'min': min, 'len': len,
                 'list': list, 'tuple': tuple}
ALLOWED_NODES = {
    ast.Module, ast.FunctionDef, ast.arguments, ast.arg, ast.Return, ast.Assign,
    ast.AugAssign, ast.Expr, ast.For, ast.If, ast.Break, ast.Continue, ast.Pass,
    ast.List, ast.Tuple, ast.Name, ast.Constant, ast.Load, ast.Store, ast.Subscript,
    ast.Slice, ast.Call, ast.keyword, ast.Attribute, ast.Compare, ast.BoolOp,
    ast.BinOp, ast.UnaryOp, ast.IfExp, ast.ListComp, ast.comprehension,
    ast.Add, ast.Sub, ast.USub, ast.UAdd, ast.Not, ast.And, ast.Or,
    ast.Eq, ast.NotEq, ast.Lt, ast.LtE, ast.Gt, ast.GtE, ast.In, ast.NotIn,
    ast.Is, ast.IsNot,
}


def load_candidate(path):
    source = Path(path).read_text()
    if len(source.encode()) > 20000:
        raise ValueError('Candidate exceeds 20 KB')
    tree = ast.parse(source)
    if len(tree.body) != 1 or not isinstance(tree.body[0], ast.FunctionDef):
        raise ValueError('Only the merge_intervals function may be defined')
    fn = tree.body[0]
    if (fn.name != 'merge_intervals' or fn.decorator_list or fn.returns
            or len(fn.args.args) != 1 or fn.args.args[0].arg != 'intervals'
            or fn.args.args[0].annotation or fn.args.defaults or fn.args.kw_defaults
            or fn.args.posonlyargs or fn.args.kwonlyargs or fn.args.vararg or fn.args.kwarg):
        raise ValueError('Candidate changed the function interface')
    for node in ast.walk(tree):
        if type(node) not in ALLOWED_NODES:
            raise ValueError('Unsupported candidate syntax: ' + type(node).__name__)
        if isinstance(node, ast.FunctionDef) and node is not fn:
            raise ValueError('Nested definitions are not allowed')
        if isinstance(node, ast.Name) and node.id.startswith('_'):
            raise ValueError('Private names are not allowed')
        if isinstance(node, ast.Attribute) and node.attr != 'append':
            raise ValueError('Only list append attribute access is allowed')
        if isinstance(node, ast.Call):
            allowed = (isinstance(node.func, ast.Name) and node.func.id in ALLOWED_CALLS)
            allowed |= isinstance(node.func, ast.Attribute) and node.func.attr == 'append'
            if not allowed:
                raise ValueError('Unsupported function call')
        if isinstance(node, ast.Constant):
            if isinstance(node.value, int) and abs(node.value) > 1000:
                raise ValueError('Candidate literal exceeds fixture bounds')
            if isinstance(node.value, str) and len(node.value) > 2000:
                raise ValueError('Candidate string exceeds fixture bounds')
    namespace = {'__builtins__': ALLOWED_CALLS.copy()}
    exec(compile(tree, str(path), 'exec'), namespace)
    return namespace['merge_intervals']


def occupancy_oracle(intervals):
    # Independent finite-domain oracle: enumerate occupied integer cells rather
    # than implement the candidate's sorted-interval merging algorithm.
    cells = sorted({cell for start, end in intervals for cell in range(start, end)})
    result = []
    for _, group in itertools.groupby(enumerate(cells), lambda pair: pair[1] - pair[0]):
        run = [cell for _, cell in group]
        result.append((run[0], run[-1] + 1))
    return result


def check_case(function, name, intervals, expected):
    original = [tuple(pair) for pair in intervals]
    argument = original.copy()
    try:
        actual = function(argument)
        valid_shape = (type(actual) is list and all(
            type(pair) is tuple and len(pair) == 2 and all(type(n) is int for n in pair)
            for pair in actual))
        passed = valid_shape and actual == expected and argument == original
        return {'name': name, 'passed': passed, 'input': original, 'expected': expected,
                'actual': actual if valid_shape else 'invalid result shape',
                'input_unchanged': argument == original}
    except Exception as error:
        return {'name': name, 'passed': False, 'error': type(error).__name__}


def run_checks(path):
    try:
        function = load_candidate(path)
    except (ValueError, SyntaxError) as error:
        return {'acceptance_state': 'HOLD', 'guard_error': str(error)}
    targeted = []
    for case in json.loads(VISIBLE.read_text()):
        targeted.append(check_case(function, case['name'], case['input'],
                                   [tuple(pair) for pair in case['expected']]))
    intervals = [(a, b) for a in range(-4, 5) for b in range(a, 5)]
    regression = []
    for i, pair in enumerate(itertools.product(intervals, repeat=2)):
        regression.append(check_case(function, f'pair_{i}', list(pair), occupancy_oracle(pair)))
    triples = [((0, 8), (2, 3), (7, 10)), ((-4, -1), (-2, 2), (2, 4)),
               ((0, 0), (1, 2), (2, 3)), ((-2, 4), (-2, 4), (0, 1))]
    for i, triple in enumerate(triples):
        for j, permutation in enumerate(itertools.permutations(triple)):
            regression.append(check_case(function, f'triple_{i}_{j}', list(permutation),
                                         occupancy_oracle(permutation)))
    def group(cases, include_passes=False):
        failures = [case for case in cases if not case['passed']]
        return {'passed': len(cases) - len(failures), 'failed': len(failures),
                'cases': cases if include_passes else failures[:10]}
    target_report = group(targeted, True)
    regression_report = group(regression)
    return {'acceptance_state': 'ACCEPT' if not target_report['failed'] and not regression_report['failed'] else 'HOLD',
            'targeted': target_report, 'regression': regression_report,
            'oracle_scope': 'integer endpoints -4..4; all ordered pairs plus 24 triple permutations'}


def verify_candidate(path):
    # A restricted-language worker with a wall timeout; this is not an OS sandbox.
    path = Path(path).resolve()
    try:
        result = subprocess.run([sys.executable, '-I', '-B', str(Path(__file__).resolve()),
                                 '--worker', str(path)], text=True, capture_output=True, timeout=10)
    except subprocess.TimeoutExpired:
        return {'acceptance_state': 'UNKNOWN', 'error': 'verifier timeout'}
    if result.returncode:
        return {'acceptance_state': 'UNKNOWN', 'error': 'verifier worker failed',
                'stderr': result.stderr[-2000:]}
    try:
        report = json.loads(result.stdout)
    except json.JSONDecodeError:
        return {'acceptance_state': 'UNKNOWN', 'error': 'invalid verifier output'}
    report['checker_sha256'] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    report['candidate_sha256'] = hashlib.sha256(path.read_bytes()).hexdigest()
    return report


if __name__ == '__main__':
    if len(sys.argv) == 3 and sys.argv[1] == '--worker':
        print(json.dumps(run_checks(sys.argv[2])))
    elif len(sys.argv) == 2:
        print(json.dumps(verify_candidate(sys.argv[1]), indent=2))
    else:
        raise SystemExit('Usage: python3 -m verifier.check CANDIDATE')
