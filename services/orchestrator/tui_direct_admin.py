"""节点管理员发布和撤销精确的 Claude 直发选择。"""

import argparse
from contextlib import ExitStack
import fcntl
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory

from runtime_files import atomic_json, directory_fd
from tui_direct_selection import (
    ACCOUNTS, DIRECT_DIRECTORY, LEGACY_ACCOUNT, account_binding, read_binding, selector_directory,
)


def _selector_root(data: Path, publish: bool) -> Path:
    if os.geteuid() != 0:
        raise PermissionError('直发开关须由节点管理员发布')
    fd = directory_fd(data)
    try:
        info = os.fstat(fd)
        if info.st_uid != 0 or info.st_mode & 0o022:
            raise ValueError('节点数据根须由管理员独占写入')
        # 首次创建需要在其它发布者读取权限之前完成。
        fcntl.flock(fd, fcntl.LOCK_EX)
        if publish:
            try:
                os.mkdir(DIRECT_DIRECTORY, mode=0o755, dir_fd=fd)
            except FileExistsError:
                pass
            else:
                # 即使管理员的 umask 较严，此目录仍需对已绑定 sender 只读。
                os.chmod(DIRECT_DIRECTORY, 0o755, dir_fd=fd)
                os.fsync(fd)
    finally:
        os.close(fd)
    return data / DIRECT_DIRECTORY


def _write(path: Path, binding: tuple[int, str]) -> None:
    account_id, environment_id = binding
    atomic_json(path / f'{account_id}.json', {'account_id': account_id, 'environment_id': environment_id}, 0o444)


def _promote_legacy(path: Path, root: int, target: tuple[int, str], publish: bool) -> bool:
    """一次性发布权威目录，原单选绑定随同迁移，撤销时保留目录边界。"""
    legacy = read_binding(root, LEGACY_ACCOUNT)
    if legacy is not None and legacy[0] == target[0] and legacy != target:
        raise ValueError('直发开关的目标账号环境已变化')
    if not publish and legacy != target:
        return False
    with TemporaryDirectory(prefix='.accounts-', dir=path) as temporary:
        stage = Path(temporary)
        if legacy is not None and legacy != target:
            _write(stage, legacy)
        if publish:
            _write(stage, target)
        stage.chmod(0o755)
        with selector_directory(stage) as directory:
            os.fsync(directory)
        os.rename(stage.name, ACCOUNTS, src_dir_fd=root, dst_dir_fd=root)
        os.fsync(root)
    return True


def update_binding(data: Path, *, account_id: int, environment_id: str, publish: bool) -> bool:
    """按原环境绑定发布或撤销单个账号的选择。@param data 节点数据根。@param account_id 网关账号。
    @param environment_id 已核验的环境。@param publish 是否发布。@return 是否改变持久记录。
    """
    target = account_binding(account_id, environment_id)
    path = _selector_root(data, publish)
    with ExitStack() as stack:
        try:
            root = stack.enter_context(selector_directory(path))
        except FileNotFoundError:
            if not publish:
                return False
            raise
        # 同一个节点的首次迁移和账号写入共用稳定目录锁，读者只看原文件或原子替换后的记录。
        fcntl.flock(root, fcntl.LOCK_EX)
        try:
            accounts = stack.enter_context(selector_directory(Path(ACCOUNTS), parent=root))
        except FileNotFoundError:
            return _promote_legacy(path, root, target, publish)
        name = f'{account_id}.json'
        existing = read_binding(accounts, name)
        if existing is not None and existing != target:
            raise ValueError('直发开关的目标账号环境已变化')
        if publish and existing is None:
            _write(path / ACCOUNTS, target)
        elif not publish and existing is not None:
            os.unlink(name, dir_fd=accounts)
            os.fsync(accounts)
        else:
            return False
        return True


def main() -> None:
    """执行节点管理员已经批准的单账号文件操作。@return 无。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-root', required=True, type=Path)
    parser.add_argument('operation', choices=('publish', 'revoke'))
    parser.add_argument('account_id', type=int)
    parser.add_argument('environment_id')
    args = parser.parse_args()
    try:
        changed = update_binding(args.data_root, account_id=args.account_id, environment_id=args.environment_id,
                                 publish=args.operation == 'publish')
    except (OSError, ValueError) as error:
        parser.exit(1, f'{error}\n')
    print(json.dumps({'account_id': args.account_id, 'environment_id': args.environment_id,
                      'operation': args.operation, 'changed': changed}, ensure_ascii=False))


if __name__ == '__main__':
    main()
