"""用真实原版、参考、等价实现和错误反例验证观察器兼容性。"""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from zipfile import ZipFile

from project_verifier import _native_contract_observer_adapter
from projects_verification import ProjectsVerification


ROOT = Path(__file__).resolve().parents[1]
CASES = {
    'webcolors': ('WEBCOLORS-06-DEV', 'project_palette_observer.py', 'library/src'),
    'bibtexparser': ('BIBTEXPARSER-O02-DEV', 'project_bibtex_validation_observer.py', 'library'),
    'click': ('CK-STABLE-WRITE-DEV', 'project_stable_write_observer.py', 'library/src'),
    'python-liquid': ('PYTHON-LIQUID-02-DEV', 'project_versioned_loader_observer.py', 'library'),
}


class BehaviorObserverTests(unittest.TestCase):
    """使用固定真实源码的替代实现证明宽容不会放行实际业务错误。"""

    @classmethod
    def setUpClass(cls):
        """应用受保护参考补丁准备独立测试树。:return: None。"""
        cls.temporary = tempfile.TemporaryDirectory(prefix='behavior-observers-')
        cls.addClassCleanup(cls.temporary.cleanup)
        cls.candidates = Path(cls.temporary.name)
        cls.dependencies = cls.candidates / 'offline-dependencies'
        cls.dependencies.mkdir()
        environment = ROOT / 'project_library/environments/python-liquid-py312'
        for artifact in json.loads((environment / 'profile/profile.json').read_text())['artifacts']:
            with ZipFile(environment / artifact['path']) as wheel:
                wheel.extractall(cls.dependencies)
        for project, (objective, _, _) in CASES.items():
            source = ROOT / 'project_library/projects' / project
            target = cls.candidates / project
            shutil.copytree(source / 'seed', target)
            result = subprocess.run(['git', 'apply', str(source / 'verification' / ('development-' + objective + '.patch'))],
                cwd=target, capture_output=True, text=True, timeout=20)
            if result.returncode:
                raise AssertionError(result.stderr)

    def observe(self, project, prelude='', *, original=False, legacy=False):
        """在独立进程核真实观察器；旧规则失败也保留为失败事实。

        :param project: 固定项目。
        :param prelude: 仅用于受保护参考树的测试变体。
        :param original: 是否使用未实施功能的原版。
        :param legacy: 是否执行旧观察器以证明原误拒。
        :return: 实际受控 JSON 或进程失败记录。
        """
        objective, filename, import_root = CASES[project]
        project_root = ROOT / 'project_library/projects' / project
        candidate = project_root / 'seed' if original else self.candidates / project
        paths = [str(ROOT / 'orchestrator'), str(candidate / import_root), str(self.dependencies)]
        if project == 'bibtexparser':
            paths.append(str(ROOT / 'project_library/environments/bibtexparser-py312/artifacts/pylatexenc-2.11-py2.py3-none-any.whl'))
        program = 'import json,runpy,sys\nfrom pathlib import Path\nsys.path[:0]=' + repr(paths) + '\n' + prelude + '\n'
        if legacy:
            source = ROOT / 'orchestrator/testdata' / (objective.lower() + '-observer-legacy.txt')
            program += ('source=Path(' + repr(str(source)) + ').read_text()\n'
                'exec(compile(source,"<原冻结观察器>","exec"),{"__file__":' + repr(str(project_root / 'verification' / (objective + '-observe.py'))) + '})\n')
        else:
            program += 'runpy.run_path(' + repr(str(ROOT / 'orchestrator' / filename)) + ',run_name="__main__")\n'
        result = subprocess.run([sys.executable, '-I', '-B', '-c', program],
            env={**os.environ, 'PROJECT_CANDIDATE_ROOT': str(candidate), 'PYTHONDONTWRITEBYTECODE': '1'},
            capture_output=True, text=True, timeout=25)
        if result.returncode:
            return {'business': False, 'process_error': result.stderr[-500:]}
        return json.loads(result.stdout)

    def test_original_fails_and_reference_passes_for_every_changed_observer(self):
        """每个修正观察器必须在真实原版失败，在真实参考实现通过。:return: None。"""
        for project in CASES:
            with self.subTest(project=project):
                self.assertFalse(self.observe(project, original=True)['business'])
                result = self.observe(project)
                self.assertTrue(result['business'], result)
                self.assertTrue(result['candidate_import'])
                self.assertEqual(result['feedback_codes'], [])

    def test_palette_allows_different_storage_but_rejects_mutable_export_and_wrong_values(self):
        """真实实现重命名私有字段可通过，泄漏导出或错误颜色仍失败。:return: None。"""
        alternative = ('import webcolors.palette as module\n'
            'source=Path(module.__file__).read_text().replace("_colors","_storage")\n'
            'exec(compile(source,str(module.__file__),"exec"),module.__dict__)\n')
        self.assertFalse(self.observe('webcolors', alternative, legacy=True)['business'])
        self.assertTrue(self.observe('webcolors', alternative)['business'])
        for bad in ('import webcolors.palette as module\nmodule.Palette.to_dict=lambda self:self._colors\n',
                'import webcolors.palette as module\nmodule.Palette.rgb=lambda self,name:(0,0,0)\n'):
            self.assertFalse(self.observe('webcolors', bad)['business'])

    def test_bibliography_allows_reasonable_rejection_but_rejects_ignored_versions_and_developer_errors(self):
        """未知版本的TypeError可以通过，吞掉版本或发生NameError仍失败。:return: None。"""
        prefix = 'import bibtexparser.validation as module\noriginal=module.validate_entries\n'
        alternative = prefix + ('def compatible(source,**options):\n'
            '    if options.get("version")=="future":raise TypeError("未知版本")\n'
            '    return original(source,**options)\nmodule.validate_entries=compatible\n')
        self.assertFalse(self.observe('bibtexparser', alternative, legacy=True)['business'])
        self.assertTrue(self.observe('bibtexparser', alternative)['business'])
        ignored = prefix + ('def broken(source,**options):\n'
            '    options.pop("version",None)\n    return original(source,**options)\nmodule.validate_entries=broken\n')
        result = self.observe('bibtexparser', ignored)
        self.assertFalse(result['business'])
        self.assertIn('bibliography_version', result['feedback_codes'])
        self.assertFalse(self.observe('bibtexparser', alternative.replace('TypeError', 'NameError'))['business'])

    def test_stable_write_allows_oserror_but_still_rejects_link_writes(self):
        """软链接以OSError拒绝可以通过，实际写穿目标或开发错误仍失败。:return: None。"""
        prefix = 'import click.writing as module\noriginal=module.write_if_changed\n'
        alternative = prefix + ('def compatible(path,content,**options):\n'
            '    if Path(path).is_symlink():raise OSError("不接受符号链接")\n'
            '    return original(path,content,**options)\nmodule.write_if_changed=compatible\n')
        self.assertFalse(self.observe('click', alternative, legacy=True)['business'])
        self.assertTrue(self.observe('click', alternative)['business'])
        bad = prefix + ('def broken(path,content,**options):\n'
            '    if Path(path).is_symlink():\n'
            '        original(Path(path).resolve(),content,**options)\n        raise OSError("已经写穿")\n'
            '    return original(path,content,**options)\nmodule.write_if_changed=broken\n')
        result = self.observe('click', bad)
        self.assertFalse(result['business'])
        self.assertIn('stable_write_symlink', result['feedback_codes'])
        self.assertFalse(self.observe('click', alternative.replace('OSError', 'NameError'))['business'])

    def test_loader_allows_different_cache_storage_but_rejects_unbounded_cache(self):
        """缓存字段重命名可通过，忽略容量造成未淘汰仍失败。:return: None。"""
        alternative = ('import liquid.versioned_loader as module\n'
            'source=Path(module.__file__).read_text().replace("_cache","_compiled")\n'
            'exec(compile(source,str(module.__file__),"exec"),module.__dict__)\n')
        self.assertFalse(self.observe('python-liquid', alternative, legacy=True)['business'])
        self.assertTrue(self.observe('python-liquid', alternative)['business'])
        bad = ('import liquid.versioned_loader as module\noriginal=module.VersionedDictLoader.__init__\n'
            'def broken(self,templates,**options):original(self,templates,capacity=128)\n'
            'module.VersionedDictLoader.__init__=broken\n')
        result = self.observe('python-liquid', bad)
        self.assertFalse(result['business'])
        self.assertIn('versioned_loader_cache', result['feedback_codes'])

    def test_frozen_and_future_sources_share_trusted_bytes_and_unknown_sources_are_rejected(self):
        """旧脚本和未来副本一致走受信入口，未知字节不自动放行。:return: None。"""
        for project, (objective, filename, _) in CASES.items():
            project_root = ROOT / 'project_library/projects' / project
            specification = json.loads((project_root / 'verification' / (objective + '.native.json')).read_text())
            expected = (ROOT / 'orchestrator' / filename).read_bytes()
            future = project_root / 'verification' / (objective + '-observe.py')
            self.assertEqual(expected, future.read_bytes())
            old = (ROOT / 'orchestrator/testdata' / (objective.lower() + '-observer-legacy.txt')).read_bytes()
            for source in (old, expected):
                actual, proof = _native_contract_observer_adapter(source, specification)
                self.assertEqual(actual, expected)
                self.assertEqual(proof['original_runner_sha256'], hashlib.sha256(source).hexdigest())
                self.assertEqual(proof['effective_runner_sha256'], hashlib.sha256(expected).hexdigest())
            with self.assertRaises(ValueError):
                _native_contract_observer_adapter(old + b'\n', specification)
            feedback = ProjectsVerification._business_feedback({'feedback_codes': self.observe(project, original=True)['feedback_codes']})
            self.assertTrue(feedback)
