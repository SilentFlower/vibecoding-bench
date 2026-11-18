#!/usr/bin/env python3
"""账号worker只向原作业root端点提交输入，响应丢失时只查询原操作。"""
from __future__ import annotations

import argparse
import json
import socket
import struct
import sys
import time
import uuid


INPUT_LIMIT = 256 * 1024


def exchange(path: str, payload: dict) -> dict:
    """通过受保护UNIX端点收取有界回执。

    :param path: 原root控制目录中的socket。
    :param payload: 该次发送或原操作查询。
    :return: root侧回执。
    """
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as stream:
        stream.settimeout(30)
        stream.connect(path)
        _, uid, _ = struct.unpack('3i', stream.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12))
        if uid != 0:
            raise ValueError('节点输入端点身份无效')
        stream.sendall(json.dumps(payload, ensure_ascii=False, separators=(',', ':')).encode())
        stream.shutdown(socket.SHUT_WR)
        raw, deadline = bytearray(), time.monotonic() + 30
        while True:
            chunk = stream.recv(min(4096, 16385 - len(raw)))
            if not chunk:
                break
            raw.extend(chunk)
            if len(raw) > 16384 or time.monotonic() >= deadline:
                raise ValueError('节点输入回执超限或超时')
        result = json.loads(raw)
        if not isinstance(result, dict):
            raise ValueError('节点输入回执格式无效')
        return result


def send(path: str, operation_id: str, text: str, keys: list[str], submit: bool) -> dict:
    """投递一次原输入，失去响应只读同operation回执。

    :param path: 原作业固定端点。
    :param operation_id: 本次输入独立标识。
    :param text: 原样正文。
    :param keys: 原受限按键。
    :param submit: 是否追加Enter。
    :return: 原匹配回执。
    """
    payload = {'action': 'send', 'operation_id': operation_id, 'text': text, 'keys': keys, 'submit': submit}
    try:
        result = exchange(path, payload)
    except (OSError, ValueError):
        result = exchange(path, {'action': 'query', 'operation_id': operation_id})
    if result.get('operation_id') != operation_id or result.get('status') not in ('sent', 'not_sent', 'unknown'):
        raise ValueError('节点输入回执等待核对')
    return result


def main(argv=None) -> int:
    """读取stdin正文并输出脱敏原输入定位。

    :param argv: 原worker提供的固定socket、按键和提交选项。
    :return: 0为已确认发送，45为回执待核对。
    """
    parser = argparse.ArgumentParser(description='节点worker原作业输入')
    parser.add_argument('--socket', required=True)
    parser.add_argument('--operation')
    parser.add_argument('--submit', action='store_true')
    parser.add_argument('--keys', nargs='*', default=[])
    arguments = parser.parse_args(argv)
    operation_id = arguments.operation or uuid.uuid4().hex
    try:
        raw = sys.stdin.buffer.read(INPUT_LIMIT + 1)
        if len(raw) > INPUT_LIMIT:
            raise ValueError('节点worker输入正文超限')
        result = send(arguments.socket, operation_id, raw.decode(), arguments.keys, arguments.submit)
        status = result['status']
    except (OSError, ValueError):
        status = 'unknown'
    print(json.dumps({'operation_id': operation_id, 'status': status}, separators=(',', ':')))
    return 0 if status == 'sent' else 45


if __name__ == '__main__':
    raise SystemExit(main())
