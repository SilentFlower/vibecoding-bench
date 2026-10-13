#!/usr/bin/env python3
"""固定账号进程监督；CLI 网络故障隔离 CLI，保留独立发送器。"""
import fcntl
import json
import os
import re
import signal
import subprocess
import time
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit


def main() -> None:
    """恢复固定环境，检查健康并监督内部服务。

    :return: None；故障退出并由管理端重新对账
    """
    root = Path("/run/v3")
    root.mkdir(exist_ok=True, mode=0o700)
    root.chmod(0o700)
    (root / "ready").unlink(missing_ok=True)
    (root / "network.pid").unlink(missing_ok=True)
    (root / "mitm.pid").unlink(missing_ok=True)
    Path("/tmp/sidecar-ready").unlink(missing_ok=True)
    machine_id = os.environ["V3_MACHINE_ID"]
    if not re.fullmatch(r"[a-f0-9]{32}", machine_id):
        raise RuntimeError("环境 machine-id 不合法")
    Path("/etc/machine-id").write_text(machine_id + "\n")
    # passthrough 不信任 MITM CA；quota/capture 切换时才发布公钥并显式注入对应 CLI。
    Path("/etc/mitm").mkdir(exist_ok=True)
    children = []
    stopping = False

    def stop(signum, frame) -> None:
        """将退出信号转换成统一进程收口。"""
        nonlocal stopping
        stopping = True

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    try:
        environment = dict(os.environ, V3_ACCOUNT="1")
        network = subprocess.Popen(["bash", "/sidecar/start.sh"], env=environment)
        children.append(network)
        deadline = time.monotonic() + 120
        while not Path("/tmp/sidecar-ready").exists():
            if stopping or network.poll() is not None or time.monotonic() > deadline:
                raise RuntimeError("网络启动未完成")
            time.sleep(0.2)
        sender_path = root / "sender.json"
        configuration = json.loads(sender_path.read_text())
        original_proxy = configuration.get("proxy_source", configuration["proxy_url"])
        proxy = urlsplit(original_proxy)
        address = (root / "proxy-ip").read_text().strip()
        userinfo = proxy.netloc.rsplit("@", 1)[0] + "@" if "@" in proxy.netloc else ""
        configuration["proxy_source"] = original_proxy
        configuration["proxy_url"] = urlunsplit((proxy.scheme, f"{userinfo}{address}:{proxy.port}", proxy.path, proxy.query, ""))
        temporary = root / "sender.tmp"
        temporary.write_text(json.dumps(configuration))
        temporary.chmod(0o600)
        temporary.replace(sender_path)
        sender = subprocess.Popen(["/usr/local/bin/account-sender"])
        children.append(sender)
        (root / "ready").touch()
        while not stopping:
            if any(process.poll() is not None for process in children):
                raise RuntimeError("账号内部服务退出")
            with (root / "network.lock").open("a") as lock:
                try:
                    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError:
                    pass
                else:
                    pid = int((root / "network.pid").read_text())
                    status = Path(f"/proc/{pid}/stat")
                    if not status.exists() or status.read_text().split()[2] == "Z":
                        # 网络监听只服务 CLI；它退出不能连带中断已接受的 API 流。
                        (root / "cli-unhealthy").touch()
                    else:
                        (root / "cli-unhealthy").unlink(missing_ok=True)
            time.sleep(0.2)
    finally:
        (root / "ready").unlink(missing_ok=True)
        for process in children:
            if process.poll() is None:
                process.terminate()
        # tini 回收孤儿；容器退出收口所有本命名空间的执行，不留直连进程。
        for process in children:
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()


if __name__ == "__main__":
    main()
