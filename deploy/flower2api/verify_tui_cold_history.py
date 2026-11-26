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
from signal import SIGKILL
from socket import create_connection, if_nameindex
from sqlite3 import connect
import ssl
from subprocess import PIPE, Popen, run
from sys import executable
from tempfile import TemporaryDirectory
from time import time_ns
from urllib.parse import parse_qs, urlsplit
from uuid import uuid4

from fixtures.native_model_send.fixture_tunnel import _relay
from verify_tui_concurrency import frame
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
QUESTION_TAIL = "NOW：保留本轮问题第二段。"
AFTER_RESTART = "RESTART：从已确认的旧问答开启另一轮。"
DROP_REPLY = "FAILURE：模型收到正文后关闭响应连接。"
SYSTEM = ["RULE1：你是便签助手。", "RULE2：请只使用已声明的工具。"]
PAST_ID = "toolu_past_fixture"
NEW_ID = "toolu_cold_fixture"
SIGNED_THINKING = {"type": "thinking", "thinking": "隔离模型的合成思考段。", "signature": "c2lnbmF0dXJlLWZpeHR1cmU="}
TOOL = {"name": "Lookup-Note", "description": "读取合成便签", "input_schema": {
    "type": "object", "required": ["key", "options"], "additionalProperties": False,
    "properties": {"key": {"type": "string"}, "options": {
        "type": "object", "properties": {"labels": {"type": "array", "items": {"type": "string"}}},
        "required": ["labels"], "additionalProperties": False,
    }},
}}
NATIVE_TOOL_NAME = "mcp__flower__" + TOOL["name"]
ARGS = {"key": "synthetic-note", "options": {"labels": ["项目", "便签"]}}
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


def install_source(root=ROOT):
    """安装与发送器配套的生产事件源。@param root 检出的源代码。@return 无。"""
    target = Path("/opt/flower/tui")
    for file in (root / "images/account").glob("tui_*.py"):
        copy2(file, target / file.name)
    copytree(root / "images/account/tui-mod", target / "tui-mod", dirs_exist_ok=True)
    for name in ("runtime_files.py", "tui_workspace_launch.py", "tui_capacity.py"):
        copy2(root / "services/orchestrator" / name, target / name)


def build_cutover_record(temporary, old, deployment, release):
    """建立隔离演练的本地准入记录。@param temporary 私有目录。@param old 原账号绑定。
    @param deployment 测试部署。@param release 目标发行标识。@return 准入目录。
    """
    gate = temporary / "update-gate"
    gate.mkdir(mode=0o700)
    admission = {"schema_version": 1, "deployment": deployment, "operation_id": None,
                 "epoch": str(uuid4()), "phase": "idle", "target_release": None,
                 "revision": str(uuid4()), "created_at": "2026-01-01T00:00:00Z"}
    rollout = {"schema_version": 1, "deployment": deployment, "control_release": release,
               "account_release": release, "environments": {old["environment_id"]: {
                   "account_id": 1, "gateway_account_id": old["account_id"], "generation": old["generation"],
                   "origin": {"release": old["release_id"], "environment_id": old["environment_id"], "protocol": 1},
               }}}
    for name, value in (("admission.json", admission), (f"account-rollout-{release}.json", rollout)):
        path = gate / name
        path.write_text(json.dumps(value))
        path.chmod(0o600)
    return gate


def fixture_tool_sse(tool, *, with_signature):
    """交付隔离模型工具流。@param tool 原生工具调用。@param with_signature 是否先交付合成签名块。@return SSE。"""
    wire = message_sse(tool, "tool_use", "msg_cold_tool")
    if not with_signature:
        return wire
    events = [json.loads(line[5:]) for line in wire.splitlines() if line.startswith(b"data:")]
    for event in events:
        if "index" in event:
            event["index"] += 1
    events[1:1] = [
        {"type": "content_block_start", "index": 0, "content_block": {"type": "thinking", "thinking": ""}},
        {"type": "content_block_delta", "index": 0, "delta": {"type": "thinking_delta", "thinking": SIGNED_THINKING["thinking"]}},
        {"type": "content_block_delta", "index": 0, "delta": {"type": "signature_delta", "signature": SIGNED_THINKING["signature"]}},
        {"type": "content_block_stop", "index": 0},
    ]
    return b"".join(map(frame, events))


def verify(gateway, sender, temporary, *, restart_history=False, text_input=False, system_policy=False,
           toggle_pending_policy=False, tool_policy=None, recover_pending=False, output_effort=False,
           history_png=False, history_images=False, history_tool_blocks=False, previous=None, failure_boundaries=False,
           current_text_blocks=False, signed_tool_history=False):
    """核对公开工具回执、CLI 正文与 HTTPS 实收。@param gateway 验证网关。@param sender 验证发送器。
    @param temporary 本次测试私有目录。@param restart_history 是否验证进程重启和历史分支。
    @param text_input 是否验证四种文本系统提示词形状。
    @param system_policy 是否按账号验证原生正文的三种动作。
    @param toggle_pending_policy 是否在客户端工具等待时更改账号动作。
    @param tool_policy 工具往返前显式设置的 V2 动作。
    @param recover_pending 是否结束等待进程并在发送器重启后恢复真实工具回执。
    @param output_effort 是否核对 CLI 实际生成的推理强度和 Token 上限。
    @param history_png 是否核对用户历史里的内嵌 PNG。
    @param history_images 是否核对用户历史里四种内嵌图像。
    @param history_tool_blocks 是否核对已完成工具结果的原始文本块。
    @param previous 可选，旧发行源码、网关、发送器三个离线制品。
    @param failure_boundaries 是否分别在模型收件前后切断隔离连接。
    @param current_text_blocks 是否验证本轮文本块顺序及边界归属。
    @param signed_tool_history 是否核对隔离模型原工具轮的签名块。
    @return 脱敏证据。
    """
    secret, admin, internal, account_token = (token_hex(32) for _ in range(4))
    nonce = uuid4().hex
    deployment = "cold-history-" + nonce
    release, next_release = ("ci-4311-1", "ci-4312-1") if previous else ("cold-history-fixture", None)
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
    lookups = []
    deny_proxy = False
    denied_tunnels = []

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
            if failure_boundaries and any(block.get("text") == DROP_REPLY
                                          for row in body["messages"] for block in blocks(row)):
                self.close_connection = True
                return
            tool = next((t for t in body.get("tools", []) if t.get("description") == TOOL["description"]), None)
            results = find_blocks(body, "tool_use_id", NEW_ID)
            restart = any(b.get("text") == AFTER_RESTART for row in body["messages"] for b in blocks(row))
            if not results and tool and not restart:
                content = {"type": "tool_use", "id": NEW_ID, "name": tool["name"], "input": ARGS}
                wire = fixture_tool_sse(content, with_signature=signed_tool_history)
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
            if deny_proxy:
                denied_tunnels.append(self.path)
                self.send_error(502)
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
            target = urlsplit(self.path)
            path = target.path
            if path == "/internal/v3/transport/1":
                if previous:
                    lookups.append(parse_qs(target.query))
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

        def write_sender_config():
            config.write_text(json.dumps({"binding": binding, "proxy_url": proxy_url,
                                          "allowed_origin": "https://api.anthropic.com",
                                          "native_capture_dir": "/flows/api/cc-prepared",
                                          "tui_v2": {"max_reservations": 4}}))
            config.chmod(0o640)
            os.chown(config, 0, 1001)

        write_sender_config()
        common = {"PATH": os.defpath, "LANG": "C.UTF-8", "HOME": "/tmp", "TOKIO_WORKER_THREADS": "2"}

        def start_sender(program=sender):
            process = Popen([program], user=1001, group=1001, extra_groups=[], env={
                **common, "RUST_LOG": "warn", "V3_SENDER_CONFIG": str(config),
                "V3_TUI_SESSION_HOST": "1", "V3_TUI_MANAGED_OAUTH": "1",
            })
            stack.callback(stop, process)
            return process

        def start_gateway(program, version, **gate):
            process = Popen([program], cwd=temporary, env={
                **common, "SERVER_PORT": "18090", "SERVER_HOST": "127.0.0.1", "DATABASE_DRIVER": "sqlite",
                "DATABASE_DSN": str(temporary / "gateway.db"), "ADMIN_PASSWORD": admin,
                "V3_INTERNAL_TOKEN": internal, "V3_DEPLOYMENT_ID": deployment,
                "V3_RELEASE": version, "V3_RUNTIME_URL": f"http://127.0.0.1:{registry.server_port}",
                "LOG_LEVEL": "warn", **gate,
            })
            stack.callback(stop, process)
            wait_for(lambda: call(18090, "GET", "/admin/accounts", admin)[0] == 200)
            return process

        source = start_sender(previous[2] if previous else sender)
        control = start_gateway(previous[1] if previous else gateway, release)

        def sender_state():
            return json.loads(call(8091, "GET", "/internal/status", secret)[1]).get("tui_v2", {})

        def restart(process):
            wait_for(lambda: sender_state().get("idle"))
            stop(process)
            restarted = start_sender()
            try:
                wait_for(lambda: sender_state().get("ready") and sender_state().get("idle"))
            except AssertionError as error:
                raise AssertionError(("账号发送器重启后未就绪", restarted.poll(), sender_state())) from error
            return restarted

        wait_for(lambda: sender_state().get("ready"))

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
        if failure_boundaries:
            def post(question):
                request = {"model": MODEL, "max_tokens": 128, "stream": False,
                           "messages": [{"role": "user", "content": question}]}
                return call(18090, "POST", "/v1/messages", token, request,
                            {**headers, "x-session-id": str(uuid4())})

            deny_proxy = True
            before, before_body = post(AFTER_RESTART)
            assert before == 502 and not received, (before, before_body, len(received))
            assert denied_tunnels == ["api.anthropic.com:443"], denied_tunnels
            deny_proxy = False
            after, after_body = post(DROP_REPLY)
            assert after == 502 and len(received) == 1, (after, after_body, len(received))
            status, answer = post(AFTER_RESTART)
            assert status == 200 and len(received) == 2, (status, answer, len(received))
            assert json.loads(answer)["content"] == [{"type": "text", "text": FINAL}]
            (failed, success) = verify_captures(manage, received, account_token)
            for attempt in (failed, success):
                assert attempt["cli_and_https_body_sha256"] != attempt["ingress_body_sha256"]
            return {"before_send": before, "before_model_posts": 0, "after_send": after,
                    "after_model_posts": 1, "next_request": status, "next_model_posts": 1,
                    "attempts": [failed, success]}
        if text_input:
            return verify_text_inputs(manage, token, account_token, headers, messages, received,
                                      current_text_blocks=current_text_blocks)
        if output_effort:
            return verify_output_effort(manage, token, account_token, headers, received)
        if history_png or history_images:
            return verify_history_images(manage, token, account_token, identifier, headers, received,
                                         all_formats=history_images)
        if system_policy:
            account_path = f"accounts/{identifier}"
            first = manage("GET", account_path)
            assert first["client_system_prompt_policy"] == "append" and first["tui_system_prompt_policy_available"]
            # 公开请求自报的私有字段只能作为普通头，模型落点仍由选定账号决定。
            headers["x-v3-tui-system-prompt-policy"] = "user_reminder"
            assert call(18090, "PUT", "/admin/" + account_path, admin,
                        {"client_system_prompt_policy": "independent"})[0] == 400
            proof = {}
            for policy in ("append", "replace", "user_reminder"):
                assert manage("PUT", account_path, {"client_system_prompt_policy": policy})[
                    "client_system_prompt_policy"] == policy
                assert manage("GET", account_path)["client_system_prompt_policy"] == policy
                proof[policy] = verify_text_inputs(manage, token, account_token, headers, messages, received,
                                                   policy=policy, current_text_blocks=current_text_blocks)
            return proof
        if tool_policy:
            assert manage("PUT", f"accounts/{identifier}", {"client_system_prompt_policy": tool_policy})[
                "client_system_prompt_policy"] == tool_policy
        old_result = "已完成的旧工具结果。"
        if history_tool_blocks:
            old_result = [{"type": "text", "text": text} for text in ("已完成的旧工具结果。", "保持第二段结果。")]
        messages[3:3] = [
            {"role": "assistant", "content": [{"type": "tool_use", "name": "OldNote", "id": PAST_ID, "input": ARGS}]},
            {"role": "user", "content": [{"type": "tool_result", "tool_use_id": PAST_ID, "content": old_result}]},
        ]
        current = ([{"type": "text", "text": part} for part in (QUESTION, QUESTION_TAIL)]
                   if current_text_blocks else QUESTION)
        messages.append({"role": "user", "content": current})
        # 历史中的旧工具结果和当前问题之间保留完成边界，CLI 启动后只提交当前问题。
        body = {"model": MODEL, "max_tokens": 128, "stream": True, "messages": messages,
                "tools": [TOOL], "system": [{"type": "text", "text": part} for part in SYSTEM]}
        if recover_pending:
            body["output_config"] = {"effort": "medium"}
        status, raw = call(18090, "POST", "/v1/messages", token, body, headers)
        assert status == 200, (status, raw)
        events = [json.loads(line[5:]) for line in raw.splitlines() if line.startswith(b"data:")]
        assert events[-1]["type"] == "message_stop", events
        (tool,) = [e["content_block"] for e in events if e["type"] == "content_block_start"
                   and e["content_block"]["type"] == "tool_use"]
        assert tool.get("id") == NEW_ID and tool.get("name") == TOOL["name"], (
            tool, [[t["name"] for t in document.get("tools", [])] for _, document, _ in received],
        )
        tool["input"] = json.loads("".join(e["delta"]["partial_json"] for e in events
                                          if e["type"] == "content_block_delta" and e["delta"]["type"] == "input_json_delta"))
        assert tool["input"] == ARGS
        # 合成客户端只执行登记过的这一个调用。旧工具的 ID 不经过公开回执。
        callbacks.append(tool["id"])
        if previous:
            assert received[0][1]["tools"][0]["name"] == TOOL["name"]
            assert not sender_state().get("idle")
            old_binding = {key: binding[key] for key in ("account_id", "environment_id", "generation", "release_id", "endpoint")}
            gate = build_cutover_record(temporary, old_binding, deployment, next_release)
            stop(control)
            start_gateway(gateway, next_release, V3_UPDATE_GATE_DIR=str(gate), V3_ACCOUNT_RELEASE=next_release)
            fresh = {**body, "stream": False, "messages": [{"role": "user", "content": AFTER_RESTART}]}
            lookup_boundary = len(lookups)
            premature, refuse = call(18090, "POST", "/v1/messages", token, fresh,
                                     {**headers, "x-session-id": str(uuid4())})
            assert premature == 503 and len(received) == 1, (premature, refuse, len(received))
            assert any("tui_previous_release" not in lookup for lookup in lookups[lookup_boundary:])
        if toggle_pending_policy:
            changed = manage("PUT", f"accounts/{identifier}", {"client_system_prompt_policy": "replace"})
            assert changed["client_system_prompt_policy"] == "replace"
        result = {"role": "user", "content": [{"type": "tool_result", "tool_use_id": NEW_ID, "content": REPLY}]}
        offered = [tool]
        if signed_tool_history:
            deltas = [event["delta"] for event in events if event["type"] == "content_block_delta" and event["index"] == 0]
            assert deltas == [{"type": "thinking_delta", "thinking": SIGNED_THINKING["thinking"]},
                              {"type": "signature_delta", "signature": SIGNED_THINKING["signature"]}]
            offered.insert(0, SIGNED_THINKING)
        follow = {**body, "stream": False, "messages": [*messages, {"role": "assistant", "content": offered}, result]}
        wrong_subject, _ = call(18090, "POST", "/v1/messages", foreign, follow, headers)
        wrong_session, _ = call(18090, "POST", "/v1/messages", token, follow,
                                {**headers, "x-session-id": str(uuid4())})
        changed = {**follow, "messages": [*messages, {"role": "assistant", "content": [
            *offered[:-1], {**tool, "input": {**ARGS, "key": "another-note"}}]}, result]}
        wrong_arguments, rejection = call(18090, "POST", "/v1/messages", token, changed, headers)
        rejected = wrong_subject, wrong_session, wrong_arguments, len(received)
        assert rejected == (400, 400, 422, 1), (rejected, rejection)
        with closing(connect(temporary / "gateway.db")) as database:
            stored = database.execute("SELECT tools FROM tui_native_turns WHERE tools IN (?, ?)",
                                      (json.dumps([NEW_ID]), "!" + json.dumps([NEW_ID]))).fetchall()
            # 公开拒绝完成时，正确回执已经可以重新认领，查询不等待后台归还。
            assert stored == [(json.dumps([NEW_ID]),)], stored
        if recover_pending:
            marker = ("--name=" + headers["x-session-id"]).encode()
            original, = [int(path.parent.name) for path in Path("/proc").glob("[0-9]*/cmdline")
                         if fixture_command_has(path, marker)]
            os.kill(original, SIGKILL)
            source = restart(source)
            assert not Path(f"/proc/{original}").exists()
            (binding_file,) = Path("/native/tui-workspaces").glob("*.json")
            original_id = json.loads(binding_file.read_text())["native_session_id"]
            projects = Path("/native/tui-sessions") / original_id / "home/.claude/projects"
            (original_file,) = projects.glob("*/" + original_id + ".jsonl")
            original_history = original_file.read_bytes()
            manage("PUT", f"accounts/{identifier}", {"client_system_prompt_policy": "user_reminder"})
            modified_system = {**follow, "system": "更改已经冻结的指令"}
            changed_policy, response = call(18090, "POST", "/v1/messages", token, modified_system, headers)
            assert changed_policy == 422 and len(received) == 1, (changed_policy, response, len(received))
            modified_effort = {**follow, "output_config": {"effort": "low"}}
            changed_effort, response = call(18090, "POST", "/v1/messages", token, modified_effort, headers)
            assert changed_effort == 422 and len(received) == 1, (changed_effort, response, len(received))
        if current_text_blocks:
            merged = {"role": "user", "content": QUESTION + QUESTION_TAIL}
            changed = {**follow, "messages": [*messages[:-1], merged, *follow["messages"][-2:]]}
            changed_blocks, response = call(18090, "POST", "/v1/messages", token, changed, headers)
            assert changed_blocks == 422 and len(received) == 1, (changed_blocks, response, len(received))
        if signed_tool_history:
            tampered = {**SIGNED_THINKING, "signature": "Y2hhbmdlZA=="}
            changed = {**follow, "messages": [*messages, {"role": "assistant", "content": [tampered, tool]}, result]}
            changed_signature, response = call(18090, "POST", "/v1/messages", token, changed, headers)
            assert changed_signature == 422 and len(received) == 1, (changed_signature, response, len(received))
        status, raw = call(18090, "POST", "/v1/messages", token, follow, headers)
        if signed_tool_history and recover_pending:
            # 固定 CLI 在本轮冷恢复的继续提示之后会裁掉签名。准备拒绝必须先于第二次模型投递。
            assert status == 422 and len(received) == 1, (status, raw, len(received))
            assert original_file.read_bytes() == original_history
            (first_attempt,) = verify_captures(manage, received, account_token)
            return {"cold_recovery_status": status, "changed_signature_status": changed_signature,
                    "model_posts": len(received), "original_history_preserved": True, "attempt": first_attempt}
        if status != 200:
            trace = [{key: row.get(key) for key in ("status_code", "outcome", "error_stage", "attempt_count")}
                     for row in manage("GET", "request-diagnostics")["items"]]
            raise AssertionError((status, raw, len(received), trace))
        final = json.loads(raw)
        assert final["content"] == [{"type": "text", "text": FINAL}]
        duplicate, _ = call(18090, "POST", "/v1/messages", token, follow, headers)
        assert duplicate == 400 and len(received) == 2, (duplicate, len(received))
        assert callbacks == [NEW_ID]
        if previous:
            ((role, old_receipt),) = find_blocks(received[1][1], "tool_use_id", NEW_ID)
            assert role == "user" and REPLY in json.dumps(old_receipt, ensure_ascii=False)
            assert any(lookup.get("tui_previous_release") == ["true"] for lookup in lookups[lookup_boundary:])
            wait_for(lambda: sender_state().get("idle"))
            with closing(connect(temporary / "gateway.db")) as database:
                wait_for(lambda: database.execute("SELECT count(*) FROM tui_native_turns WHERE tools IN (?, ?)",
                                                 (json.dumps([NEW_ID]), "!" + json.dumps([NEW_ID]))).fetchone()[0] == 0)
            stop(source)
            install_source()
            binding.update(generation=2, release_id=next_release)
            write_sender_config()
            binding["tui_predecessors"] = [old_binding]
            start_sender()
            wait_for(lambda: sender_state().get("ready") and sender_state().get("idle"))
            status, raw = call(18090, "POST", "/v1/messages", token, fresh, {**headers, "x-session-id": str(uuid4())})
            assert status == 200 and len(received) == 3, (status, raw, len(received))
            assert json.loads(raw)["content"] == [{"type": "text", "text": FINAL}]
            native = received[-1][1]
            assert any("You are Claude Code" in block["text"] for block in native["system"])
            assert any(tool["name"] == NATIVE_TOOL_NAME for tool in native["tools"])
            assert sum(block.get("text") == AFTER_RESTART for row in native["messages"] for block in blocks(row)) == 1
            assert not find_blocks(native, "tool_use_id", NEW_ID)
            (new_attempt,) = verify_captures(manage, received[-1:], account_token)
            assert new_attempt["ingress_body_sha256"] == sha256(encoded(fresh)).hexdigest()
            assert new_attempt["cli_and_https_body_sha256"] != new_attempt["ingress_body_sha256"]
            return {"old_release": release, "next_release": next_release, "new_before_drain": premature,
                    "wrong_subject": wrong_subject, "wrong_session": wrong_session,
                    "changed_arguments": wrong_arguments, "duplicate": duplicate,
                    "old_release_tool_callbacks": 1, "historical_tool_callbacks": 0,
                    "old_model_posts": 2, "new_model_posts": 1,
                    "new_attempt": new_attempt}
        verify_model(received, policy=tool_policy or "append", old_content=old_result, current_text_blocks=current_text_blocks)
        captures = verify_captures(manage, received, account_token)
        for attempt, request_body, reply_id, model_id in zip(
            captures, (body, follow), (events[0]["message"]["id"], final["id"]),
            ("msg_cold_tool", "msg_cold_reply"), strict=True,
        ):
            assert attempt["ingress_body_sha256"] == sha256(encoded(request_body)).hexdigest()
            assert attempt["cli_and_https_body_sha256"] != attempt["ingress_body_sha256"]
            attempt.update(client_message_id=reply_id, model_message_id=model_id)
        proof = {"model_posts": len(received), "client_tool_calls": callbacks, "old_tool_calls": 0,
                 "current_question_count": 1, "old_question_roles": [role for role, _ in HISTORY],
                 "foreign_receipt_status": wrong_subject, "wrong_session_status": wrong_session,
                 "changed_tool_arguments_status": wrong_arguments,
                 "duplicate_receipt_status": duplicate, "tls_versions": [tls for _, _, tls in received],
                 "proxy_connections": len(proxy_targets), "attempts": captures}
        if history_tool_blocks:
            proof["historical_tool_result_blocks"] = len(old_result)
        if current_text_blocks:
            proof.update(current_text_blocks=2, changed_current_blocks_status=changed_blocks)
        if signed_tool_history:
            hydrated = find_blocks(received[1][1], "type", "thinking")
            assert hydrated == [("assistant", SIGNED_THINKING)], (
                hydrated, [(row["role"], [block["type"] for block in blocks(row)]) for row in received[1][1]["messages"]],
            )
            proof.update(observed_signature_preserved=True, changed_signature_status=changed_signature)
        if toggle_pending_policy:
            proof["pending_policy"] = "append"
        if tool_policy:
            proof["tool_policy"] = tool_policy
        if recover_pending:
            assert original_file.read_bytes() == original_history
            _, native_recovery, _ = received[-1]
            assert all(document["output_config"]["effort"] == "medium" for _, document, _ in received)
            restored_id = json.loads(native_recovery["metadata"]["user_id"])["session_id"]
            assert restored_id != original_id and (original_file.parent / (restored_id + ".jsonl")).is_file()
            restored_text = [(row["role"], block.get("text")) for row in native_recovery["messages"] for block in blocks(row)]
            assert restored_text.count(("user", "Continue from where you left off.")) == 1
            proof["recovered_pending_tool"] = {"changed_system_http": changed_policy, "frozen_policy": "append",
                                              "changed_effort_http": changed_effort, "frozen_effort": "medium",
                                              "old_session_id": original_id, "recovered_session_id": restored_id,
                                              "original_history_preserved": True}
        if restart_history:
            wait_for(lambda: sender_state().get("idle"))
            (binding_file,) = Path("/native/tui-workspaces").glob("*.json")
            binding_bytes = binding_file.read_bytes()
            native_id = json.loads(binding_bytes)["native_session_id"]
            assert all(json.loads(document["metadata"]["user_id"])["session_id"] == native_id
                       for _, document, _ in received)
            cli_config = Path("/native/tui-sessions") / native_id / "home/.claude"
            (history_file,) = (cli_config / "projects").glob("*/" + native_id + ".jsonl")
            original = history_file.read_bytes()
            imported_rows = [json.loads(line) for line in original.splitlines()[:len(messages) - 1]]
            imported = [row["message"] for row in imported_rows]
            assert imported == [{"role": row["role"], "content": blocks(row)} for row in messages[:-1]]
            divergent = "H1：分叉历史中的项目名是水杉。"
            branch = {**body, "stream": False,
                      "messages": [{"role": "user", "content": divergent}, *messages[1:-1],
                                   {"role": "user", "content": AFTER_RESTART}]}
            # 以生产导入器模拟分叉已落盘、当前问题尚未交给 CLI 时重启发送器。
            staged_id = stage_history_branch(cli_config, imported_rows[0]["cwd"], native_id, branch)
            assert staged_id != native_id
            staged_path = history_file.with_name(staged_id + ".jsonl")
            staged_bytes = staged_path.read_bytes()
            assert set(history_file.parent.glob("*.jsonl")) == {history_file, staged_path}
            restarted = restart(source)
            expected_history = [("user", divergent), *HISTORY[1:]]
            history_texts = {text for _, text in expected_history}
            branch_ids = []
            snapshots = {history_file: original}
            followup_ids = []
            for post in (3, 4):
                status, raw = call(18090, "POST", "/v1/messages", token, branch, headers)
                assert status == 200 and len(received) == post, (status, raw, len(received))
                assert json.loads(raw)["content"] == [{"type": "text", "text": FINAL}]
                model_body = received[-1][1]
                texts = [(row["role"], b.get("text")) for row in model_body["messages"] for b in blocks(row)]
                assert [(role, text) for role, text in texts if text in history_texts] == expected_history
                assert texts.count(("user", AFTER_RESTART)) == 1 and not {QUESTION, HISTORY[0][1], FINAL} & {
                    text for _, text in texts
                }
                assert find_blocks(model_body, "id", PAST_ID) and find_blocks(model_body, "tool_use_id", PAST_ID)
                wait_for(lambda: sender_state().get("idle"))
                assert all(path.read_bytes() == data for path, data in snapshots.items())
                branch_id = json.loads(model_body["metadata"]["user_id"])["session_id"]
                branch_ids.append(branch_id)
                path = history_file.parent / (branch_id + ".jsonl")
                assert not list(cli_config.glob("history-replay-*"))
                if post == 3:
                    assert branch_id == staged_id
                    completed = path.read_bytes()
                    assert completed.startswith(staged_bytes) and len(completed) > len(staged_bytes)
                    snapshots[path] = completed
                    restart(restarted)
                else:
                    assert branch_id != native_id and path.is_file()
                followup_ids.append(json.loads(raw)["id"])
            archives = set(history_file.parent.glob("*.jsonl"))
            assert archives == {history_file, staged_path, path}
            assert len(set(followup_ids)) == 2
            assert list(binding_file.parent.glob("*.json")) == [binding_file]
            assert binding_file.read_bytes() == binding_bytes
            assistant_fields = sorted(next(row for row in imported if row["role"] == "assistant"))
            proof["restart"] = {"bound_session_id": native_id, "branch_session_ids": branch_ids,
                                "staged_branch_session_id": staged_id,
                                "binding_preserved": True,
                                "assistant_history_fields": assistant_fields,
                                "archive_count_after_repeat": len(archives),
                                "repeat_client_message_ids": followup_ids,
                                "preserved_bytes": [len(data) for data in snapshots.values()],
                                "additional_model_posts": 2,
                                "attempts": verify_captures(manage, received[-2:], account_token)}
        return proof


def stage_history_branch(config, work, native_id, body):
    """在原账号权限下发布尚未推进的分叉。
    @param config 原绑定的 CLI 配置目录。@param work 已验证对话的工作目录。
    @param native_id 已登记原生 UUID。@param body 即将从公开入口提交的确认历史。
    @return 生产导入器选中的分叉 UUID。
    """
    command = (
        "import json, sys\n"
        "from pathlib import Path\n"
        "sys.path.insert(0, '/opt/flower/tui')\n"
        "from tui_cold_history import ColdHistory\n"
        "plan = ColdHistory.from_request(json.load(sys.stdin))\n"
        "print(plan.import_session(Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3]))\n"
    )
    output = run([executable, "-I", "-B", "-c", command, str(config), work, native_id],
                 input=encoded(body), stdout=PIPE, user=1001, group=1001, extra_groups=[],
                 env={}, check=True, timeout=10)
    return output.stdout.decode().strip()


def verify_text_inputs(manage, token, account_token, headers, history, received, *, policy="append",
                       current_text_blocks=False):
    """核对模型端的默认原生指令及用户提供的文本。
    @param manage 临时管理接口。@param token 合成客户端。@param account_token 合成账号授权。
    @param headers 同一个客户端会话。@param history 合成的已确认旧问答。@param received 独立 HTTPS 实收。
    @param policy 管理端冻结的系统提示词动作。@param current_text_blocks 是否核对当前消息的文本分块。
    @return 各输入形状的复跑证据。
    """
    cases = [
        ("omitted", None, []),
        ("empty_string", "", []),
        ("empty_array", [], history),
        ("multiple_blocks", [{"type": "text", "text": part} for part in SYSTEM], history),
    ]
    if policy != "append":
        cases.append(("nonempty_string", "\n".join(SYSTEM), []))
    requests = []
    native_ids = set()
    start = len(received)
    for index, (name, system, earlier) in enumerate(cases):
        question = f"纯文本首轮问题 {policy}-{index}"
        tail = f"本轮第二个独立文本块 {policy}-{index}"
        current = ([{"type": "text", "text": text} for text in (question, tail)]
                   if current_text_blocks else question)
        body = {"model": MODEL, "max_tokens": 128, "stream": False,
                "messages": [*earlier, {"role": "user", "content": current}]}
        if system is not None:
            body["system"] = system
        status, raw = call(18090, "POST", "/v1/messages", token, body, headers)
        assert status == 200 and len(received) == start + index + 1, (name, status, raw, len(received))
        reply = json.loads(raw)
        _, native, _ = received[start + index]
        assert reply["content"] == [{"type": "text", "text": FINAL}]
        system_blocks = [b["text"] for b in native["system"]]
        joined = "\n".join(system_blocks)
        assert "You are Claude Code" in joined and "billing" in joined.lower()
        explicit = name in ("multiple_blocks", "nonempty_string")
        reminder = policy == "user_reminder" and explicit
        if policy == "replace" and name != "omitted":
            assert system_blocks[2:] == (["\n".join(SYSTEM)] if explicit else []), (name, system_blocks)
        else:
            assert len(system_blocks) > 2
        assert all(joined.count(part) == int(explicit and not reminder) for part in SYSTEM)
        if explicit and not reminder:
            assert joined.index(SYSTEM[0]) < joined.index(SYSTEM[1])
        texts = [(row["role"], b.get("text")) for row in native["messages"] for b in blocks(row)]
        user_questions = [text for role, text in texts if role == "user" and isinstance(text, str) and question in text]
        assert len(user_questions) == 1 and user_questions[0].count(question) == 1 and not native.get("tools"), name
        if current_text_blocks:
            assert user_questions == [question] and texts.count(("user", tail)) == 1
            assert texts[texts.index(("user", question)) + 1] == ("user", tail)
        reminders = [row for row in native["messages"]
                     if any(SYSTEM[0] in b.get("text", "") for b in blocks(row))]
        assert len(reminders) == int(reminder)
        if reminder:
            message, = reminders
            assert message["role"] == "user"
            content = "\n".join(b.get("text", "") for b in blocks(message))
            assert all(content.count(part) == 1 for part in SYSTEM) and content.index(SYSTEM[0]) < content.index(SYSTEM[1])
            assert (HISTORY[0][1] if earlier else question) in content
        earlier_texts = {text for _, text in HISTORY}
        assert [(role, text) for role, text in texts if text in earlier_texts] == (HISTORY if earlier else []), name
        assert [text for _, text in texts if isinstance(text, str) and text.startswith("纯文本首轮问题 ")] == user_questions
        native_id = json.loads(native["metadata"]["user_id"])["session_id"]
        assert native_id not in native_ids
        native_ids.add(native_id)
        requests.append({"case": name, "body_sha256": sha256(encoded(body)).hexdigest(), "client_message_id": reply["id"]})
    for info, attempt in zip(requests, verify_captures(manage, received[start:], account_token), strict=True):
        assert info["body_sha256"] == attempt["ingress_body_sha256"]
        info.update(attempt)
    return {"text_inputs": requests, "model_posts": len(received) - start}


def blocks(row):
    """读取模型端实际内容块。@param row 模型消息。@return 内容块序列。"""
    return row["content"] if isinstance(row["content"], list) else [{"type": "text", "text": row["content"]}]


def verify_output_effort(manage, token, account_token, headers, received):
    """按 HTTPS 模型实收核对本轮原生输出参数。
    @param manage 管理入口。@param token 客户端。@param account_token 合成账号授权。
    @param headers 公开会话。@param received 模型实收。@return 各组核对结果。
    """
    outcomes = []
    for index, effort in enumerate(("low", "medium", "high", "max"), 1):
        question = f"合成推理强度用例 {index}"
        body = {"model": MODEL, "max_tokens": 127 + index, "stream": False,
                "output_config": {"effort": effort}, "messages": [{"role": "user", "content": question}]}
        if index == 1:
            body["thinking"] = {"type": "disabled"}
        status, raw = call(18090, "POST", "/v1/messages", token, body, headers)
        assert status == 200 and len(received) == index, (status, raw, len(received))
        _, native, _ = received[-1]
        assert native["output_config"]["effort"] == effort and native["max_tokens"] == body["max_tokens"]
        if index == 1:
            assert native["thinking"] == body["thinking"]
        texts = [block.get("text") for row in native["messages"] for block in blocks(row)]
        assert texts.count(question) == 1
        outcomes.append({"effort": effort, "max_tokens": native["max_tokens"],
                         "body_sha256": sha256(encoded(body)).hexdigest()})
    for outcome, attempt in zip(outcomes, verify_captures(manage, received, account_token), strict=True):
        assert outcome["body_sha256"] == attempt["ingress_body_sha256"]
        outcome.update(attempt)
    return {"output_effort": outcomes, "model_posts": len(received)}


def verify_history_images(manage, token, account_token, account_id, headers, received, *, all_formats):
    """核对历史用户图像与新问题的真实出站。
    @param manage 管理接口。@param token 公共令牌。@param account_token 合成账号凭据。
    @param account_id 当前账号。@param headers 固定公开会话。@param received 模型实收。
    @param all_formats 是否同时校验 JPEG、GIF、WebP。@return 测试摘要。
    """
    images = {"image/png": "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+j4uoAAAAASUVORK5CYII="}
    if all_formats:
        images.update({
            "image/jpeg": "/9j/4AAQSkZJRgABAQAAAQABAAD/2wBDAAgGBgcGBQgHBwcJCQgKDBQNDAsLDBkSEw8UHRofHh0aHBwgJC4nICIsIxwc"
                          "KDcpLDAxNDQ0Hyc5PTgyPC4zNDL/wAALCAACAAIBAREA/8QAFAABAAAAAAAAAAAAAAAAAAAABv/EABQQAQAAAAAAAA"
                          "AAAAAAAAAAAAD/2gAIAQEAAD8AQP/Z",
            "image/gif": "R0lGODdhAgACAIEAAKCgoAAAAAAAAAAAACwAAAAAAgACAAAIBgABCAQQEAA7",
            "image/webp": "UklGRiQAAABXRUJQVlA4IBgAAAAwAQCdASoCAAIAAUAmJaQAA3AA/u2oAAA=",
        })
    image_blocks = [{"type": "image", "source": {"type": "base64", "media_type": media_type, "data": data}}
                    for media_type, data in images.items()]
    history = [{"role": "user", "content": [{"type": "text", "text": HISTORY[0][1]}, *image_blocks]},
               {"role": "assistant", "content": HISTORY[1][1]}]
    cases = []
    for index, policy in enumerate(("append", "user_reminder"), 1):
        manage("PUT", f"accounts/{account_id}", {"client_system_prompt_policy": policy})
        question = f"确认上一轮保留的图像 {index}"
        body = {"model": MODEL, "max_tokens": 128, "stream": False, "system": SYSTEM[0],
                "messages": [*history, {"role": "user", "content": question}]}
        status, raw = call(18090, "POST", "/v1/messages", token, body, headers)
        assert status == 200 and len(received) == index, (status, raw, len(received))
        _, native, _ = received[-1]
        rows = native["messages"]
        row, = [row for row in rows if any(block["type"] == "image" for block in blocks(row))]
        assert row["role"] == "user" and [block for block in blocks(row) if block["type"] == "image"] == image_blocks
        assert blocks(row)[0] == history[0]["content"][0]
        texts = [(message["role"], block.get("text")) for message in rows for block in blocks(message)]
        assert texts.count(("assistant", HISTORY[1][1])) == 1 and texts.count(("user", question)) == 1
        in_system = "\n".join(block["text"] for block in native["system"])
        assert in_system.count(SYSTEM[0]) == (policy == "append")
        assert json.dumps(row, ensure_ascii=False).count(SYSTEM[0]) == (policy == "user_reminder")
        cases.append({"policy": policy, "body_sha256": sha256(encoded(body)).hexdigest()})
    for case, capture in zip(cases, verify_captures(manage, received, account_token), strict=True):
        assert case["body_sha256"] == capture["ingress_body_sha256"]
        case.update(capture)
    return {"history_images" if all_formats else "history_png": cases,
            "formats": list(images), "model_posts": len(received)}


def fixture_command_has(path, argument):
    """仅比较隔离夹具的进程标记。@param path 进程参数。@param argument 合成会话标记。@return 是否匹配。"""
    try:
        return argument in path.read_bytes().split(b"\0")
    except (FileNotFoundError, PermissionError, ProcessLookupError):
        return False


def find_blocks(body, key, identifier):
    """按真实模型输入中的公开 ID 核对旧工具及续轮。@param body 模型正文。@param key ID 字段。
    @param identifier 合成调用 ID。@return 含所属角色的匹配块。
    """
    return [(row["role"], b) for row in body["messages"] for b in blocks(row) if b.get(key) == identifier]


def verify_model(received, *, policy, old_content, current_text_blocks=False):
    """检验历史、系统提示、原生动态 MCP 和续轮。@param received HTTPS 实收。
    @param policy 原工具轮的有效动作。@param old_content 已确认的旧工具结果。
    @param current_text_blocks 是否包含分块问题。@return 无。
    """
    (_, first, _), (_, second, _) = received
    for body in (first, second):
        assert body["max_tokens"] == 128, body["max_tokens"]
        system_blocks = [b["text"] for b in body["system"]]
        system = "\n".join(system_blocks)
        assert "You are Claude Code" in system and "billing" in system.lower()
        if policy == "user_reminder":
            assert all(part not in system for part in SYSTEM)
            row, = [row for row in body["messages"] if any(SYSTEM[0] in b.get("text", "") for b in blocks(row))]
            user = "\n".join(b.get("text", "") for b in blocks(row))
            assert row["role"] == "user" and HISTORY[0][1] in user
            assert all(user.count(part) == 1 for part in SYSTEM) and user.index(SYSTEM[0]) < user.index(SYSTEM[1])
        else:
            assert all(system.count(part) == 1 for part in SYSTEM) and system.index(SYSTEM[0]) < system.index(SYSTEM[1])
            if policy == "replace":
                assert system_blocks[2:] == ["\n".join(SYSTEM)]
        messages = [(row["role"], b.get("text")) for row in body["messages"] for b in blocks(row)]
        history_texts = {text for _, text in HISTORY}
        assert [(role, text) for role, text in messages if text in history_texts] == HISTORY
        assert messages.count(("user", QUESTION)) == 1
        if current_text_blocks:
            assert messages.count(("user", QUESTION_TAIL)) == 1
            index = messages.index(("user", QUESTION))
            assert messages[index + 1] == ("user", QUESTION_TAIL)
        (old,) = find_blocks(body, "id", PAST_ID)
        (old_result,) = find_blocks(body, "tool_use_id", PAST_ID)
        assert old == ("assistant", {"type": "tool_use", "id": PAST_ID, "name": "OldNote", "input": ARGS})
        assert old_result[0] == "user" and old_result[1]["content"] == old_content
        (tool,) = [t for t in body["tools"] if t.get("description") == TOOL["description"]]
        assert tool["name"] == NATIVE_TOOL_NAME and tool["input_schema"] == TOOL["input_schema"]
    assert not find_blocks(first, "id", NEW_ID) and not find_blocks(first, "tool_use_id", NEW_ID)
    (new,) = find_blocks(second, "id", NEW_ID)
    (reply,) = find_blocks(second, "tool_use_id", NEW_ID)
    assert new[0] == "assistant" and new[1]["name"] == NATIVE_TOOL_NAME and new[1]["input"] == ARGS
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
    parser.add_argument("--current-text-blocks", action="store_true")
    parser.add_argument("--signed-tool-history", action="store_true")
    scenario = parser.add_mutually_exclusive_group()
    scenario.add_argument("--restart-history", action="store_true")
    scenario.add_argument("--text-input", action="store_true")
    scenario.add_argument("--system-policy", action="store_true")
    scenario.add_argument("--toggle-pending-policy", action="store_true")
    scenario.add_argument("--tool-policy", choices=("replace", "user_reminder"))
    scenario.add_argument("--recover-pending-tool", action="store_true")
    scenario.add_argument("--output-effort", action="store_true")
    scenario.add_argument("--history-png", action="store_true")
    scenario.add_argument("--history-images", action="store_true")
    scenario.add_argument("--history-tool-blocks", action="store_true")
    scenario.add_argument("--mixed-release", nargs=3, type=Path,
                          metavar=("OLD_SOURCE", "OLD_GATEWAY", "OLD_SENDER"))
    scenario.add_argument("--failure-boundaries", action="store_true")
    args = parser.parse_args()
    if (not Path("/.dockerenv").exists() or {name for _, name in if_nameindex()} != {"lo"}
            or Path("/run/v3/sender.json").exists() or any(Path("/native").glob("*"))):
        raise RuntimeError("请在空白的 docker --network none 账号容器中运行")
    install_source(args.mixed_release[0] if args.mixed_release else ROOT)
    with TemporaryDirectory(prefix="cold-history-") as directory:
        proof = verify(args.gateway, args.sender, Path(directory),
                       restart_history=args.restart_history, text_input=args.text_input,
                       system_policy=args.system_policy, toggle_pending_policy=args.toggle_pending_policy,
                       tool_policy=args.tool_policy, recover_pending=args.recover_pending_tool,
                       output_effort=args.output_effort, history_png=args.history_png,
                       history_images=args.history_images, history_tool_blocks=args.history_tool_blocks,
                       previous=args.mixed_release,
                       failure_boundaries=args.failure_boundaries, current_text_blocks=args.current_text_blocks,
                       signed_tool_history=args.signed_tool_history)
        print(json.dumps(proof, ensure_ascii=False))


if __name__ == "__main__":
    main()
