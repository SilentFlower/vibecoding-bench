#!/usr/bin/env python3
"""在账号无 CLI 作业时切换原始透传或受控 Recorder。"""
import argparse
import fcntl
import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path

from runtime_diagnostics import NETWORK_FAILURE_PREFIX, runtime_failure, write_runtime_failure


_NETWORK_MODES = {"passthrough", "quota", "capture"}


def _listener_identity(pid: int) -> tuple[str, str] | None:
    """
    读取监听进程状态，并拒绝把复用 PID 当成本系统进程。

    :param pid: pid 文件记录的进程号
    :return: 进程状态和内核启动时刻；进程已消失时为 None
    """
    process = Path(f"/proc/{pid}")
    try:
        fields = (process / "stat").read_text().split()
        command = (process / "cmdline").read_bytes().replace(b"\0", b" ").decode("utf-8", errors="replace")
    except (FileNotFoundError, ProcessLookupError):
        # /proc 已打开后原进程退出会返回 ESRCH，仍然表示无需再收口该进程。
        return None
    state, started_at = fields[2], fields[21]
    if state == "Z":
        return state, started_at
    if "v3-passthrough" not in command and "mitmdump" not in command:
        raise RuntimeError("旧网络监听 PID 已被未知进程占用")
    return state, started_at


def _owned_process_state(pid: int, started_at: str) -> str | None:
    """
    核对原进程是否仍存在，避免 PID 复用后误杀其它进程。

    :param pid: 已验证监听进程号
    :param started_at: 初次验证得到的内核启动时刻
    :return: 原进程状态；已退出或 PID 被复用时为 None
    """
    try:
        fields = Path(f"/proc/{pid}/stat").read_text().split()
    except (FileNotFoundError, ProcessLookupError):
        return None
    return fields[2] if fields[21] == started_at else None


def _terminate_listener(pid_file: Path) -> bool:
    """
    停止上一网络监听进程并确认连接已经收口。

    :param pid_file: 保存监听进程 PID 的文件
    :return: 优雅退出或已无监听时为 True，使用强制退出时为 False。
    """
    if not pid_file.exists():
        return True
    pid = int(pid_file.read_text())
    identity = _listener_identity(pid)
    if identity is None:
        pid_file.unlink(missing_ok=True)
        return True
    state, started_at = identity
    if state == "Z":
        pid_file.unlink(missing_ok=True)
        return True
    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        pid_file.unlink(missing_ok=True)
        return True
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline:
        state = _owned_process_state(pid, started_at)
        if state is None or state == "Z":
            pid_file.unlink(missing_ok=True)
            return True
        time.sleep(0.1)
    # relay/Recorder 已通过私有 PID 和 cmdline 双重确认；优雅退出失效时必须定向强制收口，不能让新旧模式并存。
    try:
        os.kill(pid, signal.SIGKILL)
    except ProcessLookupError:
        pid_file.unlink(missing_ok=True)
        return False
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        state = _owned_process_state(pid, started_at)
        if state is None or state == "Z":
            pid_file.unlink(missing_ok=True)
            return False
        time.sleep(0.1)
    raise RuntimeError("旧网络监听进程未完成强制收口")


def _restore_capture_ca() -> None:
    """
    抓包模式启动前恢复持久 CA 私钥。

    :return: None
    """
    source = Path("/ca")
    target = Path("/root/.mitmproxy")
    target.mkdir(parents=True, exist_ok=True, mode=0o700)
    for name in ("mitmproxy-ca.pem", "mitmproxy-ca-cert.pem"):
        if (source / name).is_file():
            shutil.copy2(source / name, target / name)


def _publish_capture_ca(process: subprocess.Popen) -> None:
    """
    等待 mitmproxy CA 就绪并发布仅供本次 CLI 显式信任的证书。

    :param process: 当前 Recorder 进程
    :return: None
    """
    source = Path("/root/.mitmproxy")
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError("新抓包进程在 CA 就绪前退出")
        if (source / "mitmproxy-ca-cert.pem").is_file():
            break
        time.sleep(0.1)
    else:
        raise RuntimeError("抓包 CA 未在截止时间内就绪")
    Path("/ca").mkdir(exist_ok=True)
    Path("/etc/mitm").mkdir(exist_ok=True)
    for name in ("mitmproxy-ca.pem", "mitmproxy-ca-cert.pem"):
        if (source / name).is_file():
            shutil.copy2(source / name, Path("/ca") / name)
    shutil.copy2(source / "mitmproxy-ca-cert.pem", "/etc/mitm/mitmproxy-ca-cert.pem")
    Path("/etc/mitm/mitmproxy-ca-cert.pem").chmod(0o644)


def _reuse_passthrough(root: Path, context: dict) -> bool:
    if context.get("NETWORK_INSPECTION_MODE") != "passthrough" or context.get("QUOTA_SOURCE"):
        return False
    try:
        acknowledgement = json.loads((root / "context-ack.json").read_text())
        pid = int((root / "network.pid").read_text())
        identity = _listener_identity(pid)
        command = Path(f"/proc/{pid}/cmdline").read_bytes()
        valid = (identity is not None and identity[0] != "Z" and b"v3-passthrough" in command
            and acknowledgement.get("pid") == pid and acknowledgement.get("started_at") == identity[1]
            and acknowledgement.get("NETWORK_INSPECTION_MODE") == "passthrough"
            and acknowledgement.get("QUOTA_SOURCE") == "" and acknowledgement.get("process") == "passthrough")
        if valid:
            with socket.create_connection(("127.0.0.1", 8080), timeout=0.2):
                return True
    except (OSError, ValueError, RuntimeError):
        pass
    return False


def _switch_context(root: Path, arguments, attempt: dict) -> None:
    """执行串行切换，并更新仅供失败定位的固定步骤。:param root: 私有目录。:param arguments: 参数。:param attempt: 步骤事实。:return: None。"""
    with (root / "network.lock").open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        context_file = root / "context.json"
        context = json.loads(context_file.read_text()) if context_file.exists() else {}
        attempt['context'] = {'source': context.get('QUOTA_SOURCE', ''),
            'mode': context.get('NETWORK_INSPECTION_MODE', 'passthrough')}
        attempt['phase'] = 'reuse_listener'
        if arguments.reuse_passthrough and _reuse_passthrough(root, context):
            return
        if arguments.require_reuse:
            # 已有兄弟 CLI 时，监听证明不完整只能拒绝新入场，不能重启并截断旧连接。
            raise RuntimeError("共享透传监听不可复用，拒绝影响在途 CLI")
        pid_file = root / "network.pid"
        legacy_pid = root / "mitm.pid"
        attempt['phase'] = 'stop_listener'
        graceful = _terminate_listener(pid_file if pid_file.exists() else legacy_pid)
        legacy_pid.unlink(missing_ok=True)
        (root / "context-ack.json").unlink(missing_ok=True)
        mode = str(context.get("NETWORK_INSPECTION_MODE") or "passthrough")
        if mode not in _NETWORK_MODES:
            raise RuntimeError("网络检查模式不合法")
        environment = dict(os.environ)
        environment["V3_ACCOUNT"] = "1"
        proxy_ip = root / "proxy-ip"
        if proxy_ip.is_file():
            # 默认路由切到 tun 后不能再递归解析代理主机；复用启动阶段固化的 IP。
            environment["UPSTREAM_SOCKS5_HOST"] = proxy_ip.read_text().strip()
        permitted = {"STATS_FILE", "CAPTURE_FILE", "CAPTURE_INDEX_FILE", "CAPTURE_FULL_HTTP",
            "CAPTURE_MAX_BODY_BYTES", "CAPTURE_SCOPE", "CAPTURE_MODE", "CAPTURE_TARGETS", "CAPTURE_CONTEXT", "QUOTA_SOURCE", "QUOTA_IDENTITY", "QUOTA_STATE_FILE",
            "QUOTA_SIGNAL_FILE", "QUOTA_OBSERVATIONS_FILE", "QUOTA_CREDENTIALS_FILE", "QUOTA_WARMUP",
            "NETWORK_INSPECTION_MODE"}
        environment.update({key: str(value) for key, value in context.items() if key in permitted})
        if mode == "passthrough":
            command = ["python3", "/usr/local/bin/v3-passthrough"]
            process_kind = "passthrough"
            log_path = "/var/log/v3-passthrough.log"
        else:
            # Recorder 是 root 网络服务；CA 生成目录不能随 CLI HOME 改到账号用户目录。
            environment["HOME"] = "/root"
            environment.setdefault("STATS_FILE", "/run/v3/idle-stats.jsonl")
            attempt['phase'] = 'restore_ca'
            _restore_capture_ca()
            command = ["proxychains4", "-q", "mitmdump", "--mode", "socks5",
                "--listen-host", "127.0.0.1", "--listen-port", "8080", "-s", "/sidecar/recorder.py"]
            if context.get("SAVE_FULL_FLOWS") == "1":
                command += ["--save-stream-file", str(Path(context["STATS_FILE"]).parent / "capture.flow")]
            process_kind = "recorder"
            log_path = "/var/log/mitmdump.log"
        attempt['phase'] = 'start_listener'
        with open(log_path, "ab") as log:
            process = subprocess.Popen(command, env=environment, stdout=log, stderr=log)
        pid_file.write_text(str(process.pid))
        attempt['phase'] = 'wait_listener'
        for _ in range(80):
            if process.poll() is not None:
                raise RuntimeError("新网络监听进程启动失败")
            try:
                connection = socket.create_connection(("127.0.0.1", 8080), timeout=0.1)
            except OSError:
                time.sleep(0.1)
                continue
            with connection:
                # 只重试连接探测；CA 或确认写入故障必须保留真实原因，不能伪装成监听超时。
                if process_kind == "recorder":
                    attempt['phase'] = 'publish_ca'
                    _publish_capture_ca(process)
                attempt['phase'] = 'confirm_listener'
                temporary = root / "context-ack.tmp"
                identity = _listener_identity(process.pid)
                if identity is None:
                    raise RuntimeError("新网络监听已退出")
                temporary.write_text(json.dumps({
                    "QUOTA_SOURCE": context.get("QUOTA_SOURCE", ""),
                    "NETWORK_INSPECTION_MODE": mode,
                    "process": process_kind,
                    "pid": process.pid,
                    "started_at": identity[1],
                    "previous_listener_graceful": graceful is not False,
                }))
                temporary.replace(root / "context-ack.json")
                return
        process.terminate()
        raise RuntimeError("新网络监听未就绪")


def main() -> None:
    """切换网络并以固定错误协议返回私有诊断，避免输出任意异常正文。

    :return: None；失败保存受限记录并以状态 1 退出。
    """
    parser = argparse.ArgumentParser()
    parser.add_argument('--reuse-passthrough', action='store_true')
    parser.add_argument('--require-reuse', action='store_true')
    arguments = parser.parse_args()
    root = Path('/run/v3')
    attempt = {'phase': 'read_context', 'context': {}}
    try:
        _switch_context(root, arguments, attempt)
    except Exception as error:
        record = runtime_failure(error, attempt['phase'], attempt['context'])
        write_runtime_failure(root / 'diagnostics', record)
        try:
            sys.stderr.write(NETWORK_FAILURE_PREFIX + json.dumps(record, separators=(',', ':')) + '\n')
        except OSError:
            # 回执管道已关闭时仍保留原故障退出码，私有记录已尽力发布。
            pass
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
