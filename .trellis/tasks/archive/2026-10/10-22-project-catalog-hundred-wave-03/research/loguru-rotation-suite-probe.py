"""在完整轮转文件内只观察固定用例的真实调用，不改断言、时钟或结果。"""
from hashlib import sha256
from importlib.util import module_from_spec, spec_from_file_location
from json import dumps
from os import environ
from pathlib import Path
from types import SimpleNamespace


OBSERVER = '''

def _rotation_profile(frame, event, argument):
    """只在目标轮转调用返回时读取真实参数和文件状态。"""
    if event != 'return' or frame.f_code.co_name != '__call__' or frame.f_code.co_filename.split('/')[-1] != '_file_sink.py':
        return
    owner = frame.f_locals.get('self')
    if type(owner).__qualname__ != 'Rotation.RotationTime':
        return
    try:
        message = frame.f_locals['message']
        target = Path(frame.f_locals['file'].name)
        rows = _state().setdefault('rotation_clock_observations', [])
        module = importlib.import_module('loguru._ctime_functions')
        rows.append({'message':message.record['message'], 'record_time':message.record['time'].isoformat(),
            'wall_time':time.time(), 'limit':str(owner._limit), 'rotates':argument,
            'files':[{'name':p.name,'contents':p.read_text(),'ctime':module.get_ctime(str(p)),
                'mtime':p.stat().st_mtime} for p in sorted(target.parent.iterdir())]})
    except Exception as error:
        _state().setdefault('rotation_clock_observation_errors', []).append(type(error).__name__+':'+str(error))


def pytest_runtest_setup(item):
    """仅为两个已知真实轮转用例安装只读取证。"""
    if 'test_time_rotation_reopening_native' in item.nodeid:
        sys.setprofile(_rotation_profile)


def pytest_runtest_teardown(item):
    """原测试完成后移除本次取证。"""
    if 'test_time_rotation_reopening_native' in item.nodeid:
        sys.setprofile(None)
'''


def main() -> None:
    """运行原始轮转文件以定位完整基线的失败，不将诊断当正式准入。@return None。"""
    source = Path(__file__).with_name('native_regression.py')
    derived = Path('/work/loguru_rotation_diagnostic_control.py')
    derived.write_text(source.read_text() + OBSERVER)
    specification = spec_from_file_location('_loguru_rotation_diagnostic', derived)
    if specification is None or specification.loader is None:
        raise ValueError('诊断控制无法加载')
    control = module_from_spec(specification)
    specification.loader.exec_module(control)
    control.SUITES['loguru'] = {**control.SUITES['loguru'],
        'args': ['tests/test_filesink_rotation.py', '--cov=loguru/', '--cov-report=', '-q', '-ra', '-p', 'no:cacheprovider']}
    root = Path(environ['PROJECT_CANDIDATE_ROOT']).resolve()
    result = control._run(SimpleNamespace(project='loguru', baseline_root=root / 'library',
        candidate_root=None, contract=None, freeze_baseline_contract=Path('/evidence/diagnostic-contract.json'),
        evidence_dir=Path('/evidence/diagnostic'), timeout_sec=150))
    raw = control._json(Path('/evidence/diagnostic/pytest-master.json'))
    print(dumps({'status': 'passed', 'candidate_import': bool(result.get('imports')),
        'native_status': result['status'], 'native_counts': result['counts'],
        'runner_sha256': sha256(source.read_bytes()).hexdigest(),
        'diagnostic_runner_sha256': sha256(derived.read_bytes()).hexdigest(),
        'observations': raw.get('rotation_clock_observations'),
        'observation_errors': raw.get('rotation_clock_observation_errors', []),
        'scope': 'passed仅表示只读取证结束；文件内原始断言的结果单列，不代表完整原生通过'}))


if __name__ == '__main__':
    main()
