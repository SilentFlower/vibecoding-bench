"""只读估算排除明确可重建程序和下载缓存后的备份文件体积。"""

import collections
import json
import os
from pathlib import Path
import stat


CURRENT_CONTENT = '2905c1d0c58758830db4eead47cbd8a200367283a0ba5fa9b90579279541a297'


def excluded_reason(parts: tuple[str, ...]) -> str | None:
    """按精确路径分类排除项。@param parts 数据根下的相对路径。@return 原因或 None。"""
    if parts == ('bench', 'project-library', 'releases', CURRENT_CONTENT):
        return '已固定到当前正式镜像的项目内容'
    if len(parts) < 4 or parts[:2] != ('bench', 'environments'):
        return None
    relative = parts[3:]
    if relative == ('cli',):
        return '可重装的精确版本CLI及其下载缓存'
    if relative == ('home', '.npm', '_cacache'):
        return '用户npm下载缓存'
    if relative == ('home', '.cache', 'ms-playwright'):
        return '可按版本恢复的浏览器程序缓存'
    return None


def main() -> None:
    """仅累计文件大小，不读取业务内容或创建备份。@return None。"""
    root = Path('/srv/vibebench-v3-us')
    if json.loads((root / '.v3-deployment.json').read_text()).get('deployment') != 'us':
        raise ValueError('数据目录不属于目标部署')
    included = 0
    excluded = collections.Counter()
    skipped_sockets = 0
    pending = []
    for directory, folders, names in os.walk(root, followlinks=False):
        parent = Path(directory)
        for name in list(folders):
            path = parent / name
            reason = excluded_reason(path.relative_to(root).parts)
            if reason and not path.is_symlink():
                folders.remove(name)
                pending.append((path, reason))
        for name in names:
            metadata = (parent / name).lstat()
            if stat.S_ISSOCK(metadata.st_mode):
                skipped_sockets += 1
            else:
                included += metadata.st_size
        for name in folders:
            path = parent / name
            if path.is_symlink():
                included += path.lstat().st_size
    for base, reason in pending:
        for directory, folders, names in os.walk(base, followlinks=False):
            parent = Path(directory)
            for name in names:
                metadata = (parent / name).lstat()
                if not stat.S_ISSOCK(metadata.st_mode):
                    excluded[reason] += metadata.st_size
    print(json.dumps({
        'read_only': True,
        'proposed_policy': 'essential',
        'estimated_included_file_bytes': included,
        'excluded_file_bytes_by_reason': dict(excluded),
        'skipped_sockets': skipped_sockets,
        'retains_historical_content_releases': True,
        'retains_unrecognized_home_cache': True,
        'production_writes': 0,
    }, ensure_ascii=False))


if __name__ == '__main__':
    main()
