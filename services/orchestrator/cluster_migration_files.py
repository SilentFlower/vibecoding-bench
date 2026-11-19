"""迁移操作私有目录中的导出包、目标暂存及导入核验。"""
from __future__ import annotations

import re
import shutil
from pathlib import Path
from stat import S_ISREG

from pydantic import BaseModel, ConfigDict, Field, StrictInt, StrictStr

from account_runtime import _read_json
from cli_scratchpad import SCRATCHPAD_RUNTIME, scratchpad_runtime_registered
from cluster_archive import ArchiveIdentity, _checksum, create_environment_archive, restore_environment_archive
from cluster_environment import EnvironmentFence
from cluster_owner_state import pending_owner_transition
from runtime_files import atomic_json, private_directory


# 逻辑身份、HOME、工程与历史证据保留；这些记录只描述源宿主的运行实例，须由目标重建。
ENVIRONMENT_EXCLUSIONS = {
    'runtime/owner-transition.json': '原Node凭据交接回执保留在源环境，目标沿新归属建立自己的操作',
    'runtime/node-fence.json': '源隔离回执保留在源操作；目标组件建立本次激活记录',
    'runtime/node-assignment.json': '目标组件按中央提交的新分配版本建立本地归属',
    'runtime/node-migration-target.json': '前次目标发布回执保留在原操作目录，本次建立独立发布身份',
    'runtime/network': '目标按原代理和逻辑画像重新创建网络控制配置',
    'runtime/sender': '目标重新生成传输秘密及发送器物理地址',
    'runtime/sender.json': '旧布局发送器配置按目标三角色布局重新建立',
    'runtime/access': '目标按当前唯一凭据所有者发布执行快照',
    'runtime/cli': '目标按已冻结CLI策略重新建立控制配置',
    'runtime/native-criu': '目标重新建立暖进程，不恢复源宿主内存快照',
    'runtime/native': '目标按原请求内核重新建立运行进程与临时工作区，API历史仍保留在flows',
    'runtime/account-image.json': '目标按实际同批镜像建立新的物理来源证明',
    'runtime/physical-features.json': '目标按实际宿主重新采集观察，逻辑画像保持',
}


class ArchiveExport(EnvironmentFence):
    """仅对已隔离源执行的导出请求。:param attempt_id: 独立导出尝试。:param version: 冻结CLI版本。"""

    attempt_id: StrictStr = Field(pattern=r'^[a-f0-9]{32}$')
    version: StrictStr = Field(pattern=r'^2\.1\.[0-9]{1,6}$')


class MigrationCliIdentity(BaseModel):
    """源运行时按已验证版本合同读取的无凭据CLI身份。

    :param device_id: 原CLI设备身份。
    :param account_uuid: 原登录账号身份。
    :param source: 运行时核对的字段或请求观察来源。
    """

    model_config = ConfigDict(extra='forbid')
    device_id: StrictStr = Field(pattern=r'^[a-f0-9]{64}$')
    account_uuid: StrictStr = Field(min_length=1, max_length=256)
    source: StrictStr = Field(min_length=1, max_length=512)


class ArchiveDescriptor(BaseModel):
    """中央冻结并在两节点间核对的私有包元数据。

    :param identity: 源隔离身份。
    :param attempt_id: 源导出尝试。
    :param sha256: 精确包摘要。
    :param bytes: 包字节数。
    :param files: 清单条目数。
    :param data_bytes: 解包普通文件总字节。
    :param cli_version: 源身份核对使用的冻结版本。
    :param cli_identity: 源运行时提供的已核对CLI身份；原始文件工具可省略，业务发布要求具备。
    :param environment_generation: 源组件已停止并核对的实际环境代次。
    """

    model_config = ConfigDict(extra='forbid')
    identity: ArchiveIdentity
    attempt_id: StrictStr = Field(pattern=r'^[a-f0-9]{32}$')
    sha256: StrictStr = Field(pattern=r'^[a-f0-9]{64}$')
    bytes: StrictInt = Field(ge=0)
    files: StrictInt = Field(ge=1)
    data_bytes: StrictInt = Field(ge=0)
    cli_version: StrictStr | None = Field(default=None, pattern=r'^2\.1\.[0-9]{1,6}$')
    cli_identity: MigrationCliIdentity | None = None
    environment_generation: StrictInt | None = Field(default=None, ge=0)


class ImportStage(BaseModel):
    """目标组件创建私有上传暂存区的严格输入。

    :param node_key: 目标节点。
    :param transfer_id: 本次上传暂存尝试。
    :param target_revision: 中央切换后的新分配版本。
    :param archive: 已冻结源包。
    """

    model_config = ConfigDict(extra='forbid')
    node_key: StrictStr = Field(pattern=r'^(local|[a-f0-9]{32})$')
    transfer_id: StrictStr = Field(pattern=r'^[a-f0-9]{32}$')
    target_revision: StrictInt = Field(ge=2)
    archive: ArchiveDescriptor


class MigrationFiles:
    """将文件操作限制在当前节点和原迁移操作的私有目录。

    :param data: 当前节点数据根。
    :param node_key: 当前稳定节点身份。
    :param deployment: 安装时冻结的部署。
    """

    def __init__(self, data: Path, node_key: str, deployment: str) -> None:
        """固定私有文件操作归属。:param data: 数据根。:param node_key: 节点。:param deployment: 部署。:return: None。"""
        if not re.fullmatch('(local|[a-f0-9]{32})', node_key) or not re.fullmatch('[a-z0-9][a-z0-9-]{0,35}', deployment):
            raise ValueError('迁移文件归属无效')
        self.data, self.node_key, self.deployment = data, node_key, deployment

    def _private(self, path: Path) -> None:
        private_directory(path)

    def _operation(self, identity: ArchiveIdentity, direction: str) -> Path:
        if identity.deployment_id != self.deployment:
            raise ValueError('迁移包部署归属不一致')
        if direction == 'export' and identity.source_node_key != self.node_key:
            raise ValueError('迁移导出源节点不一致')
        path = self.data / 'node-migrations' / identity.operation_id
        self._private(path)
        marker = path / 'operation.json'
        expected = {'protocol': 1, 'node_key': self.node_key, 'direction': direction, 'identity': identity.model_dump()}
        if marker.exists() or marker.is_symlink():
            if _read_json(marker) != expected:
                raise ValueError('迁移私有目录属于其他操作或方向')
        elif any(path.iterdir()):
            raise ValueError('迁移私有目录包含未核对资料')
        else:
            atomic_json(marker, expected)
        return path

    def export(self, root: Path, identity: ArchiveIdentity, attempt_id: str, *,
               cli_version: str | None = None, cli_identity: dict | None = None,
               environment_generation: int | None = None) -> ArchiveDescriptor:
        """在已隔离源保存独立导出包及持久回执。

        :param root: 已停止的原环境根。
        :param identity: 源隔离冻结身份。
        :param attempt_id: 新导出尝试，原回执可幂等读取。
        :param cli_version: 源运行时使用的冻结版本。
        :param cli_identity: 源运行时已核对的设备与账号，调用方在同一环境锁内读取。
        :param environment_generation: 已停止的源环境实际代次。
        :return: 绑定该操作的完整包描述。
        """
        if not re.fullmatch('[a-f0-9]{32}', attempt_id):
            raise ValueError('导出尝试身份无效')
        if pending_owner_transition(root):
            raise ValueError('原凭据交接尚未完成，导出等待原操作收口')
        operation = self._operation(identity, 'export')
        exports = operation / 'exports'
        receipts = operation / 'receipts'
        self._private(exports)
        self._private(receipts)
        target = exports / (attempt_id + '.tar')
        receipt = receipts / (attempt_id + '.json')
        if receipt.exists() or receipt.is_symlink():
            result = ArchiveDescriptor.model_validate(_read_json(receipt))
            if (result.identity != identity or result.attempt_id != attempt_id
                    or result.cli_version != cli_version
                    or result.environment_generation != environment_generation
                    or (result.cli_identity.model_dump() if result.cli_identity else None) != cli_identity
                    or target.stat().st_size != result.bytes or _checksum(target) != result.sha256):
                raise ValueError('原导出回执或文件已变化')
            return result
        excluded = dict(ENVIRONMENT_EXCLUSIONS)
        # 仅双份协议已核验的宿主挂载工作目录可重建，未知同名资料继续随包保全。
        if scratchpad_runtime_registered(root, identity.environment_id):
            excluded[SCRATCHPAD_RUNTIME] = '目标按原持久临时文件布局重建私有挂载目录，源宿主工作目录保留'
        for pid in (root / 'runtime/jobs').glob('*/group.pid'):
            excluded[str(pid.relative_to(root))] = '旧进程PID只属于源宿主，恢复采用独立新handle及实际进程证明'
        result = create_environment_archive(root, target, identity, excluded)
        result['attempt_id'] = attempt_id
        result['cli_version'], result['cli_identity'] = cli_version, cli_identity
        result['environment_generation'] = environment_generation
        descriptor = ArchiveDescriptor.model_validate(result)
        atomic_json(receipt, descriptor.model_dump())
        return descriptor

    def stage(self, request: ImportStage) -> dict:
        """建立目标独占上传目录，拒绝覆盖未知或部分上传文件。

        :param request: 目标身份与源包范围。
        :return: 受控暂存身份及是否已有完全匹配的上传文件。
        """
        if request.node_key != self.node_key or request.target_revision != request.archive.identity.assignment_revision + 1:
            raise ValueError('目标暂存节点或分配版本不一致')
        operation = self._operation(request.archive.identity, 'import')
        if (operation / 'revoked.json').exists() or (operation / 'revoked.json').is_symlink():
            raise ValueError('目标迁移操作已撤销，拒绝迟到上传或发布')
        path = operation / 'imports' / request.transfer_id
        self._private(path)
        marker = path / 'stage.json'
        if marker.exists() or marker.is_symlink():
            if _read_json(marker) != request.model_dump():
                raise ValueError('目标暂存尝试属于其他包或分配版本')
        elif any(path.iterdir()):
            raise ValueError('目标暂存目录包含未核对资料')
        else:
            required = request.archive.bytes + request.archive.data_bytes
            if required > shutil.disk_usage(path).free:
                raise ValueError('目标节点迁移暂存空间不足')
            atomic_json(marker, request.model_dump())
        bundle = path / 'environment.tar'
        uploaded = bundle.exists() or bundle.is_symlink()
        if uploaded and (not S_ISREG(bundle.lstat().st_mode) or bundle.lstat().st_nlink != 1):
            raise ValueError('迁移上传文件必须为原普通文件')
        frozen = any((path / name).exists() or (path / name).is_symlink()
            for name in ('verified.json', 'publish-intent.json', 'published.json'))
        if not uploaded and frozen:
            raise ValueError('已核验或发布的迁移包缺失，请核对原操作')
        if uploaded and (bundle.stat().st_size != request.archive.bytes or _checksum(bundle) != request.archive.sha256):
            if frozen:
                raise ValueError('已核验或发布的迁移包发生变化，请核对原操作')
            return {'protocol': 1, 'node_key': self.node_key, 'operation_id': request.archive.identity.operation_id,
                'transfer_id': request.transfer_id, 'uploaded': False, 'upload_state': 'incomplete',
                'revision': request.target_revision}
        return {'protocol': 1, 'node_key': self.node_key, 'operation_id': request.archive.identity.operation_id,
            'transfer_id': request.transfer_id, 'uploaded': uploaded, 'upload_state': 'complete' if uploaded else 'empty',
            'revision': request.target_revision}

    def restore(self, request: ImportStage) -> dict:
        """将完整上传包导入操作私有树，并保存逐文件核验结果。

        :param request: 原已登记目标暂存输入。
        :return: 目标暂存资料已核对的回执，业务发布由后续激活协议处理。
        """
        staged = self.stage(request)
        if not staged['uploaded']:
            raise ValueError('迁移包尚未上传完成')
        path = self.data / 'node-migrations' / request.archive.identity.operation_id / 'imports' / request.transfer_id
        if any(item.exists() or item.is_symlink() for item in (path / 'publish-intent.json', path / 'published.json')):
            intent = _read_json(path / 'publish-intent.json')
            identity = request.archive.identity
            expected = {'protocol': 1, 'operation_id': identity.operation_id, 'transfer_id': request.transfer_id,
                'node_key': self.node_key, 'account_id': identity.account_id, 'environment_id': identity.environment_id,
                'revision': request.target_revision, 'archive_sha256': request.archive.sha256,
                'source_generation': request.archive.environment_generation, 'cli_version': request.archive.cli_version,
                'cli_identity': request.archive.cli_identity.model_dump() if request.archive.cli_identity else None}
            if not isinstance(intent, dict) or any(intent.get(key) != value for key, value in expected.items()):
                raise ValueError('目标已开始发布，请按原发布阶段核对')
            receipt = _read_json(path / 'verified.json')
            if (not isinstance(receipt, dict) or any(receipt.get(key) != value for key, value in {
                    'protocol': 1, 'operation_id': identity.operation_id, 'transfer_id': request.transfer_id,
                    'node_key': self.node_key, 'revision': request.target_revision,
                    'phase': 'verified', 'sha256': request.archive.sha256}.items())):
                raise ValueError('原发布操作缺少完整私有核验回执')
            # 已发布副本只读取同范围收据；后续prepare按实际身份和角色继续，避免重建业务树。
            return receipt
        root = path / 'environment'
        if root.is_symlink():
            raise ValueError('目标私有暂存树类型异常')
        if root.exists():
            # 原操作的未发布副本可以从同一完整包重建；源环境与上传包均继续保留。
            shutil.rmtree(root)
        result = restore_environment_archive(path / 'environment.tar', root, request.archive.identity,
            request.archive.sha256, request.archive.data_bytes)
        receipt = {**staged, 'phase': 'verified', 'sha256': request.archive.sha256,
            'files': result['files'], 'data_bytes': result['data_bytes']}
        atomic_json(path / 'verified.json', receipt)
        return receipt
