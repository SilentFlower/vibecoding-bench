"""读节点管理员发布的 Claude CLI 直发账号与环境绑定。"""

from collections.abc import Iterator
from contextlib import ExitStack, contextmanager
import json
import os
from pathlib import Path
import re
from stat import S_ISDIR, S_ISREG

from runtime_files import directory_fd


DIRECT_DIRECTORY = 'tui-direct'
DIRECT_ACCOUNT_PATH = '/run/flower/tui-direct'
MULTI_SELECTION_LABEL = 'vibebench.tui-direct-selection'
MULTI_SELECTION_VERSION = 'multi-v1'
ACCOUNTS = 'accounts'
LEGACY_ACCOUNT = 'account.json'
# 沿用现有节点选择文件的读取上限。
_MAX_RECORD_BYTES = 128 * 1024
_SENDER_GID = 1001


def account_binding(account_id: int, environment_id: str) -> tuple[int, str]:
    """校验选择器身份。@param account_id 网关账号。@param environment_id 当前环境。@return 严格绑定。"""
    if (type(account_id) is not int or not 0 < account_id < 2**63
            or not isinstance(environment_id, str) or not re.fullmatch(r'[a-f0-9]{32}', environment_id)):
        raise ValueError('直发开关须指定一个现有账号及其固定环境')
    return account_id, environment_id


def _verify_access(info, *, directory: bool) -> None:
    access = 0o5 if directory else 0o4
    readable = info.st_mode & access == access or (info.st_gid == _SENDER_GID and (info.st_mode >> 3) & access == access)
    valid_type = S_ISDIR(info.st_mode) if directory else S_ISREG(info.st_mode) and info.st_nlink == 1
    if not valid_type or not readable or info.st_uid != 0 or info.st_mode & 0o022:
        raise ValueError('直发开关须由部署管理员发布并允许 sender 只读访问')


@contextmanager
def selector_directory(path: Path, *, parent: int | None = None) -> Iterator[int]:
    """固定管理员目录。@param path 绝对目录或受控子目录名。@param parent 已打开父级。@return 目录描述符。"""
    fd = (directory_fd(path) if parent is None else
          os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent))
    try:
        _verify_access(os.fstat(fd), directory=True)
        yield fd
    finally:
        os.close(fd)


def _unique_fields(pairs):
    value = dict(pairs)
    if len(value) != len(pairs):
        raise ValueError('直发开关包含重复字段')
    return value


def _invalid_number(_):
    raise ValueError('直发开关包含非法数值')


def read_binding(directory: int, name: str) -> tuple[int, str] | None:
    """读单条选择记录。@param directory 已核验目录描述符。@param name 受控文件名。@return 已登记绑定或缺失。"""
    try:
        fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
    except FileNotFoundError:
        return None
    with os.fdopen(fd, 'rb') as source:
        _verify_access(os.fstat(source.fileno()), directory=False)
        raw = source.read(_MAX_RECORD_BYTES + 1)
    if len(raw) > _MAX_RECORD_BYTES:
        raise ValueError('直发开关超过原读取上限')
    try:
        value = json.loads(raw, object_pairs_hook=_unique_fields, parse_constant=_invalid_number)
    except (UnicodeError, RecursionError, json.JSONDecodeError) as error:
        raise ValueError('直发开关不是完整 JSON 对象') from error
    if not isinstance(value, dict):
        raise ValueError('直发开关不是完整 JSON 对象')
    return account_binding(value.get('account_id'), value.get('environment_id'))


def selector_matches(directory: Path, *, account_id: int | None, environment_id: str,
                     supports_multiple: bool = True) -> bool:
    """按当前账号读取同节点的一条记录。@param directory 节点只读选择器。@param account_id 网关账号。
    @param environment_id 当前环境。@param supports_multiple 当前账号镜像支持多账号目录。@return 该账号及环境是否开启直发。
    """
    if account_id is None:
        return False
    expected = account_binding(account_id, environment_id)
    multiple = False
    try:
        with selector_directory(directory) as root, ExitStack() as stack:
            try:
                accounts = stack.enter_context(selector_directory(Path(ACCOUNTS), parent=root))
            except FileNotFoundError:
                chosen = read_binding(root, LEGACY_ACCOUNT)
            else:
                multiple = True
                chosen = read_binding(accounts, f'{account_id}.json')
                if chosen is not None and chosen[0] != account_id:
                    raise ValueError('账号直发开关的文件名和绑定不符')
    except FileNotFoundError:
        return False
    # 多账号目录存在时，撤销一条记录不能重新启用同账号的历史单选文件。
    if chosen is None or chosen[0] != account_id:
        return False
    if chosen != expected:
        raise ValueError('直发开关的目标账号环境已变化')
    if multiple and not supports_multiple:
        raise ValueError('多账号直发需要支持该选择器的正式账号镜像')
    return True
