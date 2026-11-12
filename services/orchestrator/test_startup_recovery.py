"""通过真实环境表、目录注册与角色核对验证未启动原工作的人工恢复证明。"""
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from account_isolation import role_labels
from account_runtime import atomic_json
from projects_runtime import ProjectsTerminal
import test_account_runtime


class StartupRecoveryProofTests(unittest.TestCase):
    """仅替代 Docker 传输，保留真实的环境查询与工作区身份验证。"""

    def setUp(self) -> None:
        """创建有三角色和独立工程注册的合成账号。:return: None。"""
        self.fixture = test_account_runtime.AccountRuntimeTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.runtime = self.fixture.runtime
        self.account = {'id': 1, 'name': 'synthetic', 'cc2api_account_id': 7}
        self.row = self.runtime._row('synthetic', 1)
        self.runtime._update(self.row, state='ready', isolation_version=2,
            container_id='fixture-cli', sender_container_id='fixture-sender', network_container_id='fixture-network')
        self.root = self.runtime._root(self.row)
        for relative in ('runtime', 'projects', 'home/.claude/projects'):
            (self.root / relative).mkdir(parents=True, exist_ok=True)
        project = SimpleNamespace(manifest={'seed_digest': 'a' * 64})
        self.catalog = SimpleNamespace(objective=lambda *_: (project, {}))
        self.catalog.for_work = lambda _: self.catalog
        self.work = {'id': 'b' * 32, 'project_key': 'example', 'objective_id': 'feature', 'cycle_no': 1,
            'session_id': '7254b6c1-5576-469a-b169-7fea6a4cbdbd'}
        self.containers = {role: Mock(id='fixture-' + role, status='running',
            labels=role_labels(self.runtime, self.row, role)) for role in ('cli', 'sender', 'network')}
        self.fixture.client.containers.get.side_effect = lambda identifier: self.containers[identifier.removeprefix('fixture-')]
        self.containers['cli'].exec_run.return_value = SimpleNamespace(exit_code=0, output=b'{"orphans":[]}')
        self._register('projects')

    def _register(self, namespace: str) -> None:
        """登记真实命名与完整身份的工作区。:param namespace: 固定空间。:return: None。"""
        self.terminal = ProjectsTerminal(self.runtime, self.catalog, None, None, namespace=namespace)
        alias, identity = self.terminal._workspace_identity(self.account, self.row, 'example', 'a' * 64, 1)
        self.workspace = self.root / 'projects' / alias
        self.workspace.mkdir(exist_ok=True)
        self.marker = self.root / 'runtime' / (namespace + '-workspaces') / (alias + '.json')
        atomic_json(self.marker, identity)

    def test_both_namespaces_prove_idle_state_without_mutating_saved_identity(self) -> None:
        """两空间通过实际登记和角色核对，检查过程不创建环境或改变画像。:return: None。"""
        for namespace in ('projects', 'warmup'):
            with self.subTest(namespace=namespace):
                if namespace == 'warmup':
                    self._register(namespace)
                before = self.marker.read_bytes()
                self.assertTrue(self.terminal.startup_recovery_ready(self.account, self.work))
                self.assertEqual(before, self.marker.read_bytes())
        command = self.containers['cli'].exec_run.call_args.args[0]
        self.assertEqual(['python3', '-I', '/usr/local/bin/v3-cli-control', 'orphans'], command)

    def test_active_jobs_and_persisted_executions_are_not_idle(self) -> None:
        """内存作业、排他登记或共享登记任一存在时都不能核发恢复证明。:return: None。"""
        job = {'row': self.row, 'source': 'projects:fixture:1', 'shared_cli': True}
        self.runtime._register_job(job)
        self.assertFalse(self.terminal.startup_recovery_ready(self.account, self.work))
        self.runtime._remove_job(job)
        execution = self.root / 'runtime/execution.json'
        atomic_json(execution, {'unknown': True})
        self.assertFalse(self.terminal.startup_recovery_ready(self.account, self.work))
        execution.unlink()
        shared = self.root / 'runtime/executions/unknown.json'
        atomic_json(shared, {'unknown': True})
        self.assertFalse(self.terminal.startup_recovery_ready(self.account, self.work))

    def test_native_sessions_unknown_roles_and_orphans_block_recovery(self) -> None:
        """原生会话、角色归属变化、实际孤儿或读取失败都保持未知状态。:return: None。"""
        native = self.root / 'home/.claude/projects/original' / (self.work['session_id'] + '.jsonl')
        native.parent.mkdir()
        native.write_text('{}\n')
        self.assertFalse(self.terminal.startup_recovery_ready(self.account, self.work))
        native.unlink()
        self.containers['sender'].labels['vibebench.release'] = 'wrong-release'
        self.assertFalse(self.terminal.startup_recovery_ready(self.account, self.work))
        self.containers['sender'].labels.update(role_labels(self.runtime, self.row, 'sender'))
        for result in (SimpleNamespace(exit_code=0, output=b'{"orphans":[{"pid":123}]}'),
                SimpleNamespace(exit_code=1, output=b'private'), SimpleNamespace(exit_code=0, output=b'{}'),
                SimpleNamespace(exit_code=0, output=b'invalid')):
            with self.subTest(output=result.output):
                self.containers['cli'].exec_run.return_value = result
                self.assertFalse(self.terminal.startup_recovery_ready(self.account, self.work))

    def test_missing_or_linked_workspace_proof_is_refused(self) -> None:
        """恢复不能凭目录存在重建身份或跟随账号可替换的链接。:return: None。"""
        original = self.marker.read_bytes()
        self.marker.unlink()
        self.assertFalse(self.terminal.startup_recovery_ready(self.account, self.work))
        outside = self.fixture.root / 'outside-proof.json'
        outside.write_bytes(original)
        self.marker.symlink_to(outside)
        self.assertFalse(self.terminal.startup_recovery_ready(self.account, self.work))
        self.assertEqual(original, outside.read_bytes())
        self.marker.unlink()
        self.marker.write_bytes(original)
        self.workspace.rmdir()
        self.workspace.symlink_to(self.fixture.root, target_is_directory=True)
        self.assertFalse(self.terminal.startup_recovery_ready(self.account, self.work))

    def test_unready_environment_or_missing_database_never_creates_resources(self) -> None:
        """环境未就绪或查询失败时只拒绝，不唤醒、重建或补造环境。:return: None。"""
        self.runtime._update(self.row, state='cli_reconcile')
        self.assertFalse(self.terminal.startup_recovery_ready(self.account, self.work))
        with patch.object(self.runtime, 'database', side_effect=OSError('synthetic-secret')):
            self.assertFalse(self.terminal.startup_recovery_ready(self.account, self.work))
        self.fixture.client.containers.run.assert_not_called()
