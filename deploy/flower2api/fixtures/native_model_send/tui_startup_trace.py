"""隔离 Messages 夹具的启动阶段探针。"""

from contextlib import suppress
from hashlib import sha256
import json
import os
from pathlib import Path
import sys
from time import monotonic_ns
from traceback import extract_tb


MODEL_BODY_TRACE = Path("/run/v3/tui-v2/.fixture-model-body.jsonl")
THINKING_SUMMARIES_SETTING = ".fixture-show-thinking-summaries.json"


def startup_event(stage, **fields):
    """记录固定阶段、单调时钟与隔离关联值。@param stage 阶段名。@param fields 关联值。@return 无。"""
    line = json.dumps({"event": "tui_startup", "stage": stage, "monotonic_ns": monotonic_ns(), **fields})
    with suppress(OSError):
        os.write(2, (line + "\n").encode())


def main():
    """在隔离容器中观测原事件源的调用边界。@return 无。"""
    # 账号 sender 以 -I 启动。此入口仅由回环夹具安装。
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import fixture_tui_source as source
    import tui_sender_launch as launcher
    from tui_session import SessionDriver, _Actor

    class TracedDriver(SessionDriver):
        """沿原驱动准备预留，记录进入与完成时间。"""

        def prepare(self, reservation, raw, *, cancel_event=None):
            """观察准备过程。@param reservation 已核验预留。@param raw 原正文。@param cancel_event 取消探针。@return 原预留票据。"""
            ident = reservation["reservation_id"]
            startup_event("source_prepare", reservation_id=ident)
            try:
                handle = super().prepare(reservation, raw, cancel_event=cancel_event)
            except Exception as error:
                startup_event("source_prepare_rejected", reservation_id=ident, error_type=type(error).__name__)
                raise
            startup_event("source_prepared", reservation_id=ident)
            return handle

    send_handle = source.AccountSource._send_handle
    launch_session = launcher.launch_session
    callback = _Actor.callback
    serve_model = _Actor.serve_model
    claim_model = _Actor._claim_model
    summary_setting = Path(__file__).with_name(THINKING_SUMMARIES_SETTING)
    thinking_summaries = json.loads(summary_setting.read_text()) if summary_setting.is_file() else None

    def trace_send(self, writer, connection, handle, command):
        startup_event("source_send", reservation_id=handle.reservation["reservation_id"])
        return send_handle(self, writer, connection, handle, command)

    def trace_launch(reservation, command, **options):
        ident = reservation["reservation_id"]
        if thinking_summaries is not None:
            # 只给隔离测试 CLI 的正式启动参数增加受支持设置，保留原有会话钩子。
            arguments = options["arguments"].copy()
            position = arguments.index("--settings") + 1
            settings = json.loads(arguments[position])
            settings["showThinkingSummaries"] = thinking_summaries
            arguments[position] = json.dumps(settings)
            options["arguments"] = arguments
            startup_event("cli_thinking_summaries_setting", reservation_id=ident, enabled=thinking_summaries)
        startup_event("cli_launch", reservation_id=ident)
        try:
            process = launch_session(reservation, command, **options)
        except Exception as error:
            # 保留失败位置供回环诊断。异常原文可能含文件或命令参数。
            location = extract_tb(error.__traceback__)[-1]
            startup_event("cli_launch_failed", reservation_id=ident, error_type=type(error).__name__,
                          errno=getattr(error, "errno", None), module=Path(location.filename).name,
                          function=location.name, line=location.lineno)
            raise
        startup_event("cli_spawned", reservation_id=ident)
        if options.get("recover_incomplete_history"):
            mode, session = process.args[-2:]
            startup_event("cli_legacy_recovery_started", reservation_id=ident, cli_pid=process.pid,
                          mode=mode, native_session_id=Path(session).stem,
                          bound_native_session_id=command["workspace"]["native_session_id"])
        return process

    def trace_callback(actor, path, data):
        result = callback(actor, path, data)
        if path == "/ready":
            startup_event("cli_ready", reservation_id=actor.reservation["reservation_id"])
        elif path == "/prompt" and result is not None:
            startup_event("cli_prompt_accepted", reservation_id=actor.reservation["reservation_id"])
        return result

    def trace_model(actor, http, native, **options):
        startup_event("cli_model_callback", cli_launch_reservation_id=actor.reservation["reservation_id"])
        return serve_model(actor, http, native, **options)

    def trace_model_body(actor, headers, native, *args, **options):
        submission = claim_model(actor, headers, native, *args, **options)
        if submission is not None:
            native_raw = args[0] if args else options.get("native_raw")
            # 摘要取自已认领的提交，不能用 CLI 回调的存在推断出站正文来自 CLI。
            evidence = {"reservation_id": submission.handle.reservation["reservation_id"],
                        "cli_pid": actor.process.pid,
                        "input_format": submission.handle.reservation.get("input_format"),
                        "uses_native_history": actor.cold_history is not None,
                        "from_interactive_cli": submission.body == native_raw,
                        "cli_json_matches_submission": json.loads(submission.body) == native,
                        "cli_tool_choice": native.get("tool_choice"),
                        "cli_has_output_format": "format" in (native.get("output_config") or {}),
                        "cli_tool_names": [tool.get("name") for tool in native.get("tools") or []],
                        "cli_sha256": sha256(native_raw).hexdigest() if native_raw is not None else None,
                        "sha256": sha256(submission.body).hexdigest()}
            with suppress(OSError), MODEL_BODY_TRACE.open("ab", buffering=0) as stream:
                stream.write((json.dumps(evidence) + "\n").encode())
        return submission

    source.AccountSource._send_handle = trace_send
    launcher.launch_session = trace_launch
    _Actor.callback = trace_callback
    _Actor.serve_model = trace_model
    if MODEL_BODY_TRACE.is_file():
        _Actor._claim_model = trace_model_body
    source.main(driver_factory=TracedDriver)


if __name__ == "__main__":
    main()
