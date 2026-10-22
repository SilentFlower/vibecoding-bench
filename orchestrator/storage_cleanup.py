"""按精确清单维护本部署缓存与冻结制品，不删除业务状态。"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import uuid

from storage_assets import cli_recovery_recipe
from storage_maintenance import deduplicate_immutable_tree, tree_inventory


CACHE_PATH = re.compile(r'bench/environments/[0-9a-f]{32}/(?:home/\.npm|cli/\.npm-cache)/_cacache')
CONTENT_PATH = re.compile(r'bench/project-library/releases/[0-9a-f]{64}')
CLI_PATH = re.compile(r'bench/environments/[0-9a-f]{32}/cli/\d+\.\d+\.\d+(?:[-+][A-Za-z0-9._-]+)?')


def _digest(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def _directory(root: Path, relative: str) -> Path | None:
    current = root
    for part in relative.split('/'):
        if part in ('', '.', '..'):
            raise ValueError('维护目录路径不合法')
        current = current / part
        if current.is_symlink() or not current.is_dir():
            return None
    return current


def storage_plan(root: Path, release: str) -> dict:
    """只读生成缓存清理与冻结文件去重清单。

    :param root: 已核验归属的部署数据根。
    :param release: 已核验的正式发布批次。
    :return: 绑定逻辑文件摘要和目录身份的精确维护计划。
    """
    caches, content, cli, retained = [], [], [], []
    environments = _directory(root, 'bench/environments')
    if environments is not None:
        for environment in sorted(environments.iterdir()):
            if environment.is_symlink() or not environment.is_dir() or not re.fullmatch(r'[0-9a-f]{32}', environment.name):
                continue
            for suffix in ('home/.npm/_cacache', 'cli/.npm-cache/_cacache'):
                relative = str(environment.relative_to(root)) + '/' + suffix
                path = _directory(root, relative)
                if path is not None:
                    metadata = path.stat()
                    inventory = tree_inventory(path)
                    caches.append({'path': relative, 'inventory_sha256': _digest(inventory),
                        'device': metadata.st_dev, 'inode': metadata.st_ino,
                        'bytes': sum(item.get('size', 0) for item in inventory.values())})
            versions = _directory(environment, 'cli')
            if versions is not None:
                for path in sorted(versions.iterdir()):
                    relative = str(path.relative_to(root))
                    if not CLI_PATH.fullmatch(relative) or path.is_symlink() or not path.is_dir():
                        continue
                    try:
                        recipe = cli_recovery_recipe(path)
                        if recipe['install_receipt'] is not None:
                            cli.append({'path': relative, 'inventory_sha256': _digest(recipe['files'])})
                        else:
                            retained.append({'path': relative, 'reason': '旧安装协议不能证明后续不会原地写入'})
                    except (OSError, ValueError, KeyError):
                        retained.append({'path': relative, 'reason': '程序恢复或只读证据不足'})
            browsers = _directory(environment, 'home/.cache/ms-playwright')
            if browsers is not None:
                retained.append({'path': str(browsers.relative_to(root)), 'reason': '保留已安装浏览器，避免任务临时下载'})
    releases = _directory(root, 'bench/project-library/releases')
    if releases is not None:
        for path in sorted(releases.iterdir()):
            relative = str(path.relative_to(root))
            if CONTENT_PATH.fullmatch(relative) and not path.is_symlink() and path.is_dir():
                content.append({'path': relative, 'inventory_sha256': _digest(tree_inventory(path))})
    plan = {'schema': 1, 'source_root': str(root), 'release': release, 'caches': caches,
        'content': content, 'cli': cli, 'retained': retained}
    return dict(plan, plan_sha256=_digest(plan))


def _cache_parent(root_fd: int, relative: str) -> tuple[int, str]:
    parts = relative.split('/')
    descriptor = os.dup(root_fd)
    try:
        for name in parts[:-1]:
            child = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=descriptor)
            os.close(descriptor)
            descriptor = child
        return descriptor, parts[-1]
    except BaseException:
        os.close(descriptor)
        raise


def apply_storage_plan(root: Path, release: str, plan: dict) -> dict:
    """在调用方全停机后应用精确清单，变化中的项目拒绝操作。

    :param root: 当前部署的规范数据根。
    :param release: 当前已验证发布批次。
    :param plan: storage_plan 生成且未修改的清单。
    :return: 实际缓存清理、去重结果和文件系统空间变化。
    """
    keys = {'schema', 'source_root', 'release', 'caches', 'content', 'cli', 'retained', 'plan_sha256'}
    if (not isinstance(plan, dict) or set(plan) != keys or type(plan.get('schema')) is not int
            or any(not isinstance(plan.get(key), list) for key in ('caches', 'content', 'cli', 'retained'))):
        raise ValueError('维护清单结构不合法')
    unsigned = {key: value for key, value in plan.items() if key != 'plan_sha256'}
    if (plan.get('schema') != 1 or plan.get('source_root') != str(root)
            or plan.get('release') != release or plan.get('plan_sha256') != _digest(unsigned)):
        raise ValueError('维护清单来源、版本或摘要不匹配')
    if not shutil.rmtree.avoids_symlink_attacks:
        raise ValueError('当前平台不支持安全的目录缓存清理')
    # 删除任何缓存之前先验证整份清单，避免遗漏了后半段的非法路径。
    seen = set()
    for category, expression in (('caches', CACHE_PATH), ('content', CONTENT_PATH), ('cli', CLI_PATH)):
        for item in plan[category]:
            required = {'path', 'inventory_sha256'} | ({'device', 'inode', 'bytes'} if category == 'caches' else set())
            if (not isinstance(item, dict) or set(item) != required or not isinstance(item.get('path'), str)
                    or not isinstance(item.get('inventory_sha256'), str)
                    or not re.fullmatch(r'[0-9a-f]{64}', item['inventory_sha256'])
                    or any(type(item[key]) is not int or item[key] < 0 for key in required - {'path', 'inventory_sha256'})):
                raise ValueError('维护条目的字段不合法')
            relative = item['path']
            if relative in seen:
                raise ValueError('维护清单不能包含重复目录')
            seen.add(relative)
            path = _directory(root, relative) if expression.fullmatch(relative) else None
            if (path is None or path.stat().st_dev != root.stat().st_dev
                    or _digest(tree_inventory(path)) != item['inventory_sha256']):
                raise ValueError('维护清单已变化或目录越过允许范围')
    descriptor = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    before = shutil.disk_usage(root).free
    removed, deduplicated = [], []
    try:
        for item in plan['caches']:
            parent, name = _cache_parent(descriptor, item['path'])
            temporary = '.v3-cache-cleanup-' + uuid.uuid4().hex
            renamed = False
            try:
                metadata = os.stat(name, dir_fd=parent, follow_symlinks=False)
                if (metadata.st_dev, metadata.st_ino) != (item['device'], item['inode']):
                    raise ValueError('缓存目录身份已变化')
                os.rename(name, temporary, src_dir_fd=parent, dst_dir_fd=parent)
                renamed = True
                anchored = Path('/proc/self/fd') / str(parent) / temporary
                if _digest(tree_inventory(anchored)) != item['inventory_sha256']:
                    raise ValueError('缓存目录在收口时发生变化')
                shutil.rmtree(temporary, dir_fd=parent)
                renamed = False
                os.fsync(parent)
                removed.append(item['path'])
            except BaseException:
                if renamed:
                    try:
                        os.stat(name, dir_fd=parent, follow_symlinks=False)
                    except FileNotFoundError:
                        os.rename(temporary, name, src_dir_fd=parent, dst_dir_fd=parent)
                raise
            finally:
                os.close(parent)
        for category in ('content', 'cli'):
            for item in plan[category]:
                path = _directory(root, item['path'])
                if path is None or _digest(tree_inventory(path)) != item['inventory_sha256']:
                    raise ValueError('冻结制品在操作前发生变化')
                if category == 'cli':
                    if cli_recovery_recipe(path)['install_receipt'] is None:
                        raise ValueError('CLI 原子安装证明不可用')
                    result = deduplicate_immutable_tree(path, minimum_bytes=1024**2, owner_uid=0,
                        canonical_root=root / 'bench/cli-artifacts')
                else:
                    result = deduplicate_immutable_tree(path, owner_uid=0)
                if _digest(tree_inventory(path)) != item['inventory_sha256']:
                    raise ValueError('去重改变了冻结文件的逻辑内容')
                deduplicated.append({'path': item['path'], **result})
    finally:
        os.close(descriptor)
    after = shutil.disk_usage(root).free
    return {'status': 'passed', 'removed_caches': removed, 'deduplicated': deduplicated,
        'free_before_bytes': before, 'free_after_bytes': after, 'freed_bytes_observed': after - before,
        'retained': plan['retained']}
