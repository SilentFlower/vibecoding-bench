"""账号容器隔离演练：空数据、无公网网络、合成 CLI 和 mock 上游。

用法见 README；本脚本不执行真实登录，不加载现有账号。
"""
import argparse
import base64
import copy
import json
import os
import shutil
import socket
import sqlite3
import subprocess
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace

import docker
import requests
from account_runtime import AccountRuntime, atomic_json


def wait_cli_started(runtime: AccountRuntime, client, token: str) -> str:
    """确认合成 CLI 实际进入 tmux，不以创建 exec 代替运行证据。

    :param runtime: 当前合成账号环境
    :param client: 当前 Docker 客户端
    :param token: 本代执行 token
    :return: 正在运行的 driver exec ID
    """
    job = runtime.job_for_container(token)
    container = runtime._container(job["row"])
    deadline = time.monotonic() + 15
    last_pane = b""
    while time.monotonic() < deadline:
        state = client.api.exec_inspect(job["exec"])
        if state["Running"]:
            pane = container.exec_run(["tmux", "-S", job["tmux_socket"], "capture-pane", "-p"])
            last_pane = pane.output
            if pane.exit_code == 0 and b"Synthetic task pane" in pane.output:
                return job["exec"]
        elif state.get("ExitCode") is not None:
            transcript = runtime._root(job["row"]) / "workspaces" / job["run_id"] / ".bench-transcript.log"
            raise AssertionError(("合成 CLI 提前退出", state["ExitCode"], transcript.read_text()[-1000:] if transcript.exists() else ""))
        time.sleep(0.1)
    raise AssertionError(("合成 CLI 未在截止时间内进入 tmux", last_pane.decode(errors="replace")[-1000:]))


def verify_gateway_binding(configuration_path: Path, peer: str) -> None:
    """通过真实网关验证账号短 DNS 绑定和错误绑定的拒绝。

    :param configuration_path: 合成账号发送器配置路径
    :param peer: 对应账号容器的内网地址
    :return: None；网关未到达账号 TLS 客户端或发生重放时失败
    """
    original = json.loads(configuration_path.read_text())
    configuration = copy.deepcopy(original)
    internal_token = uuid.uuid4().hex + uuid.uuid4().hex
    account_id = 0

    class RuntimeHandler(BaseHTTPRequestHandler):
        """仅返回本次合成账号绑定，不执行调度或访问公网。"""

        def do_GET(self):
            """校验内部请求后返回当前绑定，返回 None。"""
            binding = configuration["binding"]
            if self.path != f"/internal/v3/transport/{account_id}" or self.headers.get("Authorization") != "Bearer " + internal_token:
                self.send_error(404)
                return
            body = json.dumps(binding).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format, *args):
            """关闭请求日志以免输出测试秘密，返回 None。"""
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), RuntimeHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    with socket.socket() as available:
        available.bind(("127.0.0.1", 0))
        port = available.getsockname()[1]
    password = uuid.uuid4().hex + uuid.uuid4().hex
    environment = {**os.environ, "SERVER_HOST": "127.0.0.1", "SERVER_PORT": str(port),
        "ADMIN_PASSWORD": password, "DATABASE_DRIVER": "sqlite", "DATABASE_DSN": "/verify/gateway-binding.sqlite",
        "V3_RUNTIME_URL": f"http://127.0.0.1:{server.server_port}", "V3_INTERNAL_TOKEN": internal_token}
    process = None
    session = requests.Session()
    session.trust_env = False
    base = f"http://127.0.0.1:{port}"
    try:
        with Path("/verify/gateway-binding.log").open("w") as output:
            process = subprocess.Popen(["/app/claude-code-gateway"], env=environment, stdout=output, stderr=output)
        admin = {"Authorization": "Bearer " + password}
        deadline = time.monotonic() + 30
        while True:
            try:
                response = session.get(base + "/admin/accounts", headers=admin, timeout=2)
                if response.status_code == 200:
                    break
            except requests.ConnectionError:
                pass
            if process.poll() is not None or time.monotonic() >= deadline:
                raise AssertionError("合成网关未就绪")
            time.sleep(0.1)
        response = session.post(base + "/admin/accounts", headers=admin,
            json={"email": "synthetic@example.invalid", "setup_token": "synthetic-setup-token", "auto_poll_usage": False,
                "auto_telemetry": False}, timeout=5)
        assert response.status_code == 201, response.status_code
        account_id = response.json()["id"]
        configuration["binding"]["account_id"] = account_id
        atomic_json(configuration_path, configuration)
        response = session.post(base + "/admin/tokens", headers=admin,
            json={"name": "synthetic-gateway-binding", "allowed_accounts": str(account_id)}, timeout=5)
        assert response.status_code == 201
        headers = {"Authorization": "Bearer " + response.json()["token"], "User-Agent": "python-httpx/0.28.1"}
        evidence = Path("/verify/tls.jsonl")
        before = evidence.read_text().splitlines()
        response = session.post(base + "/api/v3-synthetic", headers=headers, json={"synthetic": True}, timeout=15)
        # mock TLS 只接收 ClientHello 后关闭；502 必须伴随账号来源证据，不能以任意错误冒充贯通。
        assert response.status_code == 502, response.status_code
        after = evidence.read_text().splitlines()
        assert len(after) == len(before) + 1, "网关入口未到达账号发送器，或重复发送"
        hello = json.loads(after[-1])
        assert hello["record_type"] == 22 and hello["peer"] == peer
        lease_path = base + f"/admin/runtime/accounts/{account_id}/lease"
        result = session.post(lease_path, headers=admin, json={"operation": "prepare-cli", "owner": "run:synthetic-shared"}, timeout=5)
        assert result.status_code == 200 and result.json()["lease"]["exclusive"] is False
        lease = result.json()["lease"]
        result = session.post(lease_path, headers=admin,
            json={"operation": "claim", "owner": lease["owner"], "generation": lease["generation"]}, timeout=5)
        assert result.status_code == 200
        response = session.post(base + "/api/v3-synthetic", headers=headers, json={"synthetic": True}, timeout=15)
        assert response.status_code == 502
        after_shared = evidence.read_text().splitlines()
        assert len(after_shared) == len(after) + 1, "共享 CLI 租约不能阻止真实网关 API 入场"
        assert json.loads(after_shared[-1])["peer"] == peer
        after = after_shared
        result = session.post(lease_path, headers=admin,
            json={"operation": "release", "owner": lease["owner"], "generation": lease["generation"]}, timeout=5)
        assert result.status_code == 200
        configuration["binding"]["account_id"] = account_id + 1
        response = session.post(base + "/api/v3-synthetic", headers=headers, json={"synthetic": True}, timeout=15)
        assert response.status_code == 503
        assert evidence.read_text().splitlines() == after, "错误绑定不能提交或回退直连"
        print("通过：真实网关及共享 CLI 租约期间 API -> 短 DNS 账号发送器 -> 本地 TLS；错误绑定拒绝且无重放")
    finally:
        if process is not None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
        session.close()
        atomic_json(configuration_path, original)


def verify() -> None:
    """验证固定实例、发送归属、登录重连、取消与再次唤醒。

    :return: None；断言失败以非零状态退出
    """
    parser = argparse.ArgumentParser()
    parser.add_argument("--proxy-ip", required=True)
    args = parser.parse_args()
    root = Path("/verify/data")
    root.mkdir()

    def database():
        """返回当前隔离 SQLite 连接。"""
        connection = sqlite3.connect(root / "test.sqlite")
        connection.row_factory = sqlite3.Row
        return connection

    with database() as connection:
        connection.execute("CREATE TABLE accounts(id INTEGER PRIMARY KEY,name TEXT,cc2api_account_id INTEGER)")
        connection.execute("INSERT INTO accounts VALUES(1,'synthetic',NULL)")
        connection.execute("CREATE TABLE runs(id TEXT PRIMARY KEY)")
        connection.execute("INSERT INTO runs VALUES('synthetic-run')")
    client = docker.from_env()
    account = {"id": 1, "name": "synthetic", "upstream_proxy_scheme": "socks5", "upstream_socks5_host": args.proxy_ip, "upstream_socks5_port": 1080}
    runtime = AccountRuntime(client, root, Path(os.environ["VERIFY_HOST_ROOT"]) / "data", database,
        lambda name: {"hostname": "synthetic-fixed", "machine_id": ("a" if name == "synthetic" else "b") * 32,
            "mac": "02:00:00:00:00:71" if name == "synthetic" else "02:00:00:00:00:72", "mem": "4g", "tz": "UTC", "lang": "en_US.UTF-8"}, None)
    row = runtime._row(account["name"], account["id"])
    cached = runtime._root(row) / "cli" / "9.9.9"
    binary = cached / "node_modules" / ".bin" / "claude"
    binary.parent.mkdir(parents=True)
    shutil.copy2("/fixtures/mock_cli.py", binary)
    binary.chmod(0o755)
    (cached / ".ready").touch()
    container = None
    try:
        row, container = runtime.ensure(account, "9.9.9")
        first_id, first_generation = container.id, row["generation"]
        check = container.exec_run(runtime.cli_command(["sh", "-c", "test ! -r /run/v3/sender.json && test ! -r /ca/mitmproxy-ca.pem && grep '^CapEff:' /proc/self/status"])); assert check.exit_code == 0 and b"0000000000000000" in check.output
        machine = container.exec_run(["cat", "/etc/machine-id"]).output
        configuration_path = runtime._root(row) / "runtime" / "sender.json"
        configuration = json.loads(configuration_path.read_text())
        configuration["allowed_origin"] = "http://api.anthropic.com:8081"
        configuration["quota_identity"] = "synthetic-quota"
        atomic_json(configuration_path, configuration)
        binding = configuration["binding"]
        prepared = {"account_id": 0, "environment_id": row["environment_id"], "generation": row["generation"], "request_id": str(uuid.uuid4()), "deadline_unix_ms": int(time.time() * 1000) + 30000,
            "method": "POST", "target_url": "http://api.anthropic.com:8081/v1/messages", "headers": [["Content-Type", "application/json"]], "preserve_header_casing": True}
        session = requests.Session(); session.trust_env = False
        response = session.post(binding["endpoint"] + "/internal/send", headers={"Authorization": "Bearer " + binding["secret"], "x-v3-request": base64.b64encode(json.dumps(prepared).encode()).decode()}, data=b'{ "synthetic": true }', timeout=10)
        assert response.status_code == 429 and response.content == b'{ "synthetic": true }'
        evidence = json.loads((runtime._root(row) / "flows" / "api" / "observations.jsonl").read_text().splitlines()[-1])
        assert evidence["origin"] == "api" and evidence["identity"] == "synthetic-quota"
        configuration["allowed_origin"] = "https://api.anthropic.com"
        atomic_json(configuration_path, configuration)
        prepared.update(request_id=str(uuid.uuid4()), target_url="https://api.anthropic.com/v1/messages")
        response = session.post(binding["endpoint"] + "/internal/send", headers={"Authorization": "Bearer " + binding["secret"], "x-v3-request": base64.b64encode(json.dumps(prepared).encode()).decode()}, data=b'{}', timeout=10)
        assert response.status_code == 502
        hello = json.loads(Path("/verify/tls.jsonl").read_text().splitlines()[-1])
        assert hello["record_type"] == 22
        container.reload()
        assert hello["peer"] == container.attrs["NetworkSettings"]["Networks"][runtime.network]["IPAddress"]
        verify_gateway_binding(configuration_path, hello["peer"])
        row, container, profile, home = runtime.begin_login("abcdef123456", account, "9.9.9", False)
        time.sleep(0.5)
        before = container.exec_run(["tmux", "-S", "/tmp/v3-login-abcdef123456.sock", "display-message", "-p", "#{pane_pid}"]).output
        for _ in range(2):
            attach = client.api.exec_create(container.id, ["tmux", "-S", "/tmp/v3-login-abcdef123456.sock", "attach", "-t", "abcdef123456"], stdin=True, tty=True)["Id"]
            stream = client.api.exec_start(attach, socket=True, tty=True)
            stream.close()
        after = container.exec_run(["tmux", "-S", "/tmp/v3-login-abcdef123456.sock", "display-message", "-p", "#{pane_pid}"]).output
        assert before == after
        login_token = runtime.execution_token(container.id, "login:abcdef123456")
        assert json.loads(runtime.exec_cli(login_token, ["claude", "auth", "status"], home, "9.9.9").output)["loggedIn"]
        runtime.commit_login(SimpleNamespace(sid="abcdef123456", worker_id=container.id, profile_dir=profile, name=account["name"]), 1)
        runtime.cleanup(login_token)
        original = (runtime._root(row) / "home" / ".claude" / ".credentials.json").read_bytes()
        _, container, staged, home = runtime.begin_login("abcdef654321", account, "9.9.9", True)
        time.sleep(0.3)
        runtime.cleanup(runtime.execution_token(container.id, "login:abcdef654321"))
        assert (runtime._root(row) / "home" / ".claude" / ".credentials.json").read_bytes() == original
        environment = {"CLAUDE_CODE_VERSION": "9.9.9", "TASK_PROMPT": "Synthetic only", "RUN_ID": "synthetic-run", "TIMEOUT_SEC": "120", "TIMEOUT_WRAPUP_SEC": "0"}
        token, _ = runtime.start_run(account, {"id": 1, "capture_full_http": True}, "synthetic-run", environment, {})
        wait_cli_started(runtime, client, token)
        runtime.cleanup(token)
        assert not runtime.jobs
        # 用同一 run 的不同 source 验证额度恢复，不能用两个独立 run 绕过目录换代。
        flows = root / "flows" / account["name"] / "1" / "synthetic-run"
        target = flows.resolve()
        old_flow = runtime.execution_flows(account, "run:synthetic-run:0", flows)
        (old_flow / "stats.jsonl").write_text('{"flow_id":"synthetic-evidence","usage":{"input_tokens":1}}\n')
        evidence = {path: path.read_bytes() for path in old_flow.iterdir() if path.is_file()}
        workspace = runtime._root(row) / "workspaces" / "synthetic-run"
        token, _ = runtime.start_run(account, {"id": 1, "capture_full_http": True, "quota_attempt": 1}, "synthetic-run",
            dict(environment, QUOTA_SOURCE="run:synthetic-run:1", RESUME_SESSION_ID="synthetic-session"),
            {"QUOTA_SOURCE": "run:synthetic-run:1", "QUOTA_IDENTITY": "synthetic-quota"})
        wait_cli_started(runtime, client, token)
        context = runtime.job_for_container(token)["context"]
        resumed_flow = runtime.execution_flows(account, "run:synthetic-run:1", flows)
        assert flows.resolve() == target and resumed_flow != old_flow
        assert context["STATS_FILE"] != "/flows/" + str(old_flow.relative_to(runtime._root(row) / "flows")) + "/stats.jsonl"
        invocation = json.loads((workspace / ".synthetic-invocation.json").read_text())
        assert invocation["args"][invocation["args"].index("--resume") + 1] == "synthetic-session"
        assert invocation["cwd"] == "/workspaces/synthetic-run" and invocation["home"] == "/home/node"
        runtime.cleanup(token)
        assert all(path.read_bytes() == data for path, data in evidence.items())
        assert (resumed_flow / "capture.flow").exists()
        print("通过：同 run 第二代 CLI 在原 cwd/HOME 使用原 session 恢复，证据入口不变、旧统计/原生 flow 保留，新 flow 独立")
        configuration["allowed_origin"] = "http://api.anthropic.com:8081"
        atomic_json(configuration_path, configuration)
        with database() as connection:
            connection.executemany("INSERT INTO runs(id) VALUES(?)", [("synthetic-parallel",), ("synthetic-restart",)])
        prepared.update(request_id=str(uuid.uuid4()), target_url="http://api.anthropic.com:8081/v1/v3-stream",
            deadline_unix_ms=int(time.time() * 1000) + 90000)
        with session.post(binding["endpoint"] + "/internal/send", headers={"Authorization": "Bearer " + binding["secret"],
                "x-v3-request": base64.b64encode(json.dumps(prepared).encode()).decode()}, data=b'{}', stream=True, timeout=(5, 15)) as stream:
            assert stream.status_code == 200, (stream.status_code, stream.text)
            events = stream.iter_lines(chunk_size=1)
            assert next(events).startswith(b"data: ")
            assert runtime._sender_active(row) == 1
            token, _ = runtime.start_run(account, {"id": 1, "warmup": True, "capture_full_http": True}, "synthetic-parallel",
                dict(environment, RUN_ID="synthetic-parallel", QUOTA_SOURCE="run:synthetic-parallel"),
                {"QUOTA_SOURCE": "run:synthetic-parallel", "QUOTA_IDENTITY": "synthetic-quota"})
            execution = wait_cli_started(runtime, client, token)
            assert runtime._sender_active(row) == 1
            prepared_second = dict(prepared, request_id=str(uuid.uuid4()), target_url="http://api.anthropic.com:8081/v1/messages")
            api_response = session.post(binding["endpoint"] + "/internal/send", headers={"Authorization": "Bearer " + binding["secret"],
                "x-v3-request": base64.b64encode(json.dumps(prepared_second).encode()).decode()}, data=b'{"parallel":true}', timeout=10)
            assert api_response.status_code == 429
            assert runtime._sender_active(row) == 1
            try:
                runtime.maintenance(row["environment_id"], "stop")
            except ValueError:
                pass
            else:
                raise AssertionError("并行工作期间不能停机")
            runtime.cleanup(token)
            assert not client.api.exec_inspect(execution)["Running"]
            assert runtime._sender_active(row) == 1 and not runtime.jobs
            old_token = token
            # 再建一轮 CLI 并模拟调度器重启；从落盘句柄清理，不停止 API 容器。
            token, _ = runtime.start_run(account, {"id": 1, "capture_full_http": True}, "synthetic-restart",
                dict(environment, RUN_ID="synthetic-restart", QUOTA_SOURCE="run:synthetic-restart"),
                {"QUOTA_SOURCE": "run:synthetic-restart", "QUOTA_IDENTITY": "synthetic-quota"})
            execution = wait_cli_started(runtime, client, token)
            assert token != old_token
            runtime.cleanup(old_token)
            assert client.api.exec_inspect(execution)["Running"]
            runtime.jobs.clear()
            runtime.reconcile()
            assert not client.api.exec_inspect(execution)["Running"]
            assert runtime._row(account["name"], account["id"])["state"] == "ready"
            assert runtime._sender_active(row) == 1
            recorder_pid = int((runtime._root(row) / "runtime" / "mitm.pid").read_text())
            container.exec_run(["kill", "-TERM", str(recorder_pid)])
            unhealthy = runtime._root(row) / "runtime" / "cli-unhealthy"
            deadline = time.monotonic() + 5
            while not unhealthy.exists() and time.monotonic() < deadline:
                time.sleep(0.1)
            assert unhealthy.exists(), "Recorder 退出应隔离 CLI"
            assert runtime._sender_active(row) == 1, "CLI Recorder 故障不能停止独立 API"
            try:
                runtime.claim(row, account, "run:recorder-unhealthy")
            except ValueError:
                pass
            else:
                raise AssertionError("Recorder 不健康时不能开始下一 CLI")
            runtime.maintenance(row["environment_id"], "reconcile")
            assert runtime._row(account["name"], account["id"])["state"] == "ready"
            assert runtime._sender_active(row) == 1
            continued_at = time.time()
            for line in events:
                if line.startswith(b"data: ") and json.loads(line[6:])["time"] >= continued_at:
                    break
            else:
                raise AssertionError("CLI 清理/重启后 API 长流被截断")
            container.reload()
            assert container.id == first_id and container.status == "running"
        deadline = time.monotonic() + 5
        while runtime._sender_active(row) and time.monotonic() < deadline:
            time.sleep(0.1)
        assert runtime._sender_active(row) == 0
        print("通过：API 长流期间启动养号/抓包及第二次 API；CLI 取消、重启对账、Recorder 故障和修复保留 API 长流与同一容器")
        runtime.maintenance(row["environment_id"], "stop")
        runtime.maintenance(row["environment_id"], "stop")
        row, container = runtime.ensure(account, "9.9.9")
        assert container.id == first_id and row["generation"] > first_generation
        assert container.exec_run(["cat", "/etc/machine-id"]).output == machine
        assert (runtime._root(row) / "home" / ".claude" / ".credentials.json").read_bytes() == original
        assert not container.attrs["HostConfig"]["PortBindings"]
        assert container.attrs["HostConfig"]["Memory"] == 1536 * 1024**2
        assert container.attrs["HostConfig"]["MemorySwap"] == 3584 * 1024**2
        # 续聊仍使用同一账号 HOME、原项目目录和独立 source。
        source = "continue:abcdef111111:0"
        token, _ = runtime.begin_continue(account, {"id": "synthetic-run", "claude_code_version": "9.9.9", "capture_full_http": True},
            "abcdef111111", {"QUOTA_SOURCE": source}, flows / "continue-abcdef111111")
        handle = runtime.job_for_container(token)["handle"]
        execution = client.api.exec_create(container.id, ["setsid", "--wait", "bash", "-c",
            "echo $$ > /run/v3/job-" + handle + ".pid; exec setpriv --reuid=1000 --regid=1000 --init-groups --bounding-set=-all --no-new-privs sh -c 'sleep 120 & wait'"],
            workdir="/workspaces/synthetic-run")["Id"]
        runtime.register_exec(token, execution)
        client.api.exec_start(execution, detach=True)
        time.sleep(0.3)
        runtime.cleanup(token)
        assert not client.api.exec_inspect(execution)["Running"]
        assert json.loads((runtime._root(row) / "runtime" / "context-ack.json").read_text())["QUOTA_SOURCE"] == ""
        with database() as connection:
            connection.execute("INSERT INTO accounts VALUES(2,'synthetic-two',NULL)")
        second = {**account, "id": 2, "name": "synthetic-two"}
        runtime.limit = 2
        second_row = runtime._row(second["name"], 2)
        second_cache = runtime._root(second_row) / "cli" / "9.9.9"
        shutil.copytree(cached, second_cache)
        second_row, second_container = runtime.ensure(second, "9.9.9")
        assert second_row["environment_id"] != row["environment_id"] and second_container.id != first_id
        second_configuration = json.loads((runtime._root(second_row) / "runtime" / "sender.json").read_text())
        second_binding = second_configuration["binding"]
        prepared.update(environment_id=second_row["environment_id"], generation=second_row["generation"], request_id=str(uuid.uuid4()),
            target_url="https://api.anthropic.com/v1/messages", deadline_unix_ms=int(time.time() * 1000) + 30000)
        response = session.post(second_binding["endpoint"] + "/internal/send", headers={"Authorization": "Bearer " + second_binding["secret"], "x-v3-request": base64.b64encode(json.dumps(prepared).encode()).decode()}, data=b'{}', timeout=10)
        assert response.status_code == 502
        hellos = [json.loads(line) for line in Path("/verify/tls.jsonl").read_text().splitlines()]
        assert hellos[0]["peer"] != hellos[-1]["peer"]
        assert second_binding["secret"] != binding["secret"]
        # 网络服务故障必须关闭整个发送环境，不能保留一个失去网络约束的发送器。
        second_container.exec_run(["pkill", "-TERM", "-x", "hev-socks5-tunn"])
        deadline = time.monotonic() + 12
        while time.monotonic() < deadline:
            second_container.reload()
            if second_container.status != "running":
                break
            time.sleep(0.2)
        assert second_container.status != "running"
        runtime.maintenance(row["environment_id"], "rebuild")
        runtime.maintenance(row["environment_id"], "rebuild")
        rebuilt_row, rebuilt = runtime.ensure(account, "9.9.9")
        assert rebuilt.id != first_id and rebuilt_row["environment_id"] == row["environment_id"]
        assert rebuilt.exec_run(["cat", "/etc/machine-id"]).output == machine
        assert (runtime._root(rebuilt_row) / "home" / ".claude" / ".credentials.json").read_bytes() == original
        print("PASS: fixed HOME/container, native TLS ClientHello from account, raw body/429/API evidence, non-root isolation, tmux reattach, reauth cancellation, task capture cleanup, idempotent stop and wake")
        print("PASS: continue process-tree/capture cleanup, two accounts using the same mock proxy remain separate, network fault closes sender")
        print("通过：重复重建空实例后保留环境 ID、machine-id 和 HOME")
        print("真实 OAuth 登录与 TLS 应用响应未执行；CLI 生命周期使用明确的测试替身。")
    except Exception:
        for instance in client.containers.list(all=True, filters={"label": ["vibebench.product=v3", "vibebench.deployment=" + runtime.deployment, "vibebench.role=account"]}):
            print(instance.logs(tail=35).decode(), flush=True)
            if instance.status == "running":
                print(instance.exec_run(["tail", "-20", "/var/log/mitmdump.log"]).output.decode(), flush=True)
        raise
    finally:
        for instance in client.containers.list(all=True, filters={"label": ["vibebench.product=v3", "vibebench.deployment=" + runtime.deployment, "vibebench.role=account"]}):
            instance.remove(force=True)


if __name__ == "__main__":
    verify()
