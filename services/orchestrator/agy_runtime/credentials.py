"""发布账号内AT-only副本，完整刷新凭据保留在管理所有者。"""
import json
import os
import stat
from datetime import datetime, timezone
from pathlib import Path

from runtime_files import atomic_json, directory_fd

TOKEN_PATH = Path('.gemini/antigravity-cli/antigravity-oauth-token')


def read_private(path: Path) -> dict:
    """读取当前身份所有的私有普通JSON。@param path 受控文件。@return 解析后的对象。"""
    parent = directory_fd(path.parent)
    try:
        descriptor = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
        with os.fdopen(descriptor, 'rb') as stream:
            info = os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_nlink != 1 or info.st_mode & 0o077:
                raise ValueError('AGY私有文件归属或权限无效')
            raw = stream.read(2 * 1024 * 1024 + 1)
        if len(raw) > 2 * 1024 * 1024:
            raise ValueError('AGY私有文件超限')
        value = json.loads(raw)
        if not isinstance(value, dict):
            raise ValueError('AGY私有文件结构无效')
        return value
    finally:
        os.close(parent)


def read_access_document(home: Path) -> dict:
    """核验业务HOME中的AT-only凭据。@param home 当前worker私有HOME。@return 已核验文档。"""
    value = read_private(home / TOKEN_PATH)
    token = value.get('token')
    if value.get('auth_method') != 'consumer' or not isinstance(token, dict) or 'refresh_token' in token:
        raise ValueError('AGY业务副本必须只持有访问凭据')
    access = token.get('access_token')
    if not isinstance(access, str) or not 1 <= len(access) <= 16384 or any(ord(c) <= 32 or ord(c) >= 127 for c in access):
        raise ValueError('AGY访问凭据无效')
    try:
        expiry = datetime.fromisoformat(token['expiry'].replace('Z', '+00:00'))
        if expiry.tzinfo is None or expiry <= datetime.now(timezone.utc):
            raise ValueError
    except (KeyError, TypeError, AttributeError, ValueError):
        raise ValueError('AGY业务凭据有效期无效') from None
    return value


def publish_access_document(home: Path, snapshot: dict) -> dict:
    """将同代管理快照投影到独立业务HOME。@param home 新worker私有目录。@param snapshot 同锁内取得的AT快照。@return 不含令牌的归属。"""
    if set(snapshot) != {'account_id', 'credential_generation', 'access_token', 'expires_at', 'email'}:
        raise ValueError('AGY运行快照字段无效')
    for key in ['account_id', 'credential_generation']:
        if type(snapshot[key]) is not int or snapshot[key] < 1:
            raise ValueError('AGY运行快照归属无效')
    if type(snapshot['expires_at']) is not int or not isinstance(snapshot['email'], str):
        raise ValueError('AGY运行快照身份或时间无效')
    if (home / TOKEN_PATH).exists() or (home / TOKEN_PATH).is_symlink():
        raise ValueError('AGY业务HOME已经发布凭据')
    expiry = datetime.fromtimestamp(snapshot['expires_at'] / 1000, timezone.utc)
    value = {'auth_method': 'consumer', 'id_token_email': snapshot['email'], 'token': {
        'access_token': snapshot['access_token'], 'expiry': expiry.isoformat(), 'token_type': 'Bearer'}}
    # 每个凭据代次使用独立HOME；发布后核验同一原子文件，禁止第二份RT进入业务进程。
    atomic_json(home / TOKEN_PATH, value)
    try:
        read_access_document(home)
    except Exception:
        (home / TOKEN_PATH).unlink(missing_ok=True)
        raise
    return {key: snapshot[key] for key in ['account_id', 'credential_generation', 'expires_at']}
