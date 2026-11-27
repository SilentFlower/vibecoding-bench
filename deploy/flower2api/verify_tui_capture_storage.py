"""使用内置发送器验证 V2 工具流不等待旁路采集存储。"""

from argparse import ArgumentParser
import json
from pathlib import Path
from socket import if_nameindex
from subprocess import Popen
from tempfile import TemporaryDirectory
from time import monotonic_ns
from unittest.mock import patch

import verify_tui_cold_history as fixture
from verify_tui_public_sse import SENDER, installed


def verify(gateway, library, case):
    """公开回环运行断线接回和下一工具回执。
    @param gateway 隔离网关。@param library 注入快照存储行为的测试库。
    @param case 关闭采集、正常、阻塞或失败对照。@return 公开响应、模型实收及采集证据。
    """
    read_captures = fixture.verify_captures
    proof = {}
    with TemporaryDirectory(prefix="flower-capture-storage-") as folder:
        probe = Path(folder)
        probe.chmod(0o777)
        release = probe / "release"
        events = probe / "events"
        stop = fixture.stop

        def launch(command, **options):
            if command == [SENDER] and case in ("blocked", "failed"):
                options["env"] = {**options["env"], "LD_PRELOAD": str(library),
                                  "FLOWER_CAPTURE_PROBE_DIR": folder, "FLOWER_CAPTURE_PROBE_CASE": case}
            return Popen(command, **options)

        def stop_process(process):
            if process.args == [SENDER] and case == "blocked":
                # 即使用例先失败，也在发送器退出前解除注入，保留原始失败。
                release.touch(exist_ok=True)
            return stop(process)

        call = fixture.call

        def public_call(port, method, path, secret, data=None, headers=None, **options):
            if case == "off" and path == "/admin/settings" and method == "PUT":
                data = {**data, "request_diagnostics_log_mode": "info"}
            return call(port, method, path, secret, data, headers, **options)

        def storage_events():
            lines = events.read_text().splitlines() if events.is_file() else []
            return [{"stage": stage, "monotonic_ns": int(timestamp)}
                    for stage, timestamp in (line.split() for line in lines)]

        def observed():
            return [entry["stage"] for entry in storage_events()]

        def read_missing(manage, capture_status, capture_state):
            attempts = []
            for row in manage("GET", "request-diagnostics")["items"]:
                request_id = row["request_id"]
                for attempt in manage("GET", "request-diagnostics/" + request_id)["attempts"]:
                    if attempt.get("capture_status") != capture_status:
                        continue
                    attempt_id = attempt["attempt_id"]
                    assert attempt_id == row["context"]["tui_reservation_id"], row
                    view = manage("GET", f"request-diagnostics/{request_id}/captures/{attempt_id}")
                    assert view["state"] == capture_state, view
                    if capture_status == "dropped":
                        assert view["message"] == "本次 V2 请求采集未进入保存队列", view
                    attempts.append({"request_id": request_id, "attempt_id": attempt_id,
                                     "capture_status": capture_status, "capture_state": view["state"]})
            return attempts

        def check(manage, received, account_token, **options):
            # 接回、缓存重读、下一工具回执和过期回执检查都已走完公开接口。
            finished_ns = monotonic_ns()
            proof["public_checks_finished_ns"] = finished_ns
            assert len(received) == 3
            if case == "blocked":
                assert observed() == ["entered"] and not release.exists(), observed()
                assert not list(Path("/flows/api/cc-prepared").glob("*.json"))
                (skipped,) = read_missing(manage, "dropped", "missing")
                (held,) = storage_events()
                assert held["monotonic_ns"] < finished_ns
                proof["storage_blocked_during_public_ms"] = (finished_ns - held["monotonic_ns"]) // 1_000_000
                proof["storage_release_ns"] = monotonic_ns()
                release.touch()
                # 两个后台写入名额被占用后，第三次模型请求的采集应明确跳过。
                captures = read_captures(manage, received[:2], account_token, **options)
                assert observed() == ["entered", "released"] * 2, observed()
                return [*captures, skipped]
            if case == "normal":
                return read_captures(manage, received, account_token, **options)

            if case == "off":
                assert manage("GET", "settings")["request_diagnostics_log_mode"] == "info"
                assert not list(Path("/flows/api/cc-prepared").glob("*.json"))
                attempts = read_missing(manage, None, "summary")
                assert len(attempts) == len(received), attempts
                return attempts

            fixture.wait_for(lambda: observed().count("failed") >= len(received))
            assert observed() == ["entered", "failed"] * 3, observed()
            proof["storage_failure"] = "EACCES"
            attempts = read_missing(manage, "queued", "missing")
            assert len(attempts) == len(received), attempts
            assert not list(Path("/flows/api/cc-prepared").glob("*.json"))
            return attempts

        with patch.multiple(fixture, call=public_call, Popen=launch, stop=stop_process, verify_captures=check):
            result = installed(gateway, "reconnect")
        proof["storage_events"] = storage_events()
    assert result["public"]["client_tool_calls"] == [fixture.NEW_ID, fixture.RECONNECT_ID]
    assert len(result["deliveries"]) == 3
    connections = {(post["socket_inode"], post["model_peer_port"]) for post in result["deliveries"]}
    assert len(connections) == 1, result["deliveries"]
    proof["case"] = case
    proof["model_tls_connections"] = len(connections)
    return {**result, "storage_probe": proof}


def main():
    """校验容器隔离后运行公开对照。@return 输出脱敏采集证据。"""
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--gateway", type=Path, required=True)
    parser.add_argument("--library", type=Path, required=True)
    parser.add_argument("--case", choices=("off", "normal", "blocked", "failed"), required=True)
    args = parser.parse_args()
    assert Path("/.dockerenv").is_file() and {name for _, name in if_nameindex()} == {"lo"}
    assert args.library.is_file() and not Path("/run/v3/sender.json").exists()
    print(json.dumps(verify(args.gateway, args.library, args.case), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
