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
import hmac
import json
import os
import random
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
from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response
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
WORKER_USER = "node"
WORKER_HOME = "/home/node"
WORKER_UID = 1000
WORKER_GID = 1000

# Cookie-Session 鉴权(可选,替代 Basic Auth 给前端做风格统一的登录页):
# - WEBUI_USER + WEBUI_PASS 都填才启用,任一为空则旁路放行(本地开发)
# - WEBUI_SESSION_SECRET 用于 HMAC 签名 cookie;留空 = 进程启动随机生成
#   (单进程可用,但 orchestrator 重启会注销所有会话 → 生产建议显式设置)
# - WebSocket 路由由 sid(uuid4 12 hex ≈ 48 位熵)间接保护:sid 仅由已通过
#   鉴权的 POST /login/start 生成,直接访问 WS 拿不到合法 sid
WEBUI_USER = os.environ.get("WEBUI_USER", "")
WEBUI_PASS = os.environ.get("WEBUI_PASS", "")
_AUTH_ENABLED = bool(WEBUI_USER and WEBUI_PASS)
_SESSION_SECRET = os.environ.get("WEBUI_SESSION_SECRET") or secrets.token_hex(32)
_SESSION_TTL = 7 * 24 * 3600  # 7 天
_SESSION_COOKIE = "vb_session"
_DEFAULT_CLAUDE_SETTINGS: dict[str, object] = {
    "env": {
        "CLAUDE_CODE_EFFORT_LEVEL": "max",
    },
    "permissions": {
        "defaultMode": "bypassPermissions",
        "allow": [
            "Bash",
            "BashOutput",
            "Edit",
            "Glob",
            "Grep",
            "KillShell",
            "NotebookEdit",
            "Read",
            "SlashCommand",
            "Task",
            "TodoWrite",
            "WebFetch",
            "WebSearch",
            "Write",
        ],
        "deny": [],
    },
    "skipDangerousModePermissionPrompt": True,
    "autoMemoryEnabled": False,
    "theme": "dark",
    "model": "opus[1m]",
}
_DEFAULT_CLAUDE_TOP_CONFIG: dict[str, object] = {
    "hasCompletedOnboarding": True,
    "bypassPermissionsModeAccepted": True,
}
_PROFILE_SYNC_FILES = (".credentials.json", "settings.json", ".claude.json")
_TERMINAL_RUN_STATUSES = {"success", "failed", "timeout", "stopped"}


def _merge_claude_settings(existing: object, defaults: dict[str, object]) -> dict[str, object]:
    """
    递归合并 Claude settings，保留未知字段并让项目默认值覆盖同名字段。

    :param existing: 现有 settings.json 解析结果；非对象时视为空配置
    :param defaults: 项目要求写入的默认 settings
    :return: 合并后的 settings 对象
    """
    merged = dict(existing) if isinstance(existing, dict) else {}
    for key, value in defaults.items():
        old_value = merged.get(key)
        if isinstance(old_value, dict) and isinstance(value, dict):
            merged[key] = _merge_claude_settings(old_value, value)
        else:
            merged[key] = value
    return merged


def _persist_default_claude_settings(profile_dir: Path) -> None:
    """
    把默认 settings.json 持久化进账号 profile 目录。

    :param profile_dir: `data/profiles/<account>` 对应目录
    :return: None
    """
    profile_dir.mkdir(parents=True, exist_ok=True)
    settings_path = profile_dir / "settings.json"
    existing: object = {}
    if settings_path.exists():
        try:
            existing = json.loads(settings_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            # 先备份坏文件再覆盖，避免 Claude 写半截时把现场直接抹掉。
            backup = profile_dir / f"settings.json.invalid.{int(time.time())}"
            try:
                shutil.copy2(settings_path, backup)
            except OSError:
                pass
    merged = _merge_claude_settings(existing, _DEFAULT_CLAUDE_SETTINGS)
    tmp_path = profile_dir / "settings.json.tmp"
    tmp_path.write_text(
        json.dumps(merged, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    tmp_path.replace(settings_path)
    _make_worker_owned(settings_path)


def _persist_default_claude_top_config(profile_dir: Path) -> None:
    """
    补齐顶层 `~/.claude.json` 里的本地 onboarding / bypassPermissions gate。

    :param profile_dir: `data/profiles/<account>` 对应目录
    :return: None
    """
    top_config_path = profile_dir / ".claude.json"
    if not top_config_path.exists():
        return
    try:
        existing = json.loads(top_config_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        # 顶层配置含 OAuth 身份信息；坏文件不应被默认值覆盖成空身份。
        backup = profile_dir / f".claude.json.invalid.{int(time.time())}"
        try:
            shutil.copy2(top_config_path, backup)
        except OSError:
            pass
        return
    if not isinstance(existing, dict):
        return
    merged = dict(existing)
    merged.update(_DEFAULT_CLAUDE_TOP_CONFIG)
    tmp_path = profile_dir / ".claude.json.tmp"
    tmp_path.write_text(
        json.dumps(merged, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    tmp_path.replace(top_config_path)
    _make_worker_owned(top_config_path)


def _make_worker_owned(path: Path) -> None:
    """
    让 worker 容器内的 node 用户可读写宿主挂载路径。

    docker bind mount 会保留宿主 uid/gid；orchestrator 以 root 创建的
    profile/workspace 如果不改属主，Claude 以非 root 跑时无法写配置或产物。
    """
    if not path.exists():
        return
    targets = [path]
    if path.is_dir():
        targets.extend(path.rglob("*"))
    for target in targets:
        try:
            os.chown(target, WORKER_UID, WORKER_GID)
        except OSError:
            # 某些宿主文件系统不支持 chown，保留 chmod 兜底。
            pass
        try:
            mode = target.stat().st_mode & 0o777
            if target.is_dir():
                os.chmod(target, mode | 0o700)
            else:
                os.chmod(target, mode | 0o600)
        except OSError:
            pass


def _copy_profile_whitelist_to_claude_home(profile_dir: Path, claude_home_dir: Path) -> None:
    """
    把账号 profile 的认证白名单复制到某个 Claude home 目录。

    :param profile_dir: `data/profiles/<account>` 目录
    :param claude_home_dir: run/continue 容器挂载的 `.claude` 目录
    :return: None
    """
    claude_home_dir.mkdir(parents=True, exist_ok=True)
    for name in _PROFILE_SYNC_FILES:
        src = profile_dir / name
        if not src.exists() or not src.is_file():
            continue
        dst = claude_home_dir / name
        shutil.copy2(src, dst)
        _make_worker_owned(dst)


def _copy_claude_home_whitelist_to_profile(claude_home_dir: Path, profile_dir: Path) -> None:
    """
    把运行时 Claude home 中刷新的认证白名单回写到账号 profile。

    :param claude_home_dir: run workspace 下的 `.claude-home` 目录
    :param profile_dir: `data/profiles/<account>` 目录
    :return: None
    """
    if not claude_home_dir.exists():
        return
    profile_dir.mkdir(parents=True, exist_ok=True)
    for name in _PROFILE_SYNC_FILES:
        src = claude_home_dir / name
        if not src.exists() or not src.is_file():
            continue
        dst = profile_dir / name
        try:
            shutil.copy2(src, dst)
            _make_worker_owned(dst)
        except OSError:
            pass
    _persist_default_claude_top_config(profile_dir)


def _claude_exec_env(use_sidecar: bool, extra: Optional[dict[str, str]] = None) -> dict[str, str]:
    """
    生成 docker exec 启动 Claude 子命令时必须显式传入的环境变量。

    entrypoint 里 export 的变量不会自动进入 docker exec 创建的新进程；走
    sidecar MITM 时必须重复传 CA 路径，否则登录 TUI 可能不信 MITM 证书。
    """
    env = {"HOME": WORKER_HOME}
    if use_sidecar:
        ca = "/etc/mitm/mitmproxy-ca-cert.pem"
        env.update({
            "NODE_EXTRA_CA_CERTS": ca,
            "SSL_CERT_FILE": ca,
            "REQUESTS_CA_BUNDLE": ca,
            "CURL_CA_BUNDLE": ca,
            "GIT_SSL_CAINFO": ca,
        })
    if extra:
        env.update(extra)
    return env


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

CREATE TABLE IF NOT EXISTS topics (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  no INTEGER UNIQUE NOT NULL,
  title TEXT NOT NULL,
  description TEXT NOT NULL DEFAULT '',
  category TEXT NOT NULL DEFAULT '',
  enabled INTEGER DEFAULT 1,
  deleted_at REAL,
  created_at REAL DEFAULT (julianday('now')),
  updated_at REAL DEFAULT (julianday('now'))
);

CREATE TABLE IF NOT EXISTS tasks (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  topic_no INTEGER NOT NULL,
  title TEXT NOT NULL,
  prompt TEXT NOT NULL,
  account_id INTEGER NOT NULL,
  batch_id INTEGER,
  topic_id INTEGER,
  status TEXT DEFAULT 'active',
  deleted_at REAL,
  timeout_sec INTEGER DEFAULT 1800,
  repeat_n INTEGER DEFAULT 1,
  created_at REAL DEFAULT (julianday('now')),
  FOREIGN KEY(account_id) REFERENCES accounts(id)
);

CREATE TABLE IF NOT EXISTS task_batches (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  account_id INTEGER NOT NULL,
  name TEXT NOT NULL,
  concurrency INTEGER DEFAULT 2,
  interval_min_sec INTEGER DEFAULT 0,
  interval_max_sec INTEGER DEFAULT 0,
  timeout_sec INTEGER DEFAULT 1800,
  status TEXT NOT NULL DEFAULT 'active',
  next_launch_at REAL,
  deleted_at REAL,
  created_at REAL DEFAULT (julianday('now')),
  updated_at REAL DEFAULT (julianday('now')),
  FOREIGN KEY(account_id) REFERENCES accounts(id)
);

CREATE TABLE IF NOT EXISTS task_batch_items (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  batch_id INTEGER NOT NULL,
  topic_id INTEGER NOT NULL,
  task_id INTEGER,
  run_id TEXT,
  prompt TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'pending',
  created_at REAL DEFAULT (julianday('now')),
  updated_at REAL DEFAULT (julianday('now')),
  FOREIGN KEY(batch_id) REFERENCES task_batches(id),
  FOREIGN KEY(topic_id) REFERENCES topics(id)
);

CREATE TABLE IF NOT EXISTS runs (
  id TEXT PRIMARY KEY,
  task_id INTEGER NOT NULL,
  account_id INTEGER NOT NULL,
  batch_id INTEGER,
  topic_id INTEGER,
  status TEXT NOT NULL DEFAULT 'queued',
  exit_code INTEGER,
  worker_container TEXT,
  sidecar_container TEXT,
  workspace_dir TEXT,
  flows_dir TEXT,
  started_at REAL,
  ended_at REAL,
  stop_requested_at REAL,
  deleted_at REAL,
  error TEXT,
  created_at REAL DEFAULT (julianday('now'))
);
CREATE INDEX IF NOT EXISTS idx_runs_status  ON runs(status);
CREATE INDEX IF NOT EXISTS idx_runs_account ON runs(account_id);
CREATE INDEX IF NOT EXISTS idx_runs_task    ON runs(task_id);
CREATE INDEX IF NOT EXISTS idx_runs_batch   ON runs(batch_id);
CREATE INDEX IF NOT EXISTS idx_topics_no    ON topics(no);
CREATE INDEX IF NOT EXISTS idx_batches_account ON task_batches(account_id);
CREATE INDEX IF NOT EXISTS idx_batch_items_batch ON task_batch_items(batch_id);
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
            _ensure_column(conn, "tasks", "batch_id", "INTEGER")
            _ensure_column(conn, "tasks", "topic_id", "INTEGER")
            _ensure_column(conn, "tasks", "status", "TEXT DEFAULT 'active'")
            _ensure_column(conn, "tasks", "deleted_at", "REAL")
            _ensure_column(conn, "runs", "batch_id", "INTEGER")
            _ensure_column(conn, "runs", "topic_id", "INTEGER")
            _ensure_column(conn, "runs", "stop_requested_at", "REAL")
            _ensure_column(conn, "runs", "deleted_at", "REAL")
            _seed_topics_if_empty(conn)
    finally:
        conn.close()


def _ensure_column(conn: sqlite3.Connection, table: str, column: str, ddl: str) -> None:
    """
    幂等补 SQLite 列，兼容已经存在的旧 `data/db.sqlite`。

    :param conn: 当前数据库连接
    :param table: 表名
    :param column: 需要补齐的列名
    :param ddl: `ALTER TABLE ADD COLUMN` 后的列定义
    :return: None
    """
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    if any(r["name"] == column for r in rows):
        return
    conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")


# ============== Topics（SQLite 为主，topics.md 首次 seed）==============
_CAT_RE = re.compile(r"^##\s+[一二三四五六七八九十]+、(.+?)（")
_ITEM_RE = re.compile(r"^-\s+\[[ x]\]\s+(\d+)\.\s+\*\*(.+?)\*\*[:：]?\s*(.*)$")


def load_seed_topics() -> list[dict]:
    """
    从题库 markdown 解析首次 seed 数据。

    :return: topic dict 列表，字段包含 no/category/title/description
    """
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


def _seed_topics_if_empty(conn: sqlite3.Connection) -> None:
    """
    首次启动时把 `topics.md` 导入 SQLite。

    :param conn: 当前数据库连接
    :return: None
    """
    row = conn.execute("SELECT COUNT(*) AS n FROM topics").fetchone()
    if row and row["n"] > 0:
        return
    for topic in load_seed_topics():
        conn.execute(
            "INSERT OR IGNORE INTO topics(no, title, description, category) "
            "VALUES(?,?,?,?)",
            (
                topic["no"],
                topic["title"],
                topic.get("description") or "",
                topic.get("category") or "",
            ),
        )


def list_topic_rows(include_deleted: bool = False) -> list[dict]:
    """
    从 SQLite 读取 topic 列表。

    :param include_deleted: 是否包含软删 topic
    :return: topic dict 列表
    """
    conn = get_db()
    try:
        where = "" if include_deleted else "WHERE deleted_at IS NULL AND enabled=1"
        rows = conn.execute(
            f"SELECT * FROM topics {where} ORDER BY no"
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def build_topic_prompt(topic: dict) -> str:
    """
    按 topic 生成默认 Claude prompt。

    :param topic: topic 行字典
    :return: 默认 prompt 文本
    """
    return (
        f"{topic['title']}：{topic.get('description') or ''}\n\n"
        "请在当前目录下从 0 到 1 实现一个 MVP（功能跑通即可，先不追求架构完美）。"
        "完成后简要总结你做了什么。"
    )


def _format_quota_result(raw: dict) -> dict:
    """
    把 Claude Code statusLine 原始 JSON 转成前端稳定字段。

    :param raw: statusLine 脚本收到的原始 JSON
    :return: 额度展示对象
    """
    rate_limits = raw.get("rate_limits") if isinstance(raw, dict) else None
    if not isinstance(rate_limits, dict):
        return {
            "ok": False,
            "message": raw.get("error") if isinstance(raw, dict) else "rate limits unavailable",
            "five_hour": None,
            "seven_day": None,
            "seven_day_sonnet": None,
            "raw": raw,
        }
    five_hour = rate_limits.get("five_hour") if isinstance(rate_limits.get("five_hour"), dict) else None
    seven_day = rate_limits.get("seven_day") if isinstance(rate_limits.get("seven_day"), dict) else None
    return {
        "ok": True,
        "message": "",
        "five_hour": five_hour,
        "seven_day": seven_day,
        "seven_day_sonnet": None,
        "raw": raw,
    }


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
        (BENCH_DATA / "workspaces" / run_id / ".claude-home").mkdir(parents=True, exist_ok=True)
        (BENCH_DATA / "flows" / acc_name / str(task["id"]) / run_id).mkdir(parents=True, exist_ok=True)
        CA_DIR.mkdir(parents=True, exist_ok=True)
        _persist_default_claude_settings(BENCH_DATA / "profiles" / acc_name)
        _persist_default_claude_top_config(BENCH_DATA / "profiles" / acc_name)
        _make_worker_owned(BENCH_DATA / "workspaces" / run_id)

        host_workspace = HOST_BENCH_DATA / "workspaces" / run_id
        host_claude_home = HOST_BENCH_DATA / "workspaces" / run_id / ".claude-home"
        host_flows = HOST_BENCH_DATA / "flows" / acc_name / str(task["id"]) / run_id
        host_profile = HOST_BENCH_DATA / "profiles" / acc_name
        host_ca = HOST_BENCH_DATA / "ca"

        sidecar_id: Optional[str] = None
        worker_id: Optional[str] = None
        try:
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
            sidecar_id = sidecar.id

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
                    str(host_profile): {"bind": "/mnt/profile", "mode": "rw"},
                    str(host_workspace): {"bind": "/workspace", "mode": "rw"},
                    str(host_claude_home): {"bind": f"{WORKER_HOME}/.claude", "mode": "rw"},
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
            worker_id = worker.id
            return sidecar_id, worker_id
        except Exception:
            # worker 创建失败时 sidecar 已经可能存在；外层拿不到 id，所以这里收口。
            self.cleanup(sidecar_id, worker_id)
            raise

    def persist_worker_profile(self, worker_id: Optional[str]) -> None:
        """
        在停止容器前尽量把运行时凭据回写 profile。

        :param worker_id: worker 容器 ID
        :return: None
        """
        if not worker_id:
            return
        try:
            api = self.client.api
            cmd = (
                "mkdir -p \"$HOME/.claude\"; "
                "cp \"$HOME/.claude.json\" \"$HOME/.claude/.claude.json\" 2>/dev/null || true; "
                "if [ -d /mnt/profile ] && [ -w /mnt/profile ]; then "
                "cp \"$HOME/.claude/.credentials.json\" /mnt/profile/.credentials.json 2>/dev/null || true; "
                "cp \"$HOME/.claude/settings.json\" /mnt/profile/settings.json 2>/dev/null || true; "
                "cp \"$HOME/.claude/.claude.json\" /mnt/profile/.claude.json 2>/dev/null || true; "
                "chown node:node /mnt/profile/.credentials.json /mnt/profile/settings.json /mnt/profile/.claude.json 2>/dev/null || true; "
                "fi"
            )
            ex = api.exec_create(
                worker_id,
                ["sh", "-lc", cmd],
                stdout=True,
                stderr=True,
                environment={"HOME": WORKER_HOME},
                workdir=WORKER_HOME,
            )
            api.exec_start(ex["Id"])
        except Exception:
            # 容器可能已经退出或被删除；停止路径不应被凭据兜底阻断。
            pass

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

    def start_continue(self, sid: str, run: dict, account: dict, session_id: str) -> tuple[str, str]:
        """
        启动一个继续对话容器。

        :param sid: continue session id
        :param run: runs 表行
        :param account: accounts 表行
        :param session_id: Claude session id
        :return: (sidecar_id, worker_id)
        """
        sidecar_name = f"bench-continue-sidecar-{sid}"
        worker_name = f"bench-continue-worker-{sid}"
        acc_name = account["name"]
        fp = derive_fingerprint(acc_name)
        CA_DIR.mkdir(parents=True, exist_ok=True)
        workspace_dir = WORKSPACES_DIR / run["id"]
        claude_home_dir = workspace_dir / ".claude-home"
        profile_dir = PROFILES_DIR / acc_name
        _copy_profile_whitelist_to_claude_home(profile_dir, claude_home_dir)
        top_config = claude_home_dir / ".claude.json"
        if top_config.exists():
            shutil.copy2(top_config, workspace_dir / ".claude.json")
        _make_worker_owned(workspace_dir)

        host_workspace = HOST_BENCH_DATA / "workspaces" / run["id"]
        host_claude_home = HOST_BENCH_DATA / "workspaces" / run["id"] / ".claude-home"
        host_ca = HOST_BENCH_DATA / "ca"

        sidecar_id: Optional[str] = None
        worker_id: Optional[str] = None
        try:
            sidecar = self.client.containers.run(
                SIDECAR_IMAGE,
                name=sidecar_name,
                hostname=fp["hostname"],
                mac_address=fp["mac"],
                detach=True,
                auto_remove=False,
                cap_add=["NET_ADMIN"],
                devices=["/dev/net/tun:/dev/net/tun"],
                volumes={str(host_ca): {"bind": "/ca", "mode": "rw"}},
                environment={
                    "UPSTREAM_SOCKS5_HOST": account.get("upstream_socks5_host") or "",
                    "UPSTREAM_SOCKS5_PORT": str(account.get("upstream_socks5_port") or 1080),
                    "UPSTREAM_SOCKS5_USER": account.get("upstream_socks5_user") or "",
                    "UPSTREAM_SOCKS5_PASS": account.get("upstream_socks5_pass") or "",
                },
            )
            sidecar_id = sidecar.id
            time.sleep(SIDECAR_BOOT_WAIT)
            worker = self.client.containers.run(
                WORKER_IMAGE,
                name=worker_name,
                mem_limit=fp["mem"],
                memswap_limit=fp["mem"],
                detach=True,
                auto_remove=False,
                tty=True,
                stdin_open=True,
                network_mode=f"container:{sidecar_name}",
                volumes={
                    str(host_workspace): {"bind": "/workspace", "mode": "rw"},
                    str(host_claude_home): {"bind": f"{WORKER_HOME}/.claude", "mode": "rw"},
                    str(host_ca): {"bind": "/etc/mitm", "mode": "ro"},
                },
                environment={
                    "WORKER_MODE": "login",
                    "USE_SIDECAR_DNS": "1",
                    "HOME": WORKER_HOME,
                    "ACC_NAME": acc_name,
                    "TZ": fp["tz"],
                    "LANG": fp["lang"],
                    "LC_ALL": fp["lang"],
                    "CONTINUE_SESSION_ID": session_id,
                },
            )
            worker_id = worker.id
            return sidecar_id, worker_id
        except Exception:
            # 继续对话启动失败也要清掉已经起好的半成品容器，避免 run lock 残留。
            self.cleanup(sidecar_id, worker_id)
            raise

    def query_quota(self, account: dict) -> dict:
        """
        用账号 SOCKS5 启动临时 Claude 容器并读取 statusLine rate_limits。

        :param account: accounts 表行
        :return: 额度查询结果
        """
        if not account.get("upstream_socks5_host"):
            raise ValueError("account has no upstream socks5 configured")
        sid = uuid.uuid4().hex[:12]
        sidecar_name = f"bench-quota-sidecar-{sid}"
        worker_name = f"bench-quota-worker-{sid}"
        acc_name = account["name"]
        fp = derive_fingerprint(acc_name)
        temp_run_id = f"quota-{sid}"
        temp_workspace = WORKSPACES_DIR / temp_run_id
        temp_home = temp_workspace / ".claude-home"
        temp_workspace.mkdir(parents=True, exist_ok=True)
        _copy_profile_whitelist_to_claude_home(PROFILES_DIR / acc_name, temp_home)
        top_config = temp_home / ".claude.json"
        if top_config.exists():
            shutil.copy2(top_config, temp_workspace / ".claude.json")
        _make_worker_owned(temp_workspace)
        CA_DIR.mkdir(parents=True, exist_ok=True)

        sidecar_id: Optional[str] = None
        worker_id: Optional[str] = None
        try:
            sidecar = self.client.containers.run(
                SIDECAR_IMAGE,
                name=sidecar_name,
                hostname=fp["hostname"],
                mac_address=fp["mac"],
                detach=True,
                auto_remove=False,
                cap_add=["NET_ADMIN"],
                devices=["/dev/net/tun:/dev/net/tun"],
                volumes={str(HOST_BENCH_DATA / "ca"): {"bind": "/ca", "mode": "rw"}},
                environment={
                    "UPSTREAM_SOCKS5_HOST": account.get("upstream_socks5_host") or "",
                    "UPSTREAM_SOCKS5_PORT": str(account.get("upstream_socks5_port") or 1080),
                    "UPSTREAM_SOCKS5_USER": account.get("upstream_socks5_user") or "",
                    "UPSTREAM_SOCKS5_PASS": account.get("upstream_socks5_pass") or "",
                },
            )
            sidecar_id = sidecar.id
            time.sleep(SIDECAR_BOOT_WAIT)
            worker = self.client.containers.run(
                WORKER_IMAGE,
                name=worker_name,
                mem_limit=fp["mem"],
                memswap_limit=fp["mem"],
                detach=True,
                auto_remove=False,
                tty=True,
                stdin_open=True,
                network_mode=f"container:{sidecar_name}",
                volumes={
                    str(HOST_BENCH_DATA / "workspaces" / temp_run_id): {"bind": "/workspace", "mode": "rw"},
                    str(HOST_BENCH_DATA / "workspaces" / temp_run_id / ".claude-home"): {"bind": f"{WORKER_HOME}/.claude", "mode": "rw"},
                    str(HOST_BENCH_DATA / "ca"): {"bind": "/etc/mitm", "mode": "ro"},
                },
                environment={
                    "WORKER_MODE": "login",
                    "USE_SIDECAR_DNS": "1",
                    "HOME": WORKER_HOME,
                    "ACC_NAME": acc_name,
                    "TZ": fp["tz"],
                    "LANG": fp["lang"],
                    "LC_ALL": fp["lang"],
                },
            )
            worker_id = worker.id
            raw = self._exec_quota_probe(worker_id)
            workspace_top_config = temp_workspace / ".claude.json"
            if workspace_top_config.exists():
                shutil.copy2(workspace_top_config, temp_home / ".claude.json")
            _copy_claude_home_whitelist_to_profile(temp_home, PROFILES_DIR / acc_name)
            return _format_quota_result(raw)
        finally:
            self.cleanup(sidecar_id, worker_id)
            shutil.rmtree(temp_workspace, ignore_errors=True)

    def _exec_quota_probe(self, worker_id: str) -> dict:
        """
        在 quota worker 中运行短 Claude TUI 采集 statusLine JSON。

        :param worker_id: quota worker 容器 ID
        :return: statusLine 原始 JSON，失败时返回 raw/error
        """
        script = r'''
set -eu
if [ -f /workspace/.claude.json ] && [ ! -f "$HOME/.claude.json" ]; then
  cp /workspace/.claude.json "$HOME/.claude.json"
fi
STATUS=/workspace/.bench-quota-status.json
STATUS_SH=/workspace/.bench-quota-status.sh
cat > "$STATUS_SH" <<'EOF'
#!/bin/sh
cat > /workspace/.bench-quota-status.json
exit 0
EOF
chmod +x "$STATUS_SH"
mkdir -p "$HOME/.claude"
if [ -f "$HOME/.claude/settings.json" ]; then
  jq '.statusLine = {"type":"command","command":"/workspace/.bench-quota-status.sh"}' "$HOME/.claude/settings.json" > "$HOME/.claude/settings.json.tmp" && mv "$HOME/.claude/settings.json.tmp" "$HOME/.claude/settings.json"
else
  printf '{"statusLine":{"type":"command","command":"/workspace/.bench-quota-status.sh"}}\n' > "$HOME/.claude/settings.json"
fi
rm -f "$STATUS"
tmux new-session -d -s quota -x 160 -y 45
tmux send-keys -t quota "cd /workspace && env HOME='$HOME' NODE_EXTRA_CA_CERTS=/etc/mitm/mitmproxy-ca-cert.pem SSL_CERT_FILE=/etc/mitm/mitmproxy-ca-cert.pem REQUESTS_CA_BUNDLE=/etc/mitm/mitmproxy-ca-cert.pem CURL_CA_BUNDLE=/etc/mitm/mitmproxy-ca-cert.pem GIT_SSL_CAINFO=/etc/mitm/mitmproxy-ca-cert.pem claude" Enter
sleep 8
tmux send-keys -t quota "Reply with ok." Enter
for i in $(seq 1 45); do
  if [ -s "$STATUS" ] && grep -q "rate_limits" "$STATUS"; then
    break
  fi
  sleep 1
done
tmux capture-pane -t quota -p -S - > /workspace/.bench-quota-transcript.log 2>/dev/null || true
tmux kill-session -t quota 2>/dev/null || true
if [ -s "$STATUS" ]; then
  cat "$STATUS"
else
  printf '{"error":"statusLine did not return rate_limits","transcript":'
  python3 - <<'PY'
import json
from pathlib import Path
print(json.dumps(Path("/workspace/.bench-quota-transcript.log").read_text(errors="ignore")[-4000:]))
PY
  printf '}'
fi
'''
        api = self.client.api
        ex = api.exec_create(
            worker_id,
            ["sh", "-lc", script],
            stdout=True,
            stderr=True,
            user=WORKER_USER,
            environment=_claude_exec_env(True, {"TERM": "xterm-256color"}),
            workdir=WORKER_HOME,
        )
        raw = api.exec_start(ex["Id"])
        text = raw.decode("utf-8", errors="ignore").strip()
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return {"error": "quota probe returned non-json output", "raw": text}


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


class ContinueSession:
    """单个 run 继续对话会话：一对 sidecar+worker + 元数据"""

    __slots__ = ("sid", "run_id", "account_id", "sidecar_id", "worker_id",
                 "session_id", "created_at")

    def __init__(
        self,
        sid: str,
        run_id: str,
        account_id: int,
        sidecar_id: str,
        worker_id: str,
        session_id: str,
    ) -> None:
        self.sid = sid
        self.run_id = run_id
        self.account_id = account_id
        self.sidecar_id = sidecar_id
        self.worker_id = worker_id
        self.session_id = session_id
        self.created_at = time.time()


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
            local_profile = BENCH_DATA / "profiles" / name
            local_profile.mkdir(parents=True, exist_ok=True)
            _persist_default_claude_settings(local_profile)
            _persist_default_claude_top_config(local_profile)
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

            # worker：login 模式，profile 目录直接 rw 挂到 node 用户 HOME。
            # hostname 注入条件:network_mode=container:xxx 时 Docker 拒绝
            # 同时传 hostname(会继承 sidecar 的);只在 bridge 模式自己设。
            # MAC 同样:有 sidecar 时由 sidecar 决定,bridge 模式我们控不了。
            # mem_limit 与 task 模式一致,确保 login 时 Anthropic 看到的
            # constrainedMemory 跟后续 task 时是同一台机器。
            _make_worker_owned(local_profile)
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
                    str(host_profile): {"bind": f"{WORKER_HOME}/.claude", "mode": "rw"},
                    str(host_ca): {"bind": "/etc/mitm", "mode": "ro"},
                },
                "environment": {
                    "WORKER_MODE": "login",
                    "USE_SIDECAR_DNS": "1" if sidecar_id else "0",
                    "HOME": WORKER_HOME,
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
            user=WORKER_USER,
            environment=_claude_exec_env(s.sidecar_id is not None),
            workdir=WORKER_HOME,
        )
        raw = api.exec_start(ex["Id"])
        text = raw.decode("utf-8", errors="ignore").strip()
        # claude auth status 返回 JSON
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return {"raw": text, "loggedIn": False}

    def persist_top_config(self, sid: str) -> None:
        """
        把登录容器内的 $HOME/.claude.json 写回 profile 目录。

        不能把该文件直接 bind mount 到容器内：Claude Code 用临时文件 +
        rename 原子写配置，Docker file bind mount 会让 rename 报 EBUSY。
        """
        s = self.get(sid)
        if not s:
            raise KeyError(sid)
        api = self.client.api
        ex = api.exec_create(
            s.worker_id,
            ["sh", "-lc", "cat \"$HOME/.claude.json\""],
            stdout=True,
            stderr=True,
            user=WORKER_USER,
            environment={"HOME": WORKER_HOME},
            workdir=WORKER_HOME,
        )
        raw = api.exec_start(ex["Id"])
        inspected = api.exec_inspect(ex["Id"])
        if inspected.get("ExitCode") != 0:
            raise ValueError(
                f"failed to read top-level .claude.json: exit "
                f"{inspected.get('ExitCode')}"
            )
        text = raw.decode("utf-8", errors="ignore")
        if not text.strip():
            raise ValueError("top-level .claude.json is empty or missing")
        path = BENCH_DATA / "profiles" / s.name / ".claude.json"
        path.write_text(text, encoding="utf-8")
        _persist_default_claude_top_config(path.parent)
        _make_worker_owned(path)

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


class ContinueManager:
    """管理 runs 的继续对话 PTY 会话"""

    def __init__(self, runner: Runner) -> None:
        self.runner = runner
        self.sessions: dict[str, ContinueSession] = {}
        self._run_locks: dict[str, str] = {}
        self._lock = threading.Lock()

    def cleanup_stale(self) -> None:
        """启动时清掉上次残留的 bench-continue-* 容器"""
        try:
            for c in self.runner.client.containers.list(
                all=True, filters={"name": "bench-continue-"}
            ):
                try:
                    c.remove(force=True)
                except Exception:
                    pass
        except Exception:
            pass

    def start(self, run: dict, account: dict) -> ContinueSession:
        """
        为一个完成 run 启动继续对话会话。

        :param run: runs 表行
        :param account: accounts 表行
        :return: ContinueSession
        """
        session_id = _find_latest_claude_session_id(run["id"])
        if not session_id:
            raise ValueError(f"run {run['id']} has no Claude session jsonl")
        with self._lock:
            if run["id"] in self._run_locks:
                raise ValueError(f"continue session already active for run {run['id']}")
            sid = uuid.uuid4().hex[:12]
            self._run_locks[run["id"]] = sid
        try:
            sidecar_id, worker_id = self.runner.start_continue(sid, run, account, session_id)
            session = ContinueSession(
                sid, run["id"], int(account["id"]), sidecar_id, worker_id, session_id
            )
            with self._lock:
                self.sessions[sid] = session
            return session
        except Exception:
            with self._lock:
                self._run_locks.pop(run["id"], None)
            raise

    def get(self, sid: str) -> Optional[ContinueSession]:
        """按 sid 返回继续对话会话。"""
        return self.sessions.get(sid)

    def cleanup(self, sid: str) -> None:
        """停止并清理继续对话容器，同时尽量回写账号凭据。"""
        with self._lock:
            s = self.sessions.pop(sid, None)
        if not s:
            return
        self.runner.persist_worker_profile(s.worker_id)
        self.runner.cleanup(s.sidecar_id, s.worker_id)
        conn = get_db()
        try:
            row = conn.execute(
                "SELECT name FROM accounts WHERE id=?",
                (s.account_id,),
            ).fetchone()
            if row:
                _copy_claude_home_whitelist_to_profile(
                    WORKSPACES_DIR / s.run_id / ".claude-home",
                    PROFILES_DIR / row["name"],
                )
        finally:
            conn.close()
        workspace_top_config = WORKSPACES_DIR / s.run_id / ".claude.json"
        claude_home_top_config = WORKSPACES_DIR / s.run_id / ".claude-home" / ".claude.json"
        if claude_home_top_config.exists():
            try:
                shutil.copy2(claude_home_top_config, workspace_top_config)
                _make_worker_owned(workspace_top_config)
            except OSError:
                pass
        with self._lock:
            if self._run_locks.get(s.run_id) == sid:
                del self._run_locks[s.run_id]


def _find_latest_claude_session_id(run_id: str) -> Optional[str]:
    """
    从 run workspace 中找到最近的 Claude session jsonl。

    :param run_id: runs.id
    :return: session id，找不到则 None
    """
    base = WORKSPACES_DIR / run_id / ".claude-home" / "projects"
    if not base.exists():
        return None
    files = [p for p in base.rglob("*.jsonl") if p.is_file()]
    if not files:
        return None
    latest = max(files, key=lambda p: p.stat().st_mtime)
    return latest.stem


# ============== 调度器：每账号 Semaphore(2) ==============
class Scheduler:
    def __init__(self, runner: Runner) -> None:
        self.runner = runner
        self._sems: dict[int, threading.Semaphore] = {}
        self._sems_lock = threading.Lock()
        self._batch_threads: dict[int, threading.Thread] = {}
        self._batch_lock = threading.Lock()

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

    def submit_batch(self, batch_id: int) -> None:
        """
        后台启动一个批次调度线程。

        :param batch_id: task_batches.id
        :return: None
        """
        with self._batch_lock:
            t = self._batch_threads.get(batch_id)
            if t and t.is_alive():
                return
            t = threading.Thread(target=self._execute_batch, args=(batch_id,), daemon=True)
            self._batch_threads[batch_id] = t
            t.start()

    def _execute_batch(self, batch_id: int) -> None:
        conn = get_db()
        try:
            batch_row = conn.execute(
                "SELECT * FROM task_batches WHERE id=? AND deleted_at IS NULL",
                (batch_id,),
            ).fetchone()
            if not batch_row:
                return
            account_row = conn.execute(
                "SELECT * FROM accounts WHERE id=?",
                (batch_row["account_id"],),
            ).fetchone()
            if not account_row:
                return
            items = conn.execute(
                "SELECT bi.*, t.no AS topic_no, t.title, t.description "
                "FROM task_batch_items bi JOIN topics t ON bi.topic_id=t.id "
                "WHERE bi.batch_id=? ORDER BY bi.id",
                (batch_id,),
            ).fetchall()
            batch = dict(batch_row)
            account = dict(account_row)
        finally:
            conn.close()

        active_runs: list[str] = []
        for idx, item_row in enumerate(items):
            current = self._get_batch_status(batch_id)
            if current != "active":
                break
            # 先投满并发窗口；之后每次等一个 run 收口再按随机间隔投放下一项。
            if len(active_runs) >= int(batch.get("concurrency") or 2):
                self._wait_any_run_finished(active_runs)
            if idx >= int(batch.get("concurrency") or 2):
                delay = self._random_batch_delay(batch)
                if delay > 0:
                    self._set_batch_next_launch(batch_id, time.time() + delay)
                    time.sleep(delay)
                    if self._get_batch_status(batch_id) != "active":
                        break
            item = dict(item_row)
            run_id = uuid.uuid4().hex[:12]
            task_id = self._create_batch_task_and_run(batch, account, item, run_id)
            task = {
                "id": task_id,
                "prompt": item["prompt"],
                "timeout_sec": batch["timeout_sec"],
                "batch_id": batch_id,
                "topic_id": item["topic_id"],
            }
            self.submit(run_id, account, task)
            active_runs.append(run_id)

        self._wait_all_runs_finished(active_runs)
        self._finish_batch_when_done(batch_id)

    def _create_batch_task_and_run(
        self, batch: dict, account: dict, item: dict, run_id: str
    ) -> int:
        """
        为批次 item 创建兼容旧 runs 的 task + run。

        :param batch: task_batches 行
        :param account: accounts 行
        :param item: task_batch_items 行
        :param run_id: 新 run id
        :return: task id
        """
        with _db_lock:
            conn = get_db()
            try:
                with conn:
                    cur = conn.execute(
                        "INSERT INTO tasks(topic_no, title, prompt, account_id, batch_id, "
                        "topic_id, timeout_sec, repeat_n) VALUES(?,?,?,?,?,?,?,?)",
                        (
                            item["topic_no"],
                            item["title"],
                            item["prompt"],
                            account["id"],
                            batch["id"],
                            item["topic_id"],
                            batch["timeout_sec"],
                            1,
                        ),
                    )
                    task_id = int(cur.lastrowid)
                    conn.execute(
                        "INSERT INTO runs(id, task_id, account_id, batch_id, topic_id, status) "
                        "VALUES(?,?,?,?,?,?)",
                        (run_id, task_id, account["id"], batch["id"], item["topic_id"], "queued"),
                    )
                    conn.execute(
                        "UPDATE task_batch_items SET task_id=?, run_id=?, status='queued', "
                        "updated_at=julianday('now') WHERE id=?",
                        (task_id, run_id, item["id"]),
                    )
                    return task_id
            finally:
                conn.close()

    def _get_batch_status(self, batch_id: int) -> str:
        conn = get_db()
        try:
            row = conn.execute(
                "SELECT status FROM task_batches WHERE id=?",
                (batch_id,),
            ).fetchone()
            return row["status"] if row else "deleted"
        finally:
            conn.close()

    def _random_batch_delay(self, batch: dict) -> int:
        low = max(0, int(batch.get("interval_min_sec") or 0))
        high = max(0, int(batch.get("interval_max_sec") or 0))
        if high < low:
            high = low
        if high <= 0:
            return 0
        return random.randint(low, high)

    def _set_batch_next_launch(self, batch_id: int, next_launch_at: float) -> None:
        with _db_lock:
            conn = get_db()
            try:
                with conn:
                    conn.execute(
                        "UPDATE task_batches SET next_launch_at=?, updated_at=julianday('now') WHERE id=?",
                        (next_launch_at, batch_id),
                    )
            finally:
                conn.close()

    def _finish_batch_when_done(self, batch_id: int) -> None:
        with _db_lock:
            conn = get_db()
            try:
                with conn:
                    row = conn.execute(
                        "SELECT COUNT(*) AS n FROM task_batch_items "
                        "WHERE batch_id=? AND status IN ('pending','queued','running')",
                        (batch_id,),
                    ).fetchone()
                    status = "done" if row and row["n"] == 0 else "active"
                    conn.execute(
                        "UPDATE task_batches SET status=?, next_launch_at=NULL, "
                        "updated_at=julianday('now') WHERE id=? AND status='active'",
                        (status, batch_id),
                    )
            finally:
                conn.close()

    def _wait_any_run_finished(self, run_ids: list[str]) -> None:
        """
        等待活跃 run 列表里至少一个结束，并原地移除已结束项。

        :param run_ids: 活跃 run id 列表
        :return: None
        """
        while run_ids:
            statuses = self._get_run_statuses(run_ids)
            done = [rid for rid in run_ids if statuses.get(rid) in _TERMINAL_RUN_STATUSES]
            if done:
                for rid in done:
                    run_ids.remove(rid)
                return
            time.sleep(2)

    def _wait_all_runs_finished(self, run_ids: list[str]) -> None:
        """
        等待批次投放出的所有 run 结束。

        :param run_ids: run id 列表
        :return: None
        """
        while run_ids:
            self._wait_any_run_finished(run_ids)

    def _get_run_statuses(self, run_ids: list[str]) -> dict[str, str]:
        if not run_ids:
            return {}
        placeholders = ",".join("?" for _ in run_ids)
        conn = get_db()
        try:
            rows = conn.execute(
                f"SELECT id, status FROM runs WHERE id IN ({placeholders})",
                run_ids,
            ).fetchall()
            return {r["id"]: r["status"] for r in rows}
        finally:
            conn.close()

    def _execute(self, run_id: str, account: dict, task: dict) -> None:
        sem = self._sem(account["id"])
        sem.acquire()
        sid: Optional[str] = None
        wid: Optional[str] = None
        try:
            initial_state = self._get_run_state(run_id)
            if not initial_state or initial_state.get("deleted_at") is not None:
                return
            if initial_state["status"] in ("stopping", "stopped"):
                self._update_batch_item_for_run(run_id, "stopped")
                return
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
                run_state = self._get_run_state(run_id)
                if run_state and run_state["status"] in ("stopping", "stopped"):
                    self.runner.persist_worker_profile(wid)
                    self.runner.cleanup(sid, wid)
                    self._update(run_id, status="stopped", ended_at=time.time())
                    self._update_batch_item_for_run(run_id, "stopped")
                    return
                exit_code = self.runner.wait_worker(wid)
                run_state = self._get_run_state(run_id)
                if run_state and run_state["status"] in ("stopping", "stopped"):
                    status = "stopped"
                elif exit_code == 0:
                    status = "success"
                elif exit_code == 124:
                    status = "timeout"
                else:
                    status = "failed"
                self._update(run_id, status=status, exit_code=exit_code, ended_at=time.time())
                self._update_batch_item_for_run(run_id, status)
            except Exception as e:
                run_state = self._get_run_state(run_id)
                status = "stopped" if run_state and run_state["status"] in ("stopping", "stopped") else "failed"
                self._update(run_id, status=status, error=str(e), ended_at=time.time())
                self._update_batch_item_for_run(run_id, status)
            finally:
                self.runner.persist_worker_profile(wid)
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

    def _get_run_state(self, run_id: str) -> Optional[dict]:
        conn = get_db()
        try:
            row = conn.execute(
                "SELECT status, deleted_at FROM runs WHERE id=?",
                (run_id,),
            ).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def _update_batch_item_for_run(self, run_id: str, status: str) -> None:
        with _db_lock:
            conn = get_db()
            try:
                with conn:
                    conn.execute(
                        "UPDATE task_batch_items SET status=?, updated_at=julianday('now') "
                        "WHERE run_id=?",
                        (status, run_id),
                    )
            finally:
                conn.close()


# ============== FastAPI ==============
runner: Optional[Runner] = None
scheduler: Optional[Scheduler] = None
login_manager: Optional[LoginManager] = None
continue_manager: Optional[ContinueManager] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global runner, scheduler, login_manager, continue_manager
    init_db()
    PROFILES_DIR.mkdir(parents=True, exist_ok=True)
    FLOWS_DIR.mkdir(parents=True, exist_ok=True)
    WORKSPACES_DIR.mkdir(parents=True, exist_ok=True)
    CA_DIR.mkdir(parents=True, exist_ok=True)
    runner = Runner()
    scheduler = Scheduler(runner)
    login_manager = LoginManager(runner.client)
    continue_manager = ContinueManager(runner)
    # 清掉上次进程残留的 login 容器，避免重启后僵尸容器堆积
    login_manager.cleanup_stale()
    continue_manager.cleanup_stale()
    yield


app = FastAPI(title="vibecoding-100 bench", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ===== Cookie-Session 鉴权工具 + 中间件 =====
def _make_session_token(user: str) -> str:
    """
    生成签名 session token: base64url("user|exp_ts|hmac_sha256(user|exp_ts)")
    用 HMAC-SHA256 + _SESSION_SECRET 防伪造;不存 server 状态,scale 友好。
    """
    exp = int(time.time()) + _SESSION_TTL
    payload = f"{user}|{exp}"
    sig = hmac.new(
        _SESSION_SECRET.encode(), payload.encode(), hashlib.sha256
    ).hexdigest()
    raw = f"{payload}|{sig}".encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _verify_session_token(token: str) -> Optional[str]:
    """合法返回用户名,非法/过期返回 None"""
    if not token:
        return None
    try:
        # 补回 base64 padding
        padded = token + "=" * (-len(token) % 4)
        raw = base64.urlsafe_b64decode(padded).decode("utf-8")
        user, exp_str, sig = raw.split("|")
        if int(exp_str) < int(time.time()):
            return None
        expected = hmac.new(
            _SESSION_SECRET.encode(),
            f"{user}|{exp_str}".encode(),
            hashlib.sha256,
        ).hexdigest()
        if not secrets.compare_digest(sig, expected):
            return None
        # 进一步校验 user 与当前配置一致(env 改了密码后旧 token 立失效)
        if not secrets.compare_digest(user, WEBUI_USER):
            return None
        return user
    except Exception:
        return None


@app.middleware("http")
async def session_auth_middleware(request, call_next):
    """
    Cookie-Session 鉴权中间件。
    - WEBUI_USER/PASS 未设 → 完全旁路
    - 鉴权范围:仅 /api/*,且豁免 /api/auth/*(login/logout/me 必须可达)
    - 非 API 路径(静态 HTML/CSS/JS)放行 —— 否则首次访问连登录页都看不到
    - WebSocket(starlette scope=websocket)不经此中间件,由路由 sid 间接保护
    """
    if not _AUTH_ENABLED:
        return await call_next(request)
    path = request.url.path
    if not path.startswith("/api/") or path.startswith("/api/auth/"):
        return await call_next(request)
    token = request.cookies.get(_SESSION_COOKIE, "")
    if not _verify_session_token(token):
        return JSONResponse(status_code=401, content={"detail": "auth required"})
    return await call_next(request)


class AuthIn(BaseModel):
    user: str
    pwd: str


@app.post("/api/auth/login")
def auth_login(body: AuthIn, response: Response):
    """校验账密 → 签发 session cookie(7 天)。auth 未启用时 400。"""
    if not _AUTH_ENABLED:
        raise HTTPException(400, "auth not configured on server")
    u_ok = secrets.compare_digest(body.user, WEBUI_USER)
    p_ok = secrets.compare_digest(body.pwd, WEBUI_PASS)
    if not (u_ok and p_ok):
        # 故意不细分用户名/密码错(防爆破做用户名枚举)
        raise HTTPException(401, "invalid credentials")
    token = _make_session_token(body.user)
    response.set_cookie(
        _SESSION_COOKIE,
        token,
        max_age=_SESSION_TTL,
        httponly=True,
        samesite="lax",
        # Secure 在 HTTPS 部署时应开;HTTP 部署强制开会让浏览器丢弃 cookie
        secure=False,
    )
    return {"ok": True, "user": body.user}


@app.post("/api/auth/logout")
def auth_logout(response: Response):
    """清 session cookie,幂等。"""
    response.delete_cookie(_SESSION_COOKIE)
    return {"ok": True}


@app.get("/api/auth/me")
def auth_me(request: Request):
    """
    返回当前鉴权状态。前端启动时调一次决定要不要弹登录框。
    - auth 未启用: {authenticated: true, user: null, auth_required: false}
    - 已登录:     {authenticated: true, user: "<name>", auth_required: true}
    - 未登录:     401
    """
    if not _AUTH_ENABLED:
        return {"authenticated": True, "user": None, "auth_required": False}
    token = request.cookies.get(_SESSION_COOKIE, "")
    user = _verify_session_token(token)
    if not user:
        raise HTTPException(401, "not authenticated")
    return {"authenticated": True, "user": user, "auth_required": True}


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


@app.post("/api/accounts/{aid}/quota")
def query_account_quota(aid: int):
    """按账号 SOCKS5 查询 Claude Code 额度。"""
    if not runner:
        raise HTTPException(500, "runner not ready")
    conn = get_db()
    try:
        row = conn.execute("SELECT * FROM accounts WHERE id=?", (aid,)).fetchone()
        if not row:
            raise HTTPException(404, "account not found")
        account = dict(row)
    finally:
        conn.close()
    try:
        return runner.query_quota(account)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(500, f"quota query failed: {e}")


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
            user=WORKER_USER,
            environment=_claude_exec_env(session.sidecar_id is not None, {
                "TERM": "xterm-256color",
                "COLUMNS": "120",
                "LINES": "36",
            }),
            workdir=WORKER_HOME,
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

    try:
        login_manager.persist_top_config(sid)
    except Exception as e:
        raise HTTPException(500, f"failed to persist top-level claude config: {e}")

    _persist_default_claude_settings(BENCH_DATA / "profiles" / name)
    _persist_default_claude_top_config(BENCH_DATA / "profiles" / name)

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
class TopicIn(BaseModel):
    """创建或更新 topic 的请求体"""

    no: int
    title: str
    description: str = ""
    category: str = ""
    enabled: bool = True


@app.get("/api/topics")
def list_topics():
    """列出未删除 topic。"""
    return list_topic_rows()


@app.post("/api/topics")
def create_topic(body: TopicIn):
    """新增一个 topic，持久化到 SQLite。"""
    with _db_lock:
        conn = get_db()
        try:
            with conn:
                cur = conn.execute(
                    "INSERT INTO topics(no, title, description, category, enabled) "
                    "VALUES(?,?,?,?,?)",
                    (
                        body.no,
                        body.title.strip(),
                        body.description.strip(),
                        body.category.strip(),
                        int(body.enabled),
                    ),
                )
                return {"id": cur.lastrowid}
        except sqlite3.IntegrityError as e:
            raise HTTPException(400, f"topic exists: {e}")
        finally:
            conn.close()


@app.put("/api/topics/{topic_id}")
def update_topic(topic_id: int, body: TopicIn):
    """更新 topic 基本信息。"""
    with _db_lock:
        conn = get_db()
        try:
            with conn:
                cur = conn.execute(
                    "UPDATE topics SET no=?, title=?, description=?, category=?, enabled=?, "
                    "updated_at=julianday('now') WHERE id=? AND deleted_at IS NULL",
                    (
                        body.no,
                        body.title.strip(),
                        body.description.strip(),
                        body.category.strip(),
                        int(body.enabled),
                        topic_id,
                    ),
                )
                if cur.rowcount == 0:
                    raise HTTPException(404, "topic not found")
        finally:
            conn.close()
    return {"ok": True}


@app.delete("/api/topics/{topic_id}")
def delete_topic(topic_id: int):
    """软删除 topic，保留历史 task/run 引用。"""
    with _db_lock:
        conn = get_db()
        try:
            with conn:
                cur = conn.execute(
                    "UPDATE topics SET deleted_at=?, enabled=0, updated_at=julianday('now') "
                    "WHERE id=? AND deleted_at IS NULL",
                    (time.time(), topic_id),
                )
                if cur.rowcount == 0:
                    raise HTTPException(404, "topic not found")
        finally:
            conn.close()
    return {"ok": True}


# ---------- tasks ----------
class TaskIn(BaseModel):
    topic_no: int
    account_id: int
    prompt: Optional[str] = None
    timeout_sec: int = 1800
    repeat_n: int = 1


class BatchIn(BaseModel):
    """按账号批量调度 topic 的请求体"""

    account_id: int
    topic_ids: list[int]
    prompt: Optional[str] = None
    concurrency: int = 2
    interval_min_sec: int = 0
    interval_max_sec: int = 0
    timeout_sec: int = 1800


@app.post("/api/tasks")
def create_task(body: TaskIn):
    conn = get_db()
    try:
        topic_row = conn.execute(
            "SELECT * FROM topics WHERE no=? AND deleted_at IS NULL",
            (body.topic_no,),
        ).fetchone()
        if not topic_row:
            raise HTTPException(404, f"topic {body.topic_no} not found")
        topic = dict(topic_row)
    finally:
        conn.close()
    prompt = body.prompt or build_topic_prompt(topic)
    with _db_lock:
        conn = get_db()
        try:
            with conn:
                cur = conn.execute(
                    "INSERT INTO tasks(topic_no, title, prompt, account_id, topic_id, timeout_sec, repeat_n) "
                    "VALUES(?,?,?,?,?,?,?)",
                    (
                        body.topic_no,
                        topic["title"],
                        prompt,
                        body.account_id,
                        topic["id"],
                        body.timeout_sec,
                        body.repeat_n,
                    ),
                )
                return {"id": cur.lastrowid}
        finally:
            conn.close()


@app.get("/api/tasks")
def list_tasks():
    conn = get_db()
    try:
        rows = conn.execute(
            "SELECT * FROM tasks WHERE deleted_at IS NULL ORDER BY id DESC"
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


@app.delete("/api/tasks/{tid}")
def delete_task(tid: int):
    """软删除旧 task 定义，历史 runs 保留。"""
    with _db_lock:
        conn = get_db()
        try:
            with conn:
                cur = conn.execute(
                    "UPDATE tasks SET deleted_at=?, status='deleted' WHERE id=? AND deleted_at IS NULL",
                    (time.time(), tid),
                )
                if cur.rowcount == 0:
                    raise HTTPException(404, "task not found")
        finally:
            conn.close()
    return {"ok": True}


@app.post("/api/task-batches")
def create_task_batch(body: BatchIn):
    """创建账号维度 topic 批次，并启动后台随机间隔调度。"""
    if not scheduler:
        raise HTTPException(500, "scheduler not ready")
    topic_ids = [int(tid) for tid in body.topic_ids if int(tid) > 0]
    if not topic_ids:
        raise HTTPException(400, "topic_ids required")
    concurrency = max(1, min(2, int(body.concurrency or 2)))
    interval_min = max(0, int(body.interval_min_sec or 0))
    interval_max = max(0, int(body.interval_max_sec or 0))
    if interval_max < interval_min:
        raise HTTPException(400, "interval_max_sec must be >= interval_min_sec")
    conn = get_db()
    try:
        account = conn.execute(
            "SELECT * FROM accounts WHERE id=?",
            (body.account_id,),
        ).fetchone()
        if not account:
            raise HTTPException(404, "account not found")
        placeholders = ",".join("?" for _ in topic_ids)
        topics = conn.execute(
            f"SELECT * FROM topics WHERE id IN ({placeholders}) AND deleted_at IS NULL",
            topic_ids,
        ).fetchall()
        if len(topics) != len(set(topic_ids)):
            raise HTTPException(404, "one or more topics not found")
    finally:
        conn.close()
    name = f"batch acc#{body.account_id} · {len(topic_ids)} topics"
    with _db_lock:
        conn = get_db()
        try:
            with conn:
                cur = conn.execute(
                    "INSERT INTO task_batches(account_id, name, concurrency, interval_min_sec, "
                    "interval_max_sec, timeout_sec) VALUES(?,?,?,?,?,?)",
                    (
                        body.account_id,
                        name,
                        concurrency,
                        interval_min,
                        interval_max,
                        max(60, int(body.timeout_sec or 1800)),
                    ),
                )
                batch_id = int(cur.lastrowid)
                for topic_row in topics:
                    topic = dict(topic_row)
                    prompt = body.prompt or build_topic_prompt(topic)
                    conn.execute(
                        "INSERT INTO task_batch_items(batch_id, topic_id, prompt) VALUES(?,?,?)",
                        (batch_id, topic["id"], prompt),
                    )
        finally:
            conn.close()
    scheduler.submit_batch(batch_id)
    return {"id": batch_id}


@app.get("/api/task-batches")
def list_task_batches():
    """列出未删除批次及其 item 统计。"""
    conn = get_db()
    try:
        rows = conn.execute(
            "SELECT b.*, "
            "(SELECT COUNT(*) FROM task_batch_items i WHERE i.batch_id=b.id) AS item_count, "
            "(SELECT COUNT(*) FROM task_batch_items i WHERE i.batch_id=b.id AND i.status IN ('success','failed','timeout','stopped')) AS done_count "
            "FROM task_batches b WHERE b.deleted_at IS NULL ORDER BY b.id DESC"
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


@app.delete("/api/task-batches/{batch_id}")
def delete_task_batch(batch_id: int):
    """软删除批次；已产生的 run 和磁盘产物保留。"""
    with _db_lock:
        conn = get_db()
        try:
            with conn:
                cur = conn.execute(
                    "UPDATE task_batches SET deleted_at=?, status='deleted', "
                    "updated_at=julianday('now') WHERE id=? AND deleted_at IS NULL",
                    (time.time(), batch_id),
                )
                if cur.rowcount == 0:
                    raise HTTPException(404, "batch not found")
        finally:
            conn.close()
    return {"ok": True}


# ---------- runs ----------
@app.post("/api/tasks/{tid}/run")
def run_task(tid: int):
    conn = get_db()
    try:
        task_row = conn.execute(
            "SELECT * FROM tasks WHERE id=? AND deleted_at IS NULL",
            (tid,),
        ).fetchone()
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
                        "INSERT INTO runs(id, task_id, account_id, batch_id, topic_id, status) "
                        "VALUES(?,?,?,?,?,?)",
                        (
                            rid,
                            tid,
                            account["id"],
                            task.get("batch_id"),
                            task.get("topic_id"),
                            "queued",
                        ),
                    )
            finally:
                conn.close()
        if not scheduler:
            raise HTTPException(500, "scheduler not ready")
        scheduler.submit(rid, account, task)
        run_ids.append(rid)
    return {"run_ids": run_ids}


@app.get("/api/runs")
def list_runs(limit: int = 200):
    conn = get_db()
    try:
        rows = conn.execute(
            "SELECT * FROM runs WHERE deleted_at IS NULL "
            "ORDER BY (started_at IS NULL), started_at DESC, created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


@app.get("/api/runs/{rid}")
def get_run(rid: str):
    conn = get_db()
    try:
        row = conn.execute(
            "SELECT * FROM runs WHERE id=? AND deleted_at IS NULL",
            (rid,),
        ).fetchone()
        if not row:
            raise HTTPException(404)
        return dict(row)
    finally:
        conn.close()


@app.get("/api/runs/{rid}/transcript")
def get_transcript(rid: str):
    _require_visible_run(rid)
    p = WORKSPACES_DIR / rid / ".bench-transcript.log"
    if not p.exists():
        raise HTTPException(404, "transcript not yet available")
    return FileResponse(p, media_type="text/plain")


@app.get("/api/runs/{rid}/files")
def list_workspace(rid: str):
    _require_visible_run(rid)
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
    _require_visible_run(rid)
    base = FLOWS_DIR
    # flows 目录按 account/task/run 分层，扫描所有匹配
    matches = list(base.rglob(f"{rid}/stats.jsonl"))
    if not matches:
        return {"tokens_in": 0, "tokens_out": 0, "requests": 0, "errors": 0}
    tokens_in = tokens_out = errors = 0
    request_ids: set[str] = set()
    response_ids: set[str] = set()
    fallback_requests = 0
    for f in matches:
        for line in f.read_text(encoding="utf-8", errors="ignore").splitlines():
            try:
                rec = json.loads(line)
            except Exception:
                continue
            if "error" in rec:
                errors += 1
                continue
            if rec.get("phase") == "request":
                flow_id = rec.get("flow_id")
                if flow_id:
                    request_ids.add(str(flow_id))
                else:
                    fallback_requests += 1
                continue
            if rec.get("phase") and rec.get("phase") != "response":
                continue
            flow_id = rec.get("flow_id")
            if flow_id:
                response_ids.add(str(flow_id))
            else:
                fallback_requests += 1
            u = rec.get("usage") or {}
            tokens_in += int(u.get("input_tokens") or 0)
            tokens_out += int(u.get("output_tokens") or 0)
    requests = len(request_ids | response_ids) + fallback_requests
    return {"tokens_in": tokens_in, "tokens_out": tokens_out, "requests": requests, "errors": errors}


@app.post("/api/runs/{rid}/stop")
def stop_run(rid: str):
    """请求停止 queued/running run，并尽量先回写运行时凭据。"""
    if not runner:
        raise HTTPException(500, "runner not ready")
    conn = get_db()
    try:
        row = conn.execute(
            "SELECT * FROM runs WHERE id=? AND deleted_at IS NULL",
            (rid,),
        ).fetchone()
        if not row:
            raise HTTPException(404, "run not found")
        run = dict(row)
    finally:
        conn.close()
    if run["status"] not in ("queued", "running"):
        raise HTTPException(400, f"run {rid} is not queued/running")
    runner.persist_worker_profile(run.get("worker_container"))
    with _db_lock:
        conn = get_db()
        try:
            with conn:
                conn.execute(
                    "UPDATE runs SET status='stopping', stop_requested_at=? WHERE id=?",
                    (time.time(), rid),
                )
        finally:
            conn.close()
    runner.cleanup(run.get("sidecar_container"), run.get("worker_container"))
    with _db_lock:
        conn = get_db()
        try:
            with conn:
                row = conn.execute("SELECT status FROM runs WHERE id=?", (rid,)).fetchone()
                if row and row["status"] == "stopping":
                    conn.execute(
                        "UPDATE runs SET status='stopped', ended_at=? WHERE id=?",
                        (time.time(), rid),
                    )
        finally:
            conn.close()
    return {"ok": True}


@app.delete("/api/runs/{rid}")
def delete_run(rid: str):
    """软删除 run；workspace/flow/transcript 保留。"""
    with _db_lock:
        conn = get_db()
        try:
            with conn:
                cur = conn.execute(
                    "UPDATE runs SET deleted_at=? WHERE id=? AND deleted_at IS NULL",
                    (time.time(), rid),
                )
                if cur.rowcount == 0:
                    raise HTTPException(404, "run not found")
        finally:
            conn.close()
    return {"ok": True}


@app.post("/api/runs/{rid}/continue/start")
def continue_run_start(rid: str):
    """启动 run 继续对话会话；前端随后连接返回的 WebSocket。"""
    if not continue_manager:
        raise HTTPException(500, "continue manager not ready")
    conn = get_db()
    try:
        run_row = conn.execute(
            "SELECT * FROM runs WHERE id=? AND deleted_at IS NULL",
            (rid,),
        ).fetchone()
        if not run_row:
            raise HTTPException(404, "run not found")
        run = dict(run_row)
        if run["status"] not in _TERMINAL_RUN_STATUSES:
            raise HTTPException(400, f"run {rid} is not completed")
        account_row = conn.execute(
            "SELECT * FROM accounts WHERE id=?",
            (run["account_id"],),
        ).fetchone()
        if not account_row:
            raise HTTPException(404, "account not found")
        account = dict(account_row)
    finally:
        conn.close()
    try:
        session = continue_manager.start(run, account)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(500, f"failed to start continue session: {e}")
    return {
        "session_id": session.sid,
        "run_id": session.run_id,
        "claude_session_id": session.session_id,
        "ws_path": f"/api/run-continue/ws/{session.sid}",
    }


@app.websocket("/api/run-continue/ws/{sid}")
async def continue_run_ws(websocket: WebSocket, sid: str):
    """PTY 桥：把 `claude --resume <session>` 双向接到浏览器 xterm。"""
    await websocket.accept()
    if not continue_manager:
        await websocket.close(code=4500)
        return
    session = continue_manager.get(sid)
    if not session:
        await websocket.send_text(json.dumps(
            {"type": "error", "msg": "session not found"}))
        await websocket.close(code=4004)
        return

    api = continue_manager.runner.client.api
    try:
        exec_id = api.exec_create(
            session.worker_id,
            [
                "sh",
                "-lc",
                "if [ -f /workspace/.claude.json ] && [ ! -f \"$HOME/.claude.json\" ]; then "
                "cp /workspace/.claude.json \"$HOME/.claude.json\"; fi; "
                "claude --resume \"$CONTINUE_SESSION_ID\"",
            ],
            stdin=True,
            tty=True,
            user=WORKER_USER,
            environment=_claude_exec_env(True, {
                "TERM": "xterm-256color",
                "COLUMNS": "120",
                "LINES": "36",
                "CONTINUE_SESSION_ID": session.session_id,
            }),
            workdir="/workspace",
        )["Id"]
        sock = api.exec_start(
            exec_id, detach=False, tty=True,
            stream=False, socket=True, demux=False,
        )
    except Exception as e:
        await websocket.send_text(json.dumps(
            {"type": "error", "msg": f"exec failed: {e}"}))
        await websocket.close(code=4500)
        continue_manager.cleanup(sid)
        return

    raw = getattr(sock, "_sock", None) or sock
    try:
        raw.setblocking(False)
    except Exception:
        pass

    loop = asyncio.get_event_loop()
    closed = asyncio.Event()

    async def pump_container_to_ws():
        """worker PTY → ws"""
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
        """ws → worker PTY"""
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
        await asyncio.gather(pump_container_to_ws(), pump_ws_to_container())
    finally:
        try:
            raw.close()
        except Exception:
            pass
        continue_manager.cleanup(sid)
        if websocket.client_state == WebSocketState.CONNECTED:
            try:
                await websocket.close()
            except Exception:
                pass


@app.delete("/api/run-continue/{sid}")
def continue_run_cancel(sid: str):
    """关闭继续对话 session，并回写可能刷新的凭据。"""
    if continue_manager:
        continue_manager.cleanup(sid)
    return {"ok": True}


def _require_visible_run(rid: str) -> None:
    """
    确保 run 未被软删。

    :param rid: runs.id
    :return: None
    """
    conn = get_db()
    try:
        row = conn.execute(
            "SELECT id FROM runs WHERE id=? AND deleted_at IS NULL",
            (rid,),
        ).fetchone()
        if not row:
            raise HTTPException(404, "run not found")
    finally:
        conn.close()


# ---------- SSE：推送 runs 列表 ----------
@app.get("/api/runs-stream")
async def stream_runs():
    async def gen():
        last_payload = ""
        while True:
            conn = get_db()
            try:
                rows = conn.execute(
                    "SELECT * FROM runs WHERE deleted_at IS NULL "
                    "ORDER BY (started_at IS NULL), started_at DESC, created_at DESC LIMIT 100"
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
