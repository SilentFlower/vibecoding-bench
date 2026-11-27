"""验收已安装账号的公开 stream:true，逐项核对模型出站与流交付。"""

from argparse import ArgumentParser
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from datetime import datetime, timezone
from functools import partial
from hashlib import file_digest, sha256
from http.client import HTTPConnection, HTTPException, IncompleteRead
import json
from pathlib import Path
from socket import SOL_SOCKET, SO_RCVBUF, if_nameindex
from sqlite3 import connect
from tempfile import TemporaryDirectory
from threading import Event
from time import monotonic_ns, sleep
from unittest.mock import patch
from uuid import uuid4

import verify_tui_cold_history as fixture
from verify_tui_egress_owner import _connection_owner


SENDER = Path("/usr/local/bin/account-sender")
PROBE_QUESTION = "请返回本次公开流式验收的合成正文。"
BULK_CHUNKS = 256
CHUNK_SIZE = 32 * 1024


class ModelStream:
    """分段写出模型 SSE，直到测试端明确放行剩余帧。"""

    def __init__(self, *, pressure, interrupt=False):
        """建立首帧屏障。@param pressure 是否使用能施加套接字背压的响应。
        @param interrupt 是否在客户端读到前缀后截断真实模型流。@return 无。
        """
        self.pressure = pressure
        self.interrupt = interrupt
        self.interrupted_at_ns = None
        self.release = Event()
        self.writing_tail = Event()
        self.completed = Event()
        self.written = 0
        self.total = 0
        self.events = []
        self.first_frame_ns = None
        self.ended_ns = None

    def prepare(self, wire):
        """组装隔离模型实际发送的有序响应。@param wire 默认模型 SSE。@return 本轮完整 SSE。"""
        self.events = [json.loads(line[5:]) for line in wire.splitlines() if line.startswith(b"data:")]
        assert [event["type"] for event in self.events] == [
            "message_start", "content_block_start", "content_block_delta", "content_block_stop",
            "message_delta", "message_stop",
        ]
        if self.pressure:
            template = self.events[2]
            self.events[3:3] = [
                {**template, "delta": {**template["delta"], "text": f"{index:04d}:" + "x" * CHUNK_SIZE}}
                for index in range(BULK_CHUNKS)
            ]
        payload = b"".join(map(fixture.frame, self.events))
        self.total = len(payload)
        return payload

    def write(self, handler, wire):
        """先交付首个文本增量，再等待客户端许可。@param handler 隔离模型回环服务。
        @param wire 待发送 SSE。@return 无。
        """
        first, second, third, tail = wire.split(b"\n\n", 3)
        first += b"\n\n"
        handler.wfile.write(first)
        handler.wfile.flush()
        self.first_frame_ns = monotonic_ns()
        prefix_tail = b"\n\n".join((second, third, b""))
        handler.wfile.write(prefix_tail)
        handler.wfile.flush()
        self.written = len(first) + len(prefix_tail)
        if not self.release.wait(20):
            handler.close_connection = True
            return
        if self.interrupt:
            self.interrupted_at_ns = monotonic_ns()
            fixture.startup_event("public_sse_model_interrupted", advertised_bytes=self.total, written_bytes=self.written)
            handler.close_connection = True
            return
        self.writing_tail.set()
        for offset in range(0, len(tail), CHUNK_SIZE):
            chunk = tail[offset:offset + CHUNK_SIZE]
            handler.wfile.write(chunk)
            self.written += len(chunk)
        handler.wfile.flush()
        self.ended_ns = monotonic_ns()
        self.completed.set()


def pending_public_bytes(client_port):
    """读取同一 HTTP 连接的服务端发送队列。@param client_port 实际客户端端口。@return 等待发送的字节数。"""
    client = f"0100007F:{client_port:04X}"
    local = f"0100007F:{18090:04X}"
    for line in Path("/proc/net/tcp").read_text().splitlines()[1:]:
        fields = line.split()
        if fields[1:3] == [local, client]:
            return int(fields[4].split(":", 1)[0], 16)
    return 0


def first_frames(manage, token, identifier, received, sender_status, restart, *, source_observer, stream, observe,
                 database, case):
    """核对公开首帧早于模型终帧，并按需施加慢读。
    @param manage 管理接口。@param token 合成凭据。@param identifier 隔离账号。
    @param received 模型实收。@param sender_status 发送器诊断。@param restart 重启处理器。
    @param source_observer 是否安装额外账号事件源。@param stream 模型流屏障。
    @param observe 本地阶段记录器。@param database 隔离网关用量库。@param case 当前用例。
    @return 模型和客户端的可复跑证据。
    """
    assert not restart and not source_observer
    session = str(uuid4())
    body = {"model": fixture.MODEL, "max_tokens": 128, "stream": True,
            "messages": [{"role": "user", "content": PROBE_QUESTION}]}
    headers = {"x-session-id": session, "User-Agent": "flower2api-public-sse/1",
               "anthropic-version": "2023-06-01", "Authorization": "Bearer " + token,
               "Content-Type": "application/json"}
    phase = "public_sse_" + case.replace("-", "_")
    observe("public_request_start", session_id=session, phase=phase)
    started_at = datetime.now(timezone.utc).isoformat(timespec="milliseconds")
    request_id = status = None
    stage = "sending_request"
    try:
        with closing(HTTPConnection("127.0.0.1", 18090, timeout=30)) as connection:
            connection.connect()
            original_receive_buffer = connection.sock.getsockopt(SOL_SOCKET, SO_RCVBUF)
            if stream.pressure:
                connection.sock.setsockopt(SOL_SOCKET, SO_RCVBUF, 32768)
            client_port = connection.sock.getsockname()[1]
            started = monotonic_ns()
            connection.request("POST", "/v1/messages", fixture.encoded(body), headers)
            stage = "waiting_response_headers"
            with closing(connection.getresponse()) as response:
                request_id = response.getheader("x-cc2api-request-id")
                status = response.status
                stage = "reading_response_body"
                observe("public_response_headers", session_id=session, phase=phase, request_id=request_id,
                        http_status=status, model_posts_during=len(received))
                assert status == 200 and (response.getheader("content-type") or "").startswith("text/event-stream"), (
                    status, request_id, response.read() if status != 200 else None,
                )
                prefix = fixture.read_tool_stream_data_lines(response, 3)
                prefix_seen_ns = monotonic_ns()
                prefix_ms = (prefix_seen_ns - started) // 1_000_000
                assert not stream.writing_tail.is_set() and not stream.completed.is_set() and len(received) == 1
                observe("public_sse_prefix", request_id=request_id, model_posts=len(received), data_frames=len(prefix))
                pressure = None
                transport_error = None
                stream.release.set()
                if stream.pressure:
                    assert stream.writing_tail.wait(5)
                    queued = fixture.wait_for(lambda: pending_public_bytes(client_port) or None)
                    # 读者停在同一个响应上。至少两个时点都确认服务端存在未交付字节。
                    sleep(0.2)
                    pending_bytes = pending_public_bytes(client_port)
                    assert pending_bytes > 0
                    pressure = {"unread_queue_bytes": [queued, pending_bytes], "model_bytes_at_resume": stream.written,
                                "model_completed_at_resume": stream.completed.is_set()}
                    if connection.sock is not None:
                        connection.sock.setsockopt(SOL_SOCKET, SO_RCVBUF, original_receive_buffer)
                try:
                    tail = response.read()
                except IncompleteRead as error:
                    if not stream.interrupt:
                        raise
                    tail = error.partial
                    transport_error = type(error).__name__
    except (AssertionError, HTTPException, OSError) as error:
        failed_at = datetime.now(timezone.utc)
        observe("public_sse_failure", session_id=session, phase=phase, request_id=request_id, http_status=status,
                client_stage=stage, model_posts=len(received), error=type(error).__name__)
        fixture.report_request_diagnostics(manage, phase, request_id, session, started_at, failed_at=failed_at)
        raise
    finally:
        stream.release.set()
    lines = prefix + [line for line in tail.splitlines(keepends=True) if line.startswith(b"data:")]
    events = [json.loads(line[5:]) for line in lines]
    public_id = events[0]["message"]["id"]
    assert public_id.startswith("msg_") and len(received) == 1
    expected = stream.events
    expected[0]["message"]["id"] = public_id

    def finished():
        detail = manage("GET", "request-diagnostics/" + request_id)
        return detail if detail["request"].get("finished_at") else None

    detail = fixture.wait_for(finished)
    (attempt,) = detail["attempts"]
    record = detail["request"]
    assert attempt["request_id"] == request_id and attempt["attempt_id"] == record["context"]["tui_reservation_id"]
    result = {"stream": body["stream"], "http_status": status, "request_id": request_id,
              "reservation_id": attempt["attempt_id"], "public_message_id": public_id,
              "prefix_frames_before_model_tail": len(prefix), "prefix_ms": prefix_ms,
              "data_frames": len(lines), "data_sha256": sha256(b"".join(lines)).hexdigest(),
              "model_bytes": stream.total, "client_backpressure": pressure, "model_posts": len(received)}
    if not stream.interrupt:
        assert stream.completed.wait(5) and events == expected
        return result
    assert prefix_seen_ns < stream.interrupted_at_ns and stream.written < stream.total and not stream.completed.is_set()
    assert events[:3] == expected[:3] and len(events) == 4 and transport_error is None, (events, transport_error)
    assert events[-1]["type"] == "error" and events[-1]["error"]["type"] == "api_error", events[-1]
    assert (record["status_code"], record["outcome"], record["error_stage"], record["attempt_count"]) == (
        200, "upstream_error", "upstream_body", 1,
    ), record

    def partial_usage():
        with closing(connect(database)) as db:
            rows = db.execute("SELECT input_tokens, output_tokens, partial FROM usage_records").fetchall()
        return rows if rows else None

    (usage,) = fixture.wait_for(partial_usage)
    first_usage = expected[0]["message"]["usage"]
    assert usage == (first_usage["input_tokens"], first_usage["output_tokens"], 1), usage
    return {**result, "model_interrupted_after_prefix": True, "model_bytes_written": stream.written,
            "transport_error": transport_error, "http_body_complete": transport_error is None,
            "stream_error": events[-1]["error"],
            "outcome": record["outcome"], "error_stage": record["error_stage"], "attempt_count": record["attempt_count"],
            "usage": {"input_tokens": usage[0], "output_tokens": usage[1], "partial": True}}


def installed(gateway, case):
    """通过镜像内原有账号和管理员配置运行公开验收。@param gateway 验证网关。
    @param case 当前 SSE 用例。@return 公开流和模型连接归属。
    """
    assert not Path("/opt/flower/tui/frozen_tui_source.py").exists()
    assert not Path("/opt/flower/tui/fixture_tui_source.py").exists()
    policy = Path("/etc/claude-code/managed-settings.json")
    dropins = Path("/etc/claude-code/managed-settings.d")
    with Path("/opt/flower/tui/tui-guard").open("rb") as guard:
        authorization = {"source": "installed", "guard_sha256": file_digest(guard, "sha256").hexdigest(),
                         "managed_file_present": policy.is_file(), "managed_dropins_present": dropins.is_dir()}
    stream = None
    if case != "reconnect":
        stream = ModelStream(pressure=case == "backpressure", interrupt=case == "after-first-frame")
    current_session, sockets, posts = [], [], []
    original = fixture.startup_event

    with TemporaryDirectory(prefix="flower-public-sse-") as folder, ThreadPoolExecutor(max_workers=2) as observers:
        def observe(stage, **data):
            if stage == "public_request_start":
                current_session[:] = [data["session_id"]]
            elif stage == "proxy_connect_accepted":
                (session,) = current_session
                future = observers.submit(_connection_owner, SENDER, session, data["peer_port"], None)
                sockets.append({"source_port": data["peer_port"], "future": future})
            elif stage == "proxy_model_tcp_connected":
                sockets[-1]["model_peer_port"] = data["peer_port"]
            elif stage == "model_received":
                posts.append(data)
            original(stage, **data)

        options = {}
        replacements = {"startup_event": observe}
        if stream is None:
            options["reconnect_tool_stream"] = True
        else:
            options.update(structured_output="live", model_stream_probe=stream)
            replacements["verify_structured_tool_round"] = partial(
                first_frames, stream=stream, observe=observe, database=Path(folder) / "gateway.db", case=case,
            )
        with patch.multiple(fixture, **replacements):
            result = fixture.verify(gateway, SENDER, Path(folder), installed_runtime=True, trace_startup=True, **options)
        model_ports = {}
        for entry in sockets:
            peer_port = entry["model_peer_port"]
            model_ports[peer_port] = {**entry["future"].result(), "source_port": entry["source_port"],
                                      "model_peer_port": peer_port}
        deliveries = [{**model_ports[post["peer_port"]], "model_body_sha256": post["model_body_sha256"]} for post in posts]
    assert len(deliveries) == result["model_posts"]
    return {"case": case, "public_stream": True, "authorization": authorization, "public": result,
            "deliveries": deliveries, "wire_final": "unavailable"}


def main():
    """隔离运行一个独立的公开 SSE 验收。@return 严格模式按物理出站归属退出。"""
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--gateway", type=Path, required=True)
    parser.add_argument("--case", choices=("first-frame", "backpressure", "reconnect", "after-first-frame"), required=True)
    parser.add_argument("--require-cli-owner", action="store_true",
                        help="要求账号代理入口的客户端套接字由官方 CLI 持有")
    args = parser.parse_args()
    assert Path("/.dockerenv").is_file() and {name for _, name in if_nameindex()} == {"lo"}
    result = installed(args.gateway, args.case)
    result["matches_cli_owner"] = all(post["owner"] == "interactive_cli" for post in result["deliveries"])
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return int(args.require_cli_owner and not result["matches_cli_owner"])


if __name__ == "__main__":
    raise SystemExit(main())
