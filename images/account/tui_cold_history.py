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
from tui_messages import encode
from tui_reconnect import digest
from tui_workspace_launch import publish_workspace_history


MCP_SERVER = "flower"
MCP_PREFIX = f"mcp__{MCP_SERVER}__"
RESUME_PROMPT = "Continue from where you left off."
IMPORT_BOUNDARY = "flower2apiImportBoundary"
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


def _text_result_blocks(content):
    return isinstance(content, list) and bool(content) and all(
        isinstance(block, dict) and _plain_text(block) for block in content
    )


def _automatic_tools(choice):
    return (isinstance(choice, dict) and choice.get("type") == "auto"
            and choice.keys() <= {"type", "disable_parallel_tool_use"}
            and choice.get("disable_parallel_tool_use", False) is False)


def _closed_history(rows, *, result_types=(str,)):
    pending, seen, results = set(), set(), set()
    for index, row in enumerate(rows):
        for block in _blocks(row):
            if _plain_text(block) or (row["role"] == "user" and _inline_image(block)):
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
                    and (isinstance(block.get("content"), result_types)
                         or _text_result_blocks(block.get("content")))
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

    @classmethod
    def from_request(cls, body, system_policy="append"):
        """识别普通文本、内嵌图像及受支持的闭合历史。
        @param body 已校验的请求。@param system_policy 本轮冻结的账号系统指令动作。
        @return 原生输入计划或空。
        """
        if body.keys() - {"model", "max_tokens", "thinking", "system", "messages", "tools", "stream", "output_config",
                          "tool_choice"}:
            return None
        if type(body.get("max_tokens")) is not int or body["max_tokens"] <= 0:
            return None
        if body.get("thinking") not in (None, {"type": "disabled"}):
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
        declared = body.get("tools", [])
        choice = body.get("tool_choice")
        if "tool_choice" in body and (not declared or not _automatic_tools(choice)):
            return None
        for tool in declared:
            if (tool.keys() - {"name", "input_schema", "description"}
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
                   body.get("thinking"), system_policy, output.get("effort"),
                   tuple(content) if len(content) > 1 or content[0]["type"] == "image" else (), choice)

    def system_argument(self):
        """选择原生 CLI 提示词文件选项。@return 参数和文件正文，或缺省值。"""
        if self.system_policy == "replace" and self.system is not None:
            return "--system-prompt-file", self.system
        if self.system_policy == "append" and self.system:
            return "--append-system-prompt-file", self.system
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
        return scope if self.tool_choice is None else (*scope, self.tool_choice)

    def matches_tool_choice(self, native):
        """核对显式自动工具选择及并行许可。@param native CLI 已生成的请求。@return 是否维持原选择。"""
        # 有工具声明时，Messages 省略 tool_choice 表示 auto 并允许并行调用。
        if self.tool_choice is None:
            return True
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

    def resume_receipts(self, messages):
        """将已认领的原生工具组纳入恢复历史。
        @param messages 已核对原历史、调用和回执的完整公开消息。@return 本次原生恢复计划。
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
                content = [{**block, "content": block.get("content", "")} if block["type"] == "tool_result"
                           else block for block in content]
            if history and history[-1]["role"] == role:
                history[-1]["content"] += content
            else:
                history.append({"role": role, "content": list(content)})
        if not _closed_history(history, result_types=(str, list)):
            return None
        # 交互 CLI 从闭合的工具结果开始读取。新模型步骤仍由受管 PTY 标记认领。
        return replace(self, history=history, prompt=RESUME_PROMPT, current_blocks=())

    def _reminder(self):
        return f"<system-reminder>\n{self.system}\n</system-reminder>"

    def _reminder_index(self):
        if self.system_policy != "user_reminder" or not self.system:
            return None
        for index, row in enumerate(self.history):
            if row["role"] == "user" and all(block["type"] != "tool_result" for block in _blocks(row)):
                return index
        return len(self.history)

    def import_session(self, config, work, native_id, *, replay_resources: ExitStack | None = None):
        """在已绑定的工作区选择新会话或发布已完成的外部历史。
        @param config 私有配置。@param work 已核验工作目录。@param native_id 绑定的原生会话。
        @param replay_resources 可选，交互进程退出后清理本轮使用的临时确认前缀。
        @return 本次启动的原生会话 UUID，或 UUID 与本轮临时确认前缀。
        """
        reminder_index = self._reminder_index()
        history = []
        for index, row in enumerate(self.history):
            blocks = _blocks(row)
            if index == reminder_index:
                blocks = [*blocks, {"type": "text", "text": self._reminder()}]
            if history and history[-1][0] == row["role"]:
                # 固定 CLI 逐行检查工具配对。同一完整工具组必须在原生一轮中载入。
                history[-1][1].extend(blocks)
            else:
                history.append((row["role"], list(blocks)))

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
        )

    def _matches_history(self, rows, history, boundary):
        first = next(rows)
        # 旧导入文件只记录了当时使用的请求模型。按原条件读回，保留已存在的文件。
        legacy = IMPORT_BOUNDARY not in first
        matches = legacy or first[IMPORT_BOUNDARY] == boundary
        parent = None
        for row, expected in zip_longest(chain((first,), rows), history):
            # 直接恢复要求文件正好停在确认边界。本轮问题由新轮提交。
            if row is None or expected is None or row["type"] != expected[0]:
                matches = False
                continue
            message = row.get("message", {})
            if (row.get("parentUuid") != parent or not isinstance(row.get("uuid"), str)
                    or (message.get("role"), message.get("content")) != expected
                    or legacy and row["type"] == "assistant" and message.get("model") != self.model):
                matches = False
            parent = row.get("uuid")
        return matches

    def _transcript(self, work, session_id, history, boundary):
        timestamp = datetime.now(timezone.utc).isoformat()
        parent = None
        rows = []
        for role, content in history:
            uid = str(uuid4())
            record = {
                "parentUuid": parent, "uuid": uid, "sessionId": session_id, "cwd": str(work),
                "type": role, "message": {"role": role, "content": content}, "isSidechain": False,
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
