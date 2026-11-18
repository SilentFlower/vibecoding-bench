"""节点工作区的受限快照包，沿原源码清单与内容对象合同传输。"""
from __future__ import annotations

import hashlib
import os
import re
import shutil
import tarfile
import tempfile
import uuid
from contextlib import contextmanager
from io import BytesIO
from pathlib import Path
from stat import S_ISREG
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictInt, StrictStr, model_validator

from cluster_execution_grants import ExecutionScope
from project_library import MAX_JSON_BYTES, MAX_TREE_BYTES, MAX_TREE_FILES, canonical_json, digest_json, safe_relative, snapshot_tree
from runtime_files import atomic_json, directory_fd, private_directory
from system_update_contract import safe_read, strict_json


_ENVELOPE_LIMIT = MAX_JSON_BYTES + 16384
_BUNDLE_LIMIT = 160 * 1024 * 1024


class WorkspaceObject(BaseModel):
    """原源码文件的内容身份。:param digest: 原SHA256。:param size: 原字节数。"""

    model_config = ConfigDict(extra='forbid')
    digest: StrictStr = Field(pattern=r'^[a-f0-9]{64}$')
    size: StrictInt = Field(ge=0, le=MAX_TREE_BYTES)


class WorkspaceTree(BaseModel):
    """原snapshot_tree清单的有界验证模型。

    :param schema_version: 原清单schema，JSON字段保持schema。
    :param files: 原相对路径与内容对象。
    :param bytes: 原文件累计大小。
    :param digest: 原文件清单摘要。
    """

    model_config = ConfigDict(extra='forbid')
    schema_version: Literal[1] = Field(default=1, alias='schema')
    files: dict[StrictStr, WorkspaceObject] = Field(max_length=MAX_TREE_FILES)
    bytes: StrictInt = Field(ge=0, le=MAX_TREE_BYTES)
    digest: StrictStr = Field(pattern=r'^[a-f0-9]{64}$')

    @model_validator(mode='after')
    def validate_tree(self):
        """累计大小、路径及摘要必须同时对应原清单。:return: 原快照。"""
        files = {}
        sizes = {}
        for path, item in self.files.items():
            if safe_relative(path) != path or len(path.encode()) > 4096:
                raise ValueError('节点源码快照包含非法相对路径')
            if item.digest in sizes and sizes[item.digest] != item.size:
                raise ValueError('节点源码对象的同一摘要对应不同大小')
            sizes[item.digest] = item.size
            files[path] = item.model_dump()
        if sum(item.size for item in self.files.values()) != self.bytes or digest_json(files) != self.digest:
            raise ValueError('节点源码清单的累计大小或摘要不一致')
        return self


class WorkspaceSnapshotReference(BaseModel):
    """原执行的独立只读快照定位。:param scope: 原执行。:param snapshot_id: 原快照尝试。"""

    model_config = ConfigDict(extra='forbid')
    scope: ExecutionScope
    snapshot_id: StrictStr = Field(pattern=r'^[a-f0-9]{32}$')


class WorkspaceSnapshotRequest(WorkspaceSnapshotReference):
    """捕获原基线或冻结候选。:param purpose: 基线或候选，候选附带内容对象。"""

    purpose: Literal['baseline', 'candidate']


class WorkspaceSnapshotArchive(WorkspaceSnapshotRequest):
    """私有快照包回执，不接受任意节点文件路径。

    :param protocol: 原私有协议。
    :param sha256: 整包原字节摘要。
    :param bytes: 整包字节数。
    :param tree_digest: 原源码树摘要。
    :param tree_bytes: 原源码树总字节数。
    :param file_count: 原源码文件数。
    """

    protocol: Literal[1] = 1
    sha256: StrictStr = Field(pattern=r'^[a-f0-9]{64}$')
    bytes: StrictInt = Field(ge=10240, le=_BUNDLE_LIMIT)
    tree_digest: StrictStr = Field(pattern=r'^[a-f0-9]{64}$')
    tree_bytes: StrictInt = Field(ge=0, le=MAX_TREE_BYTES)
    file_count: StrictInt = Field(ge=0, le=MAX_TREE_FILES)


class _SnapshotEnvelope(WorkspaceSnapshotRequest):
    """包内原执行范围及完整源码清单。"""

    protocol: Literal[1] = 1
    snapshot: WorkspaceTree


@contextmanager
def _private_file(path: Path, size: int | None = None):
    parent = directory_fd(path.parent)
    try:
        descriptor = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
    finally:
        os.close(parent)
    with os.fdopen(descriptor, 'rb') as source:
        metadata = os.fstat(source.fileno())
        if (not S_ISREG(metadata.st_mode) or metadata.st_uid != os.geteuid() or metadata.st_mode & 0o077
                or metadata.st_nlink != 1 or size is not None and metadata.st_size != size):
            raise ValueError('节点快照私有文件的类型、权限或大小无效')
        yield source


class NodeWorkspaceSnapshots:
    """从原节点终端取得实际源码，并保存不可重复换源的快照包。

    :param terminals: 原NodeTerminals。
    :param source: 可选具体Run候选目录核对器。
    """

    def __init__(self, terminals, *, source=None) -> None:
        """复用原执行器、环境锁及节点启动收据。:param terminals: 原节点终端。:return: None。"""
        self.terminals, self.executor = terminals, terminals.executor
        self.source = source

    def _parent(self, scope: ExecutionScope, *, create: bool = False) -> Path:
        parent = self.terminals._directory(scope) / 'snapshots'
        if create:
            private_directory(parent)
        return parent

    def get(self, request: WorkspaceSnapshotReference) -> dict:
        """读取原包回执并核对私有文件，历史读取保持原scope。

        :param request: 原执行及快照。
        :return: 原已发布包身份。
        """
        self.terminals._record(request.scope)
        parent = self._parent(request.scope)
        receipt = WorkspaceSnapshotArchive.model_validate(strict_json(safe_read(
            parent / (request.snapshot_id + '.json'), 16384, private=True), 16384))
        if receipt.scope != request.scope or receipt.snapshot_id != request.snapshot_id:
            raise ValueError('节点快照回执属于另一原操作')
        with _private_file(parent / (request.snapshot_id + '.tar'), receipt.bytes) as source:
            if hashlib.file_digest(source, 'sha256').hexdigest() != receipt.sha256:
                raise ValueError('节点原快照包内容已变化')
        return receipt.model_dump()

    def create(self, request: WorkspaceSnapshotRequest) -> dict:
        """基线在首次输入前捕获，候选在原进程树冻结后捕获。

        :param request: 原执行、独立快照及用途。
        :return: 固定原内容的私有包回执。
        """
        scope = request.scope
        with self.executor._locked(environment_id=scope.environment_id):
            parent = self._parent(scope, create=True)
            receipt_path = parent / (request.snapshot_id + '.json')
            if receipt_path.exists() or receipt_path.is_symlink():
                previous = self.get(request)
                if previous['purpose'] != request.purpose:
                    raise ValueError('原节点快照用途已变化')
                return previous
            if self.source is not None:
                workspace = self.source(request)
            else:
                record, terminal = self.terminals._ready(scope)
                work = self.terminals._work(record)
                runtime = self.terminals.host.runtime
                info = record['result']
                job = runtime.job_for_container(info['token'])
                if (job['source'] != scope.source or job['account']['id'] != scope.account_id
                        or job['row']['environment_id'] != scope.environment_id or job['row']['generation'] != scope.generation):
                    raise ValueError('源码快照与原节点实际作业不一致')
                if request.purpose == 'baseline':
                    inputs = [path for path in self.terminals._directory(scope).glob('*.json') if path.name != 'execution.json']
                    if record.get('pending_input') is not None or work.get('resume_required') or work.get('baseline_registered') or inputs:
                        raise ValueError('原基线只能在首次输入之前捕获')
                else:
                    proof = runtime.control_execution(info['token'], 'freeze')
                    if proof.get('source') != scope.source or proof.get('frozen') is not True:
                        raise ValueError('原源码写入进程树尚未确认冻结')
            private = parent / request.snapshot_id
            private.mkdir(mode=0o700, exist_ok=False)
            atomic_json(private / 'intent.json', request.model_dump())
            if self.source is None:
                workspace = terminal.workspace(work)
            expected = self.executor.data / 'environments' / scope.environment_id / 'projects'
            if not workspace.absolute().is_relative_to(expected.absolute()):
                raise ValueError('节点源码目录超出原账号环境')
            descriptor = directory_fd(workspace)
            os.close(descriptor)
            manifest = WorkspaceTree.model_validate(snapshot_tree(workspace))
            envelope = _SnapshotEnvelope(**request.model_dump(), snapshot=manifest)
            raw = canonical_json(envelope.model_dump(by_alias=True))
            if len(raw) > _ENVELOPE_LIMIT:
                raise ValueError('节点源码快照清单超过原有大小上限')
            unique = {item.digest: item.size for item in manifest.files.values()}
            needed = 2 * len(raw) + 32768 + len(unique) * 1024
            if request.purpose == 'candidate':
                needed += 2 * sum(unique.values())
            if shutil.disk_usage(parent).free < needed:
                raise ValueError('节点空闲磁盘不足以保存本次源码快照')
            objects = private / 'objects'
            if request.purpose == 'candidate':
                private_directory(objects)
                if WorkspaceTree.model_validate(snapshot_tree(workspace, objects)) != manifest:
                    raise ValueError('源码封存期间实际文件发生变化')
            atomic_json(private / 'manifest.json', envelope.model_dump(by_alias=True))
            receipt = write_workspace_bundle(parent/(request.snapshot_id+'.tar'),request,manifest.model_dump(by_alias=True),
                objects if request.purpose=='candidate' else None)
            atomic_json(receipt_path, receipt.model_dump())
            return receipt.model_dump()


def write_workspace_bundle(path: Path, request: WorkspaceSnapshotRequest, snapshot: dict,
                           objects: Path | None = None) -> WorkspaceSnapshotArchive:
    """把原完整检查点打包到全新私有文件，供中央和节点双向传输。

    :param path: 本次执行方私有目录中的全新包路径。
    :param request: 冻结执行范围及具体快照身份。
    :param snapshot: 原snapshot_tree完整清单。
    :param objects: 候选包的只读内容对象目录；基线包为None。
    :return: 绑定原范围、完整树和整包摘要的回执。
    """
    if (request.purpose=='candidate')!=(objects is not None):
        raise ValueError('原源码包用途与内容对象目录不一致')
    private_directory(path.parent)
    manifest=WorkspaceTree.model_validate(snapshot)
    envelope=_SnapshotEnvelope(**request.model_dump(),snapshot=manifest)
    raw=canonical_json(envelope.model_dump(by_alias=True))
    if len(raw)>_ENVELOPE_LIMIT:
        raise ValueError('节点源码快照清单超过原有大小上限')
    unique={item.digest:item.size for item in manifest.files.values()}
    temporary = path.parent / ('.' + path.name + '.tmp')
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        with os.fdopen(descriptor, 'wb') as output:
            with tarfile.open(fileobj=output, mode='w', format=tarfile.USTAR_FORMAT) as archive:
                item = tarfile.TarInfo('snapshot.json')
                item.size, item.mode = len(raw), 0o600
                archive.addfile(item, BytesIO(raw))
                if request.purpose == 'candidate':
                    for digest, size in sorted(unique.items()):
                        object_path = objects / digest[:2] / digest
                        with _private_file(object_path, size) as source:
                            if hashlib.file_digest(source, 'sha256').hexdigest() != digest:
                                raise ValueError('节点源码对象在打包前发生变化')
                            source.seek(0)
                            member = tarfile.TarInfo('objects/' + digest[:2] + '/' + digest)
                            member.size, member.mode = size, 0o600
                            archive.addfile(member, source)
            output.flush()
            os.fsync(output.fileno())
        size = temporary.stat().st_size
        if size > _BUNDLE_LIMIT:
            raise ValueError('节点源码快照包超过传输上限')
        with _private_file(temporary, size) as source:
            digest = hashlib.file_digest(source, 'sha256').hexdigest()
        os.link(temporary, path, follow_symlinks=False)
        temporary.unlink()
        receipt = WorkspaceSnapshotArchive(**request.model_dump(), sha256=digest, bytes=size,
            tree_digest=manifest.digest, tree_bytes=manifest.bytes, file_count=len(manifest.files))
        return receipt
    finally:
        temporary.unlink(missing_ok=True)


def _publish_object(source: Path, objects: Path, digest: str, size: int) -> None:
    parent = directory_fd(objects / digest[:2], create=True)
    temporary = '.' + digest + '.' + uuid.uuid4().hex
    try:
        metadata = os.fstat(parent)
        if metadata.st_uid != os.geteuid() or metadata.st_mode & 0o022:
            raise ValueError('中央源码对象目录归属或写权限无效')
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=parent)
        with os.fdopen(descriptor, 'wb') as output, _private_file(source, size) as content:
            copied = hashlib.sha256()
            while chunk := content.read(1024 * 1024):
                copied.update(chunk)
                output.write(chunk)
            if copied.hexdigest() != digest:
                raise ValueError('中央暂存源码对象发生变化')
            output.flush()
            os.fsync(output.fileno())
        try:
            os.link(temporary, digest, src_dir_fd=parent, dst_dir_fd=parent, follow_symlinks=False)
        except FileExistsError:
            descriptor = os.open(digest, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
            with os.fdopen(descriptor, 'rb') as existing:
                metadata = os.fstat(existing.fileno())
                if (not S_ISREG(metadata.st_mode) or metadata.st_uid != os.geteuid() or metadata.st_mode & 0o022
                        or metadata.st_size != size or hashlib.file_digest(existing, 'sha256').hexdigest() != digest):
                    raise ValueError('中央已有源码对象损坏，保留原对象并拒绝覆盖')
        os.fsync(parent)
    finally:
        try:
            os.unlink(temporary, dir_fd=parent)
        except FileNotFoundError:
            pass
        os.close(parent)


def read_workspace_bundle(path: Path, receipt: WorkspaceSnapshotArchive, objects: Path | None = None) -> dict:
    """在同一固定描述符上核对整包及源码对象，再发布原内容对象。

    :param path: 本次中央私有下载文件。
    :param receipt: 已从原节点冻结scope取得的包身份。
    :param objects: 候选的中央受控对象目录，基线读取保持None。
    :return: 与原snapshot_tree相同的完整清单。
    """
    if receipt.purpose == 'baseline' and objects is not None:
        raise ValueError('原基线包不含候选内容对象')
    with _private_file(path, receipt.bytes) as source, tempfile.TemporaryDirectory(
            prefix='.snapshot-import-', dir=path.parent) as temporary:
        if hashlib.file_digest(source, 'sha256').hexdigest() != receipt.sha256:
            raise ValueError('中央源码快照整包摘要不一致')
        source.seek(0)
        staging, observed = Path(temporary), {}
        with tarfile.open(fileobj=source, mode='r:') as archive:
            header = archive.next()
            if header is None or header.name != 'snapshot.json' or not header.isfile() or not 0 < header.size <= _ENVELOPE_LIMIT:
                raise ValueError('节点源码快照缺少首个完整清单')
            with archive.extractfile(header) as content:
                envelope = _SnapshotEnvelope.model_validate(strict_json(content.read(_ENVELOPE_LIMIT + 1), _ENVELOPE_LIMIT))
            manifest = envelope.snapshot
            if (envelope.scope != receipt.scope or envelope.snapshot_id != receipt.snapshot_id or envelope.purpose != receipt.purpose
                    or manifest.digest != receipt.tree_digest or manifest.bytes != receipt.tree_bytes
                    or len(manifest.files) != receipt.file_count):
                raise ValueError('源码快照清单与原scope或导出回执不一致')
            wanted = {item.digest: item.size for item in manifest.files.values()} if receipt.purpose == 'candidate' else {}
            while (member := archive.next()) is not None:
                matched = re.fullmatch(r'objects/([a-f0-9]{2})/([a-f0-9]{64})', member.name)
                if (not member.isfile() or matched is None or matched[1] != matched[2][:2]
                        or matched[2] not in wanted or member.size != wanted[matched[2]]):
                    raise ValueError('源码快照包含额外对象、链接或大小不匹配')
                digest, size = matched[2], wanted.pop(matched[2])
                destination = staging / digest
                descriptor = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
                with os.fdopen(descriptor, 'wb') as output, archive.extractfile(member) as content:
                    checksum, count = hashlib.sha256(), 0
                    while chunk := content.read(1024 * 1024):
                        count += len(chunk)
                        if count > size:
                            raise ValueError('源码对象超过清单字节数')
                        checksum.update(chunk)
                        output.write(chunk)
                    if count != size or checksum.hexdigest() != digest:
                        raise ValueError('源码对象内容与清单摘要不一致')
                observed[digest] = size
            if wanted:
                raise ValueError('源码快照缺少清单声明的对象')
        while trailing := source.read(1024 * 1024):
            if any(trailing):
                raise ValueError('源码快照包含未声明的尾随内容')
        if objects is not None:
            for digest, size in observed.items():
                _publish_object(staging / digest, objects, digest, size)
        return manifest.model_dump(by_alias=True)
