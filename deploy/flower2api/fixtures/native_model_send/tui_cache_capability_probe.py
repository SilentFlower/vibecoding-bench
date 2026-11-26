"""让固定交互 CLI 在隔离夹具中亲自组装显式缓存标记。"""

from dataclasses import replace
import json
from pathlib import Path
import sys


def main():
    """给普通提示词事件与受管 MCP 添加合成标记。@return 无。"""
    directory = Path(__file__).resolve().parent
    sys.path.insert(0, str(directory))
    import fixture_startup_trace as trace
    import tui_sender_launch as launcher
    from tui_cold_history import ColdHistory, MCP_PREFIX
    from tui_session import SessionDriver, _Actor

    prepare, callback = SessionDriver.prepare, _Actor.callback
    mcp, launch = ColdHistory.mcp, launcher.launch_session

    def prepare_probe(driver, reservation, raw, *, cancel_event=None):
        body = json.loads(raw)
        content = body["messages"][-1]["content"]
        marks = {i: block.pop("cache_control") for i, block in enumerate(content) if "cache_control" in block}
        tools = {tool["name"]: tool.pop("cache_control") for tool in body.get("tools", []) if "cache_control" in tool}
        # 让生产准备步骤先建立正常原生会话，随后只在 CLI 入口送入合成标记。
        handle = prepare(driver, reservation, json.dumps(body, ensure_ascii=False).encode(), cancel_event=cancel_event)
        actor = handle.actor
        assert actor.cold_history is not None and actor.cold_history.current_blocks
        actor.fixture_prompt_marks = marks
        if tools:
            plan = actor.cold_history
            declarations = plan.tools.copy()
            for name, marker in tools.items():
                declared_name = MCP_PREFIX + name
                declarations[declared_name] = {**declarations[declared_name], "cache_control": marker}
            actor.cold_history = replace(plan, tools=declarations)
        return handle

    def prompt_probe(actor, path, data):
        result = callback(actor, path, data)
        if path == "/prompt" and result is not None and actor.fixture_prompt_marks:
            for offset, marker in actor.fixture_prompt_marks.items():
                result["blocks"][offset] = {**result["blocks"][offset], "cache_control": marker}
            trace.startup_event("probe_prompt_cache_markers", reservation_id=actor.reservation["reservation_id"],
                                markers=actor.fixture_prompt_marks)
        return result

    def mcp_probe(plan, data):
        reply = mcp(plan, data)
        if data.get("method") == "tools/list":
            for tool in reply["result"]["tools"]:
                marker = plan.tools[MCP_PREFIX + tool["name"]].get("cache_control")
                if marker is not None:
                    tool["cache_control"] = marker
                    tool["_meta"] = {"cache_control": marker}
                    trace.startup_event("probe_mcp_cache_marker", name=tool["name"], marker=marker)
        return reply

    def no_automatic_cache(reservation, command, **options):
        options["environment"] = {**options["environment"], "DISABLE_PROMPT_CACHING": "1"}
        return launch(reservation, command, **options)

    SessionDriver.prepare = prepare_probe
    _Actor.callback = prompt_probe
    ColdHistory.mcp = mcp_probe
    if (directory / "fixture_disable_automatic_cache").is_file():
        launcher.launch_session = no_automatic_cache
    trace.main()


if __name__ == "__main__":
    main()
