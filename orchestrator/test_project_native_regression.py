"""固定原生集合的实现路径、控制恢复与候选导入回归。"""
from contextlib import ExitStack
import hashlib
from importlib.util import find_spec
import json
import os
import subprocess
import sys
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

    def test_package_embedded_tests_and_fixtures_are_frozen(self) -> None:
        """包内实现可更新，但候选改删原测试、夹具或新增测试均不缩减冻结证明。@return None。"""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            baseline, candidate = root / 'baseline', root / 'candidate'
            for path in (baseline, candidate):
                (path / 'toolz/tests').mkdir(parents=True)
            (baseline / 'toolz/__init__.py').write_text('VALUE = 1\n')
            (candidate / 'toolz/__init__.py').write_text('VALUE = 2\n')
            (baseline / 'toolz/tests/test_original.py').write_text('def test_original():\n    assert False\n')
            (candidate / 'toolz/tests/test_original.py').write_text('def test_original():\n    assert True\n')
            (baseline / 'toolz/tests/input.txt').write_text('original fixture\n')
            (candidate / 'toolz/tests/test_added.py').write_text('raise RuntimeError("must not collect")\n')
            regression._overlay(baseline, candidate, root / 'runtime', regression.SUITES['toolz'])
            self.assertEqual((root / 'runtime/toolz/__init__.py').read_text(), 'VALUE = 2\n')
            for name in ('test_original.py', 'input.txt'):
                self.assertEqual((root / 'runtime/toolz/tests' / name).read_bytes(),
                    (baseline / 'toolz/tests' / name).read_bytes())
            self.assertFalse((root / 'runtime/toolz/tests/test_added.py').exists())
            with self.assertRaises(ValueError):
                regression._overlay(baseline, candidate, root / 'invalid',
                    {**regression.SUITES['toolz'], 'test_roots': ['../outside']})

    def test_module_overlay_keeps_original_tests_and_configuration(self) -> None:
        """单文件替换不能删原生测试、改配置或带入新增测试。@return None。"""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            baseline, candidate, destination = (root / name for name in ('baseline', 'candidate', 'runtime'))
            baseline.mkdir()
            candidate.mkdir()
            (baseline / 'xmltodict.py').write_text('VALUE = 1\n')
            (baseline / 'test_original.py').write_text('def test_original():\n    assert True\n')
            (baseline / 'pyproject.toml').write_text('[tool.pytest.ini_options]\ntestpaths = ["."]\n')
            (candidate / 'xmltodict.py').write_text('VALUE = 2\n')
            (candidate / 'pyproject.toml').write_text('[tool.pytest.ini_options]\naddopts = "--ignore=test_original.py"\n')
            (candidate / 'test_added.py').write_text('raise RuntimeError("must not collect")\n')
            suite = {'package': 'xmltodict', 'implementation_dir': 'xmltodict.py', 'overlay': True}
            report = regression._overlay(baseline, candidate, destination, suite)
            self.assertEqual((destination / 'xmltodict.py').read_text(), 'VALUE = 2\n')
            self.assertEqual((destination / 'test_original.py').read_bytes(),
                (baseline / 'test_original.py').read_bytes())
            self.assertEqual((destination / 'pyproject.toml').read_bytes(), (baseline / 'pyproject.toml').read_bytes())
            self.assertFalse((destination / 'test_added.py').exists())
            self.assertEqual(report['mode'], 'implementation-overlay')

    def test_module_overlay_rejects_pytest_controls_and_links(self) -> None:
        """单文件同样拒绝收集钩子、插件注入和指向其他实现的链接。@return None。"""
        changes = ['def pytest_collection_modifyitems(items):\n    items.clear()\n', 'pytest_plugins = []\n', None]
        for content in changes:
            with self.subTest(content=content), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                baseline, candidate = root / 'baseline', root / 'candidate'
                baseline.mkdir()
                candidate.mkdir()
                (baseline / 'xmltodict.py').write_text('VALUE = 1\n')
                if content is None:
                    (root / 'external.py').write_text('VALUE = 2\n')
                    (candidate / 'xmltodict.py').symlink_to(root / 'external.py')
                else:
                    (candidate / 'xmltodict.py').write_text(content)
                suite = {'package': 'xmltodict', 'implementation_dir': 'xmltodict.py', 'overlay': True}
                with self.assertRaises(regression.CandidateViolation):
                    regression._overlay(baseline, candidate, root / 'runtime', suite)

    def test_module_paths_require_the_exact_import_name(self) -> None:
        """只接受导入模块对应的py文件，不能借单文件支持改指其他源码。@return None。"""
        suite = {'package': 'decouple', 'import_root': 'src', 'implementation_dir': 'src/decouple.py'}
        self.assertEqual(regression._suite_paths(suite), (Path('src/decouple.py'), Path('src')))
        for implementation in ('src/other.py', 'decouple.py', '../src/decouple.py'):
            with self.subTest(implementation=implementation), self.assertRaises(ValueError):
                regression._suite_paths({**suite, 'implementation_dir': implementation})

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

    def test_tabulate_doctest_text_is_restored_from_frozen_source(self) -> None:
        """候选不能修改函数示例后用相同节点名掩盖原版doctest失败。@return None。"""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            baseline, project = root / 'baseline', root / 'project'
            for source in (baseline, project):
                (source / 'tabulate').mkdir(parents=True)
            expected = '>>> render()\n1'
            (baseline / 'tabulate/__init__.py').write_text(
                'def render():\n    """>>> render()\n1"""\n    return 1\n')
            origin = project / 'tabulate/__init__.py'
            origin.write_text('VALUE = "candidate"\n')
            documents = regression._documents(baseline, 'tabulate')
            self.assertEqual(documents['tabulate']['render'], expected)

            def render() -> str:
                """候选伪造的示例文本。@return 候选结果。"""
                return 'candidate'

            module = SimpleNamespace(__file__=str(origin), render=render)
            state = {'control': {'project': str(project), 'package': 'tabulate', 'documents': documents},
                'errors': [], 'imports': {}}
            with patch.object(regression, '_state', return_value=state), \
                    patch.object(regression.importlib, 'import_module', return_value=module):
                regression.pytest_sessionstart(None)
            self.assertEqual(render.__doc__, expected)
            self.assertEqual(state['imports']['tabulate']['path'], str(origin))

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

    def test_multiple_doctest_modules_use_frozen_names_and_examples(self) -> None:
        """多模块doctest须恢复各自原文，不能把不同模块都映射为同一个名称。@return None。"""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'boltons/nested').mkdir(parents=True)
            (root / 'boltons/__init__.py').write_text('VERSION = 1\n')
            (root / 'boltons/first.py').write_text('def value():\n    """>>> value()\n1"""\n    return 1\n')
            (root / 'boltons/nested/__init__.py').write_text('""">>> 2 + 2\n4"""\n')
            documents = regression._documents(root, 'boltons')
            self.assertEqual(documents['boltons.first']['value'], '>>> value()\n1')
            self.assertEqual(documents['boltons.nested'][''], '>>> 2 + 2\n4')
            self.assertNotIn('boltons.default_handlers', documents)

    def test_dynamic_frozen_doctest_exports_use_actual_runtime_names(self) -> None:
        """冻结原版动态导出函数时，应恢复实际导出名而非已删除的类内定义。@return None。"""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'boltons').mkdir()
            (root / 'boltons/__init__.py').write_text('VERSION = 1\n')
            (root / 'boltons/statsutils.py').write_text(
                'class Stats:\n'
                '    def _calc_value(self):\n'
                '        """>>> value()\n1"""\n'
                '        return 1\n'
                'def value():\n'
                '    return 1\n'
                'value.__doc__ = Stats._calc_value.__doc__\n'
                'del Stats._calc_value\n')
            documents = regression._documents(root, 'boltons')
            self.assertEqual(documents['boltons.statsutils']['value'], '>>> value()\n1')
            self.assertNotIn('Stats._calc_value', documents['boltons.statsutils'])

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

    def test_private_distribution_metadata_keeps_candidate_path_and_cleans_up(self) -> None:
        """版本查询只补固定元数据，不能安装另一份代码或遗留到共享环境。@return None。"""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            venv, purelib = root / 'python', root / 'python/lib/site-packages'
            purelib.mkdir(parents=True)
            with patch.object(regression, '_WORK_ROOT', root), \
                    patch.object(regression.sys, 'prefix', str(venv)), \
                    patch.object(regression.sys, 'base_prefix', '/system'), \
                    patch.object(regression.sysconfig, 'get_path', return_value=str(purelib)):
                with ExitStack() as cleanup:
                    result = regression._bind_source(root / 'project', Path('src'), cleanup,
                        distribution=('click', '8.6.0.dev'))
                    metadata = Path(result['distribution']['path'])
                    self.assertIn('Version: 8.6.0.dev\n', (metadata / 'METADATA').read_text())
                    self.assertFalse(result['distribution']['implementation_installed'])
                    self.assertFalse((purelib / 'click').exists())
                    self.assertEqual(Path(result['path_file']).read_text(), str(root / 'project/src') + '\n')
                self.assertFalse(metadata.exists())
                self.assertEqual(list(purelib.iterdir()), [])

    def test_private_metadata_preserves_local_version_and_license_without_installing_code(self) -> None:
        """原生元数据查询应获得真实本地版本与许可，同时拒绝注入额外元数据字段。@return None。"""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            venv, purelib = root / 'python', root / 'python/lib/site-packages'
            purelib.mkdir(parents=True)
            with patch.object(regression, '_WORK_ROOT', root), \
                    patch.object(regression.sys, 'prefix', str(venv)), \
                    patch.object(regression.sys, 'base_prefix', '/system'), \
                    patch.object(regression.sysconfig, 'get_path', return_value=str(purelib)):
                with ExitStack() as cleanup:
                    result = regression._bind_source(root / 'project', Path('.'), cleanup,
                        distribution=('jsonschema', '0.1.dev1+gc497561ea'), license_expression='MIT')
                    metadata = Path(result['distribution']['path']) / 'METADATA'
                    self.assertIn('Version: 0.1.dev1+gc497561ea\n', metadata.read_text())
                    self.assertIn('License-Expression: MIT\n', metadata.read_text())
                    self.assertFalse((purelib / 'jsonschema').exists())
                with self.assertRaises(ValueError), ExitStack() as cleanup:
                    regression._bind_source(root / 'project', Path('.'), cleanup,
                        distribution=('jsonschema', '0.1.dev1+gc497561ea'), license_expression='MIT\nName: different')
                self.assertEqual(list(purelib.iterdir()), [])

    def test_offline_executable_is_verified_and_bound_only_inside_private_venv(self) -> None:
        """真实离线工具须校验字节，只在已有可执行work内使用，结束后移除。@return None。"""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            venv, purelib = root / 'python', root / 'python/lib/site-packages'
            purelib.mkdir(parents=True)
            (venv / 'bin').mkdir()
            offline = root / 'offline'
            offline.mkdir()
            contents = b'#!/bin/sh\nexit 0\n'
            (offline / 'pager').write_bytes(contents)
            checksum = hashlib.sha256(contents).hexdigest()
            with patch.object(regression, '_WORK_ROOT', root), \
                    patch.object(regression, '_OFFLINE_ROOT', offline), \
                    patch.object(regression.sys, 'prefix', str(venv)), \
                    patch.object(regression.sys, 'base_prefix', '/system'), \
                    patch.object(regression.sysconfig, 'get_path', return_value=str(purelib)):
                with ExitStack() as cleanup:
                    result = regression._bind_source(root / 'project', Path('.'), cleanup,
                        executables=[('pager', 'pager', checksum)])
                    entry = Path(result['executables'][0]['path'])
                    self.assertEqual(entry.read_bytes(), contents)
                    self.assertEqual(entry.stat().st_mode & 0o777, 0o755)
                self.assertFalse(entry.exists())
                for relative, digest in [('pager', '0' * 64), ('../pager', checksum)]:
                    with self.assertRaises(ValueError), ExitStack() as cleanup:
                        regression._bind_source(root / 'project', Path('.'), cleanup,
                            executables=[('pager', relative, digest)])
                entry.write_bytes(b'existing entry')
                with self.assertRaises(FileExistsError), ExitStack() as cleanup:
                    regression._bind_source(root / 'project', Path('.'), cleanup,
                        executables=[('pager', 'pager', checksum)])
                self.assertEqual(entry.read_bytes(), b'existing entry')

    def test_doctest_restore_updates_underlying_classmethod_function(self) -> None:
        """类方法绑定对象的只读文档不能阻断原版示例恢复。@return None。"""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            origin = root / 'boltons/factory.py'
            origin.parent.mkdir()
            origin.write_text('VALUE = 1\n')

            class Factory:
                """模拟真实库的类方法文档入口。"""

                @classmethod
                def make(cls):
                    """候选改写的示例。@return 新实例。"""
                    return cls()

            module = SimpleNamespace(__file__=str(origin), Factory=Factory)
            package = SimpleNamespace(__file__=str(origin))
            expected = '>>> Factory.make()\nexample'
            state = {'control': {'project': str(root), 'package': 'boltons',
                'documents': {'boltons.factory': {'Factory.make': expected}}}, 'errors': [], 'imports': {}}
            modules = {'boltons': package, 'boltons.factory': module}
            with patch.object(regression, '_state', return_value=state), \
                    patch.object(regression.importlib, 'import_module', side_effect=modules.__getitem__):
                regression.pytest_sessionstart(None)
            self.assertEqual(Factory.make.__doc__, expected)

    def test_dynamic_class_doc_restore_preserves_instance_descriptor(self) -> None:
        """类文档恢复后实例仍按原描述符生成自身文档，不能被类字符串遮蔽。@return None。"""
        class InstanceProperty(property):
            """模拟已核Toolz原生描述符的类／实例区别。"""

            __module__ = 'toolz.functoolz'

            def __init__(self, getter, classval):
                """保存原生类文档值。@param getter 实例访问器。@param classval 类文档。@return None。"""
                self.classval = classval
                super().__init__(getter)

            def __get__(self, instance, owner=None):
                """按实际访问对象返回原生值。@param instance 实例。@param owner 所有者。@return 文档。"""
                return self.classval if instance is None else super().__get__(instance, owner)

        class Wrapped:
            """模拟使用动态实例文档的真实API类。"""

            def instance_document(self):
                """提供实例自身文档。@return 动态文档。"""
                return 'instance-specific document'

            __doc__ = InstanceProperty(instance_document, 'candidate class example')

        descriptor = vars(Wrapped)['__doc__']
        regression._restore_document(Wrapped, 'frozen class example')
        self.assertIs(vars(Wrapped)['__doc__'], descriptor)
        self.assertEqual(Wrapped.__doc__, 'frozen class example')
        self.assertEqual(Wrapped().__doc__, 'instance-specific document')

    def test_collection_skips_are_separate_from_collected_tests_and_frozen(self) -> None:
        """真实pytest的模块收集跳过与主项分别冻结，XML总数保留两者。@return None。"""
        suite = {'package': 'sample', 'overlay': True, 'doctests': 0, 'collection_skips': True,
            'args': ['tests', '-q', '-p', 'no:cacheprovider'], 'plugins': [], 'env': {}}
        with tempfile.TemporaryDirectory() as directory, patch.dict(regression.SUITES, {'fixture-collection': suite}):
            root = Path(directory)
            baseline, candidate = root / 'baseline', root / 'candidate/library'
            for path in (baseline, candidate):
                (path / 'sample').mkdir(parents=True)
                (path / 'sample/__init__.py').write_text('VALUE = 1\n')
            (baseline / 'tests').mkdir()
            (baseline / 'tests/test_core.py').write_text('import sample\ndef test_value():\n    assert sample.VALUE == 1\n')
            (baseline / 'tests/test_optional.py').write_text(
                'import pytest\npytest.importorskip("bench_missing_optional_dependency_48172")\n')
            contract_path = root / 'contract.json'
            options = SimpleNamespace(project='fixture-collection', baseline_root=baseline, candidate_root=None,
                contract=None, freeze_baseline_contract=contract_path, evidence_dir=root / 'original', timeout_sec=10)
            result = regression._run(options)
            self.assertEqual(result['status'], 'passed', result)
            self.assertEqual(result['collected'], 1)
            self.assertEqual(result['collection_skip_count'], 1)
            self.assertEqual(result['counts']['skipped'], 0)
            self.assertEqual(result['xml_testcases'], 2)
            self.assertEqual(result['xml_skipped'], 1)
            self.assertEqual(result['collection_skips'][0]['id'], 'tests/test_optional.py')
            options.contract, options.freeze_baseline_contract = contract_path, None
            options.candidate_root, options.evidence_dir = candidate.parent, root / 'candidate-evidence'
            self.assertEqual(regression._run(options)['status'], 'passed')
            contract = json.loads(contract_path.read_text())
            contract['collection_skips'][0]['reason'] = 'altered reason'
            contract_path.write_text(json.dumps(contract))
            options.evidence_dir = root / 'drift-evidence'
            self.assertEqual(regression._run(options)['status'], 'failed')
            del contract['collection_skips']
            contract_path.write_text(json.dumps(contract))
            with self.assertRaises(ValueError):
                regression._run(options)

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

    def test_unittest_keeps_original_nodes_rejects_wrong_code_and_changed_skip(self) -> None:
        """实际子进程发现原测试，拒绝错误实现、空集合和跳过理由漂移。@return None。"""
        suite = {'package': 'sample', 'overlay': True, 'framework': 'unittest', 'discover': 'tests',
            'doctests': 0, 'plugins': [], 'env': {}}
        with tempfile.TemporaryDirectory() as directory, patch.dict(regression.SUITES, {'fixture-unittest': suite}):
            root = Path(directory)
            baseline, candidate = root / 'baseline', root / 'candidate/library'
            for source in (baseline, candidate):
                (source / 'sample').mkdir(parents=True)
                (source / 'sample/__init__.py').write_text('VALUE = 1\nREASON = "upstream"\n')
            (baseline / 'tests').mkdir()
            (baseline / 'tests/test_original.py').write_text(
                'import unittest\nimport sample\n'
                'class Original(unittest.TestCase):\n'
                '    def test_value(self):\n        self.assertEqual(sample.VALUE, 1)\n'
                '    @unittest.skip(sample.REASON)\n'
                '    def test_optional(self):\n        self.fail("skip must stay visible")\n')
            contract_path = root / 'contract.json'
            options = SimpleNamespace(project='fixture-unittest', baseline_root=baseline, candidate_root=None,
                contract=None, freeze_baseline_contract=contract_path, evidence_dir=root / 'baseline-evidence', timeout_sec=10)
            original = regression._run(options)
            self.assertEqual(original['status'], 'passed', original)
            self.assertEqual(original['collected'], 2)
            self.assertEqual(original['counts']['skipped'], 1)
            self.assertEqual(original['xml_testcases'], 2)
            self.assertEqual(json.loads(contract_path.read_text())['unittest_skips'][0]['reason'], 'upstream')
            options.contract, options.freeze_baseline_contract = contract_path, None
            options.candidate_root = candidate.parent
            # 候选自己的测试与配置不进入受控原生树，原版测试始终完整执行。
            (candidate / 'tests').mkdir()
            (candidate / 'tests/test_original.py').write_text('raise RuntimeError("candidate test")\n')
            (candidate / 'tests/test_added.py').write_text('raise RuntimeError("added test")\n')
            options.evidence_dir = root / 'candidate-evidence'
            accepted = regression._run(options)
            self.assertEqual(accepted['status'], 'passed', accepted)
            self.assertEqual(accepted['collected'], 2)
            (candidate / 'sample/__init__.py').write_text('VALUE = 2\nREASON = "upstream"\n')
            options.evidence_dir = root / 'wrong-evidence'
            rejected = regression._run(options)
            self.assertEqual(rejected['status'], 'failed')
            self.assertEqual(rejected['counts']['failed'], 1)
            (candidate / 'sample/__init__.py').write_text('VALUE = 1\nREASON = "candidate"\n')
            options.evidence_dir = root / 'skip-evidence'
            self.assertEqual(regression._run(options)['status'], 'failed')
            empty = root / 'empty'
            (empty / 'sample').mkdir(parents=True)
            (empty / 'sample/__init__.py').write_text('VALUE = 1\n')
            (empty / 'tests').mkdir()
            options.baseline_root, options.contract = empty, None
            options.freeze_baseline_contract = root / 'empty-contract.json'
            options.evidence_dir = root / 'empty-evidence'
            self.assertEqual(regression._run(options)['status'], 'error')
            self.assertFalse(options.freeze_baseline_contract.exists())

    def test_unittest_subtest_failure_cannot_hide_behind_parent_success(self) -> None:
        """真实unittest子项断言失败必须拒绝冻结，不能依赖父项成功回调。@return None。"""
        suite = {'package': 'sample', 'overlay': True, 'framework': 'unittest', 'discover': 'tests',
            'doctests': 0, 'plugins': [], 'env': {}}
        with tempfile.TemporaryDirectory() as directory, patch.dict(regression.SUITES, {'fixture-unittest': suite}):
            root = Path(directory)
            (root / 'sample').mkdir()
            (root / 'sample/__init__.py').write_text('VALUE = 1\n')
            (root / 'tests').mkdir()
            (root / 'tests/test_original.py').write_text(
                'import unittest\n'
                'class Original(unittest.TestCase):\n'
                '    def test_value(self):\n'
                '        with self.subTest(value=2):\n            self.assertEqual(1, 2)\n')
            options = SimpleNamespace(project='fixture-unittest', baseline_root=root, candidate_root=None,
                contract=None, freeze_baseline_contract=root / 'contract.json', evidence_dir=root / 'evidence', timeout_sec=10)
            result = regression._run(options)
            self.assertEqual(result['status'], 'error')
            self.assertEqual(result['counts']['failed'], 1)
            self.assertFalse(options.freeze_baseline_contract.exists())

    @unittest.skipUnless(find_spec('nose2'), 'nose2仅在对应原生验证环境安装；专用环境另跑本项')
    def test_nose2_keeps_function_and_class_nodes_and_rejects_code_or_skip_drift(self) -> None:
        """实际nose2须保留函数和类用例、官方XML、预期失败及跳过理由，拒绝错误候选。@return None。"""
        suite = {'package': 'sample', 'overlay': True, 'framework': 'nose2', 'doctests': 0,
            'args': ['--no-user-config', '--plugin', 'nose2.plugins.junitxml', '--junit-xml'],
            'plugins': [], 'env': {}}
        with tempfile.TemporaryDirectory() as directory, patch.dict(regression.SUITES, {'fixture-nose2': suite}):
            root = Path(directory)
            baseline, candidate = root / 'baseline', root / 'candidate/library'
            for source in (baseline, candidate):
                (source / 'sample').mkdir(parents=True)
                (source / 'sample/__init__.py').write_text('VALUE = 1\nREASON = "original skip"\n')
            (baseline / 'tests').mkdir()
            (baseline / 'tests/__init__.py').write_text('')
            (baseline / 'tests/test_original.py').write_text(
                'import unittest\nimport sample\n'
                'def test_function():\n'
                '    """原生函数用例不能被unittest发现替代后遗漏。@return None。"""\n'
                '    assert sample.VALUE == 1\n'
                'class Original(unittest.TestCase):\n'
                '    """原生类用例包含成功、跳过和预期失败。"""\n'
                '    def test_value(self):\n'
                '        """核实际候选值。@return None。"""\n'
                '        self.assertEqual(sample.VALUE, 1)\n'
                '    @unittest.skip(sample.REASON)\n'
                '    def test_optional(self):\n'
                '        """保留真实跳过。@return None。"""\n'
                '        self.fail("must stay skipped")\n'
                '    @unittest.expectedFailure\n'
                '    def test_expected_failure(self):\n'
                '        """保留上游声明的预期失败。@return None。"""\n'
                '        self.fail("known upstream failure")\n')
            contract = root / 'contract.json'
            options = SimpleNamespace(project='fixture-nose2', baseline_root=baseline, candidate_root=None,
                contract=None, freeze_baseline_contract=contract, evidence_dir=root / 'original', timeout_sec=10)
            original = regression._run(options)
            self.assertEqual(original['status'], 'passed', original)
            self.assertEqual(original['collected'], 4)
            self.assertEqual(original['counts']['passed'], 2)
            self.assertEqual(original['counts']['skipped'], 1)
            self.assertEqual(original['counts']['xfailed'], 1)
            self.assertEqual(original['xml_testcases'], 4)
            self.assertEqual(original['xml_skipped'], 2)
            frozen = json.loads(contract.read_text())
            self.assertEqual(frozen['framework'], 'nose2')
            self.assertTrue(any(node['id'].endswith('test_function') for node in frozen['nodes']))
            self.assertEqual([plugin['module'] for plugin in frozen['plugins']],
                ['unittest', 'nose2', 'nose2.plugins.junitxml'])
            options.contract, options.freeze_baseline_contract = contract, None
            options.candidate_root, options.evidence_dir = candidate.parent, root / 'accepted'
            (candidate / 'tests').mkdir()
            (candidate / 'tests/test_original.py').write_text('raise RuntimeError("candidate tests cannot replace originals")\n')
            self.assertEqual(regression._run(options)['status'], 'passed')
            (candidate / 'sample/__init__.py').write_text('VALUE = 2\nREASON = "original skip"\n')
            options.evidence_dir = root / 'wrong-code'
            self.assertEqual(regression._run(options)['status'], 'failed')
            (candidate / 'sample/__init__.py').write_text('VALUE = 1\nREASON = "changed skip"\n')
            options.evidence_dir = root / 'changed-skip'
            self.assertEqual(regression._run(options)['status'], 'failed')
            frozen['framework'] = 'unittest'
            contract.write_text(json.dumps(frozen))
            with self.assertRaises(ValueError):
                regression._run(options)

    def test_unittest_subtests_keep_context_skips_and_nested_working_directory(self) -> None:
        """真实子项重复、局部跳过及临时路径均须可冻结，错误实现和理由漂移不能通过。@return None。"""
        suite = {'package': 'sample', 'implementation_dir': 'vendor/sample', 'import_root': 'vendor',
            'overlay': True, 'framework': 'unittest', 'discover': '.', 'cwd': 'vendor/test',
            'doctests': 0, 'subtests': True, 'plugins': [], 'env': {}}
        with tempfile.TemporaryDirectory() as directory, patch.dict(regression.SUITES, {'fixture-subtests': suite}):
            root = Path(directory)
            baseline, candidate = root / 'baseline', root / 'candidate/library'
            for source in (baseline, candidate):
                (source / 'vendor/sample').mkdir(parents=True)
                (source / 'vendor/sample/__init__.py').write_text('VALUE = 1\nREASON = "original reason"\n')
            (baseline / 'vendor/test').mkdir()
            (baseline / 'vendor/test/test_original.py').write_text(
                'import unittest\nfrom pathlib import Path\nimport sample\n'
                'class Original(unittest.TestCase):\n'
                '    def test_repeated(self):\n'
                '        for number in range(2):\n'
                '            with self.subTest(file=str(Path(__file__))):\n'
                '                self.assertEqual(sample.VALUE, 1)\n'
                '    def test_partial_skip(self):\n'
                '        with self.subTest(value="optional"):\n'
                '            self.skipTest(sample.REASON)\n'
                '        with self.subTest(value="required"):\n'
                '            self.assertEqual(sample.VALUE, 1)\n'
                '    @unittest.skip("parent unavailable")\n'
                '    def test_parent_skip(self):\n'
                '        self.fail("must stay skipped")\n')
            contract = root / 'contract.json'
            options = SimpleNamespace(project='fixture-subtests', baseline_root=baseline, candidate_root=None,
                contract=None, freeze_baseline_contract=contract, evidence_dir=root / 'original', timeout_sec=10)
            original = regression._run(options)
            self.assertEqual(original['status'], 'passed', original)
            self.assertEqual(original['collected'], 3)
            self.assertEqual(original['counts']['passed'], 2)
            self.assertEqual(original['counts']['skipped'], 1)
            self.assertEqual(original['xml_testcases'], 3)
            self.assertEqual(original['xml_skipped'], 1)
            self.assertEqual(original['subtest_count'], 4)
            self.assertEqual(sum(item['outcome'] == 'skipped' for item in original['subtests']), 1)
            repeated = [item for item in original['subtests'] if item['parent_nodeid'].endswith('test_repeated')]
            self.assertEqual([item['ordinal'] for item in repeated], [1, 2])
            self.assertEqual(repeated[0]['context'], repeated[1]['context'])
            self.assertIn('$PROJECT/vendor/test/test_original.py', repeated[0]['context']['kwargs']['file'])
            options.contract, options.freeze_baseline_contract = contract, None
            options.candidate_root, options.evidence_dir = candidate.parent, root / 'accepted'
            self.assertEqual(regression._run(options)['status'], 'passed')
            (candidate / 'vendor/sample/__init__.py').write_text('VALUE = 2\nREASON = "original reason"\n')
            options.evidence_dir = root / 'wrong-implementation'
            self.assertEqual(regression._run(options)['status'], 'failed')
            (candidate / 'vendor/sample/__init__.py').write_text('VALUE = 1\nREASON = "changed reason"\n')
            options.evidence_dir = root / 'changed-skip'
            self.assertEqual(regression._run(options)['status'], 'failed')

    def test_fixed_fixture_aliases_copy_current_target_and_reject_escape(self) -> None:
        """固定链接blob只在私有树还原数据，保持原件并拒绝文本漂移和链接越界。@return None。"""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            baseline, project = root / 'baseline', root / 'runtime'
            for source in (baseline, project):
                (source / 'tests').mkdir(parents=True)
                (source / 'styles').mkdir()
                (source / 'tests/style.css').write_text('../styles/style.css')
                (source / 'styles/style.css').write_text('original CSS')
            (project / 'styles/style.css').write_text('current candidate CSS')
            suite = {'fixture_aliases': [('tests/style.css', '../styles/style.css')]}
            report = regression._fixture_aliases(baseline, project, suite)
            self.assertEqual((baseline / 'tests/style.css').read_text(), '../styles/style.css')
            self.assertEqual((baseline / 'styles/style.css').read_text(), 'original CSS')
            self.assertEqual((project / 'tests/style.css').read_text(), 'current candidate CSS')
            self.assertFalse((project / 'tests/style.css').is_symlink())
            self.assertEqual(report[0]['target_sha256'], hashlib.sha256(b'current candidate CSS').hexdigest())
            self.assertEqual(report[0]['resolved_target'], 'styles/style.css')
            (project / 'tests/style.css').write_text('../styles/style.css')
            for alias, target in [('../external.css', '../styles/style.css'),
                    (str(root / 'external.css'), '../styles/style.css'),
                    ('tests/style.css', '../../external.css')]:
                with self.subTest(alias=alias, target=target), self.assertRaises(ValueError):
                    regression._fixture_aliases(baseline, project, {'fixture_aliases': [(alias, target)]})
            (baseline / 'tests/style.css').write_text('changed target')
            with self.assertRaises(ValueError):
                regression._fixture_aliases(baseline, project, suite)
            (baseline / 'tests/style.css').write_text('../styles/style.css')
            (project / 'styles/style.css').unlink()
            (root / 'external.css').write_text('external CSS')
            (project / 'styles/style.css').symlink_to(root / 'external.css')
            with self.assertRaises(ValueError):
                regression._fixture_aliases(baseline, project, suite)
            (project / 'styles/style.css').unlink()
            (project / 'styles').rmdir()
            (project / 'styles').symlink_to(root, target_is_directory=True)
            with self.assertRaises(ValueError):
                regression._fixture_aliases(baseline, project, suite)

    def test_private_metadata_entry_points_reference_controlled_candidate(self) -> None:
        """冻结分发入口只提供元数据和源码路径，结束后连同元数据清理。@return None。"""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            venv, purelib = root / 'python', root / 'python/lib/site-packages'
            purelib.mkdir(parents=True)
            with patch.object(regression, '_WORK_ROOT', root), \
                    patch.object(regression.sys, 'prefix', str(venv)), \
                    patch.object(regression.sys, 'base_prefix', '/system'), \
                    patch.object(regression.sysconfig, 'get_path', return_value=str(purelib)):
                with ExitStack() as cleanup:
                    result = regression._bind_source(root / 'project', Path('.'), cleanup,
                        distribution=('Markdown', '3.11.2'),
                        entry_points={'markdown.extensions': {'toc': 'markdown.extensions.toc:TocExtension'}})
                    metadata = Path(result['distribution']['path'])
                    self.assertEqual((metadata / 'entry_points.txt').read_text(),
                        '[markdown.extensions]\ntoc = markdown.extensions.toc:TocExtension\n')
                    self.assertFalse((purelib / 'markdown').exists())
                self.assertFalse(metadata.exists())
                self.assertEqual(list(purelib.iterdir()), [])

    def test_supplementary_doctests_keep_upstream_initialization_and_frozen_examples(self) -> None:
        """实际执行两种原生入口，保留globs且拒绝候选篡改同名示例预期。@return None。"""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            baseline, candidate = root / 'baseline', root / 'candidate'
            package = ('def value():\n    """>>> value()\n1"""\n    return 1\n')
            validator = (
                'class Validator:\n'
                '    def check(self):\n        """>>> vtor.check()\n1"""\n        return 1\n'
                'if __name__ == "__main__":\n'
                '    import doctest,sys\n'
                '    globs = globals().copy()\n    globs["vtor"] = Validator()\n'
                '    failures, tests = doctest.testmod(sys.modules["__main__"], globs=globs,\n'
                '        optionflags=doctest.IGNORE_EXCEPTION_DETAIL | doctest.ELLIPSIS)\n'
                '    assert not failures\n')
            script = (
                'import configobj,doctest,sys\nfrom configobj import value\n'
                'def example():\n    """>>> fixture is not None\nTrue"""\n'
                'if __name__ == "__main__":\n'
                '    globs = globals().copy()\n    globs["fixture"] = configobj.value()\n'
                '    first = doctest.testmod(sys.modules["__main__"], globs=globs)\n'
                '    second = doctest.testmod(configobj, globs=globs)\n'
                '    assert not (first.failed or second.failed)\n')
            for project in (baseline, candidate):
                (project / 'configobj').mkdir(parents=True)
                (project / 'configobj/__init__.py').write_text(package)
                (project / 'configobj/validate.py').write_text(validator)
                (project / 'upstream.py').write_text(script)
            control = {'project': str(candidate), 'package': 'configobj',
                'documents': regression._documents(baseline, 'configobj'),
                'supplementary': [{'script': 'upstream.py'}, {'module': 'configobj.validate'}]}
            control_path = root / 'control.json'
            environment = dict(os.environ, PYTHONPATH=str(candidate), PYTHONDONTWRITEBYTECODE='1')
            original = []
            for number in (0, 1):
                evidence = root / ('original-' + str(number))
                evidence.mkdir()
                control['evidence'] = str(evidence)
                control_path.write_text(json.dumps(control))
                result = subprocess.run([sys.executable, regression.__file__, '--doctest-worker', str(control_path), str(number)],
                    cwd=candidate, env=environment, capture_output=True, text=True, timeout=10)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                report = json.loads((evidence / ('doctest-' + str(number) + '.json')).read_text())
                self.assertEqual(report['status'], 'passed')
                original.append(report['examples'])
            self.assertEqual(len(original[0]), 2)
            self.assertEqual(len(original[1]), 1)
            self.assertTrue(original[1][0]['flags'] & regression.doctest.ELLIPSIS)
            (candidate / 'configobj/__init__.py').write_text(package.replace('\n1"""', '\n2"""').replace('return 1', 'return 2'))
            (candidate / 'configobj/validate.py').write_text(validator.replace('\n1"""', '\n2"""').replace('return 1', 'return 2'))
            for number in (0, 1):
                evidence = root / ('wrong-' + str(number))
                evidence.mkdir()
                control['evidence'] = str(evidence)
                control_path.write_text(json.dumps(control))
                result = subprocess.run([sys.executable, regression.__file__, '--doctest-worker', str(control_path), str(number)],
                    cwd=candidate, env=environment, capture_output=True, text=True, timeout=10)
                self.assertEqual(result.returncode, 1)
                report = json.loads((evidence / ('doctest-' + str(number) + '.json')).read_text())
                self.assertEqual(report['status'], 'failed')
                self.assertTrue(any(item['outcome'] == 'failed' for item in report['examples']))
                self.assertEqual([item['want_sha256'] for item in report['examples']],
                    [item['want_sha256'] for item in original[number]])


if __name__ == '__main__':
    unittest.main()
