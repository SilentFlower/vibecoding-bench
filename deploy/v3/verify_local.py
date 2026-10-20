"""账号容器隔离演练：空数据、无公网网络、合成 CLI 和 mock 上游。

用法见 README；本脚本不执行真实登录，不加载现有账号。
"""
import argparse
import base64
import copy
import json
import os
import re
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
from unittest.mock import patch

import docker
import requests
import main as orchestrator
from account_runtime import AccountRuntime, atomic_json, derive_v3_fingerprint
from account_isolation import role_container
from verify_isolation import memory_peaks, verify_roles, verify_route_failure
from verify_system_profile import verify_system_information
from verify_followups import verify_followup_delivery
from verify_quota_completion import verify_running_quota_completion
from verify_run_windows import verify_physical_observation, verify_run_window_completion



def write_sender(path: Path, value: dict) -> None:
    """按正式权限原子发布合成 sender 配置。@param path 私有配置。@param value 配置。@return None。"""
    atomic_json(path, value, 0o640)
    os.chown(path, 0, 1001)


def verify_legacy_transition(runtime, row: dict, account: dict, client) -> None:
    """在合成资料上执行旧镜像→新布局→旧镜像，保持当前凭据和身份。

    :param runtime: 隔离测试运行时。
    :param row: 已停止、无任务的固定环境。
    :param account: 未绑定的合成账号。
    :param client: 当前 Docker 客户端。
    :return: None；未指定旧镜像时不执行。
    """
    control, image = os.environ.get('VERIFY_LEGACY_CONTROL_IMAGE'), os.environ.get('VERIFY_LEGACY_ACCOUNT_IMAGE')
    if not control or not image:
        return
    root = runtime._root(row)
    files = [root / 'home/.claude.json', root / 'home/.claude/.credentials.json']
    before = [path.read_bytes() for path in files]
    fingerprint = row['fingerprint_json']
    machine = json.loads(fingerprint)['machine_id']
    (Path('/verify') / 'legacy-account.json').write_text(json.dumps(account))
    old_release = client.images.get(image).attrs['Config']['Labels']['vibebench.release']

    def old_layout() -> None:
        """用旧镜像的实际运行时重建单容器，不使用新代码模拟旧行为。@return None。"""
        runtime._stop_environment(row, remove=True)
        # 对应停机离线回退 SOP：只改运行布局登记，绝不恢复旧 DB 或旧凭据。
        runtime._update(row, isolation_version=0, state='stopped')
        environment = {key: os.environ[key] for key in ('V3_DEPLOYMENT_ID','V3_NETWORK','V3_ACCOUNT_MEMORY','V3_ACCOUNT_SWAP','VERIFY_HOST_ROOT')}
        environment.update(V3_ACCOUNT_IMAGE=image, V3_RELEASE=old_release, PYTHONPATH='/app', V3_MAX_ACTIVE_ACCOUNTS=str(runtime.limit))
        output = client.containers.run(control, ['/fixtures/legacy_runtime.py'], entrypoint='python', remove=True,
            network=runtime.network, labels={'vibebench.product':'v3','vibebench.deployment':runtime.deployment,'vibebench.role':'orchestrator'},
            environment=environment, volumes={os.environ['VERIFY_HOST_ROOT']:{'bind':'/verify','mode':'rw'},
                str(Path(os.environ['VERIFY_SOURCE_ROOT']) / 'deploy/v3/fixtures'):{'bind':'/fixtures','mode':'ro'},
                '/var/run/docker.sock':{'bind':'/var/run/docker.sock','mode':'rw'}})
        observed = json.loads(output.decode().strip().splitlines()[-1])
        assert observed == {'environment_id':row['environment_id'],'machine_id':machine}
        assert all(path.read_bytes() == value for path,value in zip(files,before))
        row.update(runtime._row(account['name'], account['id']))

    old_layout()
    runtime.maintenance(row['environment_id'], 'rebuild')
    upgraded, _ = runtime.ensure(account, '9.9.9')
    row.update(upgraded)
    assert row['isolation_version'] == 2 and row['fingerprint_json'] == fingerprint
    assert all(row[name] for name in ('container_id','network_container_id','sender_container_id'))
    assert all(path.read_bytes() == value for path,value in zip(files,before))
    assert (root / 'runtime/isolation-upgrade/before.sqlite').is_file()
    runtime.maintenance(row['environment_id'], 'stop')
    old_layout()
    print('通过：实际旧镜像单容器→三角色→停机离线回退旧镜像，身份/HOME/最新凭据均保留', flush=True)


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
            transcript = runtime.run_artifact_path(job["run_id"], "transcript.log")
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
        write_sender(configuration_path, configuration)
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
        write_sender(configuration_path, original)


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
        connection.executemany("INSERT INTO runs VALUES(?)", [("synthetic-run",), ("synthetic-warmup-native",)])
    client = docker.from_env()
    account = {"id": 1, "name": "synthetic", "upstream_proxy_scheme": "socks5", "upstream_socks5_host": args.proxy_ip, "upstream_socks5_port": 1080}
    profile_sequence = iter((("synthetic-fixed", "a" * 32, "02:00:00:00:00:71"),
        ("synthetic-two", "b" * 32, "02:00:00:00:00:72")))

    def fingerprint(timezone: str | None) -> dict:
        """返回两个彼此独立的合成账号画像，不读取真实环境。"""
        hostname, machine_id, mac = next(profile_sequence)
        return {**derive_v3_fingerprint(timezone), "hostname": hostname, "machine_id": machine_id,
            "mac": mac, "mem": "4g"}

    runtime = AccountRuntime(client, root, Path(os.environ["VERIFY_HOST_ROOT"]) / "data", database, fingerprint, None)
    row = runtime._row(account["name"], account["id"])
    cached = runtime._root(row) / "cli" / "9.9.9"
    binary = cached / "node_modules" / ".bin" / "claude"
    binary.parent.mkdir(parents=True)
    shutil.copy2("/fixtures/mock_cli.py", binary)
    binary.chmod(0o755)
    (cached / ".ready").touch()
    evidence_root = runtime._root(row) / 'flows/api'
    evidence_root.mkdir(parents=True)
    legacy_evidence = b'{"source":"synthetic-old-layout"}\n'
    for name in ('observations.jsonl', 'observations.jsonl.previous'):
        (evidence_root / name).write_bytes(legacy_evidence)
        (evidence_root / name).chmod(0o600)
    container = None
    try:
        row, container = runtime.ensure(account, "9.9.9")
        isolation = verify_roles(container, role_container(runtime, row, "sender"), runtime._network_container(row),
            json.loads(row['fingerprint_json']))
        system_profile = json.loads(row['fingerprint_json'])['system_profile']
        computer_profile = json.loads(row['fingerprint_json'])['computer_profile']
        system_facts = verify_system_information(container, runtime._network_container(row),
            role_container(runtime, row, 'sender'), json.loads(row['fingerprint_json']))
        print('通过：真实系统画像、文件 API、Node/子进程及直接 syscall/CPUID 边界：' + json.dumps(system_facts), flush=True)
        print("通过：真实 Docker 三角色权限/只读根/秘密隔离/内置 DNS 拒绝/本地构建/非 root 收口：" + json.dumps(isolation), flush=True)
        first_id, first_generation = container.id, row["generation"]
        check = container.exec_run(runtime.cli_command(["sh", "-c", "test ! -r /run/v3/sender.json && test ! -r /ca/mitmproxy-ca.pem && grep '^CapEff:' /proc/self/status"])); assert check.exit_code == 0 and b"0000000000000000" in check.output
        private_files = ["/sidecar", *("/usr/local/bin/v3-" + name for name in ("account-init", "network-context", "cli-version", "passthrough"))]
        for path in private_files:
            assert container.exec_run(runtime.cli_command(["test", "-r", path])).exit_code != 0, path
        assert container.exec_run(runtime.cli_command(["test", "-x", "/usr/local/bin/v3-cli-quota"])).exit_code == 0
        machine = container.exec_run(["cat", "/etc/machine-id"]).output
        configuration_path = runtime._sender_config(row)
        configuration = json.loads(configuration_path.read_text())
        configuration["allowed_origin"] = "http://api.anthropic.com:8081"
        configuration["quota_identity"] = "synthetic-quota"
        write_sender(configuration_path, configuration)
        binding = configuration["binding"]
        prepared = {"account_id": 0, "environment_id": row["environment_id"], "generation": row["generation"], "request_id": str(uuid.uuid4()), "deadline_unix_ms": int(time.time() * 1000) + 30000,
            "method": "POST", "target_url": "http://api.anthropic.com:8081/v1/messages", "headers": [["Content-Type", "application/json"]], "preserve_header_casing": True}
        session = requests.Session(); session.trust_env = False
        response = session.post(binding["endpoint"] + "/internal/send", headers={"Authorization": "Bearer " + binding["secret"], "x-v3-request": base64.b64encode(json.dumps(prepared).encode()).decode()}, data=b'{ "synthetic": true }', timeout=10)
        assert response.status_code == 429 and response.content == b'{ "synthetic": true }'
        assert (evidence_root / 'observations.jsonl').read_bytes().startswith(legacy_evidence)
        assert (evidence_root / 'observations.jsonl.previous').read_bytes() == legacy_evidence
        assert all((evidence_root / name).stat().st_uid == 1001
            for name in ('observations.jsonl', 'observations.jsonl.previous'))
        evidence = json.loads((runtime._root(row) / "flows" / "api" / "observations.jsonl").read_text().splitlines()[-1])
        assert evidence["origin"] == "api" and evidence["identity"] == "synthetic-quota"
        configuration["allowed_origin"] = "https://api.anthropic.com"
        write_sender(configuration_path, configuration)
        prepared.update(request_id=str(uuid.uuid4()), target_url="https://api.anthropic.com/v1/messages")
        response = session.post(binding["endpoint"] + "/internal/send", headers={"Authorization": "Bearer " + binding["secret"], "x-v3-request": base64.b64encode(json.dumps(prepared).encode()).decode()}, data=b'{}', timeout=10)
        assert response.status_code == 502
        hello = json.loads(Path("/verify/tls.jsonl").read_text().splitlines()[-1])
        assert hello["record_type"] == 22
        container.reload()
        assert hello["peer"] == runtime._network_container(row).attrs["NetworkSettings"]["Networks"][runtime.network]["IPAddress"]
        verify_gateway_binding(configuration_path, hello["peer"])
        row, container, profile, home = runtime.begin_login("abcdef123456", account, "9.9.9", False)
        time.sleep(0.5)
        expected_environment = {"TZ": "America/Los_Angeles", "LANG": "en_US.UTF-8", "LC_ALL": "en_US.UTF-8"}
        assert json.loads((runtime._root(row) / "home/.synthetic-login-environment.json").read_text()) == expected_environment
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
        verify_physical_observation(runtime, row)
        if os.environ.get("VERIFY_PROJECT_SCHEDULING_ONLY") == "1" or os.environ.get("VERIFY_PROJECT_CATALOG_ONLY") == "1":
            from verify_project_scheduling import verify_project_scheduling
            verify_project_scheduling(runtime, client, account, row,
                catalog_only=os.environ.get("VERIFY_PROJECT_CATALOG_ONLY") == "1")
            return
        if os.environ.get("VERIFY_PROJECT_ITERATIONS_ONLY") == "1":
            from verify_project_execution import verify_project_execution
            verify_project_execution(runtime, client, account, row)
            return
        if os.environ.get("VERIFY_RUN_WINDOWS_ONLY") == "1":
            verify_run_window_completion(runtime, client, account, row)
            return
        if os.environ.get("VERIFY_QUOTA_COMPLETION_ONLY") == "1":
            verify_running_quota_completion(runtime, client, account, row, database)
            return
        if os.environ.get("VERIFY_FOLLOWUPS_ONLY") == "1":
            verify_followup_delivery(runtime, client, account, row, database)
            return
        environment = {"CLAUDE_CODE_VERSION": "9.9.9", "TASK_PROMPT": "Synthetic only", "RUN_ID": "synthetic-run", "TIMEOUT_SEC": "120", "TIMEOUT_WRAPUP_SEC": "0",
            "SYNTHETIC_TLS_PROBE": "1", "TZ": "Asia/Tokyo", "LANG": "ja_JP.UTF-8", "LC_ALL": "ja_JP.UTF-8"}
        tls_before = len(Path("/verify/tls.jsonl").read_text().splitlines())
        token, _ = runtime.start_run(account, {"id": 1, "capture_full_http": False}, "synthetic-run", environment,
            {"QUOTA_SOURCE": "run:synthetic-run:0", "QUOTA_IDENTITY": "synthetic-quota"})
        wait_cli_started(runtime, client, token)
        normal_context = runtime.job_for_container(token)["context"]
        workspace = runtime._root(row) / "workspaces" / "synthetic-run"
        invocation = json.loads((workspace / ".synthetic-invocation.json").read_text())
        assert invocation["cwd"].startswith("/home/node/projects/project-") and "synthetic-run" not in invocation["cwd"]
        assert invocation["network_mode"] == "passthrough" and invocation["tls_environment"] == []
        assert invocation["environment"] == expected_environment
        assert "LANG=en_US.UTF-8" in invocation["locale"] and "PDT" in invocation["date"]
        assert not re.search(r"[\u3400-\u9fff]", invocation["date"] + invocation["ls"])
        visible_projects = container.exec_run(["find", "/home/node/projects", "-mindepth", "1", "-maxdepth", "1", "-printf", "%f\n"])
        assert visible_projects.exit_code == 0
        assert all(re.fullmatch(rb"project-[0-9a-f]{12}", name) for name in visible_projects.output.splitlines())
        assert not any((workspace / name).exists() for name in (
            ".bench-status.json", ".bench-transcript.log", ".bench-session-baseline.json",
            ".cc2api-oauth-refresh-request.json", ".cc2api-oauth-refresh-result.json", ".claude-home",
        ))
        assert not (workspace / ".claude" / "settings.local.json").exists()
        acknowledgement = json.loads((runtime._network_runtime(row) / "context-ack.json").read_text())
        assert acknowledgement["NETWORK_INSPECTION_MODE"] == "passthrough" and acknowledgement["process"] == "passthrough"
        tls_after = [json.loads(line) for line in Path("/verify/tls.jsonl").read_text().splitlines()]
        assert len(tls_after) == tls_before + 1
        assert tls_after[-1]["length"] == 8 and tls_after[-1]["payload_prefix"] == "1603030003010203"
        normal_flow = runtime._root(row) / "flows" / Path(normal_context["STATS_FILE"]).relative_to("/flows").parent
        assert not any((normal_flow / name).exists() for name in ("stats.jsonl", "http_capture.jsonl", "capture.flow"))
        settings_path = runtime._root(row) / "home/.claude/settings.json"
        installed = json.loads(settings_path.read_text())["statusLine"]
        assert "v3-cli-quota" in installed["command"], "driver 清除了本次临时采集配置"
        writable = container.exec_run(["python3", "-c",
            "import json,pathlib; settings=json.loads(pathlib.Path('/home/node/.claude/settings.json').read_text());"
            "import shlex; config=json.loads(pathlib.Path(shlex.split(settings['statusLine']['command'])[-1]).read_text());"
            "pathlib.Path(config['output']).write_text('')"])
        assert writable.exit_code == 0, "CLI 无法穿过当前额度输出目录"
        runtime.cleanup(token)
        assert "statusLine" not in json.loads(settings_path.read_text()), "退出后遗留本代采集配置"
        assert not runtime.jobs
        print("通过：普通任务使用原始 TLS 透传、无自定义 CA 环境，CLI cwd 不暴露内部 run ID 或控制文件")
        # 只信任测试服务自己的证书；它与 account MITM CA 无关，不进入生产配置。
        (runtime._root(row) / "home" / "native-usage.crt").write_bytes(Path("/verify/native-usage.crt").read_bytes())
        Path("/verify/usage-tls.enabled").touch()
        before_listener = (runtime._network_runtime(row) / "network.pid").read_text()
        probe = object.__new__(orchestrator.Runner)
        probe.client = client
        original_environment = orchestrator._claude_exec_env

        def test_environment(use_sidecar, extra=None):
            """只追加本地测试服务器信任，仍断言正式路径未注入 MITM CA。@return 执行环境。"""
            assert use_sidecar is False
            value = original_environment(False, extra)
            assert not any(key in value for key in ("NODE_EXTRA_CA_CERTS", "SSL_CERT_FILE", "CURL_CA_BUNDLE"))
            value["NODE_EXTRA_CA_CERTS"] = "/home/node/native-usage.crt"
            return value

        try:
            with patch.object(orchestrator, "account_runtime", runtime), \
                    patch.object(orchestrator, "PROFILES_DIR", root / "profiles"), \
                    patch.object(orchestrator, "_claude_exec_env", side_effect=test_environment):
                usage = probe.query_quota(account)
            assert usage["ok"] and usage["five_hour"]["utilization"] == 12
            assert usage["seven_day"]["utilization"] == 23
            assert before_listener == (runtime._network_runtime(row) / "network.pid").read_text()
            assert not runtime.jobs
            observation = json.loads(Path("/verify/usage-calls.jsonl").read_text().splitlines()[-1])
            assert observation == {"path": "/api/oauth/usage", "tls": True}
            print("通过：真实账号容器通过原生 TLS 查询 usage JSON，监听进程不重启且不使用 MITM CA")
        finally:
            Path("/verify/usage-tls.enabled").unlink(missing_ok=True)
        warmup_environment = dict(environment, RUN_ID="synthetic-warmup-native")
        token, _ = runtime.start_run(account, {"id": 1, "warmup": True, "capture_full_http": False},
            "synthetic-warmup-native", warmup_environment,
            {"QUOTA_SOURCE": "run:synthetic-warmup-native:0", "QUOTA_WARMUP": "1",
                "QUOTA_SAMPLE_REQUIRED": "0"})
        wait_cli_started(runtime, client, token)
        warmup_invocation = json.loads((runtime._root(row) / "workspaces" / "synthetic-warmup-native" / ".synthetic-invocation.json").read_text())
        assert warmup_invocation["network_mode"] == "passthrough" and warmup_invocation["tls_environment"] == []
        assert warmup_invocation["environment"] == expected_environment
        runtime.cleanup(token)
        print("通过：已有可信额度的正常养号保持 passthrough，不加载 Recorder CA")
        # 用同一 run 的不同 source 验证额度恢复，不能用两个独立 run 绕过目录换代。
        flows = root / "flows" / account["name"] / "1" / "synthetic-run"
        target = flows.resolve()
        old_flow = runtime.execution_flows(account, "run:synthetic-run:0", flows)
        (old_flow / "stats.jsonl").write_text('{"flow_id":"synthetic-evidence","usage":{"input_tokens":1}}\n')
        evidence = {path: path.read_bytes() for path in old_flow.iterdir() if path.is_file()}
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
        assert invocation["cwd"].startswith("/home/node/projects/project-") and "synthetic-run" not in invocation["cwd"]
        assert invocation["home"] == "/home/node" and invocation["network_mode"] == "capture"
        assert invocation["environment"] == expected_environment
        assert invocation["tls_environment"] == ["CURL_CA_BUNDLE", "GIT_SSL_CAINFO", "NODE_EXTRA_CA_CERTS", "REQUESTS_CA_BUNDLE", "SSL_CERT_FILE"]
        runtime.cleanup(token)
        assert all(path.read_bytes() == data for path, data in evidence.items())
        assert (resumed_flow / "capture.flow").exists()
        print("通过：同 run 第二代 CLI 在原 cwd/HOME 使用原 session 恢复，证据入口不变、旧统计/原生 flow 保留，新 flow 独立")
        print("通过：透传/抓包/CLI 构建后的角色内存峰值：" + json.dumps(memory_peaks(container, role_container(runtime, row, "sender"), runtime._network_container(row))), flush=True)
        configuration["allowed_origin"] = "http://api.anthropic.com:8081"
        write_sender(configuration_path, configuration)
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
            token, _ = runtime.start_run(account, {"id": 1, "warmup": True, "capture_full_http": False}, "synthetic-parallel",
                dict(environment, RUN_ID="synthetic-parallel", QUOTA_SOURCE="run:synthetic-parallel"),
                {"QUOTA_SOURCE": "run:synthetic-parallel", "QUOTA_IDENTITY": "synthetic-quota",
                    "QUOTA_WARMUP": "1", "QUOTA_SAMPLE_REQUIRED": "1"})
            execution = wait_cli_started(runtime, client, token)
            quota_context = json.loads((runtime._network_runtime(row) / "context-ack.json").read_text())
            assert quota_context["NETWORK_INSPECTION_MODE"] == "passthrough" and quota_context["process"] == "passthrough"
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
            token, _ = runtime.start_run(account, {"id": 1, "capture_full_http": False}, "synthetic-restart",
                dict(environment, RUN_ID="synthetic-restart", QUOTA_SOURCE="run:synthetic-restart"),
                {"QUOTA_SOURCE": "run:synthetic-restart", "QUOTA_IDENTITY": "synthetic-quota"})
            execution = wait_cli_started(runtime, client, token)
            assert token != old_token
            runtime.cleanup(old_token)
            assert client.api.exec_inspect(execution)["Running"]
            runtime.jobs.clear()
            runtime.reconcile()
            assert "statusLine" not in json.loads(settings_path.read_text()), "重启对账未恢复状态栏"
            assert not client.api.exec_inspect(execution)["Running"]
            assert runtime._row(account["name"], account["id"])["state"] == "ready"
            assert runtime._sender_active(row) == 1
            listener_pid = int((runtime._network_runtime(row) / "network.pid").read_text())
            runtime._network_container(row).exec_run(["kill", "-TERM", str(listener_pid)])
            unhealthy = runtime._network_runtime(row) / "cli-unhealthy"
            deadline = time.monotonic() + 5
            while not unhealthy.exists() and time.monotonic() < deadline:
                time.sleep(0.1)
            assert unhealthy.exists(), "CLI 网络监听退出应隔离下一作业"
            assert runtime._sender_active(row) == 1, "CLI 网络监听故障不能停止独立 API"
            try:
                runtime.claim(row, account, "run:recorder-unhealthy")
            except ValueError:
                pass
            else:
                raise AssertionError("CLI 网络监听不健康时不能开始下一 CLI")
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
        assert container.attrs["HostConfig"]["Memory"] == 1152 * 1024**2
        assert container.attrs["HostConfig"]["MemorySwap"] == 3200 * 1024**2
        # 续聊仍使用同一账号 HOME、原项目目录和独立 source。
        source = "continue:abcdef111111:0"
        token, _ = runtime.begin_continue(account, {"id": "synthetic-run", "claude_code_version": "9.9.9", "capture_full_http": True},
            "abcdef111111", {"QUOTA_SOURCE": source}, flows / "continue-abcdef111111")
        continuation_job = runtime.job_for_container(token)
        handle = continuation_job["handle"]
        execution = client.api.exec_create(container.id, ["setsid", "--wait", "bash", "-c",
            "echo $$ > /run/v3/jobs/" + handle + "/group.pid; exec sh -c 'sleep 120 & wait'"],
            workdir=continuation_job["cwd"])["Id"]
        runtime.register_exec(token, execution)
        client.api.exec_start(execution, detach=True)
        time.sleep(0.3)
        runtime.cleanup(token)
        assert not client.api.exec_inspect(execution)["Running"]
        acknowledgement = json.loads((runtime._network_runtime(row) / "context-ack.json").read_text())
        assert acknowledgement["QUOTA_SOURCE"] == "" and acknowledgement["NETWORK_INSPECTION_MODE"] == "passthrough"
        with database() as connection:
            connection.execute("INSERT INTO accounts VALUES(2,'synthetic-two',NULL)")
        second = {**account, "id": 2, "name": "synthetic-two", "upstream_proxy_scheme": "http", "upstream_socks5_port": 1081}
        runtime.limit = 2
        second_row = runtime._row(second["name"], 2)
        second_cache = runtime._root(second_row) / "cli" / "9.9.9"
        shutil.copytree(cached, second_cache)
        second_row, second_container = runtime.ensure(second, "9.9.9")
        assert second_row["environment_id"] != row["environment_id"] and second_container.id != first_id
        second_profile = root / "profiles" / second["name"]
        atomic_json(second_profile / ".credentials.json", {"claudeAiOauth": {
            "accessToken": "synthetic-http-access", "refreshToken": "synthetic-http-refresh",
            "expiresAt": int(time.time() * 1000) + 3600000}})
        runtime.sync_credentials(second_row, second)
        with database() as connection:
            connection.execute("INSERT INTO runs(id) VALUES('synthetic-http')")
        tls_before = len(Path("/verify/tls.jsonl").read_text().splitlines())
        http_environment = dict(environment, RUN_ID="synthetic-http")
        http_token, _ = runtime.start_run(second, {"id": 1, "capture_full_http": False}, "synthetic-http", http_environment, {})
        wait_cli_started(runtime, client, http_token)
        http_invocation = json.loads((runtime._root(second_row) / "workspaces" / "synthetic-http" / ".synthetic-invocation.json").read_text())
        assert http_invocation["network_mode"] == "passthrough" and http_invocation["tls_environment"] == []
        tls_after = [json.loads(line) for line in Path("/verify/tls.jsonl").read_text().splitlines()]
        assert len(tls_after) == tls_before + 1
        assert tls_after[-1]["length"] == 8 and tls_after[-1]["payload_prefix"] == "1603030003010203"
        runtime.cleanup(http_token)
        print("通过：普通任务经 SOCKS5 与 HTTP CONNECT 上游均保持合成 TLS 字节不变")
        gateway = client.networks.get(runtime.network).attrs['IPAM']['Config'][0]['Gateway']
        print("通过：默认路由回退桥网仍由账号过滤器丢弃直连包：" + json.dumps(verify_route_failure(second_container, runtime._network_container(second_row), gateway)), flush=True)
        second_configuration = json.loads((runtime._sender_config(second_row)).read_text())
        second_binding = second_configuration["binding"]
        prepared.update(environment_id=second_row["environment_id"], generation=second_row["generation"], request_id=str(uuid.uuid4()),
            target_url="https://api.anthropic.com/v1/messages", deadline_unix_ms=int(time.time() * 1000) + 30000)
        response = session.post(second_binding["endpoint"] + "/internal/send", headers={"Authorization": "Bearer " + second_binding["secret"], "x-v3-request": base64.b64encode(json.dumps(prepared).encode()).decode()}, data=b'{}', timeout=10)
        assert response.status_code == 502
        hellos = [json.loads(line) for line in Path("/verify/tls.jsonl").read_text().splitlines()]
        assert hellos[0]["peer"] != hellos[-1]["peer"]
        assert second_binding["secret"] != binding["secret"]
        # 网络服务故障必须关闭整个发送环境，不能保留一个失去网络约束的发送器。
        runtime._network_container(second_row).exec_run(["pkill", "-TERM", "-x", "hev-socks5-tunn"])
        deadline = time.monotonic() + 12
        while time.monotonic() < deadline:
            network = runtime._network_container(second_row)
            network.reload()
            if network.status != "running":
                break
            time.sleep(0.2)
        assert network.status != "running"
        try:
            runtime.ensure(second)
        except Exception:
            pass
        else:
            raise AssertionError("公共网络退出后不能继续接单")
        runtime.maintenance(row["environment_id"], "rebuild")
        runtime.maintenance(row["environment_id"], "rebuild")
        rebuilt_row, rebuilt = runtime.ensure(account, "9.9.9")
        assert json.loads(rebuilt_row['fingerprint_json'])['system_profile'] == system_profile
        assert json.loads(rebuilt_row['fingerprint_json'])['computer_profile'] == computer_profile
        assert rebuilt.id != first_id and rebuilt_row["environment_id"] == row["environment_id"]
        assert rebuilt.exec_run(["cat", "/etc/machine-id"]).output == machine
        assert (runtime._root(rebuilt_row) / "home" / ".claude" / ".credentials.json").read_bytes() == original
        runtime.maintenance(rebuilt_row['environment_id'], 'stop')
        verify_followup_delivery(runtime, client, account, rebuilt_row, database)
        verify_legacy_transition(runtime, rebuilt_row, account, client)
        print("PASS: fixed HOME/container, native TLS ClientHello from account, raw body/429/API evidence, non-root isolation, tmux reattach, reauth cancellation, task capture cleanup, idempotent stop and wake")
        print("PASS: continue process-tree/capture cleanup, two accounts using the same mock proxy remain separate, network fault closes sender")
        print("通过：重复重建空实例后保留环境 ID、machine-id 和 HOME")
        print("真实 OAuth 和公网请求未执行；本地 usage 使用真实 TLS/JSON，CLI 生命周期使用测试替身。")
    except Exception:
        for instance in client.containers.list(all=True, filters={"label": ["vibebench.product=v3", "vibebench.deployment=" + runtime.deployment]}):
            if instance.labels.get('vibebench.role') not in ('account-network','account-sender'):
                continue
            print(instance.logs(tail=35).decode(), flush=True)
            if instance.status == "running" and instance.labels.get('vibebench.role')=='account-network':
                print(instance.exec_run(["tail", "-20", "/var/log/mitmdump.log"]).output.decode(), flush=True)
        raise
    finally:
        for instance in client.containers.list(all=True, filters={"label": ["vibebench.product=v3", "vibebench.deployment=" + runtime.deployment]}):
            if instance.labels.get('vibebench.role') in ('account', 'account-network', 'account-sender'):
                instance.remove(force=True)


if __name__ == "__main__":
    verify()
