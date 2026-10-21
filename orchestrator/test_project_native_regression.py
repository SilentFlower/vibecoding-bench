"""固定原生集合的实现路径、控制恢复与候选导入回归。"""
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


if __name__ == '__main__':
    unittest.main()
