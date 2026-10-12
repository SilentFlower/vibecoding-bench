#!/usr/bin/env python3
"""在账号无 CLI 作业时切换 Recorder；网络设备和 CA 始终保留。"""
import fcntl
import json
import os
import signal
import socket
import subprocess
import time
from pathlib import Path


def main() -> None:
    """停止旧 Recorder 连接，启动新上下文并写入确认。

    :return: None，失败以非零退出码报告
    """
    root = Path("/run/v3")
    with (root / "network.lock").open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        pid_file = root / "mitm.pid"
        if pid_file.exists():
            pid = int(pid_file.read_text())
            try:
                os.kill(pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            deadline = time.monotonic() + 10
            while time.monotonic() < deadline:
                # 僵尸已无连接，由 PID1 回收；PID 记录仅允许同一镜像的 mitmdump。
                status = Path(f"/proc/{pid}/stat")
                if not status.exists() or status.read_text().split()[2] == "Z":
                    break
                time.sleep(0.1)
            else:
                raise RuntimeError("旧抓包进程未完成收口")
        context_file = root / "context.json"
        context = json.loads(context_file.read_text()) if context_file.exists() else {}
        environment = dict(os.environ)
        environment["V3_ACCOUNT"] = "1"
        # Recorder 是 root 网络服务；CA 生成目录不能随 CLI HOME 改到账号用户目录。
        environment["HOME"] = "/root"
        permitted = {"STATS_FILE", "CAPTURE_FILE", "CAPTURE_INDEX_FILE", "CAPTURE_FULL_HTTP",
            "CAPTURE_MAX_BODY_BYTES", "CAPTURE_SCOPE", "CAPTURE_MODE", "CAPTURE_TARGETS", "QUOTA_SOURCE", "QUOTA_IDENTITY", "QUOTA_STATE_FILE",
            "QUOTA_SIGNAL_FILE", "QUOTA_OBSERVATIONS_FILE", "QUOTA_CREDENTIALS_FILE"}
        environment.update({key: str(value) for key, value in context.items() if key in permitted})
        environment.setdefault("STATS_FILE", "/run/v3/idle-stats.jsonl")
        command = ["proxychains4", "-q", "mitmdump", "--mode", "socks5",
            "--listen-host", "127.0.0.1", "--listen-port", "8080", "-s", "/sidecar/recorder.py"]
        if context.get("CAPTURE_FULL_HTTP") != "1":
            command += ["--ignore-hosts", r"^(platform\.claude\.com)$"]
        if context.get("SAVE_FULL_FLOWS") == "1":
            command += ["--save-stream-file", str(Path(context["STATS_FILE"]).parent / "capture.flow")]
        with open("/var/log/mitmdump.log", "ab") as log:
            process = subprocess.Popen(command, env=environment, stdout=log, stderr=log)
        pid_file.write_text(str(process.pid))
        for _ in range(80):
            if process.poll() is not None:
                raise RuntimeError("新抓包进程启动失败")
            try:
                with socket.create_connection(("127.0.0.1", 8080), timeout=0.1):
                    temporary = root / "context-ack.tmp"
                    temporary.write_text(json.dumps({"QUOTA_SOURCE": context.get("QUOTA_SOURCE", "")}))
                    temporary.replace(root / "context-ack.json")
                    return
            except OSError:
                time.sleep(0.1)
        process.terminate()
        raise RuntimeError("新抓包监听未就绪")


if __name__ == "__main__":
    main()
