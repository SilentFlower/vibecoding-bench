"""验证源码搬迁的逻辑身份与旧宿主布局兼容性。"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from source_layout import SOURCE_ROOTS, source_path
from system_release import component_content


class SourceLayoutTests(unittest.TestCase):
    """对同一内容比较搬迁前后的组件身份及来源选择。"""

    def test_old_and_migrated_layouts_have_same_component_identity(self) -> None:
        """纯目录搬迁保持内容身份，实际内容变化仍可检测。@return None。"""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            old, new = root / 'old', root / 'new'
            names = ('images/v3/Dockerfile', 'images/v3/criu/controller.py', 'images/v3/tls-observer/observer.py',
                'cc2api/src/main.rs', 'cc2api/Cargo.toml',
                'cc2api/Cargo.lock', 'cc2api/vendor/dependency.rs', 'cc2api/craftls/lib.rs',
                'orchestrator/runtime_files.py', 'orchestrator/runtime_diagnostics.py',
                'orchestrator/cli_quota.py', 'orchestrator/process_metrics.py',
                'orchestrator/native_sender.py', 'webui/index.html', 'cc2api/web/src/main.ts',
                'cc2api/web/package-lock.json', 'images/account/init.py',
                'images/sidecar/start.sh', 'images/worker/task_followups.py')
            for name in names:
                target = old / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text('synthetic:' + name)
            shutil.copytree(old, new)
            for original, migrated in SOURCE_ROOTS:
                source = new / original
                if source.exists():
                    target = new / migrated
                    target.parent.mkdir(parents=True, exist_ok=True)
                    source.rename(target)
            for role in ('control', 'account'):
                self.assertEqual(component_content(old, role), component_content(new, role))
            changed = source_path(new, 'orchestrator/native_sender.py')
            changed.write_text('synthetic:changed')
            self.assertNotEqual(component_content(old, 'account'), component_content(new, 'account'))

    def test_missing_migrated_file_does_not_use_leftover_old_copy(self) -> None:
        """模块已迁移后，缺失文件保持可见，避免混用两套来源。@return None。"""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / 'services/orchestrator').mkdir(parents=True)
            (root / 'orchestrator').mkdir()
            (root / 'orchestrator/missing.py').write_text('synthetic')
            self.assertEqual(source_path(root, 'orchestrator/missing.py'),
                root / 'services/orchestrator/missing.py')
            self.assertFalse(source_path(root, 'orchestrator/missing.py').exists())
            with self.assertRaises(ValueError):
                source_path(root, '../outside')

    def test_deployment_layout_is_detected_independently(self) -> None:
        """新旧部署源码、上一版单仓及固定包分别选择真实来源。@return None。"""
        with tempfile.TemporaryDirectory() as temporary:
            for name, services, migrated in (('legacy', False, False),
                    ('previous-monorepo', True, False), ('current-monorepo', True, True),
                    ('deployment-only', False, True), ('installed/source', False, False)):
                with self.subTest(layout=name):
                    root = Path(temporary) / name
                    if services:
                        (root / 'services').mkdir(parents=True)
                    relative = 'deploy/flower2api/manage.py' if migrated else 'deploy/v3/manage.py'
                    target = root / relative
                    target.parent.mkdir(parents=True)
                    target.write_text('synthetic:' + name)
                    self.assertEqual(source_path(root, 'deploy/v3/manage.py'), target)
                    self.assertEqual(source_path(root, 'deploy/v3/manage.py').read_text(), 'synthetic:' + name)

    def test_missing_migrated_deployment_file_stays_missing(self) -> None:
        """新部署目录缺文件时拒绝混用旧目录残留。@return None。"""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / 'deploy/flower2api').mkdir(parents=True)
            (root / 'deploy/v3').mkdir()
            (root / 'deploy/v3/manage.py').write_text('synthetic:stale')
            path = source_path(root, 'deploy/v3/manage.py')
            self.assertEqual(path, root / 'deploy/flower2api/manage.py')
            with self.assertRaises(FileNotFoundError):
                path.read_bytes()
            with self.assertRaises(ValueError):
                source_path(root, root / 'deploy/v3/manage.py')

    def test_stack_alias_preserves_arguments_and_exit_status(self) -> None:
        """两个脚本从外部目录转发空参数、空格与退出状态。@return None。"""
        repository = Path(__file__).resolve().parents[2]
        with tempfile.TemporaryDirectory(prefix='flower2api cli ') as temporary:
            root = Path(temporary)
            (root / 'scripts').mkdir()
            (root / 'bin').mkdir()
            (root / 'deploy/flower2api').mkdir(parents=True)
            (root / 'deploy/flower2api/manage.py').touch()
            python = root / 'bin/python3'
            python.write_text(f'#!{sys.executable}\nimport json, sys\nprint(json.dumps(sys.argv[1:]))\nsys.exit(73)\n')
            python.chmod(0o755)
            environment = dict(os.environ, PATH=str(root / 'bin') + os.pathsep + os.environ['PATH'])
            arguments = ['check', '--env', 'path with spaces', '', 'literal;$value']
            for name in ('flower2api-stack', 'v3-stack'):
                shutil.copy2(repository / 'scripts' / name, root / 'scripts' / name)
            for name in ('flower2api-stack', 'v3-stack'):
                with self.subTest(entry=name):
                    result = subprocess.run([str(root / 'scripts' / name), *arguments], cwd=root / 'bin',
                        env=environment, capture_output=True, text=True, timeout=10)
                    self.assertEqual(result.returncode, 73, result.stderr)
                    received = json.loads(result.stdout)
                    self.assertEqual(Path(received[0]).resolve(), root / 'deploy/flower2api/manage.py')
                    self.assertEqual(received[1:], arguments)


if __name__ == '__main__':
    unittest.main()
