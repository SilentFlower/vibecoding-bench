#!/usr/bin/env python3
"""读取官方状态栏已产生的额度；只写本地观察，不发网络请求。"""
from __future__ import annotations

import argparse
import fcntl
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from math import isfinite
from pathlib import Path


def statusline_quota_observation(rate_limits: object, observed_at: float) -> dict:
    """归一化官方状态栏的完整通用窗口。

    :param rate_limits: 官方 stdin 的 rate_limits 对象
    :param observed_at: 已确认的正常响应时间，UTC 秒
    :return: 与现有被动合并协议一致的窗口观察；缺失窗口不补零
    """
    windows = {}
    if isinstance(rate_limits, dict) and type(observed_at) in (int, float) and isfinite(observed_at):
        for key, horizon in (("five_hour", 6 * 3600), ("seven_day", 8 * 86400)):
            window = rate_limits.get(key)
            if not isinstance(window, dict):
                continue
            used, reset = window.get("used_percentage"), window.get("resets_at")
            if (type(used) not in (int, float) or not isfinite(used) or not 0 <= used <= 100
                    or type(reset) not in (int, float) or not isfinite(reset)
                    or not observed_at < reset <= observed_at + horizon):
                continue
            windows[key] = {"observed_at": observed_at, "utilization": float(used),
                "reset_at": float(reset), "resets_at": datetime.fromtimestamp(reset, timezone.utc).isoformat(),
                "rejected": False, "exhausted": used >= 100}
    return {"windows": windows, "observed_at": observed_at, "allowed": bool(windows), "origin": "cli"}


def collect_statusline(payload: object, configuration: dict, now: float) -> bool:
    """把当前执行的新正常响应额度追加到专用文件。

    :param payload: 官方状态栏输入；全文不会保存
    :param configuration: 管理端生成的 source、identity、cwd、输出及开始时间
    :param now: 当前 UTC 秒
    :return: 写入新观察时为 True，无额度、旧响应或重复输出时为 False
    """
    if not isinstance(payload, dict) or payload.get("cwd") != configuration["cwd"]:
        return False
    session = payload.get("session_id")
    transcript = Path(str(payload.get("transcript_path") or ""))
    if (not isinstance(session, str) or not session or len(session) > 128
            or transcript.parent != Path(configuration["session_dir"])
            or transcript.name != session + ".jsonl" or transcript.is_symlink()):
        return False
    # 只读取已知主会话的有限尾部；状态栏缓存不能替代本次正式响应证据。
    with transcript.open("rb") as handle:
        size = handle.seek(0, os.SEEK_END)
        start = max(0, size - 512 * 1024)
        handle.seek(start)
        if start:
            handle.readline()
        lines = handle.read().splitlines()
    response = None
    for line in reversed(lines):
        try:
            item = json.loads(line)
        except (ValueError, UnicodeError):
            continue
        message = item.get("message") if isinstance(item, dict) else None
        if (isinstance(message, dict) and message.get("role") == "assistant"
                and not item.get("isSidechain") and not item.get("isApiErrorMessage")
                and message.get("model") != "<synthetic>"):
            response = item
            break
    if not response:
        return False
    timestamp = datetime.fromisoformat(str(response.get("timestamp") or "").replace("Z", "+00:00"))
    if timestamp.tzinfo is None:
        return False
    observed = timestamp.timestamp()
    response_id = response["message"].get("id")
    if (not configuration["started_at"] <= observed <= now + 5
            or not isinstance(response_id, str) or not response_id or len(response_id) > 200
            or any(response.get(key, session) != session for key in ("sessionId", "session_id"))):
        return False
    rate_limits = payload.get("rate_limits")
    observation = statusline_quota_observation(rate_limits, observed)
    if not observation["windows"]:
        return False
    output = Path(configuration["output"])
    state = output.with_suffix(".state.json")
    signature = {"session_id": session, "response_id": response_id,
        "windows": {key: {"used_percentage": window["utilization"], "resets_at": window["reset_at"]}
                    for key, window in observation["windows"].items()}}
    with output.with_suffix(".lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        previous = json.loads(state.read_text()) if state.is_file() else {}
        if previous == signature:
            return False
        if previous.get("session_id") not in (None, session):
            return False
        event = {"source": configuration["source"], "identity": configuration["identity"],
            "ts": observed, "origin": "cli", "session_id": session, "response_id": response_id,
            "rate_limits": signature["windows"]}
        # 在更新去重状态前落盘观察，取消脚本不会把尚未写出的额度标记为已消费。
        with output.open("a") as destination:
            destination.write(json.dumps(event, separators=(",", ":")) + "\n")
            destination.flush()
        temporary = state.with_name(state.name + f".{os.getpid()}.tmp")
        temporary.write_text(json.dumps(signature))
        temporary.replace(state)
    return True


def main() -> None:
    """执行本地采集并保留用户原有状态栏输出。

    :return: None；无效或暂未就绪的数据不影响 CLI 正式执行
    """
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True, type=Path)
    arguments = parser.parse_args()
    raw = sys.stdin.read(1024 * 1024 + 1)
    configuration = json.loads(arguments.config.read_text())
    payload = None
    try:
        if len(raw) <= 1024 * 1024:
            payload = json.loads(raw)
            collect_statusline(payload, configuration, time.time())
    except (OSError, ValueError, TypeError, KeyError, OverflowError):
        # 启动早期没有响应或状态栏被取消时保留未知，不能追加网络查询兜底。
        pass
    previous = configuration.get("previous_command")
    if isinstance(previous, str) and previous:
        try:
            result = subprocess.run(["sh", "-c", previous], input=raw, text=True,
                capture_output=True, timeout=5, check=False)
            sys.stdout.write(result.stdout)
        except (OSError, subprocess.TimeoutExpired):
            pass
    elif isinstance(payload, dict):
        observation = statusline_quota_observation(payload.get("rate_limits"), time.time())
        text = " | ".join(f"{'5h' if key == 'five_hour' else '7d'}: {value['utilization']:g}%"
                          for key, value in observation["windows"].items())
        sys.stdout.write(text or "额度未知")


if __name__ == "__main__":
    main()
