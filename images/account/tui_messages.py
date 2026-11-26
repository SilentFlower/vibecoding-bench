"""受管本机推理服务的冻结 Messages 输入和同一响应的原始 SSE 观察。"""

from dataclasses import dataclass
from email.message import Message
import hashlib
import json
import math
import re
from uuid import UUID

from tui_cache_policy import model_body
from tui_input_policy import InputRejection, native_input, validate_api, validate_api_row


BODY_LIMIT = 10 * 1024 * 1024
SIGNATURE_ERROR_BODY_LIMIT = 1024 * 1024
OAUTH_FILE_LIMIT = 8192
MODEL_VERSION_HEADERS = frozenset({"anthropic-version", "anthropic-beta"})
MODEL_PROTOCOL_HEADERS = MODEL_VERSION_HEADERS | {
    "accept",
    "accept-language",
    "cache-control",
    "anthropic-dangerous-direct-browser-access",
    "x-claude-code-prev-tool-durations",
    "x-claude-code-compaction",
    "x-claude-code-context-compacted",
}
# 这三项与 V1 parseInput 一致，客户端设置永远不进入受管进程或本机提供方。
_CLIENT_SETTINGS = {"settings", "env", "claude_settings"}
_HOST_FIELDS = {
    "extra_headers",
    "extra_body",
    "headers",
    "proxy_url",
    "api_key",
    "oauth_token",
    "claude_binary",
    "claude_home",
    "claude_config_dir",
    "workdir",
    "base_url",
    "authorization",
    "model_endpoint",
    "local_bearer",
    "model_headers",
}


def encode(value):
    """编码可重放、严格的 JSON。@param value JSON 值。@return UTF-8 字节。"""
    return json.dumps(
        value, ensure_ascii=False, separators=(",", ":"), allow_nan=False
    ).encode()


def valid_model_header_value(value):
    """校验私有帧中的 HTTP 字节表示。@param value 协议头值。@return 是否可无损发送。"""
    return isinstance(value, str) and all(c == "\t" or 32 <= ord(c) <= 255 and ord(c) != 127 for c in value)


def passive_quota_headers(headers: Message) -> dict[str, str]:
    """提取受管模型的额度证据。@param headers 实际上游响应头。@return 单值额度头。"""
    observed = {}
    # 只接收网关理解的窗口字段，重复值无法作为唯一的官方观测。
    for window in ("5h", "7d", "7d_oi"):
        for field in ("utilization", "reset", "status", "surpassed-threshold"):
            name = f"anthropic-ratelimit-unified-{window}-{field}"
            values = headers.get_all(name, ())
            if len(values) == 1 and values[0] and all(" " <= char <= "~" for char in values[0]):
                observed[name] = values[0]
    return observed


_JSON_SPACE = re.compile(r"[ \t\r\n]*")
_SESSION_HEADER = "x-claude-code-session-id"


def _member_span(text, start, name):
    decoder = json.JSONDecoder()
    cursor = _JSON_SPACE.match(text, start + 1).end()
    while text[cursor] != "}":
        key, end = decoder.raw_decode(text, cursor)
        colon = _JSON_SPACE.match(text, end).end()
        value = _JSON_SPACE.match(text, colon + 1).end()
        if key == name:
            return value
        _, end = decoder.raw_decode(text, value)
        cursor = _JSON_SPACE.match(text, end).end()
        if text[cursor] == ",":
            cursor = _JSON_SPACE.match(text, cursor + 1).end()
    return None


def provider_session(raw, headers, original, target):
    """在受管提供方投递前应用已认证的会话映射。@param raw 已校验正文。
    @param headers 本轮协议选项。@param original 预留原会话。@param target 有效出站会话。
    @return 出站正文和头，保留元数据之外的冻结字节。
    """
    if target is None:
        return raw, headers
    if any(not isinstance(sid, str) or len(sid) != 36 or str(UUID(sid)) != sid.lower()
           for sid in (original, target)):
        raise ValueError("受信来源的会话映射无效")
    headers = {**headers, _SESSION_HEADER: target}
    if original == target:
        return raw, headers
    # 输入已拒绝重复的外层键。只定位 user_id 字符串，避免重编码缓存前缀与历史。
    text = raw.decode()
    start = _JSON_SPACE.match(text).end()
    metadata = _member_span(text, start, "metadata")
    if metadata is None:
        return raw, headers
    user_id = _member_span(text, metadata, "user_id")
    if user_id is None:
        return raw, headers
    user, end = json.JSONDecoder().raw_decode(text, user_id)
    fields = json.loads(user)
    if not isinstance(fields, dict) or fields.get("session_id") != original:
        raise ValueError("出站映射与预留会话不一致")
    replacement = encode(encode({**fields, "session_id": target}).decode())
    return text[:user_id].encode() + replacement + text[end:].encode(), headers


class SubagentCapacityError(ValueError):
    """父链占满硬容量，当前子代理必须显式失败。"""


class SubagentBindingError(ValueError):
    """当前请求没有唯一、未使用且属于该主体的 Agent 工具资格。"""


class SubagentAmbiguousError(SubagentBindingError):
    """同提示工具缺少可核验的原 Agent 配对。"""


class ModelResponseError(RuntimeError):
    """本机模型在首帧前返回的 Messages 错误。@param status 模型 HTTP 状态。@param raw 上游错误正文。"""

    def __init__(
        self, status, raw, *, source=None, retry_after=None, quota_headers=None,
        complete=False, before_send=False,
    ):
        """过滤错误扩展并保存私有观察。@param status 模型 HTTP 状态。@param raw 上游错误正文。
        @param source 受信传输归属。@param retry_after 已核验的退避秒数。
        @param quota_headers 已提取的受管模型额度头。@param complete 提供方确认错误正文完整。
        @param before_send 账号发送器确认未提交模型。@return 无。
        """
        self.status = status if 400 <= status < 600 else 502
        self.source = source
        self.retry_after = retry_after
        self.quota_headers = quota_headers
        self.before_send = before_send
        fallback = {401: "authentication_error", 403: "permission_error", 429: "rate_limit_error"}
        error = {"type": fallback.get(self.status, "api_error"), "message": f"本机模型返回 HTTP {self.status}"}
        try:
            value = json.loads(raw)
        except (ValueError, TypeError):
            value = None
        data = value.get("error") if isinstance(value, dict) else None
        public_fields = (
            isinstance(data, dict)
            and isinstance(data.get("type"), str)
            and isinstance(data.get("message"), str)
        )
        if public_fields:
            error = {"type": data["type"], "message": data["message"]}
        self.body = encode({"type": "error", "error": error})
        if not isinstance(data, dict):
            data = value if isinstance(value, dict) and value.get("type") == "error" else {}
        evidence = {
            key: data[key] for key in ("type", "message", "code", "upstream_code")
            if isinstance(data.get(key), str)
        }
        self.private_body = self.body
        if public_fields and evidence != error:
            self.private_body = encode({"type": "error", "error": evidence})
        elif not public_fields and evidence:
            # 旧网关只交付 error 的公开字段。原始残缺信封只用于新网关判断会话策略。
            self.private_body = encode({
                "type": "error", "error": error, "_tui_policy_evidence": {"error": evidence}
            })
        self.signature_evidence = (
            self.private_body
            if complete and status == 400 and public_fields
            and source in ("local_provider_http", "managed_oauth_http")
            and data["type"] == "invalid_request_error" and "signature" in data["message"].lower()
            and max(len(raw), len(self.private_body)) <= SIGNATURE_ERROR_BODY_LIMIT
            else None
        )
        super().__init__(f"模型返回 HTTP {self.status}")


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Messages 含重复字段")
        result[key] = value
    return result


def _invalid_number(value):
    raise ValueError("Messages 数值无法编码为 JSON")


def _finite(value):
    if type(value) not in (int, float):
        return False
    try:
        return math.isfinite(value)
    except OverflowError:
        return False


@dataclass
class MessageInputObservation:
    """记录账号代发正文可核对的普通 Messages 指令落点。@param instruction_location 已组装的顶层落点。"""

    instruction_location: str | None = None


def input_message(
    raw, *, native=False, body_policy=None, session_id=None,
    observation: MessageInputObservation | None = None,
):
    """核验公开 Messages 业务输入，冻结本轮提供方请求。@param raw 原始字节。
    @param native 原版 CLI 来源线索。@param body_policy 受信预留的本轮设置。@param session_id 网关原会话。
    @param observation 可选，记录实际组装的普通 Messages 顶层业务指令落点。
    @return 带启动参数的原始历史、外层流选项、内部取流正文。
    """
    body = json.loads(raw, object_pairs_hook=_unique, parse_constant=_invalid_number)
    if not isinstance(body, dict):
        raise ValueError("Messages 正文应为对象")
    removed = _CLIENT_SETTINGS.intersection(body)
    for key in removed:
        del body[key]
    native = native_input(body, native)
    if body.keys() & _HOST_FIELDS or ("mcp_servers" in body and (not native or body["mcp_servers"] != [])):
        raise InputRejection("unsupported_parameter")
    if not native:
        validate_api(body, session_id)
        if "metadata" in body:
            # 原会话由网关在准备前从入站解析，业务副本不能把调用方的附加元数据送入模型。
            del body["metadata"]
            removed.add("metadata")
    def invalid(code):
        # 原生正文沿用原有支持边界；普通 API 的结构错误按 V1 分类交还调用方。
        if native:
            raise ValueError("原生 Messages 输入结构无效")
        raise InputRejection(code)

    if not isinstance(body.get("model"), str) or not body["model"].strip():
        invalid("invalid_model")
    if "\x00" in body["model"]:
        raise ValueError("交互进程的模型名含空字节")
    messages = body.get("messages")
    if not isinstance(messages, list) or not messages:
        invalid("invalid_messages")
    has_system_row = False
    for row in messages:
        if not isinstance(row, dict) or row.get("role") not in ("user", "assistant", "system"):
            invalid("invalid_message")
        if not native:
            validate_api_row(row)
        has_system_row |= row["role"] == "system"
        content = row.get("content")
        if isinstance(content, str):
            continue
        if not isinstance(content, list) or not all(isinstance(b, dict) for b in content):
            invalid("invalid_content")
        if any(not isinstance(b.get("type"), str) or not b["type"] for b in content):
            raise ValueError("Messages 内容块缺少类型")
    system = body.get("system", "")
    if not isinstance(system, str):
        if not isinstance(system, list) or not all(isinstance(b, dict) for b in system):
            invalid("invalid_system")
        for block in system:
            # V1 的普通 SDK 仅消费 type/text；显式消息级 system 走原位保留分支。
            if not native and not has_system_row and block.keys() - {"type","text"}:
                raise InputRejection("unsupported_parameter")
            if block.get("type") != "text" or not isinstance(block.get("text"), str):
                invalid("unsupported_parameter")
    tools = body.get("tools", [])
    if not isinstance(tools, list) or not all(isinstance(t, dict) for t in tools):
        invalid("invalid_tools")
    if any(not isinstance(t.get("name"), str) or not t["name"]
           or ("input_schema" not in t and "type" not in t)
           or ("input_schema" in t and not isinstance(t["input_schema"], dict)) for t in tools):
        raise ValueError("Messages 工具声明无效")
    if len({t["name"] for t in tools}) != len(tools):
        raise ValueError("同一请求中出现重复工具名称")
    for key in ("metadata","tool_choice","thinking","output_config","context_management"):
        if key in body and not isinstance(body[key], dict):
            invalid("invalid_parameter")
    for key in ("max_tokens","temperature"):
        if key in body and not _finite(body[key]):
            invalid("invalid_" + key)
    if type(body.get("stream", False)) is not bool:
        invalid("invalid_stream")
    if "safeguards" in body and (
        not isinstance(body["safeguards"], list)
        or not all(isinstance(rule, dict) for rule in body["safeguards"])
    ):
        raise ValueError("原生 safeguards 应为有序对象数组")
    # 整个公开流式请求保持原字节。需要 JSON 的客户端由外层聚合，模型仍然只请求一次。
    stream = body.get("stream", False)
    outgoing = model_body(body, body_policy, native=native)
    if (not native and "context_management" in outgoing and "thinking" in outgoing
            and outgoing["thinking"].get("type") not in ("enabled", "adaptive")
            and any(edit["type"] == "clear_thinking_20251015" for edit in outgoing["context_management"].get("edits", []))):
        # 已知的无效改写应在工具回执认领前拒绝；调用方仍可用有效配置提交同一结果。
        raise InputRejection("unsupported_parameter")
    wire = raw if stream and not removed and outgoing is body else encode({**outgoing, "stream": True})
    if observation is not None and not native:
        system = outgoing.get("system", "")
        texts = (system,) if isinstance(system, str) else (block["text"] for block in system)
        if any(text.strip() for text in texts):
            observation.instruction_location = "system"
    if outgoing.get("thinking") is not body.get("thinking"):
        # 启动器与上游模型共用本轮推理参数；工具校验、子代理归属仍读取原始历史。
        body = {**body, "thinking": outgoing["thinking"]}
    if isinstance(wire, str):
        wire = wire.encode()
    return body, stream, wire


def _blocks(row):
    content = row["content"]
    return [{"type": "text", "text": content}] if isinstance(content, str) else content


def history_digest(messages):
    """与网关相同，只在归属比较中忽略直接内容块的可移动缓存标记。@param messages 历史。
    @return 含顺序、角色及全部内容的散列。
    """
    normalized = [
        {
            **row,
            "content": [
                {k: v for k, v in b.items() if k != "cache_control"}
                for b in _blocks(row)
            ],
        }
        for row in messages
    ]
    return hashlib.sha256(
        json.dumps(
            normalized,
            sort_keys=True,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()


def split_reply(messages):
    """定位最后一条 assistant 和紧随它的 user/system 尾段。@param messages 有序消息。@return 下标与回执。"""
    i = len(messages)
    while i and messages[i - 1]["role"] in ("user", "system"):
        i -= 1
    found = []
    for row in messages[i:]:
        for block in _blocks(row):
            if block["type"] == "tool_result":
                if row["role"] != "user":
                    raise ValueError("工具回执应来自 user 消息")
                found.append(block)
    return i - 1, found


def prompt_text(messages):
    """取得供终端显示的最近用户正文；模型始终消费冻结的完整请求。@param messages 原始消息。@return 终端文本。"""
    for row in reversed(messages):
        if row["role"] == "user":
            for block in reversed(_blocks(row)):
                if (
                    block["type"] == "text"
                    and isinstance(block.get("text"), str)
                    and block["text"]
                ):
                    return block["text"]
    return "客户端已提交结构化消息"


def _snapshot(block):
    # 原文供模型，归属只在进程中保留摘要；大段思考和正文不再复制进等待队列。
    record = {k: v for k, v in block.items() if k != "cache_control"}
    for key in ("text", "thinking", "signature"):
        if key in record and isinstance(record[key], str):
            record[key] = hashlib.sha256(record[key].encode()).hexdigest()
    return record


def receipt_snapshot(block):
    """持久化声明的比较依据。@param block 原生响应快照。@return 含身份及规范摘要的记录。"""
    direct = block.get("type") == "tool_use" and block.get("caller") == {"type": "direct"}
    fields = {k: v for k, v in block.items() if not (direct and k == "caller")}
    raw = json.dumps(fields, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    proof = {"type": block["type"], "digest": hashlib.sha256(raw.encode()).hexdigest()}
    if block["type"] == "tool_use":
        proof.update(id=block["id"], name=block["name"])
    if direct:
        proof["caller"] = {"type": "direct"}
    return proof


def tool_receipts(messages, previous, expected, *, input_format=None, checkpoint=False):
    """完整校验原轮和终端所等待的结果。@param messages 本轮正文。@param previous 原历史摘要。
    @param expected 实际响应块摘要。@param input_format 本轮已识别的客户端布局。
    @param checkpoint 是否使用持久摘要。@return 原 ID 到未改写结果的映射。
    """
    pos, returned = split_reply(messages)
    if (
        pos < 0
        or messages[pos]["role"] != "assistant"
        or history_digest(messages[:pos]) != previous
    ):
        raise ValueError("工具结果不属于原历史")
    offered = [_snapshot(b) for b in _blocks(messages[pos])]
    if checkpoint:
        offered = [receipt_snapshot(b) for b in offered]
    if (input_format == "claude_code" and any(b.get("name") in ("Agent", "Task") for b in expected)
            and all(b["type"] in ("text", "tool_use") for b in expected)
            and [b["type"] for b in offered] != [b["type"] for b in expected]):
        # 2.1.293 把并发工具之间的文本放到工具组前。只重建比较顺序，逐块继续核对。
        expected = [b for b in expected if b["type"] == "text"] + [
            b for b in expected if b["type"] == "tool_use"
        ]
    for block, original in zip(offered, expected):
        if (original.get("type") == "tool_use" and original.get("caller") == {"type": "direct"}
                and "caller" not in block):
            # 只在比较快照里补齐直接调用标记，向模型发送的历史仍沿用客户端正文。
            block["caller"] = original["caller"]
    if offered != expected:
        raise ValueError("原轮助手内容或工具声明发生变化")
    ids = {b["id"] for b in expected if b["type"] == "tool_use"}
    results = {}
    for block in returned:
        tool_id = block.get("tool_use_id")
        if (
            not isinstance(tool_id, str)
            or tool_id not in ids
            or tool_id in results
            or not isinstance(block.get("content", ""), (str, list))
            or type(block.get("is_error", False)) is not bool
        ):
            raise ValueError("工具回执归属或分组无效")
        results[tool_id] = block
    if not ids or set(results) != ids:
        raise ValueError("工具组尚未完整交还")
    return results


def wire_events(response):
    """逐条读取原始 SSE，保留注释、分片、签名和字段。@param response 可信本机模型连接。
    @return (完整原始记录字节, 可选 JSON 事件)。
    """
    record = bytearray()
    payload = []
    while True:
        line = response.readline(BODY_LIMIT + 1 - len(record))
        if not line:
            if record:
                raise ValueError("模型事件在边界之前结束")
            return
        record.extend(line)
        if len(record) > BODY_LIMIT:
            raise ValueError("单条模型事件超过网关流边界")
        field = line.rstrip(b"\r\n")
        if field:
            if field.startswith(b"data:"):
                payload.append(field[5:].removeprefix(b" "))
            continue
        event = None
        if payload and b"\n".join(payload).strip() != b"[DONE]":
            event = json.loads(b"\n".join(payload))
            if not isinstance(event, dict):
                raise ValueError("模型 SSE 的 data 必须为事件")
        yield bytes(record), event
        record.clear()
        payload.clear()


class WireStep:
    """校验一份真实模型响应并记录工具归属。@param tools 公开请求声明的客户端工具。"""

    def __init__(self, tools):
        self.names = {t["name"] for t in tools}
        self._records = []
        self._open = {}
        self._argument_bytes = 0
        self.started = self.stopped = False
        self.reason = None
        self.response_model = None
        self.native = None
        self.native_model = None
        self.claimed = False
        self.terminal_seen = False
        self.final = None
        self.tool_ids = set()
        # 后台回执可晚于进程退出，只保留原步骤标识即可核对等待归属。
        self.offer_group = object()

    @property
    def blocks(self):
        """按提供方的索引返回已结束的内容块，用于原生工具回调与续轮证明。@return 内容块。"""
        return [block for block in self._records if block is not None]

    def observe(self, event):
        """只解析验证与续轮所需字段；原始事件独立交付给两端。@param event SSE 的 JSON。@return 本次完整关闭的块。"""
        if event is None or event.get("type") == "ping":
            return
        kind = event.get("type")
        if self.stopped or kind == "error":
            raise ValueError("模型流报告错误或在终态后继续")
        index = event.get("index")
        if kind in ("content_block_start", "content_block_delta", "content_block_stop") and type(index) is not int:
            raise ValueError("模型内容块索引无效")
        if (
            kind == "message_start"
            and not self.started
            and isinstance(event.get("message"), dict)
        ):
            self.started = True
            model = event["message"].get("model")
            if isinstance(model, str) and model:
                self.response_model = model
        elif not self.started:
            raise ValueError("模型流缺少首帧")
        elif (
            kind == "content_block_start"
            and index == len(self._records)
        ):
            block = event.get("content_block")
            if not isinstance(block, dict) or not isinstance(block.get("type"), str):
                raise ValueError("模型内容块无效")
            if block["type"] == "tool_use":
                if (
                    block.get("name") not in self.names
                    or not isinstance(block.get("id"), str)
                    or not block["id"]
                    or block["id"] in self.tool_ids
                ):
                    raise ValueError("模型工具不属于本轮声明")
                self.tool_ids.add(block["id"])
            hashes = {key: hashlib.sha256(block[key].encode()) for key in ("text", "thinking", "signature")
                      if isinstance(block.get(key), str)}
            # 分片和关闭事件可以交错。每一块单独保留摘要及未结束的参数。
            self._open[index] = (dict(block), hashes, None)
            self._records.append(None)
        elif (
            kind == "content_block_delta"
            and index in self._open
        ):
            active, hashes, arguments = self._open[index]
            delta = event["delta"]
            field = {
                "text_delta": "text",
                "thinking_delta": "thinking",
                "signature_delta": "signature",
            }.get(delta["type"])
            if field:
                if field not in hashes:
                    hashes[field] = hashlib.sha256()
                hashes[field].update(delta[field].encode())
            elif delta["type"] == "input_json_delta":
                chunk = delta["partial_json"].encode()
                self._argument_bytes += len(chunk)
                if self._argument_bytes > BODY_LIMIT:
                    raise ValueError("工具参数超过可续轮的正文上限")
                if arguments is None:
                    arguments = bytearray()
                    self._open[index] = (active, hashes, arguments)
                arguments.extend(chunk)
            elif delta["type"] == "citations_delta":
                if active.get("citations") is None:
                    active["citations"] = []
                active["citations"].append(delta["citation"])
        elif (
            kind == "content_block_stop"
            and index in self._open
        ):
            active, hashes, arguments = self._open.pop(index)
            if arguments is not None:
                active["input"] = json.loads(arguments or b"{}", object_pairs_hook=_unique, parse_constant=_invalid_number)
                if not isinstance(active["input"], dict):
                    raise ValueError("模型工具输入必须是对象")
            for key, digest in hashes.items():
                active[key] = digest.hexdigest()
            self._records[index] = active
            return active
        elif kind == "message_delta" and not self._open:
            self.reason = event.get("delta", {}).get("stop_reason", self.reason)
        elif kind == "message_stop" and not self._open and self.reason:
            if self.reason == "tool_use" and not self.tool_ids:
                raise ValueError("工具终态缺少原工具组")
            self.stopped = True
        else:
            raise ValueError("模型流的边界或顺序无效")
