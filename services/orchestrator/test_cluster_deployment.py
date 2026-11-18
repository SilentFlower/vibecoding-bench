"""节点镜像流式交付与同名制品冲突的离线合同验证。"""
from __future__ import annotations

import hashlib
import io
import json
import os
import tarfile
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from docker.errors import NotFound

from cluster_deployment import NodeDeployment, image_config_digest
from cluster_nodes import NodeConfiguration
import test_cluster_nodes as node_fixture


class ClusterDeploymentTests(unittest.TestCase):
    """核对原始镜像配置身份，避免信任可变标签和导入进度。"""

    def archive(self, reference: str, *, ambiguous: bool = False):
        """构建含大层和小配置的分块tar来源。:param reference: 标签。:param ambiguous: 是否包含两个候选。:return: SDK替身及预期摘要。"""
        configuration = json.dumps({'architecture': 'amd64', 'rootfs': {'type': 'layers',
            'diff_ids': ['sha256:' + 'a' * 64]}, 'config': {'Env': ['ROLE=synthetic']}}).encode()
        digest = hashlib.sha256(configuration).hexdigest()
        buffer = io.BytesIO()
        with tarfile.open(fileobj=buffer, mode='w') as archive:
            manifests = [{'Config': 'blobs/sha256/' + digest, 'RepoTags': [reference], 'Layers': ['layer.tar']}]
            if ambiguous:
                manifests.append(manifests[0])
            for name, data in [('layer.tar', b'x' * (5 * 1024 * 1024)),
                    ('blobs/sha256/' + digest, configuration), ('manifest.json', json.dumps(manifests).encode())]:
                member = tarfile.TarInfo(name)
                member.size = len(data)
                archive.addfile(member, io.BytesIO(data))
        raw = buffer.getvalue()
        closed = []

        def chunks():
            try:
                for offset in range(0, len(raw), 1703):
                    yield raw[offset:offset + 1703]
            finally:
                closed.append(True)

        client = Mock()
        client.api.get_image.side_effect = lambda value: chunks()
        return client, 'sha256:' + digest, closed

    def test_streaming_archive_uses_original_config_and_closes_response(self) -> None:
        """跨任意块边界读取原始配置，跳过大型镜像层并释放来源。:return: None。"""
        client, digest, closed = self.archive('synthetic:current')
        self.assertEqual(digest, image_config_digest(client, 'synthetic:current'))
        self.assertEqual([True], closed)

    def test_ambiguous_image_archive_is_rejected(self) -> None:
        """相同标签命中多个归档配置时保守拒绝。:return: None。"""
        client, _, closed = self.archive('synthetic:current', ambiguous=True)
        with self.assertRaisesRegex(ValueError, '唯一'):
            image_config_digest(client, 'synthetic:current')
        self.assertEqual([True], closed)

    def test_same_tag_with_different_image_content_is_not_overwritten(self) -> None:
        """同名不同原始配置拒绝安装，既有镜像保持原内容。:return: None。"""
        local, _, _ = self.archive('synthetic:current')
        local.images.get.return_value = SimpleNamespace(attrs={'Id': 'local-image', 'Config': {'Labels': {
            'vibebench.product': 'v3', 'vibebench.role': 'control', 'vibebench.release': 'synthetic'}}})
        remote, _, _ = self.archive('synthetic:current')
        remote.images.get.return_value = SimpleNamespace(attrs={'Id': 'remote-image'})
        installer = NodeDeployment(SimpleNamespace(local_client=local), 'synthetic', 'synthetic', 'synthetic:current', 'synthetic:account')
        self.assertIs(remote.images.get.return_value, installer._ensure_image(remote, 'synthetic:current', 'control', 'synthetic'))
        foreign, _, _ = self.archive('foreign:tag')
        remote.api.get_image.side_effect = foreign.api.get_image.side_effect
        with self.assertRaisesRegex(ValueError, '唯一|不同内容'):
            installer._ensure_image(remote, 'synthetic:current', 'control', 'synthetic')
        remote.api.load_image.assert_not_called()

    def test_docker_import_error_is_not_a_success_receipt(self) -> None:
        """Docker以成功HTTP返回错误进度时拒绝安装，并关闭镜像来源。:return: None。"""
        source = Mock()
        local = Mock()
        local.images.get.return_value = SimpleNamespace(attrs={'Id': 'local', 'Config': {'Labels': {
            'vibebench.product': 'v3', 'vibebench.role': 'control', 'vibebench.release': 'synthetic'}}})
        local.api.get_image.return_value = source
        remote = Mock()
        remote.images.get.side_effect = NotFound('synthetic')
        remote.api.load_image.return_value = iter([{'error': 'synthetic import failure'}])
        installer = NodeDeployment(SimpleNamespace(local_client=local), 'synthetic', 'synthetic', 'control', 'account')
        with self.assertRaisesRegex(ValueError, '导入失败'):
            installer._ensure_image(remote, 'control', 'control', 'synthetic')
        remote.api.load_image.assert_called_once_with(source, quiet=True)
        source.close.assert_called_once()

    def test_installation_uses_separate_bounded_clients_and_closes_both_after_unknown_create(self) -> None:
        """安装创建未知时关闭独立客户端，日常控制客户端继续保持原期限。:return: None。"""
        fixture = node_fixture.ClusterNodeTests(methodName='runTest'); fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        service = Mock()
        service.store.get.return_value = {'id': 3, 'kind': 'ssh', 'revision': 2, 'enabled': True,
            'node_key': 'a' * 32, 'config_json': json.dumps(fixture.config)}
        service.connection.return_value.docker_socket.return_value = fixture.root / 'docker.sock'
        transfer, install = Mock(), Mock()
        deployment = NodeDeployment(service, 'synthetic', 'synthetic', 'control', 'account')
        with patch('cluster_deployment.DockerClient', side_effect=[transfer, install]) as constructor:
            with patch.object(deployment, '_ensure_image'), patch.object(deployment, '_prepare_control', side_effect=TimeoutError('合成创建结果未知')):
                with self.assertRaises(TimeoutError):
                    deployment.prepare(3, 2)
        self.assertEqual([600, 120], [call.kwargs['timeout'] for call in constructor.call_args_list])
        transfer.close.assert_called_once(); install.close.assert_called_once()
        service.docker.assert_not_called()

    def test_installation_rejects_link_fifo_or_nonprivate_service_token_before_container_creation(self) -> None:
        """服务认证只接受私有普通文件，恢复后的错误对象在Docker创建前拒绝。:return: None。"""
        fixture = node_fixture.ClusterNodeTests(methodName='runTest'); fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        private = fixture.root / 'node-private'; private.mkdir(mode=0o700)
        token = private / 'execution-token'
        row = {'id': 3, 'revision': 2, 'node_key': 'a' * 32}
        labels = {'vibebench.product': 'v3', 'vibebench.deployment': 'synthetic', 'vibebench.cluster-node': row['node_key']}
        remote = Mock()
        remote.networks.get.return_value = SimpleNamespace(name='original-network', attrs={'Labels': labels})
        remote.containers.get.side_effect = NotFound('合成固定控制容器尚未创建')
        deployment = NodeDeployment(Mock(), 'synthetic', 'synthetic', 'control', 'account')
        for kind in ('link', 'fifo', 'public'):
            if kind == 'link': token.symlink_to(fixture.key)
            elif kind == 'fifo': os.mkfifo(token)
            else: token.write_text('a' * 64); token.chmod(0o644)
            try:
                with self.subTest(kind=kind), self.assertRaises((ValueError, OSError)):
                    deployment._prepare_control(remote, SimpleNamespace(private=private), row,
                        NodeConfiguration.model_validate(fixture.config), 'synthetic', Mock())
                remote.containers.run.assert_not_called()
            finally:
                token.unlink()

    def test_new_batch_replaces_only_stopped_owned_node_control(self) -> None:
        """同批准备可替换已停止旧控制实例，保留认证、HOME与原账号角色。:return: None。"""
        fixture = node_fixture.ClusterNodeTests(methodName='runTest'); fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        private=fixture.root/'node-private'; private.mkdir(mode=0o700)
        token=private/'execution-token'; token.write_text('b'*64); token.chmod(0o600)
        labels={'vibebench.product':'v3','vibebench.deployment':'synthetic','vibebench.cluster-node':'a'*32}
        old=Mock(labels={**labels,'vibebench.role':'node-control','vibebench.release':'previous'},status='exited')
        old.attrs={'Mounts':[{'Destination':'/data','Source':fixture.config['data_root'],'RW':True}]}
        remote=Mock()
        remote.networks.get.return_value=SimpleNamespace(name='original-network',attrs={'Labels':labels})
        remote.containers.get.return_value=old
        remote.containers.list.return_value=[]
        remote.containers.run.side_effect=TimeoutError('synthetic create response unknown')
        deployment=NodeDeployment(Mock(),'synthetic','candidate','control','account')
        with self.assertRaises(TimeoutError):
            deployment._prepare_control(remote,SimpleNamespace(private=private),{'id':3,'revision':2,'node_key':'a'*32},
                NodeConfiguration.model_validate(fixture.config),'candidate',Mock())
        old.remove.assert_called_once_with()
        self.assertEqual('b'*64,token.read_text())
        self.assertEqual('candidate',remote.containers.run.call_args.kwargs['environment']['V3_RELEASE'])
        self.assertEqual(2,remote.containers.list.call_count)

    def test_new_batch_keeps_old_control_when_any_node_role_is_running(self) -> None:
        """节点仍有实际角色运行时，原控制实例和数据归属保持。:return: None。"""
        fixture = node_fixture.ClusterNodeTests(methodName='runTest'); fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        labels={'vibebench.product':'v3','vibebench.deployment':'synthetic','vibebench.cluster-node':'a'*32}
        old=Mock(labels={**labels,'vibebench.role':'node-control','vibebench.release':'previous'},status='exited')
        old.attrs={'Mounts':[{'Destination':'/data','Source':fixture.config['data_root'],'RW':True}]}
        remote=Mock()
        remote.networks.get.return_value=SimpleNamespace(name='original-network',attrs={'Labels':labels})
        remote.containers.get.return_value=old
        remote.containers.list.return_value=[Mock()]
        deployment=NodeDeployment(Mock(),'synthetic','candidate','control','account')
        with self.assertRaisesRegex(ValueError,'先排空并停止'):
            deployment._prepare_control(remote,Mock(),{'id':3,'revision':2,'node_key':'a'*32},
                NodeConfiguration.model_validate(fixture.config),'candidate',Mock())
        old.remove.assert_not_called()
        remote.containers.run.assert_not_called()
