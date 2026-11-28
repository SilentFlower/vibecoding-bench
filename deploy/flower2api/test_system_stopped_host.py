"""用真实宿主 Unix HTTP、临时数据库和原门禁验证历史环境证据。"""

from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
import json
from pathlib import Path
from shutil import copyfile
import sqlite3
from tempfile import TemporaryDirectory
from threading import Lock, RLock, Thread
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from account_runtime import AccountRuntime
from system_updates import system_updates_router
from system_update_gate import UPDATE_GATE
from uuid import uuid4

import test_system_release as release_fixtures
from system_updater import SystemUpdater, UpdateHTTPHandler, UpdateServer
from system_update_connection import UnixUpdateConnection
from runtime_files import atomic_json
import system_update_stopped_host as observer


class HistoricalHostTests(TestCase):
    """独立宿主读取路径的门禁、角色登记和实际并发边界。"""

    def setUp(self):
        self.area = Path(self.enterContext(TemporaryDirectory()))
        self.data = self.area / "data"
        self.root = self.area / "updater"
        self.host = Mock()
        self.host.root, self.host.data, self.host.gate = self.root, self.data, self.root / "gate"
        self.host.policy = {"deployment": "test"}
        self.host.controls.return_value = {"gateway": {"Config": {"Env": ["V3_LEASE_DIR=/data/leases"]}}}
        self.op, epoch, revision = (str(uuid4()) for _ in range(3))
        self.gate = {
            "schema_version": 1,
            "deployment": "test",
            "operation_id": self.op,
            "epoch": epoch,
            "revision": revision,
            "target_release": "system-ci-42-1",
            "phase": "blocked",
            "created_at": "2026-11-28T00:00:00Z",
        }
        atomic_json(self.host.gate / "admission.json", self.gate)
        atomic_json(self.root / "operations" / self.op / "operation.json", {**self.gate, "phase": "draining"})
        self.engine = SimpleNamespace(
            backend=self.host, root=self.root, state={"active_operation": self.op}, lock=Lock()
        )
        self.engine._operation = lambda op: SystemUpdater._operation(self.engine, op)
        self.env = uuid4().hex
        self.scope = {
            "deployment": "test",
            "operation_id": self.op,
            "epoch": epoch,
            "challenge": uuid4().hex,
            "environment_id": self.env,
            "account_id": 17,
            "generation": 4,
            "profile_name": "historic",
            "draft": None,
            "role_ids": {"cli": "a" * 64, "network": "b" * 64, "sender": "c" * 64},
            "nodes": [{"id": 1, "node_key": "local", "kind": "local", "revision": 1}],
        }
        for item in ("bench", "gateway"):
            (self.data / item).mkdir(parents=True)
        with closing(sqlite3.connect(self.data / "bench/db.sqlite")) as db, db:
            db.executescript("""
                CREATE TABLE account_environments(environment_id,name,state,generation,account_id,container_id,network_container_id,sender_container_id);
                CREATE TABLE accounts(id,name,profile_path);
                CREATE TABLE account_node_assignments(account_id);
                CREATE TABLE node_login_drafts(environment_id,node_id,operation_id,phase,revision,saved_account_id);
                CREATE TABLE cluster_nodes(id,node_key,kind,revision,deleted_at);
                CREATE TABLE node_executions(environment_id,account_id);
                INSERT INTO cluster_nodes VALUES(1,'local','local',1,NULL);
            """)
            db.execute(
                "INSERT INTO account_environments VALUES(?,?,?,?,?,?,?,?)",
                (self.env, "historic", "stopped", 4, 17, *self.scope["role_ids"].values()),
            )
        with closing(sqlite3.connect(self.data / "gateway/gateway.sqlite")) as db, db:
            db.executescript("CREATE TABLE accounts(id INTEGER PRIMARY KEY); INSERT INTO accounts VALUES(41);")
        original = self.data / "bench/environments" / self.env
        (original / "home").mkdir(parents=True)
        (self.data / "bench/profiles/historic").mkdir(parents=True)
        self.binding = original / "runtime/sender/sender.json"
        atomic_json(
            self.binding, {"binding": {"environment_id": self.env, "generation": 4, "release_id": "ci-18-1"}}
        )
        self.pending = False
        self.jobs = 0
        self.lease = {"active": 0, "waiting": 0, "importing": 0, "holders": [], "lease": None}
        self.host.request.side_effect = self.observe
        self.token = uuid4().hex * 2
        self.socket = self.area / "test.sock"
        self.server = UpdateServer(str(self.socket), UpdateHTTPHandler)
        self.server.engine, self.server.token = self.engine, self.token
        self.thread = Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.close_server)

    def close_server(self):
        """回收隔离宿主监听。"""
        self.server.shutdown()
        self.thread.join()
        self.server.server_close()

    def observe(self, service, path, body=None):
        """模拟受信控制进程的实际活动投影。@param service 角色。@param path 路径。@param body 挑战。"""
        if path == observer._ROUTE:
            return {"scope": body, "jobs": self.jobs}
        if path == "/admin/runtime/system-update/status":
            return {**self.gate, "phase": "blocked", "active": 0, "tui_tool_pending": self.pending}
        if path == "/admin/runtime/accounts/41/lease":
            return self.lease
        raise AssertionError(path)

    def call(self, scope, token=None):
        """通过真实 Unix 连接发起测试读取。@param scope 证据范围。@param token 测试令牌。@return HTTP/JSON。"""
        with closing(UnixUpdateConnection(self.socket)) as conn:
            conn.request(
                "POST",
                "/maintenance/stopped-environment",
                body=json.dumps(scope),
                headers={"Authorization": "Bearer " + (token or self.token), "Content-Type": "application/json"},
            )
            response = conn.getresponse()
            return response.status, json.loads(response.read())

    def test_observation_is_readonly_and_independent_of_updater_mutex(self):
        """并发挑战不复用回执，读取不等待宿主部署锁。"""
        before = (self.binding.read_bytes(), (self.host.gate / "admission.json").read_bytes())
        with (
            patch.object(observer, "_image", return_value={"fixture": "signed tests separately"}),
            patch.object(observer, "docker", return_value="local-engine\n"),
            self.engine.lock,
        ):
            with ThreadPoolExecutor(max_workers=4) as pool:
                scopes = [{**self.scope, "challenge": uuid4().hex} for _ in range(4)]
                results = list(pool.map(self.call, scopes))
            for scope, (code, body) in zip(scopes, results):
                self.assertEqual(code, 200)
                self.assertEqual(body["scope"], scope)
                local = body["nodes"]["local"]
                self.assertEqual(
                    (local["jobs"], local["executions"], local["leases"], local["pending_receipts"]), (0, 0, 0, 0)
                )
                self.assertEqual(local["binding"], [self.env, 4])
                self.assertEqual(local["engine_id"], "local-engine")
            self.jobs = 2
            self.assertEqual(self.call(self.scope)[1]["nodes"]["local"]["jobs"], 2)
        self.assertEqual(before, (self.binding.read_bytes(), (self.host.gate / "admission.json").read_bytes()))

    def test_authentication_stale_scope_conflicts_and_pending_receipt(self):
        """错误调用身份、旧操作/epoch、冒称节点和待工具回执都得不到证据。"""
        self.assertEqual(self.call(self.scope, "wrong")[0], 403)
        for field, value in [
            ("operation_id", str(uuid4())),
            ("epoch", str(uuid4())),
            ("profile_name", ".."),
            ("deployment", "other"),
            ("nodes", []),
            ("generation", True),
            ("role_ids", {**self.scope["role_ids"], "sender": "d" * 64}),
        ]:
            with self.subTest(field=field):
                self.assertEqual(self.call({**self.scope, field: value})[0], 400)
        self.pending = True
        self.assertEqual(self.call(self.scope)[0], 400)

    def test_stale_during_read_and_real_persistent_lease(self):
        """采集间门禁变化须作废挑战，持久租约的真实条目保持可见。"""
        leases = self.data / "gateway/leases"
        leases.mkdir()
        (leases / "91.json").write_text("存量归属，无需读取内容")
        with (
            patch.object(observer, "_image", return_value={"fixture": True}),
            patch.object(observer, "docker", return_value="local-engine\n"),
        ):
            self.assertEqual(self.call(self.scope)[0], 400)
            (leases / "91.json").rename(leases / "41.json")
            self.lease.update(holders=[{"owner": "fixture"}], lease={"owner": "fixture"})
            self.assertEqual(self.call(self.scope)[1]["nodes"]["local"]["leases"], 1)
            (leases / "41.json").unlink()
            self.lease.update(holders=[], lease=None)

            def change_gate(service, path, body=None):
                result = self.observe(service, path, body)
                if path == observer._ROUTE:
                    atomic_json(self.host.gate / "admission.json", {**self.gate, "epoch": str(uuid4())})
                return result

            self.host.request.side_effect = change_gate
            self.assertEqual(self.call(self.scope)[0], 400)

    def test_process_activity_reads_real_jobs_while_environment_guard_is_held(self):
        """外层冻结环境时轻量内部路由可读取原作业锁，不递归发送整份快照。"""
        runtime = SimpleNamespace(lock=RLock(), jobs={self.env: {"source": "fixture"}})
        runtime.environment_jobs = lambda env: AccountRuntime.environment_jobs(runtime, env)
        env_guard = Lock()
        runtime.environment_lock = lambda _: env_guard
        app = FastAPI()
        app.include_router(system_updates_router(lambda: runtime))
        body = {key: self.scope[key] for key in ("operation_id", "epoch", "environment_id", "challenge")}
        with (
            TestClient(app) as client,
            env_guard,
            patch("system_updates.update_token", return_value=self.token),
            patch.object(UPDATE_GATE, "state", return_value={**self.gate, "active": 0}),
        ):
            response = client.post(observer._ROUTE, json=body, headers={"x-v3-update-token": self.token})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json(), {"scope": body, "jobs": 1})
            self.assertEqual(client.post(observer._ROUTE, json=body).status_code, 403)
            self.assertEqual(
                client.post(
                    observer._ROUTE,
                    json={**body, "epoch": str(uuid4())},
                    headers={"x-v3-update-token": self.token},
                ).status_code,
                409,
            )

    def test_signed_original_selection_and_damaged_signature(self):
        """真实临时 Ed25519 签名、固定公钥和镜像摘要共同决定原账号来源。"""
        signed = release_fixtures.SystemReleaseTests()
        self.addCleanup(signed.doCleanups)
        signed.setUp()
        account = signed.release["account"]
        dest = self.root / "releases" / signed.release["release"]
        dest.mkdir(parents=True)
        for name in ("system-release.json", "system-release.sig"):
            copyfile(signed.output / name, dest / name)
        self.host.policy["public_key"] = signed.public
        binding = {"environment_id": self.env, "generation": 4, "release_id": account["release"]}
        atomic_json(self.binding, {"binding": binding})
        labels = {
            "vibebench.role": "account",
            "vibebench.product": "v3",
            "vibebench.release": account["release"],
            "vibebench.parent-revision": account["revision"],
        }
        info = {
            "Id": account["registry_digest"],
            "Config": {"Labels": labels},
            "Os": "linux",
            "Architecture": "amd64",
        }

        def cli(*args, timeout):
            return json.dumps([info]) if args[0] == "image" else "engine"

        with patch.object(observer, "docker", side_effect=cli):
            response, body = self.call(self.scope)
            self.assertEqual(response, 200)
            self.assertEqual(body["image"]["engine_digest"], "registry_digest")
            self.assertEqual(body["image"]["system_release"], signed.release["release"])
            self.assertEqual(body["image"]["config_digest"], account["config_digest"])
            raw = (dest / "system-release.sig").read_bytes()
            (dest / "system-release.sig").write_bytes(bytes([raw[0] ^ 1]) + raw[1:])
            self.assertEqual(self.call(self.scope)[0], 400)
