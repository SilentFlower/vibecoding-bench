"""在单个隔离账号镜像内验证真实 TLS/HTTP；仅访问回环模拟上游，不启动 CLI。"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import socket
import ssl
import stat
import struct
import subprocess
import sys
import tempfile
import threading
import time
from http.client import HTTPConnection
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from io import BytesIO
from pathlib import Path
from typing import Any

from mitmproxy import tls
from mitmproxy.version import VERSION


class MockHTTPSHandler(BaseHTTPRequestHandler):
    """仅返回固定合成 JSON 的 HTTP/1.1 上游，支持同连接多次请求。"""

    protocol_version = "HTTP/1.1"

    def do_GET(self) -> None:
        """处理合成 GET。:return: None；不读取账号、凭据或项目数据。"""
        body = b'{"synthetic":true}'
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: Any) -> None:
        """禁用原始访问日志。:param format: 日志格式。:param args: 参数。:return: None。"""


def _take(stream: BytesIO, count: int) -> bytes:
    value = stream.read(count)
    if len(value) != count:
        raise AssertionError("独立解析发现截断")
    return value


def _vector(stream: BytesIO, width: int) -> bytes:
    return _take(stream, int.from_bytes(_take(stream, width), "big"))


def _numbers(payload: bytes, prefix: int, width: int) -> list[int]:
    stream = BytesIO(payload)
    content = _vector(stream, prefix)
    assert not stream.read(1), "独立向量存在尾部"
    if width == 2:
        assert len(content) % 2 == 0
        return [value for (value,) in struct.iter_unpack("!H", content)]
    return list(content)


def verify_raw_record(record: dict[str, Any]) -> dict[str, Any]:
    """独立解析已保存本体，同时核对固定 SDK，不调用产品解析器。

    :param record: 新 Collector 保存的一行私有记录。
    :return: 仅含指纹、字节数及公开 offer 的脱敏核对结果。
    """
    assert record["parse_status"] == "ok"
    assert record["raw_format"] == "clienthello_body" and record["tls_record_preserved"] is False
    assert record["direction"] == "client_to_recorder" and record["transport"] == "tcp"
    assert not record["raw_truncated"]
    raw = base64.b64decode(record["raw_base64"], validate=True)
    assert len(raw) == record["raw_bytes"] == record["raw_saved_bytes"]
    assert hashlib.sha256(raw).hexdigest() == record["raw_sha256"]
    stream = BytesIO(raw)
    legacy_version = struct.unpack("!H", _take(stream, 2))[0]
    _take(stream, 32)
    _vector(stream, 1)
    cipher_bytes = _vector(stream, 2)
    ciphers = [value for (value,) in struct.iter_unpack("!H", cipher_bytes)]
    _vector(stream, 1)
    extension_bytes = _vector(stream, 2) if stream.tell() < len(raw) else b""
    assert not stream.read(1)
    extensions = []
    extension_stream = BytesIO(extension_bytes)
    while extension_stream.tell() < len(extension_bytes):
        extensions.append((struct.unpack("!H", _take(extension_stream, 2))[0], _vector(extension_stream, 2)))
    assert legacy_version == record["legacy_version"]
    assert ciphers == record["cipher_suites"]
    assert [kind for kind, _ in extensions] == [item["type"] for item in record["extensions"]]
    assert [payload for _, payload in extensions] == [base64.b64decode(item["data_base64"], validate=True)
                                                    for item in record["extensions"]]
    assert [len(payload) for _, payload in extensions] == [item["length"] for item in record["extensions"]]
    observed: dict[str, Any] = {"signature_algorithms": None, "supported_groups": None,
        "supported_versions": None, "ec_point_formats": None, "key_share": None,
        "sni": None, "alpn_protocols": None}
    for kind, payload in extensions:
        if kind in (10, 11, 13, 43):
            field = {10: "supported_groups", 11: "ec_point_formats", 13: "signature_algorithms",
                     43: "supported_versions"}[kind]
            observed[field] = _numbers(payload, 1 if kind in (11, 43) else 2, 1 if kind == 11 else 2)
        elif kind in (0, 16, 51):
            envelope = BytesIO(payload)
            content = _vector(envelope, 2)
            assert not envelope.read(1)
            inner = BytesIO(content)
            if kind == 51:
                observed["key_share"] = []
                while inner.tell() < len(content):
                    group = struct.unpack("!H", _take(inner, 2))[0]
                    exchange = _vector(inner, 2)
                    observed["key_share"].append({"group": group, "key_exchange_length": len(exchange)})
            elif kind == 0:
                while inner.tell() < len(content):
                    name_type = _take(inner, 1)[0]
                    name = _vector(inner, 2)
                    if name_type == 0:
                        observed["sni"] = name.decode("ascii")
            else:
                observed["alpn_protocols"] = []
                while inner.tell() < len(content):
                    protocol = _vector(inner, 1)
                    observed["alpn_protocols"].append({"text": protocol.decode("ascii")
                        if all(32 <= value <= 126 for value in protocol) else None,
                        "base64": base64.b64encode(protocol).decode("ascii")})
    for field, values in observed.items():
        assert values == record[field], "独立字段不一致：" + field
    sdk = tls.ClientHello(raw)
    assert sdk.raw_bytes(wrap_in_record=False) == raw
    assert sdk.cipher_suites == ciphers and sdk.extensions == extensions
    assert sdk.sni == record["sni"]
    assert sdk.alpn_protocols == [base64.b64decode(item["base64"]) for item in record["alpn_protocols"] or []]

    def nongrease(values: list[int]) -> str:
        """以位模式独立过滤标准 GREASE。:param values: 有序 ID。:return: JA3 字段。"""
        return "-".join(str(value) for value in values
                        if not ((value & 0x0F0F) == 0x0A0A and (value >> 8) == (value & 0xFF)))

    ja3 = ",".join([str(legacy_version), nongrease(ciphers), nongrease([kind for kind, _ in extensions]),
                    nongrease(observed["supported_groups"] or []),
                    "-".join(str(value) for value in observed["ec_point_formats"] or [])])
    assert record["ja3"] == {"string": ja3, "md5": hashlib.md5(ja3.encode(), usedforsecurity=False).hexdigest()}
    return {"raw_bytes": len(raw), "ja3": record["ja3"], "supported_versions": observed["supported_versions"],
            "signature_algorithms": observed["signature_algorithms"], "supported_groups": observed["supported_groups"],
            "key_share": observed["key_share"]}


def _port() -> int:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return listener.getsockname()[1]


def _read_records(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line]


def _wait_ready(process: subprocess.Popen, port: int, certificate: Path) -> None:
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError("隔离 Recorder 启动失败；详情保留在私有验证日志")
        if certificate.exists():
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                    return
            except OSError:
                pass
        time.sleep(0.05)
    raise RuntimeError("隔离 Recorder 未在限定时间内就绪")


def _requests(proxy_port: int, upstream_port: int, ca_file: Path, tls_version: ssl.TLSVersion, label: str) -> dict[str, Any]:
    connection = None
    raw_socket = socket.create_connection(("127.0.0.1", proxy_port), timeout=8)
    try:
        authority = f"localhost:{upstream_port}"
        raw_socket.sendall(f"CONNECT {authority} HTTP/1.1\r\nHost: {authority}\r\n\r\n".encode("ascii"))
        response = b""
        while not response.endswith(b"\r\n\r\n"):
            chunk = raw_socket.recv(1)
            if not chunk or len(response) > 8192:
                raise RuntimeError("本地 CONNECT 响应不完整")
            response += chunk
        assert response.startswith(b"HTTP/1.1 200")
        context = ssl.create_default_context(cafile=str(ca_file))
        context.minimum_version = context.maximum_version = tls_version
        context.set_alpn_protocols(["http/1.1"])
        secure_socket = context.wrap_socket(raw_socket, server_hostname="localhost")
        connection = HTTPConnection("localhost", upstream_port, timeout=8)
        connection.sock = secure_socket
        descriptor = secure_socket.fileno()
        selected_version = secure_socket.version()
        for number in range(2):
            connection.request("GET", f"/v1/tls-evidence/{label}/{number}", headers={"Connection": "keep-alive"})
            answer = connection.getresponse()
            assert answer.status == 200 and answer.read() == b'{"synthetic":true}'
            assert connection.sock is secure_socket and secure_socket.fileno() == descriptor
        return {"label": label, "negotiated_tls": selected_version, "requests": 2, "same_client_socket": True}
    finally:
        if connection is not None:
            connection.close()
        raw_socket.close()


def _wait_http(path: Path, count: int) -> None:
    deadline = time.monotonic() + 8
    while time.monotonic() < deadline:
        if len({row["flow_id"] for row in _read_records(path) if row.get("capture_state") == "complete"}) >= count:
            return
        time.sleep(0.05)
    raise RuntimeError("真实 HTTP 抓包未及时完成")


def main() -> None:
    """运行固定 SDK 的本地合成验证。:return: None；失败退出非零并保留私有产物。"""
    parser = argparse.ArgumentParser(description="固定 11.1.3 客户端握手及 HTTP 关联验证（仅回环）")
    parser.add_argument("--output", type=Path, help="新的空验证目录；省略则保留在临时目录")
    parser.add_argument("--sidecar", type=Path, default=Path("/sidecar"), help="待验证 Recorder 源码目录")
    arguments = parser.parse_args()
    if VERSION != "11.1.3":
        raise RuntimeError("此验收必须运行在 mitmproxy 11.1.3，不能用其他 SDK 替代")
    output = arguments.output or Path(tempfile.mkdtemp(prefix="tls-clienthello-verification-"))
    output.mkdir(parents=True, exist_ok=True)
    if any(output.iterdir()):
        raise RuntimeError("验证输出目录必须为空，不能覆盖既有证据")
    output.chmod(0o700)
    sidecar = arguments.sidecar.absolute()
    assert all((sidecar / name).is_file() for name in ("recorder.py", "tls_clienthello.py", "quota_protocol.py"))
    ca_directory = output / "ca"
    ca_directory.mkdir(mode=0o700)
    ca_file = ca_directory / "mitmproxy-ca-cert.pem"
    http_path, tls_path = output / "http_capture.jsonl", output / "tls_clienthello.jsonl"
    context = {"schema": 1, "source": "run:tls-verification:0", "run_id": "tls-verification",
               "claude_code_version": "2.1.303"}
    environment = {key: value for key, value in os.environ.items()
                   if not key.startswith("QUOTA_") and key.upper() not in
                   ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY", "CAPTURE_CONTEXT")}
    environment.update({"STATS_FILE": str(output / "stats.jsonl"), "CAPTURE_FILE": str(http_path),
        "CAPTURE_INDEX_FILE": str(output / "capture_index.json"), "CAPTURE_FULL_HTTP": "1",
        "CAPTURE_SCOPE": "all", "CAPTURE_MAX_BODY_BYTES": "0", "V3_ACCOUNT": "0", "QUOTA_WARMUP": "0",
        "QUOTA_SOURCE": context["source"], "CAPTURE_CONTEXT": json.dumps(context)})
    proxy_port = _port()
    command = [str(Path(sys.executable).with_name("mitmdump")), "--listen-host", "127.0.0.1",
        "--listen-port", str(proxy_port), "--set", "confdir=" + str(ca_directory), "--set", "ssl_insecure=true",
        "--set", "connection_strategy=lazy", "-q", "-s", str(sidecar / "recorder.py"),
        "-w", str(output / "capture.flow")]
    log_descriptor = os.open(output / "recorder.log", os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    upstream = None
    process = None
    client_results = []
    archived = output / "saved_tls_clienthello.jsonl"
    sentinel = output / "private-sentinel"
    try:
        with os.fdopen(log_descriptor, "wb") as log:
            process = subprocess.Popen(command, env=environment, stdout=log, stderr=subprocess.STDOUT)
        _wait_ready(process, proxy_port, ca_file)
        upstream = ThreadingHTTPServer(("127.0.0.1", 0), MockHTTPSHandler)
        upstream.daemon_threads = True
        server_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        # 仅回环模拟服务器复用本次临时 CA 的密钥；不安装到系统，也不接触正式信任链。
        server_context.load_cert_chain(str(ca_directory / "mitmproxy-ca.pem"))
        upstream.socket = server_context.wrap_socket(upstream.socket, server_side=True)
        server_thread = threading.Thread(target=upstream.serve_forever, daemon=True)
        server_thread.start()
        upstream_port = upstream.server_address[1]
        for version, label in ((ssl.TLSVersion.TLSv1_2, "tls12"), (ssl.TLSVersion.TLSv1_3, "tls13")):
            client_results.append(_requests(proxy_port, upstream_port, ca_file, version, label))
        assert [item["negotiated_tls"] for item in client_results] == ["TLSv1.2", "TLSv1.3"]
        _wait_http(http_path, 4)
        assert len(_read_records(tls_path)) == 2
        original_tls = tls_path.read_bytes()
        tls_path.replace(archived)
        sentinel.write_bytes(b"unchanged-private-sentinel")
        sentinel.chmod(0o600)
        tls_path.symlink_to(sentinel)
        client_results.append(_requests(proxy_port, upstream_port, ca_file, ssl.TLSVersion.TLSv1_3, "write-failure"))
        _wait_http(http_path, 6)
        assert sentinel.read_bytes() == b"unchanged-private-sentinel"
        assert archived.read_bytes() == original_tls
    finally:
        if tls_path.is_symlink():
            tls_path.unlink()
        if archived.exists():
            archived.replace(tls_path)
        if process is not None:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
        if upstream is not None:
            upstream.shutdown()
            upstream.server_close()
    tls_records = _read_records(tls_path)
    assert len(tls_records) == 2
    assert stat.S_IMODE(tls_path.stat().st_mode) == 0o600
    http_records = {row["flow_id"]: row for row in _read_records(http_path)}
    assert len(http_records) == 6 and all(row["capture_state"] == "complete" for row in http_records.values())
    index = json.loads((output / "capture_index.json").read_text())
    assert index["total_flows"] == 6
    evidence = []
    for label, tls_record in zip(("tls12", "tls13"), tls_records):
        assert tls_record["capture_context"] == context and tls_record["capture_context_status"] == "ok"
        rows = [row for row in http_records.values() if row["request"]["path"].startswith("/v1/tls-evidence/" + label + "/")]
        assert len(rows) == 2
        assert {row["client_connection_id"] for row in rows} == {tls_record["client_connection_id"]}
        assert all(row["capture_context"] == context for row in rows)
        assert all(row["capture_context_status"] == "ok" for row in rows)
        result = verify_raw_record(tls_record)
        result.update(label=label, correlated_http_flows=len(rows))
        evidence.append(result)
    for entry in index["entries"]:
        row = http_records[entry["flow_id"]]
        assert entry["client_connection_id"] == row["client_connection_id"] and entry["capture_context"] == context
    diagnostics = _read_records(output / "stats.jsonl")
    assert any(row.get("error") == "tls_clienthello_capture_failed" for row in diagnostics)
    vectors = [("769,47-53-5-10-49161-49162-49171-49172-50-56-19-4,0-10-11,23-24-25,0", "ada70206e40642a3e4461f35503241d5"),
               ("769,4-5-10-9-100-98-3-6-19-18-99,,,", "de350869b8c85de67a350c8d186f11e6")]
    assert all(hashlib.md5(text.encode(), usedforsecurity=False).hexdigest() == digest for text, digest in vectors)
    report = {"status": "passed", "evidence_kind": "local_synthetic_tls_clients", "mitmproxy_version": VERSION,
        "client_results": client_results, "tls_records": len(tls_records), "http_flows": len(http_records),
        "fixed_ja3_vectors": len(vectors), "private_mode": "0600", "write_failure_http_continues": True,
        "frozen_context_verified": True, "raw_independent_parse": evidence,
        "limitations": ["不是官方 CLI 样本", "不覆盖 DTLS/QUIC/ECH 内层及 HRR 二次派发"]}
    report_path = output / "report.json"
    descriptor = os.open(report_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
