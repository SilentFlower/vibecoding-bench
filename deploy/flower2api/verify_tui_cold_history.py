"""用真实网关、账号事件源与 2.1.293 CLI 验收公开 Messages 冷导入。"""

import argparse
from base64 import b64decode, b64encode
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack, closing, suppress
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from faulthandler import dump_traceback
from fcntl import LOCK_EX, flock
from hashlib import sha256
from http.client import HTTPConnection, HTTPException, IncompleteRead
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from itertools import groupby
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
from zlib import compress, crc32, decompress

from fixtures.native_model_send.agent_progress import model_reply as agent_progress_model_reply, verify_agent_progress
from fixtures.native_model_send.direct_egress_identity import model_body_identity
from fixtures.native_model_send.fixture_tunnel import _relay
from fixtures.native_model_send.stock_messages import (
    POLICIES as STOCK_POLICIES,
    model_reply as stock_model_reply,
    observe_stock_delivery,
    verify_stock_client,
)
from fixtures.native_model_send.tui_startup_trace import (
    CANCEL_LAUNCH_PROBE, MODEL_BODY_TRACE, THINKING_SUMMARIES_SETTING, startup_event,
)
from verify_tui_concurrency import frame
from verify_tui_final_tls import call, encoded, serve, stop, wait_for
from verify_tui_http_handoff import MODEL, message_sse, message_sse_frames
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
SIGNED_ARCHIVE_QUESTION = "另查一条便签，保留已确认的签名工具历史。"
SIGNED_FORK_QUESTION = "从已经完成的签名分叉继续查询。"
SIGNED_FORK_PROJECT = "<environment_context>\n<cwd>/synthetic/shared-notes</cwd>\n</environment_context>"
CANCELLED_QUESTION = "CANCEL：暂停这道尚未完成的问题。"
CHANGED_QUESTION = "CHANGE：改问已确认的旧订单号。"
CHANGED_REPLY = "新问题的答案只来自已确认历史。"
AFTER_RESTART = "RESTART：从已确认的旧问答开启另一轮。"
DROP_REPLY = "FAILURE：模型收到正文后关闭响应连接。"
REJECT_MODEL_REQUEST = "FAILURE：模型收到正文后返回合成拒绝。"
QUOTA_QUESTIONS = {"allowed": "合成用量允许对照。", "rejected": "合成模型限流对照。"}
QUOTA_RETRY_SECONDS = 29
QUOTA_REJECTION = {"type": "error", "error": {"type": "rate_limit_error", "message": "隔离模型的合成限流"}}
SYSTEM = ["RULE1：你是便签助手。", "RULE2：请只使用已声明的工具。"]
PAST_ID = "toolu_past_fixture"
PAST_SECOND_ID = "toolu_past_second_fixture"
NEW_ID = "toolu_cold_fixture"
SECOND_ID = "toolu_second_cold_fixture"
SIGNED_FORK_TOOL_ID = "toolu_signed_fork_fixture"
RECONNECT_ID = "toolu_reconnect_cold_fixture"
RECONNECT_MESSAGE_ID = "msg_cold_reconnect"
INTERRUPTED_PREFIX = "第一条续轮已交付、随后中断的合成文本。"
INTERRUPTED_USAGE = (17, 2)
REGENERATED_USAGE = (19, 11)
SLOW_READER_USAGE = (17, 11)
SLOW_READER_PAUSE_SECONDS = 11
SIGNED_THINKING = {"type": "thinking", "thinking": "隔离模型的合成思考段。", "signature": "c2lnbmF0dXJlLWZpeHR1cmU="}
REDACTED_TOOL_THINKING = {"type": "redacted_thinking", "data": "c3ludGhldGljLXJlZGFjdGVkLWJsb2Nr"}
EXTERNAL_REDACTED_THINKING = {"type": "redacted_thinking", "data": "c3ludGhldGlj"}
SIGNED_FORK_THINKING = {"type": "thinking", "thinking": "隔离模型在分叉产生的合成思考段。",
                        "signature": "c2lnbmF0dXJlLWZvcms="}
ADAPTIVE_THINKING = {"type": "adaptive", "display": "updates"}
THINKING_UPDATES_BETA = "thinking-display-updates-2026-08-18"
THINKING_DISPLAY_DEFAULTS = {MODEL: "summarized", "claude-opus-5-5": "omitted"}
CONTEXT_MANAGEMENT_BETA = "context-management-2025-06-27"
SYSTEM_CLEAR_AT_BETA = "mid-conversation-system-clear-at-2026-08-21"
SYSTEM_EFFORT_BETA = "mid-conversation-output-config-2026-07-01"
SYSTEM_CONTROL_CONTRACTS = ("turn-scoped-contract", "message-effort-contract")
KEEP_ALL_THINKING = {"edits": [{"type": "clear_thinking_20251015", "keep": "all"}]}
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
AUTO_TEXT_REPLY = "模型直接回答合成问题。"
SERIAL_AUTO = {"type": "auto", "disable_parallel_tool_use": True}
SERIAL_TOOL_QUESTION = "请调用一次合成便签工具后再回答。"
TITLE_TEXT = "隔离标题用量对照"
TITLE_REPLY = json.dumps({"title": TITLE_TEXT}, ensure_ascii=False, separators=(",", ":"))
AUXILIARY_USAGE = (31, 7)
SUGGESTION_REPLY = "summarize the synthetic note next"
FORCED_CHOICES = {"any": {"type": "any"}, "named": {"type": "tool", "name": SECOND_TOOL["name"]}}


def response_json(handler, payload, *, status=200, headers=None):
    """写入合成 JSON 响应。@param handler 当前连接。@param payload 响应对象。
    @param status 该隔离服务的实际状态。@param headers 可选的原模型响应头。@return 无。
    """
    raw = json.dumps(payload).encode()
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Content-Length", str(len(raw)))
    for name, value in (headers or {}).items():
        handler.send_header(name, value)
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


def pending_mixed_tool_scope(database, session_id):
    """读出旧轮仍在等待的实际归属。@param database 隔离网关数据库。@param session_id 公开会话。
    @return 原轮 ID、账号、主体、会话和绑定摘要。
    """
    with closing(connect(database)) as connection:
        (row,) = connection.execute(
            "SELECT id,account_id,principal_id,session_id,binding FROM tui_native_turns WHERE session_id=? AND tools=?",
            (session_id, json.dumps([NEW_ID])),
        ).fetchall()
    turn, account, principal, session, binding = row
    _, environment, generation, _ = binding.split(":", 3)
    return {"turn_id": turn, "account_id": account, "principal_id": principal, "session_id": session,
            "environment_id": environment, "generation": int(generation),
            "binding_sha256": sha256(binding.encode()).hexdigest()}


def fixture_tool_sse(tool, *, with_signature, second=None, model=MODEL, thinking_text=SIGNED_THINKING["thinking"],
                     signature=SIGNED_THINKING["signature"], message_id="msg_cold_tool", redacted=None):
    """交付隔离模型工具流。@param tool 原生工具调用。@param with_signature 是否先交付合成签名块。
    @param second 可选的同轮第二次工具调用。@param model 模型实际回复的身份，可省略。
    @param thinking_text 合成思考摘要，可为空。@param signature 隔离签名。@param message_id 原响应 ID。
    @param redacted 可选的不透明思考块，完整内容随开始事件交付。
    @return SSE。"""
    wire = message_sse(tool, "tool_use", message_id)
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
    signed = [{"type": "content_block_start", "index": 0,
               "content_block": redacted or {"type": "thinking", "thinking": ""}}]
    if redacted is None:
        if thinking_text:
            signed.append({"type": "content_block_delta", "index": 0,
                           "delta": {"type": "thinking_delta", "thinking": thinking_text}})
        signed.append({"type": "content_block_delta", "index": 0,
                       "delta": {"type": "signature_delta", "signature": signature}})
    signed.append({"type": "content_block_stop", "index": 0})
    events[1:1] = signed
    return b"".join(map(frame, events))


def fixture_parallel_results(calls, callbacks):
    """按公开返回的调用执行两种合成工具，逆序交付结果。
    @param calls 从公开 SSE 重组的调用。@param callbacks 实际执行记录。@return 逆序的结果块。
    """
    def lookup_note(arguments):
        assert same_json_value(arguments, ARGS), arguments
        return REPLY

    def set_tag(arguments):
        assert same_json_value(arguments, PARALLEL_SECOND_ARGS), arguments
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


def fixture_reconnect_sse(name, *, usage=None):
    """构造可分阶段放行的同一模型流。
    @param name 模型收到的原生工具名。@param usage 可选，本轮独立输入及输出 token。
    @return 含半段参数的前缀、余下参数及终帧。
    """
    text = message_sse({"type": "text", "text": RECONNECT_PREFIX}, "end_turn", RECONNECT_MESSAGE_ID)
    tool = message_sse({"type": "tool_use", "id": RECONNECT_ID, "name": name, "input": SECOND_ARGS},
                       "tool_use", RECONNECT_MESSAGE_ID)
    prefix = [json.loads(line[5:]) for line in text.splitlines() if line.startswith(b"data:")][:-2]
    tail = [json.loads(line[5:]) for line in tool.splitlines() if line.startswith(b"data:")][1:]
    for event in tail:
        if "index" in event:
            event["index"] += 1
    start, delta, *terminal = tail
    if usage is not None:
        prefix[0]["message"]["usage"]["input_tokens"] = usage[0]
        terminal[-2]["usage"]["output_tokens"] = usage[1]
    partial = delta["delta"]["partial_json"]
    split_at = len(partial) // 2
    head = {**delta, "delta": {**delta["delta"], "partial_json": partial[:split_at]}}
    rest = {**delta, "delta": {**delta["delta"], "partial_json": partial[split_at:]}}
    return b"".join(map(frame, [*prefix, start, head])), frame(rest), b"".join(map(frame, terminal))


def fixture_cancelled_tool_sse(name):
    """分隔工具参数流，以公开客户端断开时的未完整输入为验收边界。
    @param name 隔离模型实收的工具名。@return 断开前可见前缀及未交付尾段。
    """
    wire = message_sse({"type": "tool_use", "id": NEW_ID, "name": name, "input": ARGS},
                       "tool_use", "msg_cancelled_question")
    events = [json.loads(line[5:]) for line in wire.splitlines() if line.startswith(b"data:")]
    partial = events[2]["delta"]["partial_json"]
    split_at = len(partial) // 2
    head = {**events[2], "delta": {**events[2]["delta"], "partial_json": partial[:split_at]}}
    tail = {**events[2], "delta": {**events[2]["delta"], "partial_json": partial[split_at:]}}
    return b"".join(map(frame, [*events[:2], head])), b"".join(map(frame, [tail, *events[3:]]))


def fixture_thinking_display_sse(body, *, message_id="msg_cold_thinking_display"):
    """按实收的思考设置与模型默认值生成合成流。
    @param body 隔离模型实收。@param message_id 合成助手消息 ID。@return SSE 字节。
    """
    model = body["model"]
    settings = body["thinking"]
    display = settings["display"] if "display" in settings else THINKING_DISPLAY_DEFAULTS[model]
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
           history_png=False, history_images=False, history_tool_blocks=False, previous=None, mixed_context_keep_all=None,
           failure_boundaries=False,
           current_text_blocks=False, signed_tool_history=False, signed_tool_response=None, split_history_tools=False,
           v1_runtime=None,
           parallel_tools=False, reconnect_tool_stream=False, interrupted_tool_stream=None,
           current_images=False, current_image_ending="text",
           auto_tool_choice=None, receipt_auto_tool_choice=None, auto_tool_direct_text=False, prior_auto_source=None,
           adaptive_thinking_model=None, adaptive_thinking_display="updates", thinking_display_model=None,
           fixed_thinking_model=None, fixed_thinking_display="updates",
           thinking_cli_summaries=None,
           recovery_ledger_contention=False, recovery_ledger_deadline=False, recovery_workspace_rejection=False,
           recovery_readiness_rejection=False,
           recovery_slow_model=False, replay_unknown_receipt=None,
           initial_idle_model_connection=False, trace_startup=False, cache_markers=False,
           trace_recovery_resend=False,
           history_cache_markers=False, history_cache_ttl=None, history_cache_scope=None,
           cache_capability=None, message_system_roles=False,
           structured_output=False, installed_runtime=False, forced_tool_choice=None, no_tool_choice=False,
           disable_parallel_tool_use=False,
           auxiliary_mode=None,
           auxiliary_kind="title", auxiliary_sample=None, agent_progress=None, stock_client=False,
           cancel_and_change_question=False, cancel_before_response_headers=None,
           oauth_rotation=False, observe_oauth_delivery=None, provider_quota=None, slow_tool_stream=False,
           model_connection_contract=None, external_signed_history=False, bound_signed_history=None, history_tool_images=None,
           tool_receipt_images=None, explicit_custom_tool_type=False, history_empty_tool_result=None,
           empty_tool_receipt=None, tool_receipt_text_blocks=None, tool_receipt_nested_cache=None,
           tool_receipt_outer_cache=None, model_stream_probe=None):
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
    @param history_empty_tool_result 已闭合空结果的缺省、空数组或空串形状。
    @param empty_tool_receipt 本轮实际回执的空结果形状及错误标志。
    @param tool_receipt_text_blocks 本轮实际回执的重复文本块、换行及错误标志。
    @param tool_receipt_nested_cache 本轮结果首个文本块的内层缓存 TTL，default 表示省略 TTL。
    @param tool_receipt_outer_cache 本轮整个工具结果的外层缓存 TTL，default 表示省略 TTL。
    @param history_tool_images 核对已闭合工具结果的图文块，可显式声明成功或省略错误标志。
    @param tool_receipt_images 核对本轮实际工具调用的图文回执及拒绝边界。
    @param explicit_custom_tool_type 是否通过显式 custom 的客户端声明进行原生工具往返。
    @param previous 可选，旧发行源码、网关、发送器三个离线制品。
    @param mixed_context_keep_all 可选，混版交接时显式保留全部思考的模型。
    @param failure_boundaries 是否分别在模型收件前后切断隔离连接。
    @param interrupted_tool_stream 截断位置，按下一工具首帧是否交付核对原回执重试。
    @param stock_client 是否通过真实外部 CLI 验证完整 V2 输入与工具回执。
    @param cancel_and_change_question 是否在首轮工具参数未完成时取消并从确认历史改问。
    @param cancel_before_response_headers 可选首轮公开格式，取消 CLI 启动中的 SSE 或 JSON 请求。
    @param oauth_rotation 是否在原轮等待工具期间通过正式管理入口轮换账号凭据。
    @param observe_oauth_delivery 可选，从模型接收端核对内置直发候选的实际连接和受管许可。
    @param provider_quota 可选的公开 SSE 或 JSON 供应商限流和被动额度对照。
    @param current_text_blocks 是否验证本轮文本块顺序及边界归属。
    @param signed_tool_history 是否核对隔离模型原工具轮的签名块。
    @param signed_tool_response 可选，模拟空思考、不透明思考或缺少助手模型的隔离响应。
    @param split_history_tools 是否将已闭合的旧工具组分为相邻消息。
    @param v1_runtime 固定 V1 制品，提供时仅验证 V1 内核的公开能力。
    @param parallel_tools 是否验证同一步多个新工具的回执。
    @param reconnect_tool_stream 是否在真实续轮流中断开再接回。
    @param slow_tool_stream 是否在原公开连接上慢读真实续轮，核对独立用量。
    @param model_connection_contract 可选，验证模型连接复用、模型端关闭或 sender 重启后的连接归属。
    @param external_signed_history 外部签名基线，或带独立模型响应及来源字段的对照。
    @param bound_signed_history 原生主档的签名来源及新工具的热续轮或重启恢复。
    @param current_images 是否用本轮原生图文替换纯文本问题。
    @param current_image_ending 本轮九块图文以文字或图片结尾。
    @param auto_tool_choice 原请求中自动选择的字段形状。
    @param receipt_auto_tool_choice 合法回执的等价字段形状。
    @param prior_auto_source 写入原工具回执摘要的旧账号事件源检出。
    @param auto_tool_direct_text 是否让模型在有工具声明时直接返回文本。
    @param adaptive_thinking_model 可选，核对显式 adaptive 的固定模型。
    @param adaptive_thinking_display 在工具首轮与续轮冻结的显式显示值。
    @param fixed_thinking_model 可选，核对固定 4.6 模型的显式思考预算。
    @param fixed_thinking_display 固定预算工具轮及回执使用的显式显示值。
    @param thinking_display_model 可选，核对普通 API 思考显示及客户端响应的固定模型。
    @param thinking_cli_summaries 可选，核对正式 CLI 摘要设置的隔离对照。
    @param recovery_ledger_contention 是否在提交原回执时短暂占用账号账本锁。
    @param recovery_ledger_deadline 是否持续持锁直至回执触发准入截止，然后重交。
    @param recovery_workspace_rejection 可选的工作区绑定故障，核对拒绝及原回执再次认领。
    @param recovery_readiness_rejection 是否在预留前触发账本就绪拒绝并复交原回执。
    @param recovery_slow_model 是否验证隔离模型收件后的公开超时和诊断归属。
    @param replay_unknown_receipt 按公开响应格式和原回复的可交付状态重交同一回执。
    @param initial_idle_model_connection 是否先占用一个未握手的模型 TCP 连接。
    @param trace_startup 是否记录隔离启动阶段。
    @param trace_recovery_resend 是否在隔离夹具中对合法恢复回执的 503 原样补发一次并分别取证。
    @param cache_markers 是否核对普通 Messages 显式缓存标记的模型实收和出站归属。
    @param history_cache_markers 是否冻结历史标记并验证工具往返。
    @param history_cache_ttl 工具往返启用的平台历史断点时长。
    @param history_cache_scope 可选，强制 TTL 下使用仅嵌套或混合断点。
    @param cache_capability 对照生产入口或 CLI 提示词和工具的缓存标记能力。
    @param message_system_roles 消息级系统角色对照或普通 API 固定回归模式。
    @param structured_output 是否核对普通 API 的结构化输出和实际发送路径。
    @param installed_runtime 结构化工具轮使用镜像内置事件源和管理诊断。
    @param model_stream_probe 可选，仅分段发送隔离模型的首轮文本响应。
    @param forced_tool_choice 核对强制工具选择及同进程或重启回执。
    @param no_tool_choice 是否核对无工具时的显式 none 和保留声明的兼容路径。
    @param disable_parallel_tool_use 是否核对禁并行的公开策略与模型实收。
    @param auxiliary_mode 可选，观察等待工具时的公开辅助轮投递或本地拦截。
    @param auxiliary_kind 标题或建议。@param auxiliary_sample 从官方 CLI 隔离运行导出的请求。
    @param agent_progress 已捕获父子轮与固定进度请求样本。
    @return 脱敏证据。
    """
    secret, admin, internal, account_token = (token_hex(32) for _ in range(4))
    refresh_token = token_hex(32)
    rotated_token, rotated_refresh = (token_hex(32), token_hex(32)) if oauth_rotation else (None, None)
    expected_token = account_token
    credential_observations, refresh_calls = [], []
    oauth_host = "platform.claude.com"
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
    if cancel_before_response_headers:
        CANCEL_LAUNCH_PROBE.mkdir(mode=0o700)
        os.chown(CANCEL_LAUNCH_PROBE, 1001, 1001)
    inspect_model_body = (stock_client or cache_markers or message_system_roles or thinking_display_model or structured_output
                          or forced_tool_choice or no_tool_choice or disable_parallel_tool_use or provider_quota
                          or external_signed_history or interrupted_tool_stream or observe_oauth_delivery is not None)
    if inspect_model_body and v1_runtime is None and not installed_runtime:
        MODEL_BODY_TRACE.touch(mode=0o600, exist_ok=False)
        os.chown(MODEL_BODY_TRACE, 1001, 1001)
    certificates(temporary, extra_dns_names=(oauth_host,) if oauth_rotation else ())
    config = Path("/run/v3/sender.json")
    copy2(temporary / "ca.der", config.with_name("verification-ca.der"))
    received, callbacks, proxy_targets = [], [], []
    model_tunnels, model_client_hellos, model_connection_posts = {}, [], []
    model_deliveries = {}
    quota_reads = []
    quota_reset = time_ns() // 1_000_000_000
    quota_windows = {"5h": quota_reset + 3600, "7d": quota_reset + 6 * 86400, "7d_oi": quota_reset + 5 * 86400}
    auxiliary_received = []
    auxiliary_provider_sessions = []
    suggestion = auxiliary_kind == "suggestion"
    auxiliary_reply = SUGGESTION_REPLY if suggestion else TITLE_REPLY
    auxiliary_text = SUGGESTION_REPLY if suggestion else TITLE_TEXT
    slow_model_arrivals = []
    slow_tool_prefix = Event()
    slow_tool_terminal = Event()
    retained_receipt = replay_unknown_receipt in ("live", "complete", "json-live", "json-complete")
    lost_receipt = recovery_slow_model or replay_unknown_receipt in ("lost-live", "lost")
    trace_receipt_timing = retained_receipt or lost_receipt
    model_reply = {}
    closed_model_tunnels = {}
    gateway_reply_trace = temporary / "receipt-gateway.log"
    model_betas = []
    summarized_thinking = (
        (adaptive_thinking_model is not None and adaptive_thinking_display == "summarized")
        or (fixed_thinking_model is not None and fixed_thinking_display == "summarized")
    )
    signed_thinking_text = "" if signed_tool_response == "signature-only" else SIGNED_THINKING["thinking"]
    redacted_thinking = REDACTED_TOOL_THINKING if signed_tool_response == "redacted" else None
    lookups = []
    deny_proxy = False
    denied_tunnels = []
    continue_tool_stream = Event()
    finish_stream = Event()
    slow_stream_finished = Event()
    stock_homes = tuple(temporary / f"stock-{policy}" for policy in STOCK_POLICIES) if stock_client else ()

    class Receiver(QuietHandler):
        """以生产主机名的临时证书接收原生请求，返回固定工具或文本。"""

        protocol_version = "HTTP/1.1"

        def do_GET(self):
            """记录隔离模型上意外的主动额度查询。@return 无。"""
            if provider_quota:
                quota_reads.append(self.path)
            self.send_error(501)

        def do_POST(self):
            """验证合成凭据并返回同一轮 SSE。@return 无。"""
            if oauth_rotation and self.path == "/v1/oauth/token":
                payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                accepted = (self.headers.get("Host") == oauth_host and payload.get("grant_type") == "refresh_token"
                            and payload.get("refresh_token") == refresh_token and not refresh_calls)
                refresh_calls.append(accepted)
                startup_event("isolated_oauth_refresh", accepted=accepted, refresh_count=len(refresh_calls))
                if accepted:
                    response_json(self, {"access_token": rotated_token, "refresh_token": rotated_refresh,
                                         "expires_in": 3600})
                else:
                    response_json(self, {"error": "invalid_grant"}, status=400)
                return
            accepted_path = (self.path == "/v1/messages"
                             or (v1_runtime is not None and self.path == "/v1/messages?beta=true"))
            bearer = self.headers.get("Authorization")
            if not accepted_path or bearer != "Bearer " + expected_token:
                if oauth_rotation:
                    credential_observations.append({"credential": "rejected"})
                    startup_event("isolated_model_credential_rejected", model_posts=len(received),
                                  previous_credential=bearer == "Bearer " + account_token)
                self.send_error(403)
                return
            if trace_startup:
                startup_event("model_http_headers", peer_port=self.client_address[1])
            raw = self.rfile.read(int(self.headers["Content-Length"]))
            received_ns = monotonic_ns() if trace_receipt_timing else None
            body = json.loads(raw)
            model_digest = sha256(raw).hexdigest()
            if model_connection_contract:
                model_connection_posts.append((self.client_address[1], model_digest))
            if stock_client or observe_oauth_delivery is not None:
                peer = self.client_address[1]
                assert model_digest not in model_deliveries
                inspect_delivery = observe_oauth_delivery or observe_stock_delivery
                model_deliveries[model_digest] = inspect_delivery(
                    model_digest, peer, model_tunnels[peer], proxy.server_port, source.pid,
                )
            is_auxiliary = False
            if auxiliary_sample is not None:
                sample = auxiliary_sample["body"]
                if suggestion:
                    is_auxiliary = body["messages"][-1]["content"] == sample["messages"][-1]["content"]
                else:
                    is_auxiliary = body.get("output_config", {}).get("format") == sample["output_config"]["format"]
            (auxiliary_received if is_auxiliary else received).append((model_digest, body, self.connection.version()))
            if received_ns is not None and not is_auxiliary:
                slow_model_arrivals.append({"monotonic_ns": received_ns, "model_body_sha256": model_digest,
                                            "has_tool_receipt": bool(find_blocks(body, "tool_use_id", NEW_ID))})
            if oauth_rotation:
                generation = "initial" if bearer == "Bearer " + account_token else "rotated"
                credential_observations.append({"credential": generation, "model_body_sha256": model_digest})
            if is_auxiliary:
                auxiliary_provider_sessions.append(self.headers.get("x-claude-code-session-id"))
            if trace_startup:
                startup_event("model_received", peer_port=self.client_address[1], model_posts=len(received),
                              **{f"{auxiliary_kind}_posts": len(auxiliary_received)},
                              model_body_sha256=model_digest)
            quota = {}
            if provider_quota:
                user_text = [b.get("text") for row in body["messages"] if row["role"] == "user" for b in blocks(row)]
                rejected = QUOTA_QUESTIONS["rejected"] in user_text
                windows = {"5h": (1.0, "rejected"), "7d": (0.75, "allowed_warning")} if rejected else {
                    "5h": (0.25, "allowed"), "7d": (0.5, "allowed"), "7d_oi": (0.125, "allowed"),
                }
                for window, (utilization, state) in windows.items():
                    header_prefix = f"anthropic-ratelimit-unified-{window}-"
                    quota.update({header_prefix + "utilization": str(utilization), header_prefix + "status": state,
                                  header_prefix + "reset": str(quota_windows[window])})
                if rejected:
                    response_json(self, QUOTA_REJECTION, status=429, headers={**quota, "Retry-After": str(QUOTA_RETRY_SECONDS)})
                    return
            if (v1_runtime is not None or message_system_roles or adaptive_thinking_model or fixed_thinking_model
                    or mixed_context_keep_all):
                model_betas.append(self.headers.get("anthropic-beta", ""))
            if message_system_roles in SYSTEM_CONTROL_CONTRACTS:
                betas = {part.strip() for part in model_betas[-1].split(",")}
                missing = message_system_betas(body) - betas
                if missing:
                    response_json(self, {"type": "error", "error": {
                        "type": "invalid_request_error", "message": "隔离模型缺少消息级声明：" + ",".join(sorted(missing)),
                    }}, status=400)
                    return
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
            paused_receipt = retained_receipt and results and len(received) == 2
            withheld_headers = lost_receipt and results and len(received) == 2
            if paused_receipt or withheld_headers:
                model_reply["peer_port"] = self.client_address[1]
            restart = any(b.get("text") == AFTER_RESTART for row in body["messages"] for b in blocks(row))
            paused_question = cancel_and_change_question and any(
                b.get("text") == CANCELLED_QUESTION for row in body["messages"] for b in blocks(row)
            )
            prefix = b""
            middle = b""
            receipt_frames = None
            cut_tool_reply = interrupted_tool_stream and results and len(received) == 2
            if paused_receipt or withheld_headers:
                receipt_frames = message_sse_frames({"type": "text", "text": FINAL}, "end_turn", "msg_cold_reply")
                if paused_receipt:
                    prefix = b"".join(next(receipt_frames) for _ in range(3))
                wire = b""
            elif stock_client:
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
            elif auto_tool_direct_text:
                wire = message_sse({"type": "text", "text": AUTO_TEXT_REPLY}, "end_turn", "msg_auto_text")
            elif no_tool_choice:
                wire = message_sse({"type": "text", "text": FINAL}, "end_turn", "msg_cold_reply")
            elif disable_parallel_tool_use:
                # 只有实收协议字段要求禁并行时，才给工具往返对照发出单个合成调用。
                submittable = body.get("tool_choice") == SERIAL_AUTO and not results and any(
                    b.get("text") == SERIAL_TOOL_QUESTION for row in body["messages"] for b in blocks(row)
                )
                wire = (fixture_tool_sse({"type": "tool_use", "id": NEW_ID, "name": TOOL["name"], "input": ARGS},
                                         with_signature=False) if submittable
                        else message_sse({"type": "text", "text": FINAL}, "end_turn", "msg_cold_reply"))
            elif forced_tool_choice:
                wire = fixture_forced_tool_sse(body)
            elif paused_question:
                assert tool and tool["name"] == NATIVE_TOOL_NAME
                prefix, wire = fixture_cancelled_tool_sse(tool["name"])
            elif cancel_and_change_question:
                wire = message_sse({"type": "text", "text": CHANGED_REPLY}, "end_turn", "msg_changed_question")
            elif bound_signed_history == "fork" and any(b.get("text") == SIGNED_FORK_QUESTION
                                                         for row in body["messages"] for b in blocks(row)):
                if find_blocks(body, "tool_use_id", SIGNED_FORK_TOOL_ID):
                    wire = message_sse({"type": "text", "text": FINAL}, "end_turn", "msg_signed_fork_reply")
                else:
                    wire = fixture_tool_sse(
                        {"type": "tool_use", "id": SIGNED_FORK_TOOL_ID, "name": tool["name"], "input": ARGS},
                        with_signature=False, model=body["model"], message_id="msg_signed_fork_next_tool",
                    )
            elif bound_signed_history and any(b.get("text") == SIGNED_ARCHIVE_QUESTION
                                               for row in body["messages"] for b in blocks(row)):
                if find_blocks(body, "tool_use_id", SECOND_ID):
                    wire = message_sse({"type": "text", "text": FINAL}, "end_turn", "msg_bound_signed_reply")
                else:
                    signed = SIGNED_FORK_THINKING if bound_signed_history == "fork" else SIGNED_THINKING
                    wire = fixture_tool_sse(
                        {"type": "tool_use", "id": SECOND_ID, "name": tool["name"], "input": SECOND_ARGS},
                        with_signature=True, model=body["model"], thinking_text=signed["thinking"],
                        signature=signed["signature"],
                        message_id="msg_bound_signed_fork" if bound_signed_history == "fork" else "msg_cold_tool",
                    )
            elif not results and tool and not restart and v1_runtime is None:
                content = {"type": "tool_use", "id": NEW_ID, "name": tool["name"], "input": ARGS}
                second = None
                if parallel_tools:
                    other, = [t for t in body["tools"] if t.get("description") == PARALLEL_SECOND_TOOL["description"]]
                    second = {"type": "tool_use", "id": SECOND_ID, "name": other["name"], "input": PARALLEL_SECOND_ARGS}
                response_model = None if signed_tool_response == "missing-model" else body["model"]
                wire = fixture_tool_sse(content, with_signature=signed_tool_history, second=second,
                                        model=response_model, thinking_text=signed_thinking_text, redacted=redacted_thinking)
            elif cut_tool_reply:
                if interrupted_tool_stream == "after-tool-start":
                    prefix, remaining, terminal = fixture_reconnect_sse(tool["name"], usage=INTERRUPTED_USAGE)
                    wire = remaining + terminal
                else:
                    complete = message_sse(
                        {"type": "text", "text": INTERRUPTED_PREFIX}, "end_turn", "msg_cold_interrupted",
                    )
                    events = [json.loads(line[5:]) for line in complete.splitlines() if line.startswith(b"data:")]
                    events[0]["message"]["usage"] = dict(zip(("input_tokens", "output_tokens"), INTERRUPTED_USAGE, strict=True))
                    prefix = b"".join(map(frame, events[:3]))
                    wire = b"".join(map(frame, events[3:]))
            elif interrupted_tool_stream and results and not find_blocks(body, "tool_use_id", RECONNECT_ID):
                prefix, middle, wire = fixture_reconnect_sse(tool["name"], usage=REGENERATED_USAGE)
            elif (reconnect_tool_stream or slow_tool_stream) and results and not find_blocks(body, "tool_use_id", RECONNECT_ID):
                usage = SLOW_READER_USAGE if slow_tool_stream else None
                prefix, middle, wire = fixture_reconnect_sse(tool["name"], usage=usage)
            elif thinking_display_model:
                wire = fixture_thinking_display_sse(body)
            elif summarized_thinking:
                wire = fixture_thinking_display_sse(body, message_id="msg_cold_reply")
            else:
                text = FINAL
                if structured_output and same_json_value(body.get("output_config", {}).get("format"), STRUCTURED_FORMAT):
                    text = STRUCTURED_REPLY
                wire = message_sse({"type": "text", "text": text}, "end_turn", "msg_cold_reply")
            if model_stream_probe is not None:
                assert not prefix and not middle
                wire = model_stream_probe.prepare(wire)

            def encoded_chunk(data):
                return f"{len(data):x}\r\n".encode() + data + b"\r\n"

            def send_headers(content_length):
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                if paused_receipt:
                    self.send_header("Transfer-Encoding", "chunked")
                else:
                    self.send_header("Content-Length", str(content_length))
                if model_connection_contract == "server-close":
                    self.send_header("Connection", "close")
                for name, value in quota.items():
                    self.send_header(name, value)
                self.end_headers()

            def write_terminal(include_headers=False):
                # 终帧已生成。模型本地写出、私有交付和网关缓存由各自持有连接的一侧记录。
                terminal = b"".join(receipt_frames)
                model_reply["generated"] = {"monotonic_ns": monotonic_ns(), "sse_bytes": len(terminal)}
                startup_event("unknown_receipt_model_generated", **model_reply["generated"])
                step = "http_headers" if include_headers else "terminal_body"
                written = None
                try:
                    if include_headers:
                        send_headers(len(terminal))
                    step = "terminal_body"
                    payload = encoded_chunk(terminal) + b"0\r\n\r\n" if paused_receipt else terminal
                    written = self.wfile.write(payload)
                    step = "flush"
                    self.wfile.flush()
                    write_result = {"result": "written", "http_body_bytes_written": written}
                except OSError as error:
                    write_result = {"result": "failed", "write_stage": step, "error_type": type(error).__name__,
                                    "errno": error.errno, "http_body_bytes_written": written}
                    self.close_connection = True
                model_reply["write"] = {**write_result, "monotonic_ns": monotonic_ns()}
                startup_event("unknown_receipt_model_write", **model_reply["write"])

            if withheld_headers:
                if slow_tool_terminal.wait(30):
                    write_terminal(include_headers=True)
                else:
                    self.close_connection = True
                return
            send_headers(len(prefix) + len(middle) + len(wire))
            if paused_receipt:
                # 先交付模型 HTTP 头，账户端仍持有生成流。公开网关等待的是首个 SSE 数据帧。
                self.wfile.flush()
                startup_event("unknown_receipt_model_headers", model_body_sha256=model_digest, model_posts=len(received))
                if not slow_tool_prefix.wait(15):
                    self.close_connection = True
                    return
            if prefix:
                self.wfile.write(encoded_chunk(prefix) if paused_receipt else prefix)
                self.wfile.flush()
                if middle:
                    if not continue_tool_stream.wait(30):
                        self.close_connection = True
                        return
                    self.wfile.write(middle)
                    self.wfile.flush()
                # 公开读者须实际读到首段并在模型结束前断开。夹具结束时也会释放模型。
                terminal_gate = slow_tool_terminal if paused_receipt else finish_stream
                if not terminal_gate.wait(30) or paused_question or cut_tool_reply:
                    if cut_tool_reply and finish_stream.is_set():
                        startup_event("interrupted_upstream_response", model_body_sha256=model_digest,
                                      advertised_bytes=len(prefix) + len(wire), written_bytes=len(prefix))
                    self.close_connection = True
                    return
            if paused_receipt:
                write_terminal()
            elif model_stream_probe is not None:
                model_stream_probe.write(self, wire)
            else:
                self.wfile.write(wire)
            if slow_tool_stream and middle:
                self.wfile.flush()
                startup_event("slow_reader_model_finished", model_posts=len(received))
                slow_stream_finished.set()

    class Proxy(QuietHandler):
        """只把账号认可的固定供应商目标接进当前合成模型。"""

        def do_CONNECT(self):
            """保持代理与模型的 TLS 边界。@return 无。"""
            if self.path != "api.anthropic.com:443" and not (oauth_rotation and self.path == oauth_host + ":443"):
                self.send_error(403)
                return
            if deny_proxy:
                denied_tunnels.append(self.path)
                self.send_error(502)
                return
            if trace_startup:
                startup_event("proxy_connect_accepted", peer_port=self.client_address[1])
            with create_connection(("127.0.0.1", receiver.server_port), timeout=10) as target:
                peer_port = target.getsockname()[1]
                if model_connection_contract or stock_client or observe_oauth_delivery is not None:
                    model_tunnels[peer_port] = self.client_address[1]
                if trace_startup:
                    startup_event("proxy_model_tcp_connected", peer_port=peer_port)
                try:
                    _relay(self, target, proxy_targets.append)
                finally:
                    if lost_receipt:
                        target.close()
                        closed_model_tunnels[peer_port] = monotonic_ns()
                        startup_event("unknown_receipt_proxy_closed", peer_port=peer_port,
                                      monotonic_ns=closed_model_tunnels[peer_port])

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
        if retained_receipt or lost_receipt:
            # 保存网关自身的私有 HTTP 完结和缓存事件，失败时也将原日志交验。
            stack.callback(lambda: stderr.write(gateway_reply_trace.read_text(errors="replace"))
                           if gateway_reply_trace.exists() else None)
        receiver = (TracedServer(Receiver, "model_tcp_accepted") if trace_startup
                    else ThreadingHTTPServer(("127.0.0.1", 0), Receiver))
        tls = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        tls.load_cert_chain(temporary / "leaf.pem", temporary / "leaf.key")
        if model_connection_contract:
            def record_client_hello(connection, server_name, _):
                # 由接收端记录握手和 SNI，后续实收与同一 TCP 对端关联。
                peer_port = connection.getpeername()[1]
                model_client_hellos.append((peer_port, server_name))
                startup_event("model_client_hello", peer_port=peer_port, server_name=server_name)

            tls.sni_callback = record_client_hello
        # 握手由已接收连接的工作线程完成，空闲 TCP 不会占住监听线程。
        receiver.socket = tls.wrap_socket(receiver.socket, server_side=True, do_handshake_on_connect=False)
        serve(stack, receiver)
        stack.callback(finish_stream.set)
        stack.callback(slow_tool_prefix.set)
        stack.callback(slow_tool_terminal.set)
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
            process = Popen([program], user=1001, group=1001, extra_groups=[], stdout=stderr if trace_startup else None, env={
                **common, **tui, "RUST_LOG": "warn", "V3_SENDER_CONFIG": str(config),
                "FLOWER_V2_STARTUP_TRACE": str(int(trace_startup)),
            })
            stack.callback(stop, process)
            return process

        def start_gateway(program, version, **gate):
            with ExitStack() as launch:
                trace_file = launch.enter_context(gateway_reply_trace.open("ab")) if retained_receipt or lost_receipt else None
                process = Popen([program], cwd=temporary, stdout=trace_file or (stderr if trace_startup else None),
                                stderr=trace_file, env={
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

        def sender_status():
            return json.loads(call(8091, "GET", "/internal/status", secret)[1])

        def sender_state():
            return sender_status().get("tui_v2", {})

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

        prior_auto_checkpoint = None

        def restart(process, phase):
            nonlocal prior_auto_checkpoint
            wait_for(lambda: sender_state().get("idle"))
            if trace_startup:
                startup_event("sender_stop_requested", phase=phase, sender_pid=process.pid)
            stop(process)
            if trace_startup:
                startup_event("sender_exited", phase=phase, sender_pid=process.pid, returncode=process.returncode)
            if prior_auto_source is not None:
                # 旧源已实际认领原回执。读取其持久修订和摘要，再让新源恢复同一账号卷。
                module = Path("images/account/tui_session.py")
                prior_sha = sha256((prior_auto_source / module).read_bytes()).hexdigest()
                current_sha = sha256((ROOT / module).read_bytes()).hexdigest()
                assert prior_sha != current_sha, "旧账号事件源与待验事件源相同"
                ledger = Path("/native/tui-reconnect/receipts.db")
                with closing(connect(ledger.as_uri() + "?mode=ro", uri=True)) as database:
                    ((revision, receipt_digest, state),) = database.execute(
                        "SELECT revision, request, state FROM receipts"
                    ).fetchall()
                assert state == "open" and receipt_digest and len(receipt_digest) == 64, (revision, receipt_digest, state)
                prior_auto_checkpoint = {"revision": revision, "digest": receipt_digest, "state": state,
                                         "prior_source_sha256": prior_sha, "recovery_source_sha256": current_sha}
                install_source(ROOT, trace_startup=True)
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
        credentials = {"auth_type": "oauth", "access_token": account_token, "refresh_token": refresh_token,
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
            return verify_stock_client(manage, token, identifier, received, stock_homes, FINAL, model_deliveries)
        if agent_progress:
            return verify_agent_progress(manage, token, foreign, received, temporary / "gateway.db", agent_progress,
                                         checked_messages, wait_for)
        session_id = auxiliary_sample["headers"]["x-claude-code-session-id"] if auxiliary_sample else str(uuid4())
        headers = {"x-session-id": session_id, "User-Agent": "flower2api-cold-history-fixture/1"}
        messages = [{"role": role, "content": text} for role, text in HISTORY]
        if cancel_before_response_headers:
            return verify_cancel_before_headers(
                manage, token, headers, messages, received, sender_status, sender_state_after_failure,
                cancel_before_response_headers,
            )
        if cancel_and_change_question:
            try:
                return verify_cancelled_question(
                    manage, token, headers, messages, received, finish_stream, sender_state, trace_startup,
                )
            finally:
                # 人为暂停的隔离模型应在通用进程回收前释放等待。
                finish_stream.set()
        if thinking_display_model:
            return verify_thinking_display_contract(manage, token, identifier, received, thinking_display_model,
                                                    thinking_cli_summaries)
        if message_system_roles:
            account = manage("GET", f"accounts/{identifier}")
            if message_system_roles in SYSTEM_CONTROL_CONTRACTS:
                return verify_system_controls(manage, token, account, received, model_betas,
                                              per_message_effort=message_system_roles == "message-effort-contract")
            return verify_message_system_roles(manage, token, account, received, model_betas,
                                               fixed=message_system_roles == "ordinary-contract")
        if provider_quota:
            proof = verify_provider_quota(manage, token, identifier, received, quota_windows, sender_state_after_failure,
                                          stream=provider_quota == "sse")
            assert quota_reads == []
            return {**proof, "active_quota_queries": len(quota_reads)}
        if structured_output in ("live", "restart"):
            def restart_structured_tool(headers):
                nonlocal source
                marker = ("--name=" + headers["x-session-id"]).encode()
                (pid,) = [int(path.parent.name) for path in Path("/proc").glob("[0-9]*/cmdline")
                          if fixture_command_has(path, marker)]
                startup_event("structured_tool_cli_sigkill", session_id=headers["x-session-id"], cli_pid=pid)
                os.kill(pid, SIGKILL)
                source = restart(source, "structured_tool_receipt")
                assert not Path(f"/proc/{pid}").exists()

            return verify_structured_tool_round(
                manage, token, identifier, received, sender_state_after_failure,
                restart_structured_tool if structured_output == "restart" else None,
                source_observer=not installed_runtime,
            )
        if structured_output:
            return verify_structured_output(manage, token, identifier, received)
        if external_signed_history:
            return verify_external_signed_history(
                manage, token, identifier, received, sender_state_after_failure,
                origin_stack=stack if external_signed_history == "source" else None,
            )
        if no_tool_choice:
            return verify_no_tool_choice(manage, token, identifier, received)
        if disable_parallel_tool_use:
            return verify_disable_parallel_tool_use(manage, token, identifier, received, sender_state_after_failure)
        if forced_tool_choice:
            def bound_forced_archive():
                (binding_file,) = Path("/native/tui-workspaces").glob("*.json")
                native_id = json.loads(binding_file.read_bytes())["native_session_id"]
                projects = Path("/native/tui-sessions") / native_id / "home/.claude/projects"
                archive = wait_for(lambda: next(projects.glob("*/" + native_id + ".jsonl"), None))
                return archive, binding_file

            def retain_forced_metadata(archive, binding_file, phase, session_id):
                snapshot = b"".join(line for line in archive.read_bytes().splitlines(keepends=True)
                                    if json.loads(line)["type"] not in ("user", "assistant"))
                archive.write_bytes(snapshot)
                startup_event(phase, session_id=session_id, native_session_id=archive.stem,
                              archive_sha256=sha256(snapshot).hexdigest())
                return archive, snapshot, binding_file, binding_file.read_bytes()

            def stage_closed_archive(headers):
                # 先等待旧工具轮完整交付并释放工作区，再构造下一新轮缺主链的边界。
                wait_for(lambda: sender_state().get("idle"))
                preserved = retain_forced_metadata(*bound_forced_archive(), "forced_closed_metadata_only",
                                                   headers["x-session-id"])
                assert preserved[1], preserved[0]
                return preserved

            def restart_forced(headers):
                nonlocal source
                marker = ("--name=" + headers["x-session-id"]).encode()
                (pid,) = [int(path.parent.name) for path in Path("/proc").glob("[0-9]*/cmdline")
                          if fixture_command_has(path, marker)]
                metadata_archive = bound_forced_archive() if forced_tool_choice == "restart-metadata-only" else None
                startup_event("forced_receipt_cli_sigkill", session_id=headers["x-session-id"], cli_pid=pid)
                os.kill(pid, SIGKILL)
                source = restart(source, "forced_tool_receipt")
                assert not Path(f"/proc/{pid}").exists()
                startup_event("forced_receipt_cli_exit_observed", session_id=headers["x-session-id"], cli_pid=pid)
                if metadata_archive is not None:
                    return retain_forced_metadata(*metadata_archive, "forced_receipt_metadata_only", headers["x-session-id"])

            closed_archive = stage_closed_archive if forced_tool_choice == "restart-closed-metadata-only" else None
            return verify_forced_tool_choice(manage, token, identifier, received, sender_state_after_failure,
                                             restart_forced if forced_tool_choice != "live" else None,
                                             metadata_only=forced_tool_choice == "restart-metadata-only",
                                             stage_closed_archive=closed_archive)
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
        if history_tool_images:
            png, jpeg, gif, webp = fixture_image_blocks(all_formats=True)
            initial_result = [{"type": "text", "text": old_result}] if isinstance(old_result, str) else old_result
            old_result = [*initial_result, png, {"type": "text", "text": "保持图注和换行。\n第二行"},
                          jpeg, gif, png, webp]
        historical_result = {"type": "tool_result", "tool_use_id": PAST_ID, "content": old_result}
        if history_tool_images == "explicit-success":
            historical_result["is_error"] = False
        if history_empty_tool_result:
            shape, _, failed = history_empty_tool_result.partition("-")
            old_result = {"omitted": None, "array": [], "string": ""}[shape]
            if shape == "omitted":
                historical_result.pop("content")
            else:
                historical_result["content"] = old_result
            if failed:
                historical_result["is_error"] = True
        messages[3:3] = [
            {"role": "assistant", "content": [{"type": "tool_use", "name": "OldNote", "id": PAST_ID, "input": ARGS}]},
            {"role": "user", "content": [historical_result]},
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
        if bound_signed_history == "fork":
            messages[0]["content"] = [{"type": "text", "text": messages[0]["content"]},
                                      {"type": "text", "text": SIGNED_FORK_PROJECT}]
        # 历史中的旧工具结果和当前问题之间保留完成边界，CLI 启动后只提交当前问题。
        declared = [TOOL, PARALLEL_SECOND_TOOL] if parallel_tools or auto_tool_direct_text else [TOOL]
        if explicit_custom_tool_type:
            declared = [{**tool, "type": "custom"} for tool in declared]
        expected_ids = [NEW_ID, SECOND_ID] if parallel_tools else [NEW_ID]
        registered_tools = encoded(expected_ids).decode()
        body = {"model": MODEL, "max_tokens": 128, "stream": True, "messages": messages,
                "tools": declared, "system": [{"type": "text", "text": part} for part in SYSTEM]}
        if auto_tool_choice or auto_tool_direct_text:
            body = with_auto_tool_choice(body, auto_tool_choice or "bare")
        if adaptive_thinking_model:
            body["model"] = adaptive_thinking_model
            if adaptive_thinking_display != "default":
                body["thinking"] = {**ADAPTIVE_THINKING, "display": adaptive_thinking_display}
            if adaptive_thinking_display == "updates":
                headers["anthropic-beta"] = THINKING_UPDATES_BETA
        if fixed_thinking_model:
            body.update(model=fixed_thinking_model, max_tokens=4096,
                        thinking={"type": "enabled", "budget_tokens": 1536, "display": fixed_thinking_display})
            if fixed_thinking_display == "updates":
                headers["anthropic-beta"] = THINKING_UPDATES_BETA
        if mixed_context_keep_all:
            body.update(model=mixed_context_keep_all, max_tokens=4096, thinking=ADAPTIVE_THINKING,
                        context_management=KEEP_ALL_THINKING)
            headers["anthropic-beta"] = CONTEXT_MANAGEMENT_BETA
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
        if auto_tool_direct_text:
            ((_, model_request, _),) = received
            names = verify_automatic_model_tools(model_request, declared)
            starts = [event["content_block"]["type"] for event in events if event["type"] == "content_block_start"]
            assert starts == ["text"] and not callbacks
            text = "".join(event["delta"]["text"] for event in events
                           if event.get("delta", {}).get("type") == "text_delta")
            (stop_reason,) = [event["delta"]["stop_reason"] for event in events if event["type"] == "message_delta"]
            assert (text, stop_reason) == (AUTO_TEXT_REPLY, "end_turn"), events
            (attempt,) = verify_captures(manage, received, account_token)
            assert attempt["request_id"] == initial_request_id and attempt["diagnostic_body_source"] == "interactive_cli"
            assert attempt["ingress_body_sha256"] == sha256(encoded(body)).hexdigest()
            return {"http_status": initial_status, "input_tool_choice": body.get("tool_choice"),
                    "model_tools": names, "model_tool_choice_present": "tool_choice" in model_request,
                    "model_posts": len(received),
                    "public_content_types": starts, "stop_reason": stop_reason, "client_tool_calls": callbacks,
                    "public_text": text, "attempt": attempt}
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
        public_inputs = [block["input"] for block in offered]
        assert same_json_value(public_inputs, [ARGS, PARALLEL_SECOND_ARGS] if parallel_tools else [ARGS]), offered
        tool = offered[0]
        if parallel_tools:
            result = {"role": "user", "content": fixture_parallel_results(offered, callbacks)}
        elif interrupted_tool_stream:
            result = {"role": "user", "content": [interrupted_stream_tool_result(tool, callbacks)]}
        else:
            callbacks.append(tool["id"])
            result = {"role": "user", "content": [{"type": "tool_result", "tool_use_id": tool["id"], "content": REPLY}]}
        if empty_tool_receipt:
            shape, _, flag = empty_tool_receipt.partition("-")
            (block,) = [item for item in result["content"] if item["tool_use_id"] == NEW_ID]
            block.pop("content")
            if shape != "omitted":
                block["content"] = [] if shape == "array" else ""
            block.pop("is_error", None)
            if flag:
                block["is_error"] = flag == "error"
        if tool_receipt_text_blocks:
            (block,) = [item for item in result["content"] if item["tool_use_id"] == NEW_ID]
            block["content"] = [{"type": "text", "text": value} for value in (
                "合成工具回执：重复段。", "第二段\n保留换行。\n", "合成工具回执：重复段。",
            )]
            if tool_receipt_text_blocks != "implicit-success":
                block["is_error"] = tool_receipt_text_blocks == "error"
            if tool_receipt_nested_cache:
                marker = {"type": "ephemeral"}
                if tool_receipt_nested_cache != "default":
                    marker["ttl"] = tool_receipt_nested_cache
                block["content"][0]["cache_control"] = marker
                if parallel_tools:
                    (other,) = [item for item in result["content"] if item["tool_use_id"] == SECOND_ID]
                    other["content"] = [{"type": "text", "text": other["content"]}]
            if tool_receipt_outer_cache:
                block["cache_control"] = {"type": "ephemeral"}
                if tool_receipt_outer_cache != "default":
                    block["cache_control"]["ttl"] = tool_receipt_outer_cache
        exact_tool_receipts = bool(empty_tool_receipt or tool_receipt_text_blocks)
        if tool_receipt_images:
            png, jpeg, gif, webp = fixture_image_blocks(all_formats=True)
            for block in result["content"]:
                images = [png, jpeg, gif, png, webp]
                text = REPLY if block["tool_use_id"] == NEW_ID else "第二个工具的实际图文回执。"
                if block["tool_use_id"] != NEW_ID:
                    images.reverse()
                block["content"] = [{"type": "text", "text": text}, images[0],
                                    {"type": "text", "text": "第二段图注\n保留换行"}, *images[1:]]
                block.pop("is_error", None)
                if tool_receipt_images == "explicit-success":
                    block["is_error"] = False
        if previous:
            assert received[0][1]["tools"][0]["name"] == TOOL["name"]
            assert not sender_state().get("idle")
            old_binding = {key: binding[key] for key in ("account_id", "environment_id", "generation", "release_id", "endpoint")}
            if mixed_context_keep_all:
                (principal,) = [item["id"] for item in manage("GET", "tokens")["data"] if item["token"] == token]
                original_scope = pending_mixed_tool_scope(temporary / "gateway.db", session_id)
                assert (original_scope["account_id"], original_scope["principal_id"], original_scope["session_id"]) == (
                    identifier, principal, session_id,
                ), (original_scope, identifier, principal, session_id)
                assert original_scope["generation"] == old_binding["generation"]
                assert original_scope["environment_id"] == old_binding["environment_id"]
            gate = build_cutover_record(temporary, old_binding, deployment, next_release)
            stop(control)
            start_gateway(gateway, next_release, V3_UPDATE_GATE_DIR=str(gate), V3_ACCOUNT_RELEASE=next_release)
            fresh = {**body, "stream": False, "messages": [{"role": "user", "content": AFTER_RESTART}]}
            fresh_headers = headers if mixed_context_keep_all else {**headers, "x-session-id": str(uuid4())}
            lookup_boundary = len(lookups)
            premature, refuse, blocked_request_id = checked_messages(
                manage, token, fresh, fresh_headers, received, "mixed_before_drain", expected_status=503,
            )
            assert premature == 503 and len(received) == 1, (premature, refuse, len(received))
            assert any("tui_previous_release" not in lookup for lookup in lookups[lookup_boundary:])
        if toggle_pending_policy:
            changed = manage("PUT", f"accounts/{identifier}", {"client_system_prompt_policy": "replace"})
            assert changed["client_system_prompt_policy"] == "replace"
        if signed_tool_history:
            signed_type = "redacted_thinking" if redacted_thinking else "thinking"
            (start,) = [event["content_block"] for event in events if event["type"] == "content_block_start"
                        and event["index"] == 0 and event["content_block"]["type"] == signed_type]
            if redacted_thinking:
                first_block_events = [event["type"] for event in events if event.get("index") == 0]
                assert first_block_events == ["content_block_start", "content_block_stop"], first_block_events
                assert start == redacted_thinking, start
                signed_block = start
            else:
                deltas = [event["delta"] for event in events
                          if event["type"] == "content_block_delta" and event["index"] == 0]
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
        follow = {**body, "stream": (reconnect_tool_stream or slow_tool_stream or interrupted_tool_stream is not None
                                   or replay_unknown_receipt in ("live", "complete")),
                  "messages": [*messages, {"role": "assistant", "content": offered}, result]}
        if auto_tool_choice:
            other_auto = receipt_auto_tool_choice or ("explicit-false" if auto_tool_choice == "bare" else "bare")
            if prior_auto_source is None:
                follow = with_auto_tool_choice(follow, other_auto)
        if auxiliary_mode:
            auxiliary_proof = verify_pending_auxiliary(
                manage, token, headers, received, auxiliary_received, temporary / "gateway.db",
                auxiliary_sample, kind=auxiliary_kind, mode=auxiliary_mode, reply=auxiliary_reply,
            )
        wrong_subject, _ = call(18090, "POST", "/v1/messages", foreign, follow, headers)
        wrong_session, _ = call(18090, "POST", "/v1/messages", token, follow,
                                {**headers, "x-session-id": str(uuid4())})
        changed_arguments_body = {**follow, "messages": [*messages, {"role": "assistant", "content": [
            {**block, "input": {**ARGS, "key": "another-note"}} if block is tool else block
            for block in offered]}, result]}
        wrong_arguments, rejection = call(18090, "POST", "/v1/messages", token, changed_arguments_body, headers)
        rejected = wrong_subject, wrong_session, wrong_arguments, len(received)
        assert rejected == (400, 400, 422, 1), (rejected, rejection)
        if mixed_context_keep_all:
            assert pending_mixed_tool_scope(temporary / "gateway.db", session_id) == original_scope
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
        if oauth_rotation:
            snapshot = manage("POST", f"accounts/{identifier}/oauth-credentials/resolve", {"force_refresh": True})
            assert snapshot["account_id"] == identifier and snapshot["access_token"] == rotated_token
            assert snapshot["refresh_token"] == rotated_refresh and refresh_calls == [True]
            assert len(received) == 1
            expected_token = rotated_token
            startup_event("oauth_credential_rotated", model_posts=len(received), refresh_count=len(refresh_calls))
        if recover_pending or tool_receipt_images or exact_tool_receipts or replay_unknown_receipt:
            marker = ("--name=" + headers["x-session-id"]).encode()
            original, = [int(path.parent.name) for path in Path("/proc").glob("[0-9]*/cmdline")
                         if fixture_command_has(path, marker)]
            if recover_pending:
                os.kill(original, SIGKILL)
                source = restart(source, "recovered_receipt")
                assert not Path(f"/proc/{original}").exists()
            (binding_file,) = Path("/native/tui-workspaces").glob("*.json")
            original_binding = binding_file.read_bytes()
            original_id = json.loads(original_binding)["native_session_id"]
            projects = Path("/native/tui-sessions") / original_id / "home/.claude/projects"
            (original_file,) = projects.glob("*/" + original_id + ".jsonl")
            original_history = original_file.read_bytes()
        if recover_pending:
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
        if tool_receipt_images:
            rejected = deepcopy(follow)
            failed_result = rejected["messages"][-1]["content"][0]
            failed_result["is_error"] = True
            failed_content = failed_result["content"]
            first_image = next(block for block in failed_content if block["type"] == "image")
            error_receipts = {}
            for phase, content in (("error_tool_receipt_images", failed_content),
                                   ("error_tool_receipt_image_only", [first_image])):
                failed_result["content"] = content
                error_status, raw, error_request = checked_messages(
                    manage, token, rejected, headers, received, phase, expected_status=422,
                    trace_startup=True, sender_status=sender_state_after_failure,
                )
                assert json.loads(raw)["error"]["code"] == "unsupported_parameter" and len(received) == 1
                assert manage("GET", "request-diagnostics/" + error_request)["attempts"] == []
                error_receipts[phase] = (error_status, error_request)
            if not recover_pending:
                assert fixture_command_has(Path(f"/proc/{original}/cmdline"), marker)
                original_history = original_file.read_bytes()
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
        if history_tool_images:
            changed = deepcopy(follow)
            ((_, historical),) = find_blocks(changed, "tool_use_id", PAST_ID)
            content = historical["content"]
            first, second, *_ = [index for index, block in enumerate(content) if block["type"] == "image"]
            content[first], content[second] = content[second], content[first]
            changed_history_images, _, _ = checked_messages(
                manage, token, changed, headers, received, "changed_history_tool_images", expected_status=422,
                trace_startup=trace_startup,
            )
            assert len(received) == 1
        if history_empty_tool_result:
            changed = deepcopy(follow)
            (_, historical), = find_blocks(changed, "tool_use_id", PAST_ID)
            if "content" in historical:
                historical.pop("content")
            else:
                historical["content"] = []
            changed_empty_history, _, empty_history_request_id = checked_messages(
                manage, token, changed, headers, received, "changed_empty_tool_history", expected_status=422,
                trace_startup=trace_startup, sender_status=sender_state_after_failure,
            )
            assert len(received) == 1
            assert manage("GET", "request-diagnostics/" + empty_history_request_id)["attempts"] == []
        if auto_tool_choice:
            # 合法回执切换等价形状。实际选择、工具声明和回执内容仍随原轮核验。
            changed_choices = {}
            for label, choice in (
                ("none", {"type": "none"}),
                ("parallel_disabled", {"type": "auto", "disable_parallel_tool_use": True}),
                ("named", {"type": "tool", "name": TOOL["name"]}),
                ("any", {"type": "any"}),
            ):
                changed = {**follow, "tool_choice": choice}
                rejected, raw, rejected_id = checked_messages(
                    manage, token, changed, headers, received, "changed_tool_choice_" + label,
                    expected_status=422, trace_startup=trace_startup,
                )
                assert len(received) == 1, (label, raw, len(received))
                assert not manage("GET", "request-diagnostics/" + rejected_id)["attempts"]
                changed_choices[label] = rejected
        if explicit_custom_tool_type:
            changed_tools = deepcopy(declared)
            changed_tools[0].pop("type")
            changed_custom_type, _, changed_custom_request = checked_messages(
                manage, token, {**follow, "tools": changed_tools}, headers, received, "omitted_custom_tool_type",
                expected_status=422, trace_startup=trace_startup, sender_status=sender_state_after_failure,
            )
            assert len(received) == 1
            assert not manage("GET", "request-diagnostics/" + changed_custom_request)["attempts"]
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
        if fixed_thinking_model and not previous:
            changed_fixed_thinking = {}
            changes = {
                "thinking": {"thinking": {**body["thinking"], "budget_tokens": 1792}},
                "max_tokens": {"max_tokens": 4097},
            }
            if summarized_thinking:
                changes.update(
                    display_updates={"thinking": {**body["thinking"], "display": "updates"}},
                    display_omitted={"thinking": {**body["thinking"], "display": "omitted"}},
                    display_default={"thinking": {"type": "enabled", "budget_tokens": body["thinking"]["budget_tokens"]}},
                )
            for label, patch in changes.items():
                status, raw, changed_id = checked_messages(
                    manage, token, {**follow, **patch}, headers, received, "changed_fixed_" + label,
                    expected_status=422, trace_startup=trace_startup, sender_status=sender_state_after_failure,
                )
                assert json.loads(raw)["error"]["code"] == "unsupported_parameter" and len(received) == 1
                assert not manage("GET", "request-diagnostics/" + changed_id)["attempts"]
                changed_fixed_thinking[label] = {"status": status, "request_id": changed_id}
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
            changed_field = "data" if redacted_thinking else "signature"
            changed_signed_phase = "changed_redacted_data" if redacted_thinking else "changed_signature"
            tampered = {**signed_block, changed_field: "Y2hhbmdlZA=="}
            changed = {**follow, "messages": [*messages, {"role": "assistant", "content": [tampered, *offered[1:]]}, result]}
            changed_signature, response, changed_signature_request_id = checked_messages(
                manage, token, changed, headers, received, changed_signed_phase, expected_status=422,
                trace_startup=trace_startup, sender_status=sender_state_after_failure,
            )
            assert changed_signature == 422 and len(received) == 1, (changed_signature, response, len(received))
            changed_signature_body = response
        if interrupted_tool_stream:
            retry = with_auto_tool_choice(follow, other_auto) if prior_auto_source is not None else follow
            try:
                proof = verify_interrupted_tool_stream(
                    manage, temporary, token, headers, follow, received, callbacks,
                    finish_stream, continue_tool_stream, initial_request_id, lambda: restart(source, "interrupted_tool_retry"),
                    sender_state_after_failure, after_tool_start=interrupted_tool_stream == "after-tool-start", retry=retry,
                )
            finally:
                finish_stream.set()
            verify_model(received[:2], policy="append", old_content=old_result)
            if prior_auto_source is not None:
                assert prior_auto_checkpoint is not None
                model_tools = [verify_automatic_model_tools(native, declared) for _, native, _ in received]
                proof.update(prior_auto_checkpoint=prior_auto_checkpoint, first_receipt_tool_choice=follow.get("tool_choice"),
                             retry_tool_choice=retry.get("tool_choice"), tool_choice_rejections=changed_choices,
                             retry_receipt_body_sha256=sha256(encoded(retry)).hexdigest(), model_tools=model_tools)
            return proof
        if reconnect_tool_stream or slow_tool_stream:
            try:
                if slow_tool_stream:
                    proof = verify_connected_slow_tool_stream(
                        manage, temporary, token, account_token, headers, follow, received, callbacks,
                        continue_tool_stream, finish_stream, slow_stream_finished, initial_request_id, sender_state_after_failure,
                    )
                else:
                    replay = with_auto_tool_choice(follow, auto_tool_choice) if auto_tool_choice else follow
                    proof = verify_tool_stream_reconnect(manage, temporary, token, account_token, headers, follow,
                                                         received, continue_tool_stream, finish_stream, callbacks,
                                                         replay=replay)
                    if auto_tool_choice:
                        model_tools = [verify_automatic_model_tools(native, declared) for _, native, _ in received]
                        proof.update(input_tool_choice=body.get("tool_choice"), receipt_tool_choice=follow.get("tool_choice"),
                                     replay_tool_choice=replay.get("tool_choice"), tool_choice_rejections=changed_choices,
                                     model_tools=model_tools)
            finally:
                continue_tool_stream.set()
                finish_stream.set()
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
        if recovery_readiness_rejection:
            started_at = datetime.now(timezone.utc).isoformat(timespec="milliseconds")
            with Path("/native/tui-v2-submissions.lock").open("rb") as readiness_lock:
                # 防止先前拒绝的清理写入替换账本。就绪探测本身沿无锁读取路径。
                flock(readiness_lock, LOCK_EX)
                ledger = Path("/native/tui-v2-submissions.json")
                original_mode = ledger.stat().st_mode & 0o777
                assert original_mode == 0o600
                try:
                    ledger.chmod(0o644)
                    readiness_status, _, readiness_request = checked_messages(
                        manage, token, follow, headers, received, "recovered_receipt_readiness", expected_status=503,
                        trace_startup=trace_startup,
                    )
                finally:
                    ledger.chmod(original_mode)
            assert readiness_request and len(received) == 1
            evidence = report_request_diagnostics(
                manage, "recovered_receipt_readiness", readiness_request, headers["x-session-id"], started_at,
            )
            readiness_record, = evidence["requests"]
            assert (readiness_record["error_stage"], readiness_record["outcome"]) == (
                "tui_readiness_ledger", "local_rejected",
            ), readiness_record
            assert readiness_record["attempt_count"] == 0 and readiness_record["attempts"] == [], readiness_record
            assert "tui_reservation_id" not in readiness_record["diagnostic_context"], readiness_record
        if recovery_workspace_rejection:
            original_binding = binding_file.read_bytes()
            mismatched = {**json.loads(original_binding), "session_key": "0" * 64}
            missing_target = {"missing-directory": binding_file.parent, "missing-binding": binding_file}.get(
                recovery_workspace_rejection,
            )
            held = missing_target.with_name(missing_target.name + ".fixture-held") if missing_target else None
            if held:
                checkpoint_db = "file:/native/tui-reconnect/receipts.db?mode=ro"
                with closing(connect(checkpoint_db, uri=True)) as database:
                    (original_checkpoint,) = database.execute("SELECT actor,revision,request,state FROM receipts").fetchall()
            started_at = datetime.now(timezone.utc).isoformat(timespec="milliseconds")
            if held:
                missing_target.rename(held)
            try:
                if not held:
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
                assert record["diagnostic_context"]["tui_confirmed_model_responses"] == 0, record
                reservation = record["diagnostic_context"]["tui_reservation_id"]
                assert str(UUID(reservation)) == reservation
                with closing(connect(temporary / "gateway.db")) as database:
                    tools = database.execute("SELECT tools FROM tui_native_turns WHERE tools IN (?, ?)",
                                             (registered_tools, "!" + registered_tools)).fetchall()
                    assert tools == [(registered_tools,)], tools
                if held:
                    assert not missing_target.exists()
                    kept = held / binding_file.name if missing_target == binding_file.parent else held
                    assert kept.read_bytes() == original_binding
                    with closing(connect(checkpoint_db, uri=True)) as database:
                        assert database.execute("SELECT actor,revision,request,state FROM receipts").fetchall() == [
                            original_checkpoint,
                        ]
            finally:
                if held:
                    held.rename(missing_target)
                else:
                    binding_file.write_bytes(original_binding)
            assert binding_file.read_bytes() == original_binding
            if held:
                after_restore = []
                for caller, request_body, request_headers in (
                    (foreign, follow, headers),
                    (token, follow, {**headers, "x-session-id": str(uuid4())}),
                    (token, changed_arguments_body, headers),
                ):
                    denied, _ = call(18090, "POST", "/v1/messages", caller, request_body, request_headers)
                    after_restore.append(denied)
                assert after_restore == [400, 400, 422] and len(received) == 1, after_restore
        if recovery_slow_model or replay_unknown_receipt:
            budget_key = "v3_admission_wait_seconds"
            previous_budget = manage("GET", "settings")[budget_key]
            manage("PUT", "settings", {budget_key: "3"})
            started_at = datetime.now(timezone.utc).isoformat(timespec="milliseconds")
            phase = "recovered_receipt_slow_model" if recover_pending else "live_receipt_slow_model"
            posts_before = len(slow_model_arrivals)
            try:
                status, raw, request_id = checked_messages(
                    manage, token, follow, headers, received, phase, expected_status=502,
                    trace_startup=trace_startup, sender_status=sender_state_after_failure,
                )
                returned = monotonic_ns()
                returned_at = datetime.now(timezone.utc)
                # 在查询管理端前固定公开回包时的观测，迟到收件不能改写原时序。
                observed = [item for item in slow_model_arrivals.copy() if item["monotonic_ns"] < returned]
                tool_arrivals = [item for item in observed[posts_before:] if item["has_tool_receipt"]]
                timing = {"public_return_monotonic_ns": returned, "model_posts_before": posts_before,
                          "model_posts_at_return": len(observed), "model_arrivals": observed,
                          "tool_receipts_before_return": len(tool_arrivals)}
                startup_event("unknown_receipt_public_return", phase=phase, request_id=request_id,
                              http_status=status, **timing)
                evidence = report_request_diagnostics(
                    manage, phase, request_id, headers["x-session-id"], started_at, failed_at=returned_at,
                )
                assert request_id and posts_before == 1 and len(observed) == 2 and len(tool_arrivals) == 1, (
                    phase, request_id, status, timing,
                )
                (arrival,) = tool_arrivals
                ((role, receipt),) = find_blocks(received[-1][1], "tool_use_id", NEW_ID)
                assert role == "user" and REPLY in json.dumps(receipt, ensure_ascii=False)
                record, = evidence["requests"]
                assert (record["status_code"], record["error_stage"], record["outcome"]) == (
                    status, "tui_send_http", "transport_error",
                ), record
                reservation = record["diagnostic_context"]["tui_reservation_id"]
                assert str(UUID(reservation)) == reservation
                assert record["native_rejection"] is None, record
                if retained_receipt:
                    assert record["attempt_count"] == 0 and record["attempts"] == [], record
                    assert "tui_confirmed_model_responses" not in record["diagnostic_context"], record
                else:
                    assert len(record["attempts"]) == record["attempt_count"] <= 1, record
                    assert all(attempt["attempt_id"] == reservation for attempt in record["attempts"]), record
                assert len(received) == 2 and callbacks == [NEW_ID]
                if recover_pending:
                    assert original_file.read_bytes() == original_history
                else:
                    assert fixture_command_has(Path(f"/proc/{original}/cmdline"), marker)
                    assert original_file.read_bytes().startswith(original_history)
                verify_model(received, policy="append", old_content=old_result, current_text_blocks=current_text_blocks)
                proof = {"http_status": status, **timing,
                         "model_received_before_public_return_ms": round((returned - arrival["monotonic_ns"]) / 1e6),
                         "model_posts": len(received), "client_tool_calls": len(callbacks), "old_tool_calls": 0,
                         "public_stream": follow["stream"],
                         "request_id": request_id, "reservation_id": reservation, "outcome": record["outcome"],
                         "error_stage": record["error_stage"], "attempt_count": record["attempt_count"],
                         "confirmed_model_responses": record["diagnostic_context"].get("tui_confirmed_model_responses"),
                         "original_history_preserved": True}
                if retained_receipt:
                    assert json.loads(raw) == {
                        "type": "error", "error": {"type": "upstream_error", "message": "Upstream request failed"},
                    }, raw
                    manage("PUT", "settings", {budget_key: previous_budget})
                    proof["replay"] = verify_unknown_receipt_replay(
                        manage, temporary / "gateway.db", token, follow, headers, received, callbacks,
                        slow_tool_prefix, slow_tool_terminal, request_id, reservation,
                        replay_unknown_receipt.removeprefix("json-"),
                        gateway_reply_trace, model_reply,
                    )
                    retained_history = original_file.read_bytes()
                    assert binding_file.read_bytes() == original_binding
                    if recover_pending:
                        assert retained_history == original_history
                    else:
                        assert retained_history.startswith(original_history)
                        assert proof["replay"]["session_origin"] == "live_process", proof["replay"]
                    proof["original_cli_alive_at_502"] = not recover_pending
                    proof["original_history_bytes_equal"] = retained_history == original_history
                    proof["original_binding_preserved"] = True
                else:
                    if replay_unknown_receipt == "lost-live":
                        manage("PUT", "settings", {budget_key: previous_budget})
                        proof["replay"] = verify_lost_receipt_replay(manage, token, follow, headers, received, callbacks,
                                                                    request_id, model_reply, replay_unknown_receipt)
                    private = wait_for(lambda: read_receipt_stage(gateway_reply_trace, request_id, reservation,
                                                                  "gateway_tui_private_body"))
                    cache = wait_for(lambda: read_receipt_stage(gateway_reply_trace, request_id, reservation,
                                                                "gateway_tui_reply_cache"))
                    assert private["result"] in ("no_response", "received_error", "read_failed"), private
                    assert cache["result"] in ("no_reply", "incomplete"), cache
                    closed = wait_for(lambda: closed_model_tunnels.get(model_reply["peer_port"]))
                    slow_tool_terminal.set()
                    write = wait_for(lambda: model_reply.get("write"))
                    assert closed < model_reply["generated"]["monotonic_ns"] <= write["monotonic_ns"]
                    proof["completion"] = {"model_generated": model_reply["generated"], "model_write": write,
                                           "model_proxy_closed_ns": closed, "private_delivery": private,
                                           "gateway_cache": cache, "response_deliverable": False}
                    if replay_unknown_receipt == "lost":
                        manage("PUT", "settings", {budget_key: previous_budget})
                        proof["replay"] = verify_lost_receipt_replay(manage, token, follow, headers, received, callbacks,
                                                                    request_id, model_reply, replay_unknown_receipt)
                    if replay_unknown_receipt:
                        proof["original_terminal"] = verify_unknown_receipt_terminal(
                            manage, request_id, reservation, (None, "cancelled", "tui_send_http"),
                        )
                    assert len(received) == 2 and callbacks == [NEW_ID]
                    assert original_file.read_bytes() == original_history and binding_file.read_bytes() == original_binding
                return proof
            finally:
                manage("PUT", "settings", {budget_key: previous_budget})
        rejected_signed_recovery = signed_tool_history and recover_pending and signed_tool_response == "missing-model"
        status, raw, continuation_request_id = checked_messages(
            manage, token, follow, headers, received, "recovered_receipt" if recover_pending else "receipt",
            expected_status=422 if rejected_signed_recovery else 200, trace_startup=trace_startup,
            sender_status=sender_state_after_failure, trace_recovery_resend=trace_recovery_resend,
        )
        if signed_tool_history:
            # 在原样回执收到响应后读回诊断，避免为预期中的篡改拒绝增加一次等待。
            signature_rejection = signed_receipt_rejection(
                manage, changed_signed_phase, changed_signature_request_id, headers["x-session-id"],
                changed_signature, changed_signature_body,
            )
        if rejected_signed_recovery:
            # 缺少已记录的助手模型时在准备阶段拒绝恢复，保留原签名和归属。
            assert status == 422 and len(received) == 1, (status, raw, len(received))
            assert json.loads(raw)["error"]["code"] == "unsupported_parameter", raw
            receipt_rejection = signed_receipt_rejection(
                manage, "recovered_receipt", continuation_request_id, headers["x-session-id"], status, raw,
            )
            assert original_file.read_bytes() == original_history
            (first_attempt,) = verify_captures(manage, received, account_token)
            proof = {"cold_recovery_status": status, "changed_signature_status": changed_signature,
                     "changed_signature_rejection": signature_rejection, "receipt_rejection": receipt_rejection,
                     "receipt_request_id": continuation_request_id, "receipt_attempts": receipt_rejection["attempt_count"],
                     "recorded_signed_tool_models": signed_tool_models,
                     "model_posts": len(received), "original_history_preserved": True, "attempt": first_attempt}
            if adaptive_thinking_model:
                assert received[0][1]["thinking"] == body.get("thinking", ADAPTIVE_THINKING)
                proof.update(thinking=received[0][1]["thinking"], changed_thinking_status=changed_thinking)
            return proof
        final = json.loads(raw)
        if summarized_thinking:
            verify_client_thinking_reply(raw, False, body["model"], SIGNED_THINKING["thinking"])
        else:
            assert final["content"] == [{"type": "text", "text": FINAL}]
        duplicate_body = with_auto_tool_choice(follow, auto_tool_choice) if auto_tool_choice else follow
        duplicate, _ = call(18090, "POST", "/v1/messages", token, duplicate_body, headers)
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
            if mixed_context_keep_all:
                idle_status, _, idle_request_id = checked_messages(
                    manage, token, fresh, fresh_headers, received, "mixed_before_new_binding", expected_status=503,
                )
                assert idle_status == 503 and len(received) == 2
            stop(source)
            if previous[0] is not None:
                install_source()
            binding.update(generation=2, release_id=next_release)
            write_sender_config()
            binding["tui_predecessors"] = [old_binding]
            start_sender()
            wait_for(lambda: sender_state().get("ready") and sender_state().get("idle"))
            next_headers = fresh_headers if mixed_context_keep_all else {**headers, "x-session-id": str(uuid4())}
            status, raw, new_request_id = checked_messages(manage, token, fresh, next_headers, received, "mixed_new_round")
            assert status == 200 and len(received) == 3, (status, raw, len(received))
            if summarized_thinking:
                verify_client_thinking_reply(raw, False, body["model"], SIGNED_THINKING["thinking"])
            else:
                assert json.loads(raw)["content"] == [{"type": "text", "text": FINAL}]
            native = received[-1][1]
            assert any("You are Claude Code" in block["text"] for block in native["system"])
            assert any(tool["name"] == NATIVE_TOOL_NAME for tool in native["tools"])
            assert sum(block.get("text") == AFTER_RESTART for row in native["messages"] for block in blocks(row)) == 1
            assert not find_blocks(native, "tool_use_id", NEW_ID)
            (new_attempt,) = verify_captures(manage, received[-1:], account_token)
            assert new_attempt["ingress_body_sha256"] == sha256(encoded(fresh)).hexdigest()
            assert new_attempt["cli_and_https_body_sha256"] != new_attempt["ingress_body_sha256"]
            proof = {"old_release": release, "next_release": next_release, "new_before_drain": premature,
                    "wrong_subject": wrong_subject, "wrong_session": wrong_session,
                    "changed_arguments": wrong_arguments, "duplicate": duplicate,
                    "old_release_tool_callbacks": 1, "historical_tool_callbacks": 0,
                    "old_model_posts": 2, "new_model_posts": 1,
                    "new_attempt": new_attempt}
            if fixed_thinking_model:
                assert all(native["thinking"] == body["thinking"] and native["max_tokens"] == body["max_tokens"]
                           for _, native, _ in received)
                old_attempts = []
                for request_id in (initial_request_id, continuation_request_id):
                    (attempt,) = manage("GET", "request-diagnostics/" + request_id)["attempts"]
                    assert attempt["context"]["tui_body_source"] == "account_sender"
                    old_attempts.append({"request_id": request_id, "attempt_id": attempt["attempt_id"]})
                assert new_attempt["diagnostic_body_source"] == "interactive_cli"
                proof["fixed_thinking"] = {"thinking": body["thinking"], "max_tokens": body["max_tokens"],
                                           "old_attempts": old_attempts}
            if mixed_context_keep_all:
                assert all(model["context_management"] == KEEP_ALL_THINKING and model["thinking"] == ADAPTIVE_THINKING
                           and model["model"] == mixed_context_keep_all for _, model, _ in received)
                assert len(model_betas) == 3 and all(
                    CONTEXT_MANAGEMENT_BETA in {part.strip() for part in beta.split(",")} for beta in model_betas
                ), model_betas
                ((role, old_call),) = find_blocks(received[1][1], "id", NEW_ID)
                assert role == "assistant" and old_call == tool and old_receipt == result["content"][0]
                attempts = []
                for index, (request_id, expected_source) in enumerate((
                    (initial_request_id, "account_sender"), (continuation_request_id, "account_sender"),
                    (new_request_id, "interactive_cli"),
                )):
                    detail = manage("GET", "request-diagnostics/" + request_id)
                    request = detail["request"]
                    (attempt,) = detail["attempts"]
                    reservation = request["context"]["tui_reservation_id"]
                    assert request["original_session_id"] == session_id
                    assert request["account_id"] == attempt["account_id"] == identifier
                    assert request["context"]["tui_confirmed_model_responses"] == 1
                    assert attempt["request_id"] == request_id and attempt["attempt_id"] == reservation
                    assert attempt["context"]["tui_body_source"] == expected_source, attempt
                    attempts.append({
                        "request_id": request_id, "reservation_id": reservation, "body_source": expected_source,
                        "model_body_sha256": received[index][0],
                        "session_origin": attempt["context"]["tui_session_origin"],
                    })
                assert len({attempt["reservation_id"] for attempt in attempts}) == 3
                assert attempts[1]["session_origin"] == "live_process"
                assert new_attempt["request_id"] == new_request_id
                for request_id in (blocked_request_id, idle_request_id):
                    detail = manage("GET", "request-diagnostics/" + request_id)
                    assert detail["request"]["status_code"] == 503 and detail["attempts"] == [], detail
                proof["mixed_context_keep_all"] = {
                    "model": mixed_context_keep_all, "thinking": ADAPTIVE_THINKING,
                    "context_management": KEEP_ALL_THINKING, "model_betas": model_betas,
                    "original_scope": original_scope, "new_generation": binding["generation"],
                    "tool_use_id": tool["id"], "attempts": attempts,
                    "blocked_before_drain": {"request_id": blocked_request_id, "model_posts": 0},
                    "blocked_before_new_binding": {"request_id": idle_request_id, "http_status": idle_status, "model_posts": 0},
                    "same_fresh_body_sha256": sha256(encoded(fresh)).hexdigest(),
                }
            return proof
        expected_receipts = result["content"] if exact_tool_receipts else ()
        if tool_receipt_outer_cache and history_cache_ttl:
            # 平台 TTL 冻结在工具根轮。出站外层断点应用该值，原客户端回执和内层断点照原样。
            expected_receipts = [{**item, "cache_control": {"type": "ephemeral", "ttl": history_cache_ttl}}
                                 if "cache_control" in item else item for item in expected_receipts]
        verify_model(received, policy=tool_policy or "append", old_content=old_result, current_text_blocks=current_text_blocks,
                     exact_receipts=expected_receipts, max_tokens=body["max_tokens"])
        if observe_oauth_delivery is not None:
            assert refresh_calls == [True] and callbacks == [NEW_ID]
            assert final["stop_reason"] == "end_turn" and final["content"] == [{"type": "text", "text": FINAL}]
            attempts = _verify_direct_oauth_attempts(
                manage, identifier, (initial_request_id, continuation_request_id), received,
                credential_observations, model_deliveries, recover_pending=recover_pending,
            )
            report = {
                "model_posts": len(received), "client_tool_calls": callbacks, "refresh_calls": len(refresh_calls),
                "foreign_receipt_status": wrong_subject, "wrong_session_status": wrong_session,
                "changed_tool_arguments_status": wrong_arguments, "duplicate_receipt_status": duplicate,
                "attempts": attempts, "wire_final": "unavailable",
            }
            if recover_pending:
                assert binding_file.read_bytes() == original_binding and original_file.read_bytes() == original_history
                report.update(original_history_preserved=True, original_binding_preserved=True)
            assert all(secret not in json.dumps(report) for secret in (account_token, refresh_token, rotated_token, rotated_refresh))
            return report
        if bound_signed_history:
            def restart_bound_sender():
                nonlocal source
                source = restart(source, "bound_signed_receipt")

            return verify_bound_signed_history(
                manage, token, foreign, headers, follow, final, received, callbacks, account_token,
                initial_request_id, continuation_request_id, bound_signed_history,
                restart_bound_sender, sender_state_after_failure,
            )
        captures = verify_captures(manage, received, account_token, additional_secrets=(
            (refresh_token, rotated_token, rotated_refresh) if oauth_rotation else ()
        ))
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
        proof = {"model_posts": len(received), "client_tool_calls": callbacks,
                 "current_question_count": 1, "old_question_roles": [role for role, _ in HISTORY],
                 "foreign_receipt_status": wrong_subject, "wrong_session_status": wrong_session,
                 "changed_tool_arguments_status": wrong_arguments,
                 "duplicate_receipt_status": duplicate, "tls_versions": [tls for _, _, tls in received],
                 "proxy_connections": len(proxy_targets), "attempts": captures}
        if history_tool_images:
            assert all(attempt["diagnostic_body_source"] == "interactive_cli" for attempt in captures), captures
            observed_results = []
            for _, model, _ in received:
                (role, observed), = find_blocks(model, "tool_use_id", PAST_ID)
                assert role == "user" and same_json_value(observed, historical_result), (role, observed)
                observed_results.append(observed)
            observed = observed_results[0]
            proof["history_tool_images"] = {"tool_use_id": observed["tool_use_id"],
                                            "is_error": observed.get("is_error"),
                                            "formats": [block["source"]["media_type"] for block in observed["content"]
                                                        if block["type"] == "image"],
                                            "content_sha256": sha256(encoded(observed["content"])).hexdigest(),
                                            "changed_order_http": changed_history_images}
        elif not (tool_receipt_images or history_empty_tool_result or exact_tool_receipts):
            proof["old_tool_calls"] = 0
        if history_empty_tool_result:
            observed = [find_blocks(model, "tool_use_id", PAST_ID) for _, model, _ in received]
            assert observed == [[("user", historical_result)]] * 2, observed
            assert all(attempt["diagnostic_body_source"] == "interactive_cli" for attempt in captures)
            proof["history_empty_tool_result"] = {"input_shape": history_empty_tool_result,
                                                  "observed_results": observed,
                                                  "changed_shape_http": changed_empty_history,
                                                  "changed_shape_request_id": empty_history_request_id}
        if tool_receipt_images or exact_tool_receipts:
            assert final["stop_reason"] == "end_turn"
            assert binding_file.read_bytes() == original_binding, binding_file
            history_after_receipt = original_file.read_bytes()
            assert history_after_receipt.startswith(original_history), (len(original_history), len(history_after_receipt))
            appended = [json.loads(line) for line in history_after_receipt[len(original_history):].splitlines()]
            assert all(block not in result["content"] for row in appended if row["type"] == "user"
                       for block in blocks(row["message"]))
            assert not Path(f"/proc/{original}").exists()
            assert [attempt["diagnostic_session_origin"] for attempt in captures] == ["external_import", "disk_resume"]
            assert all(attempt["diagnostic_body_source"] == "interactive_cli" for attempt in captures)
            continue_counts = [model_continue_prompt_count(model) for _, model, _ in received]
            assert continue_counts == [0, 1], continue_counts
            recovery_proof = {"standard_continue_count_by_model_post": continue_counts,
                              "original_pid": original, "original_process_exited": True,
                              "original_history_prefix_preserved": True, "binding_preserved": True,
                              "original_history_bytes_equal": history_after_receipt == original_history,
                              "original_history_added_record_types": [row["type"] for row in appended],
                              "stop_reason": final["stop_reason"]}
        if exact_tool_receipts:
            observed = [(row["role"], block) for row in received[-1][1]["messages"] for block in blocks(row)
                        if block.get("type") == "tool_result" and block["tool_use_id"] in expected_ids]
            proof_key = "empty_tool_receipt" if empty_tool_receipt else "tool_receipt_text_blocks"
            proof[proof_key] = {**recovery_proof, "input_shape": empty_tool_receipt or tool_receipt_text_blocks,
                                "submitted_results": result["content"], "observed_results": observed,
                                "initial_http": initial_status, "receipt_http": status,
                                "initial_process_lost": recover_pending}
            if tool_receipt_nested_cache or tool_receipt_outer_cache:
                direct_markers = observed_cache_breakpoints(received[-1][1])
                current_markers = [marker[-1] for marker in direct_markers if marker[-1].get("tool_use_id") in expected_ids]
                assert current_markers == [item for item in expected_receipts if "cache_control" in item], direct_markers
                if not history_cache_markers:
                    assert len(direct_markers) == len(current_markers), direct_markers
                proof[proof_key]["direct_message_cache_breakpoints"] = direct_markers
            if tool_receipt_nested_cache:
                proof[proof_key]["nested_cache_ttl"] = tool_receipt_nested_cache
            if tool_receipt_outer_cache:
                proof[proof_key]["outer_cache_ttl"] = tool_receipt_outer_cache
                proof[proof_key]["expected_model_results"] = expected_receipts
        if tool_receipt_images:
            actual = {}
            for block in result["content"]:
                tool_id = block["tool_use_id"]
                assert find_blocks(received[-1][1], "tool_use_id", tool_id) == [("user", block)]
                actual[tool_id] = {"result_sha256": sha256(encoded(block)).hexdigest(),
                                   "is_error_present": "is_error" in block,
                                   "is_error": block.get("is_error"),
                                   "formats": [item["source"]["media_type"] for item in block["content"]
                                               if item["type"] == "image"]}
            error_status, error_request = error_receipts["error_tool_receipt_images"]
            image_only_status, image_only_request = error_receipts["error_tool_receipt_image_only"]
            proof["tool_receipt_images"] = {**recovery_proof, "records": actual,
                                           "error_http": error_status, "error_request_id": error_request,
                                           "image_only_error_http": image_only_status,
                                           "image_only_error_request_id": image_only_request}
        if model_connection_contract:
            count = 1 if model_connection_contract == "live" else 2
            ports = {port for port, _ in model_connection_posts}
            assert len(ports) == len(model_tunnels) == len(model_client_hellos) == len(proxy_targets) == count
            assert set(model_tunnels) == set(proxy_targets) == ports
            assert set(model_client_hellos) == {(port, "api.anthropic.com") for port in ports}
            observations = []
            for (port, digest), attempt, session_origin in zip(
                model_connection_posts, captures,
                ("external_import", "disk_resume" if recover_pending else "live_process"), strict=True,
            ):
                assert attempt["diagnostic_body_source"] == "interactive_cli"
                assert attempt["diagnostic_session_origin"] == session_origin
                assert attempt["confirmed_model_responses"] == 1 and attempt["cli_and_https_body_sha256"] == digest
                observations.append({"model_peer_port": port, "proxy_peer_port": model_tunnels[port],
                                     "model_body_sha256": digest, "request_id": attempt["request_id"],
                                     "attempt_id": attempt["attempt_id"], "session_origin": session_origin})
            proof["model_connection_contract"] = {"mode": model_connection_contract,
                                                  "client_hellos": model_client_hellos, "model_posts": observations}
        if explicit_custom_tool_type:
            tool_definitions = []
            for _, native, _ in received:
                verify_automatic_model_tools(native, declared)
                assert all(tool.get("type", "custom") == "custom" for tool in native["tools"])
                tool_definitions.append(native["tools"])
            assert all(attempt["diagnostic_body_source"] == "interactive_cli" for attempt in captures)
            proof["explicit_custom_tool_type"] = {"input_tools": declared, "model_tools_by_post": tool_definitions,
                                                 "omitted_type_receipt_http": changed_custom_type,
                                                 "omitted_type_receipt_request_id": changed_custom_request}
        if oauth_rotation:
            assert refresh_calls == [True]
            assert [row["credential"] for row in credential_observations] == ["initial", "rotated"]
            for observed, attempt in zip(credential_observations, captures, strict=True):
                assert observed["model_body_sha256"] == attempt["cli_and_https_body_sha256"]
                assert attempt["diagnostic_body_source"] == "interactive_cli" and attempt["confirmed_model_responses"] == 1
                observed.update(request_id=attempt["request_id"], attempt_id=attempt["attempt_id"],
                                session_origin=attempt["diagnostic_session_origin"])
            assert credential_observations[1]["session_origin"] == ("disk_resume" if recover_pending else "live_process")
            proof["oauth_rotation"] = {"refresh_calls": len(refresh_calls), "model_credentials": credential_observations,
                                       "capture_credentials_redacted": True}
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
            observed = [[mark for mark in observed_cache_breakpoints(model)
                         if not tool_receipt_outer_cache or mark[-1].get("tool_use_id") != NEW_ID]
                        for _, model, _ in received]
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
        if parallel_tools and not (tool_receipt_images or exact_tool_receipts):
            first, second = (document for _, document, _ in received)
            assert final["stop_reason"] == "end_turn", final
            assert TOOL["input_schema"] != PARALLEL_SECOND_TOOL["input_schema"]
            for native in (first, second):
                second_tool, = [t for t in native["tools"] if t["name"] == NATIVE_SECOND_TOOL_NAME]
                assert same_json_value(second_tool["input_schema"], PARALLEL_SECOND_TOOL["input_schema"]), second_tool
            assert not find_blocks(first, "id", SECOND_ID) and not find_blocks(first, "tool_use_id", SECOND_ID)
            ((call_role, second_call),) = find_blocks(second, "id", SECOND_ID)
            assert call_role == "assistant" and same_json_value(second_call, {
                "type": "tool_use", "name": NATIVE_SECOND_TOOL_NAME, "id": SECOND_ID, "input": PARALLEL_SECOND_ARGS,
            }), second_call
            (success_role, success), = find_blocks(second, "tool_use_id", NEW_ID)
            assert success_role == "user" and not success.get("is_error", False) and success["content"] == REPLY
            (role, failed), = find_blocks(second, "tool_use_id", SECOND_ID)
            assert role == "user" and failed["is_error"] is True
            # 记录固定 CLI 两种续轮的实收差异，模型结果始终按原调用 ID 归属。
            token_reminder = failed["content"].startswith(SECOND_REPLY + "\n\n<system-reminder>\n<total_tokens>")
            if recover_pending:
                assert failed["content"] == SECOND_REPLY, failed
            else:
                assert token_reminder, failed
            client_order = [block["tool_use_id"] for block in result["content"]]
            model_order = [block["tool_use_id"] for row in second["messages"] for block in blocks(row)
                           if block.get("tool_use_id") in expected_ids]
            assert client_order == expected_ids[::-1]
            assert model_order == (client_order if recover_pending else expected_ids), (client_order, model_order)
            proof.update(parallel_tool_receipt_rejections=partial_statuses, preserved_tool_error=True,
                         client_result_order=client_order, model_result_order=model_order,
                         distinct_tool_schemas=True, exact_success_text=True, failure_token_reminder=token_reminder,
                         public_second_tool_input=public_inputs[1], model_second_tool_input=second_call["input"])
            if recover_pending:
                assert binding_file.read_bytes() == original_binding, binding_file
                proof["original_binding_preserved"] = True
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
            if history_cache_markers:
                assert all(not row["cli_source_cache_control"] for row in raw_media.values()), raw_media
                assert all(attempt["diagnostic_body_source"] == "interactive_cli" for attempt in captures), captures
            proof.update(current_images=[block["source"]["media_type"] for block in current if block["type"] == "image"],
                         changed_current_images_status=changed_media, raw_current_image_content=raw_media)
        if auto_tool_choice:
            model_tools = [verify_automatic_model_tools(native, declared) for _, native, _ in received]
            assert all(attempt["diagnostic_body_source"] == "interactive_cli" for attempt in captures), captures
            proof.update(auto_tool_choice=[native.get("tool_choice") for _, native, _ in received],
                         input_tool_choice=body.get("tool_choice"), receipt_tool_choice=follow.get("tool_choice"),
                         model_tools=model_tools,
                         model_tool_choice_present=["tool_choice" in native for _, native, _ in received],
                         changed_tool_choice_status=changed_choices["none"], tool_choice_rejections=changed_choices)
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
        if fixed_thinking_model:
            actual = [{key: native.get(key) for key in ("model", "thinking", "max_tokens")} for _, native, _ in received]
            assert actual == [{key: body[key] for key in ("model", "thinking", "max_tokens")}] * 2, actual
            assert all(attempt["diagnostic_body_source"] == "interactive_cli" for attempt in captures), captures
            if fixed_thinking_display == "updates":
                assert len(model_betas) == 2 and all(THINKING_UPDATES_BETA in beta.split(",") for beta in model_betas), model_betas
            proof["fixed_thinking"] = {"model_posts": actual, "changes": changed_fixed_thinking}
            if summarized_thinking:
                proof["client_content"] = final["content"]
        if signed_tool_history:
            hydrated = find_blocks(received[1][1], "type", signed_type)
            assert hydrated == [("assistant", signed_block)], (
                hydrated, [(row["role"], [block["type"] for block in blocks(row)]) for row in received[1][1]["messages"]],
            )
            proof.update(signed_reply=hydrated[0][1], recorded_signed_tool_models=signed_tool_models)
            if redacted_thinking:
                assert not find_blocks(received[1][1], "type", "thinking")
                proof.update(observed_redacted_preserved=True, changed_redacted_data_status=changed_signature,
                             changed_redacted_data_rejection=signature_rejection)
            else:
                proof.update(observed_signature_preserved=True, changed_signature_status=changed_signature,
                             changed_signature_rejection=signature_rejection)
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
                if redacted_thinking:
                    archived_thinking = [block for block in signed["content"]
                                         if block["type"] in ("thinking", "redacted_thinking")]
                    assert archived_thinking == [signed_block], archived_thinking
                proof["recovered_signed_tool_model"] = signed["model"]
            continue_prompt_count = model_continue_prompt_count(native_recovery)
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
                    "outcome": record["outcome"],
                    "confirmed_model_responses": record["diagnostic_context"]["tui_confirmed_model_responses"],
                    "attempt_count": record["attempt_count"], "request_id": rejected_request,
                    "reservation_id": reservation, "receipt_reopened": True,
                }
                if held:
                    assert captures[-1]["attempt_id"] != reservation
                    proof["recovered_pending_tool"]["workspace_rejection"].update(
                        fault=recovery_workspace_rejection, binding_preserved=True,
                        binding_recreated=False, source_receipt_revision_preserved=True,
                        denials_after_restore=after_restore, restored_reservation_id=captures[-1]["attempt_id"],
                    )
            if recovery_readiness_rejection:
                assert readiness_request != continuation_request_id
                proof["recovered_pending_tool"]["readiness_rejection"] = {
                    "http_status": readiness_status, "error_stage": readiness_record["error_stage"],
                    "attempt_count": readiness_record["attempt_count"], "request_id": readiness_request,
                    "reservation_id": None, "receipt_reopened": True,
                }
        if current_images and not recover_pending and not restart_history:
            proof["image_only"] = verify_image_only_requests(
                manage, token, account_token, headers, received,
                policy="replace" if toggle_pending_policy else tool_policy or "append",
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
                     sender_status=None, observe_response=None, trace_recovery_resend=False, resend_of=None):
    """在断言前保留本轮公开响应与诊断归属。
    @param manage 管理入口。@param token 合成凭据。@param body 公开输入。@param headers 原入口头。
    @param received 隔离模型收件。@param phase 夹具阶段。@param expected_status 预期 HTTP 状态，空值保留实测状态。
    @param trace_startup 是否记录公开请求时间及失败后线程栈。
    @param sender_status 可选，只在已保留失败和请求诊断后读取隔离发送器状态。
    @param observe_response 可选，在连接仍打开时读取公开响应头或前缀。
    @param trace_recovery_resend 可选，仅为隔离回执的 503 采集一次补发，保留原失败。
    @param resend_of 可选，原请求的夹具观测 ID。
    @return 实际状态、响应字节和公开请求 ID。
    """
    started_at = datetime.now(timezone.utc).isoformat(timespec="milliseconds")
    started = monotonic()
    before = len(received)
    session_id = headers["x-session-id"]
    attribution = {"phase": phase, "session_id": session_id, "observation_id": str(uuid4())}
    if resend_of is not None:
        attribution["resend_of"] = resend_of
    evidence = {"started_at": started_at, "http_status": None, "request_id": None,
                "expected_status": expected_status, "client_stage": "sending_request", "response_headers_ms": None}

    def request_sent():
        evidence["client_stage"] = "waiting_response_headers"
        if trace_startup:
            startup_event("public_request_sent", **attribution)

    def observe(response):
        evidence.update(http_status=response.status, request_id=response.getheader("x-cc2api-request-id"),
                        response_headers_ms=round((monotonic() - started) * 1000), client_stage="reading_response_body")
        assert response.getheader("x-v3-tui-body-source") is None
        assert response.getheader("x-v3-tui-session-origin") is None
        assert response.getheader("x-v3-tui-instruction-location") is None
        if trace_startup:
            startup_event("public_response_headers", **attribution, response_headers_ms=evidence["response_headers_ms"],
                          request_id=evidence["request_id"], http_status=response.status,
                          model_posts_during=len(received) - before)
        if observe_response is not None:
            observe_response(response)

    def report(failed_at, **details):
        failed_ns = monotonic_ns() if trace_startup else None
        event = {"event": "messages_failure", **attribution, **evidence, **details,
                 "failed_at": failed_at.isoformat(timespec="milliseconds"),
                 "elapsed_ms": round((monotonic() - started) * 1000),
                 "request_body_sha256": sha256(encoded(body)).hexdigest(),
                 "model_posts_before": before, "model_body_sha256": [sha for sha, _, _ in received[before:]]}
        if failed_ns is not None:
            event["monotonic_ns"] = failed_ns
        event["model_posts_during"] = len(event["model_body_sha256"])
        # 先留下原始观测。诊断读回失败时仍能保留同一请求的 HTTP 和模型收件情况。
        print(json.dumps(event, ensure_ascii=False), file=stderr, flush=True)
        if trace_startup:
            startup_event("fixture_threads_after_failure", **attribution, request_id=evidence["request_id"],
                          client_stage=evidence["client_stage"])
            with suppress(OSError, RuntimeError):
                dump_traceback(file=stderr)
        report_request_diagnostics(manage, phase, evidence["request_id"], session_id, started_at,
                                   failed_at=failed_at, observation_id=attribution["observation_id"])
        if trace_startup and sender_status is not None:
            try:
                state = sender_status()
            except (HTTPException, OSError, ValueError) as error:
                startup_event("sender_status_after_failure", **attribution,
                              request_id=evidence["request_id"], lookup_error=type(error).__name__)
            else:
                startup_event("sender_status_after_failure", **attribution,
                              request_id=evidence["request_id"], ready=state.get("ready"), idle=state.get("idle"))

    if trace_startup:
        startup_event("public_request_start", **attribution, started_at=started_at, model_posts_before=before)
    try:
        status, raw = call(18090, "POST", "/v1/messages", token, body, headers, observe_headers=observe,
                           observe_request_sent=request_sent)
    except (HTTPException, OSError) as error:
        report(datetime.now(timezone.utc), transport_error=type(error).__name__,
               transport_stage="response_body" if evidence["http_status"] is not None else "before_response_headers")
        raise
    if expected_status is not None and status != expected_status:
        failed_at = datetime.now(timezone.utc)
        evidence["client_stage"] = "response_complete"
        try:
            payload = json.loads(raw)
        except ValueError:
            payload = None
        error = payload.get("error") if isinstance(payload, dict) else None
        if isinstance(error, dict):
            error = {key: error[key] for key in ("type", "code", "message") if isinstance(error.get(key), str)}
        report(failed_at, response_error=error if isinstance(error, (dict, str)) else None,
               response_sha256=sha256(raw).hexdigest(), response_bytes=len(raw))
        if status == 503 and trace_recovery_resend:
            # 补发使用同一合成输入和新观测窗口。两次诊断各自收口，夹具仍报告第一次失败。
            with suppress(HTTPException, OSError):
                checked_messages(manage, token, body, headers, received, phase + "_resend", expected_status=None,
                                 trace_startup=trace_startup, sender_status=sender_status,
                                 resend_of=attribution["observation_id"])
        raise AssertionError((phase, status, expected_status, evidence["request_id"]))
    if resend_of is not None:
        startup_event("public_response_complete", **attribution, request_id=evidence["request_id"], http_status=status,
                      model_posts_during=len(received) - before, request_body_sha256=sha256(encoded(body)).hexdigest())
        report_request_diagnostics(manage, phase, evidence["request_id"], session_id, started_at,
                                   failed_at=datetime.now(timezone.utc), observation_id=attribution["observation_id"],
                                   event_name="messages_resend_diagnostics")
    return status, raw, evidence["request_id"]


def report_request_diagnostics(manage, phase, request_id, session_id, started_at, *, failed_at=None,
                               observation_id=None, event_name="messages_failure_diagnostics"):
    """在网关退出前读回本请求诊断。@param manage 管理入口。@param phase 夹具阶段。
    @param request_id 响应关联头，可为空。@param session_id 合成会话。@param started_at 本次 UTC 开始时间。
    @param failed_at 无关联头时传入本次观测结束当刻的 UTC 时间。
    @param observation_id 可选，本次夹具观测 ID。@param event_name 诊断事件名。@return 诊断事件。
    """
    event = {"event": event_name, "phase": phase, "request_id": request_id,
             "correlation": "response_request_id" if request_id else "session_candidates", "requests": []}
    if observation_id is not None:
        event["observation_id"] = observation_id
    if request_id:
        query = {"correlation_id": request_id}
    else:
        if failed_at is None:
            raise ValueError("会话候选查询须提供原失败时间")
        # 存储按毫秒记录起点。排他上界取下一毫秒，保留失败所在毫秒内的候选。
        until = (failed_at + timedelta(milliseconds=1)).isoformat(timespec="milliseconds")
        event.update(since=started_at, until=until)
        query = {"since": started_at, "until": until, "page_size": 100}
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


def read_receipt_stage(path, request_id, reservation, stage):
    """按原请求和预留读取隔离网关的实测事件。@param path 网关日志。@param request_id 原公开请求。
    @param reservation 原预留。@param stage 探针阶段。@return 事件或空值。
    """
    for line in path.read_text(errors="replace").splitlines():
        if not line.startswith("{") or stage not in line:
            continue
        with suppress(ValueError):
            event = json.loads(line)
            if (event.get("request_id"), event.get("reservation_id"), event.get("stage")) == (
                request_id, reservation, stage,
            ):
                return event
    return None


def verify_lost_receipt_replay(manage, token, body, headers, received, callbacks, original_request, model_reply, mode):
    """重交原响应已经丢失的非流式回执。@param manage 管理入口。@param token 原调用方。
    @param body 原 JSON 回执。@param headers 原会话。@param received 模型真实收件。@param callbacks 工具调用。
    @param original_request 原公开请求。@param model_reply 模型观测。@param mode 模型尚待生成或已写出。
    @return 重交的公开状态与投递证据。
    """
    assert body["stream"] is False
    generated_at_retry = "generated" in model_reply
    assert generated_at_retry == (mode == "lost")
    model_posts_before = len(received)
    status, raw, request_id = checked_messages(
        manage, token, body, headers, received, "retry_after_original_reply_lost",
        expected_status=None, trace_startup=True,
    )
    assert request_id and request_id != original_request

    def completed_diagnostic():
        detail = manage("GET", "request-diagnostics/" + request_id)
        return detail if detail["request"].get("finished_at") else None

    diagnostic = wait_for(completed_diagnostic)
    error = json.loads(raw).get("error", {})
    assert diagnostic["attempts"] == [] and len(received) == model_posts_before, (status, error, diagnostic)
    recovery_used = status == 409 and error.get("code") == "recovery_used"
    waiting_for_original = mode == "lost-live" and status == 503 and error.get("type") == "api_error"
    assert recovery_used or waiting_for_original, (status, error, diagnostic)
    return {"mode": mode, "http_status": status, "request_id": request_id, "error": error,
            "error_code": error.get("code"), "error_stage": diagnostic["request"]["error_stage"],
            "outcome": diagnostic["request"]["outcome"],
            "model_generated_at_retry": generated_at_retry, "attempt_count": len(diagnostic["attempts"]),
            "new_model_posts": len(received) - model_posts_before, "client_tool_calls": len(callbacks)}


def verify_unknown_receipt_terminal(manage, request_id, reservation, expected_attempt):
    """在后台尝试收口后核对原公开 502。@param manage 管理入口。@param request_id 原公开请求。
    @param reservation 原预留。@param expected_attempt 尝试的状态、结果及阶段。@return 根和尝试终态。
    """
    def finished_attempt():
        detail = manage("GET", "request-diagnostics/" + request_id)
        attempts = detail["attempts"]
        assert len(attempts) <= 1, detail
        if attempts and attempts[0].get("finished_at") and detail["request"].get("finished_at"):
            return detail

    original = wait_for(finished_attempt)
    record = original["request"]
    assert (record["request_id"], record["status_code"], record["outcome"], record["error_stage"]) == (
        request_id, 502, "transport_error", "tui_send_http",
    ), original
    assert record["context"]["tui_reservation_id"] == reservation
    assert record["attempt_count"] == 1 and record.get("native_rejection") is None, original
    (attempt,) = original["attempts"]
    assert (attempt["request_id"], attempt["attempt_id"]) == (request_id, reservation), original
    assert (attempt["status_code"], attempt["outcome"], attempt["error_stage"]) == expected_attempt, original
    return {"request_id": request_id, "reservation_id": reservation, "status_code": record["status_code"],
            "outcome": record["outcome"], "error_stage": record["error_stage"], "finished_at": record["finished_at"],
            "attempt_count": record["attempt_count"],
            "confirmed_model_responses": record["context"].get("tui_confirmed_model_responses"),
            "attempt": {field: attempt[field] for field in (
                "attempt_id", "request_id", "status_code", "outcome", "error_stage", "finished_at",
            )}, "session_origin": (attempt.get("context") or {}).get("tui_session_origin")}


def verify_unknown_receipt_replay(manage, database, token, body, headers, received, callbacks,
                                  model_prefix, model_terminal, original_request, reservation, mode,
                                  gateway_trace, model_reply):
    """公开 502 后读取同一次合法工具回执的回复。@param manage 管理入口。
    @param database 隔离用量库。@param token 原调用方。@param body 原回执。@param headers 原会话。
    @param received 实际模型收件。@param callbacks 已执行的工具。
    @param model_prefix 放行模型首段。@param model_terminal 放行模型终帧。
    @param original_request 原公开请求。@param reservation 原预留。@param mode 生成中或已完成。
    @param gateway_trace 网关原始阶段日志。@param model_reply 模型生成及写出结果。
    @return 公开响应、尝试及用量证据。
    """
    def usage():
        with closing(connect(database)) as db:
            rows = db.execute("SELECT input_tokens,output_tokens,partial FROM usage_records ORDER BY started_at").fetchall()
        return rows if len(rows) == 2 and all(partial == 0 for _, _, partial in rows) else None

    def observed_completion():
        write = wait_for(lambda: model_reply.get("write"))
        private = wait_for(lambda: read_receipt_stage(gateway_trace, original_request, reservation,
                                                      "gateway_tui_private_body"))
        cache = wait_for(lambda: read_receipt_stage(gateway_trace, original_request, reservation,
                                                    "gateway_tui_reply_cache"))
        assert write["result"] == "written" and private["result"] == "received" and cache["result"] == "ready", (
            write, private, cache,
        )
        generated = model_reply["generated"]
        assert generated["monotonic_ns"] <= private["monotonic_ns"] <= cache["monotonic_ns"], (
            generated, private, cache,
        )
        return {"model_generated": generated, "model_write": write, "private_delivery": private,
                "gateway_cache": cache, "response_deliverable": True}

    completion = None
    if mode == "complete":
        model_prefix.set()
        model_terminal.set()
        completion = observed_completion()

    prefix = []
    response_id = None
    content_type = None
    response_headers_ns = None
    replay_sent = None
    second_reader_id = None
    second_reader_lines = []
    model_posts_before = len(received)

    def request_sent():
        nonlocal replay_sent
        replay_sent = monotonic_ns()
        startup_event("unknown_receipt_replay_sent", mode=mode, original_request_id=original_request,
                      reservation_id=reservation, model_posts=len(received), terminal_released=model_terminal.is_set(),
                      monotonic_ns=replay_sent)
        if mode == "live":
            assert not model_terminal.is_set()
            model_prefix.set()
            # JSON 聚合后才交付公开响应头，发出原样重交后即放行终帧。
            if not body["stream"]:
                model_terminal.set()

    def read_second_prefix(response):
        nonlocal second_reader_id
        assert response.status == 200 and response.getheader("Content-Type").split(";", 1)[0] == "text/event-stream"
        second_reader_id = response.getheader("x-cc2api-request-id")
        second_reader_lines.extend(read_tool_stream_data_lines(response, 3))
        assert second_reader_lines == prefix and not model_terminal.is_set() and len(received) == 2
        model_terminal.set()

    def response_headers(response):
        nonlocal response_id, content_type, response_headers_ns
        response_id = response.getheader("x-cc2api-request-id")
        content_type = response.getheader("Content-Type")
        response_headers_ns = monotonic_ns()
        if mode == "live" and body["stream"] and response.status == 200:
            prefix.extend(read_tool_stream_data_lines(response, 3))
            assert not model_terminal.is_set() and len(received) == 2
            # 原客户端等 502 已结束。两个独立重交都接到原流前缀后，再允许模型生成终帧。
            status, tail = call(18090, "POST", "/v1/messages", token, body, headers, observe_headers=read_second_prefix)
            assert status == 200 and second_reader_id and second_reader_id not in (original_request, response_id)
            second_reader_lines.extend(line for line in tail.splitlines(keepends=True) if line.startswith(b"data:"))

    try:
        status, raw = call(18090, "POST", "/v1/messages", token, body, headers,
                           observe_headers=response_headers, observe_request_sent=request_sent)
    finally:
        model_prefix.set()
        model_terminal.set()
    assert status == 200 and content_type and response_id and response_id != original_request, (status, response_id, raw)
    assert len(received) == model_posts_before == 2 and callbacks == [NEW_ID]
    if mode == "live":
        completion = observed_completion()
        assert replay_sent < completion["model_generated"]["monotonic_ns"]
    else:
        assert completion["gateway_cache"]["monotonic_ns"] < replay_sent
    media_type = content_type.split(";", 1)[0]
    if body["stream"]:
        assert media_type == "text/event-stream", content_type
        lines = prefix + [line for line in raw.splitlines(keepends=True) if line.startswith(b"data:")]
        if mode == "live":
            assert second_reader_id and second_reader_lines == lines, (second_reader_id, second_reader_lines, lines)
        events = [json.loads(line[5:]) for line in lines]
        assert [event["type"] for event in events] == [
            "message_start", "content_block_start", "content_block_delta", "content_block_stop",
            "message_delta", "message_stop",
        ]
        assert events[2]["delta"]["text"] == FINAL and events[-2]["delta"]["stop_reason"] == "end_turn"
        message_id = events[0]["message"]["id"]
    else:
        assert media_type == "application/json", content_type
        reply = json.loads(raw)
        assert (reply["type"], reply["role"], reply["stop_reason"], reply["content"]) == (
            "message", "assistant", "end_turn", [{"type": "text", "text": FINAL}],
        ), reply
        assert response_headers_ns >= completion["model_generated"]["monotonic_ns"]
        message_id = reply["id"]
    assert message_id.startswith("msg_")

    def finished_reader(request_id):
        replay = manage("GET", "request-diagnostics/" + request_id)
        if replay["request"].get("finished_at"):
            return replay

    reader_ids = [response_id] + ([second_reader_id] if second_reader_id else [])
    expected_outcomes = {"tui_reconnect_stream"} if mode == "live" else {"tui_reconnect_cached"}
    if mode == "live" and not body["stream"]:
        # 首个私有 JSON 回包聚合期间，缓存写者可在重交读者完成订阅前发布完整响应。
        expected_outcomes.add("tui_reconnect_cached")
    reader_proofs = []
    for reader_id in reader_ids:
        replay = wait_for(lambda: finished_reader(reader_id))
        outcome = replay["request"]["outcome"]
        assert replay["request"]["status_code"] == 200 and replay["attempts"] == [] and outcome in expected_outcomes, replay
        reader = {"request_id": reader_id, "http_status": 200, "outcome": outcome, "attempt_count": 0}
        if body["stream"]:
            frames = second_reader_lines if reader_id == second_reader_id else lines
            reader.update(sse_frames=len(frames), sse_data_sha256=sha256(b"".join(frames)).hexdigest())
        reader_proofs.append(reader)
    rows = wait_for(usage)
    assert rows == [(10, 8, 0), (10, 8, 0)], rows
    original = verify_unknown_receipt_terminal(manage, original_request, reservation, (200, "success", None))
    assert original["confirmed_model_responses"] == 1
    return {"mode": mode, "request_id": response_id, "http_status": status, "outcome": reader_proofs[0]["outcome"],
            "attempt_count": 0, "new_model_posts": len(received) - model_posts_before,
            "client_tool_calls": len(callbacks), "public_message_id": message_id, "content_type": media_type,
            "json_response_sha256": None if body["stream"] else sha256(raw).hexdigest(),
            "frames_before_model_terminal": len(prefix), "late_original_attempt": reservation,
            "session_origin": original["session_origin"], "original_model_responses_after_replay": 1,
            "original_terminal": original, "readers": reader_proofs,
            "original_receipt_sha256": received[1][0], "usage": rows,
            "completion": completion, "replay_sent_ns": replay_sent, "response_headers_ns": response_headers_ns}


def signed_receipt_rejection(manage, phase, request_id, session_id, status, raw):
    """核对签名回执公开拒绝与发送前诊断。
    @param manage 管理入口。@param phase 夹具阶段。@param request_id 公开响应头中的请求 ID。
    @param session_id 合成会话。@param status 公开 HTTP 状态。@param raw 公开正文。
    @return 同一公开请求的拒绝证据。
    """
    assert request_id
    error = json.loads(raw)["error"]
    evidence = report_request_diagnostics(manage, phase, request_id, session_id, None,
                                         event_name="signed_receipt_rejection_diagnostics")
    (record,) = evidence["requests"]
    context = record["diagnostic_context"]
    assert record["request_id"] == request_id and record["status_code"] == status == 422
    assert record["attempt_count"] == 0 and not record["attempts"]
    assert context["tui_reservation_id"]
    return {"request_id": request_id, "reservation_id": context["tui_reservation_id"], "http_status": status,
            "response_error": error, "error_stage": record["error_stage"], "native_rejection": record["native_rejection"],
            "attempt_count": record["attempt_count"], "response_sha256": sha256(raw).hexdigest()}


def verify_cancel_before_headers(
    manage, token, headers, history, received, sender_status, sender_state_after_failure, public_format,
):
    """核对首响前取消后的真实进程退出和同会话发问。
    @param manage 管理入口。@param token 合成公开令牌。@param headers 隔离会话。
    @param history 客户端已确认的历史。@param received 隔离模型实收。
    @param sender_status 真实发送器的进程及预留状态。
    @param sender_state_after_failure 原失败日志后的短预算状态读取。
    @param public_format 原公开请求的响应格式。@return 两轮观察证据。
    """
    original = {"model": MODEL, "max_tokens": 128, "stream": public_format == "sse", "tools": [TOOL],
                "messages": [*history, {"role": "user", "content": CANCELLED_QUESTION}]}
    since = datetime.now(timezone.utc).isoformat(timespec="milliseconds")
    try:
        checked_messages(
            manage, token, original, headers, received, "cancel_before_headers", trace_startup=True,
            sender_status=sender_state_after_failure,
        )
        raise AssertionError("启动闸门尚未开放时已经收到首响应头")
    except TimeoutError:
        blocked = json.loads((CANCEL_LAUNCH_PROBE / "blocked.json").read_bytes())
        failure = report_request_diagnostics(
            manage, "cancel_before_headers_reservation", None, headers["x-session-id"], since,
            failed_at=datetime.now(timezone.utc),
        )
        (candidate,) = failure["requests"]
        assert candidate["diagnostic_context"]["tui_reservation_id"] == blocked["reservation_id"]
        busy = sender_status()
        assert busy["active"] > 0 and busy["tui_v2"]["ready"] and not busy["tui_v2"]["idle"], busy
        assert not received
    finally:
        launch_released_ns = monotonic_ns()
        (CANCEL_LAUNCH_PROBE / "release").touch()

    retired = wait_for(lambda: json.loads((CANCEL_LAUNCH_PROBE / "retired.json").read_bytes()))
    assert retired["reservation_id"] == blocked["reservation_id"] and retired["retired"]
    assert retired["process_slots_in_use"] == 0 and retired["monotonic_ns"] >= launch_released_ns
    spawned_path = CANCEL_LAUNCH_PROBE / "spawned.json"
    spawned = json.loads(spawned_path.read_bytes()) if spawned_path.exists() else None
    if spawned is not None:
        assert spawned["reservation_id"] == retired["reservation_id"] and spawned["pid"] == retired["pid"]
        assert launch_released_ns <= spawned["monotonic_ns"] <= retired["monotonic_ns"]
        assert retired["returncode"] is not None and not Path(f"/proc/{retired['pid']}").exists()

    def sender_idle():
        state = sender_status()
        return state if state["active"] == 0 and state["tui_v2"]["ready"] and state["tui_v2"]["idle"] else None

    idle = wait_for(sender_idle)
    assert not received
    fresh = {**original, "stream": False, "tools": [],
             "messages": [*history, {"role": "user", "content": CHANGED_QUESTION}]}
    status, raw, fresh_id = checked_messages(
        manage, token, fresh, headers, received, "same_session_after_header_cancel", trace_startup=True,
    )
    assert json.loads(raw)["content"] == [{"type": "text", "text": FINAL}]
    ((digest, model, _),) = received
    user_texts = [block.get("text") for row in model["messages"] if row["role"] == "user" for block in blocks(row)]
    assert user_texts.count(CHANGED_QUESTION) == 1 and CANCELLED_QUESTION not in user_texts
    wait_for(sender_idle)

    request_id = candidate["request_id"]
    cancelled = manage("GET", "request-diagnostics/" + request_id)
    ended = cancelled["request"]
    assert ended["request_id"] == request_id and ended["finished_at"]
    assert (ended["outcome"], ended["error_stage"], ended["status_code"]) == ("cancelled", "downstream_headers", None)
    assert ended["context"]["tui_reservation_id"] == retired["reservation_id"]
    assert ended["context"].get("tui_confirmed_model_responses") is None
    assert ended["attempt_count"] == 0 and not cancelled["attempts"]
    (next_request,) = report_request_diagnostics(
        manage, "same_session_after_header_cancel", fresh_id, headers["x-session-id"], since,
        event_name="header_cancel_followup_diagnostics",
    )["requests"]
    context = next_request["diagnostic_context"]
    assert next_request["account_id"] == ended["account_id"] and fresh_id != request_id
    assert next_request["attempt_count"] == context["tui_confirmed_model_responses"] == 1
    assert context["tui_reservation_id"] != retired["reservation_id"]
    assert [(attempt["attempt_id"], attempt["request_id"]) for attempt in next_request["attempts"]] == [
        (context["tui_reservation_id"], fresh_id),
    ]
    assert len(received) == 1
    return {
        "public_format": public_format, "account_id": ended["account_id"], "session_id": headers["x-session-id"],
        "original": {"request_id": request_id, "client_http_status": None, "client_request_id": None,
                     "reservation_id": retired["reservation_id"], "error_stage": ended["error_stage"],
                     "attempt_count": ended["attempt_count"], "model_posts": 0},
        "launch_blocked": blocked, "launch_released_ns": launch_released_ns, "spawned": spawned, "retired": retired,
        "sender": {"active_before_release": busy["active"], "active_after": idle["active"], "idle_after": idle["tui_v2"]["idle"]},
        "next": {"http_status": status, "request_id": fresh_id, "reservation_id": context["tui_reservation_id"],
                 "attempt_count": next_request["attempt_count"], "model_posts": 1, "model_body_sha256": digest},
        "wire_final": "unavailable",
    }


def verify_cancelled_question(manage, token, headers, history, received, release_model, sender_state, trace_startup):
    """取消未完整工具流，再按客户端确认历史改问。
    @param manage 管理入口。@param token 合成公开令牌。@param headers 同一公开会话。
    @param history 客户端已确认的历史。@param received 隔离模型收件。
    @param release_model 原隔离模型的尾段等待。@param sender_state 真实 sender 的状态读取。
    @param trace_startup 是否记录同钟阶段。@return 取消、新轮及旧回执的证据。
    """
    session_id = headers["x-session-id"]
    old = {"model": MODEL, "max_tokens": 128, "stream": True, "tools": [TOOL],
           "messages": [*history, {"role": "user", "content": CANCELLED_QUESTION}]}
    since = datetime.now(timezone.utc).isoformat(timespec="milliseconds")
    if trace_startup:
        startup_event("public_request_start", phase="cancelled_question", session_id=session_id, model_posts_before=0)
    with closing(HTTPConnection("127.0.0.1", 18090, timeout=30)) as connection:
        connection.request("POST", "/v1/messages", encoded(old), {
            "Authorization": "Bearer " + token, "Content-Type": "application/json",
            "anthropic-version": "2023-06-01", **headers,
        })
        with closing(connection.getresponse()) as response:
            request_id = response.getheader("x-cc2api-request-id")
            assert response.status == 200 and request_id, (response.status, request_id)
            if trace_startup:
                startup_event("public_response_headers", phase="cancelled_question", request_id=request_id,
                              session_id=session_id, http_status=response.status, model_posts_during=len(received))
            prefix = []
            while line := response.readline():
                if not line.startswith(b"data:"):
                    continue
                event = json.loads(line[5:])
                prefix.append(event)
                if event.get("delta", {}).get("type") == "input_json_delta":
                    break
            assert [event["type"] for event in prefix] == [
                "message_start", "content_block_start", "content_block_delta",
            ], prefix
            tool = prefix[1]["content_block"]
            assert (tool["type"], tool["name"], tool["id"]) == ("tool_use", TOOL["name"], NEW_ID)
            argument_prefix = prefix[-1]["delta"]["partial_json"]
            complete_args = encoded(ARGS).decode()
            assert argument_prefix and complete_args.startswith(argument_prefix) and argument_prefix != complete_args
            connection.sock.shutdown(SHUT_RDWR)
            if trace_startup:
                startup_event("public_tool_prefix_cancelled", request_id=request_id, session_id=session_id,
                              tool_id=tool["id"])

    cancelled, = report_request_diagnostics(manage, "cancelled_question", request_id, session_id, since)["requests"]
    assert cancelled["outcome"] == "cancelled" and cancelled["status_code"] == 200, cancelled
    assert cancelled["attempt_count"] == cancelled["diagnostic_context"]["tui_confirmed_model_responses"] == 1
    def sender_is_idle():
        state = sender_state()
        return state.get("ready") and state.get("idle")

    wait_for(sender_is_idle)
    assert len(received) == 1 and not release_model.is_set()
    original = received[0][1]
    original_id = json.loads(original["metadata"]["user_id"])["session_id"]
    (binding_file,) = Path("/native/tui-workspaces").glob("*.json")
    binding_snapshot = binding_file.read_bytes()
    bound = json.loads(binding_snapshot)["native_session_id"]
    projects = Path("/native/tui-sessions") / bound / "home/.claude/projects"
    (archive,) = projects.glob(f"*/{original_id}.jsonl")
    original_archive = archive.read_bytes()

    new_since = datetime.now(timezone.utc).isoformat(timespec="milliseconds")
    new = {"model": MODEL, "max_tokens": 128, "stream": False,
           "messages": [*history, {"role": "user", "content": CHANGED_QUESTION}]}
    status, raw, new_request_id = checked_messages(
        manage, token, new, headers, received, "changed_question_after_cancel", trace_startup=trace_startup,
    )
    assert len(received) == 2 and not release_model.is_set()
    assert json.loads(raw)["content"] == [{"type": "text", "text": CHANGED_REPLY}]
    new_digest, submitted, _ = received[1]
    new_id = json.loads(submitted["metadata"]["user_id"])["session_id"]
    assert new_id != original_id and archive.read_bytes() == original_archive
    assert binding_file.read_bytes() == binding_snapshot
    assert not submitted.get("tools") and not find_blocks(submitted, "id", NEW_ID)
    assert not find_blocks(submitted, "tool_use_id", NEW_ID)
    roles = [(row["role"], block.get("text")) for row in submitted["messages"] for block in blocks(row)]
    expected = [(row["role"], row["content"]) for row in new["messages"]]
    relevant = {text for _, text in expected} | {CANCELLED_QUESTION}
    assert [(role, text) for role, text in roles if text in relevant] == expected, roles
    changed, = report_request_diagnostics(
        manage, "changed_question_after_cancel", new_request_id, session_id, new_since,
    )["requests"]
    assert changed["outcome"] == "success"
    assert changed["attempt_count"] == changed["diagnostic_context"]["tui_confirmed_model_responses"] == 1
    attempt, = changed["attempts"]
    assert attempt["diagnostic_context"]["tui_body_source"] == "interactive_cli"

    stale = {**old, "stream": False, "messages": [
        *old["messages"], {"role": "assistant", "content": [{**tool, "input": ARGS}]},
        {"role": "user", "content": [{"type": "tool_result", "tool_use_id": NEW_ID, "content": REPLY}]},
    ]}
    stale_since = datetime.now(timezone.utc).isoformat(timespec="milliseconds")
    rejected, _, rejected_request_id = checked_messages(
        manage, token, stale, headers, received, "cancelled_tool_receipt", expected_status=400,
        trace_startup=trace_startup,
    )
    assert len(received) == 2 and not release_model.is_set()
    stale_record, = report_request_diagnostics(
        manage, "cancelled_tool_receipt", rejected_request_id, session_id, stale_since,
    )["requests"]
    assert stale_record["attempt_count"] == 0 and stale_record["attempts"] == [], stale_record
    return {
        "cancelled_request": cancelled, "changed_request": changed, "changed_http_status": status,
        "public_session": session_id, "cancelled_native_session": original_id, "changed_native_session": new_id,
        "cancelled_tool_id": tool["id"], "partial_argument_chars": len(argument_prefix),
        "model_body_sha256": [received[0][0], new_digest], "model_posts": len(received),
        "stale_receipt_http": rejected, "stale_receipt_request_id": rejected_request_id,
        "stale_receipt_attempts": stale_record["attempt_count"], "sender_idle_after_cancel": True,
        "original_archive_preserved": True, "binding_preserved": True, "wire_final": "unavailable",
    }


def read_tool_stream_data_lines(response, count):
    """从同一个公开响应读取指定数量的 SSE 数据行。@param response HTTP 响应。
    @param count 本阶段预期数据行数。@return 按原顺序读出的字节。
    """
    lines = []
    while len(lines) < count and (line := response.readline()):
        if line.startswith(b"data:"):
            lines.append(line)
    assert len(lines) == count, (count, lines)
    return lines


def next_tool_stream_receipt(follow, tool, *, result=None):
    """提交刚收到的工具 ID。@param follow 原续轮请求。@param tool 完整调用。
    @param result 可选的合成工具返回块。@return 下一个合法回执。
    """
    if result is None:
        result = {"type": "tool_result", "tool_use_id": tool["id"], "content": SECOND_REPLY}
    rows = [
        {"role": "assistant", "content": [{"type": "text", "text": RECONNECT_PREFIX}, tool]},
        {"role": "user", "content": [result]},
    ]
    return {**follow, "stream": False, "messages": [*follow["messages"], *rows]}


def interrupted_stream_tool_result(tool, callbacks):
    """执行合成便签查询。@param tool 客户端实际收到的调用。@param callbacks 已执行的调用 ID。
    @return 查询结果的公开回执块。
    """
    notes = {ARGS["key"]: (NEW_ID, ARGS, REPLY), SECOND_ARGS["key"]: (RECONNECT_ID, SECOND_ARGS, SECOND_REPLY)}
    call_id, args, note = notes[tool["input"]["key"]]
    assert tool["name"] == TOOL["name"] and tool["id"] == call_id and tool["input"] == args
    assert call_id not in callbacks
    callbacks.append(call_id)
    return {"type": "tool_result", "tool_use_id": call_id, "content": note}


def verify_interrupted_tool_stream(manage, temporary, token, headers, follow, received, callbacks,
                                   finish_stream, continue_tool_stream, initial_request_id, restart_sender, sender_status,
                                   *, after_tool_start, retry):
    """验证已开始交付的流丢失后，仅用原工具回执恢复一次。
    @param manage 管理入口。@param temporary 本次数据库目录。@param token 调用方。
    @param headers 原公开会话。@param follow 原回执。
    @param received 隔离模型实收。@param callbacks 已执行的客户端工具。
    @param finish_stream 允许隔离模型截断响应。@param continue_tool_stream 放行替代流尾段。
    @param initial_request_id 首轮公开请求。
    @param restart_sender 等原轮释放后重启 sender。@param sender_status 失败后读取 sender。
    @param after_tool_start 是否已交付下一工具编号及半段参数。
    @param retry 恢复时提交的原回执或其等价表示。
    @return 中断、恢复、后续工具及用量证据。
    """
    marker = ("--name=" + headers["x-session-id"]).encode()
    (cli,) = [path for path in Path("/proc").glob("[0-9]*/cmdline") if fixture_command_has(path, marker)]
    (binding,) = Path("/native/tui-workspaces").glob("*.json")
    saved_binding = binding.read_bytes()
    native_id = json.loads(saved_binding)["native_session_id"]
    project = Path("/native/tui-sessions") / native_id / "home/.claude/projects"
    (original_file,) = project.glob("*/" + native_id + ".jsonl")
    with closing(HTTPConnection("127.0.0.1", 18090, timeout=30)) as connection:
        connection.request("POST", "/v1/messages", encoded(follow), {
            "Authorization": "Bearer " + token, "Content-Type": "application/json",
            "anthropic-version": "2023-06-01", **headers,
        })
        with closing(connection.getresponse()) as response:
            interrupted_request_id = response.getheader("x-cc2api-request-id")
            assert response.status == 200 and interrupted_request_id
            lines = read_tool_stream_data_lines(response, 6 if after_tool_start else 3)
            original = [json.loads(line[5:]) for line in lines]
            assert [event["type"] for event in original[:3]] == ["message_start", "content_block_start", "content_block_delta"]
            text = RECONNECT_PREFIX if after_tool_start else INTERRUPTED_PREFIX
            assert original[2]["delta"] == {"type": "text_delta", "text": text}
            if after_tool_start:
                assert original[4]["content_block"] == {"type": "tool_use", "id": RECONNECT_ID,
                                                         "name": TOOL["name"], "input": {}}
                partial = original[5]["delta"]
                argument_prefix = partial["partial_json"]
                assert partial["type"] == "input_json_delta" and argument_prefix and not argument_prefix.endswith("}")
                assert encoded(SECOND_ARGS).decode().startswith(argument_prefix)
            assert len(received) == 2 and not finish_stream.is_set()
            startup_event("interrupted_tool_prefix", request_id=interrupted_request_id, data_frames=len(original),
                          model_posts=len(received), cli_pid=int(cli.parent.name))
            finish_stream.set()
            try:
                tail = response.read()
            except IncompleteRead as error:
                tail = error.partial
                transport_error = type(error).__name__
            else:
                raise AssertionError(("原续轮应在终帧前断开", interrupted_request_id, tail))
            (stream_error,) = [json.loads(line[5:]) for line in tail.splitlines() if line.startswith(b"data:")]
            assert stream_error["type"] == "error" and stream_error["error"]["type"] == "api_error", tail
    disconnected_at = monotonic()
    startup_event("interrupted_tool_response_lost", request_id=interrupted_request_id, transport_error=transport_error)
    if fixture_command_has(cli, marker):
        with suppress(ProcessLookupError):
            os.kill(int(cli.parent.name), SIGKILL)
    restart_sender()
    assert not cli.parent.exists() and len(received) == 2
    saved_history = original_file.read_bytes()
    sleep(max(0, 6 - (monotonic() - disconnected_at)))
    retry_wait_ms = round((monotonic() - disconnected_at) * 1000)

    def usage_rows(count):
        with closing(connect(temporary / "gateway.db")) as database:
            rows = database.execute(
                "SELECT record_id,input_tokens,output_tokens,partial FROM usage_records WHERE account_id=1 ORDER BY started_at"
            ).fetchall()
        return rows if len(rows) >= count else None

    def observe_attempt(request_id, origin, model_digest):
        reservation, record, (claim,) = cache_marker_claims(manage, request_id)
        detail = manage("GET", "request-diagnostics/" + request_id)
        (attempt,) = detail["attempts"]
        assert attempt["attempt_id"] == reservation and record["attempt_count"] == 1
        assert detail["request"]["context"]["tui_confirmed_model_responses"] == 1, record
        assert attempt["context"]["tui_session_origin"] == origin, attempt
        assert attempt["context"]["tui_body_source"] == "interactive_cli", attempt
        assert claim["from_interactive_cli"] and claim["uses_native_history"]
        assert claim["cli_sha256"] == claim["sha256"] == model_digest
        return {"request_id": request_id, "attempt_id": reservation, "session_origin": origin,
                "model_body_sha256": model_digest, "retry_reason": attempt.get("retry_reason"),
                "outcome": record.get("outcome"), "error_stage": record.get("error_stage")}

    proof = {"interrupted_request_id": interrupted_request_id, "interrupted_message_id": original[0]["message"]["id"],
             "interrupted_frames": len(original), "interrupted_transport_error": transport_error,
             "interrupted_stream_error": stream_error["error"]["type"], "retry_wait_ms": retry_wait_ms,
             "receipt_body_sha256": sha256(encoded(follow)).hexdigest(), "wire_final": "unavailable"}
    def observe_interruption():
        attempt = observe_attempt(interrupted_request_id, "live_process", received[1][0])
        assert (attempt["outcome"], attempt["error_stage"]) == ("body_error", "upstream_body"), attempt
        return attempt

    if after_tool_start:
        rejections = []
        for phase in ("interrupted_outstanding_tool", "interrupted_outstanding_tool_repeat"):
            status, raw, request_id = checked_messages(
                manage, token, follow, headers, received, phase, expected_status=409, trace_startup=True,
                sender_status=sender_status,
            )
            error_code = json.loads(raw)["error"]["code"]
            detail = manage("GET", "request-diagnostics/" + request_id)
            assert error_code == "outstanding_tool" and not detail["attempts"]
            reservation = detail["request"]["context"]["tui_reservation_id"]
            rejections.append({"request_id": request_id, "reservation_id": reservation,
                               "status": status, "error_code": error_code,
                               "attempt_count": len(detail["attempts"])})
        assert rejections[0]["request_id"] != rejections[1]["request_id"]
        assert len(received) == 2 and callbacks == [NEW_ID]
        assert original_file.read_bytes() == saved_history and binding.read_bytes() == saved_binding
        usage = wait_for(lambda: usage_rows(2))
        assert [row[1:] for row in usage] == [(10, 8, 0), (INTERRUPTED_USAGE[0], 1, 1)], usage
        return {**proof, "model_posts": len(received), "client_tool_calls": callbacks, "usage_records": usage,
                "next_tool_id": original[4]["content_block"]["id"], "retry_rejections": rejections,
                "partial_argument_chars": len(argument_prefix),
                "attempts": [observe_attempt(initial_request_id, "external_import", received[0][0]), observe_interruption()],
                "original_history_preserved": True, "binding_preserved": True}
    first_prefix = Event()

    def read_retry(phase, prefix_read):
        prefix = []

        def hold(response):
            if response.status == 200:
                prefix.extend(read_tool_stream_data_lines(response, 3))
                prefix_read.set()

        _, tail, request_id = checked_messages(
            manage, token, retry, headers, received, phase, trace_startup=True,
            sender_status=sender_status, observe_response=hold,
        )
        return prefix + [line for line in tail.splitlines(keepends=True) if line.startswith(b"data:")], request_id

    with ThreadPoolExecutor(max_workers=1) as readers:
        pending = readers.submit(read_retry, "interrupted_tool_retry", first_prefix)
        try:
            # 两位读者都看见替代流的前缀后才放行余下工具参数和终帧。
            assert first_prefix.wait(30), "恢复请求未交付替代流前缀"
            assert len(received) == 3 and not continue_tool_stream.is_set()
            shared_lines, shared_id = read_retry("interrupted_tool_concurrent_reader", continue_tool_stream)
        finally:
            continue_tool_stream.set()
        lines, retry_id = pending.result()
    assert lines == shared_lines and retry_id != shared_id
    assert len(received) == 3 and original_file.read_bytes() == saved_history and binding.read_bytes() == saved_binding
    events = [json.loads(line[5:]) for line in lines]
    assert len(events) == 10 and events[-1]["type"] == "message_stop", events
    message_id = events[0]["message"]["id"]
    assert message_id != original[0]["message"]["id"] and events[2]["delta"]["text"] == RECONNECT_PREFIX
    start = events[4]["content_block"]
    assert start == {"type": "tool_use", "id": RECONNECT_ID, "name": TOOL["name"], "input": {}}, events
    tool = {**start, "input": json.loads("".join(event["delta"]["partial_json"] for event in events[5:7]))}
    assert tool["input"] == SECOND_ARGS and events[-2]["delta"]["stop_reason"] == "tool_use"
    assert callbacks == [NEW_ID]
    current_request = next_tool_stream_receipt(retry, tool, result=interrupted_stream_tool_result(tool, callbacks))
    _, final, next_id = checked_messages(
        manage, token, current_request, headers, received, "interrupted_tool_next_receipt",
        trace_startup=True, sender_status=sender_status,
    )
    final_message = json.loads(final)
    assert final_message["stop_reason"] == "end_turn" and final_message["content"] == [{"type": "text", "text": FINAL}]
    assert len(received) == 4 and callbacks == [NEW_ID, RECONNECT_ID]
    for _, model, _ in received[1:3]:
        ((role, original_receipt),) = find_blocks(model, "tool_use_id", NEW_ID)
        assert role == "user" and original_receipt["content"].count(REPLY) == 1
    ((role, next_receipt),) = find_blocks(received[-1][1], "tool_use_id", RECONNECT_ID)
    assert role == "user" and next_receipt["content"].count(SECOND_REPLY) == 1
    stale, _, stale_id = checked_messages(
        manage, token, follow, headers, received, "interrupted_tool_stale_receipt", expected_status=400,
        trace_startup=True, sender_status=sender_status,
    )
    assert len(received) == 4

    usage = wait_for(lambda: usage_rows(4))
    assert [row[1:] for row in usage] == [(10, 8, 0), (*INTERRUPTED_USAGE, 1), (*REGENERATED_USAGE, 0), (10, 8, 0)], usage
    attempts = [
        observe_attempt(initial_request_id, "external_import", received[0][0]),
        observe_interruption(),
        observe_attempt(retry_id, "disk_resume", received[2][0]),
        observe_attempt(next_id, "live_process", received[3][0]),
    ]
    assert attempts[2]["retry_reason"] == "tui_reconnect_regenerated", attempts[2]
    shared = manage("GET", "request-diagnostics/" + shared_id)
    assert not shared["attempts"] and shared["request"]["outcome"] == "tui_reconnect_stream", shared
    assert not manage("GET", "request-diagnostics/" + stale_id)["attempts"]
    return {**proof, "model_posts": len(received), "client_tool_calls": callbacks, "usage_records": usage,
            "regenerated_message_id": message_id, "regenerated_frames": len(events),
            "concurrent_reader_request_id": shared_id, "concurrent_reader_attempts": len(shared["attempts"]),
            "regenerated_tool_id": tool["id"], "stale_receipt_status": stale, "stale_receipt_request_id": stale_id,
            "original_history_preserved": True, "binding_preserved": True,
            "attempts": attempts}


def verify_connected_slow_tool_stream(manage, temporary, token, account_token, headers, follow, received, callbacks,
                                      continue_tool_stream, finish_stream, model_finished, initial_request_id, sender_status):
    """慢读同一个公开续轮响应，核对实际交付和记账。
    @param manage 管理入口。@param temporary 隔离数据库目录。@param token 合成调用方。
    @param account_token 合成账号凭据。@param headers 原请求会话。@param follow 原工具回执。
    @param received 隔离模型实收。@param callbacks 合成工具执行记录。
    @param continue_tool_stream 放行参数余段。@param finish_stream 放行终帧。
    @param model_finished 隔离模型已写出终帧。@param initial_request_id 根轮公开请求。
    @param sender_status 失败后读取发送器。@return 慢读、模型和用量证据。
    """
    def usage_rows(count):
        with closing(connect(temporary / "gateway.db")) as database:
            rows = database.execute(
                "SELECT record_id,input_tokens,output_tokens,partial FROM usage_records WHERE account_id=1 ORDER BY started_at"
            ).fetchall()
        return rows if len(rows) >= count else None

    (first_usage,) = wait_for(lambda: usage_rows(1))
    assert first_usage[1:] == (10, 8, 0), first_usage
    prefix, pause = [], {}

    def hold_reader(response):
        if response.status != 200:
            return
        request_id = response.getheader("x-cc2api-request-id")
        prefix.extend(read_tool_stream_data_lines(response, 6))
        assert len(received) == 2 and not response.isclosed()
        assert not continue_tool_stream.is_set() and not finish_stream.is_set() and not model_finished.is_set()
        startup_event("slow_reader_prefix", request_id=request_id, data_frames=len(prefix))
        continue_tool_stream.set()
        finish_stream.set()
        assert model_finished.wait(30), "隔离模型未写出终帧"
        completed = monotonic()
        sleep(SLOW_READER_PAUSE_SECONDS)
        assert not response.isclosed() and len(received) == 2
        pause["after_model_finish_ms"] = round((monotonic() - completed) * 1000)
        startup_event("slow_reader_resuming", request_id=request_id, **pause)

    _, wire, request_id = checked_messages(
        manage, token, follow, headers, received, "slow_connected_reader", trace_startup=True,
        sender_status=sender_status, observe_response=hold_reader,
    )
    data = [*prefix, *(line for line in wire.splitlines(keepends=True) if line.startswith(b"data:"))]
    observed = [json.loads(line[5:]) for line in data]
    expected = [json.loads(line[5:]) for part in fixture_reconnect_sse(NATIVE_TOOL_NAME, usage=SLOW_READER_USAGE)
                for line in part.splitlines() if line.startswith(b"data:")]
    # 公开消息 ID 在首帧分配。其余模型数据只应用既有工具名映射。
    message_id = json.loads(prefix[0][5:])["message"]["id"]
    assert UUID(message_id.removeprefix("msg_")).version == 4
    expected[0]["message"]["id"] = message_id
    expected[4]["content_block"]["name"] = TOOL["name"]
    assert observed == expected, observed
    assert pause["after_model_finish_ms"] >= SLOW_READER_PAUSE_SECONDS * 1000
    assert len(received) == 2

    initial_usage, slow_usage = wait_for(lambda: usage_rows(2))
    assert initial_usage == first_usage and slow_usage[1:] == (*SLOW_READER_USAGE, 0), slow_usage
    tool = {**observed[4]["content_block"], "input": json.loads(
        observed[5]["delta"]["partial_json"] + observed[6]["delta"]["partial_json"]
    )}
    callbacks.append(tool["id"])
    assert callbacks == [NEW_ID, RECONNECT_ID] and tool["input"] == SECOND_ARGS
    _, final, next_id = checked_messages(
        manage, token, next_tool_stream_receipt(follow, tool), headers, received, "slow_reader_next_receipt",
        trace_startup=True, sender_status=sender_status,
    )
    assert len(received) == 3 and json.loads(final)["content"] == [{"type": "text", "text": FINAL}]
    (role, result), = find_blocks(received[-1][1], "tool_use_id", RECONNECT_ID)
    assert role == "user" and result["content"].count(SECOND_REPLY) == 1
    duplicate, _, _ = checked_messages(
        manage, token, follow, headers, received, "slow_reader_stale_receipt", expected_status=400,
        trace_startup=True, sender_status=sender_status,
    )
    assert len(received) == 3
    usage = wait_for(lambda: usage_rows(3))
    assert usage[:2] == [first_usage, slow_usage] and len(usage) == 3 and usage[2][1:] == (10, 8, 0), usage
    captures = verify_captures(manage, received, account_token)
    assert [attempt["request_id"] for attempt in captures] == [initial_request_id, request_id, next_id]
    assert all(attempt["confirmed_model_responses"] == 1 for attempt in captures), captures
    detail = manage("GET", "request-diagnostics/" + request_id)
    assert detail["request"]["outcome"] == "success" and len(detail["attempts"]) == 1, detail
    assert detail["attempts"][0]["attempt_id"] == captures[1]["attempt_id"], detail
    return {"connected_reader_request_id": request_id, "model_message_id": RECONNECT_MESSAGE_ID,
            "public_message_id": message_id, "tool_id": tool["id"], "tool_input": tool["input"],
            "data_frames": len(data), "data_sha256": sha256(b"".join(data)).hexdigest(), **pause,
            "model_posts_during_slow_receipt": 1, "model_posts": len(received), "usage_records": usage,
            "client_tool_calls": callbacks, "old_tool_calls": 0, "stale_receipt_status": duplicate, "attempts": captures}


def verify_tool_stream_reconnect(manage, temporary, token, account_token, headers, follow,
                                 received, continue_tool_stream, finish_stream, callbacks, *, replay):
    """断开真实续轮读者，再读取同一次交付。@param manage 管理入口。@param temporary 本次私有数据库目录。
    @param token 合成调用方。@param account_token 合成模型凭据。@param headers 原请求会话。
    @param follow 同一公开工具回执。@param received 模型实收。
    @param continue_tool_stream 放行余下参数。@param finish_stream 放行终帧。
    @param callbacks 客户端已执行的合成工具。@param replay 重连时提交的等价回执。@return 实测证据。
    """
    def disconnect_after_prefix(previous=None):
        with closing(HTTPConnection("127.0.0.1", 18090, timeout=30)) as connection:
            connection.request("POST", "/v1/messages", encoded(follow if previous is None else replay), {
                "Authorization": "Bearer " + token, "Content-Type": "application/json",
                "anthropic-version": "2023-06-01", **headers,
            })
            with closing(connection.getresponse()) as response:
                assert response.status == 200, response.status
                lines = read_tool_stream_data_lines(response, 6)
                assert len(received) == 2 and not continue_tool_stream.is_set() and not finish_stream.is_set()
                if previous is not None:
                    # 第二个读者先收到原始前缀，再允许模型向同一条打开的连接交付新参数。
                    assert lines == previous
                    continue_tool_stream.set()
                    lines.extend(read_tool_stream_data_lines(response, 1))
                    assert not finish_stream.is_set()
                connection.sock.shutdown(SHUT_RDWR)
                return lines, response.getheader("x-cc2api-request-id")

    original_lines, original_request_id = disconnect_after_prefix()
    original_model_posts = len(received)
    original = [json.loads(line[5:]) for line in original_lines]
    assert [event["type"] for event in original] == [
        "message_start", "content_block_start", "content_block_delta", "content_block_stop",
        "content_block_start", "content_block_delta",
    ]
    assert original[2]["delta"]["text"] == RECONNECT_PREFIX
    tool_start, first_delta = original[-2:]
    assert tool_start["index"] == first_delta["index"] == 1
    assert tool_start["content_block"] == {"type": "tool_use", "id": RECONNECT_ID, "name": TOOL["name"], "input": {}}
    assert first_delta["delta"]["type"] == "input_json_delta"
    partial = first_delta["delta"]["partial_json"]
    assert partial and not partial.endswith("}")

    disconnected_at = monotonic()
    sleep(6)
    live_lines, live_request_id = disconnect_after_prefix(original_lines)
    live_wait_and_read_ms = round((monotonic() - disconnected_at) * 1000)
    live_model_posts = len(received)
    assert live_model_posts == 2
    second_delta = json.loads(live_lines[-1][5:])
    assert second_delta["type"] == "content_block_delta" and second_delta["index"] == tool_start["index"]
    assert second_delta["delta"]["type"] == "input_json_delta"
    remaining = second_delta["delta"]["partial_json"]
    assert remaining
    tool = {**tool_start["content_block"], "input": json.loads(partial + remaining)}
    assert tool["input"] == SECOND_ARGS
    # 终帧只在打开的第二条连接读到新增参数并断开后放行，第三个读者从缓存接回。
    finish_stream.set()
    with closing(connect(temporary / "gateway.db")) as database:
        wait_for(lambda: database.execute("SELECT count(*) FROM tui_native_turns WHERE tools=?",
                                         (encoded([RECONNECT_ID]).decode(),)).fetchone()[0] == 1)
    _, wire, cached_request_id = checked_messages(manage, token, replay, headers, received, "reconnect_cached")
    cached_model_posts = len(received)
    assert cached_model_posts == 2, cached_model_posts
    reader_ids = [original_request_id, live_request_id, cached_request_id]
    assert all(reader_ids) and len(set(reader_ids)) == 3
    cached_lines = [line for line in wire.splitlines(keepends=True) if line.startswith(b"data:")]
    assert len(cached_lines) == 10 and cached_lines[:len(live_lines)] == live_lines
    assert [json.loads(line[5:])["type"] for line in cached_lines[len(live_lines):]] == [
        "content_block_stop", "message_delta", "message_stop",
    ]
    callbacks.append(RECONNECT_ID)
    assert callbacks == [NEW_ID, RECONNECT_ID]

    next_request = next_tool_stream_receipt(follow, tool)
    status, raw = call(18090, "POST", "/v1/messages", token, next_request, headers)
    assert status == 200 and len(received) == 3, (status, raw, len(received))
    assert json.loads(raw)["content"] == [{"type": "text", "text": FINAL}]
    (role, result), = find_blocks(received[-1][1], "tool_use_id", RECONNECT_ID)
    assert role == "user" and result["content"].count(SECOND_REPLY) == 1
    duplicate, response = call(18090, "POST", "/v1/messages", token, replay, headers)
    assert duplicate == 400 and len(received) == 3, (duplicate, response, len(received))

    def replay_diagnostics():
        rows = {row["request_id"]: row for row in manage("GET", "request-diagnostics")["items"]}
        if all(request_id in rows for request_id in reader_ids):
            readers = [rows[request_id] for request_id in reader_ids]
            if [row.get("outcome") for row in readers] == ["cancelled", "cancelled", "tui_reconnect_cached"]:
                return readers

    attempt_counts = [row["attempt_count"] for row in wait_for(replay_diagnostics)]
    assert attempt_counts == [1, 0, 0], attempt_counts
    return {"disconnect_before_model_finished": True, "retry_after_seconds": 6,
            "replayed_message_id": original[0]["message"]["id"], "replayed_tool_id": RECONNECT_ID,
            "live_replay_disconnected": True, "cached_replay_request_id": cached_request_id,
            "reader_data_frames": [len(original_lines), len(live_lines), len(cached_lines)],
            "reader_request_ids": reader_ids, "reader_attempt_counts": attempt_counts,
            "model_posts_after_each_reader": [original_model_posts, live_model_posts, cached_model_posts],
            "live_wait_and_read_ms": live_wait_and_read_ms,
            "live_prefix_data_sha256": sha256(b"".join(live_lines)).hexdigest(), "next_receipt_status": status,
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
    beta = ("mid-conversation-system-2026-04-07", "per-turn-control-2026-07-01", SYSTEM_CLEAR_AT_BETA)
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
            model_system = blocks({"content": model_body.get("system", [])})
            if fixed:
                marker = root["text"]
                occurrences = {
                    "system_header": sum(block["text"].count(marker) for block in model_system if block["type"] == "text"),
                    "user": 0,
                    "other_messages": 0,
                }
                for row in model_body["messages"]:
                    location = "user" if row["role"] == "user" else "other_messages"
                    occurrences[location] += sum(block["text"].count(marker) for block in blocks(row)
                                                 if block["type"] == "text")
                expected_location = "user" if policy == "user_reminder" else "system_header"
                expected_occurrences = dict.fromkeys(occurrences, 0)
                if "system" in body:
                    expected_occurrences[expected_location] = 1
                assert occurrences == expected_occurrences, (label, occurrences, expected_occurrences)
                result["root_text_occurrences"] = occurrences
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


def message_system_betas(body):
    """按隔离模型的协议检查求必需 beta。@param body 模型实收。@return 所需声明集合。"""
    required = set()
    for row in body["messages"]:
        if row["role"] != "system":
            continue
        if row.get("clear_at") is not None:
            required.add(SYSTEM_CLEAR_AT_BETA)
        if "effort" in (row.get("output_config") or {}):
            required.add(SYSTEM_EFFORT_BETA)
    return required


def verify_system_controls(manage, token, account, received, model_betas, *, per_message_effort):
    """核对普通请求的消息级控制和原工具回执。@param manage 管理 API。@param token 合成凭据。
    @param account 当前账号。@param received 模型实收。@param model_betas 模型协议头。
    @param per_message_effort 是否运行消息级推理强度用例。@return 逐请求证据。
    """
    manage("PUT", "settings", {"message_cache_control_rewrite": "off", "cache_control_ttl_rewrite": "off"})
    cases = {}
    user = {"role": "user", "content": QUESTION}
    scoped = {"role": "system", "content": "为本轮合成便签保留原系统指令。", "clear_at": "next_user_message"}
    model = "claude-opus-5-5"
    base = {"model": model, "max_tokens": 128, "stream": False, "system": SYSTEM[0]}
    if per_message_effort:
        base["output_config"] = {"effort": "high"}
    unrelated = "mid-conversation-system-2026-04-07"

    def headers():
        return {"User-Agent": "flower2api-turn-scoped-system/1", "x-session-id": str(uuid4())}

    def post(label, body, model_headers, *, expected_status=200, expected_stop="end_turn"):
        before = len(received)
        since = datetime.now(timezone.utc).isoformat(timespec="milliseconds")
        status, raw, request_id = checked_messages(
            manage, token, body, model_headers, received, label, expected_status=expected_status, trace_startup=True,
        )
        records = report_request_diagnostics(manage, label, request_id, model_headers["x-session-id"], since)
        (record,) = records["requests"]
        reply = json.loads(raw)
        result = {"request_id": request_id, "http_status": status, "model_posts": len(received) - before,
                  "attempt_count": record["attempt_count"]}
        cases[label] = result
        if status != 200:
            assert (result["model_posts"], result["attempt_count"]) == (0, 0), result
            result["error_code"] = reply["error"].get("code")
            return reply
        assert reply["stop_reason"] == expected_stop, reply
        ((digest, actual, _),) = received[before:]
        assert actual["model"] == model and actual["messages"] == body["messages"] and actual["system"] == base["system"]
        assert actual.get("output_config") == body.get("output_config"), (label, actual.get("output_config"))
        tokens = [part.strip() for part in model_betas[-1].split(",") if part.strip()]
        required = message_system_betas(body)
        assert all(tokens.count(beta) == (beta in required) for beta in (SYSTEM_CLEAR_AT_BETA, SYSTEM_EFFORT_BETA)), (
            label, tokens,
        )
        supplied = model_headers.get("anthropic-beta")
        if supplied:
            assert tokens[:len(supplied.split(","))] == supplied.split(","), (label, supplied, tokens)
        (attempt,) = record["attempts"]
        reservation = record["diagnostic_context"]["tui_reservation_id"]
        assert attempt["attempt_id"] == reservation and attempt["request_id"] == request_id
        context = attempt["diagnostic_context"]
        assert context["tui_body_source"] == "account_sender"
        assert result["attempt_count"] == record["diagnostic_context"]["tui_confirmed_model_responses"] == 1
        result.update(reservation_id=reservation, model_body_sha256=digest, model_betas=tokens,
                      session_origin=context["tui_session_origin"],
                      output_config=actual.get("output_config"),
                      model_system_rows=[row for row in actual["messages"] if row["role"] == "system"])
        return reply

    effort = {"role": "system", "content": [], "output_config": {"effort": "low"}}
    setting = effort if per_message_effort else scoped
    history = [user, scoped, {"role": "assistant", "content": "已记下合成便签。"},
               {"role": "user", "content": "继续读回历史便签。"}]
    plain = {"role": "system", "content": scoped["content"]}
    if per_message_effort:
        # 已完成的历史与新用户问之间放置原位控制。根 effort 保持 high。
        effort_history = [history[0], history[2], effort, history[3]]
        post("implicit_effort_history", {**base, "messages": effort_history}, headers())
        current = {**base, "messages": [user, effort]}
        post("effort_with_other_beta", current, {**headers(), "anthropic-beta": unrelated})
        post("explicit_effort_beta", current, {**headers(), "anthropic-beta": unrelated + "," + SYSTEM_EFFORT_BETA})
        post("root_effort_only", {**base, "messages": [user, plain]}, headers())
        post("combined_clear_at_and_effort", {**base, "messages": [*history[:3], effort, history[-1]]}, headers())
    else:
        post("implicit_current", {**base, "messages": [user, scoped]}, headers())
        post("implicit_expired_history", {**base, "messages": history}, headers())
        post("explicit_never_with_other_beta", {**base, "messages": [user, {**scoped, "clear_at": "never"}]},
             {**headers(), "anthropic-beta": unrelated})
        post("explicit_beta", {**base, "messages": history},
             {**headers(), "anthropic-beta": unrelated + "," + SYSTEM_CLEAR_AT_BETA})
        post("without_clear_at", {**base, "messages": [user, plain]}, headers())
    post("unlisted_model", {**base, "model": MODEL, "messages": [user, setting]}, headers(), expected_status=400)
    assert cases["unlisted_model"]["error_code"] == "system_role_model_not_allowed"

    session = headers()
    first = {**base, "messages": [user, setting], "tools": [TOOL]}
    reply = post("tool_initial", first, session, expected_stop="tool_use")
    (tool,) = reply["content"]
    assert (tool["id"], tool["name"], tool["input"]) == (NEW_ID, TOOL["name"], ARGS)
    result = {"type": "tool_result", "tool_use_id": tool["id"], "content": REPLY}
    follow = {**first, "messages": [*first["messages"], {"role": "assistant", "content": [tool]},
                                    {"role": "user", "content": [result]}]}
    if not per_message_effort:
        follow["messages"].append({**scoped, "content": "读完原回执后只回答合成问题。"})
    post("tool_receipt", follow, session)
    cases["tool_receipt"]["tool_use_id"] = tool["id"]
    assert cases["tool_receipt"]["session_origin"] == "live_process"
    post("duplicate_receipt", follow, session, expected_status=400)

    for policy in ("replace", "user_reminder"):
        updated = manage("PUT", f"accounts/{account['id']}", {"client_system_prompt_policy": policy})
        assert updated["client_system_prompt_policy"] == policy
        post(policy, {**base, "messages": [user, setting]}, headers(), expected_status=422)
        assert cases[policy]["error_code"] == "unsupported_parameter"
    assert len(received) == len(model_betas) == 7
    return {"cases": cases, "model_posts": len(received), "wire_final": "unavailable"}


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
    # 按公开流的顺序核对块边界，避免把落在块外的增量单独验为成功。
    order = [
        (event["type"], event.get("index")) for event in frames
        if event["type"] in ("message_start", "content_block_start", "content_block_delta",
                             "content_block_stop", "message_delta", "message_stop")
    ]
    thinking_deltas = [("content_block_delta", 0)] * (2 if summary else 1)
    assert order == [
        ("message_start", None),
        ("content_block_start", 0), *thinking_deltas, ("content_block_stop", 0),
        ("content_block_start", 1), ("content_block_delta", 1), ("content_block_stop", 1),
        ("message_delta", None), ("message_stop", None),
    ], order
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


def verify_provider_quota(manage, token, identifier, received, quota_windows, sender_status, *, stream):
    """核对真实模型的 429 与账户被动额度。
    @param manage 管理入口。@param token 调用方。@param identifier 合成账号。
    @param received 模型实收。@param quota_windows 合成窗口重置秒。
    @param sender_status 失败后读取发送器。@param stream 是否以 SSE 请求。@return 脱敏证据。
    """
    windows = {"five_hour": "5h", "seven_day": "7d", "seven_day_fable": "7d_oi"}
    expected = {"allowed": {"five_hour": 25, "seven_day": 50, "seven_day_fable": 12.5},
                "rejected": {"five_hour": 100, "seven_day": 75, "seven_day_fable": 12.5}}
    cases = {}

    def observed_usage(values):
        view = manage("GET", f"accounts/{identifier}")
        usage = view["usage_data"]
        if any(usage.get(name, {}).get("utilization") != value for name, value in values.items()):
            return None
        return {name: usage[name] for name in values}

    for phase, question in QUOTA_QUESTIONS.items():
        request_body = {"model": MODEL, "max_tokens": 128, "messages": [{"role": "user", "content": question}],
                        "stream": stream, "system": SYSTEM[0]}
        headers = {"User-Agent": "flower2api-passive-quota-fixture/1", "x-session-id": str(uuid4())}
        public_headers = {}

        def observe(response):
            public_headers["retry_after"] = response.getheader("Retry-After")
            public_headers["content_type"] = response.headers.get_content_type()

        before = len(received)
        allowed = phase == "allowed"
        status, raw, request_id = checked_messages(
            manage, token, request_body, headers, received, "quota_" + phase, expected_status=200 if allowed else 429,
            trace_startup=True, sender_status=sender_status, observe_response=observe,
        )
        if allowed and stream:
            frames = [json.loads(line[5:]) for line in raw.splitlines() if line.startswith(b"data:")]
            assert frames[-1]["type"] == "message_stop"
            assert "".join(event["delta"]["text"] for event in frames if event["type"] == "content_block_delta") == FINAL
        elif allowed:
            assert json.loads(raw)["content"] == [{"type": "text", "text": FINAL}], raw
        else:
            assert json.loads(raw) == QUOTA_REJECTION, raw
        assert public_headers["retry_after"] == (None if allowed else str(QUOTA_RETRY_SECONDS)), public_headers
        assert public_headers["content_type"] == ("text/event-stream" if allowed and stream else "application/json")
        reservation, record, claims = cache_marker_claims(manage, request_id)
        ((digest, model, _),), (claim,) = received[before:], claims
        detail = manage("GET", "request-diagnostics/" + request_id)
        (attempt,) = detail["attempts"]
        confirmed = detail["request"]["context"]["tui_confirmed_model_responses"]
        assert record["attempt_count"] == confirmed == 1 and attempt["attempt_id"] == reservation, detail
        assert attempt["status_code"] == status, attempt
        assert attempt["outcome"] == ("success" if allowed else "upstream_rejected"), attempt
        assert attempt.get("error_stage") == (None if allowed else "upstream_headers"), attempt
        assert claim["from_interactive_cli"] and claim["uses_native_history"] and claim["cli_sha256"] == claim["sha256"] == digest
        assert sum(b.get("text") == question for row in model["messages"] if row["role"] == "user" for b in blocks(row)) == 1
        usage = wait_for(lambda: observed_usage(expected[phase]))
        assert all(int(datetime.fromisoformat(window["resets_at"]).timestamp()) == quota_windows[windows[name]]
                   for name, window in usage.items()), usage
        cases[phase] = {"status": status, "request_id": request_id, "reservation_id": reservation,
                        "model_posts": 1, "attempt_count": record["attempt_count"], "confirmed_model_responses": confirmed,
                        "provider_path": "interactive_cli", "model_body_sha256": digest, "cli_body_sha256": claim["cli_sha256"],
                        "input_body_sha256": sha256(encoded(request_body)).hexdigest(),
                        "attempt_outcome": attempt["outcome"], "attempt_error_stage": attempt.get("error_stage"),
                        "passive_usage": usage, **public_headers}
    assert len(received) == 2 and not any(path.is_file() for path in Path("/flows/api").rglob("*"))
    return {"cases": cases, "stream": stream, "model_posts": len(received), "wire_final": "unavailable"}


def external_signed_responses(stack, old_call):
    """从独立回环模型响应读取公开签名和模型身份。@param stack 夹具生命周期。
    @param old_call 原外部工具。@return 两个实际读取的响应。
    """
    model = "claude-opus-5-5"
    content = {"thinking": SIGNED_THINKING, "redacted_thinking": EXTERNAL_REDACTED_THINKING}
    requests = []

    class Origin(QuietHandler):
        """为普通客户端生成独立于候选账号的合成历史响应。"""

        def do_POST(self):
            """接收公开 Messages 形状的来源请求并返回签名工具。@return 无。"""
            payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            variant = payload["messages"][0]["content"]
            assert self.path == "/v1/messages" and payload["model"] == model and variant in content
            requests.append(variant)
            response_json(self, {"type": "message", "role": "assistant", "id": f"msg_external_{variant}",
                                 "model": model, "content": [content[variant], old_call], "stop_reason": "tool_use",
                                 "usage": {"input_tokens": 12, "output_tokens": 8}})

    server = serve(stack, ThreadingHTTPServer(("127.0.0.1", 0), Origin))
    response = {}
    for variant in content:
        status, raw = call(server.server_port, "POST", "/v1/messages", "fixture-external-origin", {
            "model": model, "max_tokens": 128, "messages": [{"role": "user", "content": variant}],
            "tools": [{**TOOL, "name": old_call["name"]}],
        })
        body = json.loads(raw)
        assert status == 200 and body["role"] == "assistant" and body["model"] == model
        assert body["content"] == [content[variant], old_call]
        response[variant] = body
    assert requests == list(content)
    return response


def _external_history_tool_result(model, expected, phase):
    (role, observed), = find_blocks(model, "tool_use_id", expected["tool_use_id"])
    assert role == "user" and same_json_value(observed, expected), (phase, role, observed)
    return observed


def verify_external_signed_history(manage, token, identifier, received, sender_status, *, origin_stack=None):
    """核对外部签名历史的模型实收、调用与结果归属，以及本轮公开终态。
    @param manage 管理入口。@param token 合成调用方。@param identifier 合成账号。
    @param received 隔离模型实收。@param sender_status 失败后读取 sender。
    @param origin_stack 可选，启用独立回环模型来源。@return 按请求关联的证据。
    """
    question = "请直接确认这条合成历史。"
    old_call = {"type": "tool_use", "id": PAST_ID, "name": "PreviousNote", "input": ARGS}
    old_result = {"type": "tool_result", "tool_use_id": PAST_ID, "is_error": True, "content": "合成历史错误。\n第二行。"}
    origins = external_signed_responses(origin_stack, old_call) if origin_stack is not None else {}
    variants = []
    for label, signature in (("unsigned", None), ("thinking", SIGNED_THINKING),
                             ("redacted_thinking", EXTERNAL_REDACTED_THINKING)):
        if not origins:
            variants.append((label, {"role": "assistant", "content": [signature, old_call] if signature else [old_call]}))
        elif label in origins:
            origin = origins[label]
            row = {"role": origin["role"], "content": origin["content"]}
            variants.extend(((label, row), (label + "_model", {**row, "model": origin["model"]}),
                             (label + "_response_metadata", {**row, **{field: origin[field] for field in ("id", "model", "usage")}})))
    cases = {}
    for policy in ("append", "replace", "user_reminder"):
        account = manage("PUT", f"accounts/{identifier}", {"client_system_prompt_policy": policy})
        assert account["client_system_prompt_policy"] == policy
        for label, assistant in variants:
            blocks_before_result = assistant["content"]
            signature = blocks_before_result[0] if len(blocks_before_result) == 2 else None
            body = {"model": MODEL, "max_tokens": 128, "system": SYSTEM[0], "stream": False, "messages": [
                {"role": "user", "content": "先查询旧合成便签。"},
                assistant,
                {"role": "user", "content": [old_result]},
                {"role": "assistant", "content": "旧合成便签查询已经结束。"},
                {"role": "user", "content": question},
            ]}
            headers = {"User-Agent": "flower2api-external-history-fixture/1", "x-session-id": str(uuid4())}
            phase = f"external_signature_{policy}_{label}"
            supported_row = assistant.keys() == {"role", "content"}
            expected = 200 if supported_row and (signature is None or policy == "append") else 422
            before = len(received)
            status, raw, request_id = checked_messages(
                manage, token, body, headers, received, phase, expected_status=expected, trace_startup=True,
                sender_status=sender_status,
            )
            reservation, record, claims = cache_marker_claims(manage, request_id)
            attempts = manage("GET", "request-diagnostics/" + request_id)["attempts"]
            reply = json.loads(raw)
            case = {"http_status": status, "request_id": request_id, "reservation_id": reservation,
                    "model_posts": len(received) - before, "attempt_count": record["attempt_count"],
                    "ingress_body_sha256": sha256(encoded(body)).hexdigest()}
            cases[phase] = case
            if expected == 422:
                assert reply["error"]["code"] == "unsupported_parameter", (phase, reply)
                assert not (claims or attempts or case["attempt_count"] or case["model_posts"]), (phase, case)
                case["error_code"] = reply["error"]["code"]
                continue
            ((digest, model, _),), (claim,), (attempt,) = received[before:], claims, attempts
            from_cli = signature is None
            source = "interactive_cli" if from_cli else "account_sender"
            assert case["attempt_count"] == case["model_posts"] == 1 and attempt["attempt_id"] == reservation
            assert attempt["context"]["tui_body_source"] == source, (phase, attempt)
            assert claim["from_interactive_cli"] is claim["uses_native_history"] is from_cli, (phase, claim)
            assert claim["sha256"] == digest and claim["cli_sha256"], (phase, claim)
            assert (claim["cli_sha256"] == digest) is from_cli, (phase, claim)
            assert find_blocks(model, "id", PAST_ID) == [("assistant", old_call)]
            observed_result = _external_history_tool_result(model, old_result, phase)
            (old_turn,) = [blocks(row) for row in model["messages"] if any(b.get("id") == PAST_ID for b in blocks(row))]
            assert [block for block in old_turn if block["type"] != "text"] == blocks_before_result, (phase, old_turn)
            signed_blocks = [(row["role"], block) for row in model["messages"] for block in blocks(row)
                             if block["type"] in ("thinking", "redacted_thinking")]
            assert signed_blocks == ([("assistant", signature)] if signature else []), (phase, signed_blocks)
            if origins:
                assert model["model"] == MODEL != origins[label]["model"]
                (model_row,) = [row for row in model["messages"] if any(b.get("id") == PAST_ID for b in blocks(row))]
                assert model_row == assistant
            texts = [b.get("text", "") for row in model["messages"] if row["role"] == "user" for b in blocks(row)]
            assert sum(text.count(question) for text in texts) == 1, (phase, texts)
            system = model["system"]
            system_texts = [system] if isinstance(system, str) else [block["text"] for block in system]
            reminder = policy == "user_reminder"
            assert sum(text.count(SYSTEM[0]) for text in texts) == int(reminder), (phase, texts)
            assert sum(text.count(SYSTEM[0]) for text in system_texts) == int(not reminder), (phase, system_texts)
            assert reply["stop_reason"] == "end_turn" and reply["content"] == [{"type": "text", "text": FINAL}]
            case.update(provider_path=source, model_body_sha256=digest, cli_body_sha256=claim["cli_sha256"],
                        observed_signed_blocks=signed_blocks, old_tool_id=PAST_ID, old_tool_result=observed_result,
                        client_stop_reason=reply["stop_reason"])
    assert len(received) == (2 if origins else 5) and not any(path.is_file() for path in Path("/flows/api").rglob("*"))
    proof = {"cases": cases, "model_posts": len(received), "wire_final": "unavailable"}
    if origins:
        proof["current_request_model"] = MODEL
        proof["external_responses"] = {label: {
            "message_id": origin["id"], "response_model": origin["model"],
            "content_sha256": sha256(encoded(origin["content"])).hexdigest(),
        } for label, origin in origins.items()}
    return proof


def verify_bound_signed_history(manage, token, foreign, headers, follow, reply, received, callbacks, account_token,
                                initial_id, old_receipt_id, mode, restart_sender, sender_status):
    """用已核对的原生签名工具组开启下一轮，再按原身份交回新回执。
    @param manage 管理入口。@param token 原主体。@param foreign 另一主体。@param headers 原会话。
    @param follow 原工具回执。@param reply 已完成的原轮响应。
    @param received 隔离模型收件。@param callbacks 已执行的工具。@param account_token 合成账号凭据。
    @param initial_id 原会话首轮。@param old_receipt_id 完成原工具的请求。@param mode 热续轮或恢复。
    @param restart_sender 在原 CLI 退出后重启。@param sender_status 失败后读取 sender。@return 逐轮证据。
    """
    wait_for(lambda: sender_status().get("idle"))
    (binding,) = Path("/native/tui-workspaces").glob("*.json")
    original_binding = binding.read_bytes()
    native_id = json.loads(original_binding)["native_session_id"]
    project = Path("/native/tui-sessions") / native_id / "home/.claude/projects"
    (archive,) = project.glob("*/" + native_id + ".jsonl")
    original_archive = archive.read_bytes()
    sources = [(record["message"].get("id"), record["message"].get("model"), block)
               for line in original_archive.splitlines() if (record := json.loads(line)).get("type") == "assistant"
               for block in blocks(record["message"])
               if block.get("signature") == SIGNED_THINKING["signature"] or block.get("id") == NEW_ID]
    assert len(sources) == 2 and {row[:2] for row in sources} == {("msg_cold_tool", follow["model"])}
    assert sources[0][2] == SIGNED_THINKING and sources[1][2]["id"] == NEW_ID
    new_body = {**follow, "messages": [
        *follow["messages"], {"role": "assistant", "content": reply["content"]},
        {"role": "user", "content": SIGNED_ARCHIVE_QUESTION},
    ]}
    tampered = deepcopy(new_body)
    ((_, altered_signature),) = find_blocks(tampered, "signature", SIGNED_THINKING["signature"])
    altered_signature["signature"] = "Y2hhbmdlZA=="
    changed_tool = deepcopy(new_body)
    ((_, original_tool),) = find_blocks(changed_tool, "id", NEW_ID)
    original_tool["input"]["key"] = "different-synthetic-note"
    rejections = {}
    for phase, caller, body, request_headers in (
        ("fresh_session", token, new_body, {**headers, "x-session-id": str(uuid4())}),
        ("foreign_subject", foreign, new_body, headers),
        ("changed_signature", token, tampered, headers),
        ("changed_tool", token, changed_tool, headers),
    ):
        status, raw, request_id = checked_messages(
            manage, caller, body, request_headers, received, "bound_signature_" + phase, expected_status=422,
            trace_startup=True, sender_status=sender_status,
        )
        assert json.loads(raw)["error"]["code"] == "unsupported_parameter" and len(received) == 2
        assert not manage("GET", "request-diagnostics/" + request_id)["attempts"]
        rejections[phase] = {"request_id": request_id, "http_status": status}
    _, raw, new_id = checked_messages(
        manage, token, new_body, headers, received, "bound_signature_new_question", trace_startup=True,
        sender_status=sender_status,
    )
    response = json.loads(raw)
    expected_tool = {"type": "tool_use", "id": SECOND_ID, "name": TOOL["name"], "input": SECOND_ARGS}
    signed = SIGNED_FORK_THINKING if mode == "fork" else SIGNED_THINKING
    assert response["stop_reason"] == "tool_use" and response["content"] == [signed, expected_tool]
    assert len(received) == 3 and callbacks == [NEW_ID]
    callbacks.append(expected_tool["id"])
    continuation = {**new_body, "messages": [
        *new_body["messages"], {"role": "assistant", "content": response["content"]},
        {"role": "user", "content": [{"type": "tool_result", "tool_use_id": SECOND_ID, "content": SECOND_REPLY}]},
    ]}
    if mode == "restart":
        marker = ("--name=" + headers["x-session-id"]).encode()
        (cli,) = [path for path in Path("/proc").glob("[0-9]*/cmdline") if fixture_command_has(path, marker)]
        os.kill(int(cli.parent.name), SIGKILL)
        restart_sender()
        assert not cli.parent.exists()
    _, raw, final_id = checked_messages(
        manage, token, continuation, headers, received, "bound_signature_receipt", trace_startup=True,
        sender_status=sender_status,
    )
    finished = json.loads(raw)
    assert finished["stop_reason"] == "end_turn" and len(received) == 4
    for signed_count, (_, model, _) in enumerate(received[2:], start=1):
        assert find_blocks(model, "id", NEW_ID) == [("assistant", {
            "type": "tool_use", "id": NEW_ID, "name": NATIVE_TOOL_NAME, "input": ARGS,
        })]
        assert find_blocks(model, "tool_use_id", NEW_ID) == [("user", {
            "type": "tool_result", "tool_use_id": NEW_ID, "content": REPLY,
        })]
        present = find_blocks(model, "type", "thinking")
        assert present == [("assistant", block) for block in (SIGNED_THINKING, signed)[:signed_count]]
    (role, new_result), = find_blocks(received[-1][1], "tool_use_id", SECOND_ID)
    assert role == "user" and new_result["content"].count(SECOND_REPLY) == 1
    duplicate, _ = call(18090, "POST", "/v1/messages", token, continuation, headers)
    assert duplicate == 400 and len(received) == 4
    assert archive.read_bytes() == original_archive and binding.read_bytes() == original_binding
    attempts = verify_captures(manage, received, account_token)
    assert [a["request_id"] for a in attempts] == [initial_id, old_receipt_id, new_id, final_id]
    assert all(a["diagnostic_body_source"] == "interactive_cli" for a in attempts)
    assert attempts[-1]["diagnostic_session_origin"] == ("disk_resume" if mode == "restart" else "live_process")
    if mode == "fork":
        return verify_signed_fork_history(
            manage, token, foreign, headers, continuation, finished, received, callbacks, account_token,
            binding, archive, attempts, restart_sender, sender_status,
        )
    return {"mode": mode, "source_model": sources[0][1], "source_message_id": sources[0][0],
            "source_tool_id": NEW_ID, "model_posts": len(received), "client_tool_calls": callbacks,
            "rejections": rejections, "original_history_preserved": True, "duplicate_status": duplicate,
            "attempts": attempts, "wire_final": "unavailable"}


def verify_signed_fork_history(manage, token, foreign, headers, continuation, finished, received, callbacks,
                               account_token, binding, primary, prior_attempts, restart_sender, sender_status):
    """恢复分叉产出的签名历史，并核对同项目相邻会话。
    @param manage 管理入口。@param token 原主体。@param foreign 另一主体。@param headers 原会话。
    @param continuation 完成分叉工具的公开输入。@param finished 完整响应。
    @param received 隔离模型收件。@param callbacks 已执行的工具。@param account_token 合成凭据。
    @param binding 原绑定。@param primary 主档。@param prior_attempts 原轮与分叉的实际尝试。
    @param restart_sender 重启原发送器。@param sender_status 读取发送器。@return 归属及恢复证据。
    """
    wait_for(lambda: sender_status().get("idle"))
    (branch,) = [path for path in primary.parent.glob("*.jsonl") if path != primary]
    archived = branch.read_bytes()
    source = [row["message"] for line in archived.splitlines()
              if (row := json.loads(line)).get("type") == "assistant"
              and row["message"].get("id") == "msg_bound_signed_fork"]
    assert len(source) == 2 and {row["model"] for row in source} == {continuation["model"]}
    assert [block for row in source for block in blocks(row)] == [
        SIGNED_FORK_THINKING, {"type": "tool_use", "id": SECOND_ID, "name": NATIVE_TOOL_NAME, "input": SECOND_ARGS},
    ]
    assert SIGNED_FORK_THINKING["signature"].encode() not in primary.read_bytes()
    original = {path: path.read_bytes() for path in (binding, primary, branch)}
    neighbor_headers = {**headers, "x-session-id": str(uuid4())}
    adjacent = {**continuation, "tools": [], "messages": [{"role": "user", "content": [
        {"type": "text", "text": SIGNED_FORK_PROJECT}, {"type": "text", "text": "建立同项目的相邻会话。"},
    ]}]}
    _, raw, neighbor_id = checked_messages(
        manage, token, adjacent, neighbor_headers, received, "signed_fork_neighbor_setup",
        trace_startup=True, sender_status=sender_status,
    )
    assert json.loads(raw)["stop_reason"] == "end_turn" and len(received) == 5
    wait_for(lambda: sender_status().get("idle"))
    (neighbor_binding,) = [path for path in binding.parent.glob("*.json") if path != binding]
    neighbor_record = json.loads(neighbor_binding.read_bytes())
    assert neighbor_record["client_path"] == json.loads(original[binding])["client_path"] == "/synthetic/shared-notes"
    neighbor_native = neighbor_record["native_session_id"]
    assert neighbor_native not in (primary.stem, branch.stem)
    (neighbor_archive,) = (Path("/native/tui-sessions") / neighbor_native / "home/.claude/projects").glob(
        "*/" + neighbor_native + ".jsonl",
    )
    assert neighbor_archive.parent.name == primary.parent.name
    original.update({path: path.read_bytes() for path in (neighbor_binding, neighbor_archive)})
    restart_sender()
    body = {**continuation, "messages": [
        *continuation["messages"], {"role": "assistant", "content": finished["content"]},
        {"role": "user", "content": SIGNED_FORK_QUESTION},
    ]}
    changed = deepcopy(body)
    ((_, signature),) = find_blocks(changed, "signature", SIGNED_FORK_THINKING["signature"])
    signature["signature"] = "Y2hhbmdlZA=="
    denied = {}
    for phase, caller, payload, request_headers in (
        ("neighbor", token, body, neighbor_headers),
        ("foreign_subject", foreign, body, headers),
        ("changed_signature", token, changed, headers),
    ):
        status, raw, request_id = checked_messages(
            manage, caller, payload, request_headers, received, "signed_fork_" + phase, expected_status=422,
            trace_startup=True, sender_status=sender_status,
        )
        assert json.loads(raw)["error"]["code"] == "unsupported_parameter" and len(received) == 5
        assert not manage("GET", "request-diagnostics/" + request_id)["attempts"]
        denied[phase] = {"request_id": request_id, "http_status": status}
    _, raw, new_id = checked_messages(
        manage, token, body, headers, received, "signed_fork_new_question", trace_startup=True,
        sender_status=sender_status,
    )
    response = json.loads(raw)
    tool = {"type": "tool_use", "id": SIGNED_FORK_TOOL_ID, "name": TOOL["name"], "input": ARGS}
    assert response["stop_reason"] == "tool_use" and response["content"] == [tool]
    assert len(received) == 6 and callbacks == [NEW_ID, SECOND_ID]
    callbacks.append(tool["id"])
    receipt = {**body, "messages": [
        *body["messages"], {"role": "assistant", "content": [tool]},
        {"role": "user", "content": [{"type": "tool_result", "tool_use_id": tool["id"], "content": REPLY}]},
    ]}
    marker = ("--name=" + headers["x-session-id"]).encode()
    (cli,) = [path for path in Path("/proc").glob("[0-9]*/cmdline") if fixture_command_has(path, marker)]
    os.kill(int(cli.parent.name), SIGKILL)
    restart_sender()
    assert not cli.parent.exists()
    _, raw, receipt_id = checked_messages(
        manage, token, receipt, headers, received, "signed_fork_receipt", trace_startup=True, sender_status=sender_status,
    )
    assert json.loads(raw)["stop_reason"] == "end_turn" and len(received) == 7
    for _, model, _ in received[-2:]:
        assert find_blocks(model, "type", "thinking") == [("assistant", SIGNED_THINKING), ("assistant", SIGNED_FORK_THINKING)]
        assert find_blocks(model, "id", SECOND_ID) == [("assistant", {
            "type": "tool_use", "id": SECOND_ID, "name": NATIVE_TOOL_NAME, "input": SECOND_ARGS,
        })]
        ((role, result),) = find_blocks(model, "tool_use_id", SECOND_ID)
        assert role == "user" and result["content"].count(SECOND_REPLY) == 1
    duplicate, _ = call(18090, "POST", "/v1/messages", token, receipt, headers)
    assert duplicate == 400 and len(received) == 7
    assert all(path.read_bytes() == saved for path, saved in original.items())
    attempts = verify_captures(manage, received[-3:], account_token)
    assert [item["request_id"] for item in attempts] == [neighbor_id, new_id, receipt_id]
    assert [item["diagnostic_session_origin"] for item in attempts[-2:]] == ["external_import", "disk_resume"]
    assert all(item["diagnostic_body_source"] == "interactive_cli" for item in attempts)
    return {"primary_native_id": primary.stem, "source_branch_id": branch.stem, "neighbor_native_id": neighbor_native,
            "source_model": source[0]["model"], "source_message_id": source[0]["id"], "source_tool_id": SECOND_ID,
            "rejections": denied, "model_posts": len(received), "client_tool_calls": callbacks,
            "original_archives_preserved": True, "duplicate_status": duplicate,
            "attempts": [*prior_attempts, *attempts], "wire_final": "unavailable"}


def _verify_serial_model_tools(model, tools, choice, phase):
    assert same_json_value(model["tools"], tools), (phase, model["tools"])
    assert same_json_value(model["tool_choice"], choice), (phase, model["tool_choice"])


def verify_disable_parallel_tool_use(manage, token, identifier, received, sender_status):
    """核对禁并行、普通选择及账号策略的能力回报。
    @param manage 管理入口。@param token 调用方。@param identifier 合成账号 ID。
    @param received 隔离模型实收。@param sender_status 失败后查询发送器。@return 按请求关联的证据。
    """
    tools = [TOOL, PARALLEL_SECOND_TOOL]
    account_path = f"accounts/{identifier}"
    cases, capabilities, callbacks = {}, {}, []

    def request(question, choice):
        return {"model": MODEL, "max_tokens": 128, "stream": False, "system": SYSTEM[0],
                "messages": [{"role": "user", "content": question}], "tools": tools, "tool_choice": choice}

    def post(body, headers, phase, policy, expected_status, *, stop_reason="end_turn"):
        before = len(received)
        ingress = sha256(encoded(body)).hexdigest()
        status, raw, request_id = checked_messages(
            manage, token, body, headers, received, phase, expected_status=expected_status, trace_startup=True,
            sender_status=sender_status,
        )
        reservation, record, claims = cache_marker_claims(manage, request_id)
        proof = {"status": status, "request_id": request_id, "reservation_id": reservation,
                 "attempt_count": record["attempt_count"], "model_posts": len(received) - before,
                 "ingress_body_sha256": ingress, "input_tool_choice": body["tool_choice"]}
        cases[phase] = proof
        reply = json.loads(raw)
        if status == 422:
            assert not (claims or proof["attempt_count"] or proof["model_posts"]), (phase, proof)
            assert reply["error"]["code"] == "unsupported_parameter", (phase, reply)
            proof["error_code"] = reply["error"]["code"]
            return reply
        ((digest, model, _),), (claim,) = received[before:], claims
        (attempt,) = manage("GET", "request-diagnostics/" + request_id)["attempts"]
        from_cli = body["tool_choice"] != SERIAL_AUTO
        provider_path = "interactive_cli" if from_cli else "account_sender"
        assert proof["attempt_count"] == proof["model_posts"] == 1 and attempt["attempt_id"] == reservation
        assert attempt["context"]["tui_body_source"] == provider_path, (phase, attempt)
        assert claim["sha256"] == digest and claim["from_interactive_cli"] is from_cli, (phase, claim)
        assert claim["cli_sha256"] and (claim["cli_sha256"] == digest) is from_cli, (phase, claim)
        assert claim["uses_native_history"] is from_cli, (phase, claim)
        assert claim["cli_tool_choice"] is None, (phase, claim)
        if from_cli:
            verify_automatic_model_tools(model, tools)
        else:
            _verify_serial_model_tools(model, tools, body["tool_choice"], phase)
        texts = [b.get("text", "") for row in model["messages"] if row["role"] == "user" for b in blocks(row)]
        question = body["messages"][0]["content"]
        assert sum(text.count(question) for text in texts) == 1, (phase, texts)
        system = model["system"]
        system_texts = [system] if isinstance(system, str) else [b["text"] for b in system]
        reminder = policy == "user_reminder"
        assert sum(text.count(SYSTEM[0]) for text in texts) == int(reminder), (phase, texts)
        assert sum(text.count(SYSTEM[0]) for text in system_texts) == int(not reminder), (phase, system_texts)
        assert reply["stop_reason"] == stop_reason, (phase, reply)
        if stop_reason == "end_turn":
            assert reply["content"] == [{"type": "text", "text": FINAL}], (phase, reply)
        proof.update(attempt_id=attempt["attempt_id"], provider_path=provider_path,
                     model_body_sha256=digest, cli_body_sha256=claim["cli_sha256"],
                     model_tool_choice=model.get("tool_choice"), model_tool_choice_present="tool_choice" in model,
                     model_tools=model["tools"], client_stop_reason=reply["stop_reason"])
        return reply

    for policy in ("append", "replace", "user_reminder"):
        written = manage("PUT", account_path, {"client_system_prompt_policy": policy})
        detail = manage("GET", account_path)
        listed, = (row for row in manage("GET", "accounts")["data"] if row["id"] == identifier)
        keys = ("request_backend", "tui_v2_available", "tui_system_prompt_policy_available", "client_system_prompt_policy")
        expected = dict(zip(keys, ("tui_v2", True, True, policy), strict=True))
        capabilities[policy] = {surface: {key: view[key] for key in keys} for surface, view in (
            ("update", written), ("detail", detail), ("list", listed),
        )}
        assert all(view == expected for view in capabilities[policy].values()), capabilities[policy]
        for choice, label in ((SERIAL_AUTO, "disabled"), ({**SERIAL_AUTO, "disable_parallel_tool_use": False}, "allowed")):
            phase = f"{policy}_{label}"
            headers = {"User-Agent": "flower2api-parallel-tool-fixture/1", "x-session-id": str(uuid4())}
            status = 200 if policy == "append" or choice != SERIAL_AUTO else 422
            post(request("可直接回答的合成问题", choice), headers, phase, policy, status)
        if policy == "append":
            headers = {"User-Agent": "flower2api-parallel-tool-fixture/1", "x-session-id": str(uuid4())}
            body = request(SERIAL_TOOL_QUESTION, SERIAL_AUTO)
            reply = post(body, headers, "append_disabled_tool", policy, 200, stop_reason="tool_use")
            expected_call = {"type": "tool_use", "id": NEW_ID, "name": TOOL["name"], "input": ARGS}
            assert same_json_value(reply["content"], [expected_call]), reply
            results = fixture_parallel_results(reply["content"], callbacks)
            follow = {**body, "messages": [*body["messages"], {"role": "assistant", "content": reply["content"]},
                                           {"role": "user", "content": results}]}
            post(follow, headers, "append_disabled_receipt", policy, 200)
            continuation = received[-1][1]
            (call_role, call), = find_blocks(continuation, "id", NEW_ID)
            (result_role, result), = find_blocks(continuation, "tool_use_id", NEW_ID)
            assert call_role == "assistant" and same_json_value(call, expected_call), continuation
            assert result_role == "user" and same_json_value(result, results[0]), continuation
            cases["append_disabled_receipt"]["model_tool_result"] = results[0]
            before = len(received)
            status, _, request_id = checked_messages(
                manage, token, follow, headers, received, "append_disabled_duplicate", expected_status=400,
                trace_startup=True, sender_status=sender_status,
            )
            assert len(received) == before and callbacks == [NEW_ID]
            cases["append_disabled_duplicate"] = {"status": status, "request_id": request_id, "model_posts": 0}
    assert len(received) == 6 and not any(path.is_file() for path in Path("/flows/api").rglob("*"))
    return {"cases": cases, "account_capabilities": capabilities, "client_tool_calls": callbacks,
            "model_posts": len(received), "wire_final": "unavailable"}


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


def verify_forced_tool_choice(manage, token, identifier, received, sender_status, restart, *, metadata_only,
                              stage_closed_archive=None):
    """从公开入口核对强制选择、原工具回执和 CLI 正文。
    @param manage 管理入口。@param token 合成令牌。@param identifier 账号 ID。
    @param received 模型实收。@param sender_status 失败后查询发送器。@param restart 可选的发送器重启。
    @param metadata_only 是否仅验证在途回执遇到原档缺主轮的受控对照。
    @param stage_closed_archive 可选，按公开会话请求头在完整答复交付后保留原档的元数据并返回快照。
    @return 按请求关联的证据。
    """
    cases = {}
    tools = [TOOL, SECOND_TOOL]

    def post(body, phase, expected_status, *, new_auto=False):
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
        if new_auto:
            assert claim["from_interactive_cli"] and claim["uses_native_history"] and claim["cli_sha256"] == digest, claim
            (attempt,) = manage("GET", "request-diagnostics/" + request_id)["attempts"]
            assert attempt["context"]["tui_body_source"] == "interactive_cli", attempt
            question = body["messages"][-1]["content"]
            assert sum(block.get("text") == question for row in model["messages"] if row["role"] == "user"
                       for block in blocks(row)) == 1, (phase, model)
            assert sum(block.get("text") == FINAL for row in model["messages"] if row["role"] == "assistant"
                       for block in blocks(row)) == 1, (phase, model)
            proof.update(provider_path="interactive_cli", model_body_sha256=digest, cli_body_sha256=claim["cli_sha256"],
                         attempt_id=attempt["attempt_id"], new_question_count=1,
                         native_session_id=json.loads(model["metadata"]["user_id"])["session_id"],
                         session_origin=attempt["context"]["tui_session_origin"],
                         model_tools=verify_automatic_model_tools(model, tools))
        else:
            assert not claim["from_interactive_cli"] and not claim["uses_native_history"], (phase, claim)
            assert claim["cli_sha256"] and claim["cli_sha256"] != digest, (phase, claim)
            assert claim["cli_tool_choice"] is None, (phase, claim)
            assert same_json_value(model["tool_choice"], body["tool_choice"]), (phase, model["tool_choice"])
            assert same_json_value(model["tools"], tools), (phase, model["tools"])
            assert model["thinking"] == body["thinking"], (phase, model)
            proof.update(provider_path="account_sender", model_body_sha256=digest, model_tool_choice=model["tool_choice"],
                         model_tools=[tool["name"] for tool in model["tools"]],
                         cli_body_sha256=claim["cli_sha256"], cli_tool_choice=claim["cli_tool_choice"],
                         cli_tool_names=claim["cli_tool_names"])
        result = [[r["role"], b] for r in body["messages"] for b in blocks(r) if b["type"] in ("tool_use", "tool_result")]
        observed = [[r["role"], b] for r in model["messages"] for b in blocks(r) if b["type"] in ("tool_use", "tool_result")]
        assert same_json_value(observed, result), (phase, observed)
        proof["tool_history"] = observed
        return raw, proof

    policies = ("append",) if restart else ("append", "replace", "user_reminder")
    choices = {"named": FORCED_CHOICES["named"]} if metadata_only or stage_closed_archive else FORCED_CHOICES
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
                assert tool_reply["stop_reason"] == "tool_use" and same_json_value(tool_reply["content"], [expected]), (
                    phase, tool_reply,
                )
                tool_proofs[-1]["public_tool"] = tool_reply["content"][0]
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
            if not metadata_only:
                # 旧发送器交付完整答复后，原生新轮可从客户端确认的完整历史开始。
                if stage_closed_archive:
                    preserved = stage_closed_archive(headers)
                question = {"role": "user", "content": "工具轮完成后，请回答独立的合成问题 " + phase}
                history = [*messages, {"role": "assistant", "content": reply["content"]}]
                fresh = {**final_request, "messages": [*history, question]}
                raw, next_question = post(fresh, phase + "_next_auto_question", 200, new_auto=True)
                reply = json.loads(raw)
                assert reply["stop_reason"] == "end_turn" and reply["content"] == [{"type": "text", "text": FINAL}], raw
                if stage_closed_archive:
                    archive = preserved[0]
                    branch_id = next_question["native_session_id"]
                    assert branch_id != archive.stem and next_question["session_origin"] == "external_import"
                    assert archive.with_name(branch_id + ".jsonl").is_file()
                cases[phase]["next_auto_question"] = next_question
            if preserved:
                archive, snapshot, binding_file, binding_snapshot = preserved
                assert archive.read_bytes() == snapshot and binding_file.read_bytes() == binding_snapshot
                cases[phase]["original_archive"] = {"native_session_id": archive.stem,
                                                   "sha256": sha256(snapshot).hexdigest(),
                                                   "metadata_rows": len(snapshot.splitlines())}
    assert not any(path.is_file() for path in Path("/flows/api").rglob("*"))
    return {"wire_final": "unavailable", "restarted": restart is not None, "cases": cases, "model_posts": len(received)}


def same_json_value(actual, expected):
    """按 JSON 类型比较值，忽略对象键序并保留数组元素顺序。
    @param actual 已解码的实收值。@param expected 已解码的预期值。@return 语义是否相同。
    """
    # Python 把布尔值当整数比较，JSON Schema 的关键字则区分布尔值和数字。
    if isinstance(actual, bool) or isinstance(expected, bool):
        return actual is expected
    if isinstance(actual, dict) and isinstance(expected, dict):
        return actual.keys() == expected.keys() and all(same_json_value(actual[key], expected[key]) for key in expected)
    if isinstance(actual, list) and isinstance(expected, list):
        return len(actual) == len(expected) and all(same_json_value(a, b) for a, b in zip(actual, expected, strict=True))
    return actual == expected


def verify_structured_tool_round(manage, token, identifier, received, sender_status, restart, *, source_observer):
    """核对带结构化输出的工具轮及已认领原生轮的兼容边界。
    @param manage 管理入口。@param token 合成令牌。@param identifier 账号 ID。
    @param received 隔离模型实收。@param sender_status 失败后的发送器状态。
    @param restart 可选，终止原 CLI 并重启发送器。@param source_observer 是否安装源码正文观察器。
    @return 按公开请求关联的证据。
    """
    account = manage("PUT", f"accounts/{identifier}", {"client_system_prompt_policy": "append"})
    assert account["client_system_prompt_policy"] == "append"
    cases, returned_tool_ids = {}, []
    base_config = {"effort": "medium"}
    structured_config = {**base_config, "format": STRUCTURED_FORMAT}

    def post(label, body, expected, source=None):
        before = len(received)
        status, raw, request_id = checked_messages(
            manage, token, body, headers, received, label, expected_status=expected,
            trace_startup=True, sender_status=sender_status,
        )
        delta = len(received) - before

        def finished():
            detail = manage("GET", "request-diagnostics/" + request_id)
            return detail if detail["request"].get("finished_at") else None

        detail = wait_for(finished)
        record, attempts = detail["request"], detail["attempts"]
        context = record.get("context") or {}
        assert record["request_id"] == request_id and record["status_code"] == status
        reservation = context.get("tui_reservation_id")
        assert (reservation is None) is (status == 400), (label, context)
        proof = {"status": status, "request_id": request_id, "reservation_id": reservation,
                 "session_id": headers["x-session-id"], "model_posts": delta, "attempt_count": len(attempts)}
        cases[label] = proof
        claims = None
        if source_observer and reservation:
            _, _, claims = cache_marker_claims(manage, request_id)
        if expected != 200:
            assert delta == len(attempts) == 0 and not claims
            if status == 422:
                proof["error_code"] = json.loads(raw)["error"]["code"]
            return raw
        assert delta == len(attempts) == context["tui_confirmed_model_responses"] == 1
        ((digest, model, _),), (attempt,) = received[before:], attempts
        assert attempt["request_id"] == request_id and attempt["attempt_id"] == reservation
        assert attempt["context"]["tui_body_source"] == source
        output = model.get("output_config", {})
        assert same_json_value(output, body["output_config"]), (label, output)
        proof.update(provider_path=source, session_origin=attempt["context"]["tui_session_origin"],
                     model_body_sha256=digest, model_output_config=output)
        if claims is not None:
            (claim,) = claims
            assert claim["sha256"] == digest and claim["from_interactive_cli"] is (source == "interactive_cli")
            assert not claim["cli_has_output_format"], (label, claim)
            if body["output_config"].get("format") is not None:
                assert source == "account_sender" and claim["cli_sha256"] != digest
            proof.update(cli_body_sha256=claim["cli_sha256"], cli_has_output_format=claim["cli_has_output_format"])
        return raw

    def tool_result(raw, content, *, failed):
        reply = json.loads(raw)
        tool = {"type": "tool_use", "id": NEW_ID, "name": TOOL["name"], "input": ARGS}
        assert reply["stop_reason"] == "tool_use" and reply["content"] == [tool]
        returned_tool_ids.append(tool["id"])
        result = {"type": "tool_result", "tool_use_id": tool["id"], "content": content}
        if failed:
            result["is_error"] = True
        return tool, result

    # 旧发送器负责整轮，包含同一工具错误中的文字和原图。
    headers = {"x-session-id": str(uuid4()), "User-Agent": "flower2api-structured-tool-fixture/1"}
    messages = [{"role": "user", "content": "读取合成便签并返回订单状态。"}]
    body = {"model": MODEL, "max_tokens": 128, "messages": messages, "tools": [TOOL], "system": SYSTEM[0],
            "stream": False, "output_config": structured_config}
    raw = post("structured_initial", body, 200, "account_sender")
    (png,) = fixture_image_blocks(all_formats=False)
    content = [{"type": "text", "text": "读取失败。"}, png, {"type": "text", "text": "保留诊断截图。"}]
    tool, result = tool_result(raw, content, failed=True)
    messages = [*messages, {"role": "assistant", "content": [tool]}, {"role": "user", "content": [result]}]
    if restart:
        (binding,) = Path("/native/tui-workspaces").glob("*.json")
        binding_bytes = binding.read_bytes()
        native_id = json.loads(binding_bytes)["native_session_id"]
        projects = Path("/native/tui-sessions") / native_id / "home/.claude/projects"
        archive = wait_for(lambda: next(projects.glob("*/" + native_id + ".jsonl"), None))
        archive_bytes = archive.read_bytes()
        restart(headers)
    follow = {**body, "messages": messages, "stream": True}
    raw = post("structured_error_image_receipt", follow, 200, "account_sender")
    wire = [json.loads(line[5:]) for line in raw.splitlines() if line.startswith(b"data:")]
    text = "".join(event["delta"]["text"] for event in wire if event["type"] == "content_block_delta")
    (terminal,) = [event["delta"] for event in wire if event["type"] == "message_delta"]
    assert wire[-1]["type"] == "message_stop" and terminal["stop_reason"] == "end_turn"
    assert json.loads(text) == {"fixture_order_status": "ready"}
    model = received[-1][1]
    assert find_blocks(model, "id", tool["id"]) == [("assistant", tool)]
    ((role, observed),) = find_blocks(model, "tool_use_id", tool["id"])
    assert role == "user" and observed == result
    cases["structured_error_image_receipt"].update(model_tool_result=observed, client_json=json.loads(text),
                                                    stop_reason=terminal["stop_reason"])
    if restart:
        assert binding.read_bytes() == binding_bytes
        resumed_archive = archive.read_bytes()
        # 旧发送器恢复原 UUID 时，CLI 可以向同一档案追加记录。
        assert resumed_archive.startswith(archive_bytes), (native_id, len(archive_bytes), len(resumed_archive))
        appended_types = [json.loads(line)["type"] for line in resumed_archive[len(archive_bytes):].splitlines()]
        cases["structured_error_image_receipt"]["archive"] = {
            "native_session_id": native_id, "preserved_prefix_sha256": sha256(archive_bytes).hexdigest(),
            "binding_preserved": True, "appended_record_types": appended_types,
        }
    post("structured_duplicate_receipt", follow, 400)

    # 原生等待轮的输入合同已经确定，新增 schema 的回执须在投递前终止。
    headers = {**headers, "x-session-id": str(uuid4())}
    body = {**body, "output_config": base_config}
    raw = post("native_initial", body, 200, "interactive_cli")
    tool, result = tool_result(raw, REPLY, failed=False)
    follow = {**body, "messages": [*body["messages"], {"role": "assistant", "content": [tool]},
                                 {"role": "user", "content": [result]}]}
    if restart:
        restart(headers)
    post("native_receipt_added_schema", {**follow, "output_config": structured_config}, 422)
    assert cases["native_receipt_added_schema"]["error_code"] == "unsupported_parameter"
    raw = post("native_original_receipt", follow, 200, "interactive_cli")
    reply = json.loads(raw)
    assert reply["stop_reason"] == "end_turn" and reply["content"] == [{"type": "text", "text": FINAL}]
    ((role, observed),) = find_blocks(received[-1][1], "tool_use_id", tool["id"])
    assert role == "user" and observed["content"].count(REPLY) == 1
    origin = "disk_resume" if restart else "live_process"
    for label in ("structured_error_image_receipt", "native_original_receipt"):
        assert cases[label]["session_origin"] == origin, cases[label]
    assert returned_tool_ids == [NEW_ID, NEW_ID] and len(received) == 4
    assert not any(path.is_file() for path in Path("/flows/api").rglob("*"))
    return {"cases": cases, "model_posts": len(received), "client_tool_results": returned_tool_ids,
            "restarted": restart is not None, "source_observer": source_observer, "wire_final": "unavailable"}


def structured_sse_text(raw, phase):
    """按公开文本块的生命周期重组流式回复。
    @param raw 公开 SSE 字节。@param phase 用例名。@return 重组文本及停止原因。
    """
    frames = [json.loads(line[5:]) for line in raw.splitlines() if line.startswith(b"data:")]
    events = [event for event in frames if event["type"] != "ping"]
    assert len(events) >= 5 and (events[0]["type"], events[-2]["type"], events[-1]["type"]) == (
        "message_start", "message_delta", "message_stop",
    ), (phase, events)
    parts = []
    for index, (actual_index, group) in enumerate(groupby(events[1:-2], key=lambda event: event.get("index"))):
        block_events = list(group)
        assert actual_index == index and all(type(event.get("index")) is int for event in block_events), (
            phase, index, block_events,
        )
        assert len(block_events) >= 2 and (block_events[0]["type"], block_events[-1]["type"]) == (
            "content_block_start", "content_block_stop",
        ), (phase, index, block_events)
        start = block_events[0]["content_block"]
        assert start["type"] == "text" and isinstance(start["text"], str), (phase, index, start)
        parts.append(start["text"])
        for event in block_events[1:-1]:
            delta = event.get("delta", {})
            assert event["type"] == "content_block_delta" and delta.get("type") == "text_delta" and isinstance(
                delta.get("text"), str,
            ), (phase, index, event)
            parts.append(delta["text"])
    return "".join(parts), events[-2]["delta"]["stop_reason"]


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
                    assert ("format" not in output if from_cli else same_json_value(output, config)), (phase, output)
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
                        text, stop_reason = structured_sse_text(raw, phase)
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
    cases = [(f"{surface}_{side}_{ttl or 'implicit'}", "append", surface, ((surface, index, ttl),))
             for surface in ("text", "tool") for index, side in enumerate(("first", "last")) for ttl in (None, "5m", "1h")]
    cases.extend((f"unmarked_{surface}", "append", surface, ()) for surface in ("text", "tool", "combined"))
    combined = (("tool", 1, "1h"), ("text", 0, "5m"))
    cases.append(("combined", "append", "combined", combined))
    if mode == "baseline":
        for policy in ("replace", "user_reminder"):
            cases.extend((f"{policy}_{surface}", policy, surface, ((surface, 0, "5m"),))
                         for surface in ("text", "tool"))
            cases.append((f"{policy}_combined", policy, "combined", combined))
    proof, capabilities = {}, {}
    policy = None
    account_path = f"accounts/{account_id}"
    for name, system_policy, surface, markers in cases:
        if policy != system_policy:
            policy = system_policy
            account = manage("PUT", account_path, {"client_system_prompt_policy": policy})
            assert account["request_backend"] == "tui_v2" and account["client_system_prompt_policy"] == policy
            if mode == "baseline":
                listed, = (row for row in manage("GET", "accounts")["data"] if row["id"] == account_id)
                expected_account = {"request_backend": "tui_v2", "tui_v2_available": True,
                                    "tui_system_prompt_policy_available": True, "client_system_prompt_policy": policy}
                capabilities[policy] = {source: {key: view[key] for key in expected_account} for source, view in (
                    ("update", account), ("detail", manage("GET", account_path)), ("list", listed),
                )}
                assert all(view == expected_account for view in capabilities[policy].values()), capabilities[policy]
        current = [{"type": "text", "text": text} for text in texts]
        body = {"model": MODEL, "max_tokens": 128, "stream": False, "messages": [
            {"role": role, "content": text} for role, text in HISTORY[:2]
        ] + [{"role": "user", "content": current}]}
        targets = {"text": current}
        if surface != "text":
            body["tools"] = [tool.copy() for tool in tools]
            targets["tool"] = body["tools"]
        expected = {key: [None, None] for key in targets}
        for target, offset, ttl in markers:
            marker = {"type": "ephemeral"}
            if ttl is not None:
                marker["ttl"] = ttl
            targets[target][offset]["cache_control"] = expected[target][offset] = marker
        before = len(received)
        status, raw, request_id = checked_messages(
            manage, token, body, {**headers, "x-session-id": str(uuid4())}, received, name,
            expected_status=200 if policy == "append" else 422, trace_startup=True,
        )
        reservation, record, claims = cache_marker_claims(manage, request_id)
        evidence = {"http_status": status, "model_posts": len(received) - before, "request_id": request_id,
                    "reservation_id": reservation, "surface": surface, "client_markers": expected.get(surface, expected),
                    "policy": policy,
                    "attempt_count": record["attempt_count"]}
        if status == 422:
            evidence["code"] = json.loads(raw)["error"]["code"]
            assert evidence["code"] == "unsupported_parameter"
            assert before == len(received) and not claims and record["attempt_count"] == 0
        else:
            assert record["attempt_count"] == 1
            assert json.loads(raw)["content"] == [{"type": "text", "text": FINAL}]
            ((model_digest, model, _),) = received[before:]
            (claim,) = claims
            from_cli = mode != "baseline" or not markers
            assert claim["sha256"] == model_digest and claim["from_interactive_cli"] is from_cli, (name, claim)
            assert claim["uses_native_history"] is from_cli, (name, claim)
            if from_cli:
                assert claim["cli_sha256"] == model_digest, (name, claim)
            ((message_index, user),) = [(i, row) for i, row in enumerate(model["messages"])
                                        if any(block.get("text") in texts for block in blocks(row))]
            assert user["role"] == "user"
            content = [(i, block) for i, block in enumerate(blocks(user)) if block.get("text") in texts]
            assert [block["text"] for _, block in content] == texts and content[1][0] == content[0][0] + 1
            projected = model.get("tools", [])
            observed = {"text": [block.get("cache_control") for _, block in content]}
            if "tool" in targets:
                assert [(tool["name"].removeprefix("mcp__flower__"), tool["description"], tool["input_schema"])
                        for tool in projected] == [(tool["name"], tool["description"], tool["input_schema"]) for tool in tools]
                observed["tool"] = [tool.get("cache_control") for tool in projected]
            else:
                assert not projected
            if from_cli:
                # 固定 CLI 默认只标记当前用户末块。关闭自动缓存后，两类显式标记均无出站表示。
                automatic = None if mode == "native-no-auto" else {"type": "ephemeral", "ttl": "1h"}
                native_expected = {key: [None, None] for key in targets}
                native_expected["text"] = [None, automatic]
                assert observed == native_expected, (mode, name, observed)
            else:
                assert observed == expected, (mode, name, observed)
            evidence.update(from_interactive_cli=from_cli, uses_native_history=claim["uses_native_history"],
                            model_body_sha256=model_digest, model_markers=observed.get(surface, observed),
                            user_message_index=message_index, user_block_indexes=[i for i, _ in content],
                            user_role=user["role"], model_tool_names=[tool["name"] for tool in projected],
                            system_markers=[block["cache_control"] for block in model.get("system", [])
                                            if "cache_control" in block])
        proof[name] = evidence
    assert not any(path.is_file() for path in Path("/flows/api").rglob("*"))
    return {"mode": mode, "cases": proof, "account_capabilities": capabilities,
            "model_posts": len(received), "wire_final": "unavailable"}


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
            nested_result = name in ("nested_result", "forced_nested_result")
            from_cli = nested_result or name in ("unmarked", "history", "history_replace", "history_user_reminder",
                                                "forced_ttl_5m", "forced_ttl_1h")
            assert claim["from_interactive_cli"] is from_cli, (name, claim)
            assert model.get("tools", []) == body.get("tools", []), name
            if from_cli:
                user_texts = [b.get("text") for message in model["messages"] if message["role"] == "user"
                              for b in blocks(message)]
                assert user_texts.count(question["text"]) == user_texts.count(tail["text"]) == 1
                if nested_result:
                    assert claim["uses_native_history"] is True, (name, claim)
                    markers = observed_cache_breakpoints(model)
                    assert markers == [], (name, markers)
                    assert find_blocks(model, "id", PAST_ID) == [("assistant", historical_tool)]
                    observed = find_blocks(model, "tool_use_id", PAST_ID)
                    # 平台 TTL 只覆盖直接断点，结果内部的断点保留原值。
                    assert observed == [("user", historical_result)], (name, observed)
                    evidence.update(nested_result=observed, cache_markers=markers,
                                    uses_native_history=claim["uses_native_history"])
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


def model_continue_prompt_count(model):
    """统计完整的标准继续提示。@param model 隔离模型实收正文。@return 用户文本块里的实际出现次数。"""
    return sum(block["type"] == "text" and block.get("text") == "Continue from where you left off."
               for row in model["messages"] if row["role"] == "user" for block in blocks(row))


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
    png = b64decode(images["image/png"], validate=True)
    assert png[:8] == b"\x89PNG\r\n\x1a\n", "PNG 正例缺少文件签名"
    offset = 8
    for kind in (b"IHDR", b"IDAT", b"IEND"):
        size = int.from_bytes(png[offset:offset + 4], "big")
        end = offset + 8 + size
        assert end + 4 <= len(png) and png[offset + 4:offset + 8] == kind, ("PNG 正例块损坏", kind)
        assert crc32(png[offset + 4:end]) == int.from_bytes(png[end:end + 4], "big"), ("PNG 正例 CRC 不匹配", kind)
        content = png[offset + 8:end]
        if kind == b"IHDR":
            assert content == pack(">IIBBBBB", 1, 1, 8, 4, 0, 0, 0)
        elif kind == b"IDAT":
            assert decompress(content) == b"\x01\xff\xff", "PNG 正例像素不匹配"
        else:
            assert not content
        offset = end + 4
    assert offset == len(png), "PNG 正例在 IEND 后有多余字节"
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


def verify_image_only_requests(manage, token, account_token, headers, received, *, policy):
    """核对原生粘贴边界及超界请求的原入口。
    @param manage 管理入口。@param token 合成调用方。@param account_token 合成模型凭据。
    @param headers 公开请求头。@param received TLS 实收。
    @param policy 公开请求实际使用的账号策略。@return 各独立请求的证据。
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

    cases = [
        (name + ("_system" if system else "_omitted"), content, native, system)
        for name, content, native in [
            ("both_at_limit", make_png(2000, 512_000), True),
            ("over_width", make_png(2001, 512_000), False),
            ("over_bytes", make_png(2000, 512_001), False),
            ("over_both", make_png(2001, 512_001), False),
        ]
        for system in (None, "图像边界验收的独立业务指令。")
    ]
    if policy == "append":
        cases.append(("native_24_images", fixture_image_blocks(all_formats=True) * 6, True, None))
    result = {}
    for name, content, native, system in cases:
        body = {"model": MODEL, "max_tokens": 128, "stream": False,
                "messages": [{"role": "user", "content": content}]}
        if system is not None:
            body["system"] = system
        before = len(received)
        expected = 200 if native or policy == "append" else 422
        status, raw, request_id = checked_messages(manage, token, body, {**headers, "x-session-id": str(uuid4())},
                                                  received, name, expected_status=expected)
        observation = {"http_status": status, "model_posts": len(received) - before, "request_id": request_id}
        result[name] = observation
        assert observation["model_posts"] == int(status == 200), (name, observation)
        response = json.loads(raw)
        detail = manage("GET", "request-diagnostics/" + request_id)
        if status == 422:
            assert response["error"]["code"] == "unsupported_parameter" and detail["attempts"] == [], (
                name, response, detail,
            )
            observation["error_code"] = response["error"]["code"]
            continue
        assert response["content"] == [{"type": "text", "text": FINAL}]
        (diagnostic,) = detail["attempts"]
        assert diagnostic["attempt_id"] == detail["request"]["context"]["tui_reservation_id"]
        source = diagnostic["context"]["tui_body_source"]
        assert source == ("interactive_cli" if native else "account_sender"), (name, source)
        observation.update(body_source=source, body_sha256=received[-1][0])
        model = received[-1][1]
        if native:
            verify_current_image_row(model, content, require_alias=True)
            (attempt,) = verify_captures(manage, received[-1:], account_token)
            observation["attempt"] = attempt
        else:
            assert model["messages"] == body["messages"]
        if system is not None:
            roots = sum(block.get("text", "").count(system) for block in blocks({"content": model["system"]}))
            users = sum(block.get("text", "").count(system) for row in model["messages"] if row["role"] == "user"
                        for block in blocks(row))
            assert (roots, users) == ((0, 1) if policy == "user_reminder" else (1, 0)), (name, roots, users)
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


def with_auto_tool_choice(body, shape):
    """按指定形状传入默认工具选择。@param body 原始请求。@param shape 字段形状。@return 调整后的请求。"""
    result = dict(body)
    if shape == "omitted":
        result.pop("tool_choice", None)
    else:
        result["tool_choice"] = {"type": "auto"}
        if shape == "explicit-false":
            result["tool_choice"]["disable_parallel_tool_use"] = False
    return result


def verify_automatic_model_tools(model_request, declared):
    """核对固定 CLI 的默认工具选择及完整工具声明。
    @param model_request 隔离模型实收正文。@param declared 公开工具声明。@return 实收工具名。
    """
    assert "tool_choice" not in model_request, model_request.get("tool_choice")
    actual = [[tool["name"], tool["description"], tool["input_schema"]] for tool in model_request["tools"]]
    expected = [["mcp__flower__" + tool["name"], tool["description"], tool["input_schema"]] for tool in declared]
    assert same_json_value(actual, expected), actual
    return [name for name, _, _ in actual]


def verify_model(received, *, policy, old_content, current_text_blocks=False, exact_receipts=(), max_tokens=128):
    """检验历史、系统提示、原生动态 MCP 和续轮。@param received HTTPS 实收。
    @param policy 原工具轮的有效动作。@param old_content 已确认的旧工具结果。
    @param current_text_blocks 是否包含分块问题。@param exact_receipts 要求逐块相等的当前工具结果。
    @param max_tokens 出站需保留的输出上限。@return 无。
    """
    (_, first, _), (_, second, _) = received
    for body in (first, second):
        assert body["max_tokens"] == max_tokens, body["max_tokens"]
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
        assert old_result[0] == "user" and old_result[1].get("content") == old_content, old_result
        (tool,) = [t for t in body["tools"] if t.get("description") == TOOL["description"]]
        assert tool["name"] == NATIVE_TOOL_NAME and tool["input_schema"] == TOOL["input_schema"]
    assert not find_blocks(first, "id", NEW_ID) and not find_blocks(first, "tool_use_id", NEW_ID)
    (new,) = find_blocks(second, "id", NEW_ID)
    assert new[0] == "assistant" and new[1]["name"] == NATIVE_TOOL_NAME and same_json_value(new[1]["input"], ARGS), new
    if exact_receipts:
        for result in exact_receipts:
            tool_id = result["tool_use_id"]
            assert not find_blocks(first, "tool_use_id", tool_id)
            observed = find_blocks(second, "tool_use_id", tool_id)
            assert observed == [("user", result)], observed
    else:
        (reply,) = find_blocks(second, "tool_use_id", NEW_ID)
        assert reply[0] == "user" and REPLY in json.dumps(reply[1], ensure_ascii=False)


def _verify_direct_oauth_attempts(manage, account, requests, received, credentials, deliveries, *, recover_pending):
    assert [row["credential"] for row in credentials] == ["initial", "rotated"], credentials
    attempts = []
    for request_id, (digest, body, _tls), credential in zip(requests, received, credentials, strict=True):
        detail = manage("GET", "request-diagnostics/" + request_id)
        (attempt,) = detail["attempts"]
        context = detail["request"]["context"]
        reservation = context["tui_reservation_id"]
        delivery = deliveries[digest]
        assert credential["model_body_sha256"] == delivery["model_body_sha256"] == digest
        assert context["tui_confirmed_model_responses"] == 1
        assert attempt["attempt_id"] == reservation and attempt["account_id"] == account
        assert attempt["context"]["tui_body_source"] == delivery["connection_owner"] == "interactive_cli"
        assert delivery["permit"]["reservation_id"] == reservation
        assert delivery["permit"]["body_identity"] == {**model_body_identity(body), "billing_cch": "00000"}
        attempts.append({
            "request_id": request_id, "reservation_id": reservation, "credential": credential["credential"],
            "session_origin": attempt["context"]["tui_session_origin"], "delivery": delivery,
        })
    assert len({a["reservation_id"] for a in attempts}) == 2
    assert len({a["delivery"]["tunnel"]["cli_pid"] for a in attempts}) == (2 if recover_pending else 1)
    assert [a["session_origin"] for a in attempts] == [
        "external_import", "disk_resume" if recover_pending else "live_process",
    ]
    return attempts


def verify_captures(manage, received, account_token, *, additional_secrets=()):
    """从管理接口按尝试比对实际 CLI 正文与 HTTPS 收件摘要。@param manage 本次管理请求。
    @param received TLS 实收。@param account_token 合成凭据。
    @param additional_secrets 可选，需检查脱敏的其他合成凭据。@return 按模型请求顺序的对应关系。
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
                serialized = json.dumps(snap)
                assert all(secret not in serialized for secret in (account_token, *additional_secrets))
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
    parser.add_argument("--installed-runtime", action="store_true",
                        help="结构化工具轮使用账号镜像的内置事件源")
    parser.add_argument("--shared-state", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--current-text-blocks", action="store_true")
    parser.add_argument("--current-images", action="store_true")
    parser.add_argument("--current-image-ending", choices=("text", "image"), default="text")
    parser.add_argument("--history-cache-markers", action="store_true")
    parser.add_argument("--history-cache-ttl", choices=("5m", "1h"))
    parser.add_argument("--history-cache-scope", choices=("nested", "mixed"))
    parser.add_argument("--history-tool-images", nargs="?", const="explicit-success",
                        choices=("explicit-success", "implicit-success"))
    parser.add_argument("--history-empty-tool-result",
                        choices=("omitted", "array", "string", "omitted-error", "array-error", "string-error"))
    current_receipts = parser.add_mutually_exclusive_group()
    current_receipts.add_argument("--empty-tool-receipt", choices=("omitted", "array", "string", "omitted-error",
                                                                   "array-error", "string-error", "array-success"),
                                  help="核对本轮实际回执的空值、错误标志及继续提示")
    current_receipts.add_argument("--tool-receipt-images", nargs="?", const="explicit-success",
                        choices=("explicit-success", "implicit-success"))
    current_receipts.add_argument("--tool-receipt-text-blocks", choices=("implicit-success", "explicit-success", "error"),
                                  help="逐块核对本轮工具回执的重复文本、换行、错误标志及继续提示")
    parser.add_argument("--tool-receipt-nested-cache", choices=("5m", "1h", "default"),
                        help="在本轮工具结果的首个文本块上添加显式缓存断点")
    parser.add_argument("--tool-receipt-outer-cache", choices=("5m", "1h", "default"),
                        help="在本轮工具结果外层添加显式缓存断点")
    parser.add_argument("--explicit-custom-tool-type", action="store_true")
    system_roles = parser.add_mutually_exclusive_group()
    system_roles.add_argument("--message-system-roles", dest="message_system_roles", action="store_const", const="observe")
    system_roles.add_argument("--ordinary-message-system-contract", dest="message_system_roles", action="store_const",
                              const="ordinary-contract")
    system_roles.add_argument("--turn-scoped-system-contract", dest="message_system_roles", action="store_const",
                              const="turn-scoped-contract")
    system_roles.add_argument("--message-system-effort-contract", dest="message_system_roles", action="store_const",
                              const="message-effort-contract")
    auto_shapes = ("omitted", "bare", "explicit-false")
    parser.add_argument("--auto-tool-choice", nargs="?", const="explicit-false", choices=auto_shapes,
                        help="使用选定的普通 auto 入口并核对等价回执")
    parser.add_argument("--receipt-auto-tool-choice", choices=auto_shapes,
                        help="选择合法回执的等价 auto 字段形状")
    parser.add_argument("--prior-auto-source", type=Path,
                        help="从旧账号事件源实际认领的回执摘要恢复")
    parser.add_argument("--adaptive-thinking-model", choices=(MODEL, "claude-opus-5-5"))
    parser.add_argument("--fixed-thinking-model", choices=(MODEL, "claude-opus-4-6"))
    parser.add_argument("--fixed-thinking-display", choices=("updates", "summarized"), default="updates")
    parser.add_argument("--adaptive-thinking-display", choices=("default", "updates", "summarized"), default="updates")
    parser.add_argument("--thinking-cli-summaries", choices=("on", "off"))
    parser.add_argument("--signed-tool-history", action="store_true")
    parser.add_argument("--signed-tool-response", choices=("signature-only", "redacted", "missing-model"))
    parser.add_argument("--trace-initial-startup", action="store_true", help="记录源码 V2 夹具的启动阶段")
    parser.add_argument("--trace-recovery-resend", action="store_true",
                        help="隔离工具回执收到 503 后原样补发一次，分别取证并保留原失败")
    fault = parser.add_mutually_exclusive_group()
    fault.add_argument("--recovery-ledger-contention", action="store_true")
    fault.add_argument("--recovery-ledger-deadline", action="store_true")
    fault.add_argument("--recovery-workspace-rejection", nargs="?", const="mismatched-key",
                       choices=("mismatched-key", "missing-directory", "missing-binding"))
    fault.add_argument("--recovery-readiness-rejection", action="store_true")
    fault.add_argument("--recovery-slow-model", action="store_true")
    fault.add_argument("--replay-unknown-receipt", choices=("live", "complete", "json-live", "json-complete", "lost-live", "lost"),
                       help="核对 502 后的重交。live/complete 为 SSE，json-* 为 JSON。lost* 为 JSON 原回复丢失")
    scenario = parser.add_mutually_exclusive_group()
    scenario.add_argument("--restart-history", action="store_true")
    scenario.add_argument("--text-input", action="store_true")
    scenario.add_argument("--cache-markers", action="store_true")
    scenario.add_argument("--cache-marker-capabilities", choices=("baseline", "native-default", "native-no-auto"))
    scenario.add_argument("--system-policy", action="store_true")
    scenario.add_argument("--toggle-pending-policy", action="store_true")
    scenario.add_argument("--tool-policy", choices=("replace", "user_reminder"))
    scenario.add_argument("--recover-pending-tool", action="store_true")
    scenario.add_argument("--model-connection-contract", choices=("live", "server-close", "restart"),
                          help="经账号代理核对两轮模型请求的 TLS 连接归属")
    scenario.add_argument("--oauth-rotation", choices=("live", "restart"))
    scenario.add_argument("--provider-quota", choices=("sse", "json"))
    scenario.add_argument("--initial-idle-model-connection", action="store_true")
    scenario.add_argument("--output-effort", action="store_true")
    scenario.add_argument("--structured-output-contract", action="store_const", const="contract")
    scenario.add_argument("--structured-output-tool-round", dest="structured_output_contract", choices=("live", "restart"),
                          help="核对旧发送器的结构化工具往返及原生回执新增 schema 的拒绝")
    scenario.add_argument("--external-signed-history-contract", dest="external_signed_history", action="store_const", const="contract",
                          help="核对普通客户端提交的外部签名历史")
    scenario.add_argument("--external-signed-history-source", dest="external_signed_history", action="store_const", const="source",
                          help="用独立回环模型响应核对外部签名及来源字段")
    scenario.add_argument("--bound-signed-history", choices=("live", "restart", "fork"),
                          help="核对同一已绑定主档的签名来源及新工具回执")
    scenario.add_argument("--forced-tool-choice-contract",
                          choices=("live", "restart", "restart-metadata-only", "restart-closed-metadata-only"))
    scenario.add_argument("--no-tool-choice-contract", action="store_true")
    scenario.add_argument("--disable-parallel-tool-use-contract", action="store_true")
    scenario.add_argument("--auto-tool-direct-text", action="store_true",
                          help="带两项工具声明的 auto 请求直接返回文本")
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
    scenario.add_argument("--parallel-new-tools", nargs="?", const="live", choices=("live", "restart"),
                          help="核对双工具逆序回执；restart 结束原 CLI 并重启发送器")
    scenario.add_argument("--reconnect-tool-stream", action="store_true")
    scenario.add_argument("--interrupted-tool-stream", nargs="?", const="before-tool",
                          choices=("before-tool", "after-tool-start"),
                          help="截断已开始交付的续轮，按下一工具首帧是否交付核对原回执重试")
    scenario.add_argument("--slow-tool-stream", action="store_true")
    scenario.add_argument("--cancel-and-change-question", action="store_true")
    scenario.add_argument("--cancel-before-response-headers", nargs="?", const="sse", choices=("sse", "json"),
                          help="让首轮在 CLI 启动中取消，核对原预留释放及同账号后续请求")
    scenario.add_argument("--mixed-release", nargs=3, type=Path,
                          metavar=("OLD_SOURCE", "OLD_GATEWAY", "OLD_SENDER"))
    scenario.add_argument("--mixed-image-peers", nargs=2, type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--mixed-context-keep-all", choices=tuple(THINKING_DISPLAY_DEFAULTS),
                        help="混版排空时核对显式 keep:all 的原回执和同会话新轮")
    scenario.add_argument("--failure-boundaries", action="store_true")
    scenario.add_argument("--v1-runtime", type=Path)
    args = parser.parse_args()
    recover_pending_tool = args.recover_pending_tool or args.parallel_new_tools == "restart"
    if args.receipt_auto_tool_choice is not None and (
            args.auto_tool_choice is None or args.auto_tool_choice == args.receipt_auto_tool_choice):
        parser.error("--receipt-auto-tool-choice 需要不同形状的 --auto-tool-choice")
    if args.prior_auto_source is not None and (
            args.interrupted_tool_stream != "before-tool" or args.auto_tool_choice is None
            or recover_pending_tool or args.installed_runtime):
        parser.error("--prior-auto-source 需要 --interrupted-tool-stream before-tool 与 --auto-tool-choice")
    if args.installed_runtime and (args.structured_output_contract not in ("live", "restart")
                                   or args.sender != Path("/usr/local/bin/account-sender")):
        parser.error("--installed-runtime 需要结构化工具轮和镜像内置 account-sender")
    if args.current_image_ending == "image" and not args.current_images:
        parser.error("--current-image-ending 需要同用 --current-images")
    if args.stock_client and args.v1_runtime:
        parser.error("--stock-client 使用 V2 账号")
    if args.message_system_roles in SYSTEM_CONTROL_CONTRACTS and args.v1_runtime:
        parser.error("消息级控制隔离夹具使用 V2 账号")
    if args.cancel_and_change_question and args.v1_runtime:
        parser.error("--cancel-and-change-question 使用 V2 账号")
    if bool(args.interleaved_title) != bool(args.title_request):
        parser.error("--interleaved-title 与 --title-request 需要一起使用")
    if bool(args.interleaved_suggestion) != bool(args.suggestion_request):
        parser.error("--interleaved-suggestion 与 --suggestion-request 需要一起使用")
    auxiliary_mode = args.interleaved_title or args.interleaved_suggestion
    auxiliary_path = args.title_request or args.suggestion_request
    if args.adaptive_thinking_display != "updates" and args.adaptive_thinking_model is None:
        parser.error("--adaptive-thinking-display 需要同用 --adaptive-thinking-model")
    if args.fixed_thinking_model and args.adaptive_thinking_model:
        parser.error("显式固定思考预算和 adaptive 用例须分别运行")
    if args.fixed_thinking_display != "updates" and args.fixed_thinking_model is None:
        parser.error("--fixed-thinking-display 需要同用 --fixed-thinking-model")
    if args.signed_tool_response and not args.signed_tool_history:
        parser.error("--signed-tool-response 需要同用 --signed-tool-history")
    if args.thinking_cli_summaries is not None and not args.thinking_display_contract:
        parser.error("--thinking-cli-summaries 需要同用 --thinking-display-contract")
    thinking_cli_summaries = {"on": True, "off": False}.get(args.thinking_cli_summaries)
    if args.history_cache_ttl and not args.history_cache_markers:
        parser.error("--history-cache-ttl 需要同用 --history-cache-markers")
    if args.history_cache_scope and not args.history_cache_ttl:
        parser.error("--history-cache-scope 需要同用 --history-cache-ttl")
    if args.history_empty_tool_result and (args.history_tool_blocks or args.history_tool_images or args.history_cache_markers):
        parser.error("--history-empty-tool-result 需要独立的历史工具结果形状")
    if args.tool_receipt_nested_cache and not args.tool_receipt_text_blocks:
        parser.error("--tool-receipt-nested-cache 需要同用 --tool-receipt-text-blocks")
    if args.tool_receipt_outer_cache and not args.tool_receipt_text_blocks:
        parser.error("--tool-receipt-outer-cache 需要同用 --tool-receipt-text-blocks")
    if args.trace_recovery_resend and not (recover_pending_tool or args.model_connection_contract == "restart"):
        parser.error("--trace-recovery-resend 需要工具回执恢复场景")
    if (args.recovery_ledger_contention or args.recovery_ledger_deadline or args.recovery_workspace_rejection
        or args.recovery_readiness_rejection or args.recovery_slow_model) and (
        not args.recover_pending_tool or args.signed_tool_history
    ):
        parser.error("恢复故障注入需要可提交的 --recover-pending-tool 原回执")
    if args.replay_unknown_receipt and args.signed_tool_history:
        parser.error("--replay-unknown-receipt 使用普通未签名工具回执")
    if args.replay_unknown_receipt in ("lost-live", "lost") and not args.recover_pending_tool:
        parser.error("--replay-unknown-receipt 的原回复丢失用例需要 --recover-pending-tool")
    if (not Path("/.dockerenv").exists() or {name for _, name in if_nameindex()} != {"lo"}
            or Path("/run/v3/sender.json").exists() or any(Path("/native").glob("*"))):
        raise RuntimeError("请在空白的 docker --network none 账号容器中运行")
    previous = args.mixed_release
    if args.mixed_context_keep_all and not (previous or args.mixed_image_peers):
        parser.error("--mixed-context-keep-all 需要混版排空场景")
    if args.mixed_context_keep_all and (args.fixed_thinking_model or args.adaptive_thinking_model):
        parser.error("混版 keep:all 用例包含固定的自适应思考模式")
    cache_markers = args.cache_markers or args.cache_marker_capabilities is not None
    trace_startup = (args.initial_idle_model_connection or args.trace_initial_startup or args.trace_recovery_resend or cache_markers
                     or args.cancel_before_response_headers is not None
                     or args.stock_client
                     or args.model_connection_contract is not None or bool(args.external_signed_history)
                     or args.bound_signed_history is not None
                     or args.history_tool_images is not None or args.tool_receipt_images is not None
                     or args.history_empty_tool_result is not None or args.empty_tool_receipt is not None
                     or args.tool_receipt_text_blocks is not None
                     or args.explicit_custom_tool_type
                     or args.recovery_readiness_rejection
                     or args.recovery_slow_model
                     or args.replay_unknown_receipt is not None
                     or bool(args.structured_output_contract or args.forced_tool_choice_contract) or args.no_tool_choice_contract
                     or args.disable_parallel_tool_use_contract or bool(args.oauth_rotation or args.provider_quota)
                     or args.slow_tool_stream or args.interrupted_tool_stream is not None
                     or bool(auxiliary_mode or args.agent_progress)
                     or bool(args.thinking_display_contract)
                     or bool(args.fixed_thinking_model and not (previous or args.mixed_image_peers))
                     or (bool(args.message_system_roles) and args.v1_runtime is None))
    if trace_startup and (previous or args.mixed_image_peers or args.v1_runtime):
        parser.error("启动观测需要当前 V2 源码夹具")
    if args.mixed_image_peers:
        if args.shared_state is None:
            parser.error("镜像混跑须使用私有共享夹具目录")
        previous = (None, *args.mixed_image_peers)
    elif args.v1_runtime is None:
        if not args.installed_runtime:
            source_root = previous[0] if previous else args.prior_auto_source or ROOT
            install_source(source_root, trace_startup=trace_startup,
                           cache_capability=args.cache_marker_capabilities, thinking_cli_summaries=thinking_cli_summaries)
    elif sha256(args.v1_runtime.read_bytes()).hexdigest() != V1_RUNTIME_SHA256:
        parser.error("V1 启动器摘要与固定版不符")
    with TemporaryDirectory(prefix="cold-history-", dir=args.shared_state) as directory:
        proof = verify(args.gateway, args.sender, Path(directory),
                       restart_history=args.restart_history, text_input=args.text_input,
                       system_policy=args.system_policy, toggle_pending_policy=args.toggle_pending_policy,
                       stock_client=args.stock_client,
                       tool_policy="replace" if args.bound_signed_history else args.tool_policy,
                       recover_pending=(recover_pending_tool or args.oauth_rotation == "restart"
                                        or args.model_connection_contract == "restart"),
                       model_connection_contract=args.model_connection_contract,
                       external_signed_history=args.external_signed_history,
                       bound_signed_history=args.bound_signed_history,
                       oauth_rotation=bool(args.oauth_rotation), provider_quota=args.provider_quota,
                       output_effort=args.output_effort, history_png=args.history_png,
                       history_images=args.history_images, history_tool_blocks=args.history_tool_blocks,
                       history_tool_images=args.history_tool_images,
                       history_empty_tool_result=args.history_empty_tool_result,
                       empty_tool_receipt=args.empty_tool_receipt,
                       tool_receipt_images=args.tool_receipt_images,
                       tool_receipt_text_blocks=args.tool_receipt_text_blocks,
                       tool_receipt_nested_cache=args.tool_receipt_nested_cache,
                       tool_receipt_outer_cache=args.tool_receipt_outer_cache,
                       explicit_custom_tool_type=args.explicit_custom_tool_type,
                       previous=previous,
                       mixed_context_keep_all=args.mixed_context_keep_all,
                       failure_boundaries=args.failure_boundaries, current_text_blocks=args.current_text_blocks,
                       signed_tool_history=args.signed_tool_history or bool(args.bound_signed_history),
                       signed_tool_response=args.signed_tool_response,
                       split_history_tools=args.split_history_tools,
                       v1_runtime=args.v1_runtime, parallel_tools=args.parallel_new_tools is not None,
                       reconnect_tool_stream=args.reconnect_tool_stream, slow_tool_stream=args.slow_tool_stream,
                       interrupted_tool_stream=args.interrupted_tool_stream,
                       current_images=args.current_images,
                       cancel_and_change_question=args.cancel_and_change_question,
                       cancel_before_response_headers=args.cancel_before_response_headers,
                       current_image_ending=args.current_image_ending,
                       auto_tool_choice=args.auto_tool_choice, receipt_auto_tool_choice=args.receipt_auto_tool_choice,
                       prior_auto_source=args.prior_auto_source,
                       auto_tool_direct_text=args.auto_tool_direct_text,
                       adaptive_thinking_model=args.adaptive_thinking_model,
                       fixed_thinking_model=args.fixed_thinking_model,
                       fixed_thinking_display=args.fixed_thinking_display,
                       adaptive_thinking_display=args.adaptive_thinking_display,
                       thinking_display_model=args.thinking_display_contract,
                       thinking_cli_summaries=thinking_cli_summaries,
                       recovery_ledger_contention=args.recovery_ledger_contention,
                       recovery_ledger_deadline=args.recovery_ledger_deadline,
                       recovery_workspace_rejection=args.recovery_workspace_rejection,
                       recovery_readiness_rejection=args.recovery_readiness_rejection,
                       recovery_slow_model=args.recovery_slow_model,
                       replay_unknown_receipt=args.replay_unknown_receipt,
                       initial_idle_model_connection=args.initial_idle_model_connection, trace_startup=trace_startup,
                       trace_recovery_resend=args.trace_recovery_resend,
                       cache_markers=cache_markers, history_cache_markers=args.history_cache_markers,
                       history_cache_ttl=args.history_cache_ttl, history_cache_scope=args.history_cache_scope,
                       cache_capability=args.cache_marker_capabilities,
                       message_system_roles=args.message_system_roles, structured_output=args.structured_output_contract,
                       installed_runtime=args.installed_runtime,
                       forced_tool_choice=args.forced_tool_choice_contract, no_tool_choice=args.no_tool_choice_contract,
                       disable_parallel_tool_use=args.disable_parallel_tool_use_contract,
                       auxiliary_mode=auxiliary_mode,
                       auxiliary_kind="suggestion" if args.interleaved_suggestion else "title",
                       auxiliary_sample=json.loads(auxiliary_path.read_bytes()) if auxiliary_path else None,
                       agent_progress=json.loads(args.agent_progress.read_bytes()) if args.agent_progress else None)
        print(json.dumps(proof, ensure_ascii=False))


if __name__ == "__main__":
    main()
