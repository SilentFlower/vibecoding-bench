"""公开 Messages 客户端的模型首轮、工具回传与流式首片验收。"""

from contextlib import closing
from http.client import HTTPConnection
import json
from pathlib import Path
from select import select
from time import monotonic_ns, sleep
from uuid import uuid4

from file_activity import monitor_read, read_counts


OBSERVATIONS = Path("/native/native-observations.jsonl")
BARRIER = Path("/native/client-saw-partial")


def exercise(port, token, directory, stack, *, managed_proxy=False):
    """在隔离服务上执行两轮同会话请求。
    @param port 公开网关端口。@param token 合成访问凭据。@param directory 客户端证据目录。
    @param stack 本次客户端的资源生命周期。@param managed_proxy 是否核对独立模型的代理路径。@return 模型和工具执行计数。
    """
    headers = {
        "Authorization": "Bearer " + token,
        "Content-Type": "application/json",
        "anthropic-version": "2023-06-01",
        "User-Agent": "claude-cli/2.1.293 (external, cli)",
        "x-session-id": str(uuid4()),
        "Accept-Language": "zh-CN",
        "Cache-Control": "no-cache",
    }
    body = {
        "model": "claude-sonnet-4-6",
        "max_tokens": 128,
        "stream": True,
        "system": "读取合成便签。",
        "tools": [
            {
                "name": "ReadNote",
                "description": "读取本地合成便签",
                "input_schema": {
                    "type": "object",
                    "properties": {"key": {"type": "string"}},
                    "required": ["key"],
                },
            }
        ],
        "messages": [{"role": "user", "content": "请读取便签。"}],
    }
    note = directory / "client-note"
    if managed_proxy:
        body["messages"][0]["content"] = (
            "请读取本机的测试便签，再根据便签内容给我一个简短的答复。"
        )
    note.write_text("NOTE_OK")
    descriptor = monitor_read(stack, note)
    events = []
    response_ids = []
    with closing(HTTPConnection("127.0.0.1", port, timeout=45)) as client:
        client.request("POST", "/v1/messages", json.dumps(body).encode(), headers)
        response = client.getresponse()
        if response.status != 200:
            raise AssertionError((response.status, response.read(700)))
        pieces = []
        first = None
        for line in response:
            if not line.startswith(b"data:"):
                continue
            event = json.loads(line[5:])
            events.append(event["type"])
            if event["type"] == "message_start":
                response_ids.append(event["message"]["id"])
            if (
                event["type"] == "content_block_start"
                and event["content_block"]["type"] == "tool_use"
            ):
                first = event["content_block"]
            if event.get("delta", {}).get("type") == "input_json_delta":
                pieces.append(event["delta"]["partial_json"])
                if len(pieces) == 1:
                    assert pieces[0] == '{"key":'
                    assert not select([descriptor], [], [], 0)[0], (
                        "工具参数不完整时已经访问文件"
                    )
                    actual = [
                        json.loads(row) for row in OBSERVATIONS.read_text().splitlines()
                    ]
                    private_port = next(
                        row["private_port"] for row in actual if "private_port" in row
                    )
                    with closing(
                        HTTPConnection("127.0.0.1", private_port, timeout=5)
                    ) as check:
                        check.request("CONNECT", "api.anthropic.com:443")
                        denied = check.getresponse()
                        assert denied.status == 403, denied.status
                        denied.read()
                    if managed_proxy:
                        from fixture_tunnel import HOST

                        with closing(
                            HTTPConnection("127.0.0.1", private_port, timeout=5)
                        ) as foreign:
                            foreign.request("CONNECT", HOST + ":443")
                            foreign_reply = foreign.getresponse()
                            assert foreign_reply.status == 403
                            foreign_reply.read()
                    first_delta_ns = monotonic_ns()
                    sleep(0.5)
                    BARRIER.touch()
                    barrier_ms = (monotonic_ns() - first_delta_ns) / 1e6
        assert events[-1] == "message_stop" and first is not None
        assert events == [
            "message_start",
            "content_block_start",
            "content_block_delta",
            "content_block_delta",
            "content_block_stop",
            "message_delta",
            "message_stop",
        ]
        first["input"] = json.loads("".join(pieces))
        assert first["name"] == "ReadNote" and first["input"] == {"key": "note"}
    value = note.read_text()
    body["stream"] = False
    body["messages"].extend(
        [
            {"role": "assistant", "content": [first]},
            {
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": first["id"],
                        "content": value,
                    }
                ],
            },
        ]
    )
    with closing(HTTPConnection("127.0.0.1", port, timeout=45)) as client:
        client.request("POST", "/v1/messages", json.dumps(body).encode(), headers)
        response = client.getresponse()
        reply = json.loads(response.read())
        assert response.status == 200 and reply["stop_reason"] == "end_turn", (
            response.status,
            reply,
        )
        assert reply["content"] == [{"type": "text", "text": "收到测试便签。"}], reply[
            "content"
        ]
        response_ids.append(reply["id"])
    file_events = read_counts(descriptor)
    assert file_events == [0x20, 0x01, 0x10], file_events
    records = [json.loads(line) for line in OBSERVATIONS.read_text().splitlines()]
    key = "main_grant" if managed_proxy else "received"
    received = [r for r in records if key in r]
    completed = [r["completed"] for r in records if "completed" in r]
    assert sum(r.get("repeated_seed_rejected", False) for r in records) == 2
    assert len(received) == 2 and [r[key] for r in received] == completed
    assert received[0]["cli_pid"] == received[1]["cli_pid"]
    assert managed_proxy or all(
        r["cli_peer"]
        and r["body_equal"]
        and r["tls"] == "TLSv1.3"
        and r["language"] == "zh-CN"
        and r["cache"] == "no-cache"
        for r in received
    )
    return {
        **({} if managed_proxy else {"model_posts": len(received)}),
        "client_message_ids": response_ids,
        "client_session_id": headers["x-session-id"],
        "client_blocks": [first, reply["content"][0]],
        "repeated_seed_rejections": 2,
        "tool_reads": file_events.count(0x01),
        "file_events": file_events,
        "client_pause_ms": round(barrier_ms, 1),
        "partial_tool_frames": len(pieces),
        "root_events": events,
        "external_connect_status": denied.status,
        **(
            {"other_process_connect_status": foreign_reply.status}
            if managed_proxy
            else {}
        ),
        "result": "passed",
    }


def cancel_partial(port, token):
    """收到半截参数后真实断开下游。@param port 网关端口。@param token 合成凭据。@return 无。"""
    body = {
        "model": "claude-sonnet-4-6",
        "max_tokens": 128,
        "stream": True,
        "tools": [{"name": "ReadNote", "input_schema": {"type": "object"}}],
        "messages": [{"role": "user", "content": "在半截参数处取消本轮"}],
    }
    with closing(HTTPConnection("127.0.0.1", port, timeout=45)) as client:
        client.request(
            "POST",
            "/v1/messages",
            json.dumps(body).encode(),
            {
                "Authorization": "Bearer " + token,
                "Content-Type": "application/json",
                "User-Agent": "claude-cli/2.1.293 (external, cli)",
                "x-session-id": str(uuid4()),
                "anthropic-version": "2023-06-01",
            },
        )
        with closing(client.getresponse()) as response:
            assert response.status == 200, response.status
            for line in response:
                if (
                    line.startswith(b"data:")
                    and json.loads(line[5:]).get("delta", {}).get("type")
                    == "input_json_delta"
                ):
                    return
    raise AssertionError("模型在断连屏障前结束")
