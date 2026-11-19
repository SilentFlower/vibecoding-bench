"""真实节点文件验证已迁移工程抓包的只读归属和原预览边界。"""
from __future__ import annotations

import hashlib
import json
import shutil
import unittest
from unittest.mock import Mock

from cluster_project_capture import ProjectHistoryCapture, read_project_history_capture
from cluster_archive import ArchiveIdentity
from cluster_migration_files import ImportStage, MigrationFiles
from cluster_deployment import node_network_name
from runtime_files import atomic_json
import test_cluster_execution as node_fixture


class ProjectHistoryCaptureTests(unittest.TestCase):
    """历史读取复用真实节点投影和脱敏文件，禁止准备或启动运行环境。"""

    def setUp(self) -> None:
        """准备两个空间的不同抓包并固定当前 Node 归属。:return: None。"""
        fixture = node_fixture.NodeExecutionTests(methodName='runTest')
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        self.fixture = fixture
        fixture.executor.prepare(fixture.request)
        self.request = ProjectHistoryCapture(node_key=fixture.node_key, account_id=1,
            environment_id='e' * 32, assignment_revision=1, generation=1, namespace='projects', work_id='c' * 32)
        for namespace in ('projects', 'warmup'):
            group = hashlib.sha256(f'{namespace}/{self.request.work_id}'.encode()).hexdigest()[:20]
            base = fixture.root / 'environments' / self.request.environment_id / 'flows' / ('group-' + group)
            base.mkdir(parents=True)
            (base / 'capture-status.json').write_text(json.dumps({'state': 'complete', 'message': namespace,
                'recorder_graceful': True, 'private_field': '禁止公开'}))
        fixture.executor._runtime = Mock(side_effect=AssertionError('历史读取禁止准备运行时'))

    def test_current_location_reads_both_namespaces_without_runtime(self) -> None:
        """读取真实资料和受限预览，两个空间保持隔离。:return: None。"""
        for namespace in ('projects', 'warmup'):
            with self.subTest(namespace=namespace):
                request = self.request.model_copy(update={'namespace': namespace})
                result = read_project_history_capture(self.fixture.executor, request)
                self.assertTrue(result['capture']['available'])
                preview = read_project_history_capture(self.fixture.executor,
                    request.model_copy(update={'relative': 'capture-status.json'}))['capture']
                self.assertEqual(namespace, preview['message'])
                self.assertNotIn('private_field', preview)
        self.fixture.executor._runtime.assert_not_called()

    def test_wrong_scope_and_non_preview_paths_are_rejected(self) -> None:
        """旧代次、错账号和越界／私有文件不能被历史入口公开。:return: None。"""
        for change in ({'node_key': 'b' * 32}, {'account_id': 2}, {'generation': 2},
                {'assignment_revision': 2}, {'environment_id': 'f' * 32},
                {'relative': '../capture-status.json'}, {'relative': '.credentials.json'}):
            with self.subTest(change=change), self.assertRaises((ValueError, OSError)):
                read_project_history_capture(self.fixture.executor, self.request.model_copy(update=change))

    def test_linked_group_cannot_redirect_to_another_space(self) -> None:
        """抓包根链接拒绝跟随，保留原空间资料。:return: None。"""
        flows = self.fixture.root / 'environments' / self.request.environment_id / 'flows'
        source = flows / ('group-' + hashlib.sha256(f'projects/{self.request.work_id}'.encode()).hexdigest()[:20])
        target = source.with_name('retained')
        source.rename(target)
        source.symlink_to(target, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, '归属'):
            read_project_history_capture(self.fixture.executor, self.request)

    def test_real_archive_keeps_history_readable_on_another_node(self) -> None:
        """真实迁移包保存抓包，目标节点独立读取原空间资料。:return: None。"""
        target = node_fixture.NodeExecutionTests(methodName='runTest')
        target.setUp()
        self.addCleanup(target.doCleanups)
        target_key = 'b' * 32
        atomic_json(target.root / 'cluster-node.json', {'protocol': 1, 'node_key': target_key, 'deployment_id': 'synthetic'})
        target.executor.node_key = target_key
        identity = ArchiveIdentity(operation_id='1' * 32, deployment_id='synthetic', source_node_key=self.fixture.node_key,
            account_id=1, environment_id=self.request.environment_id, assignment_revision=1)
        source = MigrationFiles(self.fixture.root, self.fixture.node_key, 'synthetic')
        descriptor = source.export(self.fixture.root / 'environments' / identity.environment_id, identity, '2' * 32)
        files = MigrationFiles(target.root, target_key, 'synthetic')
        stage = ImportStage(node_key=target_key, transfer_id='3' * 32, target_revision=2, archive=descriptor)
        files.stage(stage)
        imported = target.root / 'node-migrations' / identity.operation_id / 'imports' / stage.transfer_id
        shutil.copyfile(self.fixture.root / 'node-migrations' / identity.operation_id / 'exports' / ('2' * 32 + '.tar'),
            imported / 'environment.tar')
        (imported / 'environment.tar').chmod(0o600)
        files.restore(stage)
        destination = target.root / 'environments' / identity.environment_id
        destination.parent.mkdir(exist_ok=True)
        (imported / 'environment').rename(destination)
        atomic_json(destination / 'runtime/node-assignment.json', {'protocol': 1, 'node_key': target_key,
            'account_id': 1, 'environment_id': identity.environment_id, 'revision': 2, 'phase': 'ready'})
        request = target.request.model_copy(update={'node_key': target_key, 'assignment_revision': 2,
            'environment': {**target.request.environment, 'generation': 1}})
        target.executor.client.containers.get.return_value.attrs['NetworkSettings']['Networks'][
            node_network_name('synthetic', target_key)] = {'IPAddress': '172.28.0.3'}
        actual = target.executor.prepare(request)['environment']
        target.executor._runtime = Mock(side_effect=AssertionError('历史读取不能访问原节点或准备环境'))
        for namespace in ('projects', 'warmup'):
            query = self.request.model_copy(update={'node_key': target_key, 'assignment_revision': 2,
                'generation': actual['generation'], 'namespace': namespace, 'relative': 'capture-status.json'})
            self.assertEqual(namespace, read_project_history_capture(target.executor, query)['capture']['message'])
