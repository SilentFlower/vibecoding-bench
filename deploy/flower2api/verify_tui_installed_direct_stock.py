"""在内置直发候选上核对真实外部 Claude Code 的文本和 Read。"""

from argparse import ArgumentParser
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack, closing
from functools import partial
from gzip import decompress
from hashlib import file_digest, sha256
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from io import BytesIO
import json
import os
from pathlib import Path
from socket import if_nameindex
from subprocess import PIPE, Popen, TimeoutExpired, run
from tempfile import TemporaryDirectory
from threading import Event
from time import monotonic_ns
from unittest.mock import patch
from urllib.parse import urlsplit

import verify_tui_cold_history as fixture
import verify_tui_core_http_hook as core
from fixtures.native_model_send.direct_egress_identity import model_body_identity
from fixtures.native_model_send.socket_owner import owns_socket
from fixtures.native_model_send.stock_messages import CLI, INSTRUCTION, NOTE, QUESTION, TOOL_ID, _tool_blocks, _user_texts
from tui_messages import wire_events


TEXT_A = "A：先读到这段。"
TEXT_B = "B：这是模型放行后的结尾。"
ARGS_A = '{"file_path":'


class ModelTimes:
    """以接收端实际写入记录模型首帧和尾帧。"""

    def __init__(self):
        """初始化各笔流的时点。@return 无。"""
        self.posts = []
        self.prefix = Event()
        self.release = Event()
        self.released_ns = None

    def prepare(self, wire):
        """保留模型的原始长度。@param wire 合成模型消息。@return 原始字节。"""
        return wire

    def write(self, handler, wire):
        """分别写出首帧与后续数据。@param handler 模型连接。@param wire 合成模型消息。@return 无。"""
        first, start, delta, tail = wire.split(b"\n\n", 3)
        handler.wfile.write(first + b"\n\n")
        handler.wfile.flush()
        first_ns = monotonic_ns()
        handler.wfile.write(start + b"\n\n" + delta + b"\n\n")
        handler.wfile.flush()
        if not self.posts:
            self.prefix.set()
            assert self.release.wait(30)
        handler.wfile.write(tail)
        handler.wfile.flush()
        self.posts.append({"model_first_frame_ns": first_ns, "model_end_ns": monotonic_ns()})


def model_reply(body, homes, final, *, case):
    """只为实收声明了 Read 的首轮返回真实客户端可执行工具。
    @param body 隔离模型输入。@param homes 外部客户端工作区。@param final 最终答复。
    @param case 本次外部 CLI 场景。@return 模型事件。
    """
    if not _tool_blocks(body, "tool_result") and [tool["name"] for tool in body.get("tools", [])] == ["Read"]:
        (home,) = homes
        arguments = {"file_path": str(home / "fixture-note.txt")}
        wire = fixture.message_sse({"type": "tool_use", "id": TOOL_ID, "name": "Read", "input": arguments},
                                   "tool_use", "msg_stock_direct_read")
        field, a = "partial_json", ARGS_A
        b = fixture.encoded(arguments).decode().removeprefix(a)
    elif case == "text":
        wire = fixture.message_sse({"type": "text", "text": TEXT_A + TEXT_B}, "end_turn", "msg_stock_direct_done")
        field, a, b = "text", TEXT_A, TEXT_B
    else:
        return fixture.message_sse({"type": "text", "text": final}, "end_turn", "msg_stock_direct_done")
    events = [event for _, event in wire_events(BytesIO(wire)) if event is not None]
    delta = events[2]
    chunks = [{**delta, "delta": {**delta["delta"], field: part}} for part in (a, b)]
    return b"".join(map(fixture.frame, [*events[:2], *chunks, *events[3:]]))


def observe_delivery(digest, model_peer, proxy_peer, proxy_port, sender_pid):
    """从实际模型 TCP 对端查回本次许可和原版 CLI 套接字。
    @param digest 模型实收摘要。@param model_peer 模型端对端端口。@param proxy_peer 账号代理对端。
    @param proxy_port 所选账号代理。@param sender_pid 账号发送器 PID。@return 逐笔出站归属。
    """
    tunnels = map(json.loads, Path("/tmp/flower-direct-tunnels.jsonl").read_text().splitlines())
    (tunnel,) = (entry for entry in tunnels if entry["account_proxy_peer_port"] == proxy_peer)
    assert tunnel["account_proxy_port"] == proxy_port
    cli_pid = tunnel["cli_pid"]
    assert cli_pid != sender_pid and owns_socket(cli_pid, tunnel["inode"])
    assert not owns_socket(sender_pid, tunnel["inode"])
    permit = json.loads(Path("/tmp/flower-direct-permits.jsonl").read_text().splitlines()[-1])
    assert permit["allowed"] is True and permit["cli_pid"] == cli_pid
    return {"permit": permit, "tunnel": tunnel, "model_peer_port": model_peer, "model_body_sha256": digest,
            "connection_owner": "interactive_cli", "sender_pid": sender_pid}


def _observe_ingress(stack, requests):
    class ClientObserver(fixture.QuietHandler):
        """透明转送外部官方客户端的 HTTP 请求，记录公开回包时点。"""

        def do_POST(self):
            """通过真实网关转交请求和响应。@return 无。"""
            wire = self.rfile.read(int(self.headers["Content-Length"]))
            body = decompress(wire) if self.headers.get("Content-Encoding") == "gzip" else wire
            with closing(HTTPConnection("127.0.0.1", 18090, timeout=40)) as connection:
                connection.request("POST", self.path, wire, dict(self.headers.items()))
                response = connection.getresponse()
                timing = {"public_response_headers_ns": monotonic_ns()}
                self.send_response(response.status)
                for name, value in response.getheaders():
                    if name.lower() not in {"transfer-encoding", "content-length", "connection", "server", "date"}:
                        self.send_header(name, value)
                self.send_header("Connection", "close")
                self.end_headers()
                public = bytearray()
                if response.getheader("content-type", "").startswith("text/event-stream"):
                    for raw, event in wire_events(response):
                        if event is not None and "public_first_data_ns" not in timing:
                            timing["public_first_data_ns"] = monotonic_ns()
                        public.extend(raw)
                        self.wfile.write(raw)
                        self.wfile.flush()
                else:
                    public.extend(response.read())
                    self.wfile.write(public)
                if urlsplit(self.path).path == "/v1/messages":
                    requests.append((json.loads(body), sha256(body).hexdigest(), response.status,
                                     response.getheader("x-cc2api-request-id"), timing, bytes(public)))

    return fixture.serve(stack, ThreadingHTTPServer(("127.0.0.1", 0), ClientObserver))


def _run_client(home, token, endpoint, prompt, case, model_times):
    tools = ["--tools", "Read", "--allowedTools", "Read"] if case == "read" else ["--tools", ""]
    command = [CLI, "--print", "--model", fixture.MODEL, "--no-session-persistence", *tools,
               "--permission-mode", "dontAsk", "--output-format", "stream-json", "--verbose",
               "--include-partial-messages", "--system-prompt", INSTRUCTION, prompt]
    environment = {
        "HOME": str(home), "PATH": os.defpath, "LANG": "C.UTF-8", "TERM": "dumb",
        "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1", "DISABLE_PROMPT_CACHING": "1",
        "ANTHROPIC_API_KEY": token, "ANTHROPIC_BASE_URL": endpoint, "ANTHROPIC_DEFAULT_HAIKU_MODEL": fixture.MODEL,
    }
    first = Event()
    fragments = []
    field, prefix = ("partial_json", ARGS_A) if case == "read" else ("text", TEXT_A)

    def read_output(pipe):
        rows = []
        for line in pipe:
            row = json.loads(line)
            rows.append(row)
            if row.get("type") != "stream_event":
                continue
            event = row["event"]
            delta = event.get("delta", {})
            if event["type"] == "content_block_delta" and field in delta:
                fragments.append({"fragment": delta[field], "monotonic_ns": monotonic_ns()})
                if delta[field] == prefix:
                    first.set()
        return rows

    with Popen(command, cwd=home, env=environment, stdout=PIPE, stderr=PIPE, text=True) as process:
        with ThreadPoolExecutor(max_workers=2) as readers:
            output = readers.submit(read_output, process.stdout)
            error = readers.submit(process.stderr.read)
            observed = None
            try:
                if case != "error":
                    observed = model_times.prefix.wait(25) and first.wait(8)
            finally:
                model_times.released_ns = monotonic_ns()
                model_times.release.set()
            try:
                process.wait(timeout=35)
            except TimeoutExpired:
                process.kill()
                raise
            return process.returncode, output.result(), error.result(), fragments, observed


def check(manage, token, account_id, received, homes, final, deliveries, *, case, model_times):
    """关联外部原版答复、网关预留及同次模型收件。
    @param manage 管理入口。@param token 合成凭据。@param account_id 所选账号。@param received 实收列表。
    @param homes 外部 CLI 工作区。@param final 预期答复。@param deliveries 模型端归属。
    @param case 外部客户端场景。@param model_times 模型写出时点。@return 结构化验收证据。
    """
    requests = []
    (home,) = homes
    home.mkdir(mode=0o700)
    (home / "fixture-note.txt").write_text(NOTE + "\n")
    prompt = fixture.REJECT_MODEL_REQUEST if case == "error" else QUESTION
    with ExitStack() as stack:
        observer = _observe_ingress(stack, requests)
        exit_code, events, error, fragments, prefix_observed = _run_client(
            home, token, f"http://127.0.0.1:{observer.server_port}", prompt, case, model_times,
        )

    request_summary = [(status, request_id) for _, _, status, request_id, _, _ in requests]
    assert requests and len(requests) == len(received), (case, request_summary, len(received), error)
    result, = (event for event in events if event.get("type") == "result")
    if case == "error":
        assert result["is_error"], result
    else:
        assert len(requests) == (2 if case == "read" else 1), (case, request_summary, len(received), error)
        expected = TEXT_A + TEXT_B if case == "text" else final
        assert exit_code == 0 and result["result"] == expected and result["is_error"] is False, result
        assert prefix_observed and fragments[0]["monotonic_ns"] < model_times.released_ns, (
            case, request_summary, fragments, model_times.released_ns,
        )
        if case == "text":
            assert [item["fragment"] for item in fragments] == [TEXT_A, TEXT_B], fragments
        usage = result["usage"]
        assert (usage["input_tokens"], usage["output_tokens"]) == (10 * len(received), 8 * len(received)), usage
    actual_tool_calls = 0
    if case == "read":
        (offered,) = _tool_blocks(requests[1][0], "tool_use")
        (receipt,) = _tool_blocks(requests[1][0], "tool_result")
        assert offered["id"] == receipt["tool_use_id"] == TOOL_ID and offered["name"] == "Read"
        assert offered["input"] == {"file_path": str(home / "fixture-note.txt")}
        assert json.loads("".join(item["fragment"] for item in fragments)) == offered["input"]
        assert not receipt.get("is_error") and json.dumps(receipt["content"], ensure_ascii=False).count(NOTE) == 1
        (model_receipt,) = _tool_blocks(received[1][1], "tool_result")
        assert model_receipt["tool_use_id"] == TOOL_ID
        assert json.dumps(model_receipt["content"], ensure_ascii=False).count(NOTE) == 1
        actual_tool_calls = 1

    attempts = []
    for (incoming, client_digest, status, request_id, timing, raw), (digest, body, tls) in zip(requests, received, strict=True):
        assert status == (400 if case == "error" else 200) and request_id, (status, request_id, raw)
        assert body["model"] == incoming["model"] == fixture.MODEL
        client_questions = sum(text.count(prompt) for text in _user_texts(incoming))
        model_questions = sum(text.count(prompt) for text in _user_texts(body))
        assert client_questions == model_questions == 1, (request_id, client_questions, model_questions)
        assert sum(block["text"].count(INSTRUCTION) for block in body["system"]) == 1, (request_id, "系统指令")
        assert [tool["name"] for tool in body.get("tools", [])] == (["Read"] if case == "read" else []), request_id

        def finished_detail():
            detail = manage("GET", f"request-diagnostics/{request_id}")
            return detail if detail["request"].get("finished_at") else None

        detail = fixture.wait_for(finished_detail)
        root = detail["request"]
        (attempt,) = detail["attempts"]
        reservation = root["context"]["tui_reservation_id"]
        assert root["context"]["tui_confirmed_model_responses"] == 1, root
        assert (attempt["account_id"], attempt["request_id"], attempt["attempt_id"]) == (account_id, request_id, reservation)
        context = attempt["context"]
        delivery = deliveries[digest]
        permit = delivery["permit"]
        actual_identity = model_body_identity(body)
        assert actual_identity["billing_cch"] not in (None, "00000"), actual_identity
        assert permit["reservation_id"] == reservation and permit["body_identity"] == {
            **actual_identity, "billing_cch": "00000",
        }, delivery
        if case == "error":
            assert json.loads(raw) == {"type": "error", "error": {"type": "api_error", "message": "本机模型返回 HTTP 400"}}
            assert (root["outcome"], root["error_stage"]) == ("upstream_rejected", "upstream_headers")
        else:
            assert context["tui_body_source"] == "interactive_cli", attempt
            public_events = [event for _, event in wire_events(BytesIO(raw)) if event is not None]
            usage, = (event["usage"] for event in public_events if event["type"] == "message_delta")
            assert (usage["input_tokens"], usage["output_tokens"]) == (10, 8), public_events
            assert (attempt["tokens"]["input_tokens"], attempt["tokens"]["output_tokens"]) == (10, 8), attempt
            times = model_times.posts[len(attempts)]
            timing = {**timing, **times}
            assert times["model_first_frame_ns"] <= timing["public_response_headers_ns"]
            assert timing["public_response_headers_ns"] <= timing["public_first_data_ns"]
            if not attempts:
                assert timing["public_first_data_ns"] <= fragments[0]["monotonic_ns"]
                assert model_times.released_ns <= times["model_end_ns"]
        attempts.append({"request_id": request_id, "reservation_id": reservation, "http_status": status,
                         "client_body_sha256": client_digest, "model_body_sha256": digest, "model_tls": tls,
                         "body_source": context.get("tui_body_source"), "timing": timing, "delivery": delivery,
                         "attempt_usage": attempt["tokens"], "session_origin": context.get("tui_session_origin"),
                         "client_question_count": client_questions, "model_question_count": model_questions})

    assert len({item["reservation_id"] for item in attempts}) == len(attempts)
    if case == "read":
        assert [row["session_origin"] for row in attempts] == ["new_session", "live_process"], attempts
    return {"case": case, "model_posts": len(received), "client_tool_calls": actual_tool_calls,
            "client_result": result.get("result"), "client_usage": result.get("usage"), "client_fragments": fragments,
            "model_tail_released_ns": model_times.released_ns if prefix_observed else None,
            "attempts": attempts, "final_tls_capture": "unavailable"}


def main():
    """以镜像已安装组件运行一次外部客户端验收。@return 无。"""
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--case", choices=("text", "read", "error"), required=True)
    parser.add_argument("--gateway", type=Path, default=Path("/verification/claude-code-gateway"))
    parser.add_argument("--sender", type=Path, default=Path("/usr/local/bin/account-sender"))
    args = parser.parse_args()
    assert Path("/.dockerenv").is_file() and {name for _, name in if_nameindex()} == {"lo"}
    files = [Path("/opt/flower/tui") / name for name in (
        "tui_source.py", "frozen_tui_source.py", "tui_sender_launch.py", "tui_session.py", "tui-guard",
        "tui-mod/hooks/session.js",
    )]
    files.extend([
        Path("/etc/claude-code/managed-settings.json"),
        Path(f"/opt/{core.POLICY_MARKET}/{core.POLICY_PLUGIN}/hooks/observe.js"),
    ])

    def digests():
        return {str(path): sha256(path.read_bytes()).hexdigest() for path in files}

    before = digests()
    versions = {}
    for version, expected in core.PROGRAMS.items():
        executable = Path(f"/cli/{version}/node_modules/.bin/claude")
        with executable.open("rb") as file:
            assert file_digest(file, "sha256").hexdigest() == expected
        versions[version] = run([executable, "--version"], check=True, stdout=PIPE, text=True, timeout=5).stdout.strip()
        assert versions[version].split()[0] == version
    measure = ModelTimes()
    with patch.multiple(fixture, STOCK_POLICIES=("append",), observe_stock_delivery=observe_delivery,
                        QuietHandler=core.ObservedModel, stock_model_reply=partial(model_reply, case=args.case),
                        verify_stock_client=partial(check, case=args.case, model_times=measure)), TemporaryDirectory() as folder:
        report = fixture.verify(args.gateway, args.sender, Path(folder), installed_runtime=True, stock_client=True,
                                trace_startup=True, failure_boundaries=True, model_stream_probe=measure)
    assert digests() == before
    print(json.dumps({**report, "cli_versions": versions, "installed_file_sha256": before},
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
