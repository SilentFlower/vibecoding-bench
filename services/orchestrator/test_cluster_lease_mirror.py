"""原AccountRuntime与有限租约镜像的认领、心跳及超期输入边界测试。"""
from __future__ import annotations

import os
import unittest
from unittest.mock import Mock, patch

from account_runtime import AccountRuntime, derive_v3_fingerprint
from cluster_deployment import node_network_name
from cluster_lease_mirror import NodeLeaseMirror
import test_cluster_execution_grants as grant_fixture


class NodeLeaseMirrorTests(unittest.TestCase):
    """实际原认领与续租代码消费私有文件和真实节点SQLite投影。"""

    def setUp(self) -> None:
        """建立原中央已认领证明和实际原运行时。:return: None。"""
        fixture = grant_fixture.ExecutionGrantTests(methodName='runTest')
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        self.fixture, self.store, self.scope = fixture, fixture.store, fixture.scope
        self.store.create(fixture.grant)
        self.store.activate(self.scope)
        self.mirror = NodeLeaseMirror(self.store)
        self.mirror.attach(self.scope)
        variables = patch.dict(os.environ, {'V3_DEPLOYMENT_ID': 'synthetic', 'V3_NODE_KEY': fixture.node_key,
            'V3_ACCOUNT_IMAGE': 'synthetic:account', 'V3_NETWORK': node_network_name('synthetic', fixture.node_key)})
        variables.start()
        self.addCleanup(variables.stop)
        gateway = Mock()
        gateway._request.side_effect = self.mirror.request
        self.runtime = AccountRuntime(Mock(), fixture.data, fixture.data, fixture.database,
            derive_v3_fingerprint, gateway)
        self.runtime.execution_admission = self.mirror.authorize_job
        self.addCleanup(self.runtime.heartbeat_pool.shutdown)
        connection = fixture.database()
        try:
            self.row = dict(connection.execute('SELECT * FROM account_environments').fetchone())
        finally:
            connection.close()
        self.account = {'id': 1, 'name': 'synthetic', 'cc2api_account_id': 7}
        self.path = '/admin/runtime/accounts/7/lease'

    def claim(self):
        """按原Pi低优先级共享CLI流程认领原许可。:return: 原作业。"""
        with self.mirror.preparing(self.scope):
            return self.runtime.claim(self.row, self.account, self.scope.source, idle_only=True, shared_cli=True)

    def test_restart_can_restore_only_original_expired_lease_for_release(self) -> None:
        """重启恢复镜像保留旧截止，prepare和新输入仍被拒绝，释放只关闭节点证明。:return: None。"""
        self.fixture.now = 1021
        restored = NodeLeaseMirror(self.store)
        restored.recover(self.scope)
        self.assertEqual(1020, restored.request('GET', self.path)['lease']['expires_at'])
        with self.assertRaises(ValueError):
            with restored.preparing(self.scope):
                self.fail('原过期证明不得开启新启动')
        job = {'row': self.row, 'account': self.account, 'source': self.scope.source}
        with self.assertRaises(ValueError):
            restored.authorize_job(job)
        proof = {'owner': self.scope.source, 'generation': self.fixture.grant.lease.generation}
        self.assertEqual([], restored.request('POST', self.path, {'operation': 'release', **proof})['holders'])
        self.assertEqual('closed', self.store.get(self.scope)['phase'])

    def test_original_runtime_claim_uses_frozen_central_generation(self) -> None:
        """空闲检查只隐藏本次预认领，原claim保存同一租约代次。:return: None。"""
        with self.mirror.preparing(self.scope):
            self.assertIsNone(self.mirror.request('GET', self.path)['lease'])
        job = self.claim()
        self.assertEqual(self.fixture.grant.lease.generation, job['lease']['generation'])
        self.assertEqual(1020, job['lease']['expires_at'])
        self.assertTrue(self.runtime._execution_path(job).exists())
        self.runtime.authorize_input(job)
        self.assertEqual(self.scope.source, self.mirror.request('GET', self.path)['lease']['owner'])

    def test_expired_mirror_heartbeat_preserves_job_and_refuses_next_input(self) -> None:
        """节点心跳不续长截止，超期作业和收据留存供中央对账。:return: None。"""
        job = self.claim()
        self.fixture.now = 1021
        with patch.object(self.runtime, 'cleanup', side_effect=AssertionError('超期不能视作停止')):
            self.runtime._renew_job(job)
        self.assertTrue(self.runtime._owns_job(job))
        self.assertNotIn('heartbeat_failed', job)
        self.assertEqual(1020, self.store.get(self.scope)['grant']['not_after'])
        self.assertEqual(1020, job['lease']['expires_at'])
        with self.assertRaisesRegex(ValueError, '过期'):
            self.runtime.authorize_input(job)
        self.assertTrue(self.runtime._execution_path(job).exists())

    def test_stopped_local_release_closes_only_original_local_permit(self) -> None:
        """原运行时确认无exec后收口本地证明，保留中央原租约身份。:return: None。"""
        job = self.claim()
        self.runtime.release(job)
        self.assertFalse(self.runtime._owns_job(job))
        record = self.store.get(self.scope)
        self.assertEqual('closed', record['phase'])
        self.assertEqual(self.fixture.grant.lease.model_dump(), record['grant']['lease'])
        self.assertEqual([], self.mirror.request('GET', self.path)['holders'])
        with self.assertRaises(ValueError):
            self.mirror.attach(self.scope)

    def test_bound_login_release_only_removes_original_closed_local_mirror(self) -> None:
        """绑定登录实际关闭后只移除同一镜像，其他来源及真实Gateway租约身份保留。:return: None。"""
        source='login:'+'a'*12
        scope=self.scope.model_copy(update={'operation_id':'f'*32,'source':source,'role':'login'})
        lease=self.fixture.grant.lease.model_copy(update={'owner':source,'exclusive':True,'shared_cli':False})
        grant=self.fixture.grant.model_copy(update={**scope.model_dump(),'lease':lease})
        self.store.create(grant)
        self.store.activate(scope)
        self.mirror.attach(scope)
        with self.assertRaisesRegex(ValueError,'实际停止'):
            self.mirror.release_bound_login(scope)
        self.store.close(scope,'node_execution_closed')
        self.mirror.release_bound_login(scope)
        self.mirror.release_bound_login(scope)
        self.assertIn((self.scope.gateway_account_id,self.scope.source),self.mirror.scopes)
        self.assertNotIn((scope.gateway_account_id,scope.source),self.mirror.scopes)
        self.assertEqual(lease.model_dump(),self.store.get(scope)['grant']['lease'])
        self.assertEqual('active',self.store.get(self.scope)['phase'])

    def test_wrong_owner_generation_mode_and_unscoped_prepare_are_rejected(self) -> None:
        """镜像只接受本次已冻结范围，任意本地调用不能派生新许可。:return: None。"""
        for payload in ({'operation': 'prepare-cli-shared', 'owner': self.scope.source},
                {'operation': 'prepare-cli', 'owner': 'other'},
                {'operation': 'heartbeat', 'owner': self.scope.source, 'generation': 'wrong'}):
            with self.subTest(payload=payload), self.assertRaises(ValueError):
                self.mirror.request('POST', self.path, payload)
        with self.mirror.preparing(self.scope), self.assertRaisesRegex(ValueError, '模式'):
            self.mirror.request('POST', self.path, {'operation': 'prepare', 'owner': self.scope.source})
        job = {'account': self.account, 'source': self.scope.source, 'row': {**self.row, 'generation': 2}}
        with self.assertRaisesRegex(ValueError, '代次'):
            self.runtime.authorize_input(job)


if __name__ == '__main__':
    unittest.main()
