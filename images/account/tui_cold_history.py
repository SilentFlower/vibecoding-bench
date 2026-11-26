"""固定 2.1.293 交互 CLI 的普通 Messages 历史导入与受管 MCP 描述。"""

from base64 import b64decode
from contextlib import ExitStack
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from itertools import chain, islice, zip_longest
from pathlib import Path
import re
from struct import unpack_from
from tempfile import TemporaryDirectory
from uuid import uuid4

from runtime_files import atomic_text
from tui_cache_policy import model_body
from tui_messages import encode
from tui_reconnect import digest
from tui_workspace_launch import WorkspaceLaunchObservation, publish_workspace_history


MCP_SERVER = "flower"
MCP_PREFIX = f"mcp__{MCP_SERVER}__"
RESUME_PROMPT = "Continue from where you left off."
IMPORT_BOUNDARY = "flower2apiImportBoundary"
SIGNED_THINKING_TYPES = ("thinking", "redacted_thinking")
_IMAGE_HEADERS = {
    "image/png": (b"\x89PNG\r\n\x1a\n",),
    "image/jpeg": (b"\xff\xd8\xff",),
    "image/gif": (b"GIF87a", b"GIF89a"),
    "image/webp": (b"RIFF",),
}
# 固定 CLI 的文件粘贴超出像素或字节边界会重采样或重编码。已有历史不经过粘贴。
_MAX_PASTE_IMAGE_EDGE = 2000
_MAX_PASTE_IMAGE_BYTES = 512_000


def _blocks(row):
    content = row["content"]
    return [{"type": "text", "text": content}] if isinstance(content, str) else content


def _plain_text(block):
    return (block.keys() == {"type", "text"} and block["type"] == "text"
            and isinstance(block["text"], str) and bool(block["text"]))


def _history_text(block):
    if "cache_control" not in block:
        return _plain_text(block)
    marker = block["cache_control"]
    return (_plain_text({key: value for key, value in block.items() if key != "cache_control"})
            and isinstance(marker, dict) and marker.keys() <= {"type", "ttl"}
            and marker.get("type") == "ephemeral" and marker.get("ttl", "5m") in ("5m", "1h"))


def _jpeg_dimensions(data):
    offset = 2
    while offset + 4 <= len(data) and data[offset] == 0xff:
        marker = data[offset + 1]
        if marker == 0xff:
            offset += 1
            continue
        if marker in (0xd9, 0xda):
            break
        size, = unpack_from(">H", data, offset + 2)
        if size < 2 or offset + 2 + size > len(data):
            break
        # 只从开始帧读取尺寸。应用数据里的相同字节可能属于 EXIF 或其他元数据。
        if 0xc0 <= marker <= 0xcf and marker not in (0xc4, 0xc8, 0xcc) and size >= 8:
            height, width = unpack_from(">HH", data, offset + 5)
            return width, height
        offset += 2 + size
    return None


def _image_dimensions(media_type, data):
    if media_type == "image/png" and len(data) >= 24 and data[12:16] == b"IHDR":
        return unpack_from(">II", data, 16)
    if media_type == "image/gif" and len(data) >= 10:
        return unpack_from("<HH", data, 6)
    if media_type == "image/jpeg":
        return _jpeg_dimensions(data)
    if media_type == "image/webp":
        chunk = data[12:16]
        if chunk == b"VP8X" and len(data) >= 30:
            return int.from_bytes(data[24:27], "little") + 1, int.from_bytes(data[27:30], "little") + 1
        if chunk == b"VP8L" and len(data) >= 25 and data[20] == 0x2f:
            packed, = unpack_from("<I", data, 21)
            return (packed & 0x3fff) + 1, ((packed >> 14) & 0x3fff) + 1
        if chunk == b"VP8 " and len(data) >= 30 and data[23:26] == b"\x9d\x01\x2a":
            width, height = unpack_from("<HH", data, 26)
            return width & 0x3fff, height & 0x3fff
    return None


def _inline_image(block, *, for_paste=False):
    if block.keys() != {"type", "source"} or block["type"] != "image":
        return False
    source = block["source"]
    if (not isinstance(source, dict) or source.keys() != {"type", "media_type", "data"}
            or source["type"] != "base64" or not isinstance(source["media_type"], str)
            or source["media_type"] not in _IMAGE_HEADERS
            or not isinstance(source["data"], str)):
        return False
    try:
        decoded = b64decode(source["data"], validate=True)
    except ValueError:
        return False
    media_type = source["media_type"]
    if not decoded.startswith(_IMAGE_HEADERS[media_type]) or (media_type == "image/webp" and decoded[8:12] != b"WEBP"):
        return False
    if not for_paste:
        return True
    if len(decoded) > _MAX_PASTE_IMAGE_BYTES:
        return False
    dimensions = _image_dimensions(media_type, decoded)
    return dimensions is not None and all(0 < side <= _MAX_PASTE_IMAGE_EDGE for side in dimensions)


def _result_blocks(content, *, allow_images):
    return isinstance(content, list) and all(
        isinstance(block, dict) and (_history_text(block) or (allow_images and _inline_image(block)))
        for block in content
    )


def tool_result_has_images(block):
    """识别结果中的图片块。@param block 工具结果。@return 是否包含图片。"""
    content = block.get("content")
    return isinstance(content, list) and any(isinstance(nested, dict) and nested.get("type") == "image"
                                             for nested in content)


def tool_result_is_empty(block):
    """识别无内容的工具结果。@param block 已核对的工具结果。@return 内容是否缺省、为空串或为空数组。"""
    return block.get("content", "") in ("", [])


def _historical_image_results(rows):
    return [(row["role"], block) for row in rows for block in _blocks(row)
            if block.get("type") == "tool_result" and tool_result_has_images(block)]


def _matches_history_results(native, expected):
    if not expected:
        return True
    ids = {block["tool_use_id"] for _, block in expected}
    observed = [(row["role"], block) for row in native["messages"] for block in _blocks(row)
                if block.get("type") == "tool_result" and block.get("tool_use_id") in ids]
    return observed == expected


def _marked_blocks(content):
    for index, block in enumerate(content):
        if "cache_control" in block:
            yield index, None, None, block
        nested = block.get("content")
        if block.get("type") == "tool_result" and isinstance(nested, list):
            for offset, inner in enumerate(nested):
                if isinstance(inner, dict) and "cache_control" in inner:
                    yield index, offset, block.get("tool_use_id"), inner


def _history_with_ttl(history, cache_ttl):
    if cache_ttl == "off":
        return history
    # 账号 TTL 只重写直接标记。工具结果内层标记沿原发送策略保留。
    return model_body({"messages": history}, {"sub2api": False, "ttl": cache_ttl, "adaptive": False},
                      native=False)["messages"]


def _automatic_tools(choice):
    return (isinstance(choice, dict) and choice.get("type") == "auto"
            and choice.keys() <= {"type", "disable_parallel_tool_use"}
            and choice.get("disable_parallel_tool_use", False) is False)


def _signed_thinking(block):
    if block["type"] == "redacted_thinking":
        return block.keys() == {"type", "data"} and isinstance(block.get("data"), str) and bool(block["data"])
    return (block["type"] == "thinking" and block.keys() == {"type", "thinking", "signature"}
            and isinstance(block.get("thinking"), str) and isinstance(block.get("signature"), str)
            and bool(block["signature"]))


def _closed_history(rows, *, result_types=(str,), signed_rows=()):
    pending, seen, results = set(), set(), set()
    for index, row in enumerate(rows):
        for block in _blocks(row):
            if (_history_text(block) or (row["role"] == "user" and _inline_image(block))
                    or (index in signed_rows and row["role"] == "assistant" and _signed_thinking(block))):
                continue
            if (row["role"] == "assistant" and block.get("type") == "tool_use"
                    and block.keys() == {"type", "id", "name", "input"}
                    and isinstance(block["id"], str) and block["id"]
                    and block["id"] not in seen and isinstance(block["name"], str)
                    and isinstance(block["input"], dict)):
                seen.add(block["id"])
                pending.add(block["id"])
            elif (row["role"] == "user" and block.get("type") == "tool_result"
                    and block.keys() <= {"type", "tool_use_id", "content", "is_error"}
                    and isinstance(block.get("tool_use_id"), str)
                    and block["tool_use_id"] not in results
                    and (isinstance(block.get("content", ""), result_types)
                         # 固定 CLI 会移除错误工具结果中的图像，并将原文本块合并。
                         or _result_blocks(block.get("content"), allow_images=not block.get("is_error", False)))
                    and type(block.get("is_error", False)) is bool):
                results.add(block["tool_use_id"])
            else:
                return False
        if row["role"] == "user" and (index + 1 == len(rows) or rows[index + 1]["role"] != "user"):
            # Messages 将相邻同角色消息视为同一轮。整组历史回传闭合后才推进到下一助理轮。
            if results != pending:
                return False
            pending.clear()
            results.clear()
    return not pending


@dataclass(frozen=True)
class ColdHistory:
    """记录已确认的普通输入、当前内容以及该会话的 MCP 工具映射。"""

    history: list
    model: str
    prompt: str
    system: str | None
    tools: dict
    max_tokens: int
    thinking: dict | None
    system_policy: str
    effort: str | None = None
    current_blocks: tuple[dict, ...] = ()
    tool_choice: dict | None = None
    cache_ttl: str = "off"
    recovered_models: tuple[tuple[int, str], ...] = ()

    @classmethod
    def from_request(cls, body, system_policy="append", *, cache_ttl="off"):
        """识别普通文本、内嵌图像及受支持的闭合历史。
        @param body 已校验的请求。@param system_policy 本轮冻结的账号系统指令动作。
        @param cache_ttl 经账号预留核对的平台 TTL。强制模式仅承接已有历史断点。
        @return 原生输入计划或空。
        """
        if body.keys() - {"model", "max_tokens", "thinking", "system", "messages", "tools", "stream", "output_config",
                          "tool_choice"}:
            return None
        if type(body.get("max_tokens")) is not int or body["max_tokens"] <= 0:
            return None
        thinking = body.get("thinking")
        if thinking not in (None, {"type": "disabled"}):
            # 只接受固定 CLI 能原样生成的显式显示模式。
            if (body["model"] not in ("claude-sonnet-4-6", "claude-opus-5-5")
                    or thinking not in ({"type": "adaptive", "display": "updates"},
                                        {"type": "adaptive", "display": "summarized"})):
                return None
        output = body.get("output_config", {})
        if not isinstance(output, dict) or output and (
                output.keys() != {"effort"} or output["effort"] not in ("low", "medium", "high", "max")):
            return None
        *history, current = body["messages"]
        if (current["role"] != "user" or (history and history[0]["role"] != "user")
                or any(row["role"] not in ("user", "assistant") or not _blocks(row) for row in history)
                or not _closed_history(history)):
            return None
        content = _blocks(current)
        if not content or not all(_plain_text(block) or _inline_image(block, for_paste=True) for block in content):
            return None
        effective_history = _history_with_ttl(history, cache_ttl)
        cache_blocks = [block for row in effective_history for _, _, _, block in _marked_blocks(_blocks(row))]
        if cache_ttl != "off" and not cache_blocks:
            return None
        if cache_blocks:
            # 断点只出现在已确认历史。当前图像仍须通过独立的原生粘贴边界。
            if len(cache_blocks) > 4:
                return None
            ttls = [block["cache_control"].get("ttl", "5m") for block in cache_blocks]
            if ttls != sorted(ttls, key=lambda ttl: ttl != "1h"):
                return None
        declared = body.get("tools", [])
        choice = body.get("tool_choice")
        if "tool_choice" in body and not (_automatic_tools(choice) if declared else choice == {"type": "none"}):
            return None
        for tool in declared:
            if (tool.keys() - {"type", "name", "input_schema", "description"}
                    or tool.get("type", "custom") != "custom"
                    or not re.fullmatch(r"[A-Za-z0-9_-]+", tool["name"])
                    or not isinstance(tool.get("description", ""), str)
                    or "input_schema" not in tool):
                return None
        system = body.get("system")
        if isinstance(system, list):
            if any(block.keys() != {"type", "text"} for block in system):
                return None
            system = "\n".join(block["text"] for block in system)
        if system_policy != "replace":
            system = system or ""
        tools = {MCP_PREFIX + tool["name"]: tool for tool in declared}
        return cls(history, body["model"], content[0].get("text", ""), system, tools, body["max_tokens"],
                   thinking, system_policy, output.get("effort"),
                   tuple(content) if len(content) > 1 or content[0]["type"] == "image" else (), choice, cache_ttl)

    def system_argument(self):
        """选择原生 CLI 提示词文件选项。@return 参数和文件正文，或缺省值。"""
        if self.system_policy == "replace" and self.system is not None:
            return "--system-prompt-file", self.system
        if self.system_policy == "append" and self.system:
            return "--append-system-prompt-file", self.system
        return None

    def observed_instruction_location(self, native):
        """在固定 CLI 已组装的正文中核对普通顶层业务指令。
        @param native 同次认领的 CLI 请求对象。@return 已匹配的角色落点，或未观测。
        """
        if not self.system or not self.system.strip():
            return None
        if self.system_policy != "user_reminder":
            root = native.get("system")
            if isinstance(root, str):
                texts = (root,)
            elif isinstance(root, list):
                texts = (block.get("text") for block in root
                         if isinstance(block, dict) and block.get("type") == "text")
            else:
                return None
            # 固定 CLI 将追加文件接到原生系统文本末尾，中间使用双换行。
            suffix = "\n\n" + self.system if self.system_policy == "append" else None
            for text in texts:
                if text == self.system or (suffix and isinstance(text, str) and text.endswith(suffix)):
                    return "system"
            return None
        # 当前单文本可能整体提交到 CLI。历史和分块提交使用独立的提醒块。
        reminder = self._reminder()
        expected = {reminder, reminder + "\n"}
        if not self.history and not self.current_blocks:
            submitted = self.submitted_prompt()
            expected.update((submitted, submitted + "\n"))
        for row in native["messages"]:
            if isinstance(row, dict) and row.get("role") == "user" and isinstance(row.get("content"), (str, list)):
                for block in _blocks(row):
                    if (isinstance(block, dict) and block.get("type") == "text" and
                            isinstance(text := block.get("text"), str) and text in expected):
                        return "user_reminder"
        return None

    def submitted_prompt(self):
        """取得单文本提交内容。@return 正文，必要时包含用户提醒。"""
        if self._reminder_index() == len(self.history):
            return f"{self.prompt}\n\n{self._reminder()}"
        return self.prompt

    def submitted_blocks(self):
        """取得原生用户行的有序内容块。@return 本轮图文，以及适用的用户提醒。"""
        if not self.current_blocks:
            return [{"type": "text", "text": self.submitted_prompt()}]
        blocks = list(self.current_blocks)
        if self._reminder_index() == len(self.history):
            blocks.append({"type": "text", "text": self._reminder()})
        return blocks

    def _scope(self):
        scope = (self.model, self.system_policy, self.system, self.tools, self.max_tokens, self.thinking)
        # 缺省沿用既有工作区和等待回执的摘要。
        if self.effort is not None:
            scope = (*scope, self.effort)
        if self.tool_choice is not None:
            scope = (*scope, self.tool_choice)
        if self.recovered_models:
            scope = (*scope, self.recovered_models)
        return scope if self.cache_ttl == "off" else (*scope, self.cache_ttl)

    def matches_tool_choice(self, native):
        """核对显式工具选择及并行许可。@param native CLI 已生成的请求。@return 是否维持原选择。"""
        if self.tool_choice is None:
            return True
        if self.tool_choice == {"type": "none"}:
            # Messages 无工具时缺省选择为 none，须一并核对 CLI 没有添加任何工具。
            return native.get("tools", []) == [] and native.get("tool_choice", self.tool_choice) == self.tool_choice
        # 有工具声明时，Messages 省略 tool_choice 表示 auto 并允许并行调用。
        tools = native.get("tools")
        return isinstance(tools, list) and bool(tools) and _automatic_tools(native.get("tool_choice", {"type": "auto"}))

    def receipt_boundary(self):
        """冻结必须随原工具回执复用的根轮输入。@return 不含客户原文的边界。"""
        current = self.current_blocks or self.prompt
        if self.current_blocks and all(block["type"] == "text" for block in self.current_blocks):
            # 已签发的纯文本多块回执仍沿用原摘要。
            current = tuple(block["text"] for block in self.current_blocks)
        return {
            "prompt_index": len(self.history) + 1,
            "system_policy": self.system_policy,
            "digest": digest([self._scope(), self.history, current]),
        }

    @classmethod
    def from_receipt_boundary(cls, body, boundary):
        """从持久摘要恢复已冻结的根轮。@param body 回执原始输入。@param boundary 原生根轮边界。@return 已匹配计划或空。"""
        root = {**body, "messages": body["messages"][:boundary["prompt_index"]]}
        # TTL 已参与旧摘要。按私有协议的三个取值核对原始输入，持久格式继续兼容已有回执。
        for ttl in ("off", "5m", "1h"):
            plan = cls.from_request(root, boundary["system_policy"], cache_ttl=ttl)
            if plan is not None and plan.receipt_boundary() == boundary:
                return plan
        return None

    def resume_receipts(self, messages, *, signed_tool_models=None):
        """将已认领的原生工具组纳入恢复历史。
        @param messages 已核对原历史、调用和回执的完整公开消息。
        @param signed_tool_models 账号亲自观测并按工具 ID 保存的模型名。@return 本次原生恢复计划。
        """
        history = []
        for index, row in enumerate(messages):
            role = row["role"]
            if role not in ("user", "assistant"):
                return None
            content = _blocks(row)
            if role == "assistant" and index > len(self.history):
                renamed = []
                for block in content:
                    if block["type"] == "tool_use":
                        name = MCP_PREFIX + block["name"]
                        if name not in self.tools:
                            return None
                        block = {**block, "name": name}
                    renamed.append(block)
                content = renamed
            if role == "user":
                # 原生历史会保留成功结果的内嵌图文。CLI 会剥掉错误结果的图片。
                if any(block["type"] == "tool_result" and tool_result_has_images(block)
                       and not _result_blocks(block["content"], allow_images=not block.get("is_error", False))
                       for block in content):
                    return None
            if history and history[-1]["role"] == role:
                history[-1]["content"] += content
            else:
                history.append({"role": role, "content": list(content)})
        models = {}
        if signed_tool_models:
            for index, row in enumerate(history):
                content = row["content"]
                if row["role"] != "assistant" or not any(block["type"] in SIGNED_THINKING_TYPES for block in content):
                    continue
                reported = {signed_tool_models.get(block["id"]) for block in content if block["type"] == "tool_use"}
                if len(reported) != 1:
                    return None
                (model,) = reported
                if not isinstance(model, str) or not model:
                    return None
                models[index] = model
        if not _closed_history(history, result_types=(str, list), signed_rows=models):
            return None
        # 交互 CLI 从闭合的工具结果开始读取。新模型步骤仍由受管 PTY 标记认领。
        return replace(self, history=history, prompt=RESUME_PROMPT, current_blocks=(),
                       recovered_models=tuple(models.items()))

    def matches_recovered_signatures(self, native):
        """核对原生出站是否保留已认证的签名及工具组。@param native CLI 正文。@return 核对结果。"""
        if not self.recovered_models:
            return True

        def signed_groups(rows):
            groups, current = [], []
            for row in rows:
                if row["role"] == "assistant":
                    current.extend(_blocks(row))
                elif current:
                    groups.append(current)
                    current = []
            if current:
                groups.append(current)
            return [[block["id"] if block["type"] == "tool_use" else block for block in content
                     if block["type"] in (*SIGNED_THINKING_TYPES, "tool_use")]
                    for content in groups if any(block["type"] in SIGNED_THINKING_TYPES for block in content)]

        return signed_groups(native["messages"]) == signed_groups(self.history)

    def _reminder(self):
        return f"<system-reminder>\n{self.system}\n</system-reminder>"

    def _reminder_index(self):
        if self.system_policy != "user_reminder" or not self.system:
            return None
        for index, row in enumerate(self.history):
            if row["role"] == "user" and all(block["type"] != "tool_result" for block in _blocks(row)):
                return index
        return len(self.history)

    def _grouped_history(self):
        reminder_index = self._reminder_index()
        history = []
        for index, row in enumerate(_history_with_ttl(self.history, self.cache_ttl)):
            blocks = _blocks(row)
            if index == reminder_index:
                blocks = [*blocks, {"type": "text", "text": self._reminder()}]
            if history and history[-1][0] == row["role"]:
                # 固定 CLI 逐行检查工具配对。同一完整工具组必须在原生一轮中载入。
                history[-1][1].extend(blocks)
            else:
                history.append((row["role"], list(blocks)))
        return history

    def has_history_cache_markers(self):
        """检查已确认的历史是否带显式缓存标记。@return 是否需关闭 CLI 自动断点。"""
        return any(marker for row in self.history for marker in _marked_blocks(_blocks(row)))

    def matches_history_tool_images(self, native):
        """核对旧工具图文结果。@param native CLI 实际正文。@return 已确认图文仍按原工具 ID 交付。"""
        return _matches_history_results(native, _historical_image_results(self.history))

    def matches_history_empty_tool_results(self, native):
        """核对历史及纳入恢复记录的空结果。@param native CLI 实际正文。@return 原结果块是否保留。"""
        expected = [(row["role"], block) for row in self.history for block in _blocks(row)
                    if block.get("type") == "tool_result" and tool_result_is_empty(block)]
        return _matches_history_results(native, expected)

    def matches_history_cache_markers(self, native):
        """核对原生出站的历史断点。@param native CLI 实际生成的请求。@return 原位置与标记是否完整保留。"""
        if not self.has_history_cache_markers():
            return True

        history = self._grouped_history()

        def positions(rows):
            return [(index, role, offset, inner, tool_id, block) for index, (role, content) in enumerate(rows)
                    for offset, inner, tool_id, block in _marked_blocks(content)
                    # 新工具回传中的嵌套字段有自己的回执合同。这里只冻结已确认前缀内的嵌套断点。
                    if inner is None or (index < len(history) and offset < len(history[index][1]))]

        # 自动断点关闭后只允许已确认的历史标记。按消息和块位置匹配可区分重复文本。
        return ("cache_control" not in native
                and not any("cache_control" in block for field in ("system", "tools")
                            for block in native.get(field, []) if isinstance(block, dict))
                and positions((row["role"], _blocks(row)) for row in native["messages"])
                == positions(history))

    def import_session(
        self, config, work, native_id, *, replay_resources: ExitStack | None = None,
        observation: WorkspaceLaunchObservation | None = None,
    ):
        """在已绑定的工作区选择新会话或发布已完成的外部历史。
        @param config 私有配置。@param work 已核验工作目录。@param native_id 绑定的原生会话。
        @param replay_resources 可选，交互进程退出后清理本轮使用的临时确认前缀。
        @param observation 可选，本轮使用外部输入发布历史时更新本机来源。
        @return 本次启动的原生会话 UUID，或 UUID 与本轮临时确认前缀。
        """
        history = self._grouped_history()

        boundary = digest((*self._scope(), history))

        def replay(rows, session_id):
            kept = list(islice(rows, len(history)))
            if not self._matches_history(iter(kept), history, boundary):
                return None
            question = next(rows, {}).get("message", {})
            if (not isinstance(question, dict) or question.get("role") != "user" or "content" not in question
                    or _blocks(question) != self.submitted_blocks()):
                return None
            last = {}
            for row in rows:
                last = row.get("message", {})
            if (not isinstance(last, dict) or last.get("role") != "assistant"
                    or last.get("stop_reason") in (None, "tool_use")):
                return None
            # 固定版 CLI 会向 --resume 的目标追加。本轮只携带客户端确认的前缀，原档案保持原字节。
            directory = replay_resources.enter_context(TemporaryDirectory(prefix="history-replay-", dir=config))
            path = Path(directory) / (session_id + ".jsonl")
            for row, (role, content) in zip(kept, history, strict=True):
                row["message"] = {"role": role, "content": content}
            atomic_text(path, "".join(encode(row).decode() + "\n" for row in kept), replace=False)
            return path

        return publish_workspace_history(
            config, work, native_id, lambda rows: self._matches_history(rows, history, boundary),
            (lambda session_id: self._transcript(work, session_id, history, boundary)) if history else None,
            boundary=boundary, replay=replay if history and replay_resources is not None else None,
            observation=observation,
        )

    def _matches_history(self, rows, history, boundary):
        first = next(rows)
        # 旧导入文件只记录了当时使用的请求模型。按原条件读回，保留已存在的文件。
        legacy = IMPORT_BOUNDARY not in first
        matches = legacy or first[IMPORT_BOUNDARY] == boundary
        models = dict(self.recovered_models)
        parent = None
        for index, (row, expected) in enumerate(zip_longest(chain((first,), rows), history)):
            # 直接恢复要求文件正好停在确认边界。本轮问题由新轮提交。
            if row is None or expected is None or row["type"] != expected[0]:
                matches = False
                continue
            message = row.get("message", {})
            if (row.get("parentUuid") != parent or not isinstance(row.get("uuid"), str)
                    or (message.get("role"), message.get("content")) != expected
                    or index in models and message.get("model") != models[index]
                    or legacy and row["type"] == "assistant" and message.get("model") != self.model):
                matches = False
            parent = row.get("uuid")
        return matches

    def _transcript(self, work, session_id, history, boundary):
        timestamp = datetime.now(timezone.utc).isoformat()
        parent = None
        rows = []
        models = dict(self.recovered_models)
        for index, (role, content) in enumerate(history):
            uid = str(uuid4())
            message = {"role": role, "content": content}
            if index in models:
                # 2.1.293 需要真实助手模型来读取已签名的工具组。
                message["model"] = models[index]
            record = {
                "parentUuid": parent, "uuid": uid, "sessionId": session_id, "cwd": str(work),
                "type": role, "message": message, "isSidechain": False,
                "userType": "external", "timestamp": timestamp,
            }
            if parent is None:
                # 本轮设置的摘要属于导入记录，不是历史消息的模型或用量。
                record[IMPORT_BOUNDARY] = boundary
            rows.append(encode(record).decode())
            parent = uid
        return "\n".join(rows) + "\n"

    def mcp(self, data):
        """应答已授权 CLI 的 MCP 握手和工具声明。@param data MCP 请求。@return 响应对象或通知的空值。"""
        if not isinstance(data, dict) or data.get("jsonrpc") != "2.0":
            raise ValueError("无效的受管 MCP 请求")
        method = data.get("method")
        if isinstance(method, str) and method.startswith("notifications/") and "id" not in data:
            return None
        reply = {"jsonrpc": "2.0", "id": data["id"]}
        if method == "initialize":
            reply["result"] = {"protocolVersion": "2025-03-26",
                               "capabilities": {"tools": {}},
                               "serverInfo": {"name": MCP_SERVER, "version": "1"}}
        elif method == "tools/list":
            reply["result"] = {"tools": [
                {"name": name.removeprefix(MCP_PREFIX), "description": tool.get("description", ""),
                 "inputSchema": tool["input_schema"]} for name, tool in self.tools.items()
            ]}
        elif method == "ping":
            reply["result"] = {}
        else:
            # 原调用 ID 只由受管 Mod 和工具回执账本核对。MCP 回调没有独立执行权限。
            reply["error"] = {"code": -32601, "message": "工具由客户端执行"}
        return reply
