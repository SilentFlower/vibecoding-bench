#!/usr/bin/env python3
"""把本地 SOCKS5 CONNECT 原样转发到账号 HTTP/SOCKS 代理。"""
from __future__ import annotations

import asyncio
import base64
import ipaddress
import os
import signal
import socket
import time
from dataclasses import dataclass


_SOCKS_VERSION = 5
_CONNECT = 1
_IPV4 = 1
_DOMAIN = 3
_IPV6 = 4
_SUCCEEDED = 0
_GENERAL_FAILURE = 1
_COMMAND_UNSUPPORTED = 7
_ADDRESS_UNSUPPORTED = 8
_MAX_HTTP_HEADER = 16 * 1024
_DEFAULT_IDLE_TIMEOUT = 300.0


class RelayError(RuntimeError):
    """表示代理握手或协议校验失败。"""


@dataclass(frozen=True)
class ProxyConfig:
    """
    passthrough 上游代理配置。

    :param scheme: `http`、`socks5` 或 `socks5h`
    :param host: 上游代理主机
    :param port: 上游代理端口
    :param username: 可选用户名
    :param password: 可选密码
    """

    scheme: str
    host: str
    port: int
    username: str = ""
    password: str = ""

    @classmethod
    def from_environment(cls) -> "ProxyConfig":
        """
        从账号容器环境读取代理配置。

        :return: 经过严格校验的代理配置
        """
        scheme = os.environ.get("UPSTREAM_PROXY_SCHEME", "socks5").strip().lower()
        host = os.environ.get("UPSTREAM_SOCKS5_HOST", "").strip()
        port_text = os.environ.get("UPSTREAM_SOCKS5_PORT", "1080").strip()
        if scheme not in ("http", "socks5", "socks5h"):
            raise RelayError("不支持的上游代理协议")
        if not host:
            raise RelayError("上游代理主机为空，拒绝直连")
        try:
            port = int(port_text)
        except ValueError as error:
            raise RelayError("上游代理端口无效") from error
        if not 1 <= port <= 65535:
            raise RelayError("上游代理端口超出范围")
        return cls(
            scheme=scheme,
            host=host,
            port=port,
            username=os.environ.get("UPSTREAM_SOCKS5_USER", ""),
            password=os.environ.get("UPSTREAM_SOCKS5_PASS", ""),
        )


async def _read_socks_address(reader: asyncio.StreamReader, address_type: int) -> str:
    """
    读取 SOCKS 地址字段。

    :param reader: 当前连接输入流
    :param address_type: SOCKS ATYP
    :return: 目标主机字符串
    """
    if address_type == _IPV4:
        return socket.inet_ntop(socket.AF_INET, await reader.readexactly(4))
    if address_type == _IPV6:
        return socket.inet_ntop(socket.AF_INET6, await reader.readexactly(16))
    if address_type == _DOMAIN:
        length = (await reader.readexactly(1))[0]
        if not length:
            raise RelayError("SOCKS 目标域名为空")
        try:
            return (await reader.readexactly(length)).decode("idna")
        except UnicodeError as error:
            raise RelayError("SOCKS 目标域名无效") from error
    raise RelayError("SOCKS 地址类型不受支持")


def _encode_socks_address(host: str) -> bytes:
    """
    编码 SOCKS 地址字段。

    :param host: 目标主机或 IP
    :return: ATYP 与地址字节
    """
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        encoded = host.encode("idna")
        if not encoded or len(encoded) > 255:
            raise RelayError("SOCKS 目标域名长度无效")
        return bytes((_DOMAIN, len(encoded))) + encoded
    if address.version == 4:
        return bytes((_IPV4,)) + address.packed
    return bytes((_IPV6,)) + address.packed


def _http_authority(host: str, port: int) -> str:
    """
    生成 HTTP CONNECT authority。

    :param host: 目标主机
    :param port: 目标端口
    :return: RFC 兼容 authority
    """
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return f"{host}:{port}"
    return f"[{host}]:{port}" if address.version == 6 else f"{host}:{port}"


async def _open_http_proxy(config: ProxyConfig, host: str, port: int) -> tuple[asyncio.StreamReader, asyncio.StreamWriter]:
    """
    通过 HTTP CONNECT 建立原始字节隧道。

    :param config: 上游 HTTP 代理配置
    :param host: 最终目标主机
    :param port: 最终目标端口
    :return: 已完成 CONNECT 的输入输出流
    """
    reader, writer = await asyncio.open_connection(config.host, config.port)
    authority = _http_authority(host, port)
    headers = [f"CONNECT {authority} HTTP/1.1", f"Host: {authority}"]
    if config.username:
        token = base64.b64encode(f"{config.username}:{config.password}".encode()).decode()
        headers.append(f"Proxy-Authorization: Basic {token}")
    writer.write(("\r\n".join(headers) + "\r\n\r\n").encode("ascii"))
    await writer.drain()
    try:
        response = await reader.readuntil(b"\r\n\r\n")
    except asyncio.LimitOverrunError as error:
        writer.close()
        await writer.wait_closed()
        raise RelayError("HTTP 代理响应头过大") from error
    if len(response) > _MAX_HTTP_HEADER:
        writer.close()
        await writer.wait_closed()
        raise RelayError("HTTP 代理响应头过大")
    status_line = response.split(b"\r\n", 1)[0].split()
    if len(status_line) < 2 or status_line[1] != b"200":
        writer.close()
        await writer.wait_closed()
        raise RelayError("HTTP 代理拒绝 CONNECT")
    return reader, writer


async def _open_socks_proxy(config: ProxyConfig, host: str, port: int) -> tuple[asyncio.StreamReader, asyncio.StreamWriter]:
    """
    通过 SOCKS5 上游建立原始字节隧道。

    :param config: 上游 SOCKS 配置
    :param host: 最终目标主机
    :param port: 最终目标端口
    :return: 已完成 CONNECT 的输入输出流
    """
    reader, writer = await asyncio.open_connection(config.host, config.port)
    methods = b"\x00\x02" if config.username else b"\x00"
    writer.write(bytes((_SOCKS_VERSION, len(methods))) + methods)
    await writer.drain()
    version, method = await reader.readexactly(2)
    if version != _SOCKS_VERSION or method == 0xFF:
        writer.close()
        await writer.wait_closed()
        raise RelayError("SOCKS 上游认证方式不兼容")
    if method == 2:
        username = config.username.encode()
        password = config.password.encode()
        if not username or len(username) > 255 or len(password) > 255:
            writer.close()
            await writer.wait_closed()
            raise RelayError("SOCKS 上游认证字段长度无效")
        writer.write(bytes((1, len(username))) + username + bytes((len(password),)) + password)
        await writer.drain()
        if await reader.readexactly(2) != b"\x01\x00":
            writer.close()
            await writer.wait_closed()
            raise RelayError("SOCKS 上游认证失败")
    elif method != 0:
        writer.close()
        await writer.wait_closed()
        raise RelayError("SOCKS 上游选择了未知认证方式")
    writer.write(bytes((_SOCKS_VERSION, _CONNECT, 0)) + _encode_socks_address(host) + port.to_bytes(2, "big"))
    await writer.drain()
    version, status, _, address_type = await reader.readexactly(4)
    if version != _SOCKS_VERSION or status != _SUCCEEDED:
        writer.close()
        await writer.wait_closed()
        raise RelayError("SOCKS 上游拒绝 CONNECT")
    await _read_socks_address(reader, address_type)
    await reader.readexactly(2)
    return reader, writer


async def open_upstream(config: ProxyConfig, host: str, port: int) -> tuple[asyncio.StreamReader, asyncio.StreamWriter]:
    """
    按配置建立上游代理隧道。

    :param config: 账号代理配置
    :param host: 最终目标主机
    :param port: 最终目标端口
    :return: 已完成代理握手的输入输出流
    """
    if config.scheme == "http":
        return await _open_http_proxy(config, host, port)
    return await _open_socks_proxy(config, host, port)


async def _copy_stream(
    reader: asyncio.StreamReader,
    writer: asyncio.StreamWriter,
    activity: list[float],
) -> None:
    """
    原样复制单向字节流并传播半关闭。

    :param reader: 来源流
    :param writer: 目标流
    :param activity: 两个方向共享的最近活动时刻
    :return: None
    """
    try:
        while chunk := await reader.read(64 * 1024):
            activity[0] = time.monotonic()
            writer.write(chunk)
            await writer.drain()
        if writer.can_write_eof():
            writer.write_eof()
            await writer.drain()
    except (ConnectionError, asyncio.CancelledError):
        return


async def relay_streams(
    client_reader: asyncio.StreamReader,
    client_writer: asyncio.StreamWriter,
    upstream_reader: asyncio.StreamReader,
    upstream_writer: asyncio.StreamWriter,
    idle_timeout: float = _DEFAULT_IDLE_TIMEOUT,
) -> None:
    """
    双向复制连接且在任一方向结束后安全收口。

    :param client_reader: SOCKS 客户端输入
    :param client_writer: SOCKS 客户端输出
    :param upstream_reader: 上游代理输入
    :param upstream_writer: 上游代理输出
    :param idle_timeout: 任一方向均无字节活动的最长秒数
    :return: None
    """
    activity = [time.monotonic()]
    tasks = {
        asyncio.create_task(_copy_stream(client_reader, upstream_writer, activity)),
        asyncio.create_task(_copy_stream(upstream_reader, client_writer, activity)),
    }
    try:
        while tasks:
            remaining = idle_timeout - (time.monotonic() - activity[0])
            if remaining <= 0:
                break
            done, tasks = await asyncio.wait(
                tasks,
                timeout=remaining,
                return_when=asyncio.FIRST_COMPLETED,
            )
            if not done:
                # 等待期间另一协程可能已转发新字节；重新计算共享活动时间，
                # 只有下一轮确认整个窗口都静默时才关闭隧道。
                continue
            await asyncio.gather(*done)
    finally:
        for task in tasks:
            task.cancel()
        upstream_writer.close()
        client_writer.close()
        await asyncio.gather(upstream_writer.wait_closed(), client_writer.wait_closed(), return_exceptions=True)


async def handle_client(
    reader: asyncio.StreamReader,
    writer: asyncio.StreamWriter,
    config: ProxyConfig,
    idle_timeout: float = _DEFAULT_IDLE_TIMEOUT,
) -> None:
    """
    处理一个本地 SOCKS5 CONNECT 请求。

    :param reader: 本地 SOCKS 客户端输入
    :param writer: 本地 SOCKS 客户端输出
    :param config: 固定账号上游代理配置
    :param idle_timeout: 建立隧道后的双向共享空闲秒数
    :return: None
    """
    upstream_writer = None
    try:
        version, count = await asyncio.wait_for(reader.readexactly(2), timeout=15)
        methods = await asyncio.wait_for(reader.readexactly(count), timeout=15)
        if version != _SOCKS_VERSION or 0 not in methods:
            writer.write(b"\x05\xff")
            await writer.drain()
            return
        writer.write(b"\x05\x00")
        await writer.drain()
        version, command, _, address_type = await asyncio.wait_for(reader.readexactly(4), timeout=15)
        if version != _SOCKS_VERSION or command != _CONNECT:
            writer.write(bytes((_SOCKS_VERSION, _COMMAND_UNSUPPORTED, 0, _IPV4, 0, 0, 0, 0, 0, 0)))
            await writer.drain()
            return
        host = await asyncio.wait_for(_read_socks_address(reader, address_type), timeout=15)
        port = int.from_bytes(await asyncio.wait_for(reader.readexactly(2), timeout=15), "big")
        if not port:
            raise RelayError("SOCKS 目标端口无效")
        upstream_reader, upstream_writer = await asyncio.wait_for(open_upstream(config, host, port), timeout=20)
        writer.write(bytes((_SOCKS_VERSION, _SUCCEEDED, 0, _IPV4, 0, 0, 0, 0, 0, 0)))
        await writer.drain()
        await relay_streams(reader, writer, upstream_reader, upstream_writer, idle_timeout)
        return
    except (RelayError, OSError, asyncio.IncompleteReadError, asyncio.TimeoutError):
        try:
            writer.write(bytes((_SOCKS_VERSION, _GENERAL_FAILURE, 0, _IPV4, 0, 0, 0, 0, 0, 0)))
            await writer.drain()
        except (ConnectionError, OSError):
            pass
    finally:
        if upstream_writer is not None:
            upstream_writer.close()
            await asyncio.gather(upstream_writer.wait_closed(), return_exceptions=True)
        writer.close()
        await asyncio.gather(writer.wait_closed(), return_exceptions=True)


async def serve(config: ProxyConfig, host: str = "127.0.0.1", port: int = 8080) -> None:
    """
    启动 passthrough SOCKS 服务并等待退出信号。

    :param config: 固定上游代理配置
    :param host: 本地监听地址
    :param port: 本地监听端口
    :return: None
    """
    try:
        idle_timeout = float(os.environ.get("V3_PASSTHROUGH_IDLE_TIMEOUT_SEC", str(_DEFAULT_IDLE_TIMEOUT)))
    except ValueError as error:
        raise RelayError("passthrough 空闲超时无效") from error
    if not 1 <= idle_timeout <= 3600:
        raise RelayError("passthrough 空闲超时超出范围")
    server = await asyncio.start_server(
        lambda reader, writer: handle_client(reader, writer, config, idle_timeout),
        host,
        port,
    )
    stopping = asyncio.Event()
    loop = asyncio.get_running_loop()
    for signum in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(signum, stopping.set)
    async with server:
        await stopping.wait()


def main() -> None:
    """
    从环境启动 passthrough 服务。

    :return: None
    """
    asyncio.run(serve(ProxyConfig.from_environment()))


if __name__ == "__main__":
    main()
