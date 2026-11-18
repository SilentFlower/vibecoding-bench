"""正式中央入口的远程额度认领、凭据准备及工程准入合同。"""
from __future__ import annotations

import json
import threading
import time
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

import main
import test_quota as quota_fixture


class ClusterMainTests(unittest.TestCase):
    """使用原QuotaGuard和真实中央数据库核对生产回调。"""

    def setUp(self) -> None:
        """创建实际账号、原QuotaGuard及固定受信绑定。:return: None。"""
        fixture = quota_fixture.QuotaGuardTests(methodName='runTest')
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        self.fixture = fixture
        connection = main.get_db()
        try:
            with connection:
                connection.execute('UPDATE accounts SET cc2api_account_id=7 WHERE id=1')
            self.account = dict(connection.execute('SELECT * FROM accounts WHERE id=1').fetchone())
        finally:
            connection.close()
        for key in ('account_runtime', 'credential_ownership', 'cluster_service', 'cluster_terminal_sessions', 'pi_owners'):
            context = patch.object(main, key, None)
            context.start()
            self.addCleanup(context.stop)
        self.source = 'projects:' + 'a' * 32 + ':1'

    def test_run_node_uses_frozen_execution_after_account_moves(self) -> None:
        """历史运行按原账本展示位置，公开响应只含固定定位字段。:return: None。"""
        runner=Mock()
        runner.for_run.return_value={'node_id':3,'record':{'scope':{'node_key':'a'*32,
            'environment_id':'e'*32,'assignment_revision':2,'generation':5,'secret':'synthetic-private'}}}
        runner.sessions.service.store.get.return_value={'name':'原执行节点','config_json':'synthetic-private'}
        with patch.object(main,'cluster_runner',runner):
            value=main._public_run_node('original-run')
        self.assertEqual({'id':3,'key':'a'*32,'name':'原执行节点','environment_id':'e'*32,
            'assignment_revision':2,'generation':5},value)
        runner.sessions.service.store.assignment.assert_not_called()
        runner.sessions.service.connection.assert_not_called()

    def test_remote_admission_claims_original_quota_and_disabled_account_cannot_claim_again(self) -> None:
        """正式远程回调使用同一额度身份和来源，停用后拒绝新认领。:return: None。"""
        identity = main._remote_projects_quota_admit(self.account, self.source)
        self.assertEqual(main._quota_identity(self.account), identity)
        self.assertEqual(identity, self.fixture.guard.snapshot(self.account)['identity'])
        connection = main.get_db()
        try:
            with connection:
                connection.execute('UPDATE accounts SET enabled=0 WHERE id=1')
        finally:
            connection.close()
        with self.assertRaisesRegex(ValueError, '账号'):
            main._remote_projects_quota_admit(self.account, self.source)
        with self.assertRaisesRegex(ValueError, '来源'):
            main._remote_projects_quota_admit(self.account, 'other-source')

    def test_remote_credentials_prepare_keeps_profile_mirror_in_original_owner_boundary(self) -> None:
        """远程工程先由唯一所有者解析凭据，实际HOME发布留给所属节点准备。:return: None。"""
        owner, runtime = Mock(), Mock()
        service = SimpleNamespace(store=SimpleNamespace(assignment=lambda _: {'kind': 'ssh'}))
        with patch.object(main, 'credential_ownership', owner), patch.object(main, 'account_runtime', runtime), \
                patch.object(main, 'cluster_service', service), patch.object(main, '_resolve_and_sync_cc2api_credentials') as mirror:
            main._projects_credentials(self.account)
        owner.guard.assert_called_once_with(self.account)
        mirror.assert_called_once_with(self.account['name'], 7, main.OAUTH_REFRESH_BUFFER_SEC, False)
        runtime.sync_credentials.assert_not_called()

    def test_engineering_admission_counts_original_remote_source_and_blocks_reconcile(self) -> None:
        """原节点工作参与CLI容量和原额度来源判定，待核对状态关闭后续输入。:return: None。"""
        row = {'source': self.source, 'phase': 'running', 'record': {'grant': {'not_after': time.time() + 30},
            'lease': {'owner': self.source}}}
        sessions = SimpleNamespace(ledger=SimpleNamespace(active=lambda _: [row]))
        runtime = SimpleNamespace(lock=threading.RLock(), jobs={})
        work = {'id': 'a' * 32, 'account_id': 1, 'runtime_json': json.dumps({'source': self.source})}
        with patch.object(main, 'cluster_terminal_sessions', sessions), patch.object(main, 'account_runtime', runtime), \
                patch.object(main, 'quota_guard', None):
            gate = main._projects_admission(self.account, work)
            self.assertTrue(gate['allowed'])
            self.assertEqual(1, gate['cli_capacity']['active'])
            row['phase'] = 'reconcile'
            gate = main._projects_admission(self.account, work)
            self.assertFalse(gate['allowed'])
            self.assertFalse(gate['retryable'])
            self.assertEqual('environment', gate['reason'])
