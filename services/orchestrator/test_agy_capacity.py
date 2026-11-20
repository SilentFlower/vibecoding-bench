"""通过真实环境记录、配置文件及受控 Docker 回执验证 AGY 在线调并发。"""
import json
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch

from agy_capacity import CapacityError, change_capacity, pending_layout, reconcile_pending
from agy_environment import SOURCE_SHA256, lookup, register, sender_config
from resource_budget import agy_worker_limits, sender_pid_limit
from runtime_files import atomic_json
import test_agy_environment


class AgyCapacityTests(unittest.TestCase):
    """覆盖实际配置与角色预算的两个生效阶段。"""

    def setUp(self):
        """建立合成账号和三个角色的实际额度视图。@return 无。"""
        fixture = test_agy_environment.AgyEnvironmentTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        self.runtime = fixture.runtime
        self.row = register(self.runtime, 17)
        self.runtime._update(self.row, state='ready', generation=2, container_id='cli',
            network_container_id='network', sender_container_id='sender')
        self.row = lookup(self.runtime, 17)
        self.authority = {'account_id': 17, 'platform': 'antigravity', 'auth_type': 'oauth',
            'concurrency': 3, 'capacity_edit_active': True, 'credential_state': {'phase': 'ready'}}
        self.runtime.gateway._request.side_effect = lambda *args: dict(self.authority)
        self.config_path = self.runtime._root(self.row) / 'runtime/sender/sender.json'
        self.config_path.parent.mkdir(parents=True)
        self.capacity = 3
        self.allocated = 3
        self.containers = {}
        self.changes = []
        self.lose_sender_update = False
        self.labels = {'vibebench.agy-runtime-protocol': '1', 'vibebench.agy-runtime-source-sha256': SOURCE_SHA256}
        self.configure(3, '4g')
        self.runtime.client.api._url.side_effect = lambda _, identifier: identifier
        self.runtime.client.api._post_json.side_effect = self.update_resource
        self.role_patch = patch('agy_capacity.role_container', side_effect=lambda _, row, role: self.containers[role])
        self.sender_patch = patch('agy_capacity._sender', side_effect=self.sender)
        self.role_patch.start()
        self.mock_sender = self.sender_patch.start()
        self.addCleanup(self.role_patch.stop)
        self.addCleanup(self.sender_patch.stop)

    def configure(self, workers, memory):
        """冻结原角色基线。@param workers 原并发。@param memory 账号内存配置。@return 无。"""
        fingerprint = {**json.loads(self.row['fingerprint_json']), 'mem': memory}
        self.runtime._update(self.row, fingerprint_json=json.dumps(fingerprint))
        self.row = lookup(self.runtime, 17)
        _, limits = agy_worker_limits(workers, fingerprint)
        for role, (ram, swap) in limits.items():
            self.containers[role] = SimpleNamespace(id=role, labels=self.labels, reload=lambda: None,
                attrs={'HostConfig': {'Memory': ram, 'MemorySwap': swap,
                    'PidsLimit': sender_pid_limit(workers, agy=True) if role == 'sender' else 512},
                    'State': {'Running': True}},
                stats=MagicMock(return_value={'memory_stats': {'usage': 1}, 'pids_stats': {'current': 1}}))
        atomic_json(self.config_path, {'agy': sender_config({'concurrency': workers}, fingerprint, self.labels),
            'binding': {'account_id': 17, 'environment_id': self.row['environment_id'], 'generation': 2}})
        self.authority['concurrency'] = self.capacity = self.allocated = workers

    def update_resource(self, role, *, data):
        """模拟资源已生效后回包丢失。@param role 实际角色。@param data 冻结额度。@return 无。"""
        self.changes.append(role)
        self.containers[role].attrs['HostConfig'].update(data)
        if role == 'sender' and self.lose_sender_update:
            self.lose_sender_update = False
            raise OSError('合成 Docker 回包中断')

    def sender(self, row, binding, workers=None):
        """记录监督器真实回执。@param row 环境。@param binding 绑定。@param workers 新上限。@return 当前生效状态。"""
        if workers is not None:
            self.capacity = workers
        return {'state': 'busy', 'max_workers': self.capacity, 'allocated_workers': self.allocated}

    def change(self, phase, before=3, target=4, operation='1' * 32):
        """执行原管理操作。@param phase 阶段。@param before 原值。@param target 目标。@param operation 操作ID。@return 无。"""
        change_capacity(self.runtime, 17, operation, before, target, phase)

    def test_prepare_expands_roles_before_authority_and_restore_if_never_saved(self):
        """物理扩容在保存前验证，控制重启按网关原值恢复。@return 无。"""
        original = json.loads(self.config_path.read_text())['agy']
        self.change('prepare')
        prepared = json.loads(self.config_path.read_text())['agy']
        self.assertEqual(self.changes, ['cli', 'sender'])
        self.assertEqual(self.capacity, 4)
        self.assertEqual(self.authority['concurrency'], 3)
        self.assertTrue(pending_layout(self.runtime, self.row, prepared, original))
        self.assertFalse(pending_layout(self.runtime, self.row, {**prepared, 'module_root': '/synthetic'}, original))
        reconcile_pending(self.runtime)
        self.assertEqual(self.capacity, 4)
        self.authority['capacity_edit_active'] = False
        reconcile_pending(self.runtime)
        self.assertEqual(self.changes, ['cli', 'sender', 'sender', 'cli'])
        self.assertEqual(self.capacity, 3)
        self.assertEqual(json.loads(self.config_path.read_text())['agy'], original)

    def test_shrink_preserves_oversubscribed_running_workers_until_reaped(self):
        """缩容先应用准入，现有四个进程返还前保留对应资源。@return 无。"""
        self.configure(4, '4g')
        self.change('prepare', before=4, target=3)
        self.assertEqual(self.capacity, 4)
        self.authority['concurrency'] = 3
        self.change('settle', before=4, target=3)
        self.assertEqual(self.capacity, 3)
        self.assertEqual(self.changes, [])
        self.assertEqual(self.containers['sender'].attrs['HostConfig']['PidsLimit'], sender_pid_limit(4, agy=True))
        self.authority['capacity_edit_active'] = False
        self.allocated = 3
        reconcile_pending(self.runtime)
        self.assertEqual(self.changes, ['sender', 'cli'])
        self.assertEqual(self.containers['sender'].attrs['HostConfig']['PidsLimit'], sender_pid_limit(3, agy=True))

    def test_lost_docker_update_receipt_recovers_real_limits(self):
        """Docker 回包中断后恢复原容量，依据实际角色重读。@return 无。"""
        self.lose_sender_update = True
        with self.assertRaises(OSError):
            self.change('prepare')
        self.assertEqual(self.containers['sender'].attrs['HostConfig']['PidsLimit'], sender_pid_limit(4, agy=True))
        self.change('settle')
        self.assertEqual(self.capacity, 3)
        self.assertEqual(self.containers['sender'].attrs['HostConfig']['PidsLimit'], sender_pid_limit(3, agy=True))

    def test_memory_and_unsupported_sender_are_rejected_before_effect(self):
        """受限账号与旧发送器保留原状态。@return 无。"""
        self.configure(3, '2g')
        with self.assertRaisesRegex(CapacityError, 'capacity_memory'):
            self.change('prepare')
        self.configure(3, 'unlimited')
        self.mock_sender.side_effect = CapacityError('capacity_unsupported')
        with self.assertRaisesRegex(CapacityError, 'capacity_unsupported'):
            self.change('prepare')
        self.assertEqual(self.changes, [])

    def test_stopped_environment_accepts_supported_maximum_without_waking(self):
        """历史停止环境的下次准备使用新上限。@return 无。"""
        self.configure(3, 'unlimited')
        self.runtime._update(self.row, state='stopped')
        for container in self.containers.values():
            container.attrs['State']['Running'] = False
        self.change('prepare', target=64)
        self.authority['concurrency'] = 64
        self.change('settle', target=64)
        self.mock_sender.assert_not_called()
        self.assertEqual(lookup(self.runtime, 17)['state'], 'stopped')
        self.assertEqual(json.loads(self.config_path.read_text())['agy']['max_workers'], 64)
        self.assertEqual(self.containers['sender'].attrs['HostConfig']['PidsLimit'], sender_pid_limit(64, agy=True))

    def test_expand_again_before_shrink_resources_finish_reclaiming(self):
        """已有进程仍在收尾时复用原额度，连续调整以新目标为准。@return 无。"""
        self.configure(6, '4g')
        self.change('prepare', before=6, target=2)
        self.authority['concurrency'] = 2
        self.change('settle', before=6, target=2)
        self.runtime.gateway._request.side_effect = lambda method, path: {
            **self.authority, 'capacity_edit_active': path.endswith('2' * 32)}
        self.change('prepare', before=2, target=3, operation='2' * 32)
        self.authority['concurrency'] = 3
        self.change('settle', before=2, target=3, operation='2' * 32)
        self.assertEqual(self.capacity, 3)
        self.assertEqual(self.changes, [])
