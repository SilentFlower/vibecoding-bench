"""沿独立tox文档入口验固定原版，保留上游文档、README与模块示例完整入口。"""
from hashlib import sha256
from importlib.util import module_from_spec, spec_from_file_location
from json import dumps
from os import environ
from pathlib import Path
from types import SimpleNamespace


def main() -> None:
    """同一可信runner在独立进程执行完整包doctest，不修改主合同。@return None。"""
    source = Path(__file__).with_name('native_regression.py')
    specification = spec_from_file_location('_natsort_original_doctest_control', source)
    if specification is None or specification.loader is None:
        raise ValueError('缺少已冻结可信runner')
    control = module_from_spec(specification)
    specification.loader.exec_module(control)
    control.SUITES['natsort'] = {**control.SUITES['natsort'],
        'args': ['--doctest-modules', '--doctest-glob=*.rst', 'natsort', 'README.rst', 'docs/examples.rst', 'docs/howitworks.rst', '-o', 'doctest_optionflags=IGNORE_EXCEPTION_DETAIL', '-q', '-ra', '-p', 'no:cacheprovider']}
    control.SUITES['natsort'].pop('doctests')
    root = Path(environ['PROJECT_CANDIDATE_ROOT']).resolve()
    result = control._run(SimpleNamespace(project='natsort', baseline_root=root / 'library',
        candidate_root=None, contract=None, freeze_baseline_contract=Path('/evidence/docs-contract.json'),
        evidence_dir=Path('/evidence/docs'), timeout_sec=150))
    observed = [row for worker in result.get('imports', {}).values() for row in worker.values()]
    passed = (result['status'] == 'passed' and bool(observed)
        and all(Path(row['path']).is_relative_to(Path(result['cwd'])) for row in observed)
        and result['strict_doctest_count'] == result['collected'] > 0)
    print(dumps({'status': 'passed' if passed else 'failed', 'candidate_import': bool(observed),
        'passed': result['counts']['passed'], 'collected': result['collected'],
        'strict_doctest_count': result['strict_doctest_count'], 'counts': result['counts'],
        'runner_sha256': sha256(source.read_bytes()).hexdigest(),
        'native_build': result.get('native_build'), 'imports': result.get('imports'),
        'scope': '固定原版独立官方doctest集合；不替代可修改候选累计回归'}))


if __name__ == '__main__':
    main()
