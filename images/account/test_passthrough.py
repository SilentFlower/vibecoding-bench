"""raw SOCKS passthrough relay 的协议与字节保真测试。"""
import asyncio
import base64
import os
import socket
import unittest
from unittest.mock import patch

from passthrough import ProxyConfig, handle_client


async def _open_relay(config: ProxyConfig, idle_timeout: float = 300):
    """
    启动测试 relay。

    :param config: 上游代理配置
    :param idle_timeout: 测试 relay 的共享空闲秒数
    :return: server 与监听端口
    """
    server = await asyncio.start_server(
        lambda reader, writer: handle_client(reader, writer, config, idle_timeout), "127.0.0.1", 0
    )
    return server, server.sockets[0].getsockname()[1]


async def _socks_client(port: int, target: str = "api.anthropic.com", target_port: int = 443):
    """
    完成本地 SOCKS5 CONNECT。

    :param port: relay 监听端口
    :param target: 目标域名
    :param target_port: 目标端口
    :return: 已连接的输入输出流及 SOCKS 状态
    """
    reader, writer = await asyncio.open_connection("127.0.0.1", port)
    writer.write(b"\x05\x01\x00")
    await writer.drain()
    if await reader.readexactly(2) != b"\x05\x00":
        raise AssertionError("relay 拒绝无认证客户端")
    encoded = target.encode()
    writer.write(b"\x05\x01\x00\x03" + bytes((len(encoded),)) + encoded + target_port.to_bytes(2, "big"))
    await writer.drain()
    reply = await reader.readexactly(10)
    return reader, writer, reply[1]


class PassthroughRelayTests(unittest.IsolatedAsyncioTestCase):
    """验证 HTTP/SOCKS 上游和失败关闭。"""

    async def test_http_connect_preserves_raw_tls_bytes(self) -> None:
        """HTTP CONNECT 后不得改写任意 TLS 字节。@return None。"""
        payload = b"\x16\x03\x01\x00\x0bsynthetic-client-hello"
        observed = {}

        async def proxy(reader, writer):
            """记录 CONNECT 和后续原始字节。"""
            header = await reader.readuntil(b"\r\n\r\n")
            observed["header"] = header
            writer.write(b"HTTP/1.1 200 Connection Established\r\n\r\n")
            await writer.drain()
            observed["payload"] = await reader.readexactly(len(payload))
            writer.write(observed["payload"])
            await writer.drain()
            writer.close()

        upstream = await asyncio.start_server(proxy, "127.0.0.1", 0)
        upstream_port = upstream.sockets[0].getsockname()[1]
        relay, relay_port = await _open_relay(ProxyConfig("http", "127.0.0.1", upstream_port, "user", "pass"))
        try:
            reader, writer, status = await _socks_client(relay_port)
            self.assertEqual(0, status)
            writer.write(payload)
            await writer.drain()
            self.assertEqual(payload, await reader.readexactly(len(payload)))
            writer.close()
            await writer.wait_closed()
        finally:
            relay.close()
            upstream.close()
            await relay.wait_closed()
            await upstream.wait_closed()
        self.assertEqual(payload, observed["payload"])
        self.assertIn(b"CONNECT api.anthropic.com:443 HTTP/1.1", observed["header"])
        expected = base64.b64encode(b"user:pass")
        self.assertIn(b"Proxy-Authorization: Basic " + expected, observed["header"])

    async def test_socks5_auth_preserves_raw_bytes(self) -> None:
        """SOCKS5 用户名密码链路必须保持应用字节不变。@return None。"""
        payload = b"native-tls-record"
        observed = {}

        async def proxy(reader, writer):
            """模拟带认证的 SOCKS5 上游。"""
            version, count = await reader.readexactly(2)
            methods = await reader.readexactly(count)
            self.assertEqual((5, b"\x00\x02"), (version, methods))
            writer.write(b"\x05\x02")
            await writer.drain()
            self.assertEqual(1, (await reader.readexactly(1))[0])
            username = await reader.readexactly((await reader.readexactly(1))[0])
            password = await reader.readexactly((await reader.readexactly(1))[0])
            observed["auth"] = (username, password)
            writer.write(b"\x01\x00")
            await writer.drain()
            version, command, _, address_type = await reader.readexactly(4)
            self.assertEqual((5, 1, 3), (version, command, address_type))
            host = await reader.readexactly((await reader.readexactly(1))[0])
            port = int.from_bytes(await reader.readexactly(2), "big")
            observed["target"] = (host, port)
            writer.write(b"\x05\x00\x00\x01\x00\x00\x00\x00\x00\x00")
            await writer.drain()
            observed["payload"] = await reader.readexactly(len(payload))
            writer.write(observed["payload"])
            await writer.drain()
            writer.close()

        upstream = await asyncio.start_server(proxy, "127.0.0.1", 0)
        upstream_port = upstream.sockets[0].getsockname()[1]
        relay, relay_port = await _open_relay(ProxyConfig("socks5h", "127.0.0.1", upstream_port, "alice", "secret"))
        try:
            reader, writer, status = await _socks_client(relay_port)
            self.assertEqual(0, status)
            writer.write(payload)
            await writer.drain()
            self.assertEqual(payload, await reader.readexactly(len(payload)))
            writer.close()
            await writer.wait_closed()
        finally:
            relay.close()
            upstream.close()
            await relay.wait_closed()
            await upstream.wait_closed()
        self.assertEqual((b"alice", b"secret"), observed["auth"])
        self.assertEqual((b"api.anthropic.com", 443), observed["target"])
        self.assertEqual(payload, observed["payload"])

    async def test_proxy_failure_does_not_fall_back_to_direct(self) -> None:
        """上游代理不可达时必须返回 SOCKS 失败。@return None。"""
        probe = socket.socket()
        probe.bind(("127.0.0.1", 0))
        unavailable_port = probe.getsockname()[1]
        probe.close()
        relay, relay_port = await _open_relay(ProxyConfig("http", "127.0.0.1", unavailable_port))
        try:
            _, writer, status = await _socks_client(relay_port)
            self.assertNotEqual(0, status)
            writer.close()
            await writer.wait_closed()
        finally:
            relay.close()
            await relay.wait_closed()

    async def test_idle_tunnel_closes_without_corrupting_payload(self) -> None:
        """双方持续静默时 relay 应在空闲期限后关闭隧道。@return None。"""
        connected = asyncio.Event()

        async def proxy(reader, writer):
            """建立 CONNECT 后保持静默，等待 relay 主动收口。"""
            await reader.readuntil(b"\r\n\r\n")
            writer.write(b"HTTP/1.1 200 Connection Established\r\n\r\n")
            await writer.drain()
            connected.set()
            await reader.read()
            writer.close()

        upstream = await asyncio.start_server(proxy, "127.0.0.1", 0)
        upstream_port = upstream.sockets[0].getsockname()[1]
        relay, relay_port = await _open_relay(
            ProxyConfig("http", "127.0.0.1", upstream_port),
            idle_timeout=0.05,
        )
        try:
            reader, writer, status = await _socks_client(relay_port)
            self.assertEqual(0, status)
            await asyncio.wait_for(connected.wait(), timeout=1)
            self.assertEqual(b"", await asyncio.wait_for(reader.read(), timeout=1))
            writer.close()
            await writer.wait_closed()
        finally:
            relay.close()
            upstream.close()
            await relay.wait_closed()
            await upstream.wait_closed()

    async def test_one_way_activity_resets_shared_idle_timeout(self) -> None:
        """单向持续发送跨越原超时窗口时不得误断连接。@return None。"""
        async def proxy(reader, writer):
            """建立 CONNECT 后逐块回显，模拟长时间单向请求流。"""
            await reader.readuntil(b"\r\n\r\n")
            writer.write(b"HTTP/1.1 200 Connection Established\r\n\r\n")
            await writer.drain()
            while chunk := await reader.read(4096):
                writer.write(chunk)
                await writer.drain()
            writer.close()

        upstream = await asyncio.start_server(proxy, "127.0.0.1", 0)
        upstream_port = upstream.sockets[0].getsockname()[1]
        relay, relay_port = await _open_relay(
            ProxyConfig("http", "127.0.0.1", upstream_port),
            idle_timeout=0.05,
        )
        try:
            reader, writer, status = await _socks_client(relay_port)
            self.assertEqual(0, status)
            for index in range(4):
                payload = f"chunk-{index}".encode()
                writer.write(payload)
                await writer.drain()
                self.assertEqual(payload, await asyncio.wait_for(reader.readexactly(len(payload)), timeout=1))
                await asyncio.sleep(0.03)
            writer.close()
            await writer.wait_closed()
        finally:
            relay.close()
            upstream.close()
            await relay.wait_closed()
            await upstream.wait_closed()

    def test_environment_requires_configured_proxy(self) -> None:
        """生产环境缺代理时应在监听前失败。@return None。"""
        with patch.dict(os.environ, {
            "UPSTREAM_PROXY_SCHEME": "http",
            "UPSTREAM_SOCKS5_HOST": "",
            "UPSTREAM_SOCKS5_PORT": "8080",
        }, clear=False):
            with self.assertRaisesRegex(RuntimeError, "拒绝直连"):
                ProxyConfig.from_environment()


if __name__ == "__main__":
    unittest.main()
