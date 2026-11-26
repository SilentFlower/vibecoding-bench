"""供客户端工具验收复用的 Linux 文件访问计数。"""

from ctypes import CDLL, get_errno
import os
from select import select
from struct import unpack_from


def monitor_read(stack, path):
    """准备独立 Linux inotify 文件读取计数。@param stack 生命周期。@param path 私有夹具。@return 文件描述符。"""
    libc = CDLL("libc.so.6", use_errno=True)
    descriptor = libc.inotify_init1(os.O_CLOEXEC | os.O_NONBLOCK)
    if descriptor < 0:
        raise OSError(get_errno(), "inotify_init1")
    stack.callback(os.close, descriptor)
    if libc.inotify_add_watch(descriptor, os.fsencode(path), 0x20 | 0x01 | 0x10) < 0:
        raise OSError(get_errno(), "inotify_add_watch")
    return descriptor


def read_counts(descriptor):
    """读取单个夹具的内核打开、读、关闭记录。@param descriptor 监控。@return 事件掩码。"""
    if not select([descriptor], [], [], 2)[0]:
        return []
    raw = os.read(descriptor, 65536)
    result, offset = [], 0
    while offset < len(raw):
        _, mask, _, length = unpack_from("iIII", raw, offset)
        result.append(mask)
        offset += 16 + length
    return result
