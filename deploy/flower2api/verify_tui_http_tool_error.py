"""用固定交互 CLI 核对 HTTP MCP 工具错误到模型正文的边界。"""

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

from verify_tui_cold_history import (
    ARGS, FINAL, MODEL, NATIVE_TOOL_NAME, QuietHandler, TOOL, find_blocks, fixture_image_blocks, response_json,
)
from verify_tui_concurrency import CLEAN_ENV, VERSION, Terminal, wait_for
from verify_tui_final_tls import serve
from verify_tui_http_handoff import message_sse


QUESTION = "读取合成便签并核对工具回执。"
CAPTIONS = ["图像之前的原文。", "图像之后的原文。"]
CLI_SHA256 = "8968405e26db478af44eabc4635ab5ca557057b702a54460a59c13e1b253e978"


class Receiver(QuietHandler):
    """同一回环服务交付合成 MCP 结果并独立记录 CLI 的模型请求。"""

    def do_POST(self):
        """检查本次合成授权，按公开协议交付 MCP 或模型响应。@return 无。"""
        if self.headers.get("Authorization") != "Bearer " + self.server.token:
            self.send_error(403)
            return
        path = urlsplit(self.path).path
        raw = self.rfile.read(int(self.headers["Content-Length"]))
        if self.headers.get("Content-Encoding") == "gzip":
            raw = decompress(raw)
        data = json.loads(raw)
        if path == "/mcp":
            self._mcp(data)
        elif path == "/v1/messages":
            self._model(raw, data)
        else:
            self.send_error(404)

    def _mcp(self, data):
        method = data["method"]
        if method.startswith("notifications/"):
            self.send_response(202)
            self.end_headers()
            return
        if method == "initialize":
            result = {"protocolVersion": "2025-03-26", "capabilities": {"tools": {}},
                      "serverInfo": {"name": "flower", "version": "1"}}
        elif method == "tools/list":
            self.server.listed = True
            result = {"tools": [{"name": TOOL["name"], "description": TOOL["description"],
                                 "inputSchema": TOOL["input_schema"]}]}
        elif method == "tools/call":
            self.server.calls.append(data["params"])
            result = self.server.tool_result
        else:
            response_json(self, {"jsonrpc": "2.0", "id": data["id"],
                                 "error": {"code": -32601, "message": "夹具不提供此方法"}})
            return
        response_json(self, {"jsonrpc": "2.0", "id": data["id"], "result": result})

    def _model(self, raw, data):
        self.server.received.append((sha256(raw).hexdigest(), data))
        if len(self.server.received) == 1:
            payload = message_sse(self.server.tool, "tool_use", "msg_http_mcp_tool")
        else:
            payload = message_sse({"type": "text", "text": FINAL}, "end_turn", "msg_http_mcp_final")
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


def verify(binary, folder):
    """以普通 PTY 提交无 schema 的交互请求。@param binary 固定 CLI。@param folder 隔离目录。
    @return 各 MCP 输入与实际模型工具结果。
    """
    if not Path("/.dockerenv").exists() or {name for _, name in if_nameindex()} != {"lo"}:
        raise RuntimeError("请在仅回环容器中运行")
    with binary.open("rb") as program:
        assert file_digest(program, "sha256").hexdigest() == CLI_SHA256
    version = check_output([binary, "--version"], env={**CLEAN_ENV, "HOME": str(folder)}, text=True).split()[0]
    assert version == VERSION, version

    png, jpeg, _, _ = fixture_image_blocks(all_formats=True)
    images = [png, jpeg, png]
    mcp_images = [{"type": "image", "data": image["source"]["data"], "mimeType": image["source"]["media_type"]}
                  for image in images]
    mixed = [{"type": "text", "text": CAPTIONS[0]}, *mcp_images, {"type": "text", "text": CAPTIONS[1]}]
    cases = {}
    for name, failed, content in (("success", False, mixed), ("mixed_error", True, mixed),
                                  ("image_error", True, mcp_images)):
        with ExitStack() as stack:
            server = serve(stack, ThreadingHTTPServer(("127.0.0.1", 0), Receiver))
            server.token, server.listed, server.calls, server.received = token_hex(16), False, [], []
            server.tool = {"type": "tool_use", "id": f"toolu_http_media_{name}", "name": NATIVE_TOOL_NAME, "input": ARGS}
            server.tool_result = {"content": content, "isError": failed}
            endpoint = f"http://127.0.0.1:{server.server_port}"
            mcp_config = folder / f"{name}.json"
            mcp_config.write_text(json.dumps({"mcpServers": {"flower": {
                "type": "http", "url": endpoint + "/mcp", "headers": {"Authorization": "Bearer " + server.token},
            }}}))
            cli = Terminal(binary, folder / name, str(uuid4()), endpoint, server.token, which("setsid"), model=MODEL,
                           extra_args=["--permission-mode", "dontAsk", "--allowedTools", NATIVE_TOOL_NAME,
                                       "--mcp-config", str(mcp_config)])
            try:
                wait_for(lambda: server.listed, f"{name} 的 HTTP MCP 工具清单")
                cli.submit(QUESTION)
                wait_for(lambda: cli.completed() == 1, f"{name} 的模型续轮")
            finally:
                cli.cleanup()
        first, second = server.received
        (call,) = server.calls
        assert call["name"] == TOOL["name"] and call["arguments"] == ARGS, (name, call)
        assert call["_meta"]["claudecode/toolUseId"] == server.tool["id"], (name, call)
        assert all("format" not in request.get("output_config", {}) for _, request in (first, second))
        assert find_blocks(second[1], "id", server.tool["id"]) == [("assistant", server.tool)]
        ((role, result),) = find_blocks(second[1], "tool_use_id", server.tool["id"])
        assert role == "user" and result.get("is_error", False) is failed
        model_images = find_blocks(second[1], "type", "image")
        cases[name] = {"mcp_result": server.tool_result, "mcp_calls": server.calls, "tool_call": server.tool,
                       "model_posts": len(server.received), "model_sha256": [first[0], second[0]],
                       "model_result": result, "top_level_images": model_images}
    return {"cli_version": version, "cli_sha256": CLI_SHA256, "cases": cases, "wire_final": "unavailable"}


def assert_contract(proof):
    """固定 HTTP MCP 实收结果的能力边界。@param proof 逐用例证据。@return 无。"""
    cases = proof["cases"]
    assert all(not case["top_level_images"] for case in cases.values())
    success = cases["success"]
    actual = success["model_result"]["content"]
    business = [block for block in actual if block["type"] == "image" or block.get("text", "").rstrip("\n") in CAPTIONS]
    expected = [{"type": "image", "source": {"type": "base64", "data": block["data"], "media_type": block["mimeType"]}}
                if block["type"] == "image" else block for block in success["mcp_result"]["content"]]
    assert [block if block["type"] == "image" else {**block, "text": block["text"].rstrip("\n")} for block in business] == expected
    assert cases["mixed_error"]["model_result"]["content"].startswith("\n".join(CAPTIONS))
    assert cases["image_error"]["model_result"]["content"].startswith("Unknown error")


if __name__ == "__main__":
    with TemporaryDirectory(prefix="tui-http-tool-error-") as directory:
        proof = verify(Path(sys.argv[1]), Path(directory))
        print(json.dumps(proof, ensure_ascii=False), flush=True)
        assert_contract(proof)
