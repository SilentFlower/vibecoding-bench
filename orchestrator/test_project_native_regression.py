"""固定原生集合的实现路径、控制恢复与候选导入回归。"""
from contextlib import ExitStack
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import project_native_regression as regression


class NativeRegressionTests(unittest.TestCase):
    """验证 src 布局适配不会放宽原版测试和实际导入的约束。"""

    def test_src_overlay_restores_baseline_tests_and_controls(self) -> None:
        """候选只替换实现，删除测试和改写配置不能缩减原版集合。@return None。"""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            baseline, candidate, destination = (root / name for name in ('baseline', 'candidate', 'runtime'))
            for source in (baseline, candidate):
                (source / 'src/jinja2').mkdir(parents=True)
            (baseline / 'src/jinja2/__init__.py').write_text('VERSION = 1\n')
            (baseline / 'src/jinja2/conftest.py').write_text('ORIGINAL = True\n')
            (baseline / 'tests').mkdir()
            (baseline / 'tests/test_original.py').write_text('def test_original():\n    assert True\n')
            (baseline / 'pyproject.toml').write_text('[tool.pytest.ini_options]\ntestpaths = ["tests"]\n')
            (candidate / 'src/jinja2/__init__.py').write_text('VERSION = 2\n')
            (candidate / 'src/jinja2/conftest.py').write_text('CHANGED = True\n')
            (candidate / 'test_added.py').write_text('raise RuntimeError("must not collect")\n')
            report = regression._overlay(baseline, candidate, destination, regression.SUITES['jinja'])
            self.assertEqual((destination / 'src/jinja2/__init__.py').read_text(), 'VERSION = 2\n')
            self.assertEqual((destination / 'src/jinja2/conftest.py').read_bytes(),
                (baseline / 'src/jinja2/conftest.py').read_bytes())
            self.assertEqual((destination / 'tests/test_original.py').read_bytes(),
                (baseline / 'tests/test_original.py').read_bytes())
            self.assertEqual((destination / 'pyproject.toml').read_bytes(), (baseline / 'pyproject.toml').read_bytes())
            self.assertFalse((destination / 'test_added.py').exists())
            self.assertEqual(report['mode'], 'implementation-overlay')

    def test_src_overlay_rejects_new_pytest_hook(self) -> None:
        """实现包中新增收集控制必须拒绝，不能影响冻结测试。@return None。"""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in ('baseline', 'candidate'):
                (root / name / 'src/jinja2').mkdir(parents=True)
                (root / name / 'src/jinja2/__init__.py').write_text('VERSION = 1\n')
            (root / 'candidate/src/jinja2/hooks.py').write_text('def pytest_collection_modifyitems(items):\n    items.clear()\n')
            with self.assertRaises(regression.CandidateViolation):
                regression._overlay(root / 'baseline', root / 'candidate', root / 'runtime', regression.SUITES['jinja'])

    def test_legacy_suite_keeps_package_root_defaults(self) -> None:
        """旧三仓仍使用原包目录和项目根导入。@return None。"""
        for name in ('python-frontmatter', 'pydantic-settings', 'typer'):
            suite = regression.SUITES[name]
            self.assertEqual(regression._suite_paths(suite), (Path(suite['package']), Path('.')))

    def test_src_overlay_rejects_linked_parent(self) -> None:
        """src 父目录也必须属于候选，不能沿链接读入另一份实现。@return None。"""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'baseline/src/jinja2').mkdir(parents=True)
            (root / 'external/jinja2').mkdir(parents=True)
            (root / 'candidate').mkdir()
            (root / 'candidate/src').symlink_to(root / 'external', target_is_directory=True)
            with self.assertRaises(regression.CandidateViolation):
                regression._overlay(root / 'baseline', root / 'candidate', root / 'runtime', regression.SUITES['jinja'])

    def test_suite_paths_reject_escape_and_module_mismatch(self) -> None:
        """路径不能逃出项目或把文件路径当成导入模块。@return None。"""
        for changes in ({'implementation_dir': '../jinja2'}, {'import_root': '/installed'},
                {'package': 'src/jinja2'}, {'implementation_dir': 'other/jinja2'}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                regression._suite_paths({**regression.SUITES['jinja'], **changes})

    def test_imported_installation_is_rejected(self) -> None:
        """安装库即使可导入也不能替代候选实现。@return None。"""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project, installed = root / 'project', root / 'site-packages/jinja2'
            project.mkdir()
            installed.mkdir(parents=True)
            origin = installed / '__init__.py'
            origin.write_text('VERSION = 1\n')
            state = {'control': {'project': str(project), 'package': 'jinja2', 'documents': {}},
                'errors': [], 'imports': {}}
            with patch.object(regression, '_state', return_value=state), \
                    patch.object(regression.importlib, 'import_module', return_value=SimpleNamespace(__file__=str(origin))):
                with self.assertRaises(ValueError):
                    regression.pytest_sessionstart(None)
            self.assertTrue(state['errors'])
            self.assertEqual(state['imports'], {})

    def test_dotenv_console_binds_src_and_cleans_private_files(self) -> None:
        """真实命令入口绑定src候选，并在本次验证结束移除。@return None。"""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            venv, purelib = root / 'python', root / 'python/lib/site-packages'
            purelib.mkdir(parents=True)
            (venv / 'bin').mkdir()
            with patch.object(regression, '_WORK_ROOT', root), \
                    patch.object(regression.sys, 'prefix', str(venv)), \
                    patch.object(regression.sys, 'base_prefix', '/system'), \
                    patch.object(regression.sys, 'executable', str(venv / 'bin/python')), \
                    patch.object(regression.sysconfig, 'get_path', return_value=str(purelib)):
                with ExitStack() as cleanup:
                    result = regression._bind_source(root / 'project', Path('src'), cleanup, console=True)
                    path_file, console = Path(result['path_file']), Path(result['console']['path'])
                    self.assertEqual(path_file.read_text(), str(root / 'project/src') + '\n')
                    self.assertIn('from dotenv.__main__ import cli', console.read_text())
                    self.assertEqual(console.stat().st_mode & 0o777, 0o755)
                    self.assertEqual(result['console']['target'], 'dotenv.__main__:cli')
                self.assertFalse(path_file.exists())
                self.assertFalse(console.exists())

    def test_dotenv_console_does_not_replace_existing_entry(self) -> None:
        """未知安装入口必须拒绝且原字节不变，已建路径文件仍清理。@return None。"""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            venv, purelib = root / 'python', root / 'python/lib/site-packages'
            purelib.mkdir(parents=True)
            (venv / 'bin').mkdir()
            entry = venv / 'bin/dotenv'
            entry.write_text('original entry\n')
            with patch.object(regression, '_WORK_ROOT', root), \
                    patch.object(regression.sys, 'prefix', str(venv)), \
                    patch.object(regression.sys, 'base_prefix', '/system'), \
                    patch.object(regression.sysconfig, 'get_path', return_value=str(purelib)):
                with self.assertRaises(RuntimeError), ExitStack() as cleanup:
                    regression._bind_source(root / 'project', Path('src'), cleanup, console=True)
            self.assertEqual(entry.read_text(), 'original entry\n')
            self.assertEqual(list(purelib.glob('*.pth')), [])

    def test_source_binding_rejects_system_or_external_venv(self) -> None:
        """绑定只能修改本轮work内的独占venv，不触碰系统或共享环境。@return None。"""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for prefix, base in [('/system', '/system'), ('/external/venv', '/system')]:
                with patch.object(regression, '_WORK_ROOT', root), \
                        patch.object(regression.sys, 'prefix', prefix), \
                        patch.object(regression.sys, 'base_prefix', base), \
                        patch.object(regression.sysconfig, 'get_path', return_value=prefix + '/lib'), \
                        self.assertRaises(RuntimeError), ExitStack() as cleanup:
                    regression._bind_source(root / 'project', Path('src'), cleanup, console=True)

    def test_subtests_keep_duplicate_contexts_and_failed_outcome(self) -> None:
        """相同上下文的多次子执行不能折叠，主项通过也不能掩盖子项失败。@return None。"""
        common = {'id': 'test_parent', 'when': 'call', 'wasxfail': False,
            'subtest_context': {'msg': None, 'kwargs': {}}}
        reports = [{**common, 'outcome': 'passed'}, {**common, 'outcome': 'failed'},
            {'id': 'test_parent', 'when': 'call', 'outcome': 'passed', 'wasxfail': False}]
        result = regression._subtest_results(reports, ['test_parent'])
        self.assertEqual([item['ordinal'] for item in result], [1, 2])
        self.assertEqual([item['outcome'] for item in result], ['passed', 'failed'])
        self.assertEqual(regression._node_results(reports, ['test_parent']), {'test_parent': 'failed'})

    def test_subtests_reject_unknown_parent_or_unserialized_context(self) -> None:
        """缺少真实主节点或无法稳定冻结的上下文必须明确拒绝。@return None。"""
        common = {'id': 'test_parent', 'when': 'call', 'outcome': 'passed', 'wasxfail': False,
            'subtest_context': {'msg': None, 'kwargs': {}}}
        for changes in ({'id': 'not_collected'}, {'when': 'setup'},
                {'subtest_context': {'msg': None, 'kwargs': {'value': object()}}}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                regression._subtest_results([{**common, **changes}], ['test_parent'])


if __name__ == '__main__':
    unittest.main()
