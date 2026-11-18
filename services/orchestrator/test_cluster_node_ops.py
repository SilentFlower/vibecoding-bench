"""本机 Node 停机入口覆盖独立验收、实际停止及固定批次恢复。"""
from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import Mock

from cluster_deployment import node_container_name
from cluster_node_ops import node_action
from project_library import digest_json
from runtime_files import atomic_json


class NodeOperationTests(unittest.TestCase):
    """真实安装标记与可观察的 Docker 操作替身。"""

    def setUp(self) -> None:
        """保存唯一节点身份与各类实际容器。:return: None。"""
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root, self.key = Path(temporary.name), 'a' * 32
        atomic_json(self.root / 'cluster-node.json', {'protocol': 1, 'node_key': self.key, 'deployment_id': 'synthetic'})
        self.order, self.containers = [], []
        for role in ('node-control', 'account-network', 'account-sender', 'account'):
            labels = {'vibebench.product': 'v3', 'vibebench.deployment': 'synthetic',
                'vibebench.cluster-node': self.key, 'vibebench.role': role, 'vibebench.release': 'current'}
            container = Mock(id=role, labels=labels, status='running')
            container.name = node_container_name('synthetic', self.key) if role == 'node-control' else role
            container.attrs = {'Mounts': [{'Destination': '/data', 'Source': str(self.root), 'RW': True}],
                'State': {'Running': True, 'Pid': 123}}
            def stop(timeout, current=container):
                """记录真实顺序并发布停止事实。:return: None。"""
                self.order.append(current.id)
                current.status = 'exited'
                current.attrs['State'] = {'Running': False, 'Pid': 0}
            container.stop.side_effect = stop
            self.containers.append(container)
        self.program = Mock(id='program', labels={'vibebench.project-verifier': 'native',
            'vibebench.node-key': self.key, 'vibebench.verifier-root': digest_json(str(self.root))}, status='running')
        self.program.attrs = {'State': {'Running': True, 'Pid': 456}}
        def stop_program(timeout):
            """保存独立验收的停止结果。:return: None。"""
            self.order.append('program')
            self.program.status = 'exited'
            self.program.attrs['State'] = {'Running': False, 'Pid': 0}
        self.program.stop.side_effect = stop_program
        self.client = SimpleNamespace(containers=SimpleNamespace(list=Mock(side_effect=lambda **kwargs:
            [self.program] if 'vibebench.project-verifier=native' in kwargs['filters']['label'] else self.containers)))

    def test_stop_covers_independent_program_before_account_and_control(self) -> None:
        """停止包含独立程序，全部实际退出后才返回停止状态。:return: None。"""
        result = node_action(self.root, self.root, 'stop', client=self.client)
        self.assertEqual(['program', 'account', 'account-sender', 'account-network', 'node-control'], self.order)
        self.assertTrue(all(item['state'] == 'exited' for item in result['containers']))

    def test_foreign_program_root_is_rejected_before_any_stop(self) -> None:
        """另一数据根的验收容器阻断本次操作，避免跨安装停止。:return: None。"""
        self.program.labels['vibebench.verifier-root'] = digest_json('/another-installation')
        with self.assertRaisesRegex(ValueError, '数据归属'):
            node_action(self.root, self.root, 'stop', client=self.client)
        self.assertEqual([], self.order)

    def test_up_requires_explicit_installed_batch_and_starts_only_control(self) -> None:
        """控制恢复保持原镜像批次，账号由原调度及生命周期唤醒。:return: None。"""
        with self.assertRaisesRegex(ValueError, '批次变化'):
            node_action(self.root, self.root, 'up', release='another', client=self.client)
        node_action(self.root, self.root, 'up', release='current', client=self.client)
        self.containers[0].start.assert_called_once_with()
        for container in self.containers[1:]:
            container.start.assert_not_called()
