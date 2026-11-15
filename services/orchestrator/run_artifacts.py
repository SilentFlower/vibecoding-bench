"""在运行产物边界内读取有界文本，避免链接跨出工作区。"""
import codecs
import os
import stat
from pathlib import Path
from project_library import safe_relative

PREVIEW_BYTES = 65536
PRIVATE_ROOTS = {'.claude-home', '.cc2api-oauth-refresh-request.json', '.cc2api-oauth-refresh-result.json'}


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
    directory = os.open(root, os.O_RDONLY | os.O_DIRECTORY)
    try:
        for part in [run_id, *parts[:-1]]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=directory)
            os.close(directory)
            directory = child
        descriptor = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
        with os.fdopen(descriptor, 'rb') as source:
            info = os.fstat(source.fileno())
            if not stat.S_ISREG(info.st_mode):
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
