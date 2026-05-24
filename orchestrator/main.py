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
import json
import os
import re
import sqlite3
import threading
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

import docker
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse


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

        # 容器内创建运行目录（docker 会按宿主路径挂载到子容器）
        (BENCH_DATA / "workspaces" / run_id).mkdir(parents=True, exist_ok=True)
        (BENCH_DATA / "flows" / acc_name / str(task["id"]) / run_id).mkdir(parents=True, exist_ok=True)
        CA_DIR.mkdir(parents=True, exist_ok=True)

        host_workspace = HOST_BENCH_DATA / "workspaces" / run_id
        host_flows = HOST_BENCH_DATA / "flows" / acc_name / str(task["id"]) / run_id
        host_profile = HOST_BENCH_DATA / "profiles" / acc_name
        host_ca = HOST_BENCH_DATA / "ca"

        # --- sidecar：透明代理 + MITM ---
        sidecar = self.client.containers.run(
            SIDECAR_IMAGE,
            name=sidecar_name,
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
        worker = self.client.containers.run(
            WORKER_IMAGE,
            name=worker_name,
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


@asynccontextmanager
async def lifespan(app: FastAPI):
    global runner, scheduler
    init_db()
    PROFILES_DIR.mkdir(parents=True, exist_ok=True)
    FLOWS_DIR.mkdir(parents=True, exist_ok=True)
    WORKSPACES_DIR.mkdir(parents=True, exist_ok=True)
    CA_DIR.mkdir(parents=True, exist_ok=True)
    runner = Runner()
    scheduler = Scheduler(runner)
    yield


app = FastAPI(title="vibecoding-100 bench", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
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
