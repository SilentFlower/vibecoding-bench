"""平台发行、目录及更新操作的严格合同，供宿主和管理端共用。"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import subprocess
import tempfile
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from stat import S_ISREG
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

from runtime_files import directory_fd

REPOSITORY = 'SilentFlower/vibecoding-bench'
DOWNLOAD_ROOT = f'https://github.com/{REPOSITORY}/releases/download'
RELEASE_RE = re.compile(r'system-ci-[1-9][0-9]*-[1-9][0-9]*')
BUILD_RE = re.compile(r'ci-[1-9][0-9]*-[1-9][0-9]*')
SHA_RE = re.compile(r'[a-f0-9]{64}')
REV_RE = re.compile(r'[a-f0-9]{40}')
ASSET_RE = re.compile(r'[A-Za-z0-9][A-Za-z0-9._-]{0,127}')
DEPLOYMENT_RE = re.compile(r'[a-z0-9][a-z0-9-]{0,35}')
ROLES = ('control', 'account')
PROTOCOL = 1
MANIFEST_LIMIT = 131072
INDEX_LIMIT = 262144
MAX_BUNDLE_BYTES = 16 * 1024 ** 3
TERMINAL = {'succeeded', 'succeeded_cleanup_pending', 'failed', 'restored', 'cancelled'}


def strict_json(raw: bytes, limit: int = MANIFEST_LIMIT) -> dict:
    """解码完整、有界且字段唯一的 JSON 对象。

    :param raw: 完整原字节。
    :param limit: 原字节上限。
    :return: 对象；重复字段、非法数值或类型抛出 ValueError。
    """
    def unique(items):
        value = dict(items)
        if len(value) != len(items):
            raise ValueError('更新合同包含重复字段')
        return value

    def invalid_number(value):
        raise ValueError('更新合同包含非法数值')

    if not isinstance(raw, bytes) or len(raw) > limit:
        raise ValueError('更新合同超过大小限制')
    try:
        value = json.loads(raw, object_pairs_hook=unique, parse_constant=invalid_number)
    except (UnicodeError, RecursionError, json.JSONDecodeError) as error:
        raise ValueError('更新合同不是完整 JSON') from error
    if not isinstance(value, dict):
        raise ValueError('更新合同必须为对象')
    return value


def safe_read(path: Path, limit: int = MANIFEST_LIMIT, *, private: bool = False) -> bytes:
    """固定文件描述符读取普通文件，拒绝链接、FIFO 和越界内容。

    :param path: 可信目录中的精确文件。
    :param limit: 字节上限。
    :param private: 是否要求当前用户私有且单链接。
    :return: 完整原字节。
    """
    directory = directory_fd(path.parent)
    try:
        descriptor = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
    finally:
        os.close(directory)
    with os.fdopen(descriptor, 'rb') as stream:
        info = os.fstat(stream.fileno())
        if not S_ISREG(info.st_mode) or info.st_size > limit:
            raise ValueError('更新文件类型或大小无效')
        if private and (info.st_uid != os.geteuid() or info.st_mode & 0o077 or info.st_nlink != 1):
            raise ValueError('更新私有文件权限或归属无效')
        raw = stream.read(limit + 1)
        if len(raw) > limit:
            raise ValueError('更新文件读取超过限制')
        return raw


def verify_signed(raw: bytes, signature: bytes, public_key: str, limit: int = MANIFEST_LIMIT) -> dict:
    """校验 Ed25519 原字节签名后解析合同。

    :param raw: 原字节。
    :param signature: 精确 64 字节签名。
    :param public_key: 部署固定原始 32 字节公钥的小写 hex。
    :param limit: 原字节限制。
    :return: 已验签对象；不做具体发行语义判断。
    """
    if not isinstance(public_key, str) or not SHA_RE.fullmatch(public_key) or len(signature) != 64 or len(raw) > limit:
        raise ValueError('更新签名参数无效')
    with tempfile.TemporaryDirectory(prefix='v3-update-signature-') as temporary:
        root = Path(temporary)
        (root / 'key.der').write_bytes(bytes.fromhex('302a300506032b6570032100' + public_key))
        (root / 'body').write_bytes(raw)
        (root / 'signature').write_bytes(signature)
        result = subprocess.run(['openssl', 'pkeyutl', '-verify', '-pubin', '-keyform', 'DER',
            '-inkey', str(root / 'key.der'), '-rawin', '-in', str(root / 'body'),
            '-sigfile', str(root / 'signature')], capture_output=True, timeout=5, check=False)
        if result.returncode:
            raise ValueError('平台发行签名无效')
    return strict_json(raw, limit)


def _fields(value, names: set[str], label: str) -> None:
    if not isinstance(value, dict) or set(value) != names:
        raise ValueError(f'{label}字段不完整或存在未知字段')


def _integer(value, lower: int, upper: int, label: str) -> None:
    if type(value) is not int or not lower <= value <= upper:
        raise ValueError(f'{label}超出范围')


def _digest(value, label: str, prefix: bool = False) -> None:
    if not isinstance(value, str) or not re.fullmatch(r'sha256:[a-f0-9]{64}' if prefix else r'[a-f0-9]{64}', value):
        raise ValueError(f'{label}摘要无效')


def _sequence(value) -> None:
    if not isinstance(value, list) or len(value) != 2:
        raise ValueError('发行顺序无效')
    for item in value:
        _integer(item, 1, 2 ** 53 - 1, '发行顺序')


def _timestamp(value) -> float:
    if not isinstance(value, str) or len(value) > 32 or not value.endswith('Z'):
        raise ValueError('发行时间必须为 UTC')
    try:
        return datetime.fromisoformat(value[:-1] + '+00:00').timestamp()
    except (ValueError, OverflowError) as error:
        raise ValueError('发行时间无效') from error


def _asset(value, maximum: int) -> None:
    _fields(value, {'name', 'size', 'sha256'}, '发行附件')
    if not isinstance(value['name'], str) or not ASSET_RE.fullmatch(value['name']):
        raise ValueError('发行附件名称无效')
    _integer(value['size'], 1, maximum, '发行附件大小')
    _digest(value['sha256'], '发行附件')


def validate_release(value: dict) -> dict:
    """校验平台发行合同的全部字段及受支持能力。

    :param value: 已解析清单。
    :return: 原对象；不兼容抛出 ValueError。
    """
    _fields(value, {'schema_version', 'release', 'sequence', 'published_at', 'platform',
        'build_manifests', 'control', 'account', 'compatibility', 'data_compatibility', 'changes', 'bundle'}, '平台发行')
    if type(value['schema_version']) is not int or value['schema_version'] != 1:
        raise ValueError('平台发行格式不受支持')
    if not isinstance(value['release'], str) or not RELEASE_RE.fullmatch(value['release']):
        raise ValueError('平台发行标签无效')
    _sequence(value['sequence'])
    _timestamp(value['published_at'])
    if value['platform'] != 'linux/amd64':
        raise ValueError('平台发行架构不受支持')
    if not isinstance(value['changes'], str) or len(value['changes']) > 8000:
        raise ValueError('版本说明超出限制')
    _fields(value['build_manifests'], set(ROLES), '组件来源')
    for role in ROLES:
        _asset(value['build_manifests'][role], MANIFEST_LIMIT)
        entry = value[role]
        _fields(entry, {'release', 'reference', 'registry_digest', 'config_digest', 'revision', 'unpacked_bytes', 'content_sha256'}, '组件镜像')
        if not isinstance(entry['release'], str) or not BUILD_RE.fullmatch(entry['release']):
            raise ValueError('组件来源批次无效')
        reference = f'ghcr.io/silentflower/vibebench-v3-{role}:v3-{entry["release"]}'
        if entry['reference'] != reference or not isinstance(entry['revision'], str) or not REV_RE.fullmatch(entry['revision']):
            raise ValueError('组件来源仓库或提交无效')
        _digest(entry['registry_digest'], '仓库镜像', True)
        _digest(entry['config_digest'], '镜像配置', True)
        _digest(entry['content_sha256'], '组件内容')
        _integer(entry['unpacked_bytes'], 1, 64 * 1024 ** 3, '镜像空间')
    capabilities = value['compatibility']
    _fields(capabilities, {'updater', 'gate', 'bridge', 'layout', 'cli_install', 'credential_ownership', 'account_protocols'}, '兼容协议')
    for key, expected in {'updater': 1, 'gate': 1, 'bridge': 1, 'layout': 2, 'cli_install': 2, 'credential_ownership': 1}.items():
        if type(capabilities[key]) is not int or capabilities[key] != expected:
            raise ValueError(f'更新所需{key}协议不受支持')
    if capabilities['account_protocols'] != [1] or any(type(item) is not int for item in capabilities['account_protocols']):
        raise ValueError('账号运行协议不受支持')
    _fields(value['data_compatibility'], {'bench', 'gateway'}, '数据兼容')
    for entry in value['data_compatibility'].values():
        _fields(entry, {'contract', 'rollback_compatible'}, '数据合同')
        _digest(entry['contract'], '数据合同')
        accepted = entry['rollback_compatible']
        if not isinstance(accepted, list) or not 1 <= len(accepted) <= 32 or len(set(map(str, accepted))) != len(accepted):
            raise ValueError('数据回退兼容集合无效')
        for digest in accepted:
            _digest(digest, '数据回退合同')
        if entry['contract'] not in accepted:
            raise ValueError('数据合同缺少自身兼容声明')
    _asset(value['bundle'], MAX_BUNDLE_BYTES)
    return value


def validate_index(value: dict, highest: list[int] | None = None, now: float | None = None) -> dict:
    """校验目录新鲜度、顺序和有界发行引用。

    :param value: 已验签目录。
    :param highest: 本部署最高已接受顺序。
    :param now: 校验时刻；默认实际时间。
    :return: 原目录；回放及过期抛出 ValueError。
    """
    _fields(value, {'schema_version', 'sequence', 'issued_at', 'expires_at', 'releases'}, '版本目录')
    if type(value['schema_version']) is not int or value['schema_version'] != 1:
        raise ValueError('版本目录格式不受支持')
    _sequence(value['sequence'])
    if highest is not None and value['sequence'] < highest:
        raise ValueError('版本目录顺序已经过期')
    instant = time.time() if now is None else now
    issued, expires = _timestamp(value['issued_at']), _timestamp(value['expires_at'])
    if not issued <= instant + 300 or not instant < expires or not 0 < expires - issued <= 31 * 86400:
        raise ValueError('版本目录已过期或时间无效')
    entries = value['releases']
    if not isinstance(entries, list) or not 1 <= len(entries) <= 64:
        raise ValueError('目录发行数量无效')
    identities = set()
    for entry in entries:
        _fields(entry, {'release', 'manifest', 'sequence'}, '目录发行')
        if not isinstance(entry['release'], str) or not RELEASE_RE.fullmatch(entry['release']) or entry['release'] in identities:
            raise ValueError('目录发行身份无效或重复')
        identities.add(entry['release'])
        _asset(entry['manifest'], MANIFEST_LIMIT)
        if entry['manifest']['name'] != 'system-release.json':
            raise ValueError('目录清单附件名称无效')
        _sequence(entry['sequence'])
        if entry['sequence'] > value['sequence']:
            raise ValueError('目录发行顺序超出目录')
    if max(entry['sequence'] for entry in entries) != value['sequence']:
        raise ValueError('目录缺少当前发行')
    return value


def validate_operation(value: dict) -> dict:
    """校验冻结的安装／准备／回退写请求。

    :param value: 原始操作对象。
    :return: 原对象；未知字段或非法 ID 拒绝。
    """
    _fields(value, {'operation_id', 'expected_revision', 'target_release', 'target_manifest_sha256', 'drain_timeout_seconds'}, '更新操作')
    for field in ('operation_id', 'expected_revision'):
        try:
            if str(uuid.UUID(value[field])) != value[field]:
                raise ValueError('更新操作身份格式无效')
        except (ValueError, AttributeError, TypeError) as error:
            raise ValueError('更新操作身份格式无效') from error
    if not isinstance(value['target_release'], str) or not RELEASE_RE.fullmatch(value['target_release']):
        raise ValueError('更新目标版本无效')
    _digest(value['target_manifest_sha256'], '更新目标')
    _integer(value['drain_timeout_seconds'], 60, 7200, '排空等待期限')
    return value


def compatible_data(original: dict, target: dict) -> bool:
    """按目标的受信回退证明判断双库是否允许在线切换。

    :param original: 已核验的原版数据兼容合同。
    :param target: 已核验的目标数据兼容合同。
    :return: 两库均具备向原版恢复的声明。
    """
    return all(original[name]['contract'] in target[name]['rollback_compatible'] for name in ('bench', 'gateway'))


class ReleaseRedirect(HTTPRedirectHandler):
    """限定发行附件的 HTTPS 跳转来源。"""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        """校核下一跳，拒绝跨信任域地址。

        :param req: 原请求。
        :param fp: 原响应。
        :param code: 状态码。
        :param msg: 状态说明。
        :param headers: 响应头。
        :param newurl: 下一跳。
        :return: 新请求。
        """
        target = urlsplit(newurl)
        if target.scheme != 'https' or target.netloc not in {'github.com', 'api.github.com', 'release-assets.githubusercontent.com', 'objects.githubusercontent.com'}:
            raise ValueError('发行下载跳转来源无效')
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def fetch_repository_file(name: str, commit: str, limit: int) -> bytes:
    """按固定提交读取目录文件，保持二进制签名原始字节。

    :param name: index.json 或 index.sig。
    :param commit: 已取得的完整目录提交 SHA。
    :param limit: 解码后的字节上限。
    :return: 校核大小及 Git blob 身份后的原始内容。
    """
    if name not in {'index.json', 'index.sig'} or not isinstance(commit, str) or not REV_RE.fullmatch(commit):
        raise ValueError('版本目录文件来源无效')
    if type(limit) is not int or limit < 1 or limit > INDEX_LIMIT:
        raise ValueError('版本目录文件大小限制无效')
    # Contents 的文本及 content 载荷都会转换部分二进制字节，只读取其固定提交下的 blob 身份。
    envelope_limit = 4 * ((limit + 2) // 3) + 8192
    metadata = strict_json(fetch_bytes(f'https://api.github.com/repos/{REPOSITORY}/contents/{name}?ref={commit}',
        envelope_limit, accept='application/vnd.github+json'), envelope_limit)
    if (metadata.get('type') != 'file' or metadata.get('path') != name
            or type(metadata.get('size')) is not int or not 0 <= metadata['size'] <= limit
            or not isinstance(metadata.get('sha'), str) or not REV_RE.fullmatch(metadata['sha'])):
        raise ValueError('版本目录文件元数据无效')
    blob = strict_json(fetch_bytes(f'https://api.github.com/repos/{REPOSITORY}/git/blobs/{metadata["sha"]}',
        envelope_limit, accept='application/vnd.github+json'), envelope_limit)
    if (blob.get('encoding') != 'base64' or type(blob.get('size')) is not int
            or blob['size'] != metadata['size'] or not isinstance(blob.get('content'), str)):
        raise ValueError('版本目录 Git blob 元数据无效')
    raw = base64.b64decode(blob['content'].replace('\n', ''), validate=True)
    if len(raw) != metadata['size']:
        raise ValueError('版本目录文件大小不符')
    identity = hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest()
    if metadata.get('sha') != identity:
        raise ValueError('版本目录 Git blob 身份不符')
    return raw


def fetch_bytes(url: str, limit: int, *, timeout: int = 90, accept: str = 'application/vnd.github.raw+json') -> bytes:
    """读取受信 GitHub 小型资源的完整字节。

    :param url: 固定仓库产生的 HTTPS 地址。
    :param limit: 完整内容字节上限。
    :param timeout: 总期限秒数。
    :param accept: 固定调用点选择的 GitHub 响应格式。
    :return: 完整字节。
    """
    target = urlsplit(url)
    if target.scheme != 'https' or target.netloc not in {'github.com', 'api.github.com'}:
        raise ValueError('发行下载起始来源无效')
    opener = build_opener(ProxyHandler({}), ReleaseRedirect())
    request = Request(url, headers={'Accept': accept, 'User-Agent': 'vibebench-system-updater/1'})
    deadline = time.monotonic() + timeout
    with opener.open(request, timeout=10) as response:
        chunks, total = [], 0
        while True:
            chunk = response.read1(min(65536, limit + 1 - total))
            if not chunk:
                break
            total += len(chunk)
            if total > limit or time.monotonic() >= deadline:
                raise ValueError('发行下载超过大小或时间限制')
            chunks.append(chunk)
    return b''.join(chunks)


def utc_now() -> str:
    """生成 UTC 秒精度时刻。

    :return: 带 Z 后缀的时间。
    """
    return datetime.now(timezone.utc).isoformat(timespec='seconds').replace('+00:00', 'Z')
