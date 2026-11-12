"""验证源码搬迁的逻辑身份与旧宿主布局兼容性。"""
import shutil
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
            names = ('images/v3/Dockerfile', 'cc2api/src/main.rs', 'cc2api/Cargo.toml',
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


if __name__ == '__main__':
    unittest.main()
