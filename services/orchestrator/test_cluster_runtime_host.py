"""持久节点运行时借用、账号配置隔离与临时入口兼容测试。"""
from __future__ import annotations

import json
import unittest
from unittest.mock import Mock

from cluster_execution import _GatewaySnapshot
from cluster_runtime_host import NodeRuntimeHost
import test_cluster_execution as execution_fixture


class _HostedRuntime(execution_fixture._Runtime):
    """按真实构造签名提供可观察生命周期的运行时替身。"""

    def __init__(self, client, data, host_data, database, fingerprint, gateway, quota_identity) -> None:
        """保留原依赖及共享jobs接口。:param client: Docker。:param data: 数据根。:param host_data: 宿主根。:param database: 节点库。:param fingerprint: 原画像。:param gateway: 配置提供器。:param quota_identity: 额度身份。:return: None。"""
        super().__init__(client, data, host_data, database, fingerprint, gateway, quota_identity)
        self.start, self.stop = Mock(), Mock()
        self.native_prewarm_account_id = 7
        self.quota_identity = quota_identity

    def _execution_records(self, row):
        return []


class NodeRuntimeHostTests(unittest.TestCase):
    """复用真实节点投影与准备入口，验证共享进程边界。"""

    def setUp(self) -> None:
        """建立节点执行器并显式绑定持久生命周期。:return: None。"""
        fixture = execution_fixture.NodeExecutionTests(methodName='runTest')
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        self.fixture, self.executor = fixture, fixture.executor
        self.host = NodeRuntimeHost(self.executor, runtime_factory=_HostedRuntime)
        self.addCleanup(self.host.close)

    def test_prepare_reuses_one_runtime_and_retains_original_notifications(self) -> None:
        """连续准备共享真实投影和同一线程池，通知仍归属本次账号快照。:return: None。"""
        first = self.executor.prepare(self.fixture.request)
        runtime = self.host.runtime
        second = self.executor.prepare(self.fixture.request)
        self.assertIs(runtime, self.host.runtime)
        runtime.start.assert_called_once()
        runtime.heartbeat_pool.shutdown.assert_not_called()
        self.assertIsNone(runtime.native_prewarm_account_id)
        self.assertEqual(([7], [7]), (first['native_notifications'], second['native_notifications']))
        self.assertEqual(2, second['environment']['generation'])
        self.assertEqual('synthetic-quota', runtime.quota_identity({'id': 1}))

    def test_configuration_reassignment_uses_released_node_binding(self) -> None:
        """原账号已解绑时，同一Gateway可由新正式账号登记；当前绑定冲突继续拒绝。:return: None。"""
        self.executor.prepare(self.fixture.request)
        with self.executor.database() as connection:
            connection.execute("INSERT INTO accounts(id,name,profile_path,cc2api_account_id) VALUES(2,'other','profiles/other',8)")
        with self.assertRaisesRegex(ValueError,'另一任务账号'):
            self.host.gateway.adopt(_GatewaySnapshot(7,{},bench_account_id=2),None)
        with self.executor.database() as connection:
            connection.execute('UPDATE accounts SET cc2api_account_id=NULL WHERE id=1')
            connection.execute('UPDATE accounts SET cc2api_account_id=7 WHERE id=2')
        self.host.gateway.adopt(_GatewaySnapshot(7,{'original_binding':7},bench_account_id=2),None)
        self.assertEqual({'original_binding':7},self.host.gateway._request('GET','/admin/runtime/accounts/7/config'))

    def test_configuration_provider_isolates_accounts_and_returns_copies(self) -> None:
        """账号配置分别注册，修改返回对象不回写原快照。:return: None。"""
        self.executor.prepare(self.fixture.request)
        second = _GatewaySnapshot(8, {'proxy_url': 'socks5://synthetic.invalid:1080'}, bench_account_id=2)
        self.host.gateway.adopt(second, lambda account: 'other-quota')
        result = self.host.gateway._request('GET', '/admin/runtime/accounts/8/config')
        result['proxy_url'] = 'changed-copy'
        self.assertEqual('socks5://synthetic.invalid:1080', self.host.gateway._request('GET', '/admin/runtime/accounts/8/config')['proxy_url'])
        self.assertEqual('other-quota', self.host.gateway.quota_identity({'id': 2}))
        self.assertEqual('synthetic-quota', self.host.gateway.quota_identity({'id': 1}))
        for path in ('/admin/accounts', '/admin/runtime/accounts/7/lease', '/admin/runtime/accounts/9/config'):
            with self.assertRaises(ValueError):
                self.host.gateway._request('GET', path)
        with self.assertRaisesRegex(ValueError, '另一任务账号'):
            self.host.gateway.adopt(_GatewaySnapshot(7, {}, bench_account_id=2), lambda account: 'wrong')

    def test_close_stops_owned_runtime_and_refuses_later_borrow(self) -> None:
        """关闭按实际节点生命周期执行，后续输入不会得到新运行时。:return: None。"""
        self.executor.prepare(self.fixture.request)
        runtime = self.host.runtime
        self.host.close()
        self.host.close()
        runtime.stop.assert_called_once()
        with self.assertRaisesRegex(ValueError, '借用已关闭'):
            self.executor.prepare(self.fixture.request)
        self.assertEqual('synthetic-access', json.loads((self.fixture.root / 'profiles/synthetic/.credentials.json').read_text())['claudeAiOauth']['accessToken'])

    def test_failed_start_preserves_original_error_when_cleanup_also_fails(self) -> None:
        """节点启动和收尾均失败时保留首个故障及完整原因链。:return: None。"""
        created = []

        def factory(*arguments):
            runtime = _HostedRuntime(*arguments)
            runtime.start.side_effect = ValueError('合成启动失败')
            runtime.stop.side_effect = RuntimeError('合成收尾失败')
            created.append(runtime)
            return runtime

        self.host.runtime_factory = factory
        with self.assertRaisesRegex(ValueError, '启动失败') as failure:
            self.executor.prepare(self.fixture.request)
        self.assertIsInstance(failure.exception.__cause__, RuntimeError)
        created[0].stop.assert_called_once()
