"""仅依赖标准库的本机更新服务 HTTP 连接。"""
from __future__ import annotations

from http.client import HTTPConnection
from pathlib import Path
from socket import AF_UNIX, SOCK_STREAM, socket


class UnixUpdateConnection(HTTPConnection):
    """使用既有 HTTP 编码访问私有 Unix socket。"""

    def __init__(self, path: Path) -> None:
        """保存固定 socket 路径。

        :param path: 首次接入固化的 Unix socket。
        :return: None。
        """
        super().__init__('localhost', timeout=10)
        self.path = path

    def connect(self) -> None:
        """建立有界本机连接。

        :return: None。
        """
        self.sock = socket(AF_UNIX, SOCK_STREAM)
        self.sock.settimeout(self.timeout)
        self.sock.connect(str(self.path))
