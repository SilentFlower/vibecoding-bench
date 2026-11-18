"""停机迁移的本机与SSH执行适配，业务根始终由所属节点读取。"""
from __future__ import annotations

import hashlib
import os
import uuid
from pathlib import Path
from stat import S_ISREG

from cluster_archive import ArchiveIdentity, _checksum
from cluster_deployment import node_container_name
from cluster_environment import EnvironmentFence, fence_environment, restore_fenced_source
from cluster_execution import ImportActivation, ImportPreparation, ImportRevocation, NodeExecution
from cluster_migration_files import ArchiveDescriptor, ArchiveExport, ImportStage, MigrationFiles
from cluster_transfer import NodeArchiveTransfer
from cluster_migration_profiles import MigrationProfiles, read_profile
from runtime_files import atomic_text


class MigrationIO:
    """协调固定操作和有界归档传输，保持中央数据库与节点投影分离。

    :param service: 中央节点服务。
    :param runtime: 中央原运行时。
    """

    def __init__(self, service, runtime) -> None:
        """冻结原执行依赖。:param service: 节点服务。:param runtime: 中央运行时。:return: None。"""
        self.service, self.runtime = service, runtime
        self.local_target = None

    def command(self, node_id: int, operation: str, payload: dict) -> dict:
        """执行固定节点动作，本机源使用原运行时，本机目标使用独立投影。

        :param node_id: 中央冻结节点。
        :param operation: 固定迁移动作。
        :param payload: 已绑定账号、环境和操作的私有输入。
        :return: 执行组件的原始私有收据。
        """
        types = {'fence': EnvironmentFence, 'restore-source': EnvironmentFence, 'export': ArchiveExport,
            'stage-import': ImportStage, 'verify-import': ImportStage, 'prepare-import': ImportPreparation,
            'activate-import': ImportActivation, 'revoke-import': ImportRevocation}
        if operation not in types:
            raise ValueError('迁移执行操作无效')
        request = types[operation].model_validate(payload)
        node = self.service.store.get(node_id)
        if node['kind'] == 'ssh':
            connection = self.service.connection(node_id)
            name = node_container_name(self.runtime.deployment, node['node_key'])
            if operation == 'fence':
                return connection.fence_environment(name, request.model_dump())
            return connection.migration_environment(name, request.model_dump(), operation)
        if node['kind'] != 'local':
            raise ValueError('迁移节点类型无效')
        if operation in ('fence', 'restore-source', 'export'):
            if request.node_key != 'local':
                raise ValueError('本机迁移源身份不一致')
            connection = self.service.store.database()
            try:
                stored = connection.execute('SELECT * FROM account_environments WHERE account_id=? AND environment_id=?',
                    (request.account_id, request.environment_id)).fetchone()
                if stored is None:
                    raise ValueError('本机迁移源环境不存在')
                row = dict(stored)
            finally:
                connection.close()
            if operation == 'restore-source':
                return restore_fenced_source(self.runtime, row, request)
            scope = EnvironmentFence.model_validate(request.model_dump(exclude={'attempt_id', 'version'}))
            receipt = fence_environment(self.runtime, row, scope)
            if operation == 'fence':
                return receipt
            identity = ArchiveIdentity(operation_id=request.operation_id, deployment_id=self.runtime.deployment,
                source_node_key='local', account_id=request.account_id, environment_id=request.environment_id,
                assignment_revision=request.assignment_revision)
            archive = MigrationFiles(self.runtime.data, 'local', self.runtime.deployment).export(
                self.runtime._root(row), identity, request.attempt_id, cli_version=request.version,
                cli_identity=self.runtime.read_cli_identity(row, request.version), environment_generation=row['generation'])
            return {'protocol': 1, 'node_key': 'local', 'archive': archive.model_dump()}
        if self.local_target is None:
            self.local_target = NodeExecution(self.runtime.data, self.runtime.host_data, 'local',
                self.runtime.deployment, self.service.local_client, local_runtime=self.runtime)
        actions = {'stage-import': self.local_target.stage_import, 'verify-import': self.local_target.verify_import,
            'prepare-import': self.local_target.prepare_import, 'activate-import': self.local_target.activate_import,
            'revoke-import': self.local_target.revoke_import}
        return actions[operation](request)

    def upload_profiles(self, node_id: int, stage: ImportStage, profiles: MigrationProfiles) -> None:
        """沿原暂存范围传输profile文件，复用摘要路径确保重试幂等。

        :param node_id: 固定目标。
        :param stage: 已建立的原暂存。
        :param profiles: 中央已过滤凭据的私有文件。
        :return: None。
        """
        node = self.service.store.get(node_id)
        for reference in profiles.references.values():
            source = profiles.path(reference)
            filename = source.name
            if node['kind'] == 'ssh':
                connection = self.service.connection(node_id)
                transfer = NodeArchiveTransfer(connection.docker_socket(), self.service.docker(node_id).api._version,
                    node_container_name(self.runtime.deployment, node['node_key']))
                transfer.upload_profile(stage.archive.identity.operation_id, stage.transfer_id,
                    source, reference.sha256, reference.bytes)
            else:
                target = self.runtime.data / 'node-migrations' / stage.archive.identity.operation_id / 'imports' / stage.transfer_id / filename
                atomic_text(target, read_profile(source, reference))

    def download(self, node_id: int, archive: ArchiveDescriptor) -> Path:
        """取得中央可访问的完整校验包，远程下载中断保留独立现场。

        :param node_id: 原源节点。
        :param archive: 原源冻结描述。
        :return: 私有普通包路径，整包保持在磁盘。
        """
        node = self.service.store.get(node_id)
        operation_id = archive.identity.operation_id
        if node['kind'] == 'local':
            bundle = self.runtime.data / 'node-migrations' / operation_id / 'exports' / (archive.attempt_id + '.tar')
        else:
            directory = self.service.data / 'cluster-migrations' / operation_id
            MigrationFiles(self.service.data, 'local', self.runtime.deployment)._private(directory)
            bundle = directory / 'environment.tar'
            if not bundle.exists() and not bundle.is_symlink():
                partial = directory / (uuid.uuid4().hex + '.download')
                connection = self.service.connection(node_id)
                transfer = NodeArchiveTransfer(connection.docker_socket(), self.service.docker(node_id).api._version,
                    node_container_name(self.runtime.deployment, node['node_key']))
                transfer.download(operation_id, archive.attempt_id, partial, archive.sha256, archive.bytes)
                os.rename(partial, bundle)
        if bundle.stat().st_size != archive.bytes or _checksum(bundle) != archive.sha256:
            raise ValueError('中央迁移包与原源描述不一致')
        return bundle

    def upload(self, node_id: int, stage: ImportStage, bundle: Path) -> None:
        """上传完整包至原独占暂存尝试，重复只接受已完全匹配的包。

        :param node_id: 固定目标节点。
        :param stage: 原上传身份。
        :param bundle: 中央完整私有包。
        :return: None。
        """
        accepted = self.command(node_id, 'stage-import', stage.model_dump())
        if accepted['uploaded']:
            return
        node = self.service.store.get(node_id)
        archive = stage.archive
        if node['kind'] == 'ssh':
            connection = self.service.connection(node_id)
            transfer = NodeArchiveTransfer(connection.docker_socket(), self.service.docker(node_id).api._version,
                node_container_name(self.runtime.deployment, node['node_key']))
            transfer.upload(archive.identity.operation_id, stage.transfer_id, bundle, archive.sha256, archive.bytes)
            return
        target = self.runtime.data / 'node-migrations' / archive.identity.operation_id / 'imports' / stage.transfer_id / 'environment.tar'
        # 本机目标也逐块读取并校验实际写入字节，失败后的部分文件由原操作保护。
        source_fd = os.open(bundle, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(source_fd, 'rb') as source:
            metadata = os.fstat(source.fileno())
            if (not S_ISREG(metadata.st_mode) or metadata.st_size != archive.bytes or metadata.st_mode & 0o077
                    or metadata.st_uid != os.geteuid() or metadata.st_nlink != 1):
                raise ValueError('本机迁移源包必须为完整私有普通文件')
            target_fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
            digest, count = hashlib.sha256(), 0
            with os.fdopen(target_fd, 'wb') as output:
                while chunk := source.read(1024 * 1024):
                    count += len(chunk)
                    if count > archive.bytes:
                        raise ValueError('本机迁移包超出原冻结大小')
                    digest.update(chunk)
                    output.write(chunk)
                output.flush()
                os.fsync(output.fileno())
            if count != archive.bytes or digest.hexdigest() != archive.sha256:
                raise ValueError('本机迁移包写入结果与原摘要不一致')
