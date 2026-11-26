"""在一次性候选账号容器里，通过真实公开网关运行受管 CLI 本机 HTTPS 回归。"""

import argparse
from contextlib import ExitStack, closing
from hashlib import sha256
from http.client import HTTPConnection
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
from secrets import token_hex
from socket import if_nameindex
import sqlite3
from subprocess import DEVNULL, Popen, TimeoutExpired, run
from tempfile import TemporaryDirectory
from threading import Thread
from time import monotonic, sleep, time_ns
from uuid import uuid4

from file_activity import monitor_read, read_counts
from scenario import BARRIER, OBSERVATIONS, cancel_partial, exercise


def request(port, method, path, token, body=None):
    """调用本机测试管理入口。@param port 端口。@param method 方法。@param path 固定路径。
    @param token 合成授权。@param body 可选正文。@return 状态和 JSON 结果。
    """
    with closing(HTTPConnection("127.0.0.1", port, timeout=10)) as client:
        client.request(
            method,
            path,
            json.dumps(body).encode() if body is not None else None,
            {"Authorization": "Bearer " + token, "Content-Type": "application/json"},
        )
        response = client.getresponse()
        return response.status, json.loads(response.read())


def wait_ready(probe, process):
    """等待测试子进程就绪。@param probe 状态回读函数。@param process 服务进程。@return 无。"""
    until = monotonic() + 30
    while monotonic() < until and process.poll() is None:
        try:
            if probe():
                return
        except OSError:
            pass
        sleep(0.05)
    raise RuntimeError("候选验证服务未就绪，请检查容器服务日志")


def stop(process):
    """回收本次测试创建的子进程。@param process 子进程。@return 无。"""
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=5)
    except TimeoutExpired:
        process.kill()
        process.wait()


def verify(gateway, sender, directory, *, probe_proxy=None, managed_proxy=None):
    """在合成账号运行环境内测试公开入口和 TLS，要求一次性容器。
    @param gateway 网关程序。@param sender 与其配套的账号发送器。@param directory 测试临时目录。
    @param probe_proxy 拒绝对照的账号代理。@param managed_proxy 单会话正对照。@return 含模型计数、状态和收包证据的摘要。
    """
    if not Path("/.dockerenv").exists() or [n for _, n in if_nameindex()] != ["lo"]:
        raise RuntimeError("仅允许 docker --network none 的一次性容器")
    if (
        Path("/run/v3/sender.json").exists()
        or OBSERVATIONS.exists()
        or BARRIER.exists()
    ):
        raise RuntimeError("发现已有账号状态，请使用新的候选测试容器")
    for path in (Path("/native"), Path("/flows/api")):
        if path.is_dir() and any(path.iterdir()):
            raise RuntimeError("验收要使用空白的账号数据与采集目录")
    synthetic_at = "sk-ant-oat01-native-lab-" + token_hex(32)
    (Path("/verify-native") / "synthetic-at.sha256").write_text(
        sha256(synthetic_at.encode()).hexdigest()
    )
    crt, key = (Path("/verify-native") / n for n in ["localhost.crt", "localhost.key"])
    run(
        [
            "openssl",
            "req",
            "-x509",
            "-newkey",
            "rsa:2048",
            "-nodes",
            "-keyout",
            str(key),
            "-out",
            str(crt),
            "-days",
            "1",
            "-subj",
            "/CN=127.0.0.1",
            "-addext",
            "subjectAltName=IP:127.0.0.1",
        ],
        stdout=DEVNULL,
        stderr=DEVNULL,
        check=True,
    )
    os.chown(key, 1001, 1001)
    cfg = Path("/run/v3/sender.json")
    for d in (cfg.parent / "tui-v2", Path("/native"), Path("/flows/api")):
        d.mkdir(mode=0o700, parents=True, exist_ok=True)
        os.chown(d, 1001, 1001)
    env_id, release = uuid4().hex, "native-candidate-fixture"
    deploy = "native-" + uuid4().hex
    hostname = "flower2api-" + sha256(deploy.encode()).hexdigest()[:12] + "-" + env_id
    with open("/etc/hosts", "a") as hosts:
        hosts.write("\n127.0.0.1 " + hostname + "\n")
    secret, admin, internal = (token_hex(32) for _ in range(3))
    binding = {
        "account_id": 1,
        "environment_id": env_id,
        "generation": 1,
        "release_id": release,
        "endpoint": f"http://{hostname}:8091",
        "secret": secret,
    }
    unexpected = []

    class Registry(BaseHTTPRequestHandler):
        """仅提供账号发现接口，同时记录候选误入旧代理的连接。"""

        def log_message(self, *_):
            """访问日志保留在测试计数器。@return 无。"""

        def do_GET(self):
            """返回与账号绑定的合成注册信息。@return 无。"""
            if self.headers.get("Authorization") != "Bearer " + internal:
                return self.send_error(404)
            path = self.path.partition("?")[0]
            if path == "/internal/v3/transport/1":
                data = binding
            elif path.startswith("/internal/v3/native-captures/1/"):
                from native_capture import read_capture

                try:
                    data = read_capture(
                        Path("/"),
                        1,
                        path.removeprefix("/internal/v3/native-captures/1/"),
                    )
                except FileNotFoundError:
                    return self.send_error(404)
            else:
                return self.send_error(404)
            wire = json.dumps(data).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(wire)))
            self.end_headers()
            self.wfile.write(wire)

        def do_CONNECT(self):
            """记录普通模型发送路径的尝试，全部拒绝拨号。@return 无。"""
            unexpected.append(self.path)
            self.send_error(403)

    with ExitStack() as stack:
        registry = stack.enter_context(ThreadingHTTPServer(("127.0.0.1", 0), Registry))
        Thread(target=registry.serve_forever, daemon=True).start()
        stack.callback(registry.shutdown)
        origin = f"http://127.0.0.1:{registry.server_port}"
        if probe_proxy:
            Path("/verify-native/probe-account-proxy").touch()
        account_proxy = managed_proxy.url if managed_proxy else probe_proxy or origin
        cfg.write_text(
            json.dumps(
                {
                    "binding": binding,
                    "proxy_url": account_proxy,
                    "allowed_origin": "https://api.anthropic.com",
                    **(
                        {"native_capture_dir": "/flows/api/cc-prepared"}
                        if not managed_proxy or managed_proxy.capture_mode != "disabled"
                        else {}
                    ),
                    "tui_v2": {"max_reservations": 4},
                }
            )
        )
        os.chown(cfg, 0, 1001)
        cfg.chmod(0o640)
        shared = {
            "PATH": os.defpath,
            "LANG": "C.UTF-8",
            "HOME": "/tmp",
            "RUST_LOG": "warn",
            "TOKIO_WORKER_THREADS": "2",
        }
        source = Popen(
            [str(sender)],
            env={
                **shared,
                "V3_SENDER_CONFIG": str(cfg),
                "V3_TUI_SESSION_HOST": "1",
                "V3_TUI_MANAGED_OAUTH": "1",
            },
            user=1001,
            group=1001,
            extra_groups=[],
        )
        stack.callback(stop, source)
        db = directory / "gateway.db"
        control = Popen(
            [str(gateway)],
            cwd=directory,
            env={
                **shared,
                "SERVER_PORT": "18090",
                "SERVER_HOST": "127.0.0.1",
                "DATABASE_DRIVER": "sqlite",
                "DATABASE_DSN": str(db),
                "ADMIN_PASSWORD": admin,
                "V3_INTERNAL_TOKEN": internal,
                "V3_DEPLOYMENT_ID": deploy,
                "V3_RELEASE": release,
                "V3_RUNTIME_URL": origin,
                "LOG_LEVEL": "warn",
            },
        )
        stack.callback(stop, control)

        def manage(method, path, body=None):
            status, result = request(18090, method, "/admin/" + path, admin, body)
            if status not in (200, 201):
                raise RuntimeError(f"管理请求 {path} 返回 {status}")
            return result

        wait_ready(
            lambda: request(18090, "GET", "/admin/accounts", admin)[0] == 200, control
        )
        wait_ready(
            lambda: (
                request(8091, "GET", "/internal/status", secret)[1]
                .get("tui_v2", {})
                .get("ready")
            ),
            source,
        )
        manage(
            "PUT",
            "settings",
            {
                "allowed_user_agents": "",
                "request_diagnostics_log_mode": "info"
                if managed_proxy and managed_proxy.capture_mode == "info"
                else "debug",
            },
        )
        account = manage(
            "POST",
            "accounts",
            {
                "email": "native-lab@example.invalid",
                "request_backend": "native293",
                "auth_type": "oauth",
                "access_token": synthetic_at,
                "refresh_token": "sk-ant-ort01-native-lab-" + token_hex(32),
                "expires_at": time_ns() // 1_000_000 + 1800000,
                "subscription_type": "max",
                "proxy_url": account_proxy,
                "auto_telemetry": False,
                "auto_poll_usage": False,
                "concurrency": 2,
                "rpm_limit": 0,
            },
        )
        assert account["id"] == 1
        account = manage("GET", "accounts/1")
        assert account["tui_v2_available"]
        manage(
            "PUT",
            "accounts/1",
            {
                "request_backend": "tui_v2",
                "request_backend_revision": account["request_backend_revision"],
            },
        )
        token = manage(
            "POST", "tokens", {"name": "native-fixture", "allowed_accounts": "1"}
        )["token"]
        proof = exercise(
            18090, token, directory, stack, managed_proxy=managed_proxy is not None
        )
        with closing(sqlite3.connect(db)) as connection:
            wait_ready(
                lambda: (
                    connection.execute("SELECT count(*) FROM usage_records").fetchone()[
                        0
                    ]
                    >= 2
                ),
                control,
            )
            proof["usage_records"], proof["input_tokens"], proof["output_tokens"] = (
                connection.execute(
                    "SELECT count(*),sum(input_tokens),sum(output_tokens) FROM usage_records"
                ).fetchone()
            )
        assert proof["usage_records"] == 2 and (
            proof["input_tokens"],
            proof["output_tokens"],
        ) == (14, 10)
        if managed_proxy:
            assert not unexpected
            result = managed_proxy.check(proof, source)
            result["capture_api"] = managed_proxy.check_captures(
                manage, control, result, synthetic_at
            )
            return result
        cancel_watcher = monitor_read(stack, directory / "client-note")
        cancel_partial(18090, token)
        wait_ready(lambda: '"canceled_model"' in OBSERVATIONS.read_text(), source)
        canceled = [json.loads(line) for line in OBSERVATIONS.read_text().splitlines()]
        attempts = [r["received"] for r in canceled if r.get("cancel_trial")]
        stopped = [r for r in canceled if "canceled_model" in r]
        assert len(attempts) == 1 and [r["canceled_model"] for r in stopped] == attempts
        cancel_file_events = read_counts(cancel_watcher)
        assert cancel_file_events == [], cancel_file_events
        proof["cancel_case"] = {
            "model_posts": len(attempts),
            "model_stop_reason": stopped[0]["stop_reason"],
            "tool_reads": cancel_file_events.count(0x01),
            "file_events": cancel_file_events,
        }
        assert not unexpected, "受管合成模型之外出现了代理连接"
        proof["observations"] = [
            json.loads(line) for line in OBSERVATIONS.read_text().splitlines()
        ]
        return proof


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gateway", type=Path, required=True)
    parser.add_argument(
        "--sender", type=Path, default=Path("/usr/local/bin/account-sender")
    )
    args = parser.parse_args()
    with TemporaryDirectory(prefix="v2-native-") as root:
        print(
            json.dumps(
                verify(args.gateway.resolve(), args.sender.resolve(), Path(root)),
                ensure_ascii=False,
            )
        )
