"""节点公开配置、主机身份与中央归属的严格合同。"""
from __future__ import annotations

import base64
import hashlib
import ipaddress
import re
from pathlib import PurePosixPath
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, StrictStr, field_validator, model_validator


def host_key_identity(value: str) -> dict[str, str]:
    """核对 OpenSSH 主机公钥并计算可供管理员核验的指纹。

    :param value: 公钥算法与 Base64 编码，不接受 known_hosts 主机前缀。
    :return: 规范公钥、算法与 SHA256 指纹。
    """
    parts = value.strip().split()
    if len(parts) != 2 or parts[0] not in ('ssh-ed25519', 'ssh-rsa',
            'ecdsa-sha2-nistp256', 'ecdsa-sha2-nistp384', 'ecdsa-sha2-nistp521'):
        raise ValueError('主机公钥格式无效')
    try:
        raw = base64.b64decode(parts[1], validate=True)
        length = int.from_bytes(raw[:4], 'big')
        algorithm = raw[4:4 + length].decode('ascii')
    except (ValueError, UnicodeError) as error:
        raise ValueError('主机公钥编码无效') from error
    if algorithm != parts[0] or len(raw) > 16 * 1024 or len(raw) <= 4 + length:
        raise ValueError('主机公钥算法或长度无效')
    digest = base64.b64encode(hashlib.sha256(raw).digest()).decode().rstrip('=')
    return {'key': ' '.join(parts), 'algorithm': algorithm, 'sha256': 'SHA256:' + digest}


class NodeAddress(BaseModel):
    """管理员指定的 SSH 目标。

    :param host: IP 或 DNS 主机名。
    :param port: SSH 服务端口。
    """

    model_config = ConfigDict(extra='forbid')
    host: StrictStr = Field(min_length=1, max_length=253)
    port: StrictInt = Field(default=22, ge=1, le=65535)

    @field_validator('host')
    @classmethod
    def normalize_host(cls, value: str) -> str:
        """限定单一网络主机，防止值被解释为 SSH 参数。

        :param value: 管理员填写的主机。
        :return: 规范 IP 或小写 DNS 名称。
        """
        if value != value.strip() or '%' in value:
            raise ValueError('节点地址必须为单一 IP 或主机名')
        try:
            return str(ipaddress.ip_address(value))
        except ValueError:
            pass
        try:
            host = value.encode('idna').decode('ascii').lower().rstrip('.')
        except UnicodeError as error:
            raise ValueError('节点主机名无效') from error
        if len(host) > 253 or any(not re.fullmatch(r'[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?', label)
                for label in host.split('.')):
            raise ValueError('节点主机名无效')
        return host


class NodeConfiguration(NodeAddress):
    """节点持久配置，包含公开主机身份与认证方式，排除私有认证材料。

    :param name: 管理员可读名称。
    :param username: 具有对应 Docker 权限的专用 SSH 用户。
    :param host_key: 管理员已确认的服务器公钥。
    :param data_root: 节点宿主的独立绝对数据目录。
    :param enabled: 是否允许新工作。
    :param auth_method: SSH 私钥或密码认证方式，历史配置默认为私钥。
    """

    name: StrictStr = Field(min_length=1, max_length=80)
    username: StrictStr = Field(pattern=r'^[a-zA-Z_][a-zA-Z0-9_-]{0,63}$')
    host_key: StrictStr = Field(min_length=1, max_length=24 * 1024)
    data_root: StrictStr = Field(default='/srv/flower2api-node', min_length=2, max_length=512)
    enabled: StrictBool = True
    auth_method: Literal['private_key', 'password'] = 'private_key'

    @field_validator('host_key')
    @classmethod
    def validate_host_key(cls, value: str) -> str:
        """规范已确认的主机公钥。:param value: 公钥。:return: 规范公钥。"""
        return host_key_identity(value)['key']

    @field_validator('name')
    @classmethod
    def validate_name(cls, value: str) -> str:
        """限定节点显示名称。:param value: 名称。:return: 去除两端空白的名称。"""
        value = value.strip()
        if not value or any(ord(character) < 32 for character in value):
            raise ValueError('节点名称无效')
        return value

    @field_validator('data_root')
    @classmethod
    def validate_data_root(cls, value: str) -> str:
        """限定节点独占数据根。:param value: 宿主目录。:return: 原规范目录。"""
        path = PurePosixPath(value)
        if (not path.is_absolute() or value.startswith('//') or value != str(path) or '..' in path.parts
                or value in ('/', '/etc', '/var', '/usr', '/home', '/root', '/tmp', '/srv')
                or any(ord(character) < 32 for character in value)):
            raise ValueError('请填写节点独立的规范绝对数据目录')
        return value


class NodeCreate(NodeConfiguration):
    """新节点登记请求，认证材料只在写入时使用。

    :param private_key: OpenSSH 支持的专用无口令私钥。
    :param password: SSH 密码，按原值使用。
    """

    private_key: StrictStr | None = Field(default=None, min_length=64, max_length=32 * 1024, exclude=True, repr=False)
    password: StrictStr | None = Field(default=None, min_length=1, max_length=4096, exclude=True, repr=False)

    @model_validator(mode='after')
    def validate_authentication(self) -> NodeCreate:
        """限定唯一认证材料并保护密码的单行传递语义。:return: 已验证请求。"""
        if self.auth_method == 'private_key':
            if self.private_key is None or self.password is not None:
                raise ValueError('请仅提供所选方式的 SSH 私钥')
        elif self.password is None or self.private_key is not None:
            raise ValueError('请仅提供所选方式的 SSH 密码')
        if self.password is not None and any(character in self.password for character in ('\x00', '\r', '\n')):
            raise ValueError('SSH 密码不能包含空字符或换行')
        return self


class NodeRevision(BaseModel):
    """节点操作的并发版本。:param revision: 页面读取的版本。"""

    model_config = ConfigDict(extra='forbid')
    revision: StrictInt = Field(ge=1)


class NodeEnabled(NodeRevision):
    """节点接单状态调整。:param enabled: 是否启用。"""

    enabled: StrictBool


class NodeRename(NodeRevision):
    """节点显示名称更新。:param name: 管理员填写的名称。"""

    name: StrictStr = Field(min_length=1, max_length=80)

    @field_validator('name')
    @classmethod
    def validate_name(cls, value: str) -> str:
        """复用登记名称校验。:param value: 名称。:return: 规范名称。"""
        return NodeConfiguration.validate_name(value)


class AccountNodeChange(NodeRevision):
    """尚未执行环境的人工分配请求。

    :param node_id: 管理员选择的节点。
    :param revision: 原账号分配版本。
    """

    node_id: StrictInt = Field(ge=1)
