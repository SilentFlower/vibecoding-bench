"""使用真实marker、工程seed和账号SQLite核对空间、轮次及精确清理。"""
import hashlib
import json
import unittest
from pathlib import Path
from unittest.mock import patch

import test_account_runtime
from project_library import ProjectDefinition, snapshot_tree
from projects_runtime import ProjectsTerminal


class ProjectsCycleTests(unittest.TestCase):
    """清理只触及该账号已证明的工程轮次，保留其它空间与历史交付对象。"""

    def setUp(self):
        """创建临时真实账号环境和可物化的合成项目。:return: None。"""
        test_account_runtime.AccountRuntimeTests.setUp(self)
        self.account = {'id': 1, 'name': 'synthetic', 'cc2api_account_id': 7}
        self.row = self.runtime._row('synthetic', 1)
        self.account_root = self.runtime._root(self.row)
        self.project_root = self.root / 'content'
        (self.project_root / 'seed/library').mkdir(parents=True)
        (self.project_root / 'seed/library/example.py').write_text('VALUE = 1\n')
        self.project = ProjectDefinition(self.project_root,
            {'seed_digest': snapshot_tree(self.project_root / 'seed')['digest']})
        self.terminal = ProjectsTerminal(self.runtime, None, None, None, namespace='warmup')
        self.original = ProjectsTerminal(self.runtime, None, None, None)

    def prepare(self, cycle_no=1, *, terminal=None, objective='FIRST', account=None, row=None):
        """通过实际工程准备器创建完整注册及输入证明。:param cycle_no: 轮次。:param terminal: 空间适配。:param objective: 目标。:param account: 账号。:param row: 环境。:return: 源码目录。"""
        account, row = account or self.account, row or self.row
        terminal = terminal or self.terminal
        source = self.project_root / 'materials' / (objective + '.md')
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_text('Implement the supplied synthetic local feature.')
        work = {'project_key': 'example', 'objective_id': objective, 'library_digest': 'a' * 64,
            'baseline_json': None, 'cycle_no': cycle_no}
        return terminal._prepare_workspace(self.runtime._root(row), row, account, work, self.project,
            {'materials': ['materials/' + objective + '.md']})

    def test_default_projects_path_and_marker_remain_exactly_compatible(self):
        """默认工程首轮不增加路径或marker字段，历史工作区仍原样接续。:return: None。"""
        workspace = self.prepare(terminal=self.original)
        digest = hashlib.sha256(f"1:example:{self.project.manifest['seed_digest']}".encode()).hexdigest()[:16]
        self.assertEqual('workspace-' + digest, workspace.name)
        marker = self.account_root / 'runtime/projects-workspaces' / (workspace.name + '.json')
        self.assertEqual({'account_id': 1, 'environment_id': self.row['environment_id'],
            'project_key': 'example', 'seed_digest': self.project.manifest['seed_digest']}, json.loads(marker.read_text()))
        (workspace / 'library/example.py').write_text('VALUE = 2\n')
        self.assertEqual(workspace, self.prepare(terminal=self.original))
        self.assertEqual('VALUE = 2\n', (workspace / 'library/example.py').read_text())

    def test_spaces_cycles_accounts_and_shared_objects_are_preserved(self):
        """只删除本账号养号首轮，工程空间、下轮、另一账号及内容对象均保留。:return: None。"""
        original = self.prepare(terminal=self.original)
        first, second = self.prepare(), self.prepare(2)
        with self.database() as connection:
            connection.execute("INSERT INTO accounts(id,name,cc2api_account_id) VALUES(2,'synthetic-other',8)")
        other = {'id': 2, 'name': 'synthetic-other', 'cc2api_account_id': 8}
        other_row = self.runtime._row(other['name'], other['id'])
        other_workspace = self.prepare(account=other, row=other_row)
        self.assertEqual(4, len({original, first, second, other_workspace}))
        objects = {str(path.relative_to(self.root)): path.read_bytes() for path in (self.root / 'projects/objects').rglob('*') if path.is_file()}
        session = self.root / 'warmup-projects/agents/1/session.jsonl'
        session.parent.mkdir(parents=True)
        session.write_text('synthetic-pi-session')
        self.terminal.cleanup_cycle(self.account, 1)
        self.assertFalse(first.exists())
        self.assertTrue(all(path.is_dir() for path in (original, second, other_workspace)))
        self.assertEqual('synthetic-pi-session', session.read_text())
        self.assertEqual(objects, {str(path.relative_to(self.root)): path.read_bytes() for path in (self.root / 'projects/objects').rglob('*') if path.is_file()})
        receipts = [json.loads(path.read_text()) for path in (self.account_root / 'runtime/warmup-inputs').glob('*.json')]
        self.assertEqual([2], [item['cycle_no'] for item in receipts])
        self.terminal.cleanup_cycle(self.account, 1)
        self.assertTrue(second.exists())

    def test_interrupted_cleanup_reenters_from_retained_registration(self):
        """源码已删但输入凭据尚未删的中断可以恢复，原注册证明最后收口。:return: None。"""
        workspace = self.prepare()
        marker = self.account_root / 'runtime/warmup-workspaces' / (workspace.name + '.json')
        real_unlink = Path.unlink
        failed = False

        def unlink(path, *args, **kwargs):
            nonlocal failed
            if path.parent == self.account_root / 'runtime/warmup-inputs' and not failed:
                failed = True
                raise OSError('合成输入凭据删除中断')
            return real_unlink(path, *args, **kwargs)

        with patch.object(Path, 'unlink', unlink):
            with self.assertRaises(OSError):
                self.terminal.cleanup_cycle(self.account, 1)
        self.assertFalse(workspace.exists())
        self.assertTrue(marker.is_file())
        self.terminal.cleanup_cycle(self.account, 1)
        self.assertFalse(marker.exists())
        self.assertEqual([], list((self.account_root / 'runtime/warmup-inputs').iterdir()))

    def test_jobs_and_orphan_execution_records_block_cleanup(self):
        """真实账号作业或遗留登记存在时禁止清理，不能只看工程业务终态。:return: None。"""
        workspace = self.prepare()
        self.runtime.jobs['synthetic-job'] = {'row': self.row}
        with self.assertRaisesRegex(ValueError, '作业'):
            self.terminal.cleanup_cycle(self.account, 1)
        self.runtime.jobs.clear()
        registration = self.account_root / 'runtime/execution.json'
        registration.write_text('{}')
        with self.assertRaisesRegex(ValueError, '登记'):
            self.terminal.cleanup_cycle(self.account, 1)
        self.assertTrue(workspace.is_dir())
        registration.unlink()
        self.terminal.cleanup_cycle(self.account, 1)
        self.assertFalse(workspace.exists())

    def test_unknown_workspace_and_symlink_are_rejected_before_any_deletion(self):
        """遇到同空间未知目录或外部链接时整轮不删，外部文件保持原样。:return: None。"""
        workspace = self.prepare()
        unknown = workspace.parent / 'warmup-workspace-unregistered'
        unknown.mkdir()
        with self.assertRaisesRegex(ValueError, '未登记'):
            self.terminal.cleanup_cycle(self.account, 1)
        self.assertTrue(workspace.is_dir())
        unknown.rmdir()
        outside = self.root / 'outside'
        outside.mkdir()
        (outside / 'keep').write_text('keep')
        (workspace / 'linked').symlink_to(outside, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, '链接'):
            self.terminal.cleanup_cycle(self.account, 1)
        self.assertEqual('keep', (outside / 'keep').read_text())
        self.assertTrue(workspace.is_dir())

    def test_tampered_seed_identity_or_real_path_cannot_select_a_workspace(self):
        """注册中的seed和真实路径必须与派生别名一致，不能借marker指定其它目录。:return: None。"""
        workspace = self.prepare()
        marker = self.account_root / 'runtime/warmup-workspaces' / (workspace.name + '.json')
        saved = json.loads(marker.read_text())
        for changes in ({'seed_digest': '0' * 64}, {'workspace': 'projects/elsewhere'}, {'account_id': 2}):
            marker.write_text(json.dumps({**saved, **changes}))
            with self.assertRaises(ValueError):
                self.terminal.cleanup_cycle(self.account, 1)
            self.assertTrue(workspace.is_dir())
        marker.write_text(json.dumps(saved))
        self.terminal.cleanup_cycle(self.account, 1)
        self.assertFalse(workspace.exists())


if __name__ == '__main__':
    unittest.main()
