"""账号恢复器的固定控制合同及私有文件边界。"""
import array
import asyncio
import json
import os
from pathlib import Path
import re
import socket
import stat
from uuid import UUID

PROTOCOL = 1
MESSAGE_LIMIT = 4096


def canonical_uuid(value: object) -> bool:
    """检查标准实例标识。@param value 待校验值。@return 是否规范UUID。"""
    try:
        return isinstance(value, str) and str(UUID(value)) == value
    except ValueError:
        return False


def command(value: object) -> dict:
    """严格解析控制消息。@param value 未信任JSON。@return 白名单命令。"""
    fields = {'template': {'type', 'key', 'template', 'worker', 'pid'},
              'restore': {'type', 'key', 'template', 'worker', 'nonce'}}
    if (not isinstance(value, dict) or not isinstance(value.get('type'), str)
            or value['type'] not in fields or set(value) != fields[value['type']]):
        raise ValueError('RESTORE_COMMAND_INVALID')
    if (not isinstance(value['key'], str) or not re.fullmatch('[0-9a-f]{64}', value['key'])
            or not canonical_uuid(value['template']) or not canonical_uuid(value['worker'])):
        raise ValueError('RESTORE_COMMAND_INVALID')
    if value['type'] == 'template':
        if type(value['pid']) is not int or not 1 < value['pid'] < 2**31:
            raise ValueError('RESTORE_COMMAND_INVALID')
    elif not isinstance(value['nonce'], str) or not re.fullmatch('[0-9a-f]{64}', value['nonce']):
        raise ValueError('RESTORE_COMMAND_INVALID')
    return value


async def receive(connection: socket.socket) -> dict:
    """读取单帧有界控制消息。@param connection 私有连接。@return JSON对象。"""
    content = bytearray()
    loop = asyncio.get_running_loop()
    # 控制面只传少量元数据；逐字节避免吞掉后一阶段ACK或描述符。
    while len(content) < MESSAGE_LIMIT:
        data = await loop.sock_recv(connection, 1)
        if not data:
            raise ValueError('RESTORE_CONNECTION_CLOSED')
        content.extend(data)
        if data == b'\n':
            result = json.loads(content)
            if not isinstance(result, dict):
                raise ValueError('RESTORE_COMMAND_INVALID')
            return result
    raise ValueError('RESTORE_COMMAND_LIMIT')


async def send(connection: socket.socket, value: dict, descriptors: tuple[int, ...] = ()) -> None:
    """移交受控FD并发送元数据。@param connection 已鉴权连接。@param value 安全元数据。@param descriptors 本组件拥有的FD。@return 无。"""
    if descriptors:
        # 每阶段单独发送一个标志字节，接收方先接管FD再读取JSON，避免流边界歧义。
        payload = [(socket.SOL_SOCKET, socket.SCM_RIGHTS, array.array('i', descriptors))]
        if connection.sendmsg([b'F'], payload, socket.MSG_NOSIGNAL) != 1:
            raise ValueError('RESTORE_FD_HANDOFF')
    await asyncio.get_running_loop().sock_sendall(connection, json.dumps(value, separators=(',', ':')).encode() + b'\n')


def freeze_tree(source: Path, destination: Path, owner: int) -> dict:
    """复制受限种子的普通文件，拒绝链接与设备。@param source 已核验源目录。@param destination 本轮新目录。@param owner 期望源UID。@return 恢复副本需要重建的相对文件元数据。"""
    budget = [0, 0]
    metadata = {}

    def remember(descriptor: int, relative: str) -> os.stat_result:
        """冻结源权限与时间。@param descriptor 已持有FD。@param relative 内部相对路径。@return 实际stat。"""
        info = os.fstat(descriptor)
        if info.st_uid != owner or info.st_mode & 0o7000:
            raise ValueError('RESTORE_DIRECTORY_OWNER')
        metadata[relative] = {'mode': info.st_mode & 0o777, 'gid': info.st_gid,
            'atime_ns': info.st_atime_ns, 'mtime_ns': info.st_mtime_ns}
        return info

    def copy(directory: int, target: Path, relative: str) -> None:
        """通过持有的目录FD复制。@param directory 源目录。@param target 新目标。@param relative 内部相对路径。@return 无。"""
        target.mkdir(mode=0o700)
        for name in os.listdir(directory):
            budget[0] += 1
            if budget[0] > 256:
                raise ValueError('RESTORE_DIRECTORY_LIMIT')
            descriptor = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK, dir_fd=directory)
            try:
                child = str(Path(relative) / name)
                info = remember(descriptor, child)
                if stat.S_ISDIR(info.st_mode):
                    copy(descriptor, target / name, child)
                elif stat.S_ISREG(info.st_mode) and info.st_nlink == 1:
                    budget[1] += info.st_size
                    if budget[1] > 16 * 1024 * 1024:
                        raise ValueError('RESTORE_DIRECTORY_LIMIT')
                    with (target / name).open('xb') as output:
                        os.chmod(target / name, 0o600)
                        remaining = info.st_size
                        while remaining:
                            data = os.read(descriptor, min(65536, remaining))
                            if not data:
                                raise ValueError('RESTORE_DIRECTORY_CHANGED')
                            output.write(data)
                            remaining -= len(data)
                        if os.read(descriptor, 1):
                            raise ValueError('RESTORE_DIRECTORY_CHANGED')
                else:
                    raise ValueError('RESTORE_DIRECTORY_TYPE')
            finally:
                os.close(descriptor)

    descriptor = os.open(source, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        remember(descriptor, '.')
        copy(descriptor, destination, '.')
        return metadata
    finally:
        os.close(descriptor)
