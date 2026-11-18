"""在运行产物边界内读取有界文本，避免链接跨出工作区。"""
import codecs
import json
import hashlib
import os
import stat
from pathlib import Path
from project_library import safe_relative
from runtime_files import directory_fd

PREVIEW_BYTES = 65536
PRIVATE_ROOTS = {'.claude-home', '.cc2api-oauth-refresh-request.json', '.cc2api-oauth-refresh-result.json'}
MAX_WORKSPACE_ENTRIES = 10000
MAX_WORKSPACE_LIST_BYTES = 2 * 1024 * 1024


def ordinary_run_alias(environment_id: str, run_id: str) -> str:
    """保留普通Run的既有物理项目别名。:param environment_id: 原环境。:param run_id: 原Run。:return: 固定摘要别名。"""
    return 'project-' + hashlib.sha256(f'{environment_id}:{run_id}'.encode()).hexdigest()[:12]


def list_workspace_files(base: Path) -> list[dict]:
    """用目录描述符列出公开产物，并限制树的规模。

    :param base: 已核对运行归属的物理工作区。
    :return: 按相对路径排序的文件与目录；链接和特殊文件被排除。
    """
    entries, encoded_size, visited = [], 0, 0

    def visit(directory: int, prefix: str, depth: int) -> None:
        nonlocal encoded_size, visited
        if depth > 64:
            raise ValueError('运行产物目录深度超过读取上限')
        with os.scandir(directory) as children:
            for child in children:
                visited += 1
                if visited > MAX_WORKSPACE_ENTRIES:
                    raise ValueError('运行产物条目超过读取上限')
                relative = prefix + child.name
                if not prefix and (child.name.startswith('.bench-') or child.name in PRIVATE_ROOTS):
                    continue
                safe_relative(relative)
                info = child.stat(follow_symlinks=False)
                if stat.S_ISDIR(info.st_mode):
                    entry = {'path': relative, 'type': 'dir'}
                elif stat.S_ISREG(info.st_mode) and info.st_nlink == 1:
                    entry = {'path': relative, 'type': 'file', 'size': info.st_size}
                else:
                    continue
                encoded_size += len(json.dumps(entry, ensure_ascii=False).encode())
                if encoded_size > MAX_WORKSPACE_LIST_BYTES:
                    raise ValueError('运行产物清单超过读取上限')
                entries.append(entry)
                if entry['type'] == 'dir':
                    nested = os.open(child.name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=directory)
                    try:
                        visit(nested, relative + '/', depth + 1)
                    finally:
                        os.close(nested)

    descriptor = directory_fd(base)
    try:
        visit(descriptor, '', 0)
    finally:
        os.close(descriptor)
    return sorted(entries, key=lambda item: item['path'])


def read_workspace_file(root: Path, run_id: str, relative: str) -> dict:
    """只读打开当前运行内的普通产物，每级目录均拒绝链接。

    :param root: 可信的工作区根目录。
    :param run_id: 已通过运行可见性校验的标识。
    :param relative: 产物相对路径。
    :return: 最多64KiB的文本、大小、二进制与截断状态。
    """
    run_id, relative = safe_relative(run_id), safe_relative(relative)
    parts = relative.split('/')
    if '/' in run_id or relative.startswith('.bench-') or parts[0] in PRIVATE_ROOTS:
        raise ValueError('该路径不是公开运行产物')
    # 使用目录描述符逐级进入，防止检查后被工作进程换成跨目录链接。
    directory = directory_fd(root)
    try:
        for part in [run_id, *parts[:-1]]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=directory)
            os.close(directory)
            directory = child
        descriptor = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
        with os.fdopen(descriptor, 'rb') as source:
            info = os.fstat(source.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                raise ValueError('只能预览普通产物文件')
            content = source.read(PREVIEW_BYTES + 1)
    finally:
        os.close(directory)
    truncated = len(content) > PREVIEW_BYTES
    data = content[:PREVIEW_BYTES]
    binary = b'\0' in data
    try:
        text = codecs.getincrementaldecoder('utf-8')().decode(data, final=not truncated) if not binary else ''
    except UnicodeDecodeError:
        text, binary = '', True
    return {'path': relative, 'text': text, 'size': info.st_size, 'truncated': truncated, 'binary': binary}
