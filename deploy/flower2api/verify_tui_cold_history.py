"""用真实网关、账号事件源与 2.1.293 CLI 验收公开 Messages 冷导入。"""

import argparse
from base64 import b64encode
from contextlib import ExitStack, closing, suppress
from copy import deepcopy
from datetime import datetime, timezone
from faulthandler import dump_traceback
from fcntl import LOCK_EX, flock
from hashlib import sha256
from http.client import HTTPConnection, HTTPException
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
from re import fullmatch
from secrets import token_hex
from shutil import copy2, copytree
from signal import SIGKILL
from socket import SHUT_RDWR, create_connection, if_nameindex
from sqlite3 import connect
import ssl
from struct import pack
from subprocess import PIPE, Popen, run
from sys import executable, stderr
from tempfile import TemporaryDirectory
from threading import Event, Timer
from time import monotonic, monotonic_ns, sleep, time_ns
from urllib.parse import parse_qs, urlencode, urlsplit
from uuid import UUID, uuid4
from zlib import compress, crc32

from fixtures.native_model_send.agent_progress import model_reply as agent_progress_model_reply, verify_agent_progress
from fixtures.native_model_send.fixture_tunnel import _relay
from fixtures.native_model_send.stock_messages import (
    POLICIES as STOCK_POLICIES,
    model_reply as stock_model_reply,
    verify_stock_client,
)
from fixtures.native_model_send.tui_startup_trace import MODEL_BODY_TRACE, THINKING_SUMMARIES_SETTING, startup_event
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
HISTORY_CACHE = ({"type": "ephemeral", "ttl": "1h"}, {"type": "ephemeral"})
QUESTION = "NOW：查询新便签并回答。"
QUESTION_TAIL = "NOW：保留本轮问题第二段。"
AFTER_RESTART = "RESTART：从已确认的旧问答开启另一轮。"
DROP_REPLY = "FAILURE：模型收到正文后关闭响应连接。"
REJECT_MODEL_REQUEST = "FAILURE：模型收到正文后返回合成拒绝。"
SLOW_MODEL_DELAY = 4.25
SYSTEM = ["RULE1：你是便签助手。", "RULE2：请只使用已声明的工具。"]
PAST_ID = "toolu_past_fixture"
PAST_SECOND_ID = "toolu_past_second_fixture"
NEW_ID = "toolu_cold_fixture"
SECOND_ID = "toolu_second_cold_fixture"
RECONNECT_ID = "toolu_reconnect_cold_fixture"
SIGNED_THINKING = {"type": "thinking", "thinking": "隔离模型的合成思考段。", "signature": "c2lnbmF0dXJlLWZpeHR1cmU="}
ADAPTIVE_THINKING = {"type": "adaptive", "display": "updates"}
THINKING_UPDATES_BETA = "thinking-display-updates-2026-08-18"
THINKING_DISPLAY_DEFAULTS = {MODEL: "summarized", "claude-opus-5-5": "omitted"}
STRUCTURED_FORMAT = {"type": "json_schema", "schema": {
    "type": "object", "properties": {"fixture_order_status": {"type": "string", "enum": ["ready"]}},
    "required": ["fixture_order_status"], "additionalProperties": False,
}}
STRUCTURED_REPLY = '{"fixture_order_status":"ready"}'
V1_RUNTIME_SHA256 = "017ec892b9dfbf08bf4cb2e5bf59048cb41a0ecfc21b1ad518751a23a911b9b7"
TOOL = {"name": "Lookup-Note", "description": "读取合成便签", "input_schema": {
    "type": "object", "required": ["key", "options"], "additionalProperties": False,
    "properties": {"key": {"type": "string"}, "options": {
        "type": "object", "properties": {"labels": {"type": "array", "items": {"type": "string"}}},
        "required": ["labels"], "additionalProperties": False,
    }},
}}
NATIVE_TOOL_NAME = "mcp__flower__" + TOOL["name"]
SECOND_TOOL = {**TOOL, "name": "Set-Tag", "description": "为合成便签设置标签"}
NATIVE_SECOND_TOOL_NAME = "mcp__flower__" + SECOND_TOOL["name"]
PARALLEL_SECOND_TOOL = {**SECOND_TOOL, "input_schema": {
    "type": "object", "required": ["tag_id", "active"], "additionalProperties": False,
    "properties": {"tag_id": {"type": "integer"}, "active": {"type": "boolean"}},
}}
ARGS = {"key": "synthetic-note", "options": {"labels": ["项目", "便签"]}}
SECOND_ARGS = {**ARGS, "key": "synthetic-other"}
PARALLEL_SECOND_ARGS = {"tag_id": 74, "active": False}
REPLY = "CLIENT：合成便签内容"
SECOND_REPLY = "SECOND：客户端工具合成错误"
RECONNECT_PREFIX = "续轮在断开前已经交付的合成文本。"
FINAL = "模型已收到本次客户端回执。"
TITLE_TEXT = "隔离标题用量对照"
TITLE_REPLY = json.dumps({"title": TITLE_TEXT}, ensure_ascii=False, separators=(",", ":"))
AUXILIARY_USAGE = (31, 7)
SUGGESTION_REPLY = "summarize the synthetic note next"
FORCED_CHOICES = {"any": {"type": "any"}, "named": {"type": "tool", "name": SECOND_TOOL["name"]}}


def response_json(handler, payload, *, status=200):
    """写入合成 JSON 响应。@param handler 当前连接。@param payload 响应对象。
    @param status 该隔离服务的实际状态。@return 无。
    """
    raw = json.dumps(payload).encode()
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Content-Length", str(len(raw)))
    handler.end_headers()
    handler.wfile.write(raw)


class QuietHandler(BaseHTTPRequestHandler):
    """回环夹具保持输出为最终核对摘要。"""

    def log_message(self, *_):
        """省略验收请求日志。@return 无。"""


def install_source(root=ROOT, *, trace_startup=False, cache_capability=None, thinking_cli_summaries=None):
    """安装配套事件源。@param root 检出目录。@param trace_startup 是否启用隔离观测。
    @param cache_capability 可选的 CLI 缓存探针模式。@param thinking_cli_summaries 可选的 CLI 摘要设置。
    @return 无。
    """
    target = Path("/opt/flower/tui")
    for file in (root / "images/account").glob("tui_*.py"):
        copy2(file, target / file.name)
    copytree(root / "images/account/tui-mod", target / "tui-mod", dirs_exist_ok=True)
    for name in ("runtime_files.py", "tui_workspace_launch.py", "tui_capacity.py"):
        copy2(root / "services/orchestrator" / name, target / name)
    if trace_startup:
        (target / "tui_source.py").rename(target / "fixture_tui_source.py")
        fixtures = ROOT / "deploy/flower2api/fixtures/native_model_send"
        copy2(fixtures / "tui_startup_trace.py", target / "tui_source.py")
        if thinking_cli_summaries is not None:
            (target / THINKING_SUMMARIES_SETTING).write_text(json.dumps(thinking_cli_summaries))
        if cache_capability in ("native-default", "native-no-auto"):
            (target / "tui_source.py").rename(target / "fixture_startup_trace.py")
            copy2(fixtures / "tui_cache_capability_probe.py", target / "tui_source.py")
            if cache_capability == "native-no-auto":
                (target / "fixture_disable_automatic_cache").touch()


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


def fixture_tool_sse(tool, *, with_signature, second=None, model=MODEL, thinking_text=SIGNED_THINKING["thinking"]):
    """交付隔离模型工具流。@param tool 原生工具调用。@param with_signature 是否先交付合成签名块。
    @param second 可选的同轮第二次工具调用。@param model 模型实际回复的身份，可省略。
    @param thinking_text 合成思考摘要，可为空。@return SSE。"""
    wire = message_sse(tool, "tool_use", "msg_cold_tool")
    if not with_signature and second is None and model == MODEL:
        return wire
    events = [json.loads(line[5:]) for line in wire.splitlines() if line.startswith(b"data:")]
    if model is None:
        events[0]["message"].pop("model")
    else:
        events[0]["message"]["model"] = model
    if second is not None:
        secondary = message_sse(second, "tool_use", "msg_fixture_unused")
        extra = [json.loads(line[5:]) for line in secondary.splitlines() if line.startswith(b"data:")]
        # 第二个调用的原始增量属于同一消息，放在该消息的终帧之前。
        events[-2:-2] = [{**event, "index": 1} for event in extra if "index" in event]
    if not with_signature:
        return b"".join(map(frame, events))
    for event in events:
        if "index" in event:
            event["index"] += 1
    signed = [{"type": "content_block_start", "index": 0, "content_block": {"type": "thinking", "thinking": ""}}]
    if thinking_text:
        signed.append({"type": "content_block_delta", "index": 0,
                       "delta": {"type": "thinking_delta", "thinking": thinking_text}})
    signed.extend([
        {"type": "content_block_delta", "index": 0, "delta": {"type": "signature_delta", "signature": SIGNED_THINKING["signature"]}},
        {"type": "content_block_stop", "index": 0},
    ])
    events[1:1] = signed
    return b"".join(map(frame, events))


def fixture_parallel_results(calls, callbacks):
    """按公开返回的调用执行两种合成工具，逆序交付结果。
    @param calls 从公开 SSE 重组的调用。@param callbacks 实际执行记录。@return 逆序的结果块。
    """
    def lookup_note(arguments):
        assert arguments == ARGS, arguments
        return REPLY

    def set_tag(arguments):
        assert arguments == PARALLEL_SECOND_ARGS, arguments
        raise ValueError(SECOND_REPLY)

    handlers = {TOOL["name"]: lookup_note, PARALLEL_SECOND_TOOL["name"]: set_tag}
    results = []
    for tool_call in calls:
        call_id = tool_call["id"]
        result = {"type": "tool_result", "tool_use_id": call_id}
        try:
            result["content"] = handlers[tool_call["name"]](tool_call["input"])
        except ValueError as error:
            result.update(content=str(error), is_error=True)
        callbacks.append(call_id)
        results.append(result)
    return list(reversed(results))


def fixture_reconnect_sse(name):
    """构造可在中间断开的同一模型流。@param name 模型收到的原生工具名。@return 首段与余下 SSE。"""
    message_id = "msg_cold_reconnect"
    text = message_sse({"type": "text", "text": RECONNECT_PREFIX}, "end_turn", message_id)
    tool = message_sse({"type": "tool_use", "id": RECONNECT_ID, "name": name, "input": SECOND_ARGS},
                       "tool_use", message_id)
    prefix = [json.loads(line[5:]) for line in text.splitlines() if line.startswith(b"data:")][:-2]
    tail = [json.loads(line[5:]) for line in tool.splitlines() if line.startswith(b"data:")][1:]
    for event in tail:
        if "index" in event:
            event["index"] += 1
    return b"".join(map(frame, prefix)), b"".join(map(frame, tail))


def fixture_thinking_display_sse(body, *, message_id="msg_cold_thinking_display"):
    """按实收的思考设置与模型默认值生成合成流。
    @param body 隔离模型实收。@param message_id 合成助手消息 ID。@return SSE 字节。
    """
    model = body["model"]
    display = body["thinking"].get("display", THINKING_DISPLAY_DEFAULTS[model])
    wire = message_sse({"type": "text", "text": FINAL}, "end_turn", message_id)
    events = [json.loads(line[5:]) for line in wire.splitlines() if line.startswith(b"data:")]
    events[0]["message"]["model"] = model
    for event in events:
        if "index" in event:
            event["index"] += 1
    thinking = [{"type": "content_block_start", "index": 0, "content_block": {"type": "thinking", "thinking": ""}}]
    if display == "summarized":
        thinking.append({"type": "content_block_delta", "index": 0,
                         "delta": {"type": "thinking_delta", "thinking": SIGNED_THINKING["thinking"]}})
    thinking.extend([
        {"type": "content_block_delta", "index": 0,
         "delta": {"type": "signature_delta", "signature": SIGNED_THINKING["signature"]}},
        {"type": "content_block_stop", "index": 0},
    ])
    events[1:1] = thinking
    return b"".join(map(frame, events))


def verify(gateway, sender, temporary, *, restart_history=False, text_input=False, system_policy=False,
           toggle_pending_policy=False, tool_policy=None, recover_pending=False, output_effort=False,
           history_png=False, history_images=False, history_tool_blocks=False, previous=None, failure_boundaries=False,
           current_text_blocks=False, signed_tool_history=False, signed_tool_response=None, split_history_tools=False,
           v1_runtime=None,
           parallel_tools=False, reconnect_tool_stream=False, current_images=False, current_image_ending="text",
           auto_tool_choice=False,
           adaptive_thinking_model=None, adaptive_thinking_display="updates", thinking_display_model=None,
           thinking_cli_summaries=None,
           recovery_ledger_contention=False, recovery_ledger_deadline=False, recovery_workspace_rejection=False,
           recovery_slow_model=False, initial_idle_model_connection=False, trace_startup=False, cache_markers=False,
           history_cache_markers=False, history_cache_ttl=None, history_cache_scope=None,
           cache_capability=None, message_system_roles=False,
           structured_output=False, forced_tool_choice=None, no_tool_choice=False, auxiliary_mode=None,
           auxiliary_kind="title", auxiliary_sample=None, agent_progress=None, stock_client=False):
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
    @param stock_client 是否通过真实外部 CLI 验证完整 V2 输入与工具回执。
    @param current_text_blocks 是否验证本轮文本块顺序及边界归属。
    @param signed_tool_history 是否核对隔离模型原工具轮的签名块。
    @param signed_tool_response 可选，模拟空思考正文或缺少助手模型的隔离响应。
    @param split_history_tools 是否将已闭合的旧工具组分为相邻消息。
    @param v1_runtime 固定 V1 制品，提供时仅验证 V1 内核的公开能力。
    @param parallel_tools 是否验证同一步多个新工具的回执。
    @param reconnect_tool_stream 是否在真实续轮流中断开再接回。
    @param current_images 是否用本轮原生图文替换纯文本问题。
    @param current_image_ending 本轮九块图文以文字或图片结尾。
    @param auto_tool_choice 是否核对显式自动选择和并行工具。
    @param adaptive_thinking_model 可选，核对显式 adaptive 的固定模型。
    @param adaptive_thinking_display 在工具首轮与续轮冻结的显式显示值。
    @param thinking_display_model 可选，核对普通 API 思考显示及客户端响应的固定模型。
    @param thinking_cli_summaries 可选，核对正式 CLI 摘要设置的隔离对照。
    @param recovery_ledger_contention 是否在提交原回执时短暂占用账号账本锁。
    @param recovery_ledger_deadline 是否持续持锁直至回执触发准入截止，然后重交。
    @param recovery_workspace_rejection 是否核对工作区绑定拒绝及原回执再次认领。
    @param recovery_slow_model 是否验证隔离模型收件后的公开超时和诊断归属。
    @param initial_idle_model_connection 是否先占用一个未握手的模型 TCP 连接。
    @param trace_startup 是否记录隔离启动阶段。
    @param cache_markers 是否核对普通 Messages 显式缓存标记的模型实收和出站归属。
    @param history_cache_markers 是否冻结历史标记并验证工具往返。
    @param history_cache_ttl 工具往返启用的平台历史断点时长。
    @param history_cache_scope 可选，强制 TTL 下使用仅嵌套或混合断点。
    @param cache_capability 对照生产入口或 CLI 提示词和工具的缓存标记能力。
    @param message_system_roles 消息级系统角色对照或普通 API 固定回归模式。
    @param structured_output 是否核对普通 API 的结构化输出和实际发送路径。
    @param forced_tool_choice 核对强制工具选择及同进程或重启回执。
    @param no_tool_choice 是否核对无工具时的显式 none 和保留声明的兼容路径。
    @param auxiliary_mode 可选，观察等待工具时的公开辅助轮投递或本地拦截。
    @param auxiliary_kind 标题或建议。@param auxiliary_sample 从官方 CLI 隔离运行导出的请求。
    @param agent_progress 已捕获父子轮与固定进度请求样本。
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
    inspect_model_body = (cache_markers or message_system_roles or thinking_display_model or structured_output
                          or forced_tool_choice or no_tool_choice)
    if inspect_model_body and v1_runtime is None:
        MODEL_BODY_TRACE.touch(mode=0o600, exist_ok=False)
        os.chown(MODEL_BODY_TRACE, 1001, 1001)
    certificates(temporary)
    config = Path("/run/v3/sender.json")
    copy2(temporary / "ca.der", config.with_name("verification-ca.der"))
    received, callbacks, proxy_targets = [], [], []
    auxiliary_received = []
    auxiliary_provider_sessions = []
    suggestion = auxiliary_kind == "suggestion"
    auxiliary_reply = SUGGESTION_REPLY if suggestion else TITLE_REPLY
    auxiliary_text = SUGGESTION_REPLY if suggestion else TITLE_TEXT
    slow_tool_arrivals = []
    model_betas = []
    summarized_thinking = adaptive_thinking_model is not None and adaptive_thinking_display == "summarized"
    signed_thinking_text = "" if signed_tool_response == "signature-only" else SIGNED_THINKING["thinking"]
    lookups = []
    deny_proxy = False
    denied_tunnels = []
    finish_stream = Event()
    stock_homes = tuple(temporary / f"stock-{policy}" for policy in STOCK_POLICIES) if stock_client else ()

    class Receiver(QuietHandler):
        """以生产主机名的临时证书接收原生请求，返回固定工具或文本。"""

        protocol_version = "HTTP/1.1"

        def do_POST(self):
            """验证合成凭据并返回同一轮 SSE。@return 无。"""
            accepted_path = (self.path == "/v1/messages"
                             or (v1_runtime is not None and self.path == "/v1/messages?beta=true"))
            if (not accepted_path
                    or self.headers.get("Authorization") != "Bearer " + account_token):
                self.send_error(403)
                return
            if trace_startup:
                startup_event("model_http_headers", peer_port=self.client_address[1])
            raw = self.rfile.read(int(self.headers["Content-Length"]))
            body = json.loads(raw)
            model_digest = sha256(raw).hexdigest()
            is_auxiliary = False
            if auxiliary_sample is not None:
                sample = auxiliary_sample["body"]
                if suggestion:
                    is_auxiliary = body["messages"][-1]["content"] == sample["messages"][-1]["content"]
                else:
                    is_auxiliary = body.get("output_config", {}).get("format") == sample["output_config"]["format"]
            (auxiliary_received if is_auxiliary else received).append((model_digest, body, self.connection.version()))
            if is_auxiliary:
                auxiliary_provider_sessions.append(self.headers.get("x-claude-code-session-id"))
            if trace_startup:
                startup_event("model_received", peer_port=self.client_address[1], model_posts=len(received),
                              **{f"{auxiliary_kind}_posts": len(auxiliary_received)},
                              model_body_sha256=model_digest)
            if v1_runtime is not None or message_system_roles or adaptive_thinking_model:
                model_betas.append(self.headers.get("anthropic-beta", ""))
            if failure_boundaries and any(block.get("text") == DROP_REPLY
                                          for row in body["messages"] for block in blocks(row)):
                self.close_connection = True
                return
            if failure_boundaries and any(block.get("text") == REJECT_MODEL_REQUEST
                                          for row in body["messages"] for block in blocks(row)):
                response_json(self, {"type": "error", "error": {
                    "type": "invalid_request_error", "message": "隔离模型明确拒绝合成请求",
                }}, status=400)
                return
            tool = next((t for t in body.get("tools", []) if t.get("description") == TOOL["description"]), None)
            results = find_blocks(body, "tool_use_id", NEW_ID)
            if recovery_slow_model and results:
                slow_tool_arrivals.append(monotonic())
                sleep(SLOW_MODEL_DELAY)
            restart = any(b.get("text") == AFTER_RESTART for row in body["messages"] for b in blocks(row))
            prefix = b""
            if stock_client:
                wire = stock_model_reply(body, stock_homes, FINAL)
            elif agent_progress:
                wire = agent_progress_model_reply(len(received) - 1, body, agent_progress, fixture_tool_sse, message_sse, frame)
            elif is_auxiliary:
                if auxiliary_mode == "tool-output":
                    frames = fixture_tool_sse({"type": "tool_use", "name": "Read", "id": "toolu_unexpected_suggestion",
                                               "input": {"file_path": "synthetic-note.txt"}}, with_signature=False)
                else:
                    frames = message_sse(
                        {"type": "text", "text": auxiliary_reply}, "end_turn", f"msg_interleaved_{auxiliary_kind}",
                    )
                events = [json.loads(line[5:]) for line in frames.splitlines() if line.startswith(b"data:")]
                events[0]["message"].update(
                    id=f"msg_interleaved_{auxiliary_kind}", model=body["model"],
                    usage={"input_tokens": AUXILIARY_USAGE[0], "output_tokens": 0},
                )
                events[-2]["usage"]["output_tokens"] = AUXILIARY_USAGE[1]
                wire = b"".join(map(frame, events))
            elif no_tool_choice:
                wire = message_sse({"type": "text", "text": FINAL}, "end_turn", "msg_cold_reply")
            elif forced_tool_choice:
                wire = fixture_forced_tool_sse(body)
            elif not results and tool and not restart and v1_runtime is None:
                content = {"type": "tool_use", "id": NEW_ID, "name": tool["name"], "input": ARGS}
                second = None
                if parallel_tools:
                    other, = [t for t in body["tools"] if t.get("description") == PARALLEL_SECOND_TOOL["description"]]
                    second = {"type": "tool_use", "id": SECOND_ID, "name": other["name"], "input": PARALLEL_SECOND_ARGS}
                response_model = None if signed_tool_response == "missing-model" else body["model"]
                wire = fixture_tool_sse(content, with_signature=signed_tool_history, second=second,
                                        model=response_model, thinking_text=signed_thinking_text)
            elif reconnect_tool_stream and results and not find_blocks(body, "tool_use_id", RECONNECT_ID):
                prefix, wire = fixture_reconnect_sse(tool["name"])
            elif thinking_display_model:
                wire = fixture_thinking_display_sse(body)
            elif summarized_thinking:
                wire = fixture_thinking_display_sse(body, message_id="msg_cold_reply")
            else:
                text = FINAL
                if structured_output and body.get("output_config", {}).get("format") == STRUCTURED_FORMAT:
                    text = STRUCTURED_REPLY
                wire = message_sse({"type": "text", "text": text}, "end_turn", "msg_cold_reply")
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Content-Length", str(len(prefix) + len(wire)))
            self.end_headers()
            if prefix:
                self.wfile.write(prefix)
                self.wfile.flush()
                # 公开读者须实际读到首段并在模型结束前断开。夹具结束时也会释放模型。
                if not finish_stream.wait(30):
                    self.close_connection = True
                    return
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
            if trace_startup:
                startup_event("proxy_connect_accepted", peer_port=self.client_address[1])
            with create_connection(("127.0.0.1", receiver.server_port), timeout=10) as target:
                if trace_startup:
                    startup_event("proxy_model_tcp_connected", peer_port=target.getsockname()[1])
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

    class TracedServer(ThreadingHTTPServer):
        """记录监听线程接收 TCP 的时点，握手由请求线程完成。"""

        def __init__(self, handler, stage):
            """设置探针边界。@param handler 回环处理器。@param stage 接收阶段。@return 无。"""
            self.stage = stage
            super().__init__(("127.0.0.1", 0), handler)

        def get_request(self):
            """保留原 accept 结果。@return 已接受的连接与对端地址。"""
            connection, peer = super().get_request()
            startup_event(self.stage, peer_port=peer[1])
            return connection, peer

    with ExitStack() as stack:
        receiver = (TracedServer(Receiver, "model_tcp_accepted") if trace_startup
                    else ThreadingHTTPServer(("127.0.0.1", 0), Receiver))
        tls = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        tls.load_cert_chain(temporary / "leaf.pem", temporary / "leaf.key")
        # 握手由已接收连接的工作线程完成，空闲 TCP 不会占住监听线程。
        receiver.socket = tls.wrap_socket(receiver.socket, server_side=True, do_handshake_on_connect=False)
        serve(stack, receiver)
        stack.callback(finish_stream.set)
        proxy = serve(stack, TracedServer(Proxy, "proxy_tcp_accepted") if trace_startup
                      else ThreadingHTTPServer(("127.0.0.1", 0), Proxy))
        registry = serve(stack, ThreadingHTTPServer(("127.0.0.1", 0), Registry))
        proxy_url = f"http://127.0.0.1:{proxy.server_port}"

        def write_sender_config():
            state = {"binding": binding, "proxy_url": proxy_url, "allowed_origin": "https://api.anthropic.com"}
            if not inspect_model_body:
                state["native_capture_dir"] = "/flows/api/cc-prepared"
            if v1_runtime is None:
                state["tui_v2"] = {"max_reservations": 4}
            else:
                state.update(native={"binary_path": str(v1_runtime), "work_root": "/native/workers",
                                     "memory_mib": 0, "max_workers": 4}, native_adaptive_prewarm=False)
            config.write_text(json.dumps(state))
            config.chmod(0o640)
            os.chown(config, 0, 1001)

        write_sender_config()
        common = {"PATH": os.defpath, "LANG": "C.UTF-8", "HOME": "/tmp", "TOKIO_WORKER_THREADS": "2"}

        def start_sender(program=sender):
            tui = {"V3_TUI_SESSION_HOST": "1", "V3_TUI_MANAGED_OAUTH": "1"} if v1_runtime is None else {}
            process = Popen([program], user=1001, group=1001, extra_groups=[], env={
                **common, **tui, "RUST_LOG": "warn", "V3_SENDER_CONFIG": str(config),
                "FLOWER_V2_STARTUP_TRACE": str(int(trace_startup)),
            })
            stack.callback(stop, process)
            return process

        def start_gateway(program, version, **gate):
            process = Popen([program], cwd=temporary, env={
                **common, "SERVER_PORT": "18090", "SERVER_HOST": "127.0.0.1", "DATABASE_DRIVER": "sqlite",
                "DATABASE_DSN": str(temporary / "gateway.db"), "ADMIN_PASSWORD": admin,
                "V3_INTERNAL_TOKEN": internal, "V3_DEPLOYMENT_ID": deployment,
                "V3_RELEASE": version, "V3_RUNTIME_URL": f"http://127.0.0.1:{registry.server_port}",
                "LOG_LEVEL": "warn", "FLOWER_V2_STARTUP_TRACE": str(int(trace_startup)), **gate,
            })
            stack.callback(stop, process)
            wait_for(lambda: call(18090, "GET", "/admin/accounts", admin)[0] == 200)
            return process

        source = start_sender(previous[2] if previous else sender)
        control = start_gateway(previous[1] if previous else gateway, release)

        def sender_state():
            return json.loads(call(8091, "GET", "/internal/status", secret)[1]).get("tui_v2", {})

        def sender_state_after_failure():
            # 首先保留公开故障。这次额外读取有独立预算，不能把夹具失败再挂住 30 秒。
            with closing(HTTPConnection("127.0.0.1", 8091, timeout=1)) as connection:
                connection.request("GET", "/internal/status", headers={"Authorization": "Bearer " + secret})
                response = connection.getresponse()
                if response.status != 200:
                    raise ValueError("无法读取隔离发送器状态")
                return json.loads(response.read()).get("tui_v2", {})

        def ready_sender(process, phase, *, require_idle=False):
            def observe():
                state = sender_state()
                return state if state.get("ready") and (not require_idle or state.get("idle")) else None

            state = wait_for(observe)
            if trace_startup:
                startup_event("sender_ready", phase=phase, sender_pid=process.pid,
                              ready=state["ready"], idle=state.get("idle"))

        def restart(process, phase):
            wait_for(lambda: sender_state().get("idle"))
            if trace_startup:
                startup_event("sender_stop_requested", phase=phase, sender_pid=process.pid)
            stop(process)
            if trace_startup:
                startup_event("sender_exited", phase=phase, sender_pid=process.pid, returncode=process.returncode)
            restarted = start_sender()
            if trace_startup:
                startup_event("sender_started", phase=phase, sender_pid=restarted.pid)
            try:
                ready_sender(restarted, phase, require_idle=True)
            except AssertionError as error:
                raise AssertionError(("账号发送器重启后未就绪", restarted.poll(), sender_state())) from error
            return restarted

        if v1_runtime is None:
            ready_sender(source, "initial")
        else:
            def native_ready():
                status, raw = call(8091, "GET", "/internal/native/status", secret)
                return status == 200 and json.loads(raw).get("raw_input_protocol") == 1

            wait_for(native_ready)

        def manage(method, path, body=None):
            status, raw = call(18090, method, "/admin/" + path, admin, body)
            assert status in (200, 201), (path, status)
            return json.loads(raw)

        manage("PUT", "settings", {"allowed_user_agents": "",
                                   "request_diagnostics_log_mode": "info" if (
                                       inspect_model_body or agent_progress or stock_client
                                   ) else "debug"})
        if auxiliary_mode:
            manage("PUT", "settings", {
                f"intercept_warmup_{auxiliary_kind}_enabled": "true" if auxiliary_mode == "mock" else "false",
            })
        if adaptive_thinking_model:
            manage("PUT", "settings", {"rewrite_disabled_thinking_enabled": "true",
                                       "rewrite_disabled_thinking_models": adaptive_thinking_model})
        if history_cache_ttl:
            manage("PUT", "settings", {"message_cache_control_rewrite": "off",
                                       "cache_control_ttl_rewrite": history_cache_ttl})
        credentials = {"auth_type": "oauth", "access_token": account_token, "refresh_token": token_hex(32),
                       "expires_at": time_ns() // 1_000_000 + 1_800_000, "subscription_type": "max"}
        if v1_runtime is not None:
            credentials = {"setup_token": account_token, "account_uuid": str(uuid4()), "organization_uuid": str(uuid4())}
        account = manage("POST", "accounts", {
            "email": "cold-history@example.invalid", "request_backend": "native293", "proxy_url": proxy_url,
            **credentials,
            "auto_telemetry": False, "auto_poll_usage": False, "concurrency": 2, "rpm_limit": 0,
        })
        identifier = account["id"]
        if auxiliary_mode in ("pooled", "pool-unsupported"):
            account = manage("PUT", f"accounts/{identifier}", {
                "upstream_session_pool_enabled": True, "upstream_session_pool_size": 1,
            })
            assert account["upstream_session_pool_enabled"]
        account = manage("GET", f"accounts/{identifier}")
        if v1_runtime is not None:
            assert account["request_backend"] == "native293" and account["client_system_prompt_policy"] == "replace"
            token = manage("POST", "tokens", {"name": "v1-policy-owner", "allowed_accounts": str(identifier)})["token"]
            if message_system_roles:
                return verify_message_system_roles(manage, token, account, received, model_betas,
                                                   fixed=message_system_roles == "ordinary-contract")
            return verify_v1_prompt_policy(token, received, model_betas)
        assert account["tui_v2_available"]
        manage("PUT", f"accounts/{identifier}", {"request_backend": "tui_v2",
               "request_backend_revision": account["request_backend_revision"]})
        token, foreign = (manage("POST", "tokens", {"name": name, "allowed_accounts": str(identifier)})["token"]
                          for name in ("cold-history-owner", "cold-history-foreign"))
        if stock_client:
            return verify_stock_client(manage, token, identifier, received, stock_homes, FINAL)
        if agent_progress:
            return verify_agent_progress(manage, token, foreign, received, temporary / "gateway.db", agent_progress,
                                         checked_messages, wait_for)
        session_id = auxiliary_sample["headers"]["x-claude-code-session-id"] if auxiliary_sample else str(uuid4())
        headers = {"x-session-id": session_id, "User-Agent": "flower2api-cold-history-fixture/1"}
        messages = [{"role": role, "content": text} for role, text in HISTORY]
        if thinking_display_model:
            return verify_thinking_display_contract(manage, token, identifier, received, thinking_display_model,
                                                    thinking_cli_summaries)
        if message_system_roles:
            account = manage("GET", f"accounts/{identifier}")
            return verify_message_system_roles(manage, token, account, received, model_betas,
                                               fixed=message_system_roles == "ordinary-contract")
        if structured_output:
            return verify_structured_output(manage, token, identifier, received)
        if no_tool_choice:
            return verify_no_tool_choice(manage, token, identifier, received)
        if forced_tool_choice:
            def restart_forced(headers):
                nonlocal source
                marker = ("--name=" + headers["x-session-id"]).encode()
                (pid,) = [int(path.parent.name) for path in Path("/proc").glob("[0-9]*/cmdline")
                          if fixture_command_has(path, marker)]
                archive = binding_file = None
                if forced_tool_choice == "restart-metadata-only":
                    (binding_file,) = Path("/native/tui-workspaces").glob("*.json")
                    native_id = json.loads(binding_file.read_bytes())["native_session_id"]
                    projects = Path("/native/tui-sessions") / native_id / "home/.claude/projects"
                    archive = wait_for(lambda: next(projects.glob("*/" + native_id + ".jsonl"), None))
                startup_event("forced_receipt_cli_sigkill", session_id=headers["x-session-id"], cli_pid=pid)
                os.kill(pid, SIGKILL)
                source = restart(source, "forced_tool_receipt")
                assert not Path(f"/proc/{pid}").exists()
                startup_event("forced_receipt_cli_exit_observed", session_id=headers["x-session-id"], cli_pid=pid)
                if archive is not None:
                    # 保留原 CLI 写出的元数据记录，模拟回执已登记而主轮未落盘的退出边界。
                    snapshot = b"".join(line for line in archive.read_bytes().splitlines(keepends=True)
                                        if json.loads(line)["type"] not in ("user", "assistant"))
                    archive.write_bytes(snapshot)
                    startup_event("forced_receipt_metadata_only", session_id=headers["x-session-id"],
                                  native_session_id=native_id, archive_sha256=sha256(snapshot).hexdigest())
                    return archive, snapshot, binding_file, binding_file.read_bytes()

            return verify_forced_tool_choice(manage, token, identifier, received, sender_state_after_failure,
                                             restart_forced if forced_tool_choice != "live" else None,
                                             metadata_only=forced_tool_choice == "restart-metadata-only")
        if cache_capability:
            return verify_cache_capabilities(manage, token, identifier, headers, received, cache_capability)
        if history_cache_markers and history_cache_scope != "nested":
            for row, marker in zip(messages[:2], HISTORY_CACHE, strict=True):
                row["content"] = [{"type": "text", "text": row["content"], "cache_control": marker}]
        if cache_markers:
            return verify_cache_markers(manage, token, identifier, headers, received)
        if failure_boundaries:
            def post(question, phase, expected_status, *, session=None):
                request = {"model": MODEL, "max_tokens": 128, "stream": False,
                           "messages": [{"role": "user", "content": question}]}
                return checked_messages(
                    manage, token, request, {**headers, "x-session-id": session or str(uuid4())}, received,
                    phase, expected_status=expected_status, trace_startup=trace_startup,
                )

            deny_proxy = True
            before, before_body, _ = post(AFTER_RESTART, "before_model", 502)
            assert before == 502 and not received, (before, before_body, len(received))
            assert denied_tunnels == ["api.anthropic.com:443"], denied_tunnels
            deny_proxy = False
            after, after_body, _ = post(DROP_REPLY, "model_stream_dropped", 502)
            assert after == 502 and len(received) == 1, (after, after_body, len(received))
            status, answer, _ = post(AFTER_RESTART, "new_request", 200)
            assert status == 200 and len(received) == 2, (status, answer, len(received))
            assert json.loads(answer)["content"] == [{"type": "text", "text": FINAL}]
            (failed, success) = verify_captures(manage, received, account_token)
            for attempt in (failed, success):
                assert attempt["cli_and_https_body_sha256"] != attempt["ingress_body_sha256"]
            assert failed["confirmed_model_responses"] is None and success["confirmed_model_responses"] == 1
            session = str(uuid4())
            started_at = datetime.now(timezone.utc).isoformat(timespec="milliseconds")
            rejected, error_body, request_id = post(REJECT_MODEL_REQUEST, "model_http_rejection", 400, session=session)
            assert rejected == 400 and len(received) == 3, (rejected, error_body, len(received))
            assert json.loads(error_body)["error"]["type"] == "invalid_request_error"
            assert request_id
            (record,) = report_request_diagnostics(manage, "model_http_rejection", request_id, session,
                                                    started_at)["requests"]
            assert record["attempt_count"] == record["diagnostic_context"]["tui_confirmed_model_responses"] == 1, record
            return {"before_send": before, "before_model_posts": 0, "after_send": after,
                    "after_model_posts": 1, "next_request": status, "next_model_posts": 1,
                    "model_http_rejection": {"http_status": rejected, "model_posts": 1, "request_id": request_id,
                                             "confirmed_model_responses": 1},
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
        nested_cache = history_cache_markers and (not history_cache_ttl or history_cache_scope is not None)
        if nested_cache:
            text = {"type": "text", "text": "已确认的重复旧工具结果。"}
            mark = {"type": "ephemeral"} if history_cache_scope else {"type": "ephemeral", "ttl": "5m"}
            old_result = [text, {**text, "cache_control": mark}]
        messages[3:3] = [
            {"role": "assistant", "content": [{"type": "tool_use", "name": "OldNote", "id": PAST_ID, "input": ARGS}]},
            {"role": "user", "content": [{"type": "tool_result", "tool_use_id": PAST_ID, "content": old_result}]},
        ]
        if split_history_tools:
            messages.insert(4, {"role": "assistant", "content": [
                {"type": "tool_use", "id": PAST_SECOND_ID, "name": "OtherOldNote", "input": ARGS}]})
            messages.insert(6, {"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": PAST_SECOND_ID, "content": "第二个已完成的旧工具结果。"}]})
        current = ([{"type": "text", "text": part} for part in (QUESTION, QUESTION_TAIL)]
                   if current_text_blocks else QUESTION)
        if current_images:
            png, jpeg, gif, webp = fixture_image_blocks(all_formats=True)
            caption = {"type": "text", "text": "  重复图注\n第二行  "}
            current = [{"type": "text", "text": QUESTION}, png, jpeg, caption, png, caption, gif, webp,
                       {"type": "text", "text": QUESTION_TAIL}]
            if current_image_ending == "image":
                current[-2], current[-1] = current[-1], current[-2]
        messages.append({"role": "user", "content": current})
        # 历史中的旧工具结果和当前问题之间保留完成边界，CLI 启动后只提交当前问题。
        declared = [TOOL, PARALLEL_SECOND_TOOL] if parallel_tools else [TOOL]
        expected_ids = [NEW_ID, SECOND_ID] if parallel_tools else [NEW_ID]
        registered_tools = encoded(expected_ids).decode()
        body = {"model": MODEL, "max_tokens": 128, "stream": True, "messages": messages,
                "tools": declared, "system": [{"type": "text", "text": part} for part in SYSTEM]}
        if auto_tool_choice:
            body["tool_choice"] = {"type": "auto", "disable_parallel_tool_use": False}
        if adaptive_thinking_model:
            body["model"] = adaptive_thinking_model
            if adaptive_thinking_display != "default":
                body["thinking"] = {**ADAPTIVE_THINKING, "display": adaptive_thinking_display}
            if adaptive_thinking_display == "updates":
                headers["anthropic-beta"] = THINKING_UPDATES_BETA
        if recover_pending:
            body["output_config"] = {"effort": "medium"}
        with ExitStack() as initial_connections:
            if initial_idle_model_connection:
                idle = initial_connections.enter_context(create_connection(("127.0.0.1", receiver.server_port), timeout=5))
                startup_event("idle_model_tcp_connected", peer_port=idle.getsockname()[1])
            initial_status, raw, initial_request_id = checked_messages(
                manage, token, body, headers, received, "initial", trace_startup=trace_startup,
                sender_status=sender_state_after_failure,
            )
            if initial_idle_model_connection:
                assert len(received) == 1
        events = [json.loads(line[5:]) for line in raw.splitlines() if line.startswith(b"data:")]
        assert events[-1]["type"] == "message_stop", events
        offered = []
        for event in events:
            if event["type"] != "content_block_start" or event["content_block"]["type"] != "tool_use":
                continue
            block = event["content_block"]
            deltas = [item["delta"]["partial_json"] for item in events
                      if item["type"] == "content_block_delta" and item["index"] == event["index"]
                      and item["delta"]["type"] == "input_json_delta"]
            block["input"] = json.loads("".join(deltas))
            offered.append(block)
        assert [block["id"] for block in offered] == expected_ids, offered
        assert [block["name"] for block in offered] == [item["name"] for item in declared], offered
        assert [block["input"] for block in offered] == (
            [ARGS, PARALLEL_SECOND_ARGS] if parallel_tools else [ARGS]
        ), offered
        tool = offered[0]
        if parallel_tools:
            result = {"role": "user", "content": fixture_parallel_results(offered, callbacks)}
        else:
            callbacks.append(tool["id"])
            result = {"role": "user", "content": [{"type": "tool_result", "tool_use_id": tool["id"], "content": REPLY}]}
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
        if signed_tool_history:
            (start,) = [event["content_block"] for event in events if event["type"] == "content_block_start"
                        and event["index"] == 0 and event["content_block"]["type"] == "thinking"]
            deltas = [event["delta"] for event in events if event["type"] == "content_block_delta" and event["index"] == 0]
            signed_block = {**start,
                            "thinking": start["thinking"] + "".join(d["thinking"] for d in deltas if d["type"] == "thinking_delta"),
                            "signature": "".join(d["signature"] for d in deltas if d["type"] == "signature_delta")}
            assert signed_block == {**SIGNED_THINKING, "thinking": signed_thinking_text}
            offered.insert(0, signed_block)
            if previous is None:
                with closing(connect("file:/native/tui-reconnect/receipts.db?mode=ro", uri=True)) as database:
                    (context,), = database.execute("SELECT n.context FROM receipts r JOIN native_receipt_inputs n"
                                                  " ON r.actor=n.actor AND r.revision=n.revision").fetchall()
                signed_tool_models = json.loads(context).get("signed_tool_models", {})
                expected_models = ({} if signed_tool_response == "missing-model"
                                   else dict.fromkeys(expected_ids, body["model"]))
                assert signed_tool_models == expected_models, signed_tool_models
        follow = {**body, "stream": reconnect_tool_stream,
                  "messages": [*messages, {"role": "assistant", "content": offered}, result]}
        if auxiliary_mode:
            auxiliary_proof = verify_pending_auxiliary(
                manage, token, headers, received, auxiliary_received, temporary / "gateway.db",
                auxiliary_sample, kind=auxiliary_kind, mode=auxiliary_mode, reply=auxiliary_reply,
            )
        wrong_subject, _ = call(18090, "POST", "/v1/messages", foreign, follow, headers)
        wrong_session, _ = call(18090, "POST", "/v1/messages", token, follow,
                                {**headers, "x-session-id": str(uuid4())})
        changed = {**follow, "messages": [*messages, {"role": "assistant", "content": [
            {**block, "input": {**ARGS, "key": "another-note"}} if block is tool else block
            for block in offered]}, result]}
        wrong_arguments, rejection = call(18090, "POST", "/v1/messages", token, changed, headers)
        rejected = wrong_subject, wrong_session, wrong_arguments, len(received)
        assert rejected == (400, 400, 422, 1), (rejected, rejection)
        partial_statuses = {}
        if parallel_tools:
            second_result = result["content"][0]
            for name, invalid in (
                ("missing_tool", [second_result]),
                ("duplicate_tool_id", [second_result] * 2),
                ("complete_plus_duplicate", [*result["content"], second_result]),
            ):
                partial = {**follow, "messages": [*follow["messages"][:-1], {**result, "content": invalid}]}
                partial_status, partial_raw = call(18090, "POST", "/v1/messages", token, partial, headers)
                assert partial_status == 400 and len(received) == 1, (name, partial_status, partial_raw)
                partial_statuses[name] = partial_status
        with closing(connect(temporary / "gateway.db")) as database:
            stored = database.execute("SELECT tools FROM tui_native_turns WHERE tools IN (?, ?)",
                                      (registered_tools, "!" + registered_tools)).fetchall()
            # 公开拒绝完成时，正确回执已经可以重新认领，查询不等待后台归还。
            assert stored == [(registered_tools,)], stored
        if history_cache_ttl:
            manage("PUT", "settings", {"cache_control_ttl_rewrite": "off"})
            assert manage("GET", "settings")["cache_control_ttl_rewrite"] == "off"
        if recover_pending:
            marker = ("--name=" + headers["x-session-id"]).encode()
            original, = [int(path.parent.name) for path in Path("/proc").glob("[0-9]*/cmdline")
                         if fixture_command_has(path, marker)]
            os.kill(original, SIGKILL)
            source = restart(source, "recovered_receipt")
            assert not Path(f"/proc/{original}").exists()
            (binding_file,) = Path("/native/tui-workspaces").glob("*.json")
            original_id = json.loads(binding_file.read_text())["native_session_id"]
            projects = Path("/native/tui-sessions") / original_id / "home/.claude/projects"
            (original_file,) = projects.glob("*/" + original_id + ".jsonl")
            original_history = original_file.read_bytes()
            manage("PUT", f"accounts/{identifier}", {"client_system_prompt_policy": "user_reminder"})
            modified_system = {**follow, "system": "更改已经冻结的指令"}
            changed_policy, response, _ = checked_messages(
                manage, token, modified_system, headers, received, "recovered_changed_system", expected_status=422,
                trace_startup=trace_startup,
            )
            assert changed_policy == 422 and len(received) == 1, (changed_policy, response, len(received))
            modified_effort = {**follow, "output_config": {"effort": "low"}}
            changed_effort, response, _ = checked_messages(
                manage, token, modified_effort, headers, received, "recovered_changed_effort", expected_status=422,
                trace_startup=trace_startup,
            )
            assert changed_effort == 422 and len(received) == 1, (changed_effort, response, len(received))
        if current_text_blocks:
            merged = {"role": "user", "content": QUESTION + QUESTION_TAIL}
            changed = {**follow, "messages": [*messages[:-1], merged, *follow["messages"][-2:]]}
            changed_blocks, response = call(18090, "POST", "/v1/messages", token, changed, headers)
            assert changed_blocks == 422 and len(received) == 1, (changed_blocks, response, len(received))
        if current_images:
            changed_image = {**messages[-1], "content": [current[0], current[2], current[1], *current[3:]]}
            changed = {**follow, "messages": [*messages[:-1], changed_image, *follow["messages"][-2:]]}
            changed_media, response = call(18090, "POST", "/v1/messages", token, changed, headers)
            assert changed_media == 422 and len(received) == 1, (changed_media, response, len(received))
        if auto_tool_choice:
            changed = {**follow, "tool_choice": {"type": "none"}}
            changed_choice, response = call(18090, "POST", "/v1/messages", token, changed, headers)
            assert changed_choice == 422 and len(received) == 1, (changed_choice, response, len(received))
        if adaptive_thinking_model:
            changed_thinking = {}
            changes = {"omitted": {"type": "adaptive", "display": "omitted"},
                       "disabled_with_platform_rewrite": {"type": "disabled"}}
            if summarized_thinking:
                changes.update(default_display={"type": "adaptive"}, updates=ADAPTIVE_THINKING)
            for label, thinking in changes.items():
                changed_status, raw, _ = checked_messages(
                    manage, token, {**follow, "thinking": thinking}, headers, received,
                    "changed_thinking_" + label, expected_status=422,
                )
                assert json.loads(raw)["error"]["code"] == "unsupported_parameter" and len(received) == 1, raw
                changed_thinking[label] = changed_status
        if history_cache_markers:
            original_markers = observed_cache_breakpoints({"messages": messages})
            if original_markers:
                first, = messages[0]["content"]
                changed_prefix = {**messages[0], "content": [{**first, "cache_control": {"type": "ephemeral", "ttl": "5m"}}]}
                changed = {**follow, "messages": [changed_prefix, *follow["messages"][1:]]}
                changed_cache, _, _ = checked_messages(
                    manage, token, changed, headers, received, "changed_history_cache", expected_status=422,
                )
                assert len(received) == 1
            if nested_cache:
                changed_nested = deepcopy(follow)
                ((_, old_tool_result),) = find_blocks(changed_nested, "tool_use_id", PAST_ID)
                old_tool_result["content"][1].pop("cache_control")
                changed_nested_cache, _, _ = checked_messages(
                    manage, token, changed_nested, headers, received, "changed_nested_history_cache", expected_status=422,
                )
            assert len(received) == 1
        if signed_tool_history:
            tampered = {**signed_block, "signature": "Y2hhbmdlZA=="}
            changed = {**follow, "messages": [*messages, {"role": "assistant", "content": [tampered, *offered[1:]]}, result]}
            changed_signature, response = call(18090, "POST", "/v1/messages", token, changed, headers)
            assert changed_signature == 422 and len(received) == 1, (changed_signature, response, len(received))
        if reconnect_tool_stream:
            proof = verify_tool_stream_reconnect(manage, temporary, token, account_token, headers, follow,
                                                 received, finish_stream, callbacks)
            verify_model(received[:2], policy="append", old_content=old_result, current_text_blocks=current_text_blocks)
            return proof
        if recovery_ledger_contention:
            # 在合法回执进入 sender 前持锁，覆盖旧固定一秒等待超时的区间。
            lock = stack.enter_context(Path("/native/tui-v2-submissions.lock").open("rb"))
            flock(lock, LOCK_EX)
            release_lock = Timer(2, lock.close)
            stack.callback(release_lock.cancel)
            release_lock.start()
        if recovery_ledger_deadline:
            budget_key = "v3_admission_wait_seconds"
            previous_budget = manage("GET", "settings")[budget_key]
            manage("PUT", "settings", {budget_key: "3"})
            try:
                with Path("/native/tui-v2-submissions.lock").open("rb") as deadline_lock:
                    flock(deadline_lock, LOCK_EX)
                    started_at = datetime.now(timezone.utc).isoformat(timespec="milliseconds")
                    started = monotonic()
                    expired_status, _, expired_request = checked_messages(
                        manage, token, follow, headers, received, "recovered_receipt_ledger_deadline", expected_status=429,
                        trace_startup=trace_startup,
                    )
                    elapsed_ms = round((monotonic() - started) * 1000)
                    posts_before_retry = len(received)
                    assert expired_request and posts_before_retry == 1
                    evidence = report_request_diagnostics(
                        manage, "recovered_receipt_ledger_deadline", expired_request, headers["x-session-id"], started_at,
                    )
                    expired, = evidence["requests"]
                    assert (expired["status_code"], expired["error_stage"], expired["outcome"]) == (
                        429, "tui_submission_ledger", "local_rejected",
                    ), expired
                    assert expired["attempt_count"] == 0 and expired["attempts"] == [], expired
                    assert expired["diagnostic_context"]["tui_confirmed_model_responses"] == 0, expired
                    expired_reservation = expired["diagnostic_context"]["tui_reservation_id"]
                    assert str(UUID(expired_reservation)) == expired_reservation
                    with closing(connect(temporary / "gateway.db")) as database:
                        tools = database.execute("SELECT tools FROM tui_native_turns WHERE tools IN (?, ?)",
                                                 (registered_tools, "!" + registered_tools)).fetchall()
                        assert tools == [(registered_tools,)], tools
            finally:
                manage("PUT", "settings", {budget_key: previous_budget})
        if recovery_workspace_rejection:
            original_binding = binding_file.read_bytes()
            mismatched = {**json.loads(original_binding), "session_key": "0" * 64}
            started_at = datetime.now(timezone.utc).isoformat(timespec="milliseconds")
            try:
                binding_file.write_text(json.dumps(mismatched))
                rejection_status, _, rejected_request = checked_messages(
                    manage, token, follow, headers, received, "recovered_receipt_workspace", expected_status=503,
                    trace_startup=trace_startup,
                )
                assert rejected_request and len(received) == 1
                evidence = report_request_diagnostics(
                    manage, "recovered_receipt_workspace", rejected_request, headers["x-session-id"], started_at,
                )
                record, = evidence["requests"]
                assert (record["status_code"], record["error_stage"], record["outcome"]) == (
                    503, "tui_workspace_bind", "local_rejected",
                ), record
                assert record["attempt_count"] == 0 and record["attempts"] == [], record
                reservation = record["diagnostic_context"]["tui_reservation_id"]
                assert str(UUID(reservation)) == reservation
                with closing(connect(temporary / "gateway.db")) as database:
                    tools = database.execute("SELECT tools FROM tui_native_turns WHERE tools IN (?, ?)",
                                             (registered_tools, "!" + registered_tools)).fetchall()
                    assert tools == [(registered_tools,)], tools
            finally:
                binding_file.write_bytes(original_binding)
        if recovery_slow_model:
            budget_key = "v3_admission_wait_seconds"
            previous_budget = manage("GET", "settings")[budget_key]
            manage("PUT", "settings", {budget_key: "3"})
            started_at = datetime.now(timezone.utc).isoformat(timespec="milliseconds")
            try:
                status, _, request_id = checked_messages(
                    manage, token, follow, headers, received, "recovered_receipt_slow_model", expected_status=502,
                    trace_startup=trace_startup, sender_status=sender_state_after_failure,
                )
                returned = monotonic()
                arrival, = slow_tool_arrivals
                assert request_id and arrival < returned < arrival + SLOW_MODEL_DELAY and len(received) == 2
                ((role, receipt),) = find_blocks(received[-1][1], "tool_use_id", NEW_ID)
                assert role == "user" and REPLY in json.dumps(receipt, ensure_ascii=False)
                sleep(max(0, arrival + SLOW_MODEL_DELAY - monotonic()))
                evidence = report_request_diagnostics(
                    manage, "recovered_receipt_slow_model", request_id, headers["x-session-id"], started_at,
                )
                record, = evidence["requests"]
                assert (record["status_code"], record["error_stage"], record["outcome"]) == (
                    status, "tui_send_http", "transport_error",
                ), record
                assert record["native_rejection"] is None and record["attempt_count"] == 0 and record["attempts"] == [], record
                assert "tui_confirmed_model_responses" not in record["diagnostic_context"], record
                reservation = record["diagnostic_context"]["tui_reservation_id"]
                assert str(UUID(reservation)) == reservation
                assert len(received) == 2 and callbacks == [NEW_ID] and original_file.read_bytes() == original_history
                verify_model(received, policy="append", old_content=old_result, current_text_blocks=current_text_blocks)
                return {"http_status": status, "model_received_before_public_return_ms": round((returned - arrival) * 1000),
                        "model_posts": len(received), "client_tool_calls": len(callbacks), "old_tool_calls": 0,
                        "request_id": request_id, "reservation_id": reservation, "outcome": record["outcome"],
                        "error_stage": record["error_stage"], "attempt_count": record["attempt_count"],
                        "confirmed_model_responses": record["diagnostic_context"].get("tui_confirmed_model_responses"),
                        "original_history_preserved": True}
            finally:
                manage("PUT", "settings", {budget_key: previous_budget})
        rejected_signed_recovery = signed_tool_history and recover_pending and signed_tool_response == "missing-model"
        status, raw, continuation_request_id = checked_messages(
            manage, token, follow, headers, received, "recovered_receipt" if recover_pending else "receipt",
            expected_status=422 if rejected_signed_recovery else 200, trace_startup=trace_startup,
            sender_status=sender_state_after_failure,
        )
        if rejected_signed_recovery:
            # 缺少已记录的助手模型时在准备阶段拒绝恢复，保留原签名和归属。
            assert status == 422 and len(received) == 1, (status, raw, len(received))
            assert json.loads(raw)["error"]["code"] == "unsupported_parameter", raw
            assert not manage("GET", "request-diagnostics/" + continuation_request_id)["attempts"]
            assert original_file.read_bytes() == original_history
            (first_attempt,) = verify_captures(manage, received, account_token)
            proof = {"cold_recovery_status": status, "changed_signature_status": changed_signature,
                     "receipt_request_id": continuation_request_id, "receipt_attempts": 0,
                     "recorded_signed_tool_models": signed_tool_models,
                     "model_posts": len(received), "original_history_preserved": True, "attempt": first_attempt}
            if adaptive_thinking_model:
                assert received[0][1]["thinking"] == body.get("thinking", ADAPTIVE_THINKING)
                proof.update(thinking=received[0][1]["thinking"], changed_thinking_status=changed_thinking)
            return proof
        final = json.loads(raw)
        if summarized_thinking:
            verify_client_thinking_reply(raw, False, adaptive_thinking_model, SIGNED_THINKING["thinking"])
        else:
            assert final["content"] == [{"type": "text", "text": FINAL}]
        duplicate, _ = call(18090, "POST", "/v1/messages", token, follow, headers)
        assert duplicate == 400 and len(received) == 2, (duplicate, len(received))
        assert callbacks == expected_ids
        if previous:
            ((role, old_receipt),) = find_blocks(received[1][1], "tool_use_id", NEW_ID)
            assert role == "user" and REPLY in json.dumps(old_receipt, ensure_ascii=False)
            assert any(lookup.get("tui_previous_release") == ["true"] for lookup in lookups[lookup_boundary:])
            wait_for(lambda: sender_state().get("idle"))
            with closing(connect(temporary / "gateway.db")) as database:
                wait_for(lambda: database.execute("SELECT count(*) FROM tui_native_turns WHERE tools IN (?, ?)",
                                                 (json.dumps([NEW_ID]), "!" + json.dumps([NEW_ID]))).fetchone()[0] == 0)
            stop(source)
            if previous[0] is not None:
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
        if restart_history or recover_pending:
            assert [attempt["diagnostic_session_origin"] for attempt in captures] == [
                "external_import", "disk_resume" if recover_pending else "live_process",
            ], captures
        if recover_pending or toggle_pending_policy or tool_policy:
            location = "user_reminder" if tool_policy == "user_reminder" else "system"
            assert [a["diagnostic_instruction_location"] for a in captures] == [location] * 2, captures
        for attempt, request_id, request_body, reply_id, model_id in zip(
            captures, (initial_request_id, continuation_request_id),
            (body, follow), (events[0]["message"]["id"], final["id"]),
            ("msg_cold_tool", "msg_cold_reply"), strict=True,
        ):
            assert attempt["request_id"] == request_id
            if recover_pending:
                assert attempt["diagnostic_body_source"] == "interactive_cli", attempt
                assert attempt["confirmed_model_responses"] == 1, attempt
            assert attempt["ingress_body_sha256"] == sha256(encoded(request_body)).hexdigest()
            assert attempt["cli_and_https_body_sha256"] != attempt["ingress_body_sha256"]
            attempt.update(client_message_id=reply_id, model_message_id=model_id)
        proof = {"model_posts": len(received), "client_tool_calls": callbacks, "old_tool_calls": 0,
                 "current_question_count": 1, "old_question_roles": [role for role, _ in HISTORY],
                 "foreign_receipt_status": wrong_subject, "wrong_session_status": wrong_session,
                 "changed_tool_arguments_status": wrong_arguments,
                 "duplicate_receipt_status": duplicate, "tls_versions": [tls for _, _, tls in received],
                 "proxy_connections": len(proxy_targets), "attempts": captures}
        if auxiliary_mode:
            auxiliary_model = auxiliary_sample["body"]["model"] if auxiliary_received else None
            rows = wait_for(lambda: auxiliary_usage_rows(
                temporary / "gateway.db", auxiliary_model, tool_output=auxiliary_mode == "tool-output",
            ))
            assert all(auxiliary_text not in json.dumps(native, ensure_ascii=False) for _, native, _ in received)
            assert auxiliary_proof[f"{auxiliary_kind}_request_id"] not in {item["request_id"] for item in captures}
            if auxiliary_mode == "pooled":
                assert auxiliary_provider_sessions == [headers["x-session-id"]]
                account, = [account for account in manage("GET", "accounts")["data"] if account["id"] == identifier]
                assert account["upstream_session_pool_active_count"] == 1
                auxiliary_proof[f"{auxiliary_kind}_upstream_session_id"] = auxiliary_provider_sessions[0]
            proof[f"interleaved_{auxiliary_kind}"] = {**auxiliary_proof, "usage_records": rows}
        if initial_idle_model_connection:
            proof["initial_idle_model_connection"] = {"http_status": initial_status, "model_posts": 1}
        if history_tool_blocks:
            proof["historical_tool_result_blocks"] = len(old_result)
        if history_cache_markers:
            observed = [observed_cache_breakpoints(model) for _, model, _ in received]
            expected = original_markers
            if history_cache_ttl:
                expected = [(i, offset, role, {**block, "cache_control": {"type": "ephemeral", "ttl": history_cache_ttl}})
                            for i, offset, role, block in expected]
            assert observed == [expected, expected], observed
            proof["history_cache_markers"] = observed
            if original_markers:
                proof["changed_history_cache_status"] = changed_cache
            if history_cache_ttl:
                proof.update(history_cache_ttl=history_cache_ttl, active_platform_ttl="off",
                             receipt_after_policy_change_status=status)
            if nested_cache:
                proof.update(nested_history_cache_markers=[find_blocks(model, "tool_use_id", PAST_ID)
                                                           for _, model, _ in received],
                             changed_nested_history_cache_status=changed_nested_cache)
        if parallel_tools:
            first, second = (document for _, document, _ in received)
            assert TOOL["input_schema"] != PARALLEL_SECOND_TOOL["input_schema"]
            for native in (first, second):
                second_tool, = [t for t in native["tools"] if t["name"] == NATIVE_SECOND_TOOL_NAME]
                assert second_tool["input_schema"] == PARALLEL_SECOND_TOOL["input_schema"]
            assert not find_blocks(first, "id", SECOND_ID) and not find_blocks(first, "tool_use_id", SECOND_ID)
            assert find_blocks(second, "id", SECOND_ID) == [("assistant", {
                "type": "tool_use", "name": NATIVE_SECOND_TOOL_NAME, "id": SECOND_ID, "input": PARALLEL_SECOND_ARGS,
            })]
            (success_role, success), = find_blocks(second, "tool_use_id", NEW_ID)
            assert success_role == "user" and not success.get("is_error", False) and success["content"] == REPLY
            (role, failed), = find_blocks(second, "tool_use_id", SECOND_ID)
            assert role == "user" and failed["is_error"] is True
            # CLI 会在最后一个结果补足原生 Token 提醒，原始失败正文必须保持在开头。
            assert failed["content"].startswith(SECOND_REPLY + "\n\n<system-reminder>\n<total_tokens>")
            client_order = [block["tool_use_id"] for block in result["content"]]
            model_order = [block["tool_use_id"] for row in second["messages"] for block in blocks(row)
                           if block.get("tool_use_id") in expected_ids]
            assert client_order == expected_ids[::-1] and model_order == expected_ids, (client_order, model_order)
            proof.update(parallel_tool_receipt_rejections=partial_statuses, preserved_tool_error=True,
                         client_result_order=client_order, model_result_order=model_order,
                         distinct_tool_schemas=True, exact_success_text=True, failure_token_reminder=True)
        if split_history_tools:
            for _, native, _ in received:
                assert find_blocks(native, "id", PAST_SECOND_ID) == [("assistant", {
                    "type": "tool_use", "id": PAST_SECOND_ID, "name": "OtherOldNote", "input": ARGS})]
                assert find_blocks(native, "tool_use_id", PAST_SECOND_ID) == [("user", {
                    "type": "tool_result", "tool_use_id": PAST_SECOND_ID, "content": "第二个已完成的旧工具结果。"})]
                blocks_in_order = [block for row in native["messages"] for block in blocks(row)]
                for key in ("id", "tool_use_id"):
                    assert [block[key] for block in blocks_in_order if block.get(key) in (PAST_ID, PAST_SECOND_ID)] == [
                        PAST_ID, PAST_SECOND_ID,
                    ]
            proof["closed_historical_tools"] = 2
        if current_text_blocks:
            proof.update(current_text_blocks=2, changed_current_blocks_status=changed_blocks)
        if current_images:
            stages = ("first", "recovered" if recover_pending else "warm_receipt")
            raw_media = {stage: verify_raw_current_image_row(native, current, stage=stage)
                         for stage, (_, native, _) in zip(stages, received, strict=True)}
            proof.update(current_images=[block["source"]["media_type"] for block in current if block["type"] == "image"],
                         changed_current_images_status=changed_media, raw_current_image_content=raw_media)
        if auto_tool_choice:
            observed = [native.get("tool_choice") for _, native, _ in received]
            assert all(choice in (None, {"type": "auto"}, body["tool_choice"]) for choice in observed)
            proof.update(auto_tool_choice=observed, changed_tool_choice_status=changed_choice)
        if adaptive_thinking_model:
            actual_thinking = [native.get("thinking") for _, native, _ in received]
            assert actual_thinking == [body.get("thinking", ADAPTIVE_THINKING)] * 2, actual_thinking
            assert all(native["model"] == adaptive_thinking_model for _, native, _ in received)
            if not summarized_thinking:
                assert len(model_betas) == 2 and all(THINKING_UPDATES_BETA in beta.split(",") for beta in model_betas), model_betas
            proof.update(thinking_model=adaptive_thinking_model, thinking=actual_thinking,
                         changed_thinking_status=changed_thinking)
            if summarized_thinking:
                proof["client_content"] = final["content"]
        if signed_tool_history:
            hydrated = find_blocks(received[1][1], "type", "thinking")
            assert hydrated == [("assistant", signed_block)], (
                hydrated, [(row["role"], [block["type"] for block in blocks(row)]) for row in received[1][1]["messages"]],
            )
            proof.update(observed_signature_preserved=True, changed_signature_status=changed_signature,
                         signed_reply=hydrated[0][1], recorded_signed_tool_models=signed_tool_models)
        if toggle_pending_policy:
            proof["pending_policy"] = "append"
        if tool_policy:
            proof["tool_policy"] = tool_policy
        if recover_pending:
            assert original_file.read_bytes() == original_history
            _, native_recovery, _ = received[-1]
            assert all(document["output_config"]["effort"] == "medium" for _, document, _ in received)
            restored_id = json.loads(native_recovery["metadata"]["user_id"])["session_id"]
            restored_file = original_file.parent / (restored_id + ".jsonl")
            assert restored_id != original_id and restored_file.is_file()
            if signed_tool_history:
                archived = [row["message"] for row in map(json.loads, restored_file.read_text().splitlines())
                            if row.get("type") == "assistant" and any(
                                block.get("id") == NEW_ID for block in blocks(row["message"]))]
                (signed,) = archived
                assert set(signed) == {"role", "content", "model"}
                assert signed["model"] == events[0]["message"]["model"]
                proof["recovered_signed_tool_model"] = signed["model"]
            restored_text = [(row["role"], block.get("text")) for row in native_recovery["messages"] for block in blocks(row)]
            continue_prompt_count = restored_text.count(("user", "Continue from where you left off."))
            assert continue_prompt_count == 1
            proof["recovered_pending_tool"] = {"changed_system_http": changed_policy, "frozen_policy": "append",
                                              "changed_effort_http": changed_effort, "frozen_effort": "medium",
                                              "old_session_id": original_id, "recovered_session_id": restored_id,
                                              "original_history_preserved": True,
                                              "continue_prompt_count": continue_prompt_count}
            if recovery_ledger_contention:
                assert lock.closed
                proof["recovered_pending_tool"]["ledger_lock_delay_seconds"] = 2
            if recovery_ledger_deadline:
                assert expired_request != continuation_request_id
                proof["recovered_pending_tool"]["ledger_deadline"] = {
                    "http_status": expired_status, "error_stage": expired["error_stage"],
                    "attempt_count": expired["attempt_count"], "request_id": expired_request,
                    "confirmed_model_responses": expired["diagnostic_context"]["tui_confirmed_model_responses"],
                    "reservation_id": expired_reservation, "elapsed_ms": elapsed_ms,
                    "model_posts_before_retry": posts_before_retry, "receipt_reopened": True,
                }
            if recovery_workspace_rejection:
                assert rejected_request != continuation_request_id
                proof["recovered_pending_tool"]["workspace_rejection"] = {
                    "http_status": rejection_status, "error_stage": record["error_stage"],
                    "attempt_count": record["attempt_count"], "request_id": rejected_request,
                    "reservation_id": reservation, "receipt_reopened": True,
                }
        if current_images and not recover_pending and not restart_history:
            proof["image_only"] = verify_image_only_requests(
                manage, token, account_token, headers, received,
                check_existing=not toggle_pending_policy and tool_policy in (None, "append"),
            )
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
            restarted = restart(source, "restart_history")
            expected_history = [("user", divergent), *HISTORY[1:]]
            history_texts = {text for _, text in expected_history}
            branch_ids = []
            snapshots = {history_file: original}
            followup_ids = []
            branch_request_ids = []
            for post in (3, 4):
                status, raw, branch_request_id = checked_messages(
                    manage, token, branch, headers, received, f"restart_history_{post}",
                    trace_startup=trace_startup, sender_status=sender_state_after_failure,
                )
                branch_request_ids.append(branch_request_id)
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
                    restart(restarted, "repeat_history")
                else:
                    assert branch_id != native_id and path.is_file()
                followup_ids.append(json.loads(raw)["id"])
            archives = set(history_file.parent.glob("*.jsonl"))
            assert archives == {history_file, staged_path, path}
            assert len(set(followup_ids)) == 2
            assert list(binding_file.parent.glob("*.json")) == [binding_file]
            assert binding_file.read_bytes() == binding_bytes
            assistant_fields = sorted(next(row for row in imported if row["role"] == "assistant"))
            branch_attempts = verify_captures(manage, received[-2:], account_token)
            assert [a["request_id"] for a in branch_attempts] == branch_request_ids, branch_attempts
            assert [a["diagnostic_session_origin"] for a in branch_attempts] == ["disk_resume"] * 2, branch_attempts
            proof["restart"] = {"bound_session_id": native_id, "branch_session_ids": branch_ids,
                                "staged_branch_session_id": staged_id,
                                "binding_preserved": True,
                                "assistant_history_fields": assistant_fields,
                                "archive_count_after_repeat": len(archives),
                                "repeat_client_message_ids": followup_ids,
                                "preserved_bytes": [len(data) for data in snapshots.values()],
                                "additional_model_posts": 2,
                                "attempts": branch_attempts}
        if history_cache_ttl:
            # 同一公开会话确认同一前缀后开启新轮，只有新轮应用管理端的 off。
            fresh = {**body, "stream": False, "messages": [*messages[:-1], {"role": "user", "content": AFTER_RESTART}]}
            fresh_status, reply, fresh_request = checked_messages(
                manage, token, fresh, headers, received, "new_round_after_ttl_change", trace_startup=trace_startup,
            )
            assert json.loads(reply)["content"] == [{"type": "text", "text": FINAL}] and len(received) == 3
            markers = observed_cache_breakpoints(received[-1][1])
            assert markers == original_markers, markers
            (old_role, old_block), = find_blocks(received[-1][1], "tool_use_id", PAST_ID)
            assert old_role == "user" and old_block["content"] == old_result, old_block
            (capture,) = verify_captures(manage, received[-1:], account_token)
            assert capture["request_id"] == fresh_request and (not recover_pending or original_file.read_bytes() == original_history)
            proof["new_round_after_ttl_change"] = {"http_status": fresh_status, "same_session": True,
                                                    "model_posts": 1, "markers": markers, "attempt": capture}
        return proof


def checked_messages(manage, token, body, headers, received, phase, *, expected_status=200, trace_startup=False,
                     sender_status=None):
    """在断言前保留本轮公开响应与诊断归属。
    @param manage 管理入口。@param token 合成凭据。@param body 公开输入。@param headers 原入口头。
    @param received 隔离模型收件。@param phase 夹具阶段。@param expected_status 预期 HTTP 状态，空值保留实测状态。
    @param trace_startup 是否记录公开请求时间及失败后线程栈。
    @param sender_status 可选，只在已保留失败和请求诊断后读取隔离发送器状态。
    @return 实际状态、响应字节和公开请求 ID。
    """
    started_at = datetime.now(timezone.utc).isoformat(timespec="milliseconds")
    started = monotonic()
    before = len(received)
    session_id = headers["x-session-id"]
    evidence = {"event": "messages_failure", "phase": phase, "started_at": started_at,
                "http_status": None, "request_id": None, "expected_status": expected_status}

    def observe(response):
        evidence.update(http_status=response.status, request_id=response.getheader("x-cc2api-request-id"))
        assert response.getheader("x-v3-tui-body-source") is None
        assert response.getheader("x-v3-tui-session-origin") is None
        assert response.getheader("x-v3-tui-instruction-location") is None
        if trace_startup:
            startup_event("public_response_headers", phase=phase, session_id=session_id,
                          request_id=evidence["request_id"], http_status=response.status,
                          model_posts_during=len(received) - before)

    def report(**details):
        failed_ns = monotonic_ns() if trace_startup else None
        event = {**evidence, **details, "elapsed_ms": round((monotonic() - started) * 1000),
                 "model_posts_before": before, "model_body_sha256": [sha for sha, _, _ in received[before:]]}
        if failed_ns is not None:
            event["monotonic_ns"] = failed_ns
        event["model_posts_during"] = len(event["model_body_sha256"])
        # 先留下原始观测。诊断读回失败时仍能保留同一请求的 HTTP 和模型收件情况。
        print(json.dumps(event, ensure_ascii=False), file=stderr, flush=True)
        if trace_startup:
            startup_event("fixture_threads_after_failure")
            with suppress(OSError, RuntimeError):
                dump_traceback(file=stderr)
        report_request_diagnostics(manage, phase, evidence["request_id"], session_id, started_at)
        if trace_startup and sender_status is not None:
            try:
                state = sender_status()
            except (HTTPException, OSError, ValueError) as error:
                startup_event("sender_status_after_failure", phase=phase, session_id=session_id,
                              request_id=evidence["request_id"], lookup_error=type(error).__name__)
            else:
                startup_event("sender_status_after_failure", phase=phase, session_id=session_id,
                              request_id=evidence["request_id"], ready=state.get("ready"), idle=state.get("idle"))

    if trace_startup:
        startup_event("public_request_start", phase=phase, session_id=session_id, model_posts_before=before)
    try:
        status, raw = call(18090, "POST", "/v1/messages", token, body, headers, observe_headers=observe)
    except (HTTPException, OSError) as error:
        report(transport_error=type(error).__name__,
               transport_stage="response_body" if evidence["http_status"] is not None else "before_response_headers")
        raise
    if expected_status is not None and status != expected_status:
        try:
            payload = json.loads(raw)
        except ValueError:
            payload = None
        error = payload.get("error") if isinstance(payload, dict) else None
        if isinstance(error, dict):
            error = {key: error[key] for key in ("type", "code", "message") if isinstance(error.get(key), str)}
        report(response_error=error if isinstance(error, (dict, str)) else None,
               response_sha256=sha256(raw).hexdigest(), response_bytes=len(raw))
        raise AssertionError((phase, status, expected_status, evidence["request_id"]))
    return status, raw, evidence["request_id"]


def report_request_diagnostics(manage, phase, request_id, session_id, started_at):
    """在网关退出前读回本请求诊断。@param manage 管理入口。@param phase 夹具阶段。
    @param request_id 响应关联头，可为空。@param session_id 合成会话。@param started_at 本次 UTC 开始时间。
    @return 诊断事件。
    """
    query = {"correlation_id": request_id} if request_id else {"since": started_at, "page_size": 100}
    event = {"event": "messages_failure_diagnostics", "phase": phase, "request_id": request_id,
             "correlation": "response_request_id" if request_id else "session_candidates", "requests": []}
    latest = []

    def observe():
        nonlocal latest
        rows = manage("GET", "request-diagnostics?" + urlencode(query))["items"]
        latest = [row for row in rows if (
            row["request_id"] == request_id if request_id else row.get("original_session_id") == session_id
        )]
        return latest if not request_id or all(row.get("finished_at") for row in latest) else None

    def selected_context(row):
        context = row.get("context") or {}
        return {key: context[key] for key in (
            "control_state", "control_error_code", "control_recovery", "observed_control_http_status",
            "native_receive_ended", "native_source_terminal", "tui_reservation_id",
            "tool_continuation_mode", "tool_continuation_path", "tool_continuation_reason",
            "tui_body_source", "tui_session_origin", "tui_instruction_location",
            "tui_confirmed_model_responses",
        ) if context.get(key) is not None}

    try:
        wait_for(observe)
    except (AssertionError, HTTPException, OSError, ValueError, KeyError) as error:
        event["lookup_error"] = type(error).__name__
    for row in latest:
        keys = ("request_id", "account_id", "started_at", "finished_at", "status_code",
                "outcome", "error_stage", "attempt_count", "native_rejection")
        item = {key: row.get(key) for key in keys}
        try:
            detail = manage("GET", "request-diagnostics/" + row["request_id"])
            assert detail["request"]["request_id"] == row["request_id"]
            item["diagnostic_context"] = selected_context(detail["request"])
            fields = ("attempt_id", "request_id", "ordinal", "account_id", "execution_location",
                      "status_code", "outcome", "error_stage", "error_type", "retry_reason")
            assert all(attempt["request_id"] == row["request_id"] for attempt in detail["attempts"])
            item["attempts"] = [{**{key: attempt.get(key) for key in fields},
                                 "diagnostic_context": selected_context(attempt)} for attempt in detail["attempts"]]
        except (AssertionError, HTTPException, OSError, ValueError, KeyError) as error:
            item["lookup_error"] = type(error).__name__
        event["requests"].append(item)
    print(json.dumps(event, ensure_ascii=False), file=stderr, flush=True)
    return event


def verify_tool_stream_reconnect(manage, temporary, token, account_token, headers, follow,
                                 received, finish_stream, callbacks):
    """断开真实续轮读者，再读取同一次交付。@param manage 管理入口。@param temporary 本次私有数据库目录。
    @param token 合成调用方。@param account_token 合成模型凭据。@param headers 原请求会话。
    @param follow 同一公开工具回执。@param received 模型实收。@param finish_stream 模型尾段放行。
    @param callbacks 客户端已执行的合成工具。@return 实测证据。
    """
    def disconnect_after_prefix():
        with closing(HTTPConnection("127.0.0.1", 18090, timeout=30)) as connection:
            connection.request("POST", "/v1/messages", encoded(follow), {
                "Authorization": "Bearer " + token, "Content-Type": "application/json",
                "anthropic-version": "2023-06-01", **headers,
            })
            with closing(connection.getresponse()) as response:
                assert response.status == 200, response.status
                prefix = []
                while line := response.readline():
                    if not line.startswith(b"data:"):
                        continue
                    event = json.loads(line[5:])
                    prefix.append(event)
                    if event.get("delta", {}).get("text") == RECONNECT_PREFIX:
                        break
                assert [event["type"] for event in prefix] == [
                    "message_start", "content_block_start", "content_block_delta",
                ]
                assert prefix[-1]["delta"]["text"] == RECONNECT_PREFIX
                connection.sock.shutdown(SHUT_RDWR)
                return prefix, response.getheader("x-cc2api-request-id")

    original, original_request_id = disconnect_after_prefix()
    assert len(received) == 2 and not finish_stream.is_set()
    # 六秒后在原模型仍在生成时接回。第二个读取者再次断开后，才放行同一响应的尾段。
    sleep(6)
    live_prefix, live_request_id = disconnect_after_prefix()
    assert live_prefix == original and len(received) == 2
    assert original_request_id and live_request_id and original_request_id != live_request_id
    finish_stream.set()
    with closing(connect(temporary / "gateway.db")) as database:
        wait_for(lambda: database.execute("SELECT count(*) FROM tui_native_turns WHERE tools=?",
                                         (encoded([RECONNECT_ID]).decode(),)).fetchone()[0] == 1)
    status, wire = call(18090, "POST", "/v1/messages", token, follow, headers)
    assert status == 200 and len(received) == 2, (status, wire, len(received))
    replay = [json.loads(line[5:]) for line in wire.splitlines() if line.startswith(b"data:")]
    assert replay[:len(original)] == original and replay[-1]["type"] == "message_stop"
    (item,) = [event for event in replay if event["type"] == "content_block_start"
               and event["content_block"]["type"] == "tool_use"]
    tool = item["content_block"]
    tool["input"] = json.loads("".join(event["delta"]["partial_json"] for event in replay
        if event["type"] == "content_block_delta" and event["index"] == item["index"]))
    assert tool == {"type": "tool_use", "id": RECONNECT_ID, "name": TOOL["name"], "input": SECOND_ARGS}
    callbacks.append(RECONNECT_ID)
    assert callbacks == [NEW_ID, RECONNECT_ID]

    rows = [
        {"role": "assistant", "content": [{"type": "text", "text": RECONNECT_PREFIX}, tool]},
        {"role": "user", "content": [{"type": "tool_result", "tool_use_id": RECONNECT_ID, "content": SECOND_REPLY}]},
    ]
    next_request = {**follow, "stream": False, "messages": [*follow["messages"], *rows]}
    status, raw = call(18090, "POST", "/v1/messages", token, next_request, headers)
    assert status == 200 and len(received) == 3, (status, raw, len(received))
    assert json.loads(raw)["content"] == [{"type": "text", "text": FINAL}]
    (role, result), = find_blocks(received[-1][1], "tool_use_id", RECONNECT_ID)
    assert role == "user" and result["content"].count(SECOND_REPLY) == 1
    duplicate, response = call(18090, "POST", "/v1/messages", token, follow, headers)
    assert duplicate == 400 and len(received) == 3, (duplicate, response, len(received))

    def replay_diagnostics():
        rows = manage("GET", "request-diagnostics")["items"]
        readers = {row["request_id"]: row for row in rows if row.get("outcome") == "cancelled"}
        cached = [row for row in rows if row.get("outcome") == "tui_reconnect_cached"]
        if original_request_id in readers and live_request_id in readers and cached:
            return readers[original_request_id], readers[live_request_id], cached

    original_record, live_record, (cached_record,) = wait_for(replay_diagnostics)
    assert original_record["attempt_count"] == 1 and live_record["attempt_count"] == cached_record["attempt_count"] == 0
    return {"disconnect_before_model_finished": True, "retry_after_seconds": 6,
            "replayed_message_id": original[0]["message"]["id"], "replayed_tool_id": RECONNECT_ID,
            "live_replay_disconnected": True, "cached_replay_request_id": cached_record["request_id"],
            "replay_new_model_posts": 0, "model_posts": len(received),
            "client_tool_calls": callbacks, "old_tool_calls": 0, "stale_receipt_status": duplicate,
            "attempts": verify_captures(manage, received, account_token)}


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


def verify_message_system_roles(manage, token, account, received, model_betas, *, fixed=False):
    """对照公开来源、消息级角色与出站归属。@param manage 管理入口。@param token 合成令牌。
    @param account 选定账号。@param received 模型实收。@param model_betas 模型头实收。
    @param fixed 是否按普通 API 已验收状态和实收断言。@return 逐例证据。
    """
    backend = account["request_backend"]
    assert backend in ("native293", "tui_v2")
    manage("PUT", "settings", {"message_cache_control_rewrite": "off", "cache_control_ttl_rewrite": "off"})
    model_ok = "claude-opus-5-5"
    beta = ("mid-conversation-system-2026-04-07", "per-turn-control-2026-07-01",
            "mid-conversation-system-clear-at-2026-08-21")
    root = {"type": "text", "text": "合成根系统指令。", "cache_control": {"type": "ephemeral", "ttl": "5m"}}
    rows = [
        {"role": "user", "content": "合成第一轮问题。"},
        {"role": "assistant", "content": "合成历史答复。"},
        {"role": "system", "content": [{**root, "text": "合成中途系统指令。"}], "clear_at": "next_user_message"},
        {"role": "system", "content": [], "output_config": {"effort": "high"}},
        {"role": "user", "content": "合成当前问题。"},
    ]
    default_policy = "replace" if backend == "native293" else "append"
    cases = [
        ("api_with_betas", "api", default_policy, model_ok, "system", True),
        ("api_without_betas", "api", default_policy, model_ok, "system", False),
        ("cc_ua_only", "ua_only", default_policy, model_ok, "system", True),
        ("cc_with_billing", "cc_with_billing", default_policy, model_ok, "system", True),
        ("cc_without_billing", "cc_without_billing", default_policy, model_ok, "system", True),
        ("cc_alias_without_billing", "cc_without_billing_alias", default_policy, model_ok, "system", True),
        ("cc_bad_metadata", "cc_bad_metadata", default_policy, model_ok, "system", True),
        ("api_denied_model", "api", default_policy, MODEL, "system", True),
        ("cc_denied_model", "cc_with_billing", default_policy, MODEL, "system", True),
        ("user_control_fields", "api", default_policy, model_ok, "user_fields", True),
        ("assistant_control_fields", "api", default_policy, model_ok, "assistant_fields", True),
        ("bad_clear_at", "api", default_policy, model_ok, "bad_clear_at", True),
        ("root_system_control", "api", default_policy, MODEL, "root_only", False),
    ]
    can_set_policy = backend == "tui_v2" and account.get("tui_system_prompt_policy_available") is True
    if can_set_policy:
        cases.extend((policy + "_" + source, source, policy, model_ok, "system", True)
                     for policy in ("replace", "user_reminder")
                     for source in ("api", "ua_only", "cc_with_billing", "cc_without_billing"))
        cases.append(("replace_cc_alias_without_billing", "cc_without_billing_alias", "replace", model_ok, "system", True))

    rejections = {
        "api_denied_model": (400, "system_role_model_not_allowed"),
        "user_control_fields": (422, "unsupported_parameter"),
        "assistant_control_fields": (422, "unsupported_parameter"),
        "bad_clear_at": (400, "invalid_parameter"),
    }
    if fixed:
        cases = [case for case in cases if case[1] == "api"]
        policies = ("replace",)
        if backend == "tui_v2":
            assert can_set_policy
            policies = ("append", "replace", "user_reminder")
            for policy in policies[1:]:
                rejections[policy + "_api"] = (422, "unsupported_parameter")
                rejections["minimal_system_" + policy] = (422, "unsupported_parameter")
                rejections["minimal_system_after_user_" + policy] = (422, "unsupported_parameter")
                rejections["minimal_system_only_" + policy] = (422, "unsupported_parameter")
        cases.extend((variant + "_" + policy, "api", policy, model_ok, variant, False)
                     for policy in policies
                     for variant in ("minimal_root_only", "minimal_system", "minimal_system_after_user"))
        if backend == "tui_v2":
            cases.extend(("minimal_system_only_" + policy, "api", policy, model_ok, "minimal_system_only", False)
                         for policy in policies)

    proof = {}
    active_policy = default_policy
    for label, origin, policy, model, variant, with_betas in cases:
        if policy != active_policy:
            account = manage("PUT", f"accounts/{account['id']}", {"client_system_prompt_policy": policy})
            assert account["client_system_prompt_policy"] == policy
            active_policy = policy
        session = str(uuid4())
        headers = {"User-Agent": "flower2api-system-role-fixture/1", "x-session-id": session}
        if with_betas:
            headers["anthropic-beta"] = ",".join(beta)
        if origin == "ua_only":
            headers["User-Agent"] = "claude-cli/2.1.293 (external, cli)"
        elif origin != "api":
            family = "claude-code" if origin == "cc_without_billing_alias" else "claude-cli"
            headers.update({"User-Agent": f"{family}/2.1.293 (external, cli)", "x-app": "cli",
                            "x-claude-code-session-id": session})
        messages = deepcopy(rows)
        system = [root]
        if variant.startswith("minimal_"):
            system = [{"type": "text", "text": root["text"]}]
            messages = [*messages[:2], messages[-1]]
            if variant != "minimal_root_only":
                # 保留监督窗口的原位置，另测供应商文档支持的 user 与 assistant 之间。
                position = 1 if variant == "minimal_system_after_user" else 2
                messages.insert(position, {"role": "system", "content": [
                    {"type": "text", "text": rows[2]["content"][0]["text"]},
                ]})
        elif variant == "root_only":
            messages = [row for row in messages if row["role"] != "system"]
            system = [dict(type="text", text=root["text"])]
        elif variant.endswith("_fields"):
            messages[2]["role"] = variant.removesuffix("_fields")
        elif variant == "bad_clear_at":
            messages[2]["clear_at"] = "past"
        body = {"model": model, "max_tokens": 128, "stream": True, "messages": messages, "system": system}
        if variant == "minimal_system_only":
            del body["system"]
        if origin.startswith("cc_"):
            # 使用合成身份对照结构校验，公开鉴权仍由同一个真实网关令牌完成。
            identity = {"type": "text", "text": "You are Claude Code, Anthropic's official CLI for Claude."}
            body["system"] = [identity, *system]
            if not origin.startswith("cc_without_billing"):
                body["system"].insert(0, {"type": "text", "text":
                    "x-anthropic-billing-header: cc_version=2.1.293.abc; cc_entrypoint=cli;"})
            body["metadata"] = {"user_id": json.dumps({"device_id": "bad" if origin == "cc_bad_metadata" else "1" * 64,
                                                       "account_uuid": "", "session_id": session})}

        before = len(received)
        before_claims = len(MODEL_BODY_TRACE.read_text().splitlines()) if backend == "tui_v2" else 0
        expected_status, expected_code = rejections.get(label, (200, None)) if fixed else (None, None)
        status, raw, request_id = checked_messages(
            manage, token, body, headers, received, label, expected_status=expected_status,
            trace_startup=backend == "tui_v2",
        )
        result = {"request_id": request_id}
        query = "request-diagnostics?" + urlencode({"correlation_id": request_id})
        (record,) = wait_for(lambda: [item for item in manage("GET", query)["items"] if item.get("finished_at")])
        assert record["request_id"] == request_id
        details = manage("GET", "request-diagnostics/" + request_id)
        reservation = (details["request"].get("context") or {}).get("tui_reservation_id")
        claims = ([json.loads(line) for line in MODEL_BODY_TRACE.read_text().splitlines()[before_claims:]]
                  if backend == "tui_v2" else [])
        result.update(status=status, origin_shape=origin, policy=policy, model=model,
                      input_roles=[row["role"] for row in messages], input_betas=list(beta) if with_betas else [],
                      model_posts=len(received) - before, attempt_count=record["attempt_count"],
                      diagnostics_stage=record.get("error_stage"))
        if status == 200:
            frames = [json.loads(line[5:]) for line in raw.splitlines() if line.startswith(b"data:")]
            assert frames[-1]["type"] == "message_stop"
            ((body_hash, model_body, _),) = received[before:]
            if backend == "tui_v2":
                (claim,) = claims
                assert claim["sha256"] == body_hash
                if reservation is not None:
                    assert claim["reservation_id"] == reservation
                result.update(reservation_id=claim["reservation_id"],
                              provider_path="interactive_cli" if claim["from_interactive_cli"] else "account_sender",
                              attribution="request_reservation" if reservation is not None else "serial_provider_digest")
                if fixed:
                    (attempt,) = details["attempts"]
                    observed = attempt["context"].get("tui_instruction_location")
                    expected = None if variant == "minimal_system_only" else (
                        "user_reminder" if policy == "user_reminder" else "system"
                    )
                    assert observed == expected, (label, attempt)
                    if variant in ("system", "minimal_system", "minimal_system_after_user", "minimal_system_only"):
                        assert attempt["context"]["tui_body_source"] == "account_sender", (label, attempt)
                    result["diagnostic_instruction_location"] = observed
            else:
                result["provider_path"] = "native293"
            model_system = model_body.get("system", [])
            identity_rows = [block.get("text", "") for block in model_system if isinstance(block, dict)]
            metadata = model_body.get("metadata", {}).get("user_id")
            model_identity = json.loads(metadata) if isinstance(metadata, str) and metadata.startswith("{") else {}
            result.update(model_body_sha256=body_hash, model_roles=[row["role"] for row in model_body["messages"]],
                          model_system_rows=[row for row in model_body["messages"] if row["role"] == "system"],
                          model_root_system=[block for block in model_system
                                             if isinstance(block, dict) and block.get("text") == root["text"]],
                          model_betas=[item.strip() for item in model_betas[-1].split(",") if item.strip()],
                          model_billing_present=any(text.startswith("x-anthropic-billing-header:") for text in identity_rows),
                          model_metadata_present=bool(metadata),
                          model_fixture_device_retained=model_identity.get("device_id") == "1" * 64,
                          messages_preserved=model_body["messages"] == messages)
            if variant in ("system", "minimal_system", "minimal_system_after_user", "minimal_system_only"):
                top_level = [] if variant == "minimal_system_only" else system
                assert model_body["messages"] == messages and result["model_root_system"] == top_level, (label, result)
        else:
            assert len(received) == before and not claims, (label, result)
            result["error_code"] = json.loads(raw)["error"].get("code")
        if fixed:
            posts = int(expected_status == 200)
            assert (result.get("error_code"), result["model_posts"], result["attempt_count"]) == (
                expected_code, posts, posts,
            ), (label, result)
            if variant in ("root_only", "minimal_root_only"):
                assert result["provider_path"] == ("interactive_cli" if backend == "tui_v2" else "native293"), (
                    label, result,
                )
        proof[label] = result
    assert not any(path.is_file() for path in Path("/flows/api").rglob("*"))
    return {"backend": backend, "cases": proof, "model_posts": len(received), "wire_final": "unavailable"}


def verify_client_thinking_reply(raw, stream, model, summary):
    """验证公开 SSE 或 JSON 保留合成摘要及签名。@param raw 公开回复。@param stream 是否流式。
    @param model 请求模型。@param summary 预期显示的文字。@return 客户端实际语义。
    """
    content = [{**SIGNED_THINKING, "thinking": summary}, {"type": "text", "text": FINAL}]
    if not stream:
        reply = json.loads(raw)
        assert (reply["model"], reply["stop_reason"], reply["content"]) == (model, "end_turn", content), reply
        return {"format": "json", "content": reply["content"]}

    frames = [json.loads(line[5:]) for line in raw.splitlines() if line.startswith(b"data:")]
    assert frames[0]["message"]["model"] == model and frames[-1]["type"] == "message_stop", frames
    starts = [(event["index"], event["content_block"]) for event in frames if event["type"] == "content_block_start"]
    assert starts == [(0, {"type": "thinking", "thinking": ""}), (1, {"type": "text", "text": ""})], starts
    deltas = [(event["index"], event["delta"]) for event in frames if event["type"] == "content_block_delta"]
    expected = [(0, {"type": "thinking_delta", "thinking": summary})] if summary else []
    expected.extend([(0, {"type": "signature_delta", "signature": SIGNED_THINKING["signature"]}),
                     (1, {"type": "text_delta", "text": FINAL})])
    assert deltas == expected, deltas
    (terminal,) = [event["delta"] for event in frames if event["type"] == "message_delta"]
    assert terminal["stop_reason"] == "end_turn", terminal
    return {"format": "sse", "deltas": deltas, "stop_reason": terminal["stop_reason"]}


def verify_thinking_display_contract(manage, token, identifier, received, model, thinking_cli_summaries):
    """对照公开入口 display 缺省和显式模式。@param manage 管理入口。@param token 合成令牌。
    @param identifier 账号 ID。@param received 模型实收列表。@param model 固定模型。
    @param thinking_cli_summaries 隔离 CLI 摘要设置。@return 逐例证据。
    """
    configurations = {
        "no_thinking": None,
        "default_display": {"type": "adaptive"},
        "omitted": {"type": "adaptive", "display": "omitted"},
        "summarized": {"type": "adaptive", "display": "summarized"},
    }
    policies = ("append", "replace", "user_reminder")
    native_default = {**ADAPTIVE_THINKING, "display": "summarized"} if thinking_cli_summaries else ADAPTIVE_THINKING
    if thinking_cli_summaries is not None:
        configurations = {"no_thinking": None}
        policies = ("append",)
    proof = {}
    for policy in policies:
        account = manage("PUT", f"accounts/{identifier}", {"client_system_prompt_policy": policy})
        assert account["client_system_prompt_policy"] == policy
        for label, thinking in configurations.items():
            native = label in ("no_thinking", "summarized")
            for stream in (True, False):
                output = "sse" if stream else "json"
                phase = f"{policy}_{label}_{output}"
                question = f"合成思考显示用例 {phase}"
                headers = {"x-session-id": str(uuid4()), "User-Agent": "flower2api-thinking-display-fixture/1"}
                body = {"model": model, "max_tokens": 128, "stream": stream,
                        "messages": [{"role": "user", "content": question}]}
                if thinking is not None:
                    body["thinking"] = thinking
                before = len(received)
                before_claims = len(MODEL_BODY_TRACE.read_text().splitlines())
                status, raw, request_id = checked_messages(
                    manage, token, body, headers, received, phase,
                    expected_status=200 if native or policy == "append" else 422, trace_startup=True,
                )
                diagnostic_path = "request-diagnostics/" + request_id

                def finished_diagnostics():
                    detail = manage("GET", diagnostic_path)
                    return detail if detail["request"].get("finished_at") else None

                detail = wait_for(finished_diagnostics)
                request, attempts = detail["request"], detail["attempts"]
                assert request["request_id"] == request_id
                reservation = (request.get("context") or {}).get("tui_reservation_id")
                claims = MODEL_BODY_TRACE.read_text().splitlines()[before_claims:]
                result = {"status": status, "policy": policy, "format": output, "request_id": request_id,
                          "reservation_id": reservation, "attempt_count": len(attempts),
                          "model_posts": len(received) - before}
                if thinking is not None:
                    result["input_thinking"] = thinking
                if status == 422:
                    assert before == len(received) and not (attempts or claims), (phase, result)
                    result["error_code"] = json.loads(raw)["error"]["code"]
                    assert result["error_code"] == "unsupported_parameter", (phase, result)
                else:
                    ((body_hash, model_body, _),) = received[before:]
                    (raw_claim,), (attempt,) = claims, attempts
                    claim = json.loads(raw_claim)
                    assert claim["sha256"] == body_hash and claim["reservation_id"] == reservation, (phase, claim)
                    assert attempt["request_id"] == request_id and attempt["attempt_id"] == reservation, (phase, attempt)
                    from_cli = claim["uses_native_history"]
                    assert from_cli is native and claim["from_interactive_cli"] is from_cli, (phase, claim)
                    assert model_body["model"] == model and model_body["thinking"] == (thinking or native_default), (
                        phase, model_body["thinking"],
                    )
                    assert sum(block.get("text") == question for row in model_body["messages"] if row["role"] == "user"
                               for block in blocks(row)) == 1, phase
                    display = thinking.get("display", THINKING_DISPLAY_DEFAULTS[model]) if thinking else native_default["display"]
                    summary = SIGNED_THINKING["thinking"] if display == "summarized" else ""
                    result.update(provider_path="interactive_cli" if from_cli else "account_sender", attempt_id=reservation,
                                  uses_native_history=from_cli,
                                  model_thinking=model_body["thinking"], model_body_sha256=body_hash,
                                  simulated_model_display=display,
                                  client=verify_client_thinking_reply(raw, stream, model, summary))
                proof[phase] = result
    assert not any(path.is_file() for path in Path("/flows/api").rglob("*"))
    return {"model": model, "cli_show_thinking_summaries": thinking_cli_summaries,
            "wire_final": "unavailable", "cases": proof, "model_posts": len(received)}


def auxiliary_usage_rows(database, model, *, tool_output=False):
    """等待主轮与辅助轮分别落账。@param database 隔离库。@param model 辅助模型。
    @param tool_output 合成模型是否返回超出建议范围的工具。@return 用量行。
    """
    expected = [(MODEL, 10, 8, 0)] * 2
    if model is not None:
        expected.append((model, AUXILIARY_USAGE[0], 0, 1) if tool_output else (model, *AUXILIARY_USAGE, 0))
    with closing(connect(database)) as connection:
        rows = connection.execute(
            "SELECT model,input_tokens,output_tokens,partial FROM usage_records WHERE account_id=1"
        ).fetchall()
    if len(rows) < len(expected):
        return None
    assert sorted(rows) == sorted(expected), rows
    return rows if tool_output else [row[:3] for row in rows]


def verify_pending_auxiliary(manage, token, headers, received, auxiliary_received, database, sample, *, kind, mode, reply):
    """在真实 CLI 等待原回执时提交真实公开辅助轮。
    @param manage 管理入口。@param token 调用方。@param headers 主轮会话。@param received 主轮模型实收。
    @param auxiliary_received 辅助轮模型实收。@param database 隔离库。@param sample 官方实际请求。
    @param kind 标题或建议。@param mode 转发、拦截或混合版本对照。@param reply 隔离模型的独立回复。
    @return 脱敏证据。
    """
    def waiting_rows():
        with closing(connect(database)) as connection:
            return connection.execute("SELECT * FROM tui_native_turns").fetchall()

    (waiting,) = waiting_rows()
    assert json.loads(waiting[-1]) == [NEW_ID]
    (binding,) = Path("/native/tui-workspaces").glob("*.json")
    bound_bytes = binding.read_bytes()
    native_id = json.loads(bound_bytes)["native_session_id"]
    projects = Path("/native/tui-sessions") / native_id / "home/.claude/projects"
    archive, = projects.glob("*/" + native_id + ".jsonl")
    snapshot = wait_for(lambda: (raw if NEW_ID.encode() in (raw := archive.read_bytes()) else None))
    session = headers["x-session-id"]
    body = sample["body"]
    assert json.loads(body["metadata"]["user_id"])["session_id"] == session
    incoming = {**sample["headers"], "x-session-id": session}
    status, raw, request_id = checked_messages(
        manage, token, body, incoming, auxiliary_received, f"{kind}_during_tool_wait",
        expected_status=503 if mode == "pool-unsupported" else 200, trace_startup=True,
    )
    assert len(received) == 1
    after = archive.read_bytes()
    assert after == snapshot
    assert waiting_rows() == [waiting] and binding.read_bytes() == bound_bytes
    detail = manage("GET", "request-diagnostics/" + request_id)
    root, attempts = detail["request"], detail["attempts"]
    assert root["original_session_id"] == session
    proof = {f"{kind}_request_id": request_id, f"{kind}_status": status, f"{kind}_model_posts": len(auxiliary_received),
             "main_archive_unchanged": after == snapshot,
             f"{kind}_attempt_count": len(attempts), "tool_history_preserved": True}
    if mode == "pool-unsupported":
        assert not auxiliary_received and not attempts and root["error_stage"] == "tui_prepare_exchange"
        proof[f"{kind}_error_stage"] = root["error_stage"]
        return proof
    events = [json.loads(line[5:]) for line in raw.splitlines() if line.startswith(b"data:")]
    if mode == "tool-output":
        assert events[-1] == {"type": "error", "error": {"type": "api_error", "message": "建议回复包含工具调用"}}
        assert b"toolu_unexpected_suggestion" not in raw
        proof["unexpected_tool_rejected"] = True
    else:
        assert events[-1]["type"] == "message_stop"
    text = "".join(event["delta"]["text"] for event in events if event["type"] == "content_block_delta")
    if mode == "mock":
        assert text == ("" if kind == "suggestion" else '{"title":"New Conversation"}')
        assert not auxiliary_received and not attempts and root["outcome"] == "mock"
    else:
        (digest, native, _), = auxiliary_received
        (attempt,) = attempts
        assert attempt["request_id"] == request_id and attempt["attempt_id"] == root["context"]["tui_reservation_id"]
        assert text == ("" if mode == "tool-output" else reply)
        assert native == body, (kind, sorted(key for key in native.keys() | body.keys() if native.get(key) != body.get(key)))
        snapshot = wait_for(lambda: manage(
            "GET", f"request-diagnostics/{request_id}/captures/{attempt['attempt_id']}"
        ).get("snapshot"))
        stages = {stage["stage"]: stage for stage in snapshot["stages"]}
        assert stages["wire_final"]["status"] == "unavailable", stages["wire_final"]
        proof.update({
            f"{kind}_attempt_id": attempt["attempt_id"], f"{kind}_model_body_sha256": digest,
            f"{kind}_response_id": events[0]["message"]["id"],
            f"{kind}_capture_representation": stages["tui_provider_request"]["representation"],
            "final_tls_capture": "unavailable",
        })
    return proof


def verify_no_tool_choice(manage, token, identifier, received):
    """核对公开无工具要求和实际 CLI 正文。@param manage 管理入口。@param token 调用方。
    @param identifier 合成账号 ID。@param received 模型实收。@return 按策略的证据。
    """
    none = {"type": "none"}
    variants = {"default": {}, "no_tools": {"tool_choice": none},
                "empty_tools": {"tools": [], "tool_choice": none},
                "declared_tool": {"tools": [TOOL], "tool_choice": none}}
    cases = {}
    for policy in ("append", "replace", "user_reminder"):
        account = manage("PUT", f"accounts/{identifier}", {"client_system_prompt_policy": policy})
        assert account["client_system_prompt_policy"] == policy
        for label, fields in variants.items():
            phase = f"{policy}_{label}"
            question = f"合成无工具请求 {phase}"
            headers = {"User-Agent": "flower2api-no-tools-fixture/1", "x-session-id": str(uuid4())}
            body = {"model": MODEL, "max_tokens": 128, "stream": False, "system": SYSTEM[0],
                    "messages": [{"role": "user", "content": question}], **fields}
            from_cli = label != "declared_tool"
            expected_status = 200 if from_cli or policy == "append" else 422
            before = len(received)
            status, raw, request_id = checked_messages(manage, token, body, headers, received, phase,
                                                       expected_status=expected_status, trace_startup=True)
            reservation, record, claims = cache_marker_claims(manage, request_id)
            proof = {"status": status, "request_id": request_id, "reservation_id": reservation,
                     "attempt_count": record["attempt_count"], "model_posts": len(received) - before,
                     "input_tools": fields.get("tools"), "input_tool_choice": fields.get("tool_choice")}
            if status == 422:
                assert not (claims or proof["attempt_count"] or proof["model_posts"]), (phase, proof)
                proof["error_code"] = json.loads(raw)["error"]["code"]
                assert proof["error_code"] == "unsupported_parameter", (phase, raw)
            else:
                ((digest, model, _),), (claim,) = received[before:], claims
                assert proof["attempt_count"] == 1 and claim["sha256"] == digest, (phase, proof, claim)
                assert claim["uses_native_history"] is from_cli and claim["from_interactive_cli"] is from_cli, claim
                assert model.get("tools", []) == fields.get("tools", []), (phase, model)
                assert model.get("tool_choice", none if from_cli else None) == none, (phase, model)
                user_texts = [b.get("text", "") for row in model["messages"] if row["role"] == "user" for b in blocks(row)]
                system = model["system"]
                system_texts = [system] if isinstance(system, str) else [b["text"] for b in system]
                assert sum(text.count(question) for text in user_texts) == 1, (phase, user_texts)
                reminder = policy == "user_reminder"
                assert sum(text.count(SYSTEM[0]) for text in user_texts) == int(reminder), (phase, user_texts)
                assert sum(text.count(SYSTEM[0]) for text in system_texts) == int(not reminder), (phase, system_texts)
                reply = json.loads(raw)
                assert reply["stop_reason"] == "end_turn" and reply["content"] == [{"type": "text", "text": FINAL}], raw
                proof.update(provider_path="interactive_cli" if from_cli else "account_sender", model_body_sha256=digest,
                             model_tools=model.get("tools"), model_tool_choice=model.get("tool_choice"),
                             client_stop_reason=reply["stop_reason"])
            cases[phase] = proof
    assert not any(path.is_file() for path in Path("/flows/api").rglob("*"))
    return {"cases": cases, "model_posts": len(received), "wire_final": "unavailable"}


def fixture_forced_tool_sse(body):
    """按实收工具选择返回合成 tool_use。@param body 模型实收。@return 原始 SSE。"""
    choice = body.get("tool_choice", {})
    if choice.get("type") in ("any", "tool"):
        repeat = bool(find_blocks(body, "tool_use_id", NEW_ID))
        # any 的两次响应选不同工具，指定工具的两次响应保持同名并分配独立 ID。
        selected = choice.get("name", SECOND_TOOL["name"] if repeat else TOOL["name"])
        if any(tool["name"] == selected for tool in body.get("tools", [])):
            tool_id = SECOND_ID if repeat else NEW_ID
            tool = {"type": "tool_use", "name": selected, "id": tool_id, "input": SECOND_ARGS if repeat else ARGS}
            return message_sse(tool, "tool_use", f"msg_{tool_id}")
    return message_sse({"type": "text", "text": FINAL}, "end_turn", "msg_forced_final")


def verify_forced_tool_choice(manage, token, identifier, received, sender_status, restart, *, metadata_only):
    """从公开入口核对强制选择、原工具回执和 CLI 正文。
    @param manage 管理入口。@param token 合成令牌。@param identifier 账号 ID。
    @param received 模型实收。@param sender_status 失败后查询发送器。@param restart 可选的发送器重启。
    @param metadata_only 是否仅验证原档缺主轮的受控对照。
    @return 按请求关联的证据。
    """
    cases = {}
    tools = [TOOL, SECOND_TOOL]

    def post(body, phase, expected_status):
        before = len(received)
        ingress_digest = sha256(encoded(body)).hexdigest()
        startup_event("forced_tool_ingress", phase=phase, session_id=headers["x-session-id"],
                      ingress_body_sha256=ingress_digest)
        status, raw, request_id = checked_messages(manage, token, body, headers, received, phase,
                                                   expected_status=expected_status, trace_startup=True,
                                                   sender_status=sender_status)
        reservation, record, claims = cache_marker_claims(manage, request_id)
        proof = {"status": status, "request_id": request_id, "reservation_id": reservation,
                 "attempt_count": record["attempt_count"], "model_posts": len(received) - before,
                 "ingress_body_sha256": ingress_digest}
        if status != 200:
            assert proof["attempt_count"] == proof["model_posts"] == 0 and not claims, (phase, proof)
            proof.update(error_code=json.loads(raw)["error"]["code"], diagnostics_stage=record.get("error_stage"))
            return raw, proof
        ((digest, model, _),), (claim,) = received[before:], claims
        assert proof["attempt_count"] == proof["model_posts"] == 1 and claim["sha256"] == digest, (phase, proof)
        assert not claim["from_interactive_cli"] and not claim["uses_native_history"], (phase, claim)
        assert claim["cli_sha256"] and claim["cli_sha256"] != digest, (phase, claim)
        assert claim["cli_tool_choice"] in (None, {"type": "auto"}), (phase, claim)
        assert model["tool_choice"] == body["tool_choice"] and model["tools"] == tools, (phase, model)
        assert model["thinking"] == body["thinking"], (phase, model)
        result = [(r["role"], b) for r in body["messages"] for b in blocks(r) if b["type"] in ("tool_use", "tool_result")]
        observed = [(r["role"], b) for r in model["messages"] for b in blocks(r) if b["type"] in ("tool_use", "tool_result")]
        assert observed == result, (phase, observed)
        proof.update(provider_path="account_sender", model_body_sha256=digest, model_tool_choice=model["tool_choice"],
                     model_tools=[tool["name"] for tool in model["tools"]], tool_history=observed,
                     cli_body_sha256=claim["cli_sha256"], cli_tool_choice=claim["cli_tool_choice"],
                     cli_tool_names=claim["cli_tool_names"])
        return raw, proof

    policies = ("append",) if restart else ("append", "replace", "user_reminder")
    choices = {"named": FORCED_CHOICES["named"]} if metadata_only else FORCED_CHOICES
    for policy in policies:
        account = manage("PUT", f"accounts/{identifier}", {"client_system_prompt_policy": policy})
        assert account["client_system_prompt_policy"] == policy
        for label, choice in choices.items():
            phase = policy + "_" + label
            headers = {"x-session-id": str(uuid4()), "User-Agent": "flower2api-forced-tool-fixture/1"}
            messages = [{"role": "user", "content": "查询合成便签。"}]
            body = {"model": MODEL, "max_tokens": 128, "messages": messages, "tools": tools, "stream": False,
                    "system": SYSTEM[0], "thinking": {"type": "disabled"}, "tool_choice": choice}
            status = 200 if policy == "append" else 422
            raw, first = post(body, phase + "_initial", status)
            if status == 422:
                assert first["error_code"] == "unsupported_parameter", (phase, raw)
                cases[phase] = {"initial": first}
                continue
            second_name = SECOND_TOOL["name"]
            first_name = TOOL["name"] if label == "any" else second_name
            follow = body
            tool_proofs = [first]
            preserved = None
            for tool_id, name, args in ((NEW_ID, first_name, ARGS), (SECOND_ID, second_name, SECOND_ARGS)):
                if tool_id == SECOND_ID:
                    raw, step = post(follow, phase + "_receipt_forced", 200)
                    tool_proofs.append(step)
                    if preserved:
                        marker = ("--name=" + headers["x-session-id"]).encode()
                        (path,) = [path for path in Path("/proc").glob("[0-9]*/cmdline")
                                   if fixture_command_has(path, marker)]
                        args_wire = path.read_bytes().split(b"\0")
                        new_id = args_wire[args_wire.index(b"--session-id") + 1].decode()
                        assert UUID(new_id).version == 4 and new_id != preserved[0].stem
                        step["recovered_native_session_id"] = new_id
                tool_reply = json.loads(raw)
                expected = {"type": "tool_use", "id": tool_id, "name": name, "input": args}
                assert tool_reply["stop_reason"] == "tool_use" and tool_reply["content"] == [expected], (phase, tool_reply)
                tool_proofs[-1]["public_tool"] = expected
                receipt = {"type": "tool_result", "tool_use_id": tool_id, "content": REPLY}
                messages = [*messages, {"role": "assistant", "content": tool_reply["content"]},
                            {"role": "user", "content": [receipt]}]
                follow = {**body, "messages": messages}
                if tool_id == NEW_ID and restart:
                    preserved = restart(headers)
            final_request = {**follow, "tool_choice": {"type": "auto"}}
            raw, final = post(final_request, phase + "_receipt_auto", 200)
            reply = json.loads(raw)
            assert reply["stop_reason"] == "end_turn" and reply["content"] == [{"type": "text", "text": FINAL}], raw
            final.update(client_text=reply["content"][0]["text"], client_stop_reason=reply["stop_reason"])
            cases[phase] = {"initial": first, "forced_receipt": tool_proofs[-1], "auto_receipt": final, "client_tool_calls": 2}
            if preserved:
                archive, snapshot, binding_file, binding_snapshot = preserved
                assert archive.read_bytes() == snapshot and binding_file.read_bytes() == binding_snapshot
                cases[phase]["original_archive"] = {"native_session_id": archive.stem,
                                                   "sha256": sha256(snapshot).hexdigest(),
                                                   "metadata_rows": len(snapshot.splitlines())}
    assert not any(path.is_file() for path in Path("/flows/api").rglob("*"))
    return {"wire_final": "unavailable", "restarted": restart is not None, "cases": cases, "model_posts": len(received)}


def verify_structured_output(manage, token, identifier, received):
    """核对三种账号动作下的普通结构化输出。
    @param manage 管理入口。@param token 合成令牌。@param identifier 账号 ID。
    @param received 隔离模型实收。@return 公开响应和发送归属证据。
    """
    system = "合成结构化输出用例的工作指令。"
    configs = {"no_schema": None, "schema": {"format": STRUCTURED_FORMAT},
               "schema_with_effort": {"effort": "medium", "format": STRUCTURED_FORMAT}}
    cases = {}
    for policy in ("append", "replace", "user_reminder"):
        account = manage("PUT", f"accounts/{identifier}", {"client_system_prompt_policy": policy})
        assert account["client_system_prompt_policy"] == policy
        for label, config in configs.items():
            for stream in (True, False):
                response_mode = "sse" if stream else "json"
                phase = f"{policy}_{label}_{response_mode}"
                question = f"查询合成订单的状态 {phase}"
                headers = {"x-session-id": str(uuid4()), "User-Agent": "flower2api-structured-output-fixture/1"}
                body = {"model": MODEL, "max_tokens": 128, "stream": stream, "system": system,
                        "messages": [{"role": "user", "content": question}]}
                if config is not None:
                    body["output_config"] = config
                expected_status = 200 if config is None or policy == "append" else 422
                before = len(received)
                before_claims = len(MODEL_BODY_TRACE.read_text().splitlines())
                status, raw, request_id = checked_messages(manage, token, body, headers, received, phase,
                                                           expected_status=expected_status, trace_startup=True)
                path = "request-diagnostics/" + request_id

                def finished_diagnostics():
                    detail = manage("GET", path)
                    return detail if detail["request"].get("finished_at") else None

                detail = wait_for(finished_diagnostics)
                request, attempts = detail["request"], detail["attempts"]
                reservation = (request.get("context") or {}).get("tui_reservation_id")
                claims = MODEL_BODY_TRACE.read_text().splitlines()[before_claims:]
                assert request["request_id"] == request_id, request
                assert request["log_mode"] == "info" and "tui_body_source" not in (request.get("context") or {})
                assert "tui_instruction_location" not in (request.get("context") or {})
                confirmed = request["context"]["tui_confirmed_model_responses"]
                assert confirmed == int(status == 200), (phase, confirmed, request)
                summary = json.dumps(detail, ensure_ascii=False)
                assert question not in summary and system not in summary
                result = {"status": status, "policy": policy, "response_mode": response_mode,
                          "input_output_config": config,
                          "request_id": request_id, "reservation_id": reservation, "attempt_count": len(attempts),
                          "confirmed_model_responses": confirmed,
                          "model_posts": len(received) - before}
                if status == 422:
                    assert not (attempts or claims or result["model_posts"]), (phase, result)
                    error_code = json.loads(raw)["error"]["code"]
                    assert error_code == "unsupported_parameter", (phase, raw)
                    result.update(error_code=error_code, diagnostics_stage=request.get("error_stage"))
                else:
                    ((digest, native, _),) = received[before:]
                    (raw_claim,), (attempt,) = claims, attempts
                    claim = json.loads(raw_claim)
                    assert claim["sha256"] == digest and claim["reservation_id"] == reservation, (phase, claim)
                    assert attempt["request_id"] == request_id and attempt["attempt_id"] == reservation, (phase, attempt)
                    from_cli = config is None
                    assert claim["uses_native_history"] is from_cli and claim["from_interactive_cli"] is from_cli, claim
                    body_source = attempt["context"]["tui_body_source"]
                    session_origin = attempt["context"]["tui_session_origin"]
                    assert session_origin == "new_session", (phase, attempt)
                    assert attempt["log_mode"] == "info" and body_source == (
                        "interactive_cli" if from_cli else "account_sender"
                    ), (phase, attempt)
                    assert native["model"] == MODEL and native["max_tokens"] == 128 and not native.get("tools"), phase
                    output = native.get("output_config", {})
                    assert ("format" not in output if from_cli else output == config), (phase, output)
                    root = native["system"]
                    root_blocks = [root] if isinstance(root, str) else [block["text"] for block in root]
                    user_texts = [b.get("text", "") for row in native["messages"] if row["role"] == "user"
                                  for b in blocks(row)]
                    reminder = policy == "user_reminder"
                    instruction_location = attempt["context"].get("tui_instruction_location")
                    assert sum(text.count(question) for text in user_texts) == 1, (phase, user_texts)
                    assert sum(text.count(system) for text in user_texts) == int(reminder), (phase, user_texts)
                    assert sum(text.count(system) for text in root_blocks) == int(not reminder), (phase, root_blocks)
                    assert instruction_location == ("user_reminder" if reminder else "system"), (
                        phase, instruction_location, sum(text == system for text in root_blocks),
                        sum(text.endswith("\n\n" + system) for text in root_blocks),
                    )
                    if policy == "replace":
                        assert root_blocks[2:] == [system], (phase, root_blocks)
                    if stream:
                        events = [json.loads(line[5:]) for line in raw.splitlines() if line.startswith(b"data:")]
                        assert events[-1]["type"] == "message_stop", (phase, events[-1])
                        (terminal,) = [event["delta"] for event in events if event["type"] == "message_delta"]
                        text = "".join(event["delta"]["text"] for event in events
                                       if event["type"] == "content_block_delta")
                        stop_reason = terminal["stop_reason"]
                    else:
                        reply = json.loads(raw)
                        (block,) = reply["content"]
                        assert block["type"] == "text", (phase, block)
                        text, stop_reason = block["text"], reply["stop_reason"]
                    assert stop_reason == "end_turn" and text == (FINAL if from_cli else STRUCTURED_REPLY), phase
                    result.update(provider_path="interactive_cli" if from_cli else "account_sender",
                                  diagnostic_body_source=body_source,
                                  diagnostic_session_origin=session_origin,
                                  diagnostic_instruction_location=instruction_location,
                                  attempt_id=reservation, model_body_sha256=digest, model_output_config=output,
                                  model_instruction_role="user" if reminder else "system",
                                  model_root_system_shape="string" if isinstance(root, str) else "blocks",
                                  client_text=text, client_stop_reason=stop_reason)
                cases[phase] = result
    assert not any(path.is_file() for path in Path("/flows/api").rglob("*"))
    return {"wire_final": "unavailable", "cases": cases, "model_posts": len(received)}


def verify_v1_prompt_policy(token, received, model_betas):
    """从公开入口核对 V1 固定策略与输入合同。
    @param token 合成调用方令牌。@param received 模型实收。@param model_betas 模型实收功能头。@return 证据。
    """
    long_system = "你是客服助手。提到 Claude Code 时仍保留客户身份。只返回订单状态 JSON。"
    cases = (("omitted", None, None), ("empty_string", "", []), ("empty_array", [], []),
             ("string", long_system, [long_system]),
             ("ordered_blocks", [{"type": "text", "text": text} for text in SYSTEM], ["\n\n".join(SYSTEM)]))
    proof = {}
    for index, (label, system, expected) in enumerate(cases, 1):
        question = f"V1 合成查询 {index}"
        body = {"model": MODEL, "max_tokens": 128, "stream": True,
                "messages": [{"role": "user", "content": question}], "tools": [TOOL]}
        if system is not None:
            body["system"] = system
        status, raw = call(18090, "POST", "/v1/messages", token, body,
                           {"User-Agent": "flower2api-v1-policy-fixture/1", "x-session-id": str(uuid4())})
        assert status == 200 and len(received) == index, (label, status, raw, len(received))
        events = [json.loads(line[5:]) for line in raw.splitlines() if line.startswith(b"data:")]
        assert events[-1]["type"] == "message_stop"
        digest, native, _ = received[-1]
        texts = [block["text"] for block in native["system"]]
        assert texts[0].startswith("x-anthropic-billing-header:") and "cc_version=2.1.293." in texts[0]
        assert texts[1] == "You are Claude Code, Anthropic's official CLI for Claude."
        if expected is None:
            assert any(text.strip() for text in texts[2:])
        else:
            assert texts[2:] == expected, (label, texts[2:])
        assert native["tools"] == [TOOL]
        turns = [part.get("text", "") for row in native["messages"] if row["role"] == "user" for part in blocks(row)]
        assert sum(text.count(question) for text in turns) == 1
        proof[label] = {"status": status, "model_body_sha256": digest}

    # 使用上一请求实际生成的完整 CC 正文，核对显式身份和计费块不会再次叠加。
    complete = received[-1][1]
    session = json.loads(complete["metadata"]["user_id"])["session_id"]
    status, raw = call(18090, "POST", "/v1/messages", token, complete,
                       {"User-Agent": "claude-code/2.1.293 (external, cli)", "x-app": "cli",
                        "x-session-id": session, "x-claude-code-session-id": session})
    assert status == 200 and len(received) == len(cases) + 1, (status, raw, len(received))
    digest, native, _ = received[-1]
    assert native["system"][1:] == complete["system"][1:], native["system"][1:]
    assert native["messages"] == complete["messages"] and native["tools"] == complete["tools"]
    proof["complete_cc"] = {"status": status, "model_body_sha256": digest}
    marker = {"type": "ephemeral", "ttl": "5m"}
    system_rows = [
        {"role": "user", "content": "V1 系统轮合同样本"},
        {"role": "system", "content": [{"type": "text", "text": SYSTEM[0], "cache_control": marker}],
         "clear_at": "next_user_message"},
        {"role": "system", "content": [], "output_config": {"effort": "high"}},
        {"role": "user", "content": "V1 系统轮的后续问题"},
    ]
    betas = ["mid-conversation-system-2026-04-07", "per-turn-control-2026-07-01",
             "mid-conversation-system-clear-at-2026-08-21"]
    system = [{"type": "text", "text": SYSTEM[1], "cache_control": marker}]
    format_spec = {"type": "json_schema", "schema": {
        "type": "object", "properties": {"title": {"type": "string"}}, "required": ["title"],
    }}
    extra_cases = (
        ("system_rows", {"model": "claude-opus-5-5", "messages": system_rows, "system": system}, betas),
        ("forced_tool", {"tool_choice": {"type": "tool", "name": TOOL["name"]},
                         "tools": [TOOL], "thinking": {"type": "disabled"}}, []),
        ("structured_output", {"output_config": {"format": format_spec}}, []),
    )
    for label, fields, beta in extra_cases:
        count = len(received)
        body = {"model": MODEL, "max_tokens": 128, "stream": True,
                "messages": [{"role": "user", "content": "V1 额外输入合同样本"}], **fields}
        headers = {"User-Agent": "flower2api-v1-policy-fixture/1", "x-session-id": str(uuid4())}
        if beta:
            headers["anthropic-beta"] = ",".join(beta)
        status, raw = call(18090, "POST", "/v1/messages", token, body, headers)
        assert status == 200 and len(received) == count + 1, (label, status, raw, len(received))
        digest, native, _ = received[-1]
        if label == "system_rows":
            assert native["messages"] == system_rows and native["system"][1:] == fields["system"]
            assert set(beta) <= {item.strip() for item in model_betas[-1].split(",")}, model_betas[-1]
        elif label == "structured_output":
            assert native.get("output_config", {}).get("format") == format_spec, native.get("output_config")
        else:
            for name, expected in fields.items():
                assert native.get(name) == expected, (label, name, native.get(name))
        proof[label] = {"status": status, "model_body_sha256": digest}
    count = len(received)
    status, raw = call(18090, "POST", "/v1/messages", token,
                       {"model": MODEL, "max_tokens": 128, "stream": True, "messages": system_rows,
                        "system": system},
                       {"User-Agent": "flower2api-v1-policy-fixture/1", "x-session-id": str(uuid4()),
                        "anthropic-beta": ",".join(betas)})
    assert status == 400 and len(received) == count, (status, raw, len(received))
    assert json.loads(raw)["error"]["code"] == "system_role_model_not_allowed"
    proof["system_rows_unsupported_model"] = {"status": status, "model_posts": 0}
    return {"v1_fixed_policy": "replace", "launcher_sha256": V1_RUNTIME_SHA256, "model_posts": len(received), "cases": proof}


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
        explicit = info["case"] in ("multiple_blocks", "nonempty_string")
        location = ("user_reminder" if policy == "user_reminder" else "system") if explicit else None
        assert attempt["diagnostic_instruction_location"] == location, (info, attempt)
        info.update(attempt)
    return {"text_inputs": requests, "model_posts": len(received) - start}


def cache_marker_claims(manage, request_id):
    """读回公开请求的预留与正文认领。@param manage 隔离管理入口。@param request_id 请求 ID。@return 预留、诊断和认领。"""
    query = "request-diagnostics?" + urlencode({"correlation_id": request_id})
    (record,) = wait_for(lambda: [item for item in manage("GET", query)["items"] if item.get("finished_at")])
    assert record["request_id"] == request_id
    details = manage("GET", "request-diagnostics/" + request_id)["request"]
    reservation = details["context"]["tui_reservation_id"]
    claims = (json.loads(line) for line in MODEL_BODY_TRACE.read_text().splitlines())
    return reservation, record, [claim for claim in claims if claim["reservation_id"] == reservation]


def verify_cache_capabilities(manage, token, account_id, headers, received, mode):
    """比对当前块与工具声明的显式断点。@param manage 管理入口。@param token 合成令牌。
    @param account_id 测试账号。@param headers 公开头。@param received 模型实收。@param mode 对照模式。
    @return 出站角色、位置、TTL 与认领证据。
    """
    manage("PUT", "settings", {"message_cache_control_rewrite": "off", "cache_control_ttl_rewrite": "off"})
    tools = [{"name": name, "description": f"缓存实验声明 {name}",
              "input_schema": {"type": "object", "properties": {}}} for name in ("ProbeFirst", "ProbeLast")]
    texts = ["当前缓存探针第一段。", "当前缓存探针末段。"]
    cases = [(f"{surface}_{side}_{ttl or 'implicit'}", "append", surface, index, ttl)
             for surface in ("text", "tool") for index, side in enumerate(("first", "last")) for ttl in (None, "5m", "1h")]
    cases.extend((f"unmarked_{surface}", "append", surface, None, None) for surface in ("text", "tool"))
    if mode == "baseline":
        cases.extend((f"{policy}_{surface}", policy, surface, 0, "5m")
                     for policy in ("replace", "user_reminder") for surface in ("text", "tool"))
    proof = {}
    policy = None
    for name, system_policy, surface, offset, ttl in cases:
        if policy != system_policy:
            policy = system_policy
            account = manage("PUT", f"accounts/{account_id}", {"client_system_prompt_policy": policy})
            assert account["request_backend"] == "tui_v2" and account["client_system_prompt_policy"] == policy
        current = [{"type": "text", "text": text} for text in texts]
        body = {"model": MODEL, "max_tokens": 128, "stream": False, "messages": [
            {"role": role, "content": text} for role, text in HISTORY[:2]
        ] + [{"role": "user", "content": current}]}
        if surface == "tool":
            body["tools"] = [tool.copy() for tool in tools]
        expected = [None, None]
        if offset is not None:
            marker = {"type": "ephemeral"}
            if ttl is not None:
                marker["ttl"] = ttl
            targets = current if surface == "text" else body["tools"]
            targets[offset]["cache_control"] = expected[offset] = marker
        before = len(received)
        status, raw, request_id = checked_messages(
            manage, token, body, {**headers, "x-session-id": str(uuid4())}, received, name,
            expected_status=200 if policy == "append" else 422, trace_startup=True,
        )
        reservation, record, claims = cache_marker_claims(manage, request_id)
        evidence = {"http_status": status, "model_posts": len(received) - before, "request_id": request_id,
                    "reservation_id": reservation, "surface": surface, "client_markers": expected, "policy": policy,
                    "attempt_count": record["attempt_count"]}
        if status == 422:
            assert json.loads(raw)["error"]["code"] == "unsupported_parameter"
            assert before == len(received) and not claims and record["attempt_count"] == 0
        else:
            assert record["attempt_count"] == 1
            assert json.loads(raw)["content"] == [{"type": "text", "text": FINAL}]
            ((model_digest, model, _),) = received[before:]
            (claim,) = claims
            from_cli = mode != "baseline" or offset is None
            assert claim["sha256"] == model_digest and claim["from_interactive_cli"] is from_cli
            ((message_index, user),) = [(i, row) for i, row in enumerate(model["messages"])
                                        if any(block.get("text") in texts for block in blocks(row))]
            assert user["role"] == "user"
            content = [(i, block) for i, block in enumerate(blocks(user)) if block.get("text") in texts]
            assert [block["text"] for _, block in content] == texts and content[1][0] == content[0][0] + 1
            projected = model.get("tools", [])
            if surface == "tool":
                assert [(tool["name"].removeprefix("mcp__flower__"), tool["description"], tool["input_schema"])
                        for tool in projected] == [(tool["name"], tool["description"], tool["input_schema"]) for tool in tools]
            else:
                assert not projected
            observed = ([block.get("cache_control") for _, block in content] if surface == "text" else
                        [tool.get("cache_control") for tool in projected])
            if mode == "baseline" and offset is not None:
                assert observed == expected, (name, observed)
            evidence.update(from_interactive_cli=from_cli, model_body_sha256=model_digest, model_markers=observed,
                            user_message_index=message_index, user_block_indexes=[i for i, _ in content],
                            user_role=user["role"], model_tool_names=[tool["name"] for tool in projected],
                            system_markers=[block["cache_control"] for block in model.get("system", [])
                                            if "cache_control" in block])
        proof[name] = evidence
    assert not any(path.is_file() for path in Path("/flows/api").rglob("*"))
    return {"mode": mode, "cases": proof, "model_posts": len(received), "wire_final": "unavailable"}


def verify_cache_markers(manage, token, account_id, headers, received):
    """对照普通请求的缓存标记、模型实收和账号出站选择。
    @param manage 隔离管理入口。@param token 合成用户令牌。@param account_id 本次 V2 账号。
    @param headers 公开请求头。@param received 隔离模型实收。@return 按场景输出的证据。
    """
    def text(value):
        return {"type": "text", "text": value}

    def row(role, *content):
        return {"role": role, "content": list(content)}

    implied = {"type": "ephemeral"}
    short = {**implied, "ttl": "5m"}
    long = {**implied, "ttl": "1h"}
    past, answer = text("缓存标记：历史用户段。"), text("缓存标记：历史助手段。")
    question, tail = text("缓存标记：本轮问题。"), text("缓存标记：本轮尾段。")
    system = text("缓存标记：顶层系统正文。")
    prefix = [row("user", past), row("assistant", answer)]
    plain = [*prefix, row("user", question, tail)]
    current = [*prefix, row("user", {**question, "cache_control": short}, tail)]
    history = [row("user", {**past, "cache_control": long}),
               row("assistant", {**answer, "cache_control": implied}), plain[-1]]
    historical_tool = {"type": "tool_use", "name": "OldNote", "id": PAST_ID, "input": ARGS}
    historical_result = {"type": "tool_result", "tool_use_id": PAST_ID,
                         "content": [{**answer, "cache_control": short}]}
    tool = {"name": "CacheProof", "description": "仅核对声明上的缓存标记。",
            "input_schema": {"type": "object", "properties": {}}, "cache_control": long}
    closed = [prefix[0], row("assistant", historical_tool), row("user", historical_result),
              row("assistant", text("已结束旧工具轮。")), plain[-1]]
    def forced_history(marker):
        return [row("user", {**past, "cache_control": marker}),
                row("assistant", {**answer, "cache_control": marker}), plain[-1]]

    cases = (
        ("unmarked", "append", {}, plain, None, 200),
        ("current", "append", {}, current, current, 200),
        ("history", "append", {}, history, history, 200),
        ("history_replace", "replace", {"system": [system]}, history, history, 200),
        ("history_user_reminder", "user_reminder", {"system": [system]}, history, history, 200),
        ("tool", "append", {"tools": [tool]}, plain, plain, 200),
        ("nested_result", "append", {}, closed, closed, 200),
        ("root", "append", {"cache_control": implied}, plain, None, 422),
        ("system", "append", {"system": [{**system, "cache_control": long}]}, plain, None, 422),
        ("replace", "replace", {"system": [system]}, current, None, 422),
        ("user_reminder", "user_reminder", {"system": [system]}, current, None, 422),
        ("forced_ttl_5m", "append", {}, history, forced_history(short), 200),
        ("forced_ttl_1h", "append", {}, history, forced_history(long), 200),
        ("forced_unmarked", "append", {}, plain, plain, 200),
        ("forced_nested_result", "append", {}, closed, closed, 200),
    )
    ttl_settings = {"forced_ttl_5m": "5m", "forced_ttl_1h": "1h", "forced_unmarked": "5m", "forced_nested_result": "1h"}
    proof = {}
    account_path = f"accounts/{account_id}"
    for name, policy, extra, messages, expected, http_status in cases:
        account = manage("PUT", account_path, {"client_system_prompt_policy": policy})
        assert account["request_backend"] == "tui_v2" and account["client_system_prompt_policy"] == policy
        forced_ttl = ttl_settings.get(name, "off")
        manage("PUT", "settings", {"message_cache_control_rewrite": "off", "cache_control_ttl_rewrite": forced_ttl})
        body = {"model": MODEL, "max_tokens": 128, "stream": False, "messages": messages, **extra}
        before = len(received)
        status, raw, request_id = checked_messages(
            manage, token, body, {**headers, "x-session-id": str(uuid4())}, received, name,
            expected_status=http_status, trace_startup=True,
        )
        assert request_id
        reservation, record, own_claims = cache_marker_claims(manage, request_id)
        evidence = {"http_status": status, "model_posts": len(received) - before, "account_policy": policy,
                    "ttl_policy": forced_ttl,
                    "request_id": request_id, "reservation_id": reservation, "attempt_count": record["attempt_count"]}
        if status == 422:
            assert len(received) == before and not own_claims and record["attempt_count"] == 0, (name, evidence)
            error = json.loads(raw)["error"]["code"]
            assert error == "unsupported_parameter", (name, error)
            evidence["code"] = error
        else:
            assert record["attempt_count"] == 1, (name, evidence)
            assert json.loads(raw)["content"] == [text(FINAL)], (name, raw)
            ((digest, model, _),) = received[before:]
            (claim,) = own_claims
            assert claim["sha256"] == digest, (name, evidence, claim)
            from_cli = name in ("unmarked", "history", "history_replace", "history_user_reminder", "nested_result",
                                "forced_ttl_5m", "forced_ttl_1h")
            assert claim["from_interactive_cli"] is from_cli, (name, claim)
            assert model.get("tools", []) == body.get("tools", []), name
            if from_cli:
                user_texts = [b.get("text") for message in model["messages"] if message["role"] == "user"
                              for b in blocks(message)]
                assert user_texts.count(question["text"]) == user_texts.count(tail["text"]) == 1
                if name == "nested_result":
                    assert observed_cache_breakpoints(model) == []
                    assert find_blocks(model, "id", PAST_ID) == [("assistant", historical_tool)]
                    observed = find_blocks(model, "tool_use_id", PAST_ID)
                    assert observed == [("user", historical_result)], observed
                    evidence["nested_result"] = observed
                elif expected is not None:
                    markers = observed_cache_breakpoints(model)
                    assert markers == [(i, 0, row["role"], row["content"][0])
                                       for i, row in enumerate(expected[:2])], (name, markers)
                    system_text = "\n".join(block["text"] for block in model["system"])
                    assert system_text.count(system["text"]) == int(policy == "replace"), name
                    assert sum(text.count(system["text"]) for text in user_texts if text) == int(policy == "user_reminder")
                    evidence["cache_markers"] = markers
            else:
                assert model["messages"] == expected, (name, model["messages"])
                evidence["model_messages"] = model["messages"]
                if model.get("tools"):
                    evidence["model_tools"] = model["tools"]
            evidence.update(from_interactive_cli=claim["from_interactive_cli"], model_body_sha256=digest)
        proof[name] = evidence
    assert not any(path.is_file() for path in Path("/flows/api").rglob("*"))
    return {"account_backend": "tui_v2", "cases": proof, "model_posts": len(received), "wire_final": "unavailable"}


def blocks(row):
    """读取模型端实际内容块。@param row 模型消息。@return 内容块序列。"""
    return row["content"] if isinstance(row["content"], list) else [{"type": "text", "text": row["content"]}]


def observed_cache_breakpoints(model):
    """读取模型实际收到的断点。@param model 隔离模型正文。@return 有序消息、块位置与标记。"""
    assert "cache_control" not in model
    assert not any("cache_control" in block for key in ("system", "tools") for block in model.get(key, []))
    return [(index, offset, row["role"], block) for index, row in enumerate(model["messages"])
            for offset, block in enumerate(blocks(row)) if "cache_control" in block]


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


def fixture_image_blocks(*, all_formats):
    """构造内嵌图像块。@param all_formats 是否加入 JPEG、GIF、WebP。@return 合成图像块。"""
    images = {"image/png": "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+ip1sAAAAASUVORK5CYII="}
    if all_formats:
        images.update({
            "image/jpeg": "/9j/4AAQSkZJRgABAQAAAQABAAD/2wBDAAgGBgcGBQgHBwcJCQgKDBQNDAsLDBkSEw8UHRofHh0aHBwgJC4nICIsIxwc"
                          "KDcpLDAxNDQ0Hyc5PTgyPC4zNDL/wAALCAACAAIBAREA/8QAFAABAAAAAAAAAAAAAAAAAAAABv/EABQQAQAAAAAAAA"
                          "AAAAAAAAAAAAD/2gAIAQEAAD8AQP/Z",
            "image/gif": "R0lGODdhAgACAIEAAKCgoAAAAAAAAAAAACwAAAAAAgACAAAIBgABCAQQEAA7",
            "image/webp": "UklGRiQAAABXRUJQVlA4IBgAAAAwAQCdASoCAAIAAUAmJaQAA3AA/u2oAAA=",
        })
    return [{"type": "image", "source": {"type": "base64", "media_type": media_type, "data": data}}
            for media_type, data in images.items()]


def verify_image_only_requests(manage, token, account_token, headers, received, *, check_existing):
    """核对原生粘贴边界及超界请求的原入口。
    @param manage 管理入口。@param token 合成调用方。@param account_token 合成模型凭据。
    @param headers 公开请求头。@param received TLS 实收。
    @param check_existing 默认账号动作下核对超界兼容。@return 各独立请求的证据。
    """
    def chunk(kind, data):
        return pack(">I", len(data)) + kind + data + pack(">I", crc32(data, crc32(kind)))

    def make_png(width, size=None):
        # 构造合法的一行灰度 PNG，区别像素边界和文件大小边界。
        png = (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", pack(">IIBBBBB", width, 1, 8, 0, 0, 0, 0))
               + chunk(b"IDAT", compress(b"\x00" * (width + 1))) + chunk(b"IEND", b""))
        if size is not None:
            metadata = b"Probe\x00" + b"x" * (size - len(png) - 18)
            png = png[:-12] + chunk(b"tEXt", metadata) + png[-12:]
            assert len(png) == size
        return [{"type": "image", "source": {
            "type": "base64", "media_type": "image/png", "data": b64encode(png).decode("ascii"),
        }}]

    cases = [("native_width_2000", make_png(2000), True), ("native_bytes_512000", make_png(2, 512_000), True)]
    if check_existing:
        cases.extend([
            ("native_24_images", fixture_image_blocks(all_formats=True) * 6, True),
            ("existing_width_2001", make_png(2001), False),
            ("existing_bytes_512001", make_png(2, 512_001), False),
        ])
    result = {}
    for name, content, native in cases:
        body = {"model": MODEL, "max_tokens": 128, "stream": False,
                "messages": [{"role": "user", "content": content}]}
        before = len(received)
        status, raw = call(18090, "POST", "/v1/messages", token, body, {**headers, "x-session-id": str(uuid4())})
        assert status == 200 and len(received) == before + 1, (name, status, raw, len(received))
        assert json.loads(raw)["content"] == [{"type": "text", "text": FINAL}]
        if native:
            verify_current_image_row(received[-1][1], content, require_alias=True)
            (attempt,) = verify_captures(manage, received[-1:], account_token)
            result[name] = {"model_posts": 1, "attempt": attempt}
        else:
            # 只在默认账号动作核对超界兼容，保留原入口实收的图像和消息。
            assert received[-1][1]["messages"] == body["messages"]
            result[name] = {"model_posts": 1, "body_sha256": received[-1][0]}
    return result


def verify_current_image_row(native, expected, *, require_alias):
    """核对实收图文在同一条用户消息内。@param native 模型正文。
    @param expected 原始图文块。@param require_alias 是否从本轮粘贴。@return 无。
    """
    row, = [row for row in native["messages"] if any(block["type"] == "image" for block in blocks(row))]
    assert row["role"] == "user"
    observed = [{key: value for key, value in block.items() if key != "cache_control"} for block in blocks(row)]
    images = [block for block in expected if block["type"] == "image"]
    assert [block for block in observed if block["type"] == "image"] == images
    if expected[-1]["type"] == "text":
        native_end = {**expected[-1], "text": expected[-1]["text"] + "\n"}
        observed = [expected[-1] if block == native_end else block for block in observed]
    assert sum(observed[index:index + len(expected)] == expected for index in range(len(observed))) == 1
    sources = [block["text"] for block in observed if block.get("text", "").startswith("[Image: source:")]
    assert all(fullmatch(r"\[Image: source: /proc/self/fd/[0-9]+/attachment-[0-9]+\.(png|jpeg|gif|webp)\]", path)
               for path in sources)
    if require_alias:
        assert len(sources) == len(images)


def verify_raw_current_image_row(native, expected, *, stage):
    """独立核对原始模型图文块及 CLI 附加数据。@param native 模型正文。@param expected 公开业务块。
    @param stage 首轮、同进程回执或丢进程恢复。@return 原始收件字段及摘要。
    """
    row, = [row for row in native["messages"] if any(block["type"] == "image" for block in blocks(row))]
    assert row["role"] == "user"
    raw = row["content"]
    if stage == "recovered":
        assert raw == expected
        prefix = sources = []
        business = raw
    else:
        images = [block["source"] for block in expected if block["type"] == "image"]
        business_start = len(raw) - len(expected) - len(images)
        assert business_start >= 0
        prefix, business, sources = raw[:business_start], raw[business_start:-len(images)], raw[-len(images):]
        assert all(set(block) == {"type", "text"} and block["type"] == "text"
                   and block["text"].startswith("<system-reminder>\n")
                   and block["text"].rstrip("\n").endswith("</system-reminder>") for block in prefix)
        final = expected[-1]
        suffix = {**final, "text": final["text"] + "\n"} if final["type"] == "text" else final
        assert business == [*expected[:-1], suffix]
        descriptors = set()
        for number, (block, image) in enumerate(zip(sources, images, strict=True), 1):
            extension = image["media_type"].split("/")[-1]
            match = fullmatch(rf"\[Image: source: /proc/self/fd/([0-9]+)/attachment-{number}\.{extension}\]",
                              block.get("text", ""))
            assert match is not None and block["type"] == "text"
            descriptors.add(match[1])
            fields = {"type", "text"}
            if "cache_control" in block:
                assert stage == "first" and number == len(images)
                assert block["cache_control"] == {"type": "ephemeral", "ttl": "1h"}
                fields.add("cache_control")
            assert block.keys() == fields
        assert len(descriptors) == 1
    return {"role": row["role"], "raw_content_sha256": sha256(encoded(raw)).hexdigest(),
            "raw_content_equal": raw == expected, "raw_business_slice_equal": business == expected,
            "business_block_count": len(business), "raw_block_count": len(raw),
            "extra_terminal_lf": stage != "recovered" and expected[-1]["type"] == "text",
            "cli_context_count": len(prefix), "cli_attachment_source_count": len(sources),
            "cli_source_cache_control": [block["cache_control"] for block in sources if "cache_control" in block]}


def verify_history_images(manage, token, account_token, account_id, headers, received, *, all_formats):
    """核对历史用户图像与新问题的真实出站。
    @param manage 管理接口。@param token 公共令牌。@param account_token 合成账号凭据。
    @param account_id 当前账号。@param headers 固定公开会话。@param received 模型实收。
    @param all_formats 是否同时校验 JPEG、GIF、WebP。@return 测试摘要。
    """
    image_blocks = fixture_image_blocks(all_formats=all_formats)
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
            "formats": [block["source"]["media_type"] for block in image_blocks], "model_posts": len(received)}


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
        assert old_result[0] == "user" and old_result[1]["content"] == old_content, old_result
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
                                    "cli_and_https_body_sha256": digest, "final_tls_capture": "unavailable",
                                    "confirmed_model_responses": (row.get("context") or {}).get(
                                        "tui_confirmed_model_responses"),
                                    "diagnostic_body_source": (attempt.get("context") or {}).get("tui_body_source"),
                                    "diagnostic_session_origin": (attempt.get("context") or {}).get("tui_session_origin"),
                                    "diagnostic_instruction_location": (attempt.get("context") or {}).get(
                                        "tui_instruction_location")}
        return [captures[digest] for digest in expected] if captures.keys() == expected.keys() else None

    return wait_for(observe)


def main():
    """运行一次性容器中的公开验收。@return 输出脱敏证据。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gateway", type=Path, required=True)
    parser.add_argument("--sender", type=Path, required=True)
    parser.add_argument("--shared-state", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--current-text-blocks", action="store_true")
    parser.add_argument("--current-images", action="store_true")
    parser.add_argument("--current-image-ending", choices=("text", "image"), default="text")
    parser.add_argument("--history-cache-markers", action="store_true")
    parser.add_argument("--history-cache-ttl", choices=("5m", "1h"))
    parser.add_argument("--history-cache-scope", choices=("nested", "mixed"))
    system_roles = parser.add_mutually_exclusive_group()
    system_roles.add_argument("--message-system-roles", dest="message_system_roles", action="store_const", const="observe")
    system_roles.add_argument("--ordinary-message-system-contract", dest="message_system_roles", action="store_const",
                              const="ordinary-contract")
    parser.add_argument("--auto-tool-choice", action="store_true")
    parser.add_argument("--adaptive-thinking-model", choices=(MODEL, "claude-opus-5-5"))
    parser.add_argument("--adaptive-thinking-display", choices=("default", "updates", "summarized"), default="updates")
    parser.add_argument("--thinking-cli-summaries", choices=("on", "off"))
    parser.add_argument("--signed-tool-history", action="store_true")
    parser.add_argument("--signed-tool-response", choices=("signature-only", "missing-model"))
    parser.add_argument("--trace-initial-startup", action="store_true", help="记录源码 V2 夹具的启动阶段")
    fault = parser.add_mutually_exclusive_group()
    fault.add_argument("--recovery-ledger-contention", action="store_true")
    fault.add_argument("--recovery-ledger-deadline", action="store_true")
    fault.add_argument("--recovery-workspace-rejection", action="store_true")
    fault.add_argument("--recovery-slow-model", action="store_true")
    scenario = parser.add_mutually_exclusive_group()
    scenario.add_argument("--restart-history", action="store_true")
    scenario.add_argument("--text-input", action="store_true")
    scenario.add_argument("--cache-markers", action="store_true")
    scenario.add_argument("--cache-marker-capabilities", choices=("baseline", "native-default", "native-no-auto"))
    scenario.add_argument("--system-policy", action="store_true")
    scenario.add_argument("--toggle-pending-policy", action="store_true")
    scenario.add_argument("--tool-policy", choices=("replace", "user_reminder"))
    scenario.add_argument("--recover-pending-tool", action="store_true")
    scenario.add_argument("--initial-idle-model-connection", action="store_true")
    scenario.add_argument("--output-effort", action="store_true")
    scenario.add_argument("--structured-output-contract", action="store_true")
    scenario.add_argument("--forced-tool-choice-contract", choices=("live", "restart", "restart-metadata-only"))
    scenario.add_argument("--no-tool-choice-contract", action="store_true")
    scenario.add_argument("--interleaved-title", choices=("forward", "mock", "pooled", "pool-unsupported"))
    parser.add_argument("--title-request", type=Path, help="官方 CLI 隔离模型导出的标题请求")
    scenario.add_argument("--interleaved-suggestion", choices=("forward", "mock", "pooled", "pool-unsupported", "tool-output"))
    parser.add_argument("--suggestion-request", type=Path, help="官方 CLI 隔离模型导出的建议请求")
    scenario.add_argument("--agent-progress", type=Path, help="官方父子轮与固定进度查询的隔离样本")
    scenario.add_argument("--stock-client", action="store_true", help="用固定原版 CLI 验证公开 V2 的 Read 往返")
    scenario.add_argument("--thinking-display-contract", choices=tuple(THINKING_DISPLAY_DEFAULTS))
    scenario.add_argument("--history-png", action="store_true")
    scenario.add_argument("--history-images", action="store_true")
    scenario.add_argument("--history-tool-blocks", action="store_true")
    scenario.add_argument("--split-history-tools", action="store_true")
    scenario.add_argument("--parallel-new-tools", action="store_true")
    scenario.add_argument("--reconnect-tool-stream", action="store_true")
    scenario.add_argument("--mixed-release", nargs=3, type=Path,
                          metavar=("OLD_SOURCE", "OLD_GATEWAY", "OLD_SENDER"))
    scenario.add_argument("--mixed-image-peers", nargs=2, type=Path, help=argparse.SUPPRESS)
    scenario.add_argument("--failure-boundaries", action="store_true")
    scenario.add_argument("--v1-runtime", type=Path)
    args = parser.parse_args()
    if args.current_image_ending == "image" and not args.current_images:
        parser.error("--current-image-ending 需要同用 --current-images")
    if args.stock_client and args.v1_runtime:
        parser.error("--stock-client 使用 V2 账号")
    if bool(args.interleaved_title) != bool(args.title_request):
        parser.error("--interleaved-title 与 --title-request 需要一起使用")
    if bool(args.interleaved_suggestion) != bool(args.suggestion_request):
        parser.error("--interleaved-suggestion 与 --suggestion-request 需要一起使用")
    auxiliary_mode = args.interleaved_title or args.interleaved_suggestion
    auxiliary_path = args.title_request or args.suggestion_request
    if args.adaptive_thinking_display != "updates" and args.adaptive_thinking_model is None:
        parser.error("--adaptive-thinking-display 需要同用 --adaptive-thinking-model")
    if args.signed_tool_response and not args.signed_tool_history:
        parser.error("--signed-tool-response 需要同用 --signed-tool-history")
    if args.thinking_cli_summaries is not None and not args.thinking_display_contract:
        parser.error("--thinking-cli-summaries 需要同用 --thinking-display-contract")
    thinking_cli_summaries = {"on": True, "off": False}.get(args.thinking_cli_summaries)
    if args.history_cache_ttl and not args.history_cache_markers:
        parser.error("--history-cache-ttl 需要同用 --history-cache-markers")
    if args.history_cache_scope and not args.history_cache_ttl:
        parser.error("--history-cache-scope 需要同用 --history-cache-ttl")
    if (args.recovery_ledger_contention or args.recovery_ledger_deadline or args.recovery_workspace_rejection
        or args.recovery_slow_model) and (
        not args.recover_pending_tool or args.signed_tool_history
    ):
        parser.error("恢复故障注入需要可提交的 --recover-pending-tool 原回执")
    if (not Path("/.dockerenv").exists() or {name for _, name in if_nameindex()} != {"lo"}
            or Path("/run/v3/sender.json").exists() or any(Path("/native").glob("*"))):
        raise RuntimeError("请在空白的 docker --network none 账号容器中运行")
    previous = args.mixed_release
    cache_markers = args.cache_markers or args.cache_marker_capabilities is not None
    trace_startup = (args.initial_idle_model_connection or args.trace_initial_startup or cache_markers
                     or args.structured_output_contract or bool(args.forced_tool_choice_contract) or args.no_tool_choice_contract
                     or bool(auxiliary_mode or args.agent_progress)
                     or bool(args.thinking_display_contract)
                     or (bool(args.message_system_roles) and args.v1_runtime is None))
    if trace_startup and (previous or args.mixed_image_peers or args.v1_runtime):
        parser.error("启动观测需要当前 V2 源码夹具")
    if args.mixed_image_peers:
        if args.shared_state is None:
            parser.error("镜像混跑须使用私有共享夹具目录")
        previous = (None, *args.mixed_image_peers)
    elif args.v1_runtime is None:
        install_source(previous[0] if previous else ROOT, trace_startup=trace_startup,
                       cache_capability=args.cache_marker_capabilities, thinking_cli_summaries=thinking_cli_summaries)
    elif sha256(args.v1_runtime.read_bytes()).hexdigest() != V1_RUNTIME_SHA256:
        parser.error("V1 启动器摘要与固定版不符")
    with TemporaryDirectory(prefix="cold-history-", dir=args.shared_state) as directory:
        proof = verify(args.gateway, args.sender, Path(directory),
                       restart_history=args.restart_history, text_input=args.text_input,
                       system_policy=args.system_policy, toggle_pending_policy=args.toggle_pending_policy,
                       stock_client=args.stock_client,
                       tool_policy=args.tool_policy, recover_pending=args.recover_pending_tool,
                       output_effort=args.output_effort, history_png=args.history_png,
                       history_images=args.history_images, history_tool_blocks=args.history_tool_blocks,
                       previous=previous,
                       failure_boundaries=args.failure_boundaries, current_text_blocks=args.current_text_blocks,
                       signed_tool_history=args.signed_tool_history, signed_tool_response=args.signed_tool_response,
                       split_history_tools=args.split_history_tools,
                       v1_runtime=args.v1_runtime, parallel_tools=args.parallel_new_tools,
                       reconnect_tool_stream=args.reconnect_tool_stream, current_images=args.current_images,
                       current_image_ending=args.current_image_ending,
                       auto_tool_choice=args.auto_tool_choice,
                       adaptive_thinking_model=args.adaptive_thinking_model,
                       adaptive_thinking_display=args.adaptive_thinking_display,
                       thinking_display_model=args.thinking_display_contract,
                       thinking_cli_summaries=thinking_cli_summaries,
                       recovery_ledger_contention=args.recovery_ledger_contention,
                       recovery_ledger_deadline=args.recovery_ledger_deadline,
                       recovery_workspace_rejection=args.recovery_workspace_rejection,
                       recovery_slow_model=args.recovery_slow_model,
                       initial_idle_model_connection=args.initial_idle_model_connection, trace_startup=trace_startup,
                       cache_markers=cache_markers, history_cache_markers=args.history_cache_markers,
                       history_cache_ttl=args.history_cache_ttl, history_cache_scope=args.history_cache_scope,
                       cache_capability=args.cache_marker_capabilities,
                       message_system_roles=args.message_system_roles, structured_output=args.structured_output_contract,
                       forced_tool_choice=args.forced_tool_choice_contract, no_tool_choice=args.no_tool_choice_contract,
                       auxiliary_mode=auxiliary_mode,
                       auxiliary_kind="suggestion" if args.interleaved_suggestion else "title",
                       auxiliary_sample=json.loads(auxiliary_path.read_bytes()) if auxiliary_path else None,
                       agent_progress=json.loads(args.agent_progress.read_bytes()) if args.agent_progress else None)
        print(json.dumps(proof, ensure_ascii=False))


if __name__ == "__main__":
    main()
