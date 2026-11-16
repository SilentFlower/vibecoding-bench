"""隔离实验的有界帧读取器。"""
import json
import os
import select
import time


def frame(descriptor, timeout=20):
    """有界读取一条私有JSONL帧。@param descriptor 文件描述符。@param timeout 秒。@return 解码帧。"""
    deadline = time.monotonic() + timeout
    content = bytearray()
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0 or not select.select([descriptor], [], [], remaining)[0]:
            raise TimeoutError('私有帧等待超时')
        value = os.read(descriptor, 1)
        if not value:
            raise EOFError('私有管道关闭')
        if value == b'\n':
            return json.loads(content)
        content.extend(value)
        if len(content) > 4 * 1024 * 1024:
            raise ValueError('研究帧超出预算')
