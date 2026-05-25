"""
vibecoding-100 bench · Orchestrator

职责：
  1. 账号 / 题库 / 任务 / 运行 的 CRUD（SQLite 持久化）
  2. 调度：每账号信号量 = 2，超出排队；任务指定账号派发
  3. 起 sidecar（透明代理 + MITM）→ 起 worker（claude code）→ 等结果 → 清理
  4. 静态托管 WebUI / SSE 推送状态
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import os
import re
import secrets
import shutil
import sqlite3
import threading
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

import docker
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse
from starlette.websockets import WebSocketState


# ============== 配置 ==============
# 容器内路径
BENCH_DATA = Path(os.environ.get("BENCH_DATA", "/data"))
DB_PATH = BENCH_DATA / "db.sqlite"
PROFILES_DIR = BENCH_DATA / "profiles"
FLOWS_DIR = BENCH_DATA / "flows"
WORKSPACES_DIR = BENCH_DATA / "workspaces"
CA_DIR = BENCH_DATA / "ca"
TOPICS_FILE = Path(os.environ.get("TOPICS_FILE", "/repo/topics.md"))
WEBUI_DIR = Path(os.environ.get("WEBUI_DIR", "/webui"))

# 宿主机路径（用于让 docker daemon 给 sibling 容器挂载 volume；与容器内路径可能不同）
HOST_BENCH_DATA = Path(os.environ.get("HOST_BENCH_DATA", str(BENCH_DATA)))

WORKER_IMAGE = os.environ.get("WORKER_IMAGE", "vibebench-worker:latest")
SIDECAR_IMAGE = os.environ.get("SIDECAR_IMAGE", "vibebench-sidecar:latest")
PER_ACCOUNT_CONCURRENCY = int(os.environ.get("PER_ACCOUNT_CONCURRENCY", "2"))
SIDECAR_BOOT_WAIT = float(os.environ.get("SIDECAR_BOOT_WAIT", "4"))

# HTTP Basic Auth(可选):两者都填才启用,任一为空则跳过(向下兼容本地开发)
# WebSocket 路由由 sid(uuid4 12 hex ≈ 48 位熵)间接保护:sid 仅由已通过
# 鉴权的 POST /login/start 生成,直接访问 WS 拿不到合法 sid
WEBUI_USER = os.environ.get("WEBUI_USER", "")
WEBUI_PASS = os.environ.get("WEBUI_PASS", "")
_AUTH_ENABLED = bool(WEBUI_USER and WEBUI_PASS)


# ============== DB ==============
_SCHEMA = """
CREATE TABLE IF NOT EXISTS accounts (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT UNIQUE NOT NULL,
  profile_path TEXT NOT NULL,
  upstream_socks5_host TEXT,
  upstream_socks5_port INTEGER,
  upstream_socks5_user TEXT,
  upstream_socks5_pass TEXT,
  enabled INTEGER DEFAULT 1,
  created_at REAL DEFAULT (julianday('now'))
);

CREATE TABLE IF NOT EXISTS tasks (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  topic_no INTEGER NOT NULL,
  title TEXT NOT NULL,
  prompt TEXT NOT NULL,
  account_id INTEGER NOT NULL,
  timeout_sec INTEGER DEFAULT 1800,
  repeat_n INTEGER DEFAULT 1,
  created_at REAL DEFAULT (julianday('now')),
  FOREIGN KEY(account_id) REFERENCES accounts(id)
);

CREATE TABLE IF NOT EXISTS runs (
  id TEXT PRIMARY KEY,
  task_id INTEGER NOT NULL,
  account_id INTEGER NOT NULL,
  status TEXT NOT NULL DEFAULT 'queued',
  exit_code INTEGER,
  worker_container TEXT,
  sidecar_container TEXT,
  workspace_dir TEXT,
  flows_dir TEXT,
  started_at REAL,
  ended_at REAL,
  error TEXT,
  created_at REAL DEFAULT (julianday('now'))
);
CREATE INDEX IF NOT EXISTS idx_runs_status  ON runs(status);
CREATE INDEX IF NOT EXISTS idx_runs_account ON runs(account_id);
CREATE INDEX IF NOT EXISTS idx_runs_task    ON runs(task_id);
"""

_db_lock = threading.Lock()


def get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = get_db()
    try:
        with conn:
            conn.executescript(_SCHEMA)
    finally:
        conn.close()


# ============== Topics（从 README.md 解析 100 题）==============
_CAT_RE = re.compile(r"^##\s+[一二三四五六七八九十]+、(.+?)（")
_ITEM_RE = re.compile(r"^-\s+\[[ x]\]\s+(\d+)\.\s+\*\*(.+?)\*\*[:：]?\s*(.*)$")


def load_topics() -> list[dict]:
    """从题库 markdown 解析题库列表"""
    if not TOPICS_FILE.exists():
        return []
    topics: list[dict] = []
    current_category: Optional[str] = None
    for line in TOPICS_FILE.read_text(encoding="utf-8").splitlines():
        cm = _CAT_RE.match(line)
        if cm:
            current_category = cm.group(1).strip()
            continue
        im = _ITEM_RE.match(line)
        if im:
            no, title, desc = im.groups()
            topics.append({
                "no": int(no),
                "category": current_category or "",
                "title": title.strip(),
                "description": desc.strip(),
            })
    return topics


# ============== 账号指纹派生 ==============
# 让 Anthropic 端遥测看到的设备画像满足:同账号跨 run 一致 / 跨账号不同。
# 派生纯函数 stateless,同名输入必出同结果;输入由 _ACC_NAME_RE 收紧字符集
# 后再传入,所以这里不再二次校验。
#
# 候选池规模(锁定):TZ 10 × LANG 5 = 50 组合,足够覆盖 <50 账号场景。
# 刻意排除:
#   - LANG: zh_CN.UTF-8 —— 出口 IP 已偏中文区,locale 再叠中文 = 关联信号放大
#   - TZ:  Asia/Shanghai —— 同上,时区与 IP 相关性会让差异化失效
# 详见 .trellis/tasks/05-25-account-env-fingerprint-isolation/design.md §2
_TZ_POOL = [
    "Asia/Tokyo", "Asia/Singapore", "Asia/Seoul",
    "Australia/Sydney", "Europe/London", "Europe/Berlin", "Europe/Paris",
    "America/Los_Angeles", "America/New_York", "America/Chicago",
]
_LANG_POOL = [
    "en_US.UTF-8", "ja_JP.UTF-8", "ko_KR.UTF-8",
    "de_DE.UTF-8", "fr_FR.UTF-8",
]
# Docker mem_limit 池(给 worker 容器),刻意避开 2g 防止 compile/test 重题 OOM
# 走 cgroup 后 Node 的 process.constrainedMemory() / os.totalmem() 都会读到此值
_MEM_POOL = ["4g", "8g", "16g", "32g"]


def derive_fingerprint(account_name: str) -> dict[str, str]:
    """
    按账号名 sha256 派生稳定的环境指纹。

    :param account_name: 账号名(调用前已被 _ACC_NAME_RE 校验)
    :return: dict 包含 hostname / mac / tz / lang / machine_id / mem
             - hostname: "vb-<8 hex>",11 字符,符合 Docker hostname / DNS label
             - mac: "02:xx:xx:xx:xx:xx",高位 0x02 = 本地管理 + individual
             - tz: IANA 时区名(_TZ_POOL 之一)
             - lang: locale 字符串(_LANG_POOL 之一)
             - machine_id: 32 位小写 hex,写入容器内 /etc/machine-id
             - mem: Docker mem_limit 字符串("4g"/"8g"/"16g"/"32g"),让 cgroup
                    层面 Node 读到的 totalmem / constrainedMemory 按账号差异化
    """
    digest = hashlib.sha256(account_name.encode("utf-8")).digest()
    # hostname / MAC 用 seed[0:4] / seed[1:6] 故意 1 字节重叠 —— 视觉弱关联,
    # 但不会造成熵冲突(两者各自取的独立字节组合空间仍 > 2^32)
    hostname = "vb-" + digest[0:4].hex()
    mac_bytes = bytes([0x02]) + digest[1:6]
    mac = ":".join(f"{b:02x}" for b in mac_bytes)
    return {
        "hostname": hostname,
        "mac": mac,
        "tz": _TZ_POOL[digest[6] % len(_TZ_POOL)],
        "lang": _LANG_POOL[digest[7] % len(_LANG_POOL)],
        "machine_id": digest.hex()[:32],
        "mem": _MEM_POOL[digest[8] % len(_MEM_POOL)],
    }


# ============== Docker 运行器 ==============
class Runner:
    """封装 sidecar + worker 的生命周期"""

    def __init__(self) -> None:
        self.client = docker.from_env()

    def start_run(self, run_id: str, account: dict, task: dict) -> tuple[str, str]:
        """启动 sidecar + worker，返回 (sidecar_id, worker_id)"""
        sidecar_name = f"bench-sidecar-{run_id}"
        worker_name = f"bench-worker-{run_id}"
        acc_name = account["name"]
        # 账号派生指纹:同账号每次 run 拿到一致的 hostname/MAC/TZ/LANG/machine-id,
        # 跨账号则不同,避免 Anthropic 端把多账号识别为同台机器
        fp = derive_fingerprint(acc_name)

        # 容器内创建运行目录（docker 会按宿主路径挂载到子容器）
        (BENCH_DATA / "workspaces" / run_id).mkdir(parents=True, exist_ok=True)
        (BENCH_DATA / "flows" / acc_name / str(task["id"]) / run_id).mkdir(parents=True, exist_ok=True)
        CA_DIR.mkdir(parents=True, exist_ok=True)

        host_workspace = HOST_BENCH_DATA / "workspaces" / run_id
        host_flows = HOST_BENCH_DATA / "flows" / acc_name / str(task["id"]) / run_id
        host_profile = HOST_BENCH_DATA / "profiles" / acc_name
        host_ca = HOST_BENCH_DATA / "ca"

        # --- sidecar：透明代理 + MITM ---
        # hostname + mac_address 由账号派生,worker 共享其 netns 后出口 MAC 即此值
        sidecar = self.client.containers.run(
            SIDECAR_IMAGE,
            name=sidecar_name,
            hostname=fp["hostname"],
            mac_address=fp["mac"],
            detach=True,
            auto_remove=False,
            cap_add=["NET_ADMIN"],
            devices=["/dev/net/tun:/dev/net/tun"],
            volumes={
                str(host_flows): {"bind": "/flows", "mode": "rw"},
                str(host_ca): {"bind": "/ca", "mode": "rw"},
            },
            environment={
                "UPSTREAM_SOCKS5_HOST": account.get("upstream_socks5_host") or "",
                "UPSTREAM_SOCKS5_PORT": str(account.get("upstream_socks5_port") or 1080),
                "UPSTREAM_SOCKS5_USER": account.get("upstream_socks5_user") or "",
                "UPSTREAM_SOCKS5_PASS": account.get("upstream_socks5_pass") or "",
            },
        )

        # 等 sidecar 起：mitmdump 启动 + CA 落盘大约 2-4 秒
        time.sleep(SIDECAR_BOOT_WAIT)

        # --- worker：共享 sidecar 网络命名空间 ---
        # 注意:network_mode=container:xxx 时 Docker 拒绝同时传 hostname,
        # worker 会自动继承 sidecar 的 hostname —— 这正好是我们想要的语义,
        # 所以不显式传 hostname,让 sidecar 的 fp["hostname"] 自然生效。
        # ACC_NAME 注入用于 entrypoint 写 /etc/machine-id;TZ/LANG/LC_ALL 影响
        # Claude Code 在 system prompt 与 telemetry 里上报的字面值
        worker = self.client.containers.run(
            WORKER_IMAGE,
            name=worker_name,
            # mem_limit + memswap_limit 同值:走 cgroup,Node 的
            # constrainedMemory 自动反映此值;同值禁止 swap,Node 撞上限直接
            # 被 oom-killer 杀(明确失败 > 走 swap 死撑)
            mem_limit=fp["mem"],
            memswap_limit=fp["mem"],
            detach=True,
            auto_remove=False,
            network_mode=f"container:{sidecar_name}",
            volumes={
                str(host_profile): {"bind": "/mnt/profile", "mode": "ro"},
                str(host_workspace): {"bind": "/workspace", "mode": "rw"},
                str(host_ca): {"bind": "/etc/mitm", "mode": "ro"},
            },
            environment={
                "TASK_PROMPT": task["prompt"],
                "RUN_ID": run_id,
                "TIMEOUT_SEC": str(task.get("timeout_sec", 1800)),
                "ACC_NAME": acc_name,
                "TZ": fp["tz"],
                "LANG": fp["lang"],
                "LC_ALL": fp["lang"],
            },
        )

        return sidecar.id, worker.id

    def wait_worker(self, worker_id: str) -> int:
        worker = self.client.containers.get(worker_id)
        result = worker.wait()
        return int(result.get("StatusCode", -1))

    def cleanup(self, sidecar_id: Optional[str], worker_id: Optional[str]) -> None:
        for cid in (worker_id, sidecar_id):
            if not cid:
                continue
            try:
                c = self.client.containers.get(cid)
                try:
                    c.stop(timeout=5)
                except Exception:
                    pass
                c.remove(force=True)
            except Exception:
                # 容器可能已经被 remove
                pass


# ============== Login 会话管理 ==============
# OAuth 必须走 PTY（`claude auth login` 拒绝非 TTY 输入），所以在 worker 容器里
# `docker exec -it claude auth login`，把 PTY socket 桥到浏览器 xterm.js WebSocket。
# OAuth 流量必须走 sidecar（账号绑 IP），否则后续 API 调用会因换 IP 被风控。
_ACC_NAME_RE = re.compile(r"^[a-zA-Z0-9_-]+$")


class LoginSession:
    """单个 OAuth 引导会话：一对 sidecar+worker + 元数据"""

    __slots__ = ("sid", "name", "sidecar_id", "worker_id", "created_at",
                 "socks5", "committed")

    def __init__(self, sid: str, name: str, sidecar_id: Optional[str],
                 worker_id: str, socks5: dict) -> None:
        self.sid = sid
        self.name = name
        self.sidecar_id = sidecar_id
        self.worker_id = worker_id
        self.created_at = time.time()
        self.socks5 = socks5
        self.committed = False


class LoginManager:
    def __init__(self, client: "docker.DockerClient") -> None:
        self.client = client
        self.sessions: dict[str, LoginSession] = {}
        # 同一个账号名同时只允许一个 login session（防并发覆盖 profile）
        self._name_locks: dict[str, str] = {}
        self._lock = threading.Lock()

    def cleanup_stale(self) -> None:
        """启动时调用：清掉上次 orchestrator 进程残留的 bench-login-* 容器"""
        try:
            for c in self.client.containers.list(
                all=True, filters={"name": "bench-login-"}
            ):
                try:
                    c.remove(force=True)
                except Exception:
                    pass
        except Exception:
            pass

    def start(self, name: str, socks5: dict) -> LoginSession:
        if not _ACC_NAME_RE.match(name):
            raise ValueError(
                "invalid account name: must match [a-zA-Z0-9_-]+"
            )
        with self._lock:
            if name in self._name_locks:
                raise ValueError(
                    f"login session already in progress for '{name}'; "
                    f"cancel it first"
                )
            sid = uuid.uuid4().hex[:12]
            self._name_locks[name] = sid

        try:
            host_profile = HOST_BENCH_DATA / "profiles" / name
            (BENCH_DATA / "profiles" / name).mkdir(parents=True, exist_ok=True)
            CA_DIR.mkdir(parents=True, exist_ok=True)
            host_ca = HOST_BENCH_DATA / "ca"

            sidecar_name = f"bench-login-sidecar-{sid}"
            worker_name = f"bench-login-worker-{sid}"
            sidecar_id: Optional[str] = None
            worker_network: str = "bridge"
            # login 模式与 task 模式共用同一派生指纹,确保 OAuth 时和后续 API
            # 调用在 Anthropic 端看起来是同一台机器
            fp = derive_fingerprint(name)

            # 有 SOCKS5 才起 sidecar；没填的话直走宿主默认网络（用户自担风险）
            if socks5.get("host"):
                sidecar = self.client.containers.run(
                    SIDECAR_IMAGE,
                    name=sidecar_name,
                    hostname=fp["hostname"],
                    mac_address=fp["mac"],
                    detach=True,
                    auto_remove=False,
                    cap_add=["NET_ADMIN"],
                    devices=["/dev/net/tun:/dev/net/tun"],
                    volumes={
                        str(host_ca): {"bind": "/ca", "mode": "rw"},
                    },
                    environment={
                        "UPSTREAM_SOCKS5_HOST": socks5.get("host") or "",
                        "UPSTREAM_SOCKS5_PORT": str(socks5.get("port") or 1080),
                        "UPSTREAM_SOCKS5_USER": socks5.get("user") or "",
                        "UPSTREAM_SOCKS5_PASS": socks5.get("pass") or "",
                    },
                )
                sidecar_id = sidecar.id
                time.sleep(SIDECAR_BOOT_WAIT)
                worker_network = f"container:{sidecar_name}"

            # worker：login 模式，profile 目录直接 rw 挂到 /root/.claude
            # hostname 注入条件:network_mode=container:xxx 时 Docker 拒绝
            # 同时传 hostname(会继承 sidecar 的);只在 bridge 模式自己设。
            # MAC 同样:有 sidecar 时由 sidecar 决定,bridge 模式我们控不了。
            # mem_limit 与 task 模式一致,确保 login 时 Anthropic 看到的
            # constrainedMemory 跟后续 task 时是同一台机器。
            worker_kwargs: dict = {
                "name": worker_name,
                "mem_limit": fp["mem"],
                "memswap_limit": fp["mem"],
                "detach": True,
                "auto_remove": False,
                "tty": True,
                "stdin_open": True,
                "network_mode": worker_network,
                "volumes": {
                    str(host_profile): {"bind": "/root/.claude", "mode": "rw"},
                    str(host_ca): {"bind": "/etc/mitm", "mode": "ro"},
                },
                "environment": {
                    "WORKER_MODE": "login",
                    "ACC_NAME": name,
                    "TZ": fp["tz"],
                    "LANG": fp["lang"],
                    "LC_ALL": fp["lang"],
                },
            }
            if worker_network == "bridge":
                # 走 bridge 才能自己设 hostname;共享 netns 时继承 sidecar 的
                worker_kwargs["hostname"] = fp["hostname"]
            worker = self.client.containers.run(WORKER_IMAGE, **worker_kwargs)

            session = LoginSession(
                sid, name, sidecar_id, worker.id, socks5
            )
            with self._lock:
                self.sessions[sid] = session
            return session
        except Exception:
            with self._lock:
                self._name_locks.pop(name, None)
            raise

    def get(self, sid: str) -> Optional[LoginSession]:
        return self.sessions.get(sid)

    def auth_status(self, sid: str) -> dict:
        s = self.get(sid)
        if not s:
            raise KeyError(sid)
        api = self.client.api
        ex = api.exec_create(
            s.worker_id, ["claude", "auth", "status"],
            stdout=True, stderr=True,
        )
        raw = api.exec_start(ex["Id"])
        text = raw.decode("utf-8", errors="ignore").strip()
        # claude auth status 返回 JSON
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return {"raw": text, "loggedIn": False}

    def cleanup(self, sid: str) -> None:
        with self._lock:
            s = self.sessions.pop(sid, None)
        if not s:
            return
        for cid in (s.worker_id, s.sidecar_id):
            if not cid:
                continue
            try:
                c = self.client.containers.get(cid)
                try:
                    c.stop(timeout=3)
                except Exception:
                    pass
                c.remove(force=True)
            except Exception:
                pass
        with self._lock:
            if self._name_locks.get(s.name) == sid:
                del self._name_locks[s.name]


# ============== 调度器：每账号 Semaphore(2) ==============
class Scheduler:
    def __init__(self, runner: Runner) -> None:
        self.runner = runner
        self._sems: dict[int, threading.Semaphore] = {}
        self._sems_lock = threading.Lock()

    def _sem(self, account_id: int) -> threading.Semaphore:
        with self._sems_lock:
            if account_id not in self._sems:
                self._sems[account_id] = threading.Semaphore(PER_ACCOUNT_CONCURRENCY)
            return self._sems[account_id]

    def submit(self, run_id: str, account: dict, task: dict) -> None:
        threading.Thread(
            target=self._execute,
            args=(run_id, dict(account), dict(task)),
            daemon=True,
        ).start()

    def _execute(self, run_id: str, account: dict, task: dict) -> None:
        sem = self._sem(account["id"])
        sem.acquire()
        sid: Optional[str] = None
        wid: Optional[str] = None
        try:
            self._update(
                run_id,
                status="running",
                started_at=time.time(),
                workspace_dir=str(WORKSPACES_DIR / run_id),
                flows_dir=str(FLOWS_DIR / account["name"] / str(task["id"]) / run_id),
            )
            try:
                sid, wid = self.runner.start_run(run_id, account, task)
                self._update(run_id, sidecar_container=sid, worker_container=wid)
                exit_code = self.runner.wait_worker(wid)
                if exit_code == 0:
                    status = "success"
                elif exit_code == 124:
                    status = "timeout"
                else:
                    status = "failed"
                self._update(run_id, status=status, exit_code=exit_code, ended_at=time.time())
            except Exception as e:
                self._update(run_id, status="failed", error=str(e), ended_at=time.time())
            finally:
                self.runner.cleanup(sid, wid)
        finally:
            sem.release()

    def _update(self, run_id: str, **fields) -> None:
        if not fields:
            return
        cols = ", ".join(f"{k}=?" for k in fields)
        params = list(fields.values()) + [run_id]
        with _db_lock:
            conn = get_db()
            try:
                with conn:
                    conn.execute(f"UPDATE runs SET {cols} WHERE id=?", params)
            finally:
                conn.close()


# ============== FastAPI ==============
runner: Optional[Runner] = None
scheduler: Optional[Scheduler] = None
login_manager: Optional[LoginManager] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global runner, scheduler, login_manager
    init_db()
    PROFILES_DIR.mkdir(parents=True, exist_ok=True)
    FLOWS_DIR.mkdir(parents=True, exist_ok=True)
    WORKSPACES_DIR.mkdir(parents=True, exist_ok=True)
    CA_DIR.mkdir(parents=True, exist_ok=True)
    runner = Runner()
    scheduler = Scheduler(runner)
    login_manager = LoginManager(runner.client)
    # 清掉上次进程残留的 login 容器，避免重启后僵尸容器堆积
    login_manager.cleanup_stale()
    yield


app = FastAPI(title="vibecoding-100 bench", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def basic_auth_middleware(request, call_next):
    """
    HTTP Basic Auth 网关。
    - 仅在 WEBUI_USER + WEBUI_PASS 都设置时启用,留空则放行所有请求(本地开发兼容)
    - 使用 secrets.compare_digest 防 timing attack
    - 仅作用于 HTTP 请求;WebSocket(/api/accounts/login/ws/{sid})不经此中间件,
      但 sid 必须先通过鉴权的 login_start 才能拿到,间接受保护
    - 401 响应带 WWW-Authenticate 头,触发浏览器原生密码弹窗
    """
    if not _AUTH_ENABLED:
        return await call_next(request)
    auth = request.headers.get("authorization", "")
    if auth.startswith("Basic "):
        try:
            decoded = base64.b64decode(auth[6:].strip()).decode("utf-8", "ignore")
            user, _, pwd = decoded.partition(":")
            if (
                secrets.compare_digest(user, WEBUI_USER)
                and secrets.compare_digest(pwd, WEBUI_PASS)
            ):
                return await call_next(request)
        except Exception:
            pass
    return Response(
        status_code=401,
        content="auth required",
        headers={"WWW-Authenticate": 'Basic realm="vibebench"'},
    )


# ---------- accounts ----------
class AccountIn(BaseModel):
    name: str
    upstream_socks5_host: Optional[str] = None
    upstream_socks5_port: Optional[int] = None
    upstream_socks5_user: Optional[str] = None
    upstream_socks5_pass: Optional[str] = None
    enabled: bool = True


@app.post("/api/accounts")
def create_account(body: AccountIn):
    pp = PROFILES_DIR / body.name
    if not pp.exists() or not any(pp.iterdir()):
        raise HTTPException(
            400,
            f"profile empty or missing: {pp}. "
            f"Run scripts/init-account.sh {body.name} first.",
        )
    with _db_lock:
        conn = get_db()
        try:
            with conn:
                cur = conn.execute(
                    "INSERT INTO accounts(name, profile_path, "
                    "upstream_socks5_host, upstream_socks5_port, "
                    "upstream_socks5_user, upstream_socks5_pass, enabled) "
                    "VALUES(?,?,?,?,?,?,?)",
                    (
                        body.name,
                        f"profiles/{body.name}",
                        body.upstream_socks5_host,
                        body.upstream_socks5_port,
                        body.upstream_socks5_user,
                        body.upstream_socks5_pass,
                        int(body.enabled),
                    ),
                )
                return {"id": cur.lastrowid}
        except sqlite3.IntegrityError as e:
            raise HTTPException(400, f"account exists: {e}")
        finally:
            conn.close()


@app.get("/api/accounts")
def list_accounts():
    conn = get_db()
    try:
        rows = conn.execute("SELECT * FROM accounts ORDER BY id").fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


@app.delete("/api/accounts/{aid}")
def delete_account(aid: int):
    with _db_lock:
        conn = get_db()
        try:
            with conn:
                conn.execute("DELETE FROM accounts WHERE id=?", (aid,))
        finally:
            conn.close()
    return {"ok": True}


# ---------- accounts: 内嵌 OAuth 登录（WebUI 用） ----------
class LoginStartIn(BaseModel):
    """添加账号第一步：起 login 会话，配置 SOCKS5 走代理做 OAuth"""

    name: str
    upstream_socks5_host: Optional[str] = None
    upstream_socks5_port: Optional[int] = None
    upstream_socks5_user: Optional[str] = None
    upstream_socks5_pass: Optional[str] = None


@app.post("/api/accounts/login/start")
def login_start(body: LoginStartIn):
    """启动一个 OAuth 引导会话；前端拿到 session_id 后开 WS 拿 PTY"""
    if not login_manager:
        raise HTTPException(500, "login manager not ready")
    try:
        session = login_manager.start(
            body.name,
            {
                "host": body.upstream_socks5_host,
                "port": body.upstream_socks5_port,
                "user": body.upstream_socks5_user,
                "pass": body.upstream_socks5_pass,
            },
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(500, f"failed to start login session: {e}")
    return {
        "session_id": session.sid,
        "ws_path": f"/api/accounts/login/ws/{session.sid}",
        "has_sidecar": session.sidecar_id is not None,
        "name": session.name,
    }


@app.websocket("/api/accounts/login/ws/{sid}")
async def login_ws(websocket: WebSocket, sid: str):
    """PTY 桥：把 worker 里 `claude auth login` 的 PTY 双向接到浏览器 xterm"""
    await websocket.accept()
    if not login_manager:
        await websocket.close(code=4500)
        return
    session = login_manager.get(sid)
    if not session:
        await websocket.send_text(json.dumps(
            {"type": "error", "msg": "session not found"}))
        await websocket.close(code=4004)
        return

    api = login_manager.client.api
    try:
        exec_id = api.exec_create(
            session.worker_id,
            ["claude", "auth", "login"],
            stdin=True,
            tty=True,
            environment={
                "TERM": "xterm-256color",
                "COLUMNS": "120",
                "LINES": "36",
            },
        )["Id"]
        sock = api.exec_start(
            exec_id, detach=False, tty=True,
            stream=False, socket=True, demux=False,
        )
    except Exception as e:
        await websocket.send_text(json.dumps(
            {"type": "error", "msg": f"exec failed: {e}"}))
        await websocket.close(code=4500)
        return

    raw = getattr(sock, "_sock", None) or sock
    try:
        raw.setblocking(False)
    except Exception:
        pass

    loop = asyncio.get_event_loop()
    closed = asyncio.Event()

    async def pump_container_to_ws():
        """worker PTY → ws (binary)"""
        try:
            while not closed.is_set():
                try:
                    data = await asyncio.wait_for(
                        loop.sock_recv(raw, 4096), timeout=1.0
                    )
                except asyncio.TimeoutError:
                    continue
                if not data:
                    break
                if websocket.client_state != WebSocketState.CONNECTED:
                    break
                await websocket.send_bytes(data)
        except Exception:
            pass
        finally:
            closed.set()

    async def pump_ws_to_container():
        """ws → worker PTY (text json msg or binary)"""
        try:
            while not closed.is_set():
                msg = await websocket.receive()
                if msg["type"] == "websocket.disconnect":
                    break
                if msg.get("bytes"):
                    raw.send(msg["bytes"])
                    continue
                txt = msg.get("text")
                if not txt:
                    continue
                # text 消息约定 JSON：{type:input|resize, ...}
                try:
                    ev = json.loads(txt)
                except json.JSONDecodeError:
                    raw.send(txt.encode())
                    continue
                if ev.get("type") == "resize":
                    try:
                        api.exec_resize(
                            exec_id,
                            height=int(ev.get("rows") or 36),
                            width=int(ev.get("cols") or 120),
                        )
                    except Exception:
                        pass
                elif ev.get("type") == "input":
                    raw.send((ev.get("data") or "").encode())
        except WebSocketDisconnect:
            pass
        except Exception:
            pass
        finally:
            closed.set()

    try:
        await asyncio.gather(
            pump_container_to_ws(), pump_ws_to_container()
        )
    finally:
        try:
            raw.close()
        except Exception:
            pass
        if websocket.client_state == WebSocketState.CONNECTED:
            try:
                await websocket.close()
            except Exception:
                pass


@app.post("/api/accounts/login/{sid}/commit")
def login_commit(sid: str, body: LoginStartIn):
    """登录完成后调用：校验 `claude auth status`，落 accounts 表，清容器"""
    if not login_manager:
        raise HTTPException(500)
    session = login_manager.get(sid)
    if not session:
        raise HTTPException(404, "session not found")
    if session.name != body.name:
        raise HTTPException(400, "name mismatch with session")

    # 撞 in-flight run 直接拒绝:此时若 commit 继续往下走会清 telemetry/backups,
    # 与正在跑的 run 复制 profile 的窗口发生竞态。让用户主动决定何时重登。
    # 首次登录场景下 account 还没入库,COUNT 必为 0,自然通过。
    name = session.name
    conn = get_db()
    try:
        inflight = conn.execute(
            "SELECT COUNT(*) AS n FROM runs r "
            "JOIN accounts a ON r.account_id = a.id "
            "WHERE a.name = ? AND r.status IN ('queued','running')",
            (name,),
        ).fetchone()
    finally:
        conn.close()
    if inflight and inflight["n"] > 0:
        raise HTTPException(
            409,
            f"account '{name}' has {inflight['n']} in-flight run(s); "
            f"wait for them to finish or cancel before re-login",
        )

    try:
        status = login_manager.auth_status(sid)
    except KeyError:
        raise HTTPException(404, "session not found")
    except Exception as e:
        raise HTTPException(500, f"auth status check failed: {e}")
    if not status.get("loggedIn"):
        # 不清容器：让用户继续 retry。返回错误细节给前端展示。
        raise HTTPException(400, f"not logged in yet: {status}")

    # 清理 profile 残留遥测痕迹:OAuth 启动那次 claude 写到 telemetry/ 和
    # backups/ 的内容对后续 task run 无用,反而会被一路重放 → 入库前清掉。
    # 路径只用 session.name(_ACC_NAME_RE 已校验),且必须用 BENCH_DATA
    # (orchestrator 容器内路径),不能用 HOST_BENCH_DATA(那是给 docker daemon
    # 报告挂载点的宿主路径,在 orchestrator 容器里访问不到)。
    profile_dir = BENCH_DATA / "profiles" / name
    shutil.rmtree(profile_dir / "telemetry", ignore_errors=True)
    shutil.rmtree(profile_dir / "backups", ignore_errors=True)

    with _db_lock:
        conn = get_db()
        try:
            with conn:
                try:
                    cur = conn.execute(
                        "INSERT INTO accounts(name, profile_path, "
                        "upstream_socks5_host, upstream_socks5_port, "
                        "upstream_socks5_user, upstream_socks5_pass, enabled) "
                        "VALUES(?,?,?,?,?,?,?)",
                        (
                            name,
                            f"profiles/{name}",
                            body.upstream_socks5_host,
                            body.upstream_socks5_port,
                            body.upstream_socks5_user,
                            body.upstream_socks5_pass,
                            1,
                        ),
                    )
                    account_id = cur.lastrowid
                except sqlite3.IntegrityError:
                    # 同名账号已存在 → 视为"重新登录"：只覆盖 socks5
                    conn.execute(
                        "UPDATE accounts SET upstream_socks5_host=?, "
                        "upstream_socks5_port=?, upstream_socks5_user=?, "
                        "upstream_socks5_pass=? WHERE name=?",
                        (
                            body.upstream_socks5_host,
                            body.upstream_socks5_port,
                            body.upstream_socks5_user,
                            body.upstream_socks5_pass,
                            name,
                        ),
                    )
                    r = conn.execute(
                        "SELECT id FROM accounts WHERE name=?", (name,)
                    ).fetchone()
                    account_id = r["id"]
        finally:
            conn.close()

    login_manager.cleanup(sid)
    return {
        "id": account_id,
        "name": name,
        "auth_method": status.get("authMethod"),
    }


@app.delete("/api/accounts/login/{sid}")
def login_cancel(sid: str):
    """放弃登录：停容器 + 清状态。可重复调用幂等。"""
    if login_manager:
        login_manager.cleanup(sid)
    return {"ok": True}


# ---------- topics ----------
@app.get("/api/topics")
def list_topics():
    return load_topics()


# ---------- tasks ----------
class TaskIn(BaseModel):
    topic_no: int
    account_id: int
    prompt: Optional[str] = None
    timeout_sec: int = 1800
    repeat_n: int = 1


@app.post("/api/tasks")
def create_task(body: TaskIn):
    topic = next((t for t in load_topics() if t["no"] == body.topic_no), None)
    if not topic:
        raise HTTPException(404, f"topic {body.topic_no} not found")
    prompt = body.prompt or (
        f"{topic['title']}：{topic['description']}\n\n"
        "请在当前目录下从 0 到 1 实现一个 MVP（功能跑通即可，先不追求架构完美）。"
        "完成后简要总结你做了什么。"
    )
    with _db_lock:
        conn = get_db()
        try:
            with conn:
                cur = conn.execute(
                    "INSERT INTO tasks(topic_no, title, prompt, account_id, timeout_sec, repeat_n) "
                    "VALUES(?,?,?,?,?,?)",
                    (body.topic_no, topic["title"], prompt, body.account_id, body.timeout_sec, body.repeat_n),
                )
                return {"id": cur.lastrowid}
        finally:
            conn.close()


@app.get("/api/tasks")
def list_tasks():
    conn = get_db()
    try:
        rows = conn.execute("SELECT * FROM tasks ORDER BY id DESC").fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


# ---------- runs ----------
@app.post("/api/tasks/{tid}/run")
def run_task(tid: int):
    conn = get_db()
    try:
        task_row = conn.execute("SELECT * FROM tasks WHERE id=?", (tid,)).fetchone()
        if not task_row:
            raise HTTPException(404, "task not found")
        task = dict(task_row)
        account_row = conn.execute("SELECT * FROM accounts WHERE id=?", (task["account_id"],)).fetchone()
        if not account_row:
            raise HTTPException(404, "account not found")
        account = dict(account_row)
    finally:
        conn.close()

    run_ids: list[str] = []
    for _ in range(int(task.get("repeat_n", 1))):
        rid = uuid.uuid4().hex[:12]
        with _db_lock:
            conn = get_db()
            try:
                with conn:
                    conn.execute(
                        "INSERT INTO runs(id, task_id, account_id, status) VALUES(?,?,?,?)",
                        (rid, tid, account["id"], "queued"),
                    )
            finally:
                conn.close()
        assert scheduler is not None
        scheduler.submit(rid, account, task)
        run_ids.append(rid)
    return {"run_ids": run_ids}


@app.get("/api/runs")
def list_runs(limit: int = 200):
    conn = get_db()
    try:
        rows = conn.execute(
            "SELECT * FROM runs ORDER BY (started_at IS NULL), started_at DESC, created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


@app.get("/api/runs/{rid}")
def get_run(rid: str):
    conn = get_db()
    try:
        row = conn.execute("SELECT * FROM runs WHERE id=?", (rid,)).fetchone()
        if not row:
            raise HTTPException(404)
        return dict(row)
    finally:
        conn.close()


@app.get("/api/runs/{rid}/transcript")
def get_transcript(rid: str):
    p = WORKSPACES_DIR / rid / ".bench-transcript.log"
    if not p.exists():
        raise HTTPException(404, "transcript not yet available")
    return FileResponse(p, media_type="text/plain")


@app.get("/api/runs/{rid}/files")
def list_workspace(rid: str):
    base = WORKSPACES_DIR / rid
    if not base.exists():
        raise HTTPException(404)
    out: list[dict] = []
    for p in sorted(base.rglob("*")):
        rel = p.relative_to(base)
        if str(rel).startswith(".bench-"):
            continue
        if p.is_dir():
            out.append({"path": str(rel), "type": "dir"})
        else:
            out.append({"path": str(rel), "type": "file", "size": p.stat().st_size})
    return out


@app.get("/api/runs/{rid}/stats")
def get_stats(rid: str):
    """从 sidecar 写的 stats.jsonl 聚合 token / 状态码"""
    base = FLOWS_DIR
    # flows 目录按 account/task/run 分层，扫描所有匹配
    matches = list(base.rglob(f"{rid}/stats.jsonl"))
    if not matches:
        return {"tokens_in": 0, "tokens_out": 0, "requests": 0, "errors": 0}
    tokens_in = tokens_out = requests = errors = 0
    for f in matches:
        for line in f.read_text(encoding="utf-8", errors="ignore").splitlines():
            try:
                rec = json.loads(line)
            except Exception:
                continue
            if "error" in rec:
                errors += 1
                continue
            requests += 1
            u = rec.get("usage") or {}
            tokens_in += int(u.get("input_tokens") or 0)
            tokens_out += int(u.get("output_tokens") or 0)
    return {"tokens_in": tokens_in, "tokens_out": tokens_out, "requests": requests, "errors": errors}


# ---------- SSE：推送 runs 列表 ----------
@app.get("/api/runs/stream")
async def stream_runs():
    async def gen():
        last_payload = ""
        while True:
            conn = get_db()
            try:
                rows = conn.execute(
                    "SELECT * FROM runs ORDER BY (started_at IS NULL), started_at DESC, created_at DESC LIMIT 100"
                ).fetchall()
            finally:
                conn.close()
            payload = json.dumps([dict(r) for r in rows], default=str, ensure_ascii=False)
            if payload != last_payload:
                last_payload = payload
                yield {"event": "runs", "data": payload}
            await asyncio.sleep(1)
    return EventSourceResponse(gen())


# ---------- 静态 WebUI ----------
if WEBUI_DIR.exists():
    app.mount("/", StaticFiles(directory=str(WEBUI_DIR), html=True), name="ui")
