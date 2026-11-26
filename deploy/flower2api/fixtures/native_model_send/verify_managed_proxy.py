"""通过一个受管会话的固定测试账号代理核对真实工具和自动标题。"""

import argparse
from collections import Counter
from contextlib import ExitStack
import gzip
from hashlib import sha256
from http.server import ThreadingHTTPServer
from io import BytesIO
import json
from pathlib import Path
from secrets import token_hex
from socket import if_nameindex
import ssl
from subprocess import DEVNULL, run
from tempfile import TemporaryDirectory
from time import monotonic, sleep

from fixture_tunnel import HOST, connect_model
from managed_route import is_title, semantic_digest
from scenario import BARRIER, OBSERVATIONS
from verify import verify, wait_ready
from verify_proxy import LocalHandler, serve
from tui_source import chunks
from tui_messages import BODY_LIMIT

FIXTURE = Path("/verify-native")
TITLE = "隔离标题观察专用文本"


class ModelServer(ThreadingHTTPServer):
    """独立统计模型端收到的 ClientHello 和完成 TLS 握手的连接。"""

    def get_request(self):
        """由 TLS 监听套接字接收已完成握手的连接。@return 已连接的套接字和对端地址。"""
        connection, peer = super().get_request()
        self.established.append(peer[1])
        return connection, peer

    def observe_tls(self, connection, direction, version, content_type, message, data):
        """统计模型端实际读取的消息。@param connection 本端套接字。@param direction 消息方向。
        @param version TLS 版本。@param content_type 记录类型。@param message 消息类型。
        @param data 握手消息字节。@return 无。
        """
        if direction == "read" and content_type.name == "HANDSHAKE" and message.name == "CLIENT_HELLO":
            self.client_hellos.append(connection.getpeername()[1])


class ManagedModel(LocalHandler):
    """独立 TLS 接收端，校验合成凭据并实际记录每份请求和回复。"""

    protocol_version = "HTTP/1.1"

    def parse_request(self):
        """在标准解析器读原始头时计算请求前缀摘要。@return 原 HTTP 解析结果。"""
        reader = self.rfile
        self.http_digest = sha256(self.raw_requestline)
        self.prefix_bytes = len(self.raw_requestline)
        owner = self

        class HeaderReader:
            """只观察标准解析器实际读取的字节。"""

            def readline(self, limit=-1):
                """@param limit 标准解析器的行上限。@return 未改动的原始行。"""
                line = reader.readline(limit)
                owner.http_digest.update(line)
                owner.prefix_bytes += len(line)
                return line

        self.rfile = HeaderReader()
        try:
            return super().parse_request()
        finally:
            self.rfile = reader

    def do_POST(self):
        """收到主轮后分片交付工具调用；标题独立返回。@return 无。"""
        if self.path.partition("?")[0] != "/v1/messages":
            return self.send_error(404)
        authorization = self.headers.get("Authorization", "")
        if (
            not authorization.startswith("Bearer ")
            or sha256(authorization[7:].encode()).hexdigest()
            != (FIXTURE / "synthetic-at.sha256").read_text()
        ):
            return self.send_error(403)
        length = int(self.headers.get("Content-Length", "0"))
        if not 0 < length <= BODY_LIMIT:
            return self.send_error(413)
        raw = self.rfile.read(length)
        if len(raw) != length:
            return self.send_error(400)
        # 实际实体可能是 gzip。写出端和接收端应比较同一层的字节。
        self.http_digest.update(raw)
        received = {
            "observed_http_bytes": self.prefix_bytes + len(raw),
            "http_sha256": self.http_digest.hexdigest(),
            "observed_body_bytes": len(raw),
            "body_sha256": sha256(raw).hexdigest(),
        }
        if self.headers.get("Content-Encoding") == "gzip":
            with gzip.GzipFile(fileobj=BytesIO(raw)) as compressed:
                raw = compressed.read(BODY_LIMIT + 1)
        if len(raw) > BODY_LIMIT:
            return self.send_error(413)
        body = json.loads(raw)
        title = is_title(body)
        label = token_hex(12)
        frames = chunks(body, label, title=TITLE if title else None)
        digest = sha256(raw).hexdigest()
        response_digest = sha256(b"".join(frames)).hexdigest()
        events = [json.loads(frame.split(b"\ndata: ", 1)[1]) for frame in frames]
        block = dict(events[1]["content_block"])
        deltas = [e["delta"] for e in events if e["type"] == "content_block_delta"]
        if block["type"] == "text":
            block["text"] = "".join(d["text"] for d in deltas)
        else:
            block["input"] = json.loads("".join(d["partial_json"] for d in deltas))
        self.server.received.append(
            {
                "kind": "session_title" if title else "main",
                "message_id": events[0]["message"]["id"],
                "body_sha256": digest,
                "received_http": received,
                "semantic_sha256": semantic_digest(body),
                "response_sha256": response_digest,
                "peer_port": self.client_address[1],
                "tls": self.connection.version(),
                "header_names": [name for name, _ in self.headers.raw_items()],
                "language": self.headers.get("Accept-Language"),
                "cache": self.headers.get("Cache-Control"),
                "input_tokens": events[0]["message"]["usage"]["input_tokens"],
                "output_tokens": events[-2]["usage"]["output_tokens"],
                "content_block": block,
            }
        )
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Content-Length", str(sum(map(len, frames))))
        self.end_headers()
        for i, frame in enumerate(frames):
            self.wfile.write(frame)
            self.wfile.flush()
            if i == 2 and events[1]["content_block"]["type"] == "tool_use":
                # 复用原测试的外层屏障，防止本机网络缓冲伪造客户端实时消费。
                until = monotonic() + 30
                while not BARRIER.exists():
                    if monotonic() >= until:
                        raise TimeoutError("外层未收到工具参数首段")
                    sleep(0.02)


class AccountProxy(LocalHandler):
    """独立的测试账号代理，只能接通固定的合成模型。"""

    def do_CONNECT(self):
        """独立记录会话代理入口与模型端口的映射。@return 无。"""

        def opened(remote_port):
            self.server.hops.append(
                {
                    "account_peer_port": self.client_address[1],
                    "model_peer_port": remote_port,
                }
            )

        connect_model(self, self.server.origin_port, opened)


class ManagedCase:
    """将账号侧回执与模型侧、公开客户端和 SQLite 的独立证据汇合。"""

    def __init__(self, origin, proxy, automatic_name, capture_mode):
        """@param origin TLS 模型。@param proxy 账号代理。@param automatic_name 自动命名。
        @param capture_mode 内容采集策略。@return 无。
        """
        self.origin = origin
        self.proxy = proxy
        self.url = f"http://127.0.0.1:{proxy.server_port}"
        self.automatic_name = automatic_name
        self.capture_mode = capture_mode

    def check_captures(self, manage, gateway, case, synthetic_at):
        """从原管理接口核对尝试归属与真实证据来源。@param manage 管理接口。@param gateway 网关进程。
        @param case 两端独立观测。@param synthetic_at 本次合成账号身份。@return 脱敏摘要。
        """
        observed = {}
        expected = case["attempt_bodies"]

        def ready():
            listing = manage("GET", "request-diagnostics")
            for item in listing["items"]:
                key = item["request_id"]
                detail = manage("GET", "request-diagnostics/" + key)
                for attempt in detail["attempts"]:
                    aid = attempt["attempt_id"]
                    assert aid in expected
                    view = manage("GET", f"request-diagnostics/{key}/captures/{aid}")
                    state = view["state"]
                    if state == "missing":
                        continue
                    if self.capture_mode == "debug":
                        assert state == "saved", (state, attempt.get("capture_status"))
                        snap = view["snapshot"]
                        assert (
                            synthetic_at not in json.dumps(snap)
                            and snap["attempt_id"] == aid
                        )
                        stages = {s["stage"]: s for s in snap["stages"]}
                        handoff = stages["tui_provider_request"]
                        assert handoff["representation"] == "request_to_interactive_cli"
                        assert snap["original_body_sha256"] == expected[aid]
                        wire = snap.get("wire_final")
                        if wire is None:
                            assert stages["wire_final"]["status"] == "unavailable"
                        else:
                            assert stages["wire_final"]["status"] == "complete"
                            assert stages["wire_final"]["source"] == "native_tls_uprobe"
                            model = case["attempt_received"][aid]
                            assert wire["source"] == "native_tls_uprobe"
                            assert wire["representation"] == "http_entity_from_tls_accepted_write"
                            assert wire["complete"] is True and wire["status"] == "complete"
                            assert wire["request_id"] == aid and wire["worker_pid"] == case["cli_pid"]
                            assert all(wire[key] == value for key, value in model["received_http"].items())
                            assert [name for name, _ in wire["headers"]] == model["header_names"]
                        observed[aid] = {
                            "request_id": key,
                            "state": state,
                            "submitted": handoff["representation"],
                            "body_sha256": expected[aid],
                            "wire_final": stages["wire_final"]["status"],
                        }
                    else:
                        assert state == (
                            "summary" if self.capture_mode == "info" else "disabled"
                        )
                        observed[aid] = {"request_id": key, "state": state}
            return observed.keys() == expected.keys()

        wait_ready(ready, gateway)
        paths = list(Path("/flows/api/cc-prepared").glob("*.json"))
        assert {p.stem for p in paths} == (
            set(expected) if self.capture_mode == "debug" else set()
        )
        return observed

    def check(self, public, source):
        """校验一次已完成工具往返的所有归属。@param public 公开响应和账本。@param source 账号子进程。@return 汇总。"""

        def records():
            return [json.loads(row) for row in OBSERVATIONS.read_text().splitlines()]

        main_pid = next(r["cli_pid"] for r in records() if "main_grant" in r)
        if self.automatic_name:
            wait_ready(lambda: any("title_receipt" in r for r in records()), source)
        # 此基线在最终 end_turn 后回收进程；待它退出再清点，覆盖末尾才产生的辅助调用。
        wait_ready(lambda: not Path(f"/proc/{main_pid}").exists(), source)
        # 两个主轮都已结束。等待已经受理的每个标题由真实 CLI 消费到 message_stop。
        wait_ready(
            lambda: (
                bool(rows := records())
                and {r["title_receipt"] for r in rows if "title_receipt" in r}
                == {r["title_grant"] for r in rows if "title_grant" in r}
            ),
            source,
        )
        rows = records()
        (launch,) = [r for r in rows if "reserved_session_id" in r]
        assert launch["reserved_session_id"] == public["client_session_id"]
        assert launch["cli_name"] == (
            None if self.automatic_name else public["client_session_id"]
        )
        sessions = {r["account_peer_port"]: r for r in rows if "account_peer_port" in r}
        proxy = {
            r["model_peer_port"]: sessions[r["account_peer_port"]]
            for r in self.proxy.hops
        }
        grants = [r for r in rows if "main_grant" in r]
        receipts = [r for r in rows if "title_receipt" in r]
        upstream = list(self.origin.received)
        mains = [r for r in upstream if r["kind"] == "main"]
        titles = [r for r in upstream if r["kind"] == "session_title"]
        assert len(grants) == len(mains) == 2 and public["tool_reads"] == 1
        pid = main_pid
        assert all(r["cli_pid"] == pid for r in rows if "cli_pid" in r)
        assert all(
            proxy[r["peer_port"]]["cli_pid"] == pid and r["tls"] == "TLSv1.3"
            for r in upstream
        )
        assert (
            len(
                {
                    self.proxy.server_port,
                    self.origin.server_port,
                    grants[0]["private_port"],
                }
            )
            == 3
        )
        assert [r["sha256"] for r in grants] == [r["body_sha256"] for r in mains]
        assert all(r["language"] == "zh-CN" and r["cache"] == "no-cache" for r in mains)
        assert not any(
            name.lower().startswith("x-v3-") for row in upstream for name in row["header_names"]
        )
        # 对外消息 ID 由网关重新分配。按内容块、工具 ID 和主流摘要验证消费归属。
        assert [r["content_block"] for r in mains] == public["client_blocks"]
        # 模型回复自带各自的消息 ID。按两端独立计算的完整响应摘要配对，再按实际连接归档。
        outcomes = {r["completed"]: r["sse_sha256"] for r in rows if "completed" in r}
        by_response = {r["response_sha256"]: r for r in mains}
        assert len(outcomes) == len(by_response) == len(grants)
        attempts = {}
        attempt_received = {}
        bindings = {}
        for g in grants:
            model = by_response[outcomes[g["main_grant"]]]
            assert g["sha256"] == model["body_sha256"]
            attempts[g["attempt_id"]] = model["body_sha256"]
            attempt_received[g["attempt_id"]] = {
                "received_http": model["received_http"],
                "header_names": model["header_names"],
            }
            bindings[model["message_id"]] = g["attempt_id"]
        assert len(attempts) == len(grants)
        assert Counter(
            r["semantic_sha256"] for r in rows if "title_grant" in r
        ) == Counter(r["semantic_sha256"] for r in titles)

        def usage(row):
            return (row["message_id"], row["input_tokens"], row["output_tokens"])

        assert Counter(map(usage, receipts)) == Counter(map(usage, titles))
        bindings.update({r["message_id"]: r["title_receipt"] for r in receipts})
        assert len(bindings) == len(upstream)
        connections = self.origin.established
        assert len(set(connections)) == len(connections)
        assert set(connections) == set(proxy) == set(self.origin.client_hellos)
        exchanges = [
            {
                "connection": index,
                "client_hellos": self.origin.client_hellos.count(port),
                "requests": [
                    {"kind": r["kind"], "message_id": r["message_id"], "private_id": bindings[r["message_id"]]}
                    for r in upstream if r["peer_port"] == port
                ],
            }
            for index, port in enumerate(connections, start=1)
        ]
        assert (
            bool(titles) == self.automatic_name
            and len(set(public["client_message_ids"])) == 2
        )
        assert all(r["content_block"] not in public["client_blocks"] for r in titles)
        keys = ("input_tokens", "output_tokens")
        main_usage = {k: public[k] for k in keys}
        assert main_usage == {k: sum(r[k] for r in mains) for k in keys}
        return {
            "result": "passed",
            "automatic_name": self.automatic_name,
            "cli_pid": pid,
            "cli_name": launch["cli_name"],
            "counted_after_cli_exit": True,
            "session_connections": list(sessions.values()),
            "proxy_connections": self.proxy.hops,
            "account_proxy_port": self.proxy.server_port,
            "origin_port": self.origin.server_port,
            "origin": upstream,
            "model_tls_connections": exchanges,
            "attempt_bodies": attempts,
            "attempt_received": attempt_received,
            "public": public,
            "main_posts": len(mains),
            "title_posts": len(titles),
            "title_receipts": receipts,
            "main_gateway_usage": main_usage,
            "title_observed_usage": {k: sum(r[k] for r in receipts) for k in keys},
            "other_process_connect_status": public["other_process_connect_status"],
        }


def check(gateway, sender, root, automatic_name, capture_mode):
    """启动独立 TLS 模型并跑受管账号。@param gateway 网关。@param sender 发送器。
    @param root 一次性数据库目录。@param automatic_name 启用原生自动命名。@param capture_mode 内容采集策略。@return 代理实测结果。
    """
    if not Path("/.dockerenv").exists() or [i for _, i in if_nameindex()] != ["lo"]:
        raise RuntimeError("必须在全新的仅回环容器运行")
    cert, key = FIXTURE / "model.crt", root / "model.key"
    run(
        [
            "openssl",
            "req",
            "-x509",
            "-newkey",
            "rsa:2048",
            "-nodes",
            "-days",
            "1",
            "-subj",
            "/CN=" + HOST,
            "-addext",
            "subjectAltName=DNS:" + HOST,
            "-keyout",
            str(key),
            "-out",
            str(cert),
        ],
        check=True,
        stdout=DEVNULL,
        stderr=DEVNULL,
    )
    with ExitStack() as stack:
        origin = stack.enter_context(ModelServer(("127.0.0.1", 0), ManagedModel))
        origin.established = []
        origin.client_hellos = []
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(cert, key)
        context._msg_callback = origin.observe_tls
        origin.socket = context.wrap_socket(origin.socket, server_side=True)
        origin.received = []
        serve(stack, origin)
        proxy = stack.enter_context(ThreadingHTTPServer(("127.0.0.1", 0), AccountProxy))
        proxy.origin_port, proxy.hops = origin.server_port, []
        serve(stack, proxy)
        (FIXTURE / "managed-proxy.json").write_text(
            json.dumps(
                {"proxy_port": proxy.server_port, "automatic_name": automatic_name}
            )
        )
        return verify(
            gateway,
            sender,
            root,
            managed_proxy=ManagedCase(origin, proxy, automatic_name, capture_mode),
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gateway", type=Path, required=True)
    parser.add_argument("--sender", type=Path, required=True)
    parser.add_argument("--fixed-name", action="store_true")
    parser.add_argument("--require-cli-wire", action="store_true",
                        help="要求首轮和续轮均通过实际 CLI 写出校验")
    parser.add_argument(
        "--capture-mode", choices=("debug", "info", "disabled"), default="debug"
    )
    args = parser.parse_args()
    with TemporaryDirectory(prefix="managed-proxy-") as folder:
        if args.require_cli_wire and args.capture_mode != "debug":
            parser.error("验证最终写出需要开启 debug 采集")
        result = check(args.gateway, args.sender, Path(folder), not args.fixed_name, args.capture_mode)
        missing = [aid for aid, capture in result["capture_api"].items()
                   if capture.get("wire_final") != "complete"]
        if args.require_cli_wire and missing:
            result.update(result="failed", missing_cli_wire=missing)
        print(json.dumps(result, ensure_ascii=False))
        if result["result"] == "failed":
            raise SystemExit(1)
