"""用真实网关、账号事件源与 2.1.293 CLI 验收公开 Messages 冷导入。"""

import argparse
from contextlib import ExitStack, closing
from hashlib import sha256
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
from secrets import token_hex
from shutil import copy2, copytree
from socket import create_connection, if_nameindex
from sqlite3 import connect
import ssl
from subprocess import Popen
from tempfile import TemporaryDirectory
from time import time_ns
from uuid import uuid4

from fixtures.native_model_send.fixture_tunnel import _relay
from verify_tui_final_tls import call, encoded, serve, stop, wait_for
from verify_tui_http_handoff import MODEL, message_sse
from native_capture import read_capture
from tls_http import certificates


ROOT = Path(__file__).resolve().parents[2]
HISTORY = [
    ("user", "H1：项目名是海棠。"), ("assistant", "H2：项目名已记录。"),
    ("user", "H3：订单号是 123。"), ("assistant", "H4：订单号已记录。"),
]
QUESTION = "NOW：查询新便签并回答。"
SYSTEM = ["RULE1：你是便签助手。", "RULE2：请只使用已声明的工具。"]
PAST_ID = "toolu_past_fixture"
NEW_ID = "toolu_cold_fixture"
TOOL = {"name": "LookupNote", "description": "读取合成便签", "input_schema": {
    "type": "object", "properties": {"key": {"type": "string"}}, "required": ["key"],
}}
ARGS = {"key": "synthetic-note"}
REPLY = "CLIENT：合成便签内容"
FINAL = "模型已收到本次客户端回执。"


def response_json(handler, payload):
    """写入合成 JSON 响应。@param handler 当前连接。@param payload 响应对象。@return 无。"""
    raw = json.dumps(payload).encode()
    handler.send_response(200)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Content-Length", str(len(raw)))
    handler.end_headers()
    handler.wfile.write(raw)


class QuietHandler(BaseHTTPRequestHandler):
    """回环夹具保持输出为最终核对摘要。"""

    def log_message(self, *_):
        """省略验收请求日志。@return 无。"""


def install_source():
    """把当前版本生产模块安装到 Rust 发送器的固定入口。@return 无。"""
    target = Path("/opt/flower/tui")
    for file in (ROOT / "images/account").glob("tui_*.py"):
        copy2(file, target / file.name)
    copytree(ROOT / "images/account/tui-mod", target / "tui-mod", dirs_exist_ok=True)
    for name in ("runtime_files.py", "tui_workspace_launch.py", "tui_capacity.py"):
        copy2(ROOT / "services/orchestrator" / name, target / name)


def verify(gateway, sender, temporary):
    """核对公开工具回执、CLI 正文与 HTTPS 实收。@param gateway 验证网关。@param sender 验证发送器。
    @param temporary 本次测试私有目录。@return 脱敏证据。
    """
    secret, admin, internal, account_token = (token_hex(32) for _ in range(4))
    nonce = uuid4().hex
    deployment, release = "cold-history-" + nonce, "cold-history-fixture"
    host = "flower2api-" + sha256(deployment.encode()).hexdigest()[:12] + "-" + nonce
    binding = {"account_id": 1, "environment_id": nonce, "generation": 1, "release_id": release,
               "endpoint": f"http://{host}:8091", "secret": secret}
    with Path("/etc/hosts").open("a") as stream:
        stream.write(f"\n127.0.0.1 {host}\n")
    for directory in (Path("/run/v3/tui-v2"), Path("/native"), Path("/flows/api")):
        directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        os.chown(directory, 1001, 1001)
    certificates(temporary)
    config = Path("/run/v3/sender.json")
    copy2(temporary / "ca.der", config.with_name("verification-ca.der"))
    received, callbacks, proxy_targets = [], [], []

    class Receiver(QuietHandler):
        """以生产主机名的临时证书接收原生请求，返回固定工具或文本。"""

        protocol_version = "HTTP/1.1"

        def do_POST(self):
            """验证合成凭据并返回同一轮 SSE。@return 无。"""
            if (self.path != "/v1/messages"
                    or self.headers.get("Authorization") != "Bearer " + account_token):
                self.send_error(403)
                return
            raw = self.rfile.read(int(self.headers["Content-Length"]))
            body = json.loads(raw)
            received.append((sha256(raw).hexdigest(), body, self.connection.version()))
            tool = next((t for t in body.get("tools", []) if t.get("description") == TOOL["description"]), None)
            results = find_blocks(body, "tool_use_id", NEW_ID)
            if not results and tool:
                content = {"type": "tool_use", "id": NEW_ID, "name": tool["name"], "input": ARGS}
                wire = message_sse(content, "tool_use", "msg_cold_tool")
            else:
                wire = message_sse({"type": "text", "text": FINAL}, "end_turn", "msg_cold_reply")
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Content-Length", str(len(wire)))
            self.end_headers()
            self.wfile.write(wire)

    class Proxy(QuietHandler):
        """只把账号认可的固定供应商目标接进当前合成模型。"""

        def do_CONNECT(self):
            """保持代理与模型的 TLS 边界。@return 无。"""
            if self.path != "api.anthropic.com:443":
                self.send_error(403)
                return
            with create_connection(("127.0.0.1", receiver.server_port), timeout=10) as target:
                _relay(self, target, proxy_targets.append)

    class Registry(QuietHandler):
        """实现本次账号发现与现有采集回读所需的编排接口。"""

        def do_GET(self):
            """按本次内部令牌返回账号绑定或诊断。@return 无。"""
            if self.headers.get("Authorization") != "Bearer " + internal:
                self.send_error(403)
                return
            path = self.path.partition("?")[0]
            if path == "/internal/v3/transport/1":
                return response_json(self, binding)
            prefix = "/internal/v3/native-captures/1/"
            if path.startswith(prefix):
                try:
                    return response_json(self, read_capture(Path("/"), 1, path.removeprefix(prefix)))
                except FileNotFoundError:
                    pass
            self.send_error(404)

    with ExitStack() as stack:
        receiver = ThreadingHTTPServer(("127.0.0.1", 0), Receiver)
        tls = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        tls.load_cert_chain(temporary / "leaf.pem", temporary / "leaf.key")
        receiver.socket = tls.wrap_socket(receiver.socket, server_side=True)
        serve(stack, receiver)
        proxy = serve(stack, ThreadingHTTPServer(("127.0.0.1", 0), Proxy))
        registry = serve(stack, ThreadingHTTPServer(("127.0.0.1", 0), Registry))
        proxy_url = f"http://127.0.0.1:{proxy.server_port}"
        config.write_text(json.dumps({"binding": binding, "proxy_url": proxy_url,
                                     "allowed_origin": "https://api.anthropic.com",
                                     "native_capture_dir": "/flows/api/cc-prepared",
                                     "tui_v2": {"max_reservations": 4}}))
        config.chmod(0o640)
        os.chown(config, 0, 1001)
        common = {"PATH": os.defpath, "LANG": "C.UTF-8", "HOME": "/tmp", "TOKIO_WORKER_THREADS": "2"}
        source = Popen([sender], user=1001, group=1001, extra_groups=[], env={
            **common, "RUST_LOG": "warn", "V3_SENDER_CONFIG": str(config),
            "V3_TUI_SESSION_HOST": "1", "V3_TUI_MANAGED_OAUTH": "1",
        })
        stack.callback(stop, source)
        control = Popen([gateway], cwd=temporary, env={
            **common, "SERVER_PORT": "18090", "SERVER_HOST": "127.0.0.1", "DATABASE_DRIVER": "sqlite",
            "DATABASE_DSN": str(temporary / "gateway.db"), "ADMIN_PASSWORD": admin,
            "V3_INTERNAL_TOKEN": internal, "V3_DEPLOYMENT_ID": deployment,
            "V3_RELEASE": release, "V3_RUNTIME_URL": f"http://127.0.0.1:{registry.server_port}",
            "LOG_LEVEL": "warn",
        })
        stack.callback(stop, control)
        wait_for(lambda: call(18090, "GET", "/admin/accounts", admin)[0] == 200)
        wait_for(lambda: json.loads(call(8091, "GET", "/internal/status", secret)[1]).get("tui_v2", {}).get("ready"))

        def manage(method, path, body=None):
            status, raw = call(18090, method, "/admin/" + path, admin, body)
            assert status in (200, 201), (path, status)
            return json.loads(raw)

        manage("PUT", "settings", {"allowed_user_agents": "", "request_diagnostics_log_mode": "debug"})
        account = manage("POST", "accounts", {
            "email": "cold-history@example.invalid", "request_backend": "native293", "auth_type": "oauth",
            "access_token": account_token, "refresh_token": token_hex(32), "proxy_url": proxy_url,
            "expires_at": time_ns() // 1_000_000 + 1_800_000, "subscription_type": "max",
            "auto_telemetry": False, "auto_poll_usage": False, "concurrency": 2, "rpm_limit": 0,
        })
        identifier = account["id"]
        account = manage("GET", f"accounts/{identifier}")
        assert account["tui_v2_available"]
        manage("PUT", f"accounts/{identifier}", {"request_backend": "tui_v2",
               "request_backend_revision": account["request_backend_revision"]})
        token, foreign = (manage("POST", "tokens", {"name": name, "allowed_accounts": str(identifier)})["token"]
                          for name in ("cold-history-owner", "cold-history-foreign"))
        headers = {"x-session-id": str(uuid4()), "User-Agent": "flower2api-cold-history-fixture/1"}
        messages = [{"role": role, "content": text} for role, text in HISTORY]
        messages[3:3] = [
            {"role": "assistant", "content": [{"type": "tool_use", "name": "OldNote", "id": PAST_ID, "input": ARGS}]},
            {"role": "user", "content": [{"type": "tool_result", "tool_use_id": PAST_ID, "content": "已完成的旧工具结果。"}]},
        ]
        messages.append({"role": "user", "content": QUESTION})
        # 历史中的旧工具结果和当前问题之间保留完成边界，CLI 启动后只提交当前问题。
        body = {"model": MODEL, "max_tokens": 128, "stream": True, "messages": messages,
                "tools": [TOOL], "system": [{"type": "text", "text": part} for part in SYSTEM]}
        status, raw = call(18090, "POST", "/v1/messages", token, body, headers)
        assert status == 200, (status, raw)
        events = [json.loads(line[5:]) for line in raw.splitlines() if line.startswith(b"data:")]
        assert events[-1]["type"] == "message_stop", events
        (tool,) = [e["content_block"] for e in events if e["type"] == "content_block_start"]
        assert tool["id"] == NEW_ID and tool["name"] == TOOL["name"], tool
        tool["input"] = json.loads("".join(e["delta"]["partial_json"] for e in events
                                          if e["type"] == "content_block_delta"))
        assert tool["input"] == ARGS
        # 合成客户端只执行登记过的这一个调用。旧工具的 ID 不经过公开回执。
        callbacks.append(tool["id"])
        result = {"role": "user", "content": [{"type": "tool_result", "tool_use_id": NEW_ID, "content": REPLY}]}
        follow = {**body, "stream": False, "messages": [*messages, {"role": "assistant", "content": [tool]}, result]}
        wrong_subject, _ = call(18090, "POST", "/v1/messages", foreign, follow, headers)
        wrong_session, _ = call(18090, "POST", "/v1/messages", token, follow,
                                {**headers, "x-session-id": str(uuid4())})
        changed = {**follow, "messages": [*messages, {"role": "assistant", "content": [
            {**tool, "input": {"key": "another-note"}}]}, result]}
        wrong_arguments, _ = call(18090, "POST", "/v1/messages", token, changed, headers)
        rejected = wrong_subject, wrong_session, wrong_arguments, len(received)
        assert rejected == (400, 400, 422, 1), rejected
        with closing(connect(temporary / "gateway.db")) as database:
            stored = database.execute("SELECT tools FROM tui_native_turns WHERE tools IN (?, ?)",
                                      (json.dumps([NEW_ID]), "!" + json.dumps([NEW_ID]))).fetchall()
            # 公开拒绝完成时，正确回执已经可以重新认领，查询不等待后台归还。
            assert stored == [(json.dumps([NEW_ID]),)], stored
        status, raw = call(18090, "POST", "/v1/messages", token, follow, headers)
        if status != 200:
            trace = [{key: row.get(key) for key in ("status_code", "outcome", "error_stage", "attempt_count")}
                     for row in manage("GET", "request-diagnostics")["items"]]
            raise AssertionError((status, raw, len(received), trace))
        final = json.loads(raw)
        assert final["content"] == [{"type": "text", "text": FINAL}]
        duplicate, _ = call(18090, "POST", "/v1/messages", token, follow, headers)
        assert duplicate == 400 and len(received) == 2, (duplicate, len(received))
        assert callbacks == [NEW_ID]
        verify_model(received)
        captures = verify_captures(manage, received, account_token)
        for attempt, request_body, reply_id, model_id in zip(
            captures, (body, follow), (events[0]["message"]["id"], final["id"]),
            ("msg_cold_tool", "msg_cold_reply"), strict=True,
        ):
            assert attempt["ingress_body_sha256"] == sha256(encoded(request_body)).hexdigest()
            assert attempt["cli_and_https_body_sha256"] != attempt["ingress_body_sha256"]
            attempt.update(client_message_id=reply_id, model_message_id=model_id)
        return {"model_posts": len(received), "client_tool_calls": callbacks, "old_tool_calls": 0,
                "current_question_count": 1, "old_question_roles": [role for role, _ in HISTORY],
                "foreign_receipt_status": wrong_subject, "wrong_session_status": wrong_session,
                "changed_tool_arguments_status": wrong_arguments,
                "duplicate_receipt_status": duplicate, "tls_versions": [tls for _, _, tls in received],
                "proxy_connections": len(proxy_targets), "attempts": captures}


def blocks(row):
    """读取模型端实际内容块。@param row 模型消息。@return 内容块序列。"""
    return row["content"] if isinstance(row["content"], list) else [{"type": "text", "text": row["content"]}]


def find_blocks(body, key, identifier):
    """按真实模型输入中的公开 ID 核对旧工具及续轮。@param body 模型正文。@param key ID 字段。
    @param identifier 合成调用 ID。@return 含所属角色的匹配块。
    """
    return [(row["role"], b) for row in body["messages"] for b in blocks(row) if b.get(key) == identifier]


def verify_model(received):
    """检验模型端的历史、系统提示、原生动态 MCP 和续轮。@param received HTTPS 实收。@return 无。"""
    (_, first, _), (_, second, _) = received
    for body in (first, second):
        assert body["max_tokens"] == 128, body["max_tokens"]
        system = "\n".join(b["text"] for b in body["system"])
        assert "You are Claude Code" in system and all(system.count(part) == 1 for part in SYSTEM)
        assert system.index(SYSTEM[0]) < system.index(SYSTEM[1])
        messages = [(row["role"], b.get("text")) for row in body["messages"] for b in blocks(row)]
        history_texts = {text for _, text in HISTORY}
        assert [(role, text) for role, text in messages if text in history_texts] == HISTORY
        assert messages.count(("user", QUESTION)) == 1
        (old,) = find_blocks(body, "id", PAST_ID)
        (old_result,) = find_blocks(body, "tool_use_id", PAST_ID)
        assert old == ("assistant", {"type": "tool_use", "id": PAST_ID, "name": "OldNote", "input": ARGS})
        assert old_result[0] == "user" and old_result[1]["content"] == "已完成的旧工具结果。"
        (tool,) = [t for t in body["tools"] if t.get("description") == TOOL["description"]]
        assert tool["name"] == "mcp__flower__LookupNote" and tool["input_schema"] == TOOL["input_schema"]
    assert not find_blocks(first, "id", NEW_ID) and not find_blocks(first, "tool_use_id", NEW_ID)
    (new,) = find_blocks(second, "id", NEW_ID)
    (reply,) = find_blocks(second, "tool_use_id", NEW_ID)
    assert new[0] == "assistant" and new[1]["name"] == "mcp__flower__LookupNote" and new[1]["input"] == ARGS
    assert reply[0] == "user" and REPLY in json.dumps(reply[1], ensure_ascii=False)


def verify_captures(manage, received, account_token):
    """从管理接口按尝试比对实际 CLI 正文与 HTTPS 收件摘要。@param manage 本次管理请求。
    @param received TLS 实收。@param account_token 合成凭据。@return 按模型请求顺序的对应关系。
    """
    expected = {raw_sha: i for i, (raw_sha, _, _) in enumerate(received)}

    def observe():
        captures = {}
        for row in manage("GET", "request-diagnostics")["items"]:
            request_id = row["request_id"]
            for attempt in manage("GET", "request-diagnostics/" + request_id)["attempts"]:
                attempt_id = attempt["attempt_id"]
                view = manage("GET", f"request-diagnostics/{request_id}/captures/{attempt_id}")
                if view["state"] != "saved":
                    continue
                snap = view["snapshot"]
                digest = snap["original_body_sha256"]
                if digest not in expected:
                    continue
                stages = {s["stage"]: s for s in snap["stages"]}
                assert stages["wire_final"]["status"] == "unavailable" and "wire_final" not in snap
                assert stages["tui_provider_request"]["representation"] == "request_from_interactive_cli"
                assert account_token not in json.dumps(snap)
                captures[digest] = {"request_id": request_id, "attempt_id": attempt_id,
                                    "ingress_body_sha256": snap["ingress"]["original_body_sha256"],
                                    "cli_and_https_body_sha256": digest, "final_tls_capture": "unavailable"}
        return [captures[digest] for digest in expected] if captures.keys() == expected.keys() else None

    return wait_for(observe)


def main():
    """运行一次性容器中的公开验收。@return 输出脱敏证据。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gateway", type=Path, required=True)
    parser.add_argument("--sender", type=Path, required=True)
    args = parser.parse_args()
    if (not Path("/.dockerenv").exists() or {name for _, name in if_nameindex()} != {"lo"}
            or Path("/run/v3/sender.json").exists() or any(Path("/native").glob("*"))):
        raise RuntimeError("请在空白的 docker --network none 账号容器中运行")
    install_source()
    with TemporaryDirectory(prefix="cold-history-") as directory:
        print(json.dumps(verify(args.gateway, args.sender, Path(directory)), ensure_ascii=False))


if __name__ == "__main__":
    main()
