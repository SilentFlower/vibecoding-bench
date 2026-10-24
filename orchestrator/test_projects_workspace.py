"""验证同一项目多个完整目标接续时的输入投递与成果保护。"""
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from project_library import ProjectDefinition, snapshot_tree
from projects_runtime import ProjectsTerminal


class ProjectsWorkspaceTests(unittest.TestCase):
    """使用真实文件系统验证输入冲突、恢复及链接边界。"""

    def setUp(self):
        """建立固定源码和两个目标的独立公开材料。:return: None。"""
        temporary = tempfile.TemporaryDirectory(prefix='projects-workspace-')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.data = self.root / 'data'
        self.account_root = self.data / 'environment'
        self.project_root = self.root / 'content'
        seed = self.project_root / 'seed/library'
        seed.mkdir(parents=True)
        (seed / 'example.py').write_text('VALUE = 1\n')
        self.project = ProjectDefinition(self.project_root,
            {'seed_digest': snapshot_tree(self.project_root / 'seed')['digest']})
        self.account = {'id': 7}
        self.row = {'environment_id': 'environment-seven'}
        self.terminal = ProjectsTerminal(SimpleNamespace(data=self.data), None, None, None)
        for name in ('chown', 'fchown'):
            mocked = patch('projects_runtime.os.' + name)
            mocked.start()
            self.addCleanup(mocked.stop)

    def prepare(self, objective, files, *, setup=None, baseline=None):
        """按实际适配器输入准备一个完整目标。

        :param objective: 稳定目标标识。
        :param files: 公开相对路径与固定内容。
        :param setup: 可选业务输入映射。
        :param baseline: 恢复旧工作时已有的冻结基线。
        :return: 累计工作目录。
        """
        for relative, content in files.items():
            source = self.project_root / relative
            source.parent.mkdir(parents=True, exist_ok=True)
            source.write_text(content)
        definition = {'id': objective, 'materials': list(files), 'owner_materials': [], 'setup': setup or []}
        work = {'project_key': 'example', 'objective_id': objective, 'library_digest': 'a' * 64,
            'baseline_json': baseline}
        return self.terminal._prepare_workspace(self.account_root, self.row, self.account, work,
            self.project, definition)

    def test_next_objective_gets_its_materials_and_preserves_accepted_source(self):
        """后继目标补齐自身材料，前一目标的真实修改保持不变。:return: None。"""
        first = self.prepare('FIRST', {'materials/FIRST/contract.md': '第一个完整需求'})
        (first / 'library/example.py').write_text('VALUE = 2\n')
        second = self.prepare('SECOND', {'materials/SECOND/contract.md': '第二个完整需求'})
        self.assertEqual(first, second)
        self.assertEqual('VALUE = 2\n', (second / 'library/example.py').read_text())
        self.assertEqual('第一个完整需求', (second / 'materials/FIRST/contract.md').read_text())
        self.assertEqual('第二个完整需求', (second / 'materials/SECOND/contract.md').read_text())

    def test_setup_is_available_before_the_work_baseline_is_captured(self):
        """业务初始文件实际物化到 app，候选无需猜测或自行补造。:return: None。"""
        workspace = self.prepare('APP', {'materials/APP/order.json': '{"quantity":2}'},
            setup=[{'source': 'materials/APP/order.json', 'target': 'app/APP/order.json'}])
        self.assertEqual({'quantity': 2}, json.loads((workspace / 'app/APP/order.json').read_text()))

    def test_setup_conflict_does_not_overwrite_prior_work_or_partially_deliver_files(self):
        """先校验全部输入，冲突不能覆盖成果或留下半份材料。:return: None。"""
        workspace = self.prepare('FIRST', {})
        (workspace / 'app').mkdir()
        (workspace / 'app/order.json').write_text('已交付的业务数据')
        with self.assertRaisesRegex(ValueError, '冲突'):
            self.prepare('SECOND', {'materials/SECOND/contract.md': '新合同',
                'materials/SECOND/order.json': '新初始值'},
                setup=[{'source': 'materials/SECOND/order.json', 'target': 'app/order.json'}])
        self.assertEqual('已交付的业务数据', (workspace / 'app/order.json').read_text())
        self.assertFalse((workspace / 'materials/SECOND/contract.md').exists())

    def test_repeated_resume_preserves_user_changes_to_materials(self):
        """输入成功投递后恢复同一任务，用户编辑不会被模板重新覆盖。:return: None。"""
        workspace = self.prepare('FIRST', {'materials/FIRST/contract.md': '固定输入'})
        (workspace / 'materials/FIRST/contract.md').write_text('调查期间的工作注释')
        self.prepare('FIRST', {'materials/FIRST/contract.md': '固定输入'}, baseline='{}')
        self.assertEqual('调查期间的工作注释', (workspace / 'materials/FIRST/contract.md').read_text())

    def test_legacy_started_work_keeps_its_original_baseline(self):
        """升级恢复已有工作时不往既有基线插入控制端文件。:return: None。"""
        workspace = self.prepare('FIRST', {})
        (workspace / 'library/example.py').write_text('VALUE = 3\n')
        self.prepare('LEGACY', {'materials/LEGACY/contract.md': '旧合同'}, baseline='{"files":{}}')
        self.assertFalse((workspace / 'materials/LEGACY/contract.md').exists())
        self.assertEqual('VALUE = 3\n', (workspace / 'library/example.py').read_text())

    def test_directory_link_cannot_receive_next_objective_inputs(self):
        """使用目录 fd 拒绝材料父目录链接，外部目录保持未写入。:return: None。"""
        workspace = self.prepare('FIRST', {})
        outside = self.root / 'outside'
        outside.mkdir()
        (workspace / 'materials').symlink_to(outside, target_is_directory=True)
        with self.assertRaises(OSError):
            self.prepare('SECOND', {'materials/SECOND/contract.md': '不能越界'})
        self.assertEqual([], list(outside.iterdir()))

    def test_file_link_cannot_replace_or_read_outside_input(self):
        """已有材料链接不能被视为合法的固定输入。:return: None。"""
        workspace = self.prepare('FIRST', {})
        outside = self.root / 'external-secret'
        outside.write_text('外部原内容')
        (workspace / 'materials/SECOND').mkdir(parents=True)
        (workspace / 'materials/SECOND/contract.md').symlink_to(outside)
        with self.assertRaises(OSError):
            self.prepare('SECOND', {'materials/SECOND/contract.md': '不能读取'})
        self.assertEqual('外部原内容', outside.read_text())

    def test_existing_unregistered_workspace_is_never_replaced(self):
        """原工作区身份凭据缺失时保留现场，不覆盖源码。:return: None。"""
        workspace = self.prepare('FIRST', {})
        marker = next((self.account_root / 'runtime/projects-workspaces').glob('*.json'))
        marker.unlink()
        with self.assertRaisesRegex(ValueError, '未登记'):
            self.prepare('SECOND', {'materials/SECOND/contract.md': '新需求'})
        self.assertEqual('VALUE = 1\n', (workspace / 'library/example.py').read_text())


if __name__ == '__main__':
    unittest.main()
