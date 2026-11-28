"""通过公开 Messages 核对受管父子轮与后台进度回复的归属。"""

from contextlib import closing
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
from sqlite3 import connect
from uuid import uuid4


MODEL_TEXT_REPLIES = {
    "progress": ("Reading the synthetic note", (29, 6)),
    "child_receipt": ("子轮已完成合成笔记读取。", (17, 3)),
    "parent_receipt": ("父轮已完成合成任务汇总。", (23, 5)),
}


def model_reply(index, body, samples, tool_sse, text_sse, frame):
    """为已核验的原始正文交付隔离模型应答。
    @param index 实际模型收件位置。@param body 本次模型正文。@param samples 固定请求样本。
    @param tool_sse 工具事件生成器。@param text_sse 文本事件生成器。@param frame 事件编码器。
    @return 模型流字节。
    """
    label = ("parent", "child", "progress", "progress", "child_receipt", "parent_receipt")[index]
    expected = {**samples[label]["body"], "stream": True}
    assert body == expected, (label, sorted(key for key in body.keys() | expected.keys()
                                            if body.get(key) != expected.get(key)))
    if label in ("parent", "child"):
        (tool,) = (block for row in samples[label + "_receipt"]["body"]["messages"]
                   if row["role"] == "assistant" and isinstance(row["content"], list)
                   for block in row["content"] if block["type"] == "tool_use")
        return tool_sse(tool, with_signature=False, model=body["model"])
    text, (input_tokens, output_tokens) = MODEL_TEXT_REPLIES[label]
    wire = text_sse({"type": "text", "text": text}, "end_turn", f"msg_{uuid4().hex}")
    events = [json.loads(line[5:]) for line in wire.splitlines() if line.startswith(b"data:")]
    events[0]["message"]["usage"]["input_tokens"] = input_tokens
    events[-2]["usage"]["output_tokens"] = output_tokens
    return b"".join(map(frame, events))


def _public_text_reply(raw, stream):
    if stream:
        from tui_message_json import MessageJSON
        from tui_messages import BODY_LIMIT, wire_events

        # 复用消息聚合器，按块重组公开流并核对完整结束。
        assembled = MessageJSON(BODY_LIMIT)
        for _, event in wire_events(BytesIO(raw)):
            if event is not None:
                assembled.add(event)
        raw = assembled.finish()
    reply = json.loads(raw)
    blocks = reply["content"]
    assert blocks and all(block["type"] == "text" for block in blocks), reply
    text = "".join(block["text"] for block in blocks)
    usage = reply["usage"]
    return reply["id"], text, (usage["input_tokens"], usage["output_tokens"]), reply["stop_reason"]


def verify_agent_progress(manage, token, foreign, received, database, samples, checked, wait_for):
    """等待父子轮的真实工具时核对本地和转发的公开进度回复。
    @param manage 管理入口。@param token 原令牌。@param foreign 异主体令牌。@param received 模型收件。
    @param database 夹具数据库。@param samples 固定真实父子请求及现有进度模板。
    @param checked 公开 Messages 调用。@param wait_for 有界等待。@return 脱敏证据。
    """
    def send(label, phase, *, stream=None, secret=token, status=200):
        sample = samples[label]
        headers = {**sample["headers"], "x-session-id": sample["headers"]["x-claude-code-session-id"]}
        body = sample["body"] if stream is None else {**sample["body"], "stream": stream}
        return checked(manage, secret, body, headers, received, phase, expected_status=status, trace_startup=True)

    def pending_tools():
        with closing(connect(database)) as db:
            return db.execute("SELECT * FROM tui_native_turns ORDER BY id").fetchall()

    def finished_receipt(request_id):
        detail = manage("GET", "request-diagnostics/" + request_id)
        return detail if detail["request"]["finished_at"] else None

    def archive_snapshot():
        snapshots = {}
        archived_tools = []
        for binding in Path("/native/tui-workspaces").glob("*.json"):
            payload = binding.read_bytes()
            native_id = json.loads(payload)["native_session_id"]
            projects = Path("/native/tui-sessions") / native_id / "home/.claude/projects"
            files = list(projects.glob("*/" + native_id + ".jsonl"))
            if not files:
                return None
            (archive,) = files
            snapshots[binding] = payload
            raw = snapshots[archive] = archive.read_bytes()
            archived_tools.append(tuple(tool for tool in tools if tool in raw))
        if sorted(archived_tools) == sorted((tool,) for tool in tools):
            return snapshots
        return None

    _, parent, parent_id = send("parent", "progress_parent_start")
    _, child, child_id = send("child", "progress_child_start")
    tools = (b"toolu_fixture_background_agent", b"toolu_fixture_child_read")
    assert tools[0] in parent and tools[1] in child and len(received) == 2
    pending = pending_tools()
    assert sorted(json.loads(row[-1])[0].encode() for row in pending) == sorted(tools)
    snapshots = wait_for(archive_snapshot)

    modes = []
    for retired_setting in (True, False):
        manage("PUT", "settings", {"tui_local_agent_summary": str(retired_setting).lower()})
        for stream in (True, False):
            before = len(received)
            _, raw, request_id = send("progress", f"progress_setting_{retired_setting}_stream_{stream}", stream=stream)
            message_id, text, usage, _ = _public_text_reply(raw, stream)
            assert (text, usage) == MODEL_TEXT_REPLIES["progress"]
            assert len(received) - before == 1
            assert pending_tools() == pending
            assert all(file.read_bytes() == data for file, data in snapshots.items())
            detail = manage("GET", "request-diagnostics/" + request_id)
            attempts = detail["attempts"]
            assert len(attempts) == 1 and attempts[0]["request_id"] == request_id
            modes.append({"retired_setting": retired_setting, "stream": stream, "request_id": request_id, "message_id": message_id,
                          "usage": usage, "model_posts": len(received) - before, "attempts": attempts,
                          "model_body_sha256": received[-1][0]})
    assert len({mode["message_id"] for mode in modes}) == len(modes)
    send("progress", "progress_foreign_principal", secret=foreign, status=400)
    unrelated = str(uuid4())
    sample = samples["progress"]
    metadata = sample["body"]["metadata"]
    identity = {**json.loads(metadata["user_id"]), "session_id": unrelated}
    wrong_session = {**sample["body"], "metadata": {**metadata, "user_id": json.dumps(identity)}}
    headers = {**sample["headers"], "x-claude-code-session-id": unrelated, "x-session-id": unrelated}
    checked(manage, token, wrong_session, headers, received, "progress_foreign_session",
            expected_status=400, trace_startup=True)
    receipts = {}
    for label, stream in (("child_receipt", True), ("parent_receipt", False)):
        before = len(received)
        status, raw, request_id = send(label, label, stream=stream)
        message_id, text, usage, stop_reason = _public_text_reply(raw, stream)
        assert (text, usage) == MODEL_TEXT_REPLIES[label] and stop_reason == "end_turn", (
            label, text, usage, stop_reason,
        )
        duplicate, _, _ = send(label, "progress_duplicate_" + label, stream=stream, status=400)
        assert len(received) - before == 1
        detail = wait_for(lambda: finished_receipt(request_id))
        attempt, = detail["attempts"]
        reservation = detail["request"]["context"]["tui_reservation_id"]
        assert (attempt["request_id"], attempt["attempt_id"]) == (request_id, reservation), detail
        tokens = attempt["tokens"]
        assert (tokens["input_tokens"], tokens["output_tokens"]) == usage, detail
        receipts[label] = {"request_id": request_id, "status": status, "duplicate_status": duplicate,
                           "stream": stream, "message_id": message_id, "text": text, "usage": usage,
                           "stop_reason": stop_reason, "attempt_id": reservation, "model_body_sha256": received[-1][0]}
    assert len({receipt["message_id"] for receipt in receipts.values()}) == len(receipts)
    assert len(received) == 8

    def usage_rows():
        with closing(connect(database)) as db:
            result = db.execute("SELECT input_tokens,output_tokens,partial FROM usage_records WHERE account_id=1").fetchall()
        return result if len(result) >= 8 else None

    ledger = wait_for(usage_rows)
    assert sorted(ledger) == [(10, 8, 0)] * 2 + [(17, 3, 0), (23, 5, 0)] + [(29, 6, 0)] * 4
    assert not any(file.is_file() for file in Path("/flows/api").rglob("*"))
    return {"parent_request_id": parent_id, "child_request_id": child_id, "cases": modes, "usage_records": ledger,
            "original_archive_and_bindings": len(snapshots), "receipts": receipts, "foreign_principal_status": 400,
            "foreign_session_status": 400,
            "model_posts": len(received), "final_tls_capture": "unavailable",
            "progress_sample_sha256": sha256(json.dumps(samples["progress"]["body"], sort_keys=True).encode()).hexdigest()}
