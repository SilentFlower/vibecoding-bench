"""使用真实marker、工程seed和账号SQLite核对空间、轮次及精确清理。"""
import hashlib
import json
import shutil
import unittest
from pathlib import Path
from types import SimpleNamespace
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

    def legacy_workspace(self, *, terminal=None, cycle_no=1):
        """按升级前的固定格式建立真实旧工程，避免用新实现生成兼容夹具。

        :param terminal: 原工程空间。
        :param cycle_no: 旧工程轮次。
        :return: 保留旧注册的物理工作区。
        """
        terminal = terminal or self.terminal
        seed = self.project.manifest['seed_digest']
        identity = {'account_id': 1, 'environment_id': self.row['environment_id'],
            'project_key': 'example', 'seed_digest': seed}
        if terminal.namespace == 'projects' and cycle_no == 1:
            alias = 'workspace-' + hashlib.sha256(f'1:example:{seed}'.encode()).hexdigest()[:16]
        else:
            alias = terminal.namespace + '-workspace-' + hashlib.sha256(
                f'{terminal.namespace}:1:example:{seed}:{cycle_no}'.encode()).hexdigest()[:16]
            identity.update(namespace=terminal.namespace, cycle_no=cycle_no, workspace='projects/' + alias)
        workspace = self.account_root / 'projects' / alias
        shutil.copytree(self.project_root / 'seed', workspace)
        marker = self.account_root / 'runtime' / (terminal.namespace + '-workspaces') / (alias + '.json')
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text(json.dumps(identity))
        return workspace

    def test_new_workspaces_use_project_names_in_both_spaces(self):
        """两空间新建目录体现实际项目，注册仍证明各自空间与轮次。:return: None。"""
        for terminal in (self.original, self.terminal):
            with self.subTest(namespace=terminal.namespace):
                workspace = self.prepare(terminal=terminal)
                self.assertRegex(workspace.name, r'^example-[a-f0-9]{8}$')
                marker = self.account_root / 'runtime' / (terminal.namespace + '-workspaces') / (workspace.name + '.json')
                saved = json.loads(marker.read_text())
                self.assertEqual(2, saved['naming_version'])
                self.assertEqual(terminal.namespace, saved['namespace'])
                self.assertEqual(1, saved['cycle_no'])
                self.assertEqual('projects/' + workspace.name, saved['workspace'])

    def test_default_projects_path_and_marker_remain_exactly_compatible(self):
        """已有工程首轮不增加路径或marker字段，历史工作区仍原样接续。:return: None。"""
        workspace = self.legacy_workspace(terminal=self.original)
        digest = hashlib.sha256(f"1:example:{self.project.manifest['seed_digest']}".encode()).hexdigest()[:16]
        self.assertEqual('workspace-' + digest, workspace.name)
        marker = self.account_root / 'runtime/projects-workspaces' / (workspace.name + '.json')
        self.assertEqual({'account_id': 1, 'environment_id': self.row['environment_id'],
            'project_key': 'example', 'seed_digest': self.project.manifest['seed_digest']}, json.loads(marker.read_text()))
        (workspace / 'library/example.py').write_text('VALUE = 2\n')
        self.assertEqual(workspace, self.prepare(terminal=self.original))
        self.assertEqual('VALUE = 2\n', (workspace / 'library/example.py').read_text())

    def test_old_warmup_and_later_projects_keep_original_registration_and_inputs(self):
        """旧养号及后续工程轮次接续原源码，既有输入凭据逐字节保持。:return: None。"""
        for terminal, cycle in ((self.terminal, 1), (self.terminal, 2), (self.original, 2)):
            with self.subTest(namespace=terminal.namespace, cycle=cycle):
                workspace = self.legacy_workspace(terminal=terminal, cycle_no=cycle)
                marker = self.account_root / 'runtime' / (terminal.namespace + '-workspaces') / (workspace.name + '.json')
                original = marker.read_bytes()
                self.assertEqual(workspace, self.prepare(cycle, terminal=terminal))
                inputs = self.account_root / 'runtime' / (terminal.namespace + '-inputs')
                receipts = {path.name: path.read_bytes() for path in inputs.iterdir()}
                (workspace / 'library/example.py').write_text('VALUE = 3\n')
                self.assertEqual(workspace, self.prepare(cycle, terminal=terminal))
                self.assertEqual(original, marker.read_bytes())
                self.assertEqual(receipts, {path.name: path.read_bytes() for path in inputs.iterdir()})
                self.assertEqual('VALUE = 3\n', (workspace / 'library/example.py').read_text())

    def test_execution_paths_and_original_conversation_follow_the_selected_workspace(self):
        """实际准备器和原生交流读取共用选定目录，新旧工程都能定位原会话。:return: None。"""
        for terminal, cycle, legacy in ((self.original, 1, True), (self.original, 2, False),
                (self.terminal, 1, True), (self.terminal, 2, False)):
            with self.subTest(namespace=terminal.namespace, legacy=legacy):
                if legacy:
                    self.legacy_workspace(terminal=terminal, cycle_no=cycle)
                workspace = self.prepare(cycle, terminal=terminal)
                cwd = '/home/node/projects/' + workspace.name
                session = '11111111-2222-4333-8444-555555555555'
                native = self.account_root / 'home/.claude/projects' / cwd.replace('/', '-')
                native.mkdir(parents=True)
                raw = json.dumps({'message': {'role': 'user', 'content': '原会话正文'}}).encode() + b'\n'
                (native / (session + '.jsonl')).write_bytes(raw)
                work = {'project_key': 'example', 'objective_id': 'FIRST', 'library_digest': 'a' * 64,
                    'cycle_no': cycle, 'baseline_json': '{}', 'session_id': session,
                    'settings_json': '{"claude_code_version":"2.1.293"}',
                    'runtime_json': json.dumps({'workspace': str(workspace.relative_to(self.root)),
                        'native': str(native.relative_to(self.root))})}
                assets = SimpleNamespace(library=None,
                    objective=lambda key, objective: (self.project, {'materials': ['materials/FIRST.md']}))
                terminal.catalog = SimpleNamespace(for_work=lambda current: assets)
                with patch.object(terminal, '_prepare_python', return_value={'bin': '/cli/python/bin', 'site': '/cli/python/site'}):
                    selected, environment = terminal._prepare_execution(self.account_root, self.row, self.account, work)
                self.assertEqual(workspace, selected)
                self.assertEqual(cwd + '/library:' + cwd + '/app:/cli/python/site', environment['PYTHONPATH'])
                self.assertEqual(workspace, terminal.workspace(work))
                self.assertEqual([{'role': 'user', 'content': '原会话正文'}], terminal.conversation(work))
                self.assertEqual(raw, (native / (session + '.jsonl')).read_bytes())

    def test_mixed_old_and_new_cycles_cleanup_only_the_requested_cycle(self):
        """旧目录与自然目录共存时，轮次清理仍精确且可重入。:return: None。"""
        old = self.legacy_workspace()
        self.assertEqual(old, self.prepare())
        second = self.prepare(2)
        sibling = self.prepare(terminal=self.original)
        self.terminal.cleanup_cycle(self.account, 1)
        self.assertFalse(old.exists())
        self.assertTrue(second.is_dir() and sibling.is_dir())
        self.terminal.cleanup_cycle(self.account, 1)
        self.terminal.cleanup_cycle(self.account, 2)
        self.assertFalse(second.exists())
        self.assertTrue(sibling.is_dir())

    def test_two_valid_formats_for_the_same_identity_require_reconciliation(self):
        """同一工程出现新旧两份注册时不得猜测最新源码或同时清除。:return: None。"""
        new = self.prepare()
        old = self.legacy_workspace()
        with self.assertRaisesRegex(ValueError, '多份'):
            self.prepare(objective='SECOND')
        with self.assertRaisesRegex(ValueError, '多份'):
            self.terminal.cleanup_cycle(self.account, 1)
        self.assertTrue(new.is_dir() and old.is_dir())

    def test_unregistered_legacy_directory_cannot_be_bypassed_with_a_new_name(self):
        """旧注册丢失时拒绝创建自然目录，保留原源码供核对。:return: None。"""
        old = self.legacy_workspace()
        marker = self.account_root / 'runtime/warmup-workspaces' / (old.name + '.json')
        marker.unlink()
        with self.assertRaisesRegex(ValueError, '未登记'):
            self.prepare()
        self.assertEqual([old], list(old.parent.iterdir()))

    def test_unregistered_natural_directory_blocks_cleanup_before_deletion(self):
        """自然目录无空间前缀，仍不能绕过未知归属保护。:return: None。"""
        workspace = self.prepare()
        unknown = workspace.parent / 'example-00000000'
        unknown.mkdir()
        with self.assertRaisesRegex(ValueError, '未登记'):
            self.terminal.cleanup_cycle(self.account, 1)
        self.assertTrue(workspace.is_dir() and unknown.is_dir())

    def test_short_name_collision_never_overwrites_the_other_space(self):
        """主动构造短后缀碰撞，新空间不能覆盖另一空间的已登记源码。:return: None。"""
        original = ProjectsTerminal._workspace_identity

        def collide(terminal, *args, **kwargs):
            """仅强制可见名称碰撞，完整私有身份仍来自真实派生。:return: 别名与身份。"""
            alias, identity = original(terminal, *args, **kwargs)
            if identity.get('naming_version') == 2:
                alias = 'example-aaaaaaaa'
                identity = {**identity, 'workspace': 'projects/' + alias}
            return alias, identity

        with patch.object(ProjectsTerminal, '_workspace_identity', autospec=True, side_effect=collide):
            workspace = self.prepare()
            (workspace / 'library/example.py').write_text('VALUE = 4\n')
            with self.assertRaisesRegex(ValueError, '未登记'):
                self.prepare(terminal=self.original)
        self.assertEqual('VALUE = 4\n', (workspace / 'library/example.py').read_text())

    def test_new_seed_has_a_separate_natural_directory(self):
        """同项目更换冻结初始版本时不能复用另一版本的累计成果。:return: None。"""
        first = self.prepare()
        (self.project_root / 'seed/library/example.py').write_text('VALUE = 5\n')
        self.project = ProjectDefinition(self.project_root,
            {'seed_digest': snapshot_tree(self.project_root / 'seed')['digest']})
        second = self.prepare()
        self.assertNotEqual(first, second)
        self.assertEqual('VALUE = 1\n', (first / 'library/example.py').read_text())
        self.assertEqual('VALUE = 5\n', (second / 'library/example.py').read_text())

    def test_legacy_round_marker_is_retained_during_natural_workspace_cleanup(self):
        """早期题库轮次注册不属于新工程，清理时保留其原件。:return: None。"""
        workspace = self.prepare()
        marker = self.account_root / 'runtime/warmup-workspaces' / ('a' * 32 + '.json')
        marker.write_text('{"legacy":"round"}')
        self.terminal.cleanup_cycle(self.account, 1)
        self.assertFalse(workspace.exists())
        self.assertEqual('{"legacy":"round"}', marker.read_text())

    def test_sibling_registration_link_blocks_cleanup_without_touching_its_target(self):
        """读取兄弟空间归属时仍拒绝目录链接，不能扩大工程清理范围。:return: None。"""
        workspace = self.prepare()
        outside = self.root / 'external-registration'
        outside.mkdir()
        (outside / 'keep').write_text('保留原件')
        (self.account_root / 'runtime/projects-workspaces').symlink_to(outside, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, '链接'):
            self.terminal.cleanup_cycle(self.account, 1)
        self.assertTrue(workspace.is_dir())
        self.assertEqual('保留原件', (outside / 'keep').read_text())

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
        for changes in ({'seed_digest': '0' * 64}, {'workspace': 'projects/elsewhere'}, {'account_id': 2},
                {'naming_version': True}, {'naming_version': 3}, {'naming_version': 1},
                {'cycle_no': False}, {'project_key': '../elsewhere'}):
            marker.write_text(json.dumps({**saved, **changes}))
            with self.assertRaises(ValueError):
                self.terminal.cleanup_cycle(self.account, 1)
            self.assertTrue(workspace.is_dir())
        marker.write_text(json.dumps(saved))
        self.terminal.cleanup_cycle(self.account, 1)
        self.assertFalse(workspace.exists())


if __name__ == '__main__':
    unittest.main()
