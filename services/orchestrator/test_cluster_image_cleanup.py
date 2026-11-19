"""用真实节点维护文件验证镜像回收、引用保护和重试。"""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from docker.errors import APIError, NotFound

from cluster_deployment import node_container_name
from cluster_synchronization import NodeSynchronization
from runtime_files import atomic_json
from runtime_names import image_reference


class NodeImageCleanupTests(unittest.TestCase):
    """验证已就绪远程节点的后台回收，以及换版记录代表的安全边界。"""

    def setUp(self) -> None:
        """建立节点和六批发布镜像，模拟旧版留存回执。"""
        storage = tempfile.TemporaryDirectory()
        self.addCleanup(storage.cleanup)
        private = Path(storage.name)
        self.directory = private / 'maintenance'
        self.node_key = 'a' * 32
        self.labels = {'vibebench.product': 'v3', 'vibebench.deployment': 'synthetic',
                       'vibebench.cluster-node': self.node_key, 'vibebench.role': 'node-control'}
        self.images = {}
        self.names = {}
        for number in range(1, 7):
            for role in ('control', 'account'):
                release = f'ci-{number}-1'
                ref = image_reference(role, release, namespace='ghcr.io/silentflower')
                image_id = 'sha256:' + hashlib.sha256(ref.encode()).hexdigest()
                attrs = {'Id': image_id, 'Config': {'Labels': {'vibebench.product': 'v3',
                    'vibebench.release': release, 'vibebench.role': role}}, 'RepoTags': [ref], 'RepoDigests': []}
                self.images[image_id] = self.names[ref] = SimpleNamespace(id=image_id, attrs=attrs)
        self.preparation = {'state': 'prepared', 'phase': 'ready', 'release': 'ci-6-1',
            'account_release': 'ci-6-1', 'account_reference': self.reference('account', 6),
            'account_image_id': self.names[self.reference('account', 6)].id, 'container_id': 'running-control'}
        self.row = {'id': 2, 'kind': 'ssh', 'node_key': self.node_key, 'revision': 1,
            'config_json': '{"data_root":"/srv/synthetic"}', 'preparation_json': json.dumps(self.preparation)}
        self.store = Mock()
        self.store.get.return_value = self.row
        self.store.list.return_value = [{**self.row, 'preparation': self.preparation, 'account_count': 0}]
        self.control = SimpleNamespace(id='running-control', status='running',
            attrs=self.control_record(6, 6, 'running-control'))
        self.node = Mock(private=private)
        self.node.agent_health.return_value = {'protocol': 1, 'node_key': self.node_key, 'deployment': 'synthetic',
                                             'release': 'ci-6-1', 'state': 'ready'}
        self.node.observe.return_value = {'disk_available_bytes': 4096}
        self.remote = Mock()
        self.remote.images.get.side_effect = self.inspect_image
        self.remote.api.images.side_effect = lambda **kwargs: list(self.images)
        self.remote.api.remove_image.side_effect = self.delete_reference
        self.remote.containers.get.return_value = self.control
        self.containers = [self.control]
        self.remote.containers.list.side_effect = lambda **kwargs: list(self.containers)
        self.service = SimpleNamespace(lock=threading.Lock(), operation_locks={}, store=self.store,
            connection=Mock(return_value=self.node), docker=Mock(return_value=self.remote), closing=False)
        runtime = SimpleNamespace(release_id='ci-6-1', deployment='synthetic')
        self.sync = NodeSynchronization(self.service, runtime, Mock(), Mock())
        self.addCleanup(self.sync.close)
        self.gate = {'phase': 'idle'}
        gate = patch('cluster_synchronization.UPDATE_GATE.state', side_effect=lambda: self.gate)
        gate.start()
        self.addCleanup(gate.stop)
        for number, account in ((1, 1), (2, 2), (3, 4), (4, 4), (5, 4)):
            self.save_job(number, account, legacy=number == 4)

    def reference(self, role: str, number: int) -> str:
        """返回合成发布标签。:param role: 角色。:param number: 批号。:return: 标签。"""
        return image_reference(role, f'ci-{number}-1', namespace='ghcr.io/silentflower')

    def control_record(self, number: int, account: int, container_id: str) -> dict:
        """保存同一控制容器的实际镜像和账号组合。"""
        ref = self.reference('control', number)
        return {'Id': container_id, 'Image': self.names[ref].id, 'Config': {'Image': ref,
            'Labels': {**self.labels, 'vibebench.release': f'ci-{number}-1'},
            'Env': [f'V3_ACCOUNT_IMAGE={self.reference("account", account)}', f'V3_ACCOUNT_RELEASE=ci-{account}-1']}}

    def save_job(self, number: int, account: int, *, legacy: bool = False) -> None:
        """写入原维护检查点和冻结控制收据。"""
        job_id = f'{number:032x}'
        original = self.control_record(number, account, f'old-control-{number}')
        atomic_json(self.directory / (job_id + '-container.json'), original)
        ref = self.reference('account', account)
        prior = {} if legacy else {'account_reference': ref, 'account_release': f'ci-{account}-1',
                                   'account_image_id': self.names[ref].id}
        path = self.directory / ('current.json' if number == 5 else job_id + '.json')
        atomic_json(path, {'phase': 'completed', 'node_key': self.node_key, 'node_id': 2, 'job_id': job_id,
            'config_sha256': hashlib.sha256(self.row['config_json'].encode()).hexdigest(),
            'target_release': f'ci-{number+1}-1', 'old_release': f'ci-{number}-1',
            'old_container': original['Id'], 'old_image': original['Image'], 'preparation_before': prior})
        os.utime(path, (number, number))

    def inspect_image(self, value: str):
        """返回合成 Docker 镜像。:param value: 引用或 ID。:return: 镜像。"""
        image = self.names.get(value) or self.images.get(value)
        if image is None:
            raise NotFound('synthetic')
        return image

    def delete_reference(self, ref: str, *, force: bool, noprune: bool) -> None:
        """删除精确引用并模拟所有引用消失后回收内容。"""
        self.assertFalse(force)
        self.assertTrue(noprune)
        image = self.names.pop(ref)
        for key in ('RepoTags', 'RepoDigests'):
            if ref in image.attrs[key]:
                image.attrs[key].remove(ref)
        if not image.attrs['RepoTags'] and not image.attrs['RepoDigests']:
            del self.images[image.id]

    def receipt(self) -> dict:
        """返回持久回收结果。:return: 原节点审计记录。"""
        return json.loads((self.directory / 'image-cleanup.json').read_text())

    def test_cleanup_old_releases_after_health_check(self) -> None:
        """保护最近两套组合、停止容器、其它控制端配置以及附加别名。"""
        ref, alias_ref = self.reference('control', 2), 'other/image:kept'
        self.names[alias_ref] = self.names[ref]
        self.names[ref].attrs['RepoTags'].append(alias_ref)
        stopped = self.reference('account', 2)
        self.containers.append(SimpleNamespace(status='exited', attrs={'Image': self.names[stopped].id,
            'Config': {'Image': stopped, 'Env': None,
                       'Labels': {'vibebench.product': 'v3', 'vibebench.deployment': 'another'}}}))
        protected_account = self.reference('account', 1)
        self.containers.append(SimpleNamespace(attrs={'Image': 'other-image', 'Config': {
            'Image': 'other-control', 'Labels': {'vibebench.product': 'v3'},
            'Env': ['V3_ACCOUNT_IMAGE=' + protected_account]}}))
        original = self.reference('control', 1)
        digest = original.rsplit(':', 1)[0] + '@sha256:' + 'b' * 64
        self.names[digest] = self.names[original]
        self.names[original].attrs['RepoDigests'] = [digest]

        self.sync._cleanup_ready_nodes()
        result = self.receipt()
        self.assertEqual('completed', result['state'])
        self.assertEqual('removed', result['outcomes'][original])
        self.assertEqual('removed', result['outcomes'][self.reference('control', 3)])
        self.assertEqual('identity_or_alias_changed', result['outcomes'][ref])
        self.assertEqual('referenced', result['outcomes'][stopped])
        self.assertEqual('referenced', result['outcomes'][protected_account])
        self.assertNotIn(digest, self.names)
        for role, number in (('control', 6), ('control', 5), ('control', 4), ('account', 6), ('account', 4)):
            self.assertIn(self.reference(role, number), self.names)
        self.node.agent_health.assert_called_once_with(node_container_name('synthetic', self.node_key))
        self.store.save_preparation.assert_not_called()
        self.remote.api.remove_image.reset_mock()
        self.sync._cleanup_ready_nodes()
        self.remote.api.remove_image.assert_not_called()

    def test_partial_cleanup_retries_without_reopening_node_installation(self) -> None:
        """删除中断时保存已完成项，恢复后只处理仍存在的旧引用。"""
        original_delete = self.delete_reference
        fail = self.reference('control', 2)

        def remove(ref: str, **options):
            if ref == fail:
                raise APIError('synthetic')
            original_delete(ref, **options)

        self.remote.api.remove_image.side_effect = remove
        self.sync._cleanup_ready_nodes()
        removed = self.reference('control', 3)
        self.assertEqual('pending', self.receipt()['state'])
        self.assertEqual('removed', self.receipt()['outcomes'][removed])
        self.store.save_preparation.assert_not_called()
        self.remote.api.remove_image.side_effect = original_delete
        self.remote.api.remove_image.reset_mock()
        self.sync._cleanup_ready_nodes()
        self.assertEqual('completed', self.receipt()['state'])
        self.assertEqual('removed', self.receipt()['outcomes'][fail])
        self.assertNotIn(removed, [call.args[0] for call in self.remote.api.remove_image.call_args_list])

    def test_cleanup_waits_for_platform_and_the_original_node_lock(self) -> None:
        """平台维护及原节点占用期间继续保护镜像。"""
        self.gate['phase'] = 'blocked'
        self.sync._cleanup_ready_nodes()
        self.service.docker.assert_not_called()
        self.gate['phase'] = 'idle'
        lock = self.service.operation_locks[2] = threading.Lock()
        with lock:
            self.sync._cleanup_ready_nodes()
        self.service.docker.assert_not_called()

    def test_replaced_historical_tag_is_not_deleted(self) -> None:
        """旧标签已被重绑时保留两份制品，防止删除非原版本。"""
        old = self.reference('control', 2)
        replacement = self.names[self.reference('control', 1)]
        self.names[old] = replacement
        self.sync._cleanup_ready_nodes()
        self.assertEqual('identity_or_alias_changed', self.receipt()['outcomes'][old])
        self.assertIs(self.names[old], replacement)

    def test_missing_part_of_history_keeps_two_available_rollback_pairs(self) -> None:
        """最近历史共享的账号镜像已被清走时，保留更早的完整组合。"""
        self.delete_reference(self.reference('account', 4), force=False, noprune=True)
        self.sync._cleanup_ready_nodes()
        self.assertEqual('completed', self.receipt()['state'])
        self.remote.api.remove_image.assert_not_called()
        for number in (1, 2, 3, 4, 5, 6):
            self.assertIn(self.reference('control', number), self.names)

    def test_platform_change_during_reference_scan_retries_without_deleting(self) -> None:
        """平台在扫描期间关闭准入时，先退出本轮，待新门禁空闲再重试。"""
        def scan(**options):
            self.gate['phase'] = 'blocked'
            return self.containers

        self.remote.containers.list.side_effect = scan
        self.sync._cleanup_ready_nodes()
        self.remote.api.remove_image.assert_not_called()
        self.assertEqual('pending', self.receipt()['state'])
        self.assertEqual('prepared', self.preparation['state'])

    def test_unconfirmed_switch_does_not_start_cleanup(self) -> None:
        """切换、回退中的原节点日志尚无已完成回执，继续保留所有镜像。"""
        journal = self.directory / 'current.json'
        job = json.loads(journal.read_text())
        job['phase'] = 'restoring'
        atomic_json(journal, job)
        self.sync._cleanup_ready_nodes()
        self.service.docker.assert_not_called()
