"""固定 2.1.293 交互 CLI 的普通 Messages 历史导入与受管 MCP 描述。"""

from base64 import b64decode
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from itertools import zip_longest
import re
from uuid import uuid4

from tui_messages import encode
from tui_reconnect import digest
from tui_workspace_launch import publish_workspace_history


MCP_SERVER = "flower"
MCP_PREFIX = f"mcp__{MCP_SERVER}__"
RESUME_PROMPT = "Continue from where you left off."


def _blocks(row):
    content = row["content"]
    return [{"type": "text", "text": content}] if isinstance(content, str) else content


def _plain_text(block):
    return (block.keys() == {"type", "text"} and block["type"] == "text"
            and isinstance(block["text"], str) and bool(block["text"]))


def _inline_png(block):
    if block.keys() != {"type", "source"} or block["type"] != "image":
        return False
    source = block["source"]
    if (not isinstance(source, dict) or source.keys() != {"type", "media_type", "data"}
            or source["type"] != "base64" or source["media_type"] != "image/png"
            or not isinstance(source["data"], str)):
        return False
    try:
        return b64decode(source["data"], validate=True).startswith(b"\x89PNG\r\n\x1a\n")
    except ValueError:
        return False


def _closed_history(rows, *, result_types=(str,)):
    pending, seen = set(), set()
    for row in rows:
        results = set()
        for block in _blocks(row):
            if _plain_text(block) or (row["role"] == "user" and _inline_png(block)):
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
                    and isinstance(block.get("content"), result_types)
                    and type(block.get("is_error", False)) is bool):
                results.add(block["tool_use_id"])
            else:
                return False
        if row["role"] == "user":
            if results != pending:
                return False
            pending.clear()
    return not pending


@dataclass(frozen=True)
class ColdHistory:
    """记录已确认的普通输入、当前文本以及该会话的 MCP 工具映射。"""

    history: list
    model: str
    prompt: str
    system: str | None
    tools: dict
    max_tokens: int
    thinking: dict | None
    system_policy: str
    effort: str | None = None

    @classmethod
    def from_request(cls, body, system_policy="append"):
        """识别普通文本首轮及受支持的闭合历史。
        @param body 已校验的请求。@param system_policy 本轮冻结的账号系统指令动作。
        @return 原生输入计划或空。
        """
        if body.keys() - {"model", "max_tokens", "thinking", "system", "messages", "tools", "stream", "output_config"}:
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
        if (current["role"] != "user" or any(
                row["role"] != ("user" if i % 2 == 0 else "assistant") or not _blocks(row)
                for i, row in enumerate(history))
                or not _closed_history(history)):
            return None
        content = _blocks(current)
        if len(content) != 1 or not _plain_text(content[0]):
            return None
        declared = body.get("tools", [])
        for tool in declared:
            if (tool.keys() - {"name", "input_schema", "description"}
                    or not re.fullmatch(r"[A-Za-z0-9_]+", tool["name"])
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
        return cls(history, body["model"], content[0]["text"], system, tools, body["max_tokens"],
                   body.get("thinking"), system_policy, output.get("effort"))

    def system_argument(self):
        """选择原生 CLI 提示词文件选项。@return 参数和文件正文，或缺省值。"""
        if self.system_policy == "replace" and self.system is not None:
            return "--system-prompt-file", self.system
        if self.system_policy == "append" and self.system:
            return "--append-system-prompt-file", self.system
        return None

    def submitted_prompt(self):
        """取得提交给当前交互轮的问题。@return 正文，必要时包含用户提醒。"""
        if self._reminder_index() == len(self.history):
            return f"{self.prompt}\n\n{self._reminder()}"
        return self.prompt

    def _scope(self):
        scope = (self.model, self.system_policy, self.system, self.tools, self.max_tokens, self.thinking)
        # 缺省沿用既有工作区和等待回执的摘要。
        return scope if self.effort is None else (*scope, self.effort)

    def receipt_boundary(self):
        """冻结必须随原工具回执复用的根轮输入。@return 不含客户原文的边界。"""
        return {
            "prompt_index": len(self.history) + 1,
            "system_policy": self.system_policy,
            "digest": digest([self._scope(), self.history, self.prompt]),
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
        return replace(self, history=history, prompt=RESUME_PROMPT)

    def _reminder(self):
        return f"<system-reminder>\n{self.system}\n</system-reminder>"

    def _reminder_index(self):
        if self.system_policy != "user_reminder" or not self.system:
            return None
        for index, row in enumerate(self.history):
            if row["role"] == "user" and all(block["type"] != "tool_result" for block in _blocks(row)):
                return index
        return len(self.history)

    def import_session(self, config, work, native_id):
        """在已绑定的工作区选择新会话或发布已完成的外部历史。
        @param config 私有配置。@param work 已核验工作目录。@param native_id 绑定的原生会话。
        @return 本次启动的原生会话 UUID。
        """
        reminder_index = self._reminder_index()
        history = []
        for index, row in enumerate(self.history):
            blocks = _blocks(row)
            if index == reminder_index:
                blocks = [*blocks, {"type": "text", "text": self._reminder()}]
            history.append((row["role"], blocks))

        boundary = digest((*self._scope(), history))
        return publish_workspace_history(
            config, work, native_id, lambda rows: self._matches_history(rows, history),
            (lambda session_id: self._transcript(work, session_id, history)) if history else None,
            boundary=boundary,
        )

    def _matches_history(self, rows, history):
        matches = True
        parent = None
        for row, expected in zip_longest(rows, history):
            # 当前问题由新轮提交。已经追加过的真实原生对话只能作为独立分支的依据。
            if row is None or expected is None or row["type"] != expected[0]:
                matches = False
                continue
            message = row.get("message", {})
            if (row.get("parentUuid") != parent or not isinstance(row.get("uuid"), str)
                    or (message.get("role"), message.get("content")) != expected
                    or row["type"] == "assistant" and message.get("model") != self.model):
                matches = False
            parent = row.get("uuid")
        return matches

    def _transcript(self, work, session_id, history):
        timestamp = datetime.now(timezone.utc).isoformat()
        parent = None
        rows = []
        for role, content in history:
            uid = str(uuid4())
            message = {"role": role, "content": content}
            if role == "assistant":
                message.update(id="msg_" + uuid4().hex, type="message", model=self.model,
                               stop_reason="tool_use" if any(block["type"] == "tool_use" for block in content)
                               else "end_turn", stop_sequence=None,
                               usage={"input_tokens": 0, "output_tokens": 0})
            rows.append(encode({
                "parentUuid": parent, "uuid": uid, "sessionId": session_id, "cwd": str(work),
                "type": role, "message": message, "isSidechain": False,
                "userType": "external", "timestamp": timestamp,
            }).decode())
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
