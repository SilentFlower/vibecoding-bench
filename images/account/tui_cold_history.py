"""固定 2.1.293 交互 CLI 的普通 Messages 历史导入与受管 MCP 描述。"""

from dataclasses import dataclass
from datetime import datetime, timezone
import re
from uuid import uuid4

from runtime_files import atomic_text, private_directory
from tui_messages import encode


MCP_SERVER = "flower"
MCP_PREFIX = f"mcp__{MCP_SERVER}__"


def _blocks(row):
    content = row["content"]
    return [{"type": "text", "text": content}] if isinstance(content, str) else content


def _plain_text(block):
    return (block.keys() == {"type", "text"} and block["type"] == "text"
            and isinstance(block["text"], str) and bool(block["text"]))


def _closed_history(rows):
    pending, seen = set(), set()
    for row in rows:
        results = set()
        for block in _blocks(row):
            if _plain_text(block):
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
                    and isinstance(block.get("content"), str)
                    and type(block.get("is_error", False)) is bool):
                results.add(block["tool_use_id"])
            else:
                return False
        if row["role"] == "user":
            if results != pending:
                return False
            pending.clear()
    return bool(seen) and not pending


@dataclass(frozen=True)
class ColdHistory:
    """记录已确认的可导入边界、当前文本以及该会话的 MCP 工具映射。"""

    history: list
    model: str
    prompt: str
    system: str
    tools: dict
    max_tokens: int
    thinking: dict | None

    @classmethod
    def from_request(cls, body):
        """识别本切片已支持的封闭工具历史。@param body 已校验的请求。@return 原生输入计划或空。"""
        if body.keys() - {"model", "max_tokens", "thinking", "system", "messages", "tools", "stream"}:
            return None
        if type(body.get("max_tokens")) is not int or body["max_tokens"] <= 0:
            return None
        if body.get("thinking") not in (None, {"type": "disabled"}):
            return None
        *history, current = body["messages"]
        if (not history or current["role"] != "user" or any(
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
        if not declared:
            return None
        system = body.get("system", "")
        if isinstance(system, list):
            if any(block.keys() != {"type", "text"} for block in system):
                return None
            system = "\n".join(block["text"] for block in system)
        tools = {MCP_PREFIX + tool["name"]: tool for tool in declared}
        return cls(history, body["model"], content[0]["text"], system, tools, body["max_tokens"], body.get("thinking"))

    def import_session(self, config, work):
        """在本会话配置目录发布已完成的外部历史。@param config 私有配置。@param work 已核验工作目录。@return 导入的会话记录。"""
        session_id = str(uuid4())
        project = config / "projects" / re.sub(r"[^a-zA-Z0-9]", "-", str(work))
        private_directory(project.parent)
        private_directory(project)
        path = project / (session_id + ".jsonl")
        timestamp = datetime.now(timezone.utc).isoformat()
        parent = None
        rows = []
        for row in self.history:
            uid = str(uuid4())
            role = row["role"]
            content = _blocks(row)
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
        atomic_text(path, "\n".join(rows) + "\n")
        return path

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
