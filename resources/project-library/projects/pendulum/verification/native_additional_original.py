"""独立运行固定原版Python路径的完整集合，与Rust原件入口分开记账。"""
from hashlib import sha256
from importlib.util import module_from_spec, spec_from_file_location
from json import dumps, loads
from os import environ
from pathlib import Path
from subprocess import run
from sys import executable
from types import SimpleNamespace


def main() -> None:
    """沿上游明确的PENDULUM_EXTENSIONS=0模式核完整原始测试。@return None。"""
    source = Path(__file__).with_name('native_regression.py')
    specification = spec_from_file_location('_pendulum_python_original_control', source)
    if specification is None or specification.loader is None:
        raise ValueError('缺少已冻结可信runner')
    control = module_from_spec(specification)
    specification.loader.exec_module(control)
    suite = dict(control.SUITES['pendulum'])
    suite.pop('native_modules')
    suite['env'] = {**suite['env'], 'PENDULUM_EXTENSIONS': '0'}
    control.SUITES['pendulum'] = suite
    root = Path(environ['PROJECT_CANDIDATE_ROOT']).resolve()
    binding = run([executable, '-I', '-B', '-c', '''import json,sys
from pathlib import Path
sys.path.insert(0,sys.argv[1])
import pendulum,pendulum.helpers,pendulum.parsing
print(json.dumps({'package':str(Path(pendulum.__file__).resolve()),
 'helpers':pendulum.helpers.is_leap.__module__,
 'parser':pendulum.parsing.parse_iso8601.__module__}))
''', str(root / 'library/src')], env={**environ, 'PENDULUM_EXTENSIONS': '0'},
        capture_output=True, text=True, check=True, timeout=20)
    bound = loads(binding.stdout)
    result = control._run(SimpleNamespace(project='pendulum', baseline_root=root / 'library',
        candidate_root=None, contract=None, freeze_baseline_contract=Path('/evidence/python-contract.json'),
        evidence_dir=Path('/evidence/python'), timeout_sec=150))
    observed = [row for worker in result.get('imports', {}).values() for row in worker.values()]
    passed = (result['status'] == 'passed' and bool(observed) and result['collected'] == 1874
        and bound == {'package': str(root / 'library/src/pendulum/__init__.py'),
            'helpers': 'pendulum._helpers', 'parser': 'pendulum.parsing.iso8601'}
        and all(Path(row['path']).is_relative_to(Path(result['cwd'])) for row in observed))
    print(dumps({'status': 'passed' if passed else 'failed', 'candidate_import': bool(observed),
        'passed': result['counts']['passed'], 'collected': result['collected'],
        'strict_doctest_count': result['strict_doctest_count'], 'counts': result['counts'],
        'runner_sha256': sha256(source.read_bytes()).hexdigest(), 'imports': result.get('imports'),
        'mode_environment': suite['env'], 'python_binding': bound,
        'scope': '固定原版独立Python实现完整集合；主合同另验固定Rust运行原件，不声称本轮重新构建Rust'}))


if __name__ == '__main__':
    main()
