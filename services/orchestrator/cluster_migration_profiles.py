"""将迁移profile以私有文件传输，控制消息只携带摘要引用。"""
from __future__ import annotations

import hashlib
import os
import re
from pathlib import Path
from stat import S_ISREG

from pydantic import BaseModel, ConfigDict, Field, StrictInt, StrictStr

from runtime_files import atomic_text, private_directory


PROFILE_NAMES = ('.credentials.json', '.claude.json', 'settings.json')


class ProfileReference(BaseModel):
    """绑定已投影profile文件的真实大小和摘要。:param sha256: 摘要。:param bytes: 字节数。"""

    model_config = ConfigDict(extra='forbid')
    sha256: StrictStr = Field(pattern=r'^[a-f0-9]{64}$')
    bytes: StrictInt = Field(ge=2)


class MigrationProfiles:
    """保存原操作的独立profile文件。:param data: 中央数据根。:param operation: 原迁移操作。"""

    def __init__(self, data: Path, operation: str) -> None:
        """建立原操作私有文件目录。:param data: 数据根。:param operation: 原操作。:return: None。"""
        if not re.fullmatch('[a-f0-9]{32}', operation):
            raise ValueError('迁移profile操作身份无效')
        self.root = data / 'cluster-migration-profiles' / operation
        private_directory(self.root)
        self.references = {}

    def save(self, name: str, content: str) -> None:
        """保存已按凭据所有权过滤的单个文件。:param name: 固定文件名。:param content: 原JSON。:return: None。"""
        if name not in PROFILE_NAMES:
            raise ValueError('迁移profile文件身份无效')
        raw = content.encode()
        reference = ProfileReference(sha256=hashlib.sha256(raw).hexdigest(), bytes=len(raw))
        target = self.path(reference)
        if target.exists() or target.is_symlink():
            read_profile(target, reference)
        else:
            atomic_text(target, content)
        self.references[name] = reference

    def path(self, reference: ProfileReference) -> Path:
        """定位固定摘要文件。:param reference: 本操作文件引用。:return: 私有路径。"""
        return self.root / ('profile-' + reference.sha256 + '.json')


def read_profile(path: Path, reference: ProfileReference) -> str:
    """读取已冻结的私有profile并核验实际内容。:param path: 固定操作路径。:param reference: 引用。:return: JSON原文。"""
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(descriptor, 'rb') as source:
        metadata = os.fstat(source.fileno())
        if (not S_ISREG(metadata.st_mode) or metadata.st_size != reference.bytes
                or metadata.st_uid != os.geteuid() or metadata.st_mode & 0o077 or metadata.st_nlink != 1):
            raise ValueError('迁移profile文件大小或权限不一致')
        raw = source.read(reference.bytes + 1)
        if len(raw) != reference.bytes or hashlib.sha256(raw).hexdigest() != reference.sha256:
            raise ValueError('迁移profile文件摘要不一致')
        return raw.decode()
