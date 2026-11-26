"""在仅回环容器验证固定交互 CLI 的工具权限与模型选择字段。"""

from contextlib import ExitStack
from gzip import decompress
from hashlib import file_digest, sha256
from http.server import ThreadingHTTPServer
import json
from pathlib import Path
from secrets import token_hex
from shutil import which
from socket import if_nameindex
from subprocess import check_output
import sys
from tempfile import TemporaryDirectory
from urllib.parse import urlsplit
from uuid import uuid4

from verify_tui_cold_history import MODEL, QuietHandler, SECOND_TOOL, TOOL, blocks, response_json
from verify_tui_concurrency import CLEAN_ENV, VERSION, Terminal, wait_for
from verify_tui_final_tls import serve
from verify_tui_http_handoff import message_sse


QUESTION = "请选择是否需要合成便签工具。"
DIRECT_REPLY = "模型直接返回合成文本。"


class Receiver(QuietHandler):
    """用同一回环服务交付两个合成 MCP 声明并记录 CLI 请求。"""

    def do_POST(self):
        """记录实际模型字段或应答 MCP 协商。@return 无。"""
        path = urlsplit(self.path).path
        if self.headers.get("Authorization") != "Bearer " + self.server.token:
            self.send_error(403)
            return
        raw = self.rfile.read(int(self.headers["Content-Length"]))
        if self.headers.get("Content-Encoding") == "gzip":
            raw = decompress(raw)
        data = json.loads(raw)
        if path == "/mcp":
            method = data["method"]
            if method == "initialize":
                result = {"protocolVersion": "2025-03-26", "capabilities": {"tools": {}},
                          "serverInfo": {"name": "flower", "version": "1"}}
            elif method == "tools/list":
                result = {"tools": [{"name": tool["name"], "description": tool["description"],
                                    "inputSchema": tool["input_schema"]} for tool in (TOOL, SECOND_TOOL)]}
            elif method.startswith("notifications/"):
                self.send_response(202)
                self.end_headers()
                return
            else:
                if method == "tools/call":
                    self.server.tool_calls.append(data["params"]["name"])
                response_json(self, {"jsonrpc": "2.0", "id": data["id"],
                                     "error": {"code": -32601, "message": "合成声明服务不执行工具"}})
                return
            response_json(self, {"jsonrpc": "2.0", "id": data["id"], "result": result})
            if method == "tools/list":
                self.server.tool_lists.append(len(result["tools"]))
            return
        if path != "/v1/messages":
            self.send_error(404)
            return
        self.server.received.append({"sha256": sha256(raw).hexdigest(), "body": data})
        payload = message_sse({"type": "text", "text": DIRECT_REPLY}, "end_turn", "msg_direct_tool_choice")
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


def verify(binary, folder):
    """对照默认权限、允许指定工具和从上下文移除另一个工具。
    @param binary 官方 CLI 路径。@param folder 隔离目录。@return 模型实收证据。
    """
    if {name for _, name in if_nameindex()} != {"lo"}:
        raise RuntimeError("请在仅回环网络中运行")
    version = check_output([binary, "--version"], env={**CLEAN_ENV, "HOME": str(folder)}, text=True).split()[0]
    assert version == VERSION, version
    token = token_hex(16)
    first, second = ("mcp__flower__" + tool["name"] for tool in (TOOL, SECOND_TOOL))
    variants = (("default", [], {first, second}),
                ("allow_named", ["--allowedTools", second], {first, second}),
                ("deny_other", ["--disallowedTools", first], {second}))
    results = {}
    with ExitStack() as stack:
        server = serve(stack, ThreadingHTTPServer(("127.0.0.1", 0), Receiver))
        server.token, server.received, server.tool_lists, server.tool_calls = token, [], [], []
        endpoint = f"http://127.0.0.1:{server.server_port}"
        config = folder / "mcp.json"
        config.write_text(json.dumps({"mcpServers": {"flower": {"type": "http", "url": endpoint + "/mcp",
                                                              "headers": {"Authorization": "Bearer " + token}}}}))
        for label, flags, expected in variants:
            before, before_lists = len(server.received), len(server.tool_lists)
            session = str(uuid4())
            cli = Terminal(binary, folder / label, session, endpoint, token, which("setsid"), model=MODEL,
                           extra_args=["--permission-mode", "dontAsk", "--mcp-config", str(config), *flags])
            try:
                wait_for(lambda: len(server.tool_lists) > before_lists, label + " MCP 声明")
                cli.submit(QUESTION)
                wait_for(lambda: cli.completed() == 1, label + " 合成直接回复")
            finally:
                cli.cleanup()
            (archive,) = (folder / label / "home" / ".claude" / "projects").rglob(session + ".jsonl")
            rows = [json.loads(line) for line in archive.read_text().splitlines()]
            replies = [block["text"] for row in rows if row["type"] == "assistant"
                       for block in blocks(row["message"]) if block["type"] == "text"]
            assert replies == [DIRECT_REPLY], (label, replies)
            (record,) = server.received[before:]
            body = record.pop("body")
            (declared_count,) = server.tool_lists[before_lists:]
            assert declared_count == 2 and body["model"] == MODEL, (label, body)
            native = {tool["name"]: tool for tool in body["tools"]}
            assert native.keys() == expected and "tool_choice" not in body, (label, body)
            source_tools = {first: TOOL, second: SECOND_TOOL}
            assert all(native[name]["input_schema"] == source_tools[name]["input_schema"] for name in expected)
            assert sum(QUESTION in b.get("text", "") for r in body["messages"] if r["role"] == "user"
                       for b in blocks(r)) == 1
            results[label] = {**record, "cli_flags": flags, "declared_count": declared_count,
                              "model_tools": sorted(native), "model_tool_choice": body.get("tool_choice"),
                              "model_tool_choice_present": "tool_choice" in body,
                              "completed_direct_reply": True}
        assert not server.tool_calls, server.tool_calls
    with binary.open("rb") as program:
        return {"cli_version": version, "cli_sha256": file_digest(program, "sha256").hexdigest(), "cases": results}


if __name__ == "__main__":
    with TemporaryDirectory(prefix="tui-tool-choice-") as directory:
        print(json.dumps(verify(Path(sys.argv[1]), Path(directory)), ensure_ascii=False))
