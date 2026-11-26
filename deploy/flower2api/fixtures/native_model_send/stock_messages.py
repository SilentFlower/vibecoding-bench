"""通过公开 Messages 验证固定原版客户端实际执行的工具往返。"""

from contextlib import ExitStack, closing
from gzip import decompress
from hashlib import sha256
from http.client import HTTPConnection
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
from subprocess import PIPE, run
from urllib.parse import urlsplit

from verify_tui_final_tls import serve, wait_for
from verify_tui_http_handoff import MODEL, message_sse


CLI = Path("/cli/2.1.293/node_modules/.bin/claude")
NOTE = "固定客户端读取的合成便签。"
INSTRUCTION = "用合成便签的内容作答。"
QUESTION = "请读取当前目录的 fixture-note.txt。"
TOOL_ID = "toolu_stock_read_fixture"
POLICIES = ("append", "replace", "user_reminder")
IDENTITIES = {
    "You are Claude Code, Anthropic's official CLI for Claude.": "cli",
    "You are a Claude agent, built on Anthropic's Claude Agent SDK.": "agent_sdk",
}


def _tool_blocks(body, block_type):
    return [block for row in body["messages"] if isinstance(row["content"], list)
            for block in row["content"] if block["type"] == block_type]


def _user_texts(body):
    for row in body["messages"]:
        if row["role"] == "user":
            content = row["content"]
            if isinstance(content, str):
                yield content
            else:
                yield from (block["text"] for block in content if block["type"] == "text")


def model_reply(body, homes, final):
    """按外部客户端正文返回一次 Read 调用或最终文本。
    @param body 隔离模型实收请求。@param homes 三个客户端私有工作区。
    @param final 本组最后答复。@return 同一次模型的 SSE 字节。
    """
    results = _tool_blocks(body, "tool_result")
    if results:
        return message_sse({"type": "text", "text": final}, "end_turn", "msg_stock_read_done")
    (home,) = [path for path in homes if any(
        path.name in text for text in _user_texts(body)
    )]
    assert [tool["name"] for tool in body["tools"]] == ["Read"]
    return message_sse({
        "type": "tool_use", "id": TOOL_ID, "name": "Read",
        "input": {"file_path": str(home / "fixture-note.txt")},
    }, "tool_use", "msg_stock_read")


def verify_stock_client(manage, token, account_id, received, homes, final):
    """用固定 CLI 和自有便签验证三种 V2 策略下的原版输入和回执。
    @param manage 合成管理入口。@param token 公开入口测试令牌。@param account_id 被测账号。
    @param received 隔离模型收件。@param homes 各策略的私有测试工作区。
    @param final 隔离模型的最终答复。@return 按策略关联客户端、尝试和实际分支。
    """
    requests = []
    hop_headers = {"transfer-encoding", "content-length", "connection", "server", "date"}

    class ClientObserver(BaseHTTPRequestHandler):
        """转交真实客户端的公开请求，并在内存中核对原请求与响应关联。"""

        def log_message(self, *_):
            """省略测试 HTTP 日志。@return 无。"""

        def do_POST(self):
            """转交原始请求字节，通过原网关返回 SSE 或错误。@return 无。"""
            wire = self.rfile.read(int(self.headers["Content-Length"]))
            body = decompress(wire) if self.headers.get("Content-Encoding") == "gzip" else wire
            with closing(HTTPConnection("127.0.0.1", 18090, timeout=40)) as connection:
                connection.request("POST", self.path, wire, dict(self.headers.items()))
                response = connection.getresponse()
                reply = response.read()
                if urlsplit(self.path).path == "/v1/messages":
                    requests.append((json.loads(body), sha256(body).hexdigest(),
                                     response.status, response.getheader("x-cc2api-request-id")))
                self.send_response(response.status)
                for name, value in response.getheaders():
                    if name.lower() not in hop_headers:
                        self.send_header(name, value)
                self.send_header("Content-Length", str(len(reply)))
                self.end_headers()
                self.wfile.write(reply)

    version = run([CLI, "--version"], check=True, stdout=PIPE, text=True, timeout=5).stdout.strip()
    assert version.startswith("2.1.293 "), version
    cases = {}
    with ExitStack() as stack:
        observer = serve(stack, ThreadingHTTPServer(("127.0.0.1", 0), ClientObserver))
        for policy, home in zip(POLICIES, homes, strict=True):
            home.mkdir(mode=0o700)
            (home / "fixture-note.txt").write_text(NOTE + "\n")
            account = manage("PUT", f"accounts/{account_id}", {"client_system_prompt_policy": policy})
            assert account["client_system_prompt_policy"] == policy
            before, model_before = len(requests), len(received)
            process = run([
                CLI, "--print", "--model", MODEL, "--no-session-persistence",
                "--tools", "Read", "--allowedTools", "Read", "--permission-mode", "dontAsk",
                "--output-format", "stream-json", "--verbose",
                "--system-prompt", INSTRUCTION, f"{QUESTION}\n本次验收标识 {home.name}。",
            ], cwd=home, env={
                "HOME": str(home), "PATH": os.defpath, "LANG": "C.UTF-8", "TERM": "dumb",
                "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1", "ANTHROPIC_API_KEY": token,
                "ANTHROPIC_BASE_URL": f"http://127.0.0.1:{observer.server_port}",
                "ANTHROPIC_DEFAULT_HAIKU_MODEL": MODEL,
            }, stdout=PIPE, stderr=PIPE, text=True, timeout=55)
            own = requests[before:]
            posts = received[model_before:]
            events = [json.loads(line) for line in process.stdout.splitlines()]
            errors = [event.get("error") for event in events if event.get("error")]
            assert process.returncode == 0 and len(own) == len(posts) == 2, (
                policy, process.returncode, [(status, request_id) for _, _, status, request_id in own], len(posts), errors,
            )
            (last,) = [event for event in events if event.get("type") == "result"]
            assert last.get("result") == final and last.get("is_error") is False, (policy, last)
            (executed,) = _tool_blocks(own[1][0], "tool_result")
            assert executed["tool_use_id"] == TOOL_ID and not executed.get("is_error"), (policy, executed)
            assert json.dumps(executed["content"], ensure_ascii=False).count(NOTE) == 1, (policy, executed)
            (call,) = _tool_blocks(own[1][0], "tool_use")
            assert call["id"] == TOOL_ID and call["name"] == "Read"
            assert call["input"] == {"file_path": str(home / "fixture-note.txt")}
            attempts = []
            for (body, client_digest, status, request_id), (digest, model, _) in zip(own, posts, strict=True):
                assert status == 200 and request_id, (policy, status)
                assert model["model"] == body["model"] == MODEL, policy
                assert digest == client_digest, (policy, request_id, digest, client_digest)
                assert [tool["name"] for tool in model["tools"]] == ["Read"], policy
                billing, identity, *_ = model["system"]
                assert billing["text"].startswith("x-anthropic-billing-header:"), policy
                client_identity = IDENTITIES.get(identity["text"])
                assert client_identity, (policy, identity["text"][:96])
                assert sum(block["text"].count(INSTRUCTION) for block in model["system"]) == 1, policy
                assert sum(text.count(QUESTION) for text in _user_texts(model)) == 1, policy

                def completed():
                    detail = manage("GET", f"request-diagnostics/{request_id}")
                    return detail if detail["request"].get("finished_at") else None

                detail = wait_for(completed)
                (attempt,) = detail["attempts"]
                context = attempt["context"]
                root = detail["request"]["context"]
                reservation = root["tui_reservation_id"]
                assert root["tui_confirmed_model_responses"] == 1
                assert attempt["request_id"] == request_id and attempt["attempt_id"] == reservation
                assert context["kernel"] == "tui_v2"
                assert context["tui_body_source"] == "account_sender", (policy, context)
                attempts.append({"request_id": request_id, "reservation_id": reservation, "model_sha256": digest,
                                 "client_body_sha256": client_digest, "http_status": status,
                                 "client_identity": client_identity,
                                 "confirmed_model_responses": root["tui_confirmed_model_responses"],
                                 "body_source": context["tui_body_source"],
                                 "session_origin": context["tui_session_origin"]})
            assert [attempt["session_origin"] for attempt in attempts] == ["new_session", "live_process"], attempts
            cases[policy] = {"model_posts": len(posts), "client_read_calls": 1, "tool_id": TOOL_ID,
                             "exact_messages_body": True, "attempts": attempts}
    assert len({attempt["reservation_id"] for case in cases.values() for attempt in case["attempts"]}) == 6
    return {"client_version": version, "cases": cases, "model_posts": len(received), "wire_final": "unavailable"}
