"""另跑上游完整Python实现集合，保留独立C构建主合同。"""
from hashlib import sha256
from importlib.util import module_from_spec, spec_from_file_location
from json import dumps
from os import environ
from pathlib import Path
from types import SimpleNamespace


def main() -> None:
    """实际切换Python实现，不省略原测试或mypy用例。@return None。"""
    source = Path(__file__).with_name('native_regression.py')
    specification = spec_from_file_location('_wrapt_python_original_control', source)
    if specification is None or specification.loader is None:
        raise ValueError('缺少已冻结可信runner')
    control = module_from_spec(specification)
    specification.loader.exec_module(control)
    suite = dict(control.SUITES['wrapt'])
    suite.pop('build_ext')
    suite.pop('native_modules')
    suite['env'] = {**suite['env'], 'WRAPT_DISABLE_EXTENSIONS': '1'}
    control.SUITES['wrapt'] = suite
    root = Path(environ['PROJECT_CANDIDATE_ROOT']).resolve()
    result = control._run(SimpleNamespace(project='wrapt', baseline_root=root / 'library',
        candidate_root=None, contract=None, freeze_baseline_contract=Path('/evidence/python-contract.json'),
        evidence_dir=Path('/evidence/python'), timeout_sec=300))
    observed = [row for worker in result.get('imports', {}).values() for row in worker.values()]
    passed = (result['status'] == 'passed' and bool(observed)
        and all(Path(row['path']).is_relative_to(Path(result['cwd'])) for row in observed)
        and result['counts']['passed'] > 0 and result.get('subtest_count', 0) > 0)
    print(dumps({'status': 'passed' if passed else 'failed', 'candidate_import': bool(observed),
        'passed': result['counts']['passed'], 'collected': result['collected'],
        'strict_doctest_count': result['strict_doctest_count'], 'counts': result['counts'],
        'runner_sha256': sha256(source.read_bytes()).hexdigest(), 'imports': result.get('imports'),
        'subtest_count': result.get('subtest_count'), 'mode_environment': suite['env'],
        'scope': '固定原版独立Python实现完整集合；主合同另从真实候选强制构建C扩展'}))


if __name__ == '__main__':
    main()
