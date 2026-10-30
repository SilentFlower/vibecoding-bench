"""账号运行文件的安全目录访问与原子发布，供管理端和网络角色共用。"""
from __future__ import annotations

import json
import os
import uuid
from pathlib import Path


def directory_fd(path: Path, create: bool = False) -> int:
    """逐级固定无链接目录，避免检查后被替换的路径进入文件操作。

    :param path: 受控目录。
    :param create: 是否创建缺少的目录。
    :return: 调用者负责关闭的目录描述符。
    """
    absolute = path.absolute()
    if '..' in absolute.parts:
        raise ValueError('账号文件路径不能包含上级目录')
    directory = os.open(absolute.anchor, os.O_DIRECTORY)
    try:
        for part in absolute.parts[1:]:
            if create:
                try:
                    os.mkdir(part, dir_fd=directory)
                except FileExistsError:
                    pass
            following = os.open(part, os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=directory)
            os.close(directory)
            directory = following
        return directory
    except Exception:
        os.close(directory)
        raise


def atomic_json(path: Path, value: dict, mode: int = 0o600) -> None:
    """原子保存受限 JSON。

    :param path: 目标路径。
    :param value: JSON 对象。
    :param mode: 文件权限。
    :return: None。
    """
    atomic_text(path, json.dumps(value, ensure_ascii=False), mode)


def atomic_text(path: Path, value: str, mode: int = 0o600) -> None:
    """通过受控目录 fd 原子保存文本，供 JSON 和只读画像共同使用。

    :param path: 目标文件。
    :param value: 完整 UTF-8 文本。
    :param mode: 文件权限。
    :return: None。
    """
    directory = directory_fd(path.parent, create=True)
    temporary = path.name + '.' + uuid.uuid4().hex
    try:
        # 目录逐级以 fd 固定；不能先检查链接、随后再沿可被业务进程替换的路径写入。
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
            mode, dir_fd=directory)
        with os.fdopen(descriptor, 'w') as output:
            os.fchmod(output.fileno(), mode)
            output.write(value)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path.name, src_dir_fd=directory, dst_dir_fd=directory)
        os.fsync(directory)
    finally:
        try:
            os.unlink(temporary, dir_fd=directory)
        except FileNotFoundError:
            pass
        finally:
            os.close(directory)
