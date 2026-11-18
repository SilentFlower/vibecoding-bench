"""验证后台节点安装的真实HTTP、SQLite状态与更新活动生命周期。"""
import threading
import time
import unittest
import uuid
from unittest.mock import Mock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from cluster_api import cluster_router
from cluster_nodes import NodeCreate
from cluster_service import ClusterService
from runtime_files import atomic_json
from system_update_gate import DeploymentGate
import test_cluster_nodes


class NodeInstallationTests(unittest.TestCase):
    """使用合成安装器阻塞长IO，核对HTTP立即返回和门禁持续保护。"""

    def setUp(self) -> None:
        """建立隔离节点、安装器和真实维护门禁。:return: None。"""
        self.fixture = test_cluster_nodes.ClusterNodeTests(methodName='runTest')
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.service = self.fixture.service
        self.node = self.service.register(NodeCreate(**self.fixture.config, private_key=self.fixture.key.read_text()))
        self.installer = Mock()
        self.installer.prepare.return_value = {'state': 'prepared', 'release': 'synthetic', 'protocol': 1}
        self.gate = DeploymentGate(self.fixture.root / 'gate', 'synthetic')
        self.gate_path = self.fixture.root / 'gate' / 'admission.json'
        self.gate_record = {'schema_version': 1, 'deployment': 'synthetic', 'operation_id': None,
            'epoch': str(uuid.uuid4()), 'phase': 'idle', 'target_release': None,
            'revision': str(uuid.uuid4()), 'created_at': time.time()}
        atomic_json(self.gate_path, self.gate_record)
        for context in [patch('cluster_service.NodeDeployment', return_value=self.installer),
                patch('cluster_service.UPDATE_GATE', self.gate)]:
            context.start()
            self.addCleanup(context.stop)
        app = FastAPI()
        app.include_router(cluster_router(lambda: self.service))
        self.client = TestClient(app)
        self.addCleanup(self.client.close)
        self.path = f"/api/nodes/{self.node['id']}/prepare"

    def settled(self) -> dict:
        """等待合成作业收口，再读取实际公开状态。:return: 节点投影。"""
        deadline = time.monotonic() + 3
        while True:
            with self.service.lock:
                running = bool(self.service.install_workers)
            if not running:
                return next(row for row in self.client.get('/api/nodes').json()['items'] if row['id'] == self.node['id'])
            self.assertLess(time.monotonic(), deadline)
            time.sleep(0.01)

    def test_returns_202_deduplicates_and_keeps_gate_until_finished(self) -> None:
        """浏览器离开后后台仍有门禁，重复提交复用原安装，维护期拒绝新安装。:return: None。"""
        entered, released = threading.Event(), threading.Event()
        self.addCleanup(released.set)
        def install(*args):
            entered.set()
            if not released.wait(3):
                raise RuntimeError('合成安装未释放')
            return {'state': 'prepared', 'release': 'synthetic', 'protocol': 1}
        self.installer.prepare.side_effect = install
        response = self.client.post(self.path, json={'revision': 1})
        self.assertEqual(202, response.status_code)
        self.assertEqual('preparing', response.json()['preparation']['state'])
        self.assertTrue(entered.wait(1))
        self.assertGreater(self.gate.state()['active'], 0)
        repeated = self.client.post(self.path, json={'revision': 1})
        self.assertEqual(202, repeated.status_code)
        self.assertEqual(1, self.installer.prepare.call_count)
        self.assertEqual(409, self.client.request('DELETE', f"/api/nodes/{self.node['id']}", json={'revision': 1}).status_code)
        self.assertEqual(409, self.client.post(self.path, json={'revision': 2}).status_code)
        self.gate_record.update(phase='blocked', operation_id=str(uuid.uuid4()))
        atomic_json(self.gate_path, self.gate_record)
        released.set()
        self.assertEqual('prepared', self.settled()['preparation']['state'])
        self.assertEqual(0, self.gate.state()['active'])
        self.assertEqual(409, self.client.post(self.path, json={'revision': 1}).status_code)
        self.assertEqual(1, self.installer.prepare.call_count)

    def test_failure_is_public_and_releases_for_retry(self) -> None:
        """安装失败写入脱敏状态，原锁与门禁释放后可明确重试。:return: None。"""
        self.installer.prepare.side_effect = ValueError('PRIVATE_INSTALL_CANARY')
        self.assertEqual(202, self.client.post(self.path, json={'revision': 1}).status_code)
        failed = self.settled()
        self.assertEqual('failed', failed['preparation']['state'])
        self.assertNotIn('PRIVATE_INSTALL_CANARY', str(failed))
        self.assertEqual(0, self.gate.state()['active'])
        self.installer.prepare.side_effect = None
        self.assertEqual(202, self.client.post(self.path, json={'revision': 1}).status_code)
        self.assertEqual('prepared', self.settled()['preparation']['state'])

    def test_thread_start_failure_releases_gate_and_lock(self) -> None:
        """线程创建失败时保存失败并释放原活动，后续安装可正常提交。:return: None。"""
        with patch('cluster_service.threading.Thread.start', side_effect=RuntimeError('合成线程启动失败')):
            with self.assertRaises(RuntimeError):
                self.service.prepare_node(self.node['id'], 1)
        self.assertEqual(0, self.gate.state()['active'])
        self.assertEqual('failed', self.settled()['preparation']['state'])
        self.assertEqual(202, self.client.post(self.path, json={'revision': 1}).status_code)
        self.assertEqual('prepared', self.settled()['preparation']['state'])

    def test_restart_marks_interrupted_installation_for_check(self) -> None:
        """重启后的旧安装保持待核对状态，保留节点版本并拒绝关闭后新作业。:return: None。"""
        self.service.store.save_preparation(self.node['id'], 1, {'state': 'preparing'})
        recovered = ClusterService(self.fixture.store, self.fixture.root, Mock(), self.fixture.root / 'recovered')
        self.addCleanup(recovered.close)
        value = next(row for row in recovered.store.list() if row['id'] == self.node['id'])
        self.assertEqual('needs_check', value['preparation']['state'])
        self.assertEqual(1, value['revision'])
        recovered.close()
        with self.assertRaisesRegex(ValueError, '关闭'):
            recovered.prepare_node(self.node['id'], 1)
