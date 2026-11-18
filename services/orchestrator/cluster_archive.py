"""环境停机迁移的流式归档、身份绑定与受限解包。"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import tarfile
from io import BytesIO
from pathlib import Path, PurePosixPath
from stat import S_ISREG
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictInt, StrictStr

from storage_maintenance import preserve_metadata, tree_inventory
from system_update_contract import strict_json


_MANIFEST_LIMIT = 16 * 1024 * 1024
_ENTRY_LIMIT = 100000


class ArchiveIdentity(BaseModel):
    """由源隔离收据冻结的迁移包身份。

    :param protocol: 固定归档协议。
    :param operation_id: 本次持久迁移操作。
    :param deployment_id: 原部署。
    :param source_node_key: 原节点。
    :param account_id: 编排账号。
    :param environment_id: 固定环境。
    :param assignment_revision: 原人工分配版本。
    """

    model_config = ConfigDict(extra='forbid')
    protocol: Literal[1] = 1
    operation_id: StrictStr = Field(pattern=r'^[a-f0-9]{32}$')
    deployment_id: StrictStr = Field(pattern=r'^[a-z0-9][a-z0-9-]{0,35}$')
    source_node_key: StrictStr = Field(pattern=r'^(local|[a-f0-9]{32})$')
    account_id: StrictInt = Field(ge=1)
    environment_id: StrictStr = Field(pattern=r'^[a-f0-9]{32}$')
    assignment_revision: StrictInt = Field(ge=1)


class _HashReader:
    """对实际读取的字节计算摘要，并限制不可信包的总读取量。"""
    def __init__(self, source, maximum: int | None = None) -> None:
        self.source, self.digest = source, hashlib.sha256()
        self.maximum, self.count = maximum, 0

    def read(self, length: int) -> bytes:
        """读取一个有界块并累计摘要。:param length: 本次长度。:return: 实际字节。"""
        content = self.source.read(length)
        self.count += len(content)
        if self.maximum is not None and self.count > self.maximum:
            raise ValueError('迁移包超出允许的归档字节上限')
        self.digest.update(content)
        return content


def _relative(value: str) -> None:
    if (not isinstance(value, str) or not value or '\x00' in value
            or PurePosixPath(value).is_absolute() or str(PurePosixPath(value)) != value
            or any(part in ('', '.', '..') for part in value.split('/'))):
        raise ValueError('迁移清单包含非法相对路径')


def _inventory(entries: dict) -> int:
    if not isinstance(entries, dict) or not 1 <= len(entries) <= _ENTRY_LIMIT:
        raise ValueError('迁移文件清单大小无效')
    total = 0
    for name, item in entries.items():
        if name != '.':
            _relative(name)
        if not isinstance(item, dict):
            raise ValueError('迁移文件条目无效')
        kind = item.get('kind')
        extra = {'directory': set(), 'file': {'size', 'sha256'}, 'symlink': {'target'}}.get(kind) if isinstance(kind, str) else None
        if extra is None or set(item) != {'kind', 'mode', 'uid', 'gid'} | extra:
            raise ValueError('迁移文件条目类型无效')
        for field, limit in (('mode', 0o7777), ('uid', 2 ** 32 - 2), ('gid', 2 ** 32 - 2)):
            if type(item[field]) is not int or not 0 <= item[field] <= limit:
                raise ValueError('迁移文件权限或归属无效')
        if name == '.' and kind != 'directory':
            raise ValueError('迁移数据根必须为目录')
        if kind == 'file':
            if (type(item['size']) is not int or item['size'] < 0 or not isinstance(item['sha256'], str)
                    or not re.fullmatch('[a-f0-9]{64}', item['sha256'])):
                raise ValueError('迁移文件大小或摘要无效')
            total += item['size']
        if kind == 'symlink' and (not isinstance(item['target'], str) or '\x00' in item['target']
                or not item['target'] or len(os.fsencode(item['target'])) > 4096):
            raise ValueError('迁移符号链接无效')
    if '.' not in entries:
        raise ValueError('迁移清单缺少数据根')
    for name in entries:
        if name != '.':
            parent = str(PurePosixPath(name).parent)
            if entries.get(parent, {}).get('kind') != 'directory':
                raise ValueError('迁移路径的父条目必须为目录')
    return total


def _exclusions(excluded: dict) -> None:
    if not isinstance(excluded, dict):
        raise ValueError('迁移排除清单无效')
    for name, reason in excluded.items():
        _relative(name)
        if not isinstance(reason, str) or not reason.strip() or len(reason) > 1024:
            raise ValueError('迁移排除项必须登记恢复依据')


def _checksum(path: Path) -> str:
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(descriptor, 'rb') as stream:
        if not S_ISREG(os.fstat(stream.fileno()).st_mode):
            raise ValueError('迁移包必须为普通文件')
        digest = hashlib.sha256()
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def create_environment_archive(root: Path, target: Path, identity: ArchiveIdentity,
                               excluded: dict[str, str]) -> dict:
    """为已停止环境生成有身份和逐文件摘要的独立私有包。

    :param root: 调用方已经排空并隔离的源环境根。
    :param target: 本操作私有目录下的新包路径，须位于源树之外。
    :param identity: 原隔离收据身份。
    :param excluded: 精确排除项及各项恢复依据。
    :return: 包摘要、实际字节数和文件数；包内容含私有账号资料。
    """
    if target.resolve().is_relative_to(root.resolve()):
        raise ValueError('迁移包必须保存在源环境之外')
    _exclusions(excluded)
    entries = tree_inventory(root, set(excluded), entry_limit=_ENTRY_LIMIT)
    total = _inventory(entries)
    manifest = {'identity': identity.model_dump(), 'entries': entries, 'excluded': excluded}
    raw = json.dumps(manifest, ensure_ascii=True, sort_keys=True, separators=(',', ':')).encode()
    if len(raw) > _MANIFEST_LIMIT:
        raise ValueError('迁移清单超过大小上限')
    descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        with os.fdopen(descriptor, 'wb') as output, tarfile.open(fileobj=output, mode='w|') as archive:
            header = tarfile.TarInfo('manifest.json')
            header.mode, header.size = 0o600, len(raw)
            archive.addfile(header, BytesIO(raw))
            for name, item in sorted(entries.items()):
                if name == '.':
                    continue
                member = tarfile.TarInfo('content/' + name)
                member.mode, member.uid, member.gid = item['mode'], item['uid'], item['gid']
                if item['kind'] == 'directory':
                    member.type = tarfile.DIRTYPE
                    archive.addfile(member)
                elif item['kind'] == 'symlink':
                    member.type, member.linkname = tarfile.SYMTYPE, item['target']
                    archive.addfile(member)
                else:
                    member.size = item['size']
                    file_fd = os.open(root / name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
                    with os.fdopen(file_fd, 'rb') as source:
                        if not S_ISREG(os.fstat(source.fileno()).st_mode):
                            raise ValueError('迁移期间源文件被替换')
                        reader = _HashReader(source)
                        archive.addfile(member, reader)
                        if reader.digest.hexdigest() != item['sha256']:
                            raise ValueError('迁移期间源文件内容发生变化')
            if tree_inventory(root, set(excluded), entry_limit=_ENTRY_LIMIT) != entries:
                raise ValueError('迁移期间源环境发生变化')
        with target.open('rb') as output:
            os.fsync(output.fileno())
        return {'identity': identity.model_dump(), 'sha256': _checksum(target), 'bytes': target.stat().st_size,
            'files': len(entries), 'data_bytes': total}
    except BaseException:
        target.unlink(missing_ok=True)
        raise


def restore_environment_archive(source: Path, target: Path, identity: ArchiveIdentity,
                                checksum: str, maximum_bytes: int) -> dict:
    """在本操作私有暂存树中逐条验证和导入，保持链接原值。

    :param source: 已传输到目标节点的普通包文件。
    :param target: 本操作私有目录中的全新目录。
    :param identity: 中央另行冻结的源隔离身份。
    :param checksum: 中央核对的整包SHA256。
    :param maximum_bytes: 目标预检允许的普通文件总大小。
    :return: 已核对的文件数及数据大小；发布和开放准入由迁移协调方执行。
    """
    if (not re.fullmatch('[a-f0-9]{64}', checksum) or type(maximum_bytes) is not int or maximum_bytes < 0):
        raise ValueError('迁移包摘要或容量边界无效')
    parent = target.parent.lstat()
    if target.parent.is_symlink() or parent.st_uid != os.geteuid() or parent.st_mode & 0o077:
        raise ValueError('迁移暂存目录必须位于当前操作的私有目录')
    descriptor = os.open(source, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(descriptor, 'rb') as input_file:
        if not S_ISREG(os.fstat(input_file.fileno()).st_mode):
            raise ValueError('迁移包必须为普通文件')
        reader = _HashReader(input_file, maximum_bytes + _MANIFEST_LIMIT * 5 + _ENTRY_LIMIT * 1024 + 1024 * 1024)
        return _restore(reader, target, identity, checksum, maximum_bytes)


def _restore(reader: _HashReader, target: Path, identity: ArchiveIdentity, checksum: str, maximum_bytes: int) -> dict:
    with tarfile.open(fileobj=reader, mode='r|') as archive:
        header = archive.next()
        if header is None or header.name != 'manifest.json' or not header.isfile() or header.size > _MANIFEST_LIMIT:
            raise ValueError('迁移包首项清单无效')
        manifest = strict_json(archive.extractfile(header).read(), _MANIFEST_LIMIT)
        if set(manifest) != {'identity', 'entries', 'excluded'} or manifest['identity'] != identity.model_dump():
            raise ValueError('迁移包与本次源隔离身份不一致')
        _exclusions(manifest['excluded'])
        entries = manifest['entries']
        total = _inventory(entries)
        if total > maximum_bytes or total > shutil.disk_usage(target.parent).free:
            raise ValueError('目标节点迁移暂存空间不足')
        target.mkdir(mode=0o700)
        try:
            # 先建完整目录骨架，所有链接最后创建，杜绝解包路径经过包内链接。
            for name, item in sorted(entries.items(), key=lambda value: value[0].count('/')):
                if name != '.' and item['kind'] == 'directory':
                    (target / name).mkdir(mode=0o700)
            seen = set()
            while member := archive.next():
                if not member.name.startswith('content/'):
                    raise ValueError('迁移包包含清单之外的路径')
                name = member.name[len('content/'):]
                _relative(name)
                item = entries.get(name)
                if name in seen or item is None:
                    raise ValueError('迁移包包含重复或未登记的文件')
                seen.add(name)
                if item['kind'] == 'directory':
                    if not member.isdir():
                        raise ValueError('迁移目录类型不一致')
                elif item['kind'] == 'symlink':
                    if not member.issym() or member.linkname != item['target']:
                        raise ValueError('迁移链接类型或目标不一致')
                else:
                    if not member.isfile() or member.size != item['size']:
                        raise ValueError('迁移文件类型或大小不一致')
                    descriptor = os.open(target / name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
                    digest = hashlib.sha256()
                    with os.fdopen(descriptor, 'wb') as output, archive.extractfile(member) as content:
                        while chunk := content.read(1024 * 1024):
                            digest.update(chunk)
                            output.write(chunk)
                        output.flush()
                        os.fsync(output.fileno())
                    if digest.hexdigest() != item['sha256']:
                        raise ValueError('迁移文件摘要不一致')
            if seen != set(entries) - {'.'}:
                raise ValueError('迁移包缺少已登记文件')
            # 摘要覆盖实际解包读取的同一描述符与剩余填充，避免先验哈希后换包的时间窗口。
            while reader.read(1024 * 1024):
                pass
            if reader.digest.hexdigest() != checksum:
                raise ValueError('迁移包摘要不一致')
            for name, item in entries.items():
                if item['kind'] == 'symlink':
                    (target / name).symlink_to(item['target'])
            preserve_metadata(target, entries)
            if tree_inventory(target, durable=True, entry_limit=_ENTRY_LIMIT) != entries:
                raise ValueError('迁移暂存数据核验失败')
            return {'identity': identity.model_dump(), 'files': len(entries), 'data_bytes': total}
        except BaseException:
            shutil.rmtree(target)
            raise
