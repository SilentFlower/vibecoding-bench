"""通过官方提示钩子和原生恢复观测固定 CLI 的中途系统上下文。"""

from contextlib import ExitStack
from gzip import decompress
from hashlib import file_digest, sha256
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
from secrets import token_hex
from shlex import join
from shutil import which
from socket import if_nameindex
from subprocess import check_output
import sys
from tempfile import TemporaryDirectory
from urllib.parse import urlsplit
from uuid import uuid4

from verify_tui_concurrency import CLEAN_ENV, Terminal, VERSION, frame, wait_for
from verify_tui_final_tls import serve


MODEL = "claude-opus-5-5"
QUESTIONS = {
    "control": "FLOWER_CONTROL：记下第一条便签。",
    "with_prompt_context": "FLOWER_PROMPT：记下第二条便签。",
    "warm": "FLOWER_WARM：继续使用当前窗口。",
    "resumed": "FLOWER_RESUMED：恢复后列出便签。",
}
PROMPT_CONTEXT = "FLOWER_PROMPT_SYSTEM：第二条便签属于海棠项目。"
RESUME_CONTEXT = "FLOWER_RESUME_SYSTEM：本次重开在合成环境中运行。"


class ModelReceiver(BaseHTTPRequestHandler):
    """记录 CLI 实际发来的消息，回复合成文本。"""

    def log_message(self, *_):
        """省略默认 HTTP 日志。@return 无。"""

    def do_POST(self):
        """接收一次回环 Messages。@return 无。"""
        if urlsplit(self.path).path != "/v1/messages":
            self.send_error(404)
            return
        if self.headers.get("Authorization") != "Bearer " + self.server.token:
            self.send_error(401)
            return
        raw = self.rfile.read(int(self.headers["Content-Length"]))
        if self.headers.get("Content-Encoding") == "gzip":
            raw = decompress(raw)
        body = json.loads(raw)
        record = {"model_body_sha256": sha256(raw).hexdigest(), "model": body["model"],
                  "cli_session_header": self.headers.get("x-claude-code-session-id"),
                  "user_agent": self.headers.get("User-Agent"), "body": body}
        self.server.received.append(record)
        start = {"id": "msg_" + uuid4().hex, "type": "message", "role": "assistant", "model": body["model"],
                 "content": [], "usage": {"input_tokens": 1, "output_tokens": 0}}
        events = [
            {"type": "message_start", "message": start},
            {"type": "content_block_start", "index": 0, "content_block": {"type": "text", "text": ""}},
            {"type": "content_block_delta", "index": 0,
             "delta": {"type": "text_delta", "text": reply(len(self.server.received))}},
            {"type": "content_block_stop", "index": 0},
            {"type": "message_delta", "delta": {"stop_reason": "end_turn"}, "usage": {"output_tokens": 1}},
            {"type": "message_stop"},
        ]
        payload = b"".join(map(frame, events))
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


def reply(turn):
    """得到该轮合成回复。@param turn 轮序号。@return 回复文本。"""
    return f"FLOWER_REPLY_{turn}：已记录合成请求。"


def emit_context(path):
    """按文档的 hook 响应仅为指定轮返回附加上下文。@param path 本次钩子记录。@return 无。"""
    event = json.load(sys.stdin)
    name = event["hook_event_name"]
    context = None
    if name == "UserPromptSubmit" and event["prompt"] == QUESTIONS["with_prompt_context"]:
        context = PROMPT_CONTEXT
    elif name == "SessionStart" and event["source"] == "resume":
        context = RESUME_CONTEXT
    if context is not None:
        with path.open("a") as output:
            print(json.dumps({"hook": name, "session_id": event["session_id"], "marker": context},
                             ensure_ascii=False), file=output)
        print(json.dumps({"hookSpecificOutput": {"hookEventName": name, "additionalContext": context}}))


def locations(body, marker):
    """定位单个标记在模型正文的角色和块。@param body 模型实收。@param marker 合成文本。@return 命中位点。"""
    hits = []
    for row, role, content in [(None, "top_level_system", body.get("system", [])), *(
        (i, message["role"], message["content"]) for i, message in enumerate(body["messages"])
    )]:
        blocks = [{"type": "text", "text": content}] if isinstance(content, str) else content
        for slot, block in enumerate(blocks):
            text = block.get("text", "")
            if marker in text:
                hits.append({"row": row, "role": role, "block": slot, "count": text.count(marker),
                             "verbatim_block": text == marker,
                             "matching_lines": [line for line in text.splitlines() if marker in line]})
    return hits


def verify(binary, folder):
    """从官方 PTY 依次运行首轮、提示钩子、热续轮和档案恢复。@param binary 固定 CLI。
    @param folder 独立实验目录。@return 模型实收的相对位置和来源。
    """
    assert {name for _, name in if_nameindex()} == {"lo"}
    version = check_output([binary, "--version"], env={**CLEAN_ENV, "HOME": str(folder)}, text=True).split()[0]
    assert version == VERSION, version
    with binary.open("rb") as program:
        binary_hash = file_digest(program, "sha256").hexdigest()
    terminal_dir, events = folder / "terminal", folder / "hooks.jsonl"
    command = {"type": "command", "command": join([sys.executable, str(Path(__file__).resolve()),
                                                   "--emit-context", str(events)])}
    hooks = {"UserPromptSubmit": [{"hooks": [command]}],
             "SessionStart": [{"matcher": "resume", "hooks": [command]}]}
    session_id, token = str(uuid4()), token_hex(16)
    with ExitStack() as stack:
        server = serve(stack, ThreadingHTTPServer(("127.0.0.1", 0), ModelReceiver))
        server.received, server.token = [], token
        args = binary, terminal_dir, session_id, f"http://127.0.0.1:{server.server_port}", token, which("setsid")
        with ExitStack() as original:
            cli = Terminal(*args, model=MODEL, hooks=hooks)
            original.callback(cli.cleanup)
            first_pid = cli.process.pid
            for n, prompt in enumerate(list(QUESTIONS.values())[:3], start=1):
                cli.submit(prompt)
                wait_for(lambda: cli.completed() == n, f"原进程第 {n} 轮完成", timeout=25)

        (archive,) = (terminal_dir / "home" / ".claude" / "projects").rglob(session_id + ".jsonl")
        original_archive = archive.read_bytes()
        stored_markers = [json.loads(line) for line in original_archive.splitlines() if PROMPT_CONTEXT.encode() in line]
        with ExitStack() as resumed:
            cli = Terminal(*args, model=MODEL, hooks=hooks, resume=archive)
            resumed.callback(cli.cleanup)
            assert cli.process.pid != first_pid
            cli.submit(QUESTIONS["resumed"])
            wait_for(lambda: cli.completed() == 4, "原生恢复后本轮完成", timeout=25)
        assert archive.read_bytes().startswith(original_archive), "恢复后原会话前缀发生变化"
        assert len(server.received) == len(QUESTIONS), len(server.received)

    hook_calls = [json.loads(line) for line in events.read_text().splitlines()]
    assert [(e["hook"], e["session_id"]) for e in hook_calls] == [
        ("UserPromptSubmit", session_id), ("SessionStart", session_id),
    ], hook_calls
    turns = {}
    for n, (phase, record) in enumerate(zip(QUESTIONS, server.received, strict=True), start=1):
        body = record.pop("body")
        assert record["model"] == MODEL and record["cli_session_header"] == session_id, record
        assert f"/{VERSION}" in record["user_agent"], record
        questions = {key: locations(body, text) for key, text in QUESTIONS.items()}
        replies = {i: locations(body, reply(i)) for i in range(1, n)}
        for i, (key, seen) in enumerate(questions.items(), start=1):
            if i <= n:
                (hit,) = seen
                assert (hit["role"], hit["count"]) == ("user", 1), (phase, key, seen)
            else:
                assert not seen, (phase, key, seen)
        for i, (hit,) in replies.items():
            assert (hit["role"], hit["count"]) == ("assistant", 1), (phase, i, hit)
        turns[phase] = {**record, "message_roles": [row["role"] for row in body["messages"]],
                        "question_rows": questions, "previous_replies": replies,
                        "prompt_context": locations(body, PROMPT_CONTEXT), "resume_context": locations(body, RESUME_CONTEXT)}
    assert not turns["control"]["prompt_context"] and not turns["control"]["resume_context"]
    for phase in ("with_prompt_context", "warm", "resumed"):
        turn = turns[phase]
        (hit,) = turn["prompt_context"]
        assert (hit["role"], hit["count"], hit["verbatim_block"]) == ("system", 1, False), (phase, hit)
        assert hit["matching_lines"] == [f"UserPromptSubmit hook additional context: {PROMPT_CONTEXT}"], (phase, hit)
        assert hit["row"] == turn["question_rows"]["with_prompt_context"][0]["row"] + 1, (phase, hit)
        if phase in ("warm", "resumed"):
            assert hit["row"] < turn["previous_replies"][2][0]["row"], (phase, hit)
        if phase != "resumed":
            assert not turn["resume_context"], (phase, turn["resume_context"])
    cold = turns["resumed"]
    (hit,) = cold["resume_context"]
    assert (hit["role"], hit["count"], hit["verbatim_block"]) == ("system", 1, False), hit
    assert hit["matching_lines"] == [f"SessionStart hook additional context: {RESUME_CONTEXT}"], hit
    assert hit["row"] == cold["question_rows"]["resumed"][0]["row"] + 1 == len(cold["message_roles"]) - 1, hit
    archived = [{"type": row["type"], "attachment_type": row.get("attachment", {}).get("type")}
                for row in stored_markers]
    assert archived == [{"type": "attachment", "attachment_type": "hook_additional_context"}], archived
    return {"cli_version": version, "cli_sha256": binary_hash,
            "provider_path": "interactive_cli_direct", "model_posts": len(turns),
            "session_id": session_id, "resumed_same_archive": True,
            "archive_prefix_sha256": sha256(original_archive).hexdigest(), "archive_prefix_preserved": True,
            "archived_prompt_context": archived, "hook_calls": hook_calls, "turns": turns,
            "transport": "http_loopback", "wire_final": "unavailable"}


if __name__ == "__main__":
    if sys.argv[1] == "--emit-context":
        emit_context(Path(sys.argv[2]))
    else:
        with TemporaryDirectory(prefix="flower-native-system-test-") as temporary:
            print(json.dumps(verify(Path(sys.argv[1]), Path(temporary)), ensure_ascii=False, indent=2))
