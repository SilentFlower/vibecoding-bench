"""固定发行源的只读版本发现；发现结果由原签名准备流程另行授信。"""
import copy
import json
import threading
import time
import urllib.error
import urllib.request

from native_kernel_upgrade import ReleaseRedirect, TAG
from native_sender import ASSET, SHA256, VERSION

API = 'https://api.github.com/repos/SilentFlower/cc-runtime-bridge/releases?per_page=100'
LIMIT = 2 * 1024 * 1024
TTL = 300
_LOCK = threading.Lock()
_cache = None
_expires = 0


def parse_releases(value: object) -> list[dict]:
    """投影可选择的合法发行标签。@param value 有界发行API响应。@return 按beta数字降序的最小元数据；制品尚待准备验签。"""
    if not isinstance(value, list) or len(value) > 100:
        raise ValueError('发行响应无效')
    versions = {}
    for item in value:
        if not isinstance(item, dict):
            continue
        release = item.get('tag_name')
        assets = item.get('assets')
        if not isinstance(release, str) or not TAG.fullmatch(release) or item.get('draft') is not False or not isinstance(assets, list):
            continue
        names = [entry.get('name') for entry in assets if isinstance(entry, dict)]
        if any(names.count(name) != 1 for name in (ASSET, 'runtime-release.json', 'runtime-release.sig')):
            continue
        published = item.get('published_at')
        versions[release] = {'release': release, 'published_at': published if isinstance(published, str) and len(published) <= 32 else None}
    return sorted(versions.values(), key=lambda entry: int(entry['release'].rsplit('.', 1)[1]), reverse=True)


def fetch_releases() -> list[dict]:
    """有界读取固定GitHub API。@return 白名单版本元数据；异常交发现所有者统一降级。"""
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), ReleaseRedirect())
    request = urllib.request.Request(API, headers={'Accept': 'application/vnd.github+json', 'User-Agent': 'flower2api-native-updates/1'})
    deadline = time.monotonic() + 10
    with opener.open(request, timeout=5) as response:
        chunks, size = [], 0
        while True:
            data = response.read1(min(65536, LIMIT + 1 - size))
            if not data:
                break
            chunks.append(data)
            size += len(data)
            if size > LIMIT or time.monotonic() > deadline:
                raise ValueError('发行响应超过大小或时间预算')
    def unique(items):
        """拒绝重复元数据字段。@param items JSON字段。@return 唯一字段对象。"""
        value = dict(items)
        if len(value) != len(items):
            raise ValueError('发行响应包含重复字段')
        return value

    def invalid_number(value):
        """拒绝JSON外数值。@param value 原始数值标识。@return 抛出受控错误。"""
        raise ValueError('发行响应包含非法数值')

    try:
        # 发行API顶层为数组；更新清单的strict_json只接受对象，不能用于此合同。
        return parse_releases(json.loads(b''.join(chunks), object_pairs_hook=unique, parse_constant=invalid_number))
    except (UnicodeError, RecursionError, json.JSONDecodeError) as error:
        raise ValueError('发行响应JSON无效') from error


def discover_releases(refresh: bool = False) -> dict:
    """读取或显式刷新发行列表，失败保留缓存和可见原因。@param refresh 是否绕过五分钟缓存。@return ready/stale/unavailable及最小版本列表，不触发模型。"""
    global _cache, _expires
    with _LOCK:
        if not refresh and _cache is not None and time.monotonic() < _expires:
            return copy.deepcopy(_cache)
        reason = None
        try:
            versions = fetch_releases()
        except urllib.error.HTTPError as error:
            reason = 'release_rate_limited' if error.code in (403, 429) else 'release_fetch_failed'
        except (OSError, ValueError, TypeError, TimeoutError):
            reason = 'release_fetch_failed'
        if reason:
            # 陈旧列表只是发现线索；每次真正准备仍独立校验签名和精确摘要。
            result = copy.deepcopy(_cache) if _cache else {'versions': [], 'latest': None, 'checked_at_ms': None,
                'builtin': {'release': VERSION, 'launcher_sha256': SHA256}}
            result.update(state='stale' if _cache else 'unavailable', reason=reason)
            return result
        _cache = {'state': 'ready', 'reason': None, 'versions': versions,
            'latest': versions[0]['release'] if versions else None, 'checked_at_ms': int(time.time() * 1000),
            'builtin': {'release': VERSION, 'launcher_sha256': SHA256}}
        _expires = time.monotonic() + TTL
        return copy.deepcopy(_cache)
