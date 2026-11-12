#!/usr/local/bin/python3
"""将sender私有JSONL协议转入本账号受限加载器，不改业务TLS。"""
import argparse
import json
import os
import select
import socket
import sys

SOCKET_PATH = '/run/ccrb-observer/control.sock'


def main() -> None:
    """转发固定参数和有界字节流；stdin关闭立即撤销。@return None。"""
    parser = argparse.ArgumentParser()
    parser.add_argument('--pid', type=int, required=True)
    parser.add_argument('--worker', required=True)
    parser.add_argument('--capture', required=True)
    parser.add_argument('--image', required=True)
    args = parser.parse_args()
    try:
        with socket.socket(socket.AF_UNIX) as connection:
            connection.connect(SOCKET_PATH)
            connection.sendall(json.dumps(vars(args)).encode() + b'\n')
            while True:
                readable, _, _ = select.select([connection, sys.stdin.buffer], [], [])
                if sys.stdin.buffer in readable:
                    data = os.read(sys.stdin.fileno(), 4096)
                    if not data:
                        return
                    connection.sendall(data)
                if connection in readable:
                    data = connection.recv(65536)
                    if not data:
                        return
                    sys.stdout.buffer.write(data)
                    sys.stdout.buffer.flush()
    except (OSError, ValueError):
        print(json.dumps({'schema_version': 1, 'capture_id': args.capture,
            'worker_id': args.worker, 'reason': 'OBSERVER_BROKER_UNAVAILABLE'}), flush=True)


if __name__ == '__main__':
    main()
