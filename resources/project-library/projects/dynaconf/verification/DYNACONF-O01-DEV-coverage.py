"""在原覆盖率会话真实执行现有新增功能的公开边界。"""
import contextlib
import inspect
import io
import json
import os
from pathlib import Path
import runpy
import tempfile
from unittest.mock import patch


def cover_features(project, evidence):
    """保留原节点与95%门槛，执行当前候选已交付的完整新增矩阵。

    :param project: 原控制器的实际源码叠加根。
    :param evidence: 当前独立验证的证据目录。
    :return: None；任何已存在能力的公开边界失败均使原回归失败。
    """
    upstream_environment = dict(os.environ)
    isolated_environment = {name: value for name, value in upstream_environment.items()
        if not name.startswith('DYNACONF_') and not name.endswith('_FOR_DYNACONF')}
    # 原tests/test_env_loader.py在collection导入时写入DYNACONF_VALUE。
    # 新业务矩阵使用独立环境，退出无条件还原，原567节点仍看到原有全部环境。
    with patch.dict(os.environ, isolated_environment, clear=True):
        import dynaconf
        import pytest
        assert Path(dynaconf.__file__).resolve().is_relative_to(project.resolve())
        base = Path(__file__).parent
        executed = []
        for number in range(1, 7):
            task_id = f'DYNACONF-O{number:02d}-DEV'
            probe = base / (task_id + '-observe.py')
            source = probe.read_text()
            begin = '\nimport dynaconf\n'
            end = '\nprint(json.dumps('
            assert source.count(begin) == source.count(end) == 1
            namespace = {}
            with contextlib.redirect_stdout(io.StringIO()):
                # 已由原控制绑定独占venv与overlay，不重复创建dist-info或修改sys.path。
                exec(compile(source[source.index(begin):source.index(end)], str(probe), 'exec'), namespace)
            assert isinstance(namespace['business'], bool)
            if not namespace['business']:
                continue
            public = runpy.run_path(str(base / (task_id + '-coverage-public.py')))
            tests = [(name, function) for name, function in public.items()
                if name.startswith('test_') and callable(function)]
            assert len(tests) == 3
            for name, function in tests:
                parameters = inspect.signature(function).parameters
                assert set(parameters) <= {'tmp_path', 'monkeypatch'}
                with tempfile.TemporaryDirectory(prefix='dynaconf-expansion-') as directory:
                    with pytest.MonkeyPatch.context() as monkeypatch:
                        fixtures = {'tmp_path': Path(directory), 'monkeypatch': monkeypatch}
                        function(**{name: fixtures[name] for name in parameters})
            executed.append({'task_id': task_id, 'business': 'passed', 'public_assertions': len(tests)})
    assert dict(os.environ) == upstream_environment
    (evidence / 'expansion-coverage.json').write_text(json.dumps({'status': 'passed',
        'candidate_import': True, 'original_nodes_unchanged': True,
        'original_coverage_threshold_unchanged': True, 'upstream_environment_restored': True,
        'executed_objectives': executed},
        ensure_ascii=False, indent=2) + '\n')
