"""
vibecoding bench · Orchestrator

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
import shlex
import sqlite3
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from collections import deque
from contextlib import ExitStack, asynccontextmanager, contextmanager
from pathlib import Path
from typing import Literal, Optional, Sequence

import docker
from docker.errors import NotFound
from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, StrictInt, StrictStr, ValidationError
from sse_starlette.sse import EventSourceResponse
from starlette.websockets import WebSocketState

from quota_protocol import merge_quota_observation, quota_decision, quota_observation, quota_timestamp, warmup_quota_decision, warmup_sample_used
from account_runtime import AccountRuntime, RuntimeBusy, V3_DEFAULT_TIMEZONE, atomic_json, derive_v3_fingerprint
from cli_quota import statusline_quota_observation
from login_terminal import authorization_url
from login_drafts import LoginDraftStore


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
V3_ENABLED = bool(os.environ.get("V3_DEPLOYMENT_ID"))
PER_ACCOUNT_CONCURRENCY = 1 if V3_ENABLED else int(os.environ.get("PER_ACCOUNT_CONCURRENCY", "2"))
SIDECAR_READY_TIMEOUT = float(os.environ.get("SIDECAR_READY_TIMEOUT", "120"))
DNS_READY_HOST = os.environ.get("DNS_READY_HOST", "example.com")
_SIDECAR_DNS_READY_SH = (
    "grep -q '^nameserver 127[.]0[.]0[.]1' /etc/resolv.conf "
    "&& dig @127.0.0.1 \"$DNS_READY_HOST\" A +time=3 +tries=1 +short "
    "2>/dev/null | grep -q ."
)
_CLAUDE_MODEL_OVERRIDE_RE = re.compile(r"^[A-Za-z0-9._\-\[\]]+$")
_CLAUDE_CODE_VERSION_RE = re.compile(r"^[0-9]+[.][0-9]+[.][0-9]+(?:[-+][A-Za-z0-9._-]+)?$")
_RUNTIME_MODEL_SETTING_KEY = "claude_default_model"
_RUNTIME_EFFORT_SETTING_KEY = "claude_effort_level"
_RUNTIME_CLAUDE_CODE_VERSION_SETTING_KEY = "claude_code_version"
_CLAUDE_EFFORT_LEVELS = ("max", "xhigh", "high", "medium", "low")
_UPSTREAM_PROXY_SCHEMES = ("http", "socks5", "socks5h")
CC2API_BASE_URL = os.environ.get("CC2API_BASE_URL", "").strip().rstrip("/")
CC2API_ADMIN_PASSWORD = os.environ.get("CC2API_ADMIN_PASSWORD", "")
CC2API_REQUEST_TIMEOUT_SEC = float(os.environ.get("CC2API_REQUEST_TIMEOUT_SEC", "15"))
WARMUP_SCHEDULER_TICK_SEC = float(os.environ.get("WARMUP_SCHEDULER_TICK_SEC", "30"))
WARMUP_SYNC_RETRY_SEC = int(os.environ.get("WARMUP_SYNC_RETRY_SEC", "900"))
_CC2API_SECRET_RE = re.compile(r"(?:sk|ant)-[A-Za-z0-9_\-]{12,}")


def _normalize_claude_model_name(value: Optional[str], field_name: str) -> Optional[str]:
    """
    规范化 Claude Code 模型名，供环境配置和一次性 run 覆盖复用。

    :param value: 原始模型名
    :param field_name: 错误消息中展示的字段名
    :return: trim 后的模型名；空值返回 None
    """
    if value is None:
        return None
    model = value.strip()
    if not model:
        return None
    if len(model) > 128:
        raise ValueError(f"{field_name} 过长：最多 128 个字符")
    if not _CLAUDE_MODEL_OVERRIDE_RE.match(model):
        raise ValueError(
            f"{field_name} 包含非法字符：只允许字母、数字、点、下划线、短横线和 []"
        )
    return model


def _normalize_claude_effort_level(value: Optional[str], field_name: str) -> Optional[str]:
    """
    规范化 Claude Code 思考预算值。

    :param value: 原始思考预算值
    :param field_name: 错误消息中展示的字段名
    :return: 规范化后的枚举值；空值返回 None
    """
    if value is None:
        return None
    effort = value.strip().lower()
    if not effort:
        return None
    if effort not in _CLAUDE_EFFORT_LEVELS:
        allowed = ", ".join(_CLAUDE_EFFORT_LEVELS)
        raise ValueError(f"{field_name} 无效：只允许 {allowed}")
    return effort


def _normalize_claude_code_version(value: Optional[str], field_name: str) -> Optional[str]:
    """
    规范化 Claude Code CLI 版本号。

    :param value: 原始版本号
    :param field_name: 错误消息中展示的字段名
    :return: trim 后的版本号；空值返回 None
    """
    if value is None:
        return None
    version = value.strip()
    if not version:
        return None
    if len(version) > 64:
        raise ValueError(f"{field_name} 过长：最多 64 个字符")
    if not _CLAUDE_CODE_VERSION_RE.match(version):
        raise ValueError(
            f"{field_name} 无效：必须类似 2.1.195，只允许语义版本号和 -/+ 后缀"
        )
    return version


def _normalize_upstream_proxy_scheme(value: Optional[str]) -> str:
    """
    规范化账号上游代理协议。

    :param value: 原始代理协议
    :return: 规范化后的协议；空值返回兼容旧账号的 socks5
    """
    if value is None:
        return "socks5"
    scheme = value.strip().lower()
    if not scheme:
        return "socks5"
    if scheme not in _UPSTREAM_PROXY_SCHEMES:
        allowed = ", ".join(_UPSTREAM_PROXY_SCHEMES)
        raise ValueError(f"upstream_proxy_scheme 无效：只允许 {allowed}")
    return scheme


def _sidecar_proxy_env(proxy: dict) -> dict[str, str]:
    """
    生成 sidecar 上游代理环境变量，保留历史 SOCKS5 变量名以兼容脚本入口。

    :param proxy: accounts 表行或登录会话代理配置
    :return: sidecar 可直接使用的代理环境变量
    """
    scheme = _normalize_upstream_proxy_scheme(
        proxy.get("upstream_proxy_scheme") or proxy.get("scheme")
    )
    return {
        "UPSTREAM_PROXY_SCHEME": scheme,
        "UPSTREAM_SOCKS5_HOST": proxy.get("upstream_socks5_host") or proxy.get("host") or "",
        "UPSTREAM_SOCKS5_PORT": str(
            proxy.get("upstream_socks5_port") or proxy.get("port") or 1080
        ),
        "UPSTREAM_SOCKS5_USER": proxy.get("upstream_socks5_user") or proxy.get("user") or "",
        "UPSTREAM_SOCKS5_PASS": proxy.get("upstream_socks5_pass") or proxy.get("pass") or "",
    }


WORKER_USER = "node"
WORKER_HOME = "/home/node"
WORKER_UID = 1000
WORKER_GID = 1000
CLAUDE_CODE_VERSION = _normalize_claude_code_version(
    os.environ.get("CLAUDE_CODE_VERSION") or "2.1.280",
    "CLAUDE_CODE_VERSION",
) or "2.1.280"
CLAUDE_CODE_EFFORT_LEVEL = _normalize_claude_effort_level(
    os.environ.get("CLAUDE_CODE_EFFORT_LEVEL") or "max",
    "CLAUDE_CODE_EFFORT_LEVEL",
) or "max"
CLAUDE_DEFAULT_MODEL = _normalize_claude_model_name(
    os.environ.get("CLAUDE_DEFAULT_MODEL") or "opus[1m]",
    "CLAUDE_DEFAULT_MODEL",
) or "opus[1m]"
SAVE_FULL_FLOWS = os.environ.get("SAVE_FULL_FLOWS", "0")
CLEAN_WORKSPACE_DEPS = os.environ.get("CLEAN_WORKSPACE_DEPS", "1")
TIMEOUT_WRAPUP_SEC = int(os.environ.get("TIMEOUT_WRAPUP_SEC", "600"))
OAUTH_CREDENTIAL_SYNC_INTERVAL_SEC = int(os.environ.get("OAUTH_CREDENTIAL_SYNC_INTERVAL_SEC", "15"))
OAUTH_401_PROFILE_WAIT_SEC = int(os.environ.get("OAUTH_401_PROFILE_WAIT_SEC", "90"))
CLAUDE_API_STALL_WATCHDOG_SEC = int(os.environ.get("CLAUDE_API_STALL_WATCHDOG_SEC", "400"))
CLAUDE_API_STALL_MAX_RECOVERIES = int(os.environ.get("CLAUDE_API_STALL_MAX_RECOVERIES", "1"))
CLAUDE_BUSY_INTERRUPT_GRACE_SEC = int(os.environ.get("CLAUDE_BUSY_INTERRUPT_GRACE_SEC", "8"))
CLAUDE_API_STALL_RECOVERY_PROMPT = os.environ.get("CLAUDE_API_STALL_RECOVERY_PROMPT", "")

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
_SESSION_COOKIE = "vb_v3_session" if V3_ENABLED else "vb_session"
_DEFAULT_CLAUDE_SETTINGS: dict[str, object] = {
    "env": {
        "CLAUDE_CODE_EFFORT_LEVEL": CLAUDE_CODE_EFFORT_LEVEL,
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
    # 新版 Auto 推荐菜单会消费题目提交的回车，自动任务必须跳过该首次引导。
    "hasSeenAutoDefaultNudge": True,
    "projects": {
        "/workspace": {
            "hasTrustDialogAccepted": True,
        },
    },
}
_PROFILE_SYNC_FILES = (".credentials.json", "settings.json", ".claude.json")
_PROFILE_CONFIG_SYNC_FILES = ("settings.json", ".claude.json")
_TERMINAL_RUN_STATUSES = {"success", "failed", "timeout", "stopped", "auth_failed"}
OAUTH_REFRESH_INTERVAL_SEC = 60
OAUTH_REFRESH_BUFFER_SEC = 10 * 60
_profile_locks: dict[str, threading.Lock] = {}
_profile_locks_lock = threading.Lock()
_oauth_owner_locks: dict[str, threading.Lock] = {}
_oauth_owner_locks_lock = threading.Lock()
_cc2api_binding_lock = threading.Lock()


def _profile_lock(account_name: str) -> threading.Lock:
    """
    获取账号 profile 的进程内互斥锁。

    :param account_name: accounts.name 字段
    :return: 该账号对应的 threading.Lock
    """
    with _profile_locks_lock:
        if account_name not in _profile_locks:
            _profile_locks[account_name] = threading.Lock()
        return _profile_locks[account_name]


def _oauth_owner_lock(account_name: str) -> threading.Lock:
    """
    获取账号 OAuth 所有权切换锁。

    :param account_name: accounts.name 字段
    :return: 串行化 worker 启动与 cc2api 绑定切换的账号级锁
    """
    with _oauth_owner_locks_lock:
        if account_name not in _oauth_owner_locks:
            _oauth_owner_locks[account_name] = threading.Lock()
        return _oauth_owner_locks[account_name]


def _usage_input_tokens(usage: dict) -> int:
    """
    计算一次 Claude usage 的输入 token 总量。

    :param usage: Claude usage 对象
    :return: 普通输入 + cache 写入 + cache 读取 token
    """
    return (
        int(usage.get("input_tokens") or 0)
        + int(usage.get("cache_creation_input_tokens") or 0)
        + int(usage.get("cache_read_input_tokens") or 0)
    )


def _merge_claude_settings(existing: object, defaults: dict[str, object]) -> dict[str, object]:
    """
    递归合并 Claude settings，保留未知字段并让项目默认值覆盖同名字段。

    :param existing: 现有 settings.json 解析结果；非对象时视为空配置
    :param defaults: 项目要求写入的默认 settings
    :return: 合并后的 settings 对象
    """
    merged = dict(existing) if isinstance(existing, dict) else {}
    # hooks/statusLine 必须只存在于单次 run 的 workspace local settings。
    # 早期 quota 探测把 statusLine 写进 profile 后，会污染后续 task 并制造错误完成信号。
    merged.pop("hooks", None)
    merged.pop("statusLine", None)
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
    补齐顶层 `~/.claude.json` 里的本地启动 gate。

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
    merged = _merge_claude_top_config(existing, _DEFAULT_CLAUDE_TOP_CONFIG)
    tmp_path = profile_dir / ".claude.json.tmp"
    tmp_path.write_text(
        json.dumps(merged, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    tmp_path.replace(top_config_path)
    _make_worker_owned(top_config_path)


def _merge_claude_top_config(
    existing: object,
    defaults: dict[str, object],
) -> dict[str, object]:
    """
    递归补齐 Claude 顶层配置，并保留账号身份及已有项目状态。

    :param existing: 现有 `~/.claude.json` 解析结果
    :param defaults: 项目要求写入的顶层默认值
    :return: 合并后的顶层配置
    """
    merged = dict(existing) if isinstance(existing, dict) else {}
    for key, value in defaults.items():
        old_value = merged.get(key)
        if isinstance(old_value, dict) and isinstance(value, dict):
            merged[key] = _merge_claude_top_config(old_value, value)
        else:
            merged[key] = value
    return merged


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


def _copy_file_atomically(src: Path, dst: Path) -> None:
    """
    通过临时文件 + rename 原子替换目标文件。

    :param src: 源文件路径
    :param dst: 目标文件路径
    :return: None
    """
    dst.parent.mkdir(parents=True, exist_ok=True)
    tmp = dst.with_name(f"{dst.name}.tmp.{uuid.uuid4().hex}")
    shutil.copy2(src, tmp)
    tmp.replace(dst)
    _make_worker_owned(dst)


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
    兼容旧调用名：现在只回写运行时本地配置，不回写 OAuth 凭据。

    :param claude_home_dir: run workspace 下的 `.claude-home` 目录
    :param profile_dir: `data/profiles/<account>` 目录
    :return: None
    """
    _copy_claude_home_config_to_profile(claude_home_dir, profile_dir)


def _copy_claude_home_config_to_profile(claude_home_dir: Path, profile_dir: Path) -> None:
    """
    只把运行时本地配置回写到账号 profile，不回写 OAuth 凭据。

    :param claude_home_dir: run workspace 下的 `.claude-home` 目录
    :param profile_dir: `data/profiles/<account>` 目录
    :return: None
    """
    if not claude_home_dir.exists():
        return
    profile_dir.mkdir(parents=True, exist_ok=True)
    for name in _PROFILE_CONFIG_SYNC_FILES:
        src = claude_home_dir / name
        if not src.exists() or not src.is_file():
            continue
        dst = profile_dir / name
        try:
            _copy_file_atomically(src, dst)
        except OSError:
            pass
    _persist_default_claude_top_config(profile_dir)


def _read_account_oauth_status(account_name: str) -> dict[str, object]:
    """
    读取账号 profile 中的 OAuth access token 过期状态。

    :param account_name: accounts.name 字段
    :return: 仅包含过期时间和状态的安全对象，不返回 token 明文
    """
    credentials_path = PROFILES_DIR / account_name / ".credentials.json"
    result: dict[str, object] = {
        "oauth_expires_at_ms": None,
        "oauth_expires_at_iso": None,
        "oauth_expires_in_sec": None,
        "oauth_token_state": "missing",
    }
    if not credentials_path.exists():
        return result
    try:
        data = json.loads(credentials_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        result["oauth_token_state"] = "invalid"
        return result
    oauth = data.get("claudeAiOauth") if isinstance(data, dict) else None
    if not isinstance(oauth, dict):
        result["oauth_token_state"] = "invalid"
        return result
    token = oauth.get("accessToken")
    expires_at = oauth.get("expiresAt")
    if not isinstance(token, str) or not token:
        result["oauth_token_state"] = "missing"
        return result
    if not isinstance(expires_at, (int, float)):
        result["oauth_token_state"] = "invalid"
        return result
    expires_at_ms = int(expires_at)
    expires_in_sec = int((expires_at_ms - int(time.time() * 1000)) / 1000)
    if expires_in_sec <= 0:
        state = "expired"
    elif expires_in_sec <= 10 * 60:
        state = "expiring"
    else:
        state = "valid"
    result.update({
        "oauth_expires_at_ms": expires_at_ms,
        "oauth_expires_at_iso": time.strftime(
            "%Y-%m-%dT%H:%M:%SZ",
            time.gmtime(expires_at_ms / 1000),
        ),
        "oauth_expires_in_sec": expires_in_sec,
        "oauth_token_state": state,
    })
    return result


# ============== cc2api 集成 ==============
def _redact_cc2api_error(value: object) -> str:
    """
    生成可展示的 cc2api 错误摘要，同时移除可能混入的凭据。

    :param value: 下游错误字段或异常文本
    :return: 最长 300 字符的脱敏摘要
    """
    text = str(value or "cc2api 请求失败")
    text = _CC2API_SECRET_RE.sub("***", text)
    return text[:300]


def _mask_email(value: object) -> str:
    """
    对账号邮箱做最小展示脱敏。

    :param value: 原始邮箱
    :return: 脱敏邮箱；格式异常时返回空字符串
    """
    email = str(value or "").strip()
    if "@" not in email:
        return ""
    local, domain = email.split("@", 1)
    if not local or not domain:
        return ""
    visible = local[:2]
    return f"{visible}{'*' * max(3, len(local) - len(visible))}@{domain}"


def _normalize_identity_value(value: object) -> str:
    """
    规范化账号身份匹配字段。

    :param value: 邮箱或 UUID 原始值
    :return: trim 后的小写字符串
    """
    return str(value or "").strip().lower()


def _cc2api_error_detail_is_permanent(detail: str) -> bool:
    """
    从 cc2api 脱敏错误类别识别不应自动重试的凭据问题。

    :param detail: cc2api 返回的错误摘要
    :return: invalid_grant、账号状态或凭据结构错误返回 True
    """
    lowered = detail.lower()
    return any(
        marker in lowered
        for marker in (
            "invalid_grant",
            "account_on_hold",
            "not found",
            "不是 active",
            "not active",
            "不是 oauth",
            "not oauth",
            "refresh token is empty",
            "refresh token 为空",
            "credentials are incomplete",
            "credentials missing",
            "凭据不完整",
            "凭据缺少",
            "账号不存在",
            "账号已禁用",
            "账号不是 active",
            "账号不是 oauth",
        )
    )


class Cc2ApiClient:
    """封装 orchestrator 到 cc2api 管理 API 的受信任调用。"""

    def __init__(
        self,
        base_url: str,
        admin_password: str,
        timeout_sec: float,
    ) -> None:
        """
        初始化 cc2api 客户端。

        :param base_url: cc2api 根地址
        :param admin_password: 管理 API Bearer 密码
        :param timeout_sec: 单次请求超时秒数
        :return: None
        """
        self.base_url = base_url.rstrip("/")
        self.admin_password = admin_password
        self.timeout_sec = max(1.0, float(timeout_sec))

    def is_configured(self) -> bool:
        """
        判断 cc2api 集成是否具备最小配置。

        :return: base URL 和管理密码都存在时返回 True
        """
        return bool(self.base_url and self.admin_password)

    def _request(
        self,
        method: str,
        path: str,
        body: Optional[dict] = None,
    ) -> dict:
        """
        发送管理 API JSON 请求。

        :param method: HTTP 方法
        :param path: 以 `/` 开头的管理 API 路径
        :param body: 可选 JSON 请求体
        :return: JSON object 响应
        """
        if not self.is_configured():
            raise ValueError("cc2api 集成尚未配置")
        payload = None
        if body is not None:
            payload = json.dumps(body, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(
            f"{self.base_url}{path}",
            data=payload,
            method=method,
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.admin_password}",
                **({"x-v3-service-token": os.environ.get("V3_INTERNAL_TOKEN", "")} if
                    (path == "/admin/accounts" and body and body.get("cli_identity"))
                    or re.fullmatch(r"/admin/accounts/[0-9]+/(?:oauth-credentials/import(?:/[a-f0-9]{32})?|cli-process/import)", path) else {}),
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_sec) as response:
                raw = response.read(2 * 1024 * 1024)
        except urllib.error.HTTPError as exc:
            raw = exc.read(4096)
            detail = f"HTTP {exc.code}"
            try:
                data = json.loads(raw.decode("utf-8", errors="replace"))
                if isinstance(data, dict):
                    detail = _redact_cc2api_error(data.get("error") or data.get("detail") or detail)
            except json.JSONDecodeError:
                pass
            message = f"cc2api 请求失败：{detail}"
            if _cc2api_error_detail_is_permanent(detail):
                raise ValueError(message) from exc
            if exc.code in (401, 403, 408, 429) or exc.code >= 500:
                raise ConnectionError(message) from exc
            raise ValueError(message) from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise ConnectionError("cc2api 请求失败：网络不可用") from exc

        try:
            data = json.loads(raw.decode("utf-8")) if raw else {}
        except json.JSONDecodeError as exc:
            raise ValueError("cc2api 响应不是有效 JSON") from exc
        if not isinstance(data, dict):
            raise ValueError("cc2api 响应必须是 JSON object")
        return data

    def list_accounts(self, *, require_complete: bool = False) -> list[dict]:
        """
        分页读取全部 cc2api 账号。

        :param require_complete: 缺失证明要求完整分页与有效 ID，不能把坏响应当作空列表
        :return: cc2api Account object 列表
        """
        page = 1
        accounts: list[dict] = []
        while True:
            data = self._request("GET", f"/admin/accounts?page={page}&page_size=100")
            rows = data.get("data")
            if not isinstance(rows, list):
                raise ValueError("cc2api 账号列表响应无效")
            if require_complete:
                total = data.get("total")
                metadata = (data.get("page"), data.get("page_size"), total, data.get("total_pages"))
                # 解绑依赖“不存在”的结论，缺页、坏行或重复 ID 都不能成为删除证明。
                if (any(type(value) is not int for value in metadata) or total < 0
                        or metadata[0] != page or metadata[1] != 100 or metadata[3] != (total + 99) // 100
                        or len(rows) != min(100, max(0, total - (page - 1) * 100))
                        or any(not isinstance(row, dict) or type(row.get("id")) is not int
                            or row["id"] <= 0 for row in rows)):
                    raise ValueError("cc2api 账号列表不完整，无法确认原绑定已删除")
            accounts.extend(row for row in rows if isinstance(row, dict))
            total_pages = int(data.get("total_pages") or 1)
            if page >= total_pages:
                if require_complete and (len(accounts) != total or len({row["id"] for row in accounts}) != total):
                    raise ValueError("cc2api 账号列表不完整，无法确认原绑定已删除")
                return accounts
            page += 1

    def create_account(self, payload: dict) -> dict:
        """
        创建 cc2api OAuth 账号。

        :param payload: cc2api CreateAccountRequest 字段
        :return: 新建后的 Account object
        """
        return self._request("POST", "/admin/accounts", payload)

    def resolve_credentials(
        self,
        account_id: int,
        min_validity_seconds: int,
        force_refresh: bool = False,
    ) -> dict:
        """
        在 cc2api 账号锁内解析 OAuth 凭据。

        :param account_id: cc2api 账号 ID
        :param min_validity_seconds: AT 最小剩余有效期
        :param force_refresh: 是否强制刷新一次
        :return: AT、RT 和 expires_at 快照
        """
        data = self._request(
            "POST",
            f"/admin/accounts/{account_id}/oauth-credentials/resolve",
            {
                "min_validity_seconds": int(min_validity_seconds),
                "force_refresh": bool(force_refresh),
            },
        )
        if int(data.get("account_id") or 0) != int(account_id):
            raise ValueError("cc2api 凭据账号 ID 不匹配")
        access_token = data.get("access_token")
        refresh_token = data.get("refresh_token")
        expires_at = data.get("expires_at")
        if not isinstance(access_token, str) or not access_token:
            raise ValueError("cc2api 凭据缺少 access_token")
        if not isinstance(refresh_token, str) or not refresh_token:
            raise ValueError("cc2api 凭据缺少 refresh_token")
        if not isinstance(expires_at, (int, float)):
            raise ValueError("cc2api 凭据缺少 expires_at")
        return {
            "account_id": int(account_id),
            "access_token": access_token,
            "refresh_token": refresh_token,
            "expires_at": int(expires_at),
        }

    def refresh_usage(self, account_id: int) -> dict:
        """
        通过 cc2api 账号服务刷新 OAuth usage。

        :param account_id: cc2api 账号 ID
        :return: cc2api usage handler 响应
        """
        return self._request("POST", f"/admin/accounts/{account_id}/usage")

    def import_credentials(self, account_id: int, payload: dict) -> dict:
        """向原绑定账号导入真实 CLI 新凭据。

        :param account_id: 原关联 ID
        :param payload: 凭据、身份、操作 ID 与租约证明
        :return: 同一操作的最终权威快照
        """
        data = self._request("POST", f"/admin/accounts/{account_id}/oauth-credentials/import", payload)
        return self._import_snapshot(account_id, payload["operation_id"], data)

    def import_status(self, account_id: int, operation_id: str) -> Optional[dict]:
        """查询回执；网络错误不能被当成未提交。

        :param account_id: 原关联 ID
        :param operation_id: 唯一提交 ID
        :return: 已提交的当前快照，明确未提交时为 None
        """
        if not re.fullmatch(r"[a-f0-9]{32}", operation_id):
            raise ValueError("凭据提交操作 ID 不合法")
        data = self._request("GET", f"/admin/accounts/{account_id}/oauth-credentials/import/{operation_id}")
        if data.get("imported") is False and data.get("account_id") == account_id and data.get("operation_id") == operation_id:
            return None
        return self._import_snapshot(account_id, operation_id, data)

    @staticmethod
    def _import_snapshot(account_id: int, operation_id: str, data: dict) -> dict:
        """严格核对导入回执，拒绝错误账号和不完整凭据。

        :param account_id: 期望账号
        :param operation_id: 期望操作
        :param data: 受信任服务返回值
        :return: 最小凭据快照
        """
        if data.get("imported") is not True or data.get("account_id") != account_id or data.get("operation_id") != operation_id:
            raise ValueError("凭据导入回执不匹配")
        if any(not isinstance(data.get(key), str) or not data[key] for key in ("access_token", "refresh_token")) or type(data.get("expires_at")) is not int:
            raise ValueError("凭据导入回执不完整")
        return {key: data[key] for key in ("account_id", "access_token", "refresh_token", "expires_at")}


cc2api_client = Cc2ApiClient(
    CC2API_BASE_URL,
    CC2API_ADMIN_PASSWORD,
    CC2API_REQUEST_TIMEOUT_SEC,
)


def _read_bench_profile_identity(account_name: str, profile_dir: Optional[Path] = None,
    top_config_path: Optional[Path] = None) -> dict:
    """
    读取同步 cc2api 所需的 bench OAuth profile 字段。

    :param account_name: bench accounts.name
    :param profile_dir: 可选暂存凭据目录
    :param top_config_path: 可选暂存顶层配置
    :return: 经过结构校验的身份与凭据字段
    """
    profile_dir = profile_dir or PROFILES_DIR / account_name
    credentials_path = profile_dir / ".credentials.json"
    top_config_path = top_config_path or profile_dir / ".claude.json"
    try:
        credentials = json.loads(credentials_path.read_text(encoding="utf-8"))
        top_config = json.loads(top_config_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError("bench profile 文件不完整") from exc
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("bench profile JSON 无效") from exc
    oauth = credentials.get("claudeAiOauth") if isinstance(credentials, dict) else None
    oauth_account = top_config.get("oauthAccount") if isinstance(top_config, dict) else None
    if not isinstance(oauth, dict) or not isinstance(oauth_account, dict):
        raise ValueError("bench profile OAuth 身份信息不完整")
    access_token = oauth.get("accessToken")
    refresh_token = oauth.get("refreshToken")
    expires_at = oauth.get("expiresAt")
    email = oauth_account.get("emailAddress")
    if not isinstance(access_token, str) or not access_token:
        raise ValueError("bench profile 缺少 access token")
    if not isinstance(refresh_token, str) or not refresh_token:
        raise ValueError("bench profile 缺少 refresh token")
    if not isinstance(expires_at, (int, float)):
        raise ValueError("bench profile 缺少 expiresAt")
    if not isinstance(email, str) or not email.strip():
        raise ValueError("bench profile 缺少 emailAddress")
    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "expires_at": int(expires_at),
        "subscription_type": str(oauth.get("subscriptionType") or "").strip() or None,
        "email": email.strip(),
        "account_uuid": str(oauth_account.get("accountUuid") or "").strip() or None,
        "organization_uuid": str(oauth_account.get("organizationUuid") or "").strip() or None,
    }


def _account_proxy_url(account: dict) -> str:
    """
    把 bench 分列代理配置转换为 cc2api proxy_url。

    :param account: bench accounts 行
    :return: 完整代理 URL；未配置代理时返回空字符串
    """
    host = str(account.get("upstream_socks5_host") or "").strip()
    if not host:
        return ""
    scheme = _normalize_upstream_proxy_scheme(account.get("upstream_proxy_scheme"))
    port = int(account.get("upstream_socks5_port") or 1080)
    user = urllib.parse.quote(str(account.get("upstream_socks5_user") or ""), safe="")
    password = urllib.parse.quote(str(account.get("upstream_socks5_pass") or ""), safe="")
    auth = ""
    if user:
        auth = user
        if password:
            auth += f":{password}"
        auth += "@"
    return f"{scheme}://{auth}{host}:{port}"


def _sync_cc2api_credentials_to_profile(account_name: str, snapshot: dict) -> None:
    """
    用 cc2api 最终凭据原子更新 bench profile。

    :param account_name: bench 账号名
    :param snapshot: `Cc2ApiClient.resolve_credentials` 返回值
    :return: None
    """
    with _profile_lock(account_name):
        _sync_cc2api_credentials_to_profile_locked(account_name, snapshot)


def _sync_cc2api_credentials_to_profile_locked(
    account_name: str,
    snapshot: dict,
) -> None:
    """
    在已持有 profile 锁时写入 cc2api 凭据。

    :param account_name: bench 账号名
    :param snapshot: `Cc2ApiClient.resolve_credentials` 返回值
    :return: None
    """
    access_token = snapshot.get("access_token")
    refresh_token = snapshot.get("refresh_token")
    expires_at = snapshot.get("expires_at")
    if not isinstance(access_token, str) or not access_token:
        raise ValueError("cc2api 凭据缺少 access_token")
    if not isinstance(refresh_token, str) or not refresh_token:
        raise ValueError("cc2api 凭据缺少 refresh_token")
    if not isinstance(expires_at, (int, float)):
        raise ValueError("cc2api 凭据缺少 expires_at")
    credentials_path = PROFILES_DIR / account_name / ".credentials.json"
    try:
        data = json.loads(credentials_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError("bench profile 缺少凭据文件") from exc
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("bench profile 凭据 JSON 无效") from exc
    oauth = data.get("claudeAiOauth") if isinstance(data, dict) else None
    if not isinstance(oauth, dict):
        raise ValueError("bench profile 缺少 claudeAiOauth")
    oauth["accessToken"] = access_token
    oauth["refreshToken"] = refresh_token
    oauth["expiresAt"] = int(expires_at)
    tmp_path = credentials_path.with_name(
        f"{credentials_path.name}.tmp.{uuid.uuid4().hex}"
    )
    fd: Optional[int] = None
    try:
        # 凭据临时文件从创建时就必须是 0600，避免原子替换前出现短暂明文暴露窗口。
        fd = os.open(tmp_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            fd = None
            stream.write(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        tmp_path.replace(credentials_path)
    finally:
        if fd is not None:
            os.close(fd)
        try:
            tmp_path.unlink()
        except FileNotFoundError:
            pass
    _make_worker_owned(credentials_path)
    os.chmod(credentials_path, 0o600)


def _resolve_and_sync_cc2api_credentials(
    account_name: str,
    cc2api_account_id: int,
    min_validity_seconds: int,
    force_refresh: bool = False,
) -> dict:
    """
    串行完成 cc2api 凭据解析与 profile 落盘。

    :param account_name: bench 账号名
    :param cc2api_account_id: cc2api 账号 ID
    :param min_validity_seconds: access token 最小剩余有效期
    :param force_refresh: 是否强制刷新一次
    :return: cc2api 最终凭据快照
    """
    validity = max(60, min(7200, int(min_validity_seconds)))
    with _profile_lock(account_name):
        snapshot = cc2api_client.resolve_credentials(
            int(cc2api_account_id),
            validity,
            force_refresh,
        )
        _sync_cc2api_credentials_to_profile_locked(account_name, snapshot)
        return snapshot


def _write_json_atomically(path: Path, payload: dict) -> None:
    """
    原子写入内部状态 JSON，避免 worker 读取半截标记文件。

    :param path: 目标 JSON 路径
    :param payload: 可 JSON 序列化的状态对象
    :return: None
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(f"{path.name}.tmp.{uuid.uuid4().hex}")
    tmp_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    tmp_path.replace(path)
    _make_worker_owned(path)


def _cc2api_account_is_active_oauth(account: dict) -> bool:
    """
    判断 cc2api 账号是否可作为 bench 的 OAuth 凭据来源。

    :param account: cc2api Account object
    :return: active OAuth 账号返回 True
    """
    return (
        str(account.get("status") or "").lower() == "active"
        and str(account.get("auth_type") or "").lower() == "oauth"
    )


def _cc2api_account_summary(account: dict) -> dict:
    """
    生成允许返回 WebUI 的 cc2api 账号摘要。

    :param account: cc2api Account object
    :return: 不含 token、代理和设备画像的脱敏摘要
    """
    return {
        "id": int(account.get("id") or 0),
        "name": str(account.get("name") or ""),
        "email_masked": _mask_email(account.get("email")),
        "status": str(account.get("status") or ""),
        "auth_type": str(account.get("auth_type") or ""),
        "account_uuid_present": bool(_normalize_identity_value(account.get("account_uuid"))),
    }


def _validate_cc2api_identity(profile: dict, cc2api_account: dict) -> None:
    """
    校验显式选择的 cc2api 账号与 bench profile 属于同一身份。

    :param profile: `_read_bench_profile_identity` 返回值
    :param cc2api_account: cc2api Account object
    :return: None
    """
    bench_uuid = _normalize_identity_value(profile.get("account_uuid"))
    cc_uuid = _normalize_identity_value(cc2api_account.get("account_uuid"))
    bench_email = _normalize_identity_value(profile.get("email"))
    cc_email = _normalize_identity_value(cc2api_account.get("email"))
    if bench_uuid:
        if not cc_uuid or cc_uuid != bench_uuid:
            raise ValueError("cc2api 账号 UUID 与 bench profile 不匹配")
        return
    if not bench_email or cc_email != bench_email:
        raise ValueError("cc2api 账号邮箱与 bench profile 不匹配")


def _find_cc2api_account_for_profile(profile: dict, accounts: list[dict]) -> Optional[dict]:
    """
    按 UUID 优先、邮箱兜底规则查找现有 cc2api 账号。

    :param profile: `_read_bench_profile_identity` 返回值
    :param accounts: cc2api 账号列表
    :return: 唯一匹配账号；没有匹配时返回 None
    """
    bench_uuid = _normalize_identity_value(profile.get("account_uuid"))
    bench_email = _normalize_identity_value(profile.get("email"))
    if bench_uuid:
        uuid_matches = [
            account
            for account in accounts
            if _normalize_identity_value(account.get("account_uuid")) == bench_uuid
        ]
        if len(uuid_matches) > 1:
            raise ValueError("多个 cc2api 账号使用了同一个 account UUID")
        email_conflicts = [
            account
            for account in accounts
            if _normalize_identity_value(account.get("email")) == bench_email
            and _normalize_identity_value(account.get("account_uuid"))
            and _normalize_identity_value(account.get("account_uuid")) != bench_uuid
        ]
        if email_conflicts:
            raise ValueError("cc2api 中存在相同邮箱但 account UUID 不同的账号")
        return uuid_matches[0] if uuid_matches else None

    email_matches = [
        account
        for account in accounts
        if _normalize_identity_value(account.get("email")) == bench_email
    ]
    if len(email_matches) > 1:
        raise ValueError("多个 cc2api 账号使用了同一个邮箱")
    return email_matches[0] if email_matches else None


def _sync_bound_account_credentials_locked(
    account: dict,
    min_validity_seconds: int,
    force_refresh: bool = False,
) -> dict:
    """
    在已持有 OAuth owner lock 时解析并镜像绑定账号凭据。

    :param account: bench accounts 行
    :param min_validity_seconds: 本次运行要求的最小 AT 有效期
    :param force_refresh: 是否要求 cc2api 强制刷新一次
    :return: cc2api 最终凭据快照
    """
    cc2api_account_id = account.get("cc2api_account_id")
    if cc2api_account_id is None:
        raise ValueError("bench 账号尚未绑定 cc2api")
    snapshot = _resolve_and_sync_cc2api_credentials(
        str(account["name"]),
        int(cc2api_account_id),
        min_validity_seconds,
        force_refresh,
    )
    if account_runtime:
        row = account_runtime._row(account["name"], account["id"])
        account_runtime.sync_credentials(row, account)
    return snapshot


def _sync_bound_account_credentials(
    account: dict,
    min_validity_seconds: int,
    force_refresh: bool = False,
) -> dict:
    """
    在账号所有权锁内重读绑定并镜像 cc2api 最终凭据。

    :param account: 调用方读取的 bench accounts 行
    :param min_validity_seconds: 本次运行要求的最小 AT 有效期
    :param force_refresh: 是否要求 cc2api 强制刷新一次
    :return: cc2api 最终凭据快照
    """
    account_id = account.get("id")
    account_name = str(account.get("name") or "")
    expected_binding = account.get("cc2api_account_id")
    if account_id is None or not account_name:
        raise ValueError("bench 账号信息不完整")
    if expected_binding is None:
        raise ValueError("bench 账号尚未绑定 cc2api")

    with _oauth_owner_lock(account_name):
        conn = get_db()
        try:
            current_row = _get_available_account(conn, int(account_id))
            if not current_row:
                raise ValueError("bench 账号不存在或已停用")
            current = dict(current_row)
        finally:
            conn.close()
        current_binding = current.get("cc2api_account_id")
        if current_binding is None or int(current_binding) != int(expected_binding):
            raise ValueError("bench 账号的 cc2api 绑定已变化，请重试")
        return _sync_bound_account_credentials_locked(
            current,
            min_validity_seconds,
            force_refresh,
        )


def _cc2api_error_is_permanent(exc: Exception) -> bool:
    """
    区分需要暂停养号的永久错误与可重试网络错误。

    :param exc: cc2api 调用异常
    :return: 非网络类 ValueError 返回 True
    """
    return isinstance(exc, ValueError) and not isinstance(exc, ConnectionError)


def _claude_exec_env(use_sidecar: bool, extra: Optional[dict[str, str]] = None) -> dict[str, str]:
    """
    生成 docker exec 启动 Claude 子命令时必须显式传入的环境变量。

    entrypoint 里 export 的变量不会自动进入 docker exec 创建的新进程；走
    sidecar MITM 时必须重复传 CA 路径，否则登录 TUI 可能不信 MITM 证书。
    """
    try:
        claude_code_version = effective_claude_code_version()
    except Exception:
        claude_code_version = CLAUDE_CODE_VERSION
    env = {
        "HOME": WORKER_HOME,
        "CLAUDE_CODE_VERSION": claude_code_version,
    }
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


def _host_bench_data_path(container_path: Path) -> Path:
    """
    将 orchestrator 容器内 BENCH_DATA 路径转换成宿主机挂载路径。

    :param container_path: orchestrator 视角下的文件路径
    :return: docker daemon 可识别的宿主机路径
    """
    try:
        relative_path = container_path.relative_to(BENCH_DATA)
    except ValueError:
        return container_path
    return HOST_BENCH_DATA / relative_path


def _resolve_capture_flows_dirs(
    run: dict,
    *,
    ensure_exists: bool = False,
) -> Optional[tuple[Path, Path]]:
    """
    解析 run 是否需要完整抓包，以及对应的容器内/宿主机 flows 目录。

    :param run: runs 表行
    :param ensure_exists: 是否创建本地 flows 目录
    :return: (orchestrator 容器内 flows 目录, 宿主机 flows 目录)；非 capture run 返回 None
    """
    capture_summary_path = run.get("capture_summary_path")
    is_capture_run = isinstance(capture_summary_path, str) and bool(capture_summary_path)
    is_capture_run = is_capture_run or (run.get("run_kind") or "normal") == "capture"
    if not is_capture_run:
        return None

    flows_dir_value = run.get("flows_dir")
    if isinstance(flows_dir_value, str) and flows_dir_value:
        flows_dir = Path(flows_dir_value)
    else:
        run_id = str(run.get("id") or "")
        matches = [p.parent for p in FLOWS_DIR.rglob(f"{run_id}/stats.jsonl")] if run_id else []
        if not matches:
            raise ValueError(f"capture run {run_id or '(unknown)'} has no flows_dir")
        flows_dir = matches[0]

    # sibling sidecar 挂卷必须用宿主机路径；DB 里保存的是 orchestrator 容器内路径。
    if ensure_exists:
        flows_dir.mkdir(parents=True, exist_ok=True)
    return flows_dir, _host_bench_data_path(flows_dir)


# ============== DB ==============
_SCHEMA = """
CREATE TABLE IF NOT EXISTS accounts (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT UNIQUE NOT NULL,
  profile_path TEXT NOT NULL,
  upstream_proxy_scheme TEXT DEFAULT 'socks5',
  upstream_socks5_host TEXT,
  upstream_socks5_port INTEGER,
  upstream_socks5_user TEXT,
  upstream_socks5_pass TEXT,
  timezone TEXT,
  cc2api_account_id INTEGER,
  warmup_enabled INTEGER DEFAULT 0,
  warmup_interval_min_hours INTEGER DEFAULT 3,
  warmup_interval_max_hours INTEGER DEFAULT 5,
  warmup_quota_5h_limit_percent INTEGER,
  warmup_quota_7d_limit_percent INTEGER,
  warmup_next_run_at REAL,
  warmup_last_attempt_at REAL,
  warmup_last_run_id TEXT,
  warmup_last_status TEXT,
  warmup_last_error TEXT,
  warmup_auth_failures INTEGER DEFAULT 0,
  oauth_refresh_last_attempt_at REAL,
  oauth_refresh_last_status TEXT,
  oauth_refresh_last_error TEXT,
  enabled INTEGER DEFAULT 1,
  deleted_at REAL,
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

CREATE TABLE IF NOT EXISTS app_settings (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL,
  updated_at REAL DEFAULT (julianday('now'))
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
  run_kind TEXT DEFAULT 'normal',
  capture_mode TEXT,
  capture_summary_path TEXT,
  capture_model_override TEXT,
  capture_permission_mode TEXT DEFAULT 'bypassPermissions',
  claude_code_version TEXT,
  claude_effort_level TEXT,
  execution_model TEXT,
  quota_attempt INTEGER NOT NULL DEFAULT 0,
  quota_resume_at REAL,
  quota_identity TEXT,
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
CREATE INDEX IF NOT EXISTS idx_topics_no    ON topics(no);
CREATE INDEX IF NOT EXISTS idx_batches_account ON task_batches(account_id);
CREATE INDEX IF NOT EXISTS idx_batch_items_batch ON task_batch_items(batch_id);
CREATE TABLE IF NOT EXISTS account_quota_states (
  account_id INTEGER PRIMARY KEY,
  identity TEXT NOT NULL,
  state_json TEXT NOT NULL DEFAULT '{}',
  recovery_source TEXT,
  updated_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS quota_observation_cursors (
  source TEXT PRIMARY KEY,
  account_id INTEGER NOT NULL,
  identity TEXT NOT NULL,
  path TEXT NOT NULL,
  file_identity TEXT,
  byte_offset INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS warmup_quota_admissions (
  account_id INTEGER PRIMARY KEY,
  identity TEXT NOT NULL,
  policy_key TEXT NOT NULL,
  window_key TEXT NOT NULL,
  source TEXT NOT NULL,
  created_at REAL NOT NULL
);
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
            _ensure_column(conn, "accounts", "upstream_proxy_scheme", "TEXT DEFAULT 'socks5'")
            _ensure_column(conn, "accounts", "timezone", "TEXT")
            _ensure_column(conn, "accounts", "deleted_at", "REAL")
            _ensure_column(conn, "accounts", "cc2api_account_id", "INTEGER")
            _ensure_column(conn, "accounts", "warmup_enabled", "INTEGER DEFAULT 0")
            _ensure_column(conn, "accounts", "warmup_quota_5h_limit_percent", "INTEGER")
            _ensure_column(conn, "accounts", "warmup_quota_7d_limit_percent", "INTEGER")
            _ensure_column(
                conn, "accounts", "warmup_interval_min_hours", "INTEGER DEFAULT 3"
            )
            _ensure_column(
                conn, "accounts", "warmup_interval_max_hours", "INTEGER DEFAULT 5"
            )
            _ensure_column(conn, "accounts", "warmup_next_run_at", "REAL")
            _ensure_column(conn, "accounts", "warmup_last_attempt_at", "REAL")
            _ensure_column(conn, "accounts", "warmup_last_run_id", "TEXT")
            _ensure_column(conn, "accounts", "warmup_last_status", "TEXT")
            _ensure_column(conn, "accounts", "warmup_last_error", "TEXT")
            _ensure_column(
                conn, "accounts", "warmup_auth_failures", "INTEGER DEFAULT 0"
            )
            _ensure_column(conn, "accounts", "oauth_refresh_last_attempt_at", "REAL")
            _ensure_column(conn, "accounts", "oauth_refresh_last_status", "TEXT")
            _ensure_column(conn, "accounts", "oauth_refresh_last_error", "TEXT")
            _ensure_column(conn, "tasks", "batch_id", "INTEGER")
            _ensure_column(conn, "tasks", "topic_id", "INTEGER")
            _ensure_column(conn, "tasks", "status", "TEXT DEFAULT 'active'")
            _ensure_column(conn, "tasks", "deleted_at", "REAL")
            _ensure_column(conn, "runs", "batch_id", "INTEGER")
            _ensure_column(conn, "runs", "topic_id", "INTEGER")
            _ensure_column(conn, "runs", "stop_requested_at", "REAL")
            _ensure_column(conn, "runs", "deleted_at", "REAL")
            _ensure_column(conn, "runs", "run_kind", "TEXT DEFAULT 'normal'")
            _ensure_column(conn, "runs", "capture_mode", "TEXT")
            _ensure_column(conn, "runs", "capture_summary_path", "TEXT")
            _ensure_column(conn, "runs", "capture_model_override", "TEXT")
            _ensure_column(
                conn,
                "runs",
                "capture_permission_mode",
                "TEXT DEFAULT 'bypassPermissions'",
            )
            _ensure_column(conn, "runs", "claude_code_version", "TEXT")
            _ensure_column(conn, "runs", "claude_effort_level", "TEXT")
            _ensure_column(conn, "runs", "execution_model", "TEXT")
            _ensure_column(conn, "runs", "quota_attempt", "INTEGER NOT NULL DEFAULT 0")
            _ensure_column(conn, "runs", "quota_resume_at", "REAL")
            _ensure_column(conn, "runs", "quota_identity", "TEXT")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_runs_batch ON runs(batch_id)")
            conn.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_accounts_cc2api_account_id "
                "ON accounts(cc2api_account_id) WHERE cc2api_account_id IS NOT NULL"
            )
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
_CAT_RE = re.compile(
    r"^##\s+(?:[一二三四五六七八九十百零\d]+、|\d+\.\s+)"
    r"(.+?)(?:（\d+\s*题）|\(\d+\s+topics?\))\s*$",
    re.IGNORECASE,
)
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


def _account_reference_counts(conn: sqlite3.Connection, account_id: int) -> dict[str, int]:
    """
    统计账号是否仍被任务、运行或批次引用。

    :param conn: 当前数据库连接
    :param account_id: accounts.id
    :return: 各引用表的数量
    """
    counts: dict[str, int] = {}
    for table in ("tasks", "runs", "task_batches"):
        row = conn.execute(
            f"SELECT COUNT(*) AS n FROM {table} WHERE account_id=?",
            (account_id,),
        ).fetchone()
        counts[table] = int(row["n"] if row else 0)
    return counts


def _account_is_available(account: dict) -> bool:
    """
    判断账号是否仍允许参与新运行或凭据刷新。

    :param account: accounts 表行
    :return: 启用且未软删除时返回 True
    """
    return int(account.get("enabled") or 0) == 1 and account.get("deleted_at") is None


def _get_available_account(conn: sqlite3.Connection, account_id: int) -> Optional[sqlite3.Row]:
    """
    读取允许参与新运行和凭据刷新的账号。

    :param conn: 当前数据库连接
    :param account_id: accounts.id
    :return: 可用账号行；不存在、停用或软删除时返回 None
    """
    row = conn.execute(
        "SELECT * FROM accounts WHERE id=? AND enabled=1 AND deleted_at IS NULL",
        (account_id,),
    ).fetchone()
    return row if row and not _login_save_pending(conn, row["name"]) else None


def _login_save_pending(conn: sqlite3.Connection, name: str) -> bool:
    if not account_runtime:
        return False
    environment = conn.execute("SELECT * FROM account_environments WHERE name=?", (name,)).fetchone()
    if not environment:
        return False
    try:
        return LoginDraftStore(account_runtime, get_db, _db_lock).record(dict(environment))["phase"] == "submitting"
    except FileNotFoundError:
        # 提交尾部已删除标记，账号的 HOME 与数据库已完整保存。
        return False
    except (ValueError, KeyError):
        return True


def _restore_deleted_account(
    conn: sqlite3.Connection,
    account_id: int,
    name: str,
    proxy_scheme: str,
    upstream_socks5_host: Optional[str],
    upstream_socks5_port: Optional[int],
    upstream_socks5_user: Optional[str],
    upstream_socks5_pass: Optional[str],
    timezone: Optional[str],
    enabled: int,
) -> int:
    """
    恢复同名软删除账号，保留历史 account_id 引用。

    :param conn: 当前数据库连接
    :param account_id: 要恢复的 accounts.id
    :param name: 账号 profile 名
    :param proxy_scheme: 上游代理协议
    :param upstream_socks5_host: 上游代理 host
    :param upstream_socks5_port: 上游代理端口
    :param upstream_socks5_user: 上游代理用户名
    :param upstream_socks5_pass: 上游代理密码
    :param timezone: 账号显式时区；None 表示自动派生
    :param enabled: 恢复后的启用状态
    :return: 恢复后的账号 ID
    """
    conn.execute(
        "UPDATE accounts SET profile_path=?, upstream_proxy_scheme=?, "
        "upstream_socks5_host=?, upstream_socks5_port=?, upstream_socks5_user=?, "
        "upstream_socks5_pass=?, timezone=?, enabled=?, deleted_at=NULL WHERE id=?",
        (
            f"profiles/{name}",
            proxy_scheme,
            upstream_socks5_host,
            upstream_socks5_port,
            upstream_socks5_user,
            upstream_socks5_pass,
            timezone,
            enabled,
            account_id,
        ),
    )
    return account_id


def _infer_deleted_account_id(conn: sqlite3.Connection, account_name: str) -> Optional[int]:
    """
    从历史 run 的 flows_dir 反推被误删账号的原始 ID。

    :param conn: 当前数据库连接
    :param account_name: 账号 profile 名
    :return: 能唯一推断时返回原 account_id，否则返回 None
    """
    existing = conn.execute(
        "SELECT id FROM accounts WHERE name=?",
        (account_name,),
    ).fetchone()
    if existing:
        return None
    flows_prefix = str(FLOWS_DIR / account_name) + "/%"
    rows = conn.execute(
        "SELECT r.account_id, COUNT(*) AS n "
        "FROM runs r LEFT JOIN accounts a ON a.id=r.account_id "
        "WHERE a.id IS NULL AND r.flows_dir LIKE ? "
        "GROUP BY r.account_id ORDER BY n DESC",
        (flows_prefix,),
    ).fetchall()
    if len(rows) != 1:
        return None
    return int(rows[0]["account_id"])


def get_runtime_model_setting() -> Optional[str]:
    """
    读取 WebUI 保存的普通 / 批量 run 默认模型覆盖值。

    :return: 模型覆盖值；未配置时返回 None
    """
    conn = get_db()
    try:
        row = conn.execute(
            "SELECT value FROM app_settings WHERE key=?",
            (_RUNTIME_MODEL_SETTING_KEY,),
        ).fetchone()
    finally:
        conn.close()
    if not row:
        return None
    try:
        return _normalize_claude_model_name(row["value"], "runtime_model")
    except ValueError:
        # SQLite 是运行态存储，遇到旧版本遗留坏值时不能静默传给 worker。
        raise ValueError("已保存的默认模型配置无效，请在 WebUI 运行页重置")


def effective_runtime_model() -> str:
    """
    返回普通 / 批量 run 当前生效的默认模型。

    :return: WebUI 覆盖值优先，否则返回 `.env` 的 CLAUDE_DEFAULT_MODEL
    """
    return get_runtime_model_setting() or CLAUDE_DEFAULT_MODEL


def save_runtime_model_setting(value: Optional[str]) -> Optional[str]:
    """
    保存或清除 WebUI 默认模型覆盖值。

    :param value: 用户提交的模型名；空值表示清除覆盖并回退到 `.env`
    :return: 保存后的模型名；清除覆盖时返回 None
    """
    try:
        model = _normalize_claude_model_name(value, "default_model")
    except ValueError as e:
        raise HTTPException(400, str(e))

    with _db_lock:
        conn = get_db()
        try:
            with conn:
                if model is None:
                    conn.execute(
                        "DELETE FROM app_settings WHERE key=?",
                        (_RUNTIME_MODEL_SETTING_KEY,),
                    )
                    return None
                conn.execute(
                    "INSERT INTO app_settings(key, value, updated_at) VALUES(?,?,julianday('now')) "
                    "ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=julianday('now')",
                    (_RUNTIME_MODEL_SETTING_KEY, model),
                )
                return model
        finally:
            conn.close()


def get_runtime_effort_setting() -> Optional[str]:
    """
    读取 WebUI 保存的普通 / 批量 run 思考预算覆盖值。

    :return: 思考预算覆盖值；未配置时返回 None
    """
    conn = get_db()
    try:
        row = conn.execute(
            "SELECT value FROM app_settings WHERE key=?",
            (_RUNTIME_EFFORT_SETTING_KEY,),
        ).fetchone()
    finally:
        conn.close()
    if not row:
        return None
    try:
        return _normalize_claude_effort_level(row["value"], "runtime_effort")
    except ValueError:
        # SQLite 是运行态存储，遇到旧版本遗留坏值时不能静默传给 worker。
        raise ValueError("已保存的思考预算配置无效，请在 WebUI 运行页重置")


def effective_runtime_effort() -> str:
    """
    返回普通 / 批量 run 当前生效的思考预算。

    :return: WebUI 覆盖值优先，否则返回 `.env` 的 CLAUDE_CODE_EFFORT_LEVEL
    """
    return get_runtime_effort_setting() or CLAUDE_CODE_EFFORT_LEVEL


def save_runtime_effort_setting(value: Optional[str]) -> Optional[str]:
    """
    保存或清除 WebUI 思考预算覆盖值。

    :param value: 用户提交的思考预算；空值表示清除覆盖并回退到 `.env`
    :return: 保存后的思考预算；清除覆盖时返回 None
    """
    try:
        effort = _normalize_claude_effort_level(value, "effort_level")
    except ValueError as e:
        raise HTTPException(400, str(e))

    with _db_lock:
        conn = get_db()
        try:
            with conn:
                if effort is None:
                    conn.execute(
                        "DELETE FROM app_settings WHERE key=?",
                        (_RUNTIME_EFFORT_SETTING_KEY,),
                    )
                    return None
                conn.execute(
                    "INSERT INTO app_settings(key, value, updated_at) VALUES(?,?,julianday('now')) "
                    "ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=julianday('now')",
                    (_RUNTIME_EFFORT_SETTING_KEY, effort),
                )
                return effort
        finally:
            conn.close()


def get_runtime_claude_code_version_setting() -> Optional[str]:
    """
    读取 WebUI 保存的 Claude Code 版本覆盖值。

    :return: Claude Code 版本覆盖值；未配置时返回 None
    """
    conn = get_db()
    try:
        row = conn.execute(
            "SELECT value FROM app_settings WHERE key=?",
            (_RUNTIME_CLAUDE_CODE_VERSION_SETTING_KEY,),
        ).fetchone()
    finally:
        conn.close()
    if not row:
        return None
    try:
        return _normalize_claude_code_version(row["value"], "runtime_claude_code_version")
    except ValueError:
        # SQLite 是运行态存储，遇到旧版本遗留坏值时不能静默传给 worker。
        raise ValueError("已保存的 Claude Code 版本配置无效，请在 WebUI 运行页重置")


def effective_claude_code_version() -> str:
    """
    返回当前新 worker 应使用的 Claude Code CLI 版本。

    :return: WebUI 覆盖值优先，否则返回 `.env` 的 CLAUDE_CODE_VERSION
    """
    return get_runtime_claude_code_version_setting() or CLAUDE_CODE_VERSION


def _resolve_run_claude_code_version(value: Optional[str]) -> str:
    """
    解析 run 已保存的 Claude Code 版本，兼容缺少快照的旧内部调用。

    :param value: run 或调度 payload 中的版本快照
    :return: 规范化后的快照；空值时返回当前有效版本
    """
    return (
        _normalize_claude_code_version(value, "run.claude_code_version")
        or effective_claude_code_version()
    )


def _ensure_run_claude_code_version(run: dict) -> str:
    """
    确保历史 run 在继续对话前拥有稳定的 Claude Code 版本快照。

    :param run: `runs` 表行字典
    :return: 已存在或刚补写的版本快照
    """
    version = _normalize_claude_code_version(
        run.get("claude_code_version"),
        "run.claude_code_version",
    )
    if version:
        return version

    fallback_version = effective_claude_code_version()
    with _db_lock:
        conn = get_db()
        try:
            with conn:
                row = conn.execute(
                    "SELECT claude_code_version FROM runs WHERE id=?",
                    (run["id"],),
                ).fetchone()
                if not row:
                    raise ValueError(f"运行 {run['id']} 不存在")
                version = _normalize_claude_code_version(
                    row["claude_code_version"],
                    "run.claude_code_version",
                )
                if not version:
                    # 历史行没有快照时只补写一次，避免后续页面配置变化再次影响该会话。
                    version = fallback_version
                    conn.execute(
                        "UPDATE runs SET claude_code_version=? "
                        "WHERE id=? AND claude_code_version IS NULL",
                        (version, run["id"]),
                    )
        finally:
            conn.close()
    run["claude_code_version"] = version
    return version


def _resolve_run_claude_effort_level(value: Optional[str]) -> str:
    """
    解析 run 已保存的思考预算，兼容缺少快照的旧内部调用。

    :param value: run 或调度 payload 中的思考预算快照
    :return: 规范化后的快照；空值时返回 `.env` 默认预算
    """
    return (
        _normalize_claude_effort_level(value, "run.claude_effort_level")
        or CLAUDE_CODE_EFFORT_LEVEL
    )


def _ensure_run_claude_effort_level(run: dict) -> str:
    """
    确保历史 run 在继续对话前拥有稳定的思考预算快照。

    :param run: `runs` 表行字典
    :return: 已存在或刚补写的思考预算快照
    """
    effort_level = _normalize_claude_effort_level(
        run.get("claude_effort_level"),
        "run.claude_effort_level",
    )
    if effort_level:
        return effort_level

    fallback_effort_level = CLAUDE_CODE_EFFORT_LEVEL
    with _db_lock:
        conn = get_db()
        try:
            with conn:
                row = conn.execute(
                    "SELECT claude_effort_level FROM runs WHERE id=?",
                    (run["id"],),
                ).fetchone()
                if not row:
                    raise ValueError(f"运行 {run['id']} 不存在")
                effort_level = _normalize_claude_effort_level(
                    row["claude_effort_level"],
                    "run.claude_effort_level",
                )
                if not effort_level:
                    # 旧版继续会话固定使用 .env；历史行因此只按该值补写一次。
                    effort_level = fallback_effort_level
                    conn.execute(
                        "UPDATE runs SET claude_effort_level=? "
                        "WHERE id=? AND claude_effort_level IS NULL",
                        (effort_level, run["id"]),
                    )
        finally:
            conn.close()
    run["claude_effort_level"] = effort_level
    return effort_level


def save_runtime_claude_code_version_setting(value: Optional[str]) -> Optional[str]:
    """
    保存或清除 WebUI Claude Code 版本覆盖值。

    :param value: 用户提交的版本号；空值表示清除覆盖并回退到 `.env`
    :return: 保存后的版本号；清除覆盖时返回 None
    """
    try:
        version = _normalize_claude_code_version(value, "claude_code_version")
    except ValueError as e:
        raise HTTPException(400, str(e))

    with _db_lock:
        conn = get_db()
        try:
            with conn:
                if version is None:
                    conn.execute(
                        "DELETE FROM app_settings WHERE key=?",
                        (_RUNTIME_CLAUDE_CODE_VERSION_SETTING_KEY,),
                    )
                    return None
                conn.execute(
                    "INSERT INTO app_settings(key, value, updated_at) VALUES(?,?,julianday('now')) "
                    "ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=julianday('now')",
                    (_RUNTIME_CLAUDE_CODE_VERSION_SETTING_KEY, version),
                )
                return version
        finally:
            conn.close()


TopicPromptMode = Literal["natural", "canonical"]
CapturePermissionMode = Literal[
    "manual",
    "acceptEdits",
    "plan",
    "auto",
    "dontAsk",
    "bypassPermissions",
]
_CAPTURE_PERMISSION_MODES = (
    "manual",
    "acceptEdits",
    "plan",
    "auto",
    "dontAsk",
    "bypassPermissions",
)


def _resolve_capture_permission_mode(value: Optional[str]) -> str:
    """
    解析抓包 run 保存的权限模式，兼容没有该快照的历史记录。

    :param value: API、调度 payload 或 runs 行中的权限模式
    :return: Claude Code CLI 支持的规范权限模式
    """
    mode = value.strip() if isinstance(value, str) else ""
    if not mode:
        return "bypassPermissions"
    if mode not in _CAPTURE_PERMISSION_MODES:
        raise ValueError(
            "capture permission mode 无效：只允许 manual, acceptEdits, plan, "
            "auto, dontAsk, bypassPermissions"
        )
    return mode

_NATURAL_TOPIC_PROMPT_CANDIDATE_COUNT = 12
_NATURAL_TOPIC_PROMPT_HISTORY_LIMIT = 64
_NATURAL_TOPIC_PROMPT_NGRAM_SIZE = 4

_NATURAL_TOPIC_PROMPT_STYLE_KEYWORDS = (
    ("data_ai", ("AI Applications", "AI Agents", "Data Visualization", "Data Operations", "Dashboard")),
    ("creative", ("Games", "Content Creation", "Education", "Creative", "Creativity")),
    (
        "product",
        ("Web", "Browser Extensions", "Collaboration", "Business", "Industry", "Team Knowledge", "Community", "Recordkeeping"),
    ),
    (
        "engineering",
        ("Command-Line", "Automation", "Developer Tools", "Hardware", "Edge", "Security", "Operations"),
    ),
)

_NATURAL_TOPIC_PROMPT_STYLE_OPENERS = {
    "engineering": (
        "I want to build {title}, a tool in the {category} category.",
        "Please implement {title} as a {category} project.",
        "I need a practical {category} project called {title}.",
        "Start with a usable version of {title} for the {category} space.",
    ),
    "product": (
        "I want to turn a {category} idea into a product called {title}.",
        "Please build the first version of {title} for the {category} space.",
        "The product requirement is {title}, aimed at a {category} use case.",
        "Create an initial release of {title}, positioned as a {category} product.",
    ),
    "data_ai": (
        "Build {title} for data or intelligent processing in the {category} space.",
        "The data or AI project for this task is {title}, in the {category} category.",
        "Implement the core workflow for the {category} project {title}.",
        "Create a {category} project named {title}.",
    ),
    "creative": (
        "Build an interactive version of {title} in the {category} category.",
        "Turn the {category} idea {title} into a working project.",
        "Create a small {category} project called {title}.",
        "Implement {title} as a demonstrable {category} experience.",
    ),
    "generic": (
        "I want to implement {title}, in the {category} category.",
        "The project for this task is {title}, which belongs to {category}.",
        "Please turn this requirement into a working project: {title} ({category}).",
        "Start with a complete first version of {title} for the {category} use case.",
    ),
}

_NATURAL_TOPIC_PROMPT_REQUIREMENTS = (
    "The main problem to solve is: {description}",
    "The core requirement is: {description}",
    "It should cover the following workflow: {description}",
    "The requested capabilities are: {description}",
    "The requirement can be summarized as follows: {description}",
)

_NATURAL_TOPIC_PROMPT_DELIVERIES = (
    "Implement the core workflow in the current workspace and deliver a runnable first version.",
    "Write the code in the existing directory and make the primary workflow usable end to end.",
    "Complete a version in this workspace that can be launched and demonstrated.",
    "Deliver a working first version that runs in the current project.",
    "Build a runnable version in the current directory, prioritizing a complete core workflow.",
)

_NATURAL_TOPIC_PROMPT_REPORTS = (
    "When finished, include the launch command, the scenarios you verified, and the trade-offs used to control scope.",
    "Explain how to run it, which inputs and outputs you tested, and which capabilities were intentionally deferred.",
    "Describe the run steps, validation results, and the key implementation trade-offs in the final report.",
    "Provide usage commands and test results, and explain what the first version leaves out.",
    "After completing it, state how to launch it, which paths you checked, and how you kept the scope manageable.",
)

_NATURAL_TOPIC_PROMPT_LAYOUTS = (
    "{opening}\n\n{requirement}\n\n{delivery} {report}",
    "{requirement}\n\n{opening}\n\n{delivery}\n{report}",
    "{opening} {requirement}\n\n{delivery}\n\n{report}",
    "{opening}\n{requirement}\n\n{delivery}\n\n{report}",
    "{opening}\n\n{requirement} {delivery}\n\n{report}",
)


def _topic_prompt_values(topic: dict) -> tuple[str, str, str]:
    """
    读取生成 prompt 使用的标准 topic 字段。

    :param topic: topic 行字典
    :return: `(title, category, description)`
    """
    title = str(topic["title"]).strip()
    category = str(topic.get("category") or "Uncategorized").strip()
    description = str(topic.get("description") or "").strip()
    return title, category, description


def _topic_prompt_style(category: str) -> str:
    """
    把题库分类映射到自然 prompt 的表达风格。

    :param category: topic 分类
    :return: 已定义的风格名称；未命中时返回 `generic`
    """
    for style, keywords in _NATURAL_TOPIC_PROMPT_STYLE_KEYWORDS:
        if any(keyword.casefold() in category.casefold() for keyword in keywords):
            return style
    return "generic"


def _build_natural_topic_prompt_candidates(topic: dict) -> list[str]:
    """
    从独立片段组合出一组语义等价的自然 prompt 候选。

    :param topic: topic 行字典
    :return: 不重复的自然 prompt 候选列表
    """
    title, category, description = _topic_prompt_values(topic)
    openers = _NATURAL_TOPIC_PROMPT_STYLE_OPENERS[_topic_prompt_style(category)]
    fragment_groups = (
        openers,
        _NATURAL_TOPIC_PROMPT_REQUIREMENTS,
        _NATURAL_TOPIC_PROMPT_DELIVERIES,
        _NATURAL_TOPIC_PROMPT_REPORTS,
        _NATURAL_TOPIC_PROMPT_LAYOUTS,
    )
    signature_count = 1
    for group in fragment_groups:
        signature_count *= len(group)
    selected_indexes = random.sample(
        range(signature_count),
        k=min(_NATURAL_TOPIC_PROMPT_CANDIDATE_COUNT, signature_count),
    )
    candidates: list[str] = []
    for selected_index in selected_indexes:
        offsets: list[int] = []
        # 直接解码组合索引，避免每个 topic 都先构造完整的笛卡尔积。
        for group in reversed(fragment_groups):
            selected_index, offset = divmod(selected_index, len(group))
            offsets.append(offset)
        opening, requirement, delivery, report, layout = (
            group[offset]
            for group, offset in zip(fragment_groups, reversed(offsets))
        )
        candidates.append(layout.format(
            opening=opening.format(title=title, category=category),
            requirement=requirement.format(description=description),
            delivery=delivery,
            report=report,
        ))
    return list(dict.fromkeys(candidates))


def _normalize_topic_prompt_fingerprint(prompt: str, topic: dict) -> str:
    """
    弱化 topic 专属文本，保留公共包装措辞用于相似度比较。

    :param prompt: 已生成或已持久化的 prompt
    :param topic: prompt 对应的 topic 行字典
    :return: 去除空白和标点后的归一化文本
    """
    title, category, description = _topic_prompt_values(topic)
    normalized = str(prompt)
    # 长字段先替换，避免标题同时出现在描述中时留下正文碎片。
    topic_values = sorted(
        {value for value in (description, title, category) if value},
        key=len,
        reverse=True,
    )
    for value in topic_values:
        normalized = normalized.replace(value, "topic content")
    return re.sub(r"[\W_]+", "", normalized.casefold())


def _topic_prompt_ngrams(text: str) -> frozenset[str]:
    """
    生成固定长度字符 n-gram 集合。

    :param text: 已归一化的 prompt 文本
    :return: 用于 Jaccard 比较的 n-gram 集合
    """
    if not text:
        return frozenset()
    if len(text) <= _NATURAL_TOPIC_PROMPT_NGRAM_SIZE:
        return frozenset({text})
    return frozenset(
        text[index:index + _NATURAL_TOPIC_PROMPT_NGRAM_SIZE]
        for index in range(len(text) - _NATURAL_TOPIC_PROMPT_NGRAM_SIZE + 1)
    )


def _topic_prompt_fingerprint(prompt: str, topic: dict) -> frozenset[str]:
    """
    生成已弱化 topic 正文的 prompt 指纹。

    :param prompt: prompt 文本
    :param topic: prompt 对应的 topic 行字典
    :return: 归一化后的 n-gram 集合
    """
    return _topic_prompt_ngrams(_normalize_topic_prompt_fingerprint(prompt, topic))


def _topic_prompt_similarity(
    left: frozenset[str],
    right: frozenset[str],
) -> float:
    """
    计算两个 prompt 指纹的 Jaccard 相似度。

    :param left: 左侧 prompt 指纹
    :param right: 右侧 prompt 指纹
    :return: 0 到 1 的相似度
    """
    if not left or not right:
        return 0.0
    if len(left) > len(right):
        left, right = right, left
    # 只遍历较小集合计数交集，避免每次比较都分配临时交集和并集。
    overlap = sum(1 for gram in left if gram in right)
    return overlap / (len(left) + len(right) - overlap)


def _select_low_similarity_topic_prompt(
    topic: dict,
    candidates: Sequence[str],
    recent_fingerprints: Sequence[frozenset[str]],
) -> str:
    """
    从候选中选择与近期公共措辞最不相似的一条。

    :param topic: 当前 topic 行字典
    :param candidates: 自然 prompt 候选
    :param recent_fingerprints: 近期持久化 prompt 的指纹
    :return: 最大历史相似度最低的候选；平分时随机选择
    """
    if not candidates:
        raise ValueError("自然 prompt 候选不能为空")
    if not recent_fingerprints:
        return random.choice(list(candidates))
    scored: list[tuple[float, str]] = []
    for candidate in candidates:
        fingerprint = _topic_prompt_fingerprint(candidate, topic)
        max_similarity = max(
            _topic_prompt_similarity(fingerprint, recent)
            for recent in recent_fingerprints
        )
        scored.append((max_similarity, candidate))
    best_score = min(score for score, _ in scored)
    return random.choice([
        candidate
        for score, candidate in scored
        if score == best_score
    ])


def _load_recent_topic_prompt_fingerprints(
    conn: sqlite3.Connection,
    limit: int = _NATURAL_TOPIC_PROMPT_HISTORY_LIMIT,
) -> deque[frozenset[str]]:
    """
    从现有 task 与 batch item 读取近期 topic prompt 指纹。

    :param conn: 当前 SQLite 连接
    :param limit: 最大指纹数量
    :return: 从旧到新排列的固定长度指纹窗口
    """
    safe_limit = max(1, int(limit))
    rows = conn.execute(
        "SELECT prompt, title, description, category FROM ("
        "SELECT ta.prompt, tp.title, tp.description, tp.category, "
        "ta.created_at, ta.id AS source_id "
        "FROM tasks ta JOIN topics tp ON ta.topic_id=tp.id "
        "WHERE ta.batch_id IS NULL "
        "UNION ALL "
        "SELECT bi.prompt, tp.title, tp.description, tp.category, "
        "bi.created_at, bi.id AS source_id "
        "FROM task_batch_items bi JOIN topics tp ON bi.topic_id=tp.id"
        ") recent ORDER BY created_at DESC, source_id DESC LIMIT ?",
        (safe_limit,),
    ).fetchall()
    fingerprints: deque[frozenset[str]] = deque(maxlen=safe_limit)
    for row in reversed(rows):
        fingerprints.append(_topic_prompt_fingerprint(
            row["prompt"],
            {
                "title": row["title"],
                "description": row["description"],
                "category": row["category"],
            },
        ))
    return fingerprints


def build_topic_prompt(
    topic: dict,
    mode: TopicPromptMode = "natural",
    recent_fingerprints: Optional[Sequence[frozenset[str]]] = None,
) -> str:
    """
    按 topic 和表达模式生成默认 Claude prompt。

    :param topic: topic 行字典
    :param mode: `natural` 随机选择自然表达，`canonical` 使用稳定规范模板
    :param recent_fingerprints: 近期 prompt 指纹；仅用于自然模式降低重复措辞
    :return: 默认 prompt 文本
    """
    title, category, description = _topic_prompt_values(topic)
    if mode == "canonical":
        return (
            f"Topic: {title}\n"
            f"Category: {category}\n"
            f"Description: {description}\n\n"
            "Implement a runnable MVP in the current directory.\n"
            "When finished, explain how to launch it, how you validated it, and the main trade-offs."
        )
    if mode != "natural":
        raise ValueError(f"不支持的 topic prompt 模式：{mode}")
    candidates = _build_natural_topic_prompt_candidates(topic)
    return _select_low_similarity_topic_prompt(
        topic,
        candidates,
        recent_fingerprints or (),
    )


def _resolve_topic_prompt(
    topic: dict,
    prompt_override: Optional[str],
    mode: TopicPromptMode,
    recent_fingerprints: Optional[Sequence[frozenset[str]]] = None,
) -> str:
    """
    解析任务最终使用的 prompt，自定义文本始终优先。

    :param topic: topic 行字典
    :param prompt_override: 用户提交的完整 prompt 覆盖
    :param mode: 未覆盖时使用的默认 prompt 表达模式
    :param recent_fingerprints: 近期 prompt 指纹；仅在默认自然模式下使用
    :return: 应持久化并下发给 worker 的最终 prompt
    """
    return prompt_override or build_topic_prompt(topic, mode, recent_fingerprints)


def _should_load_topic_prompt_history(
    prompt_override: Optional[str],
    mode: TopicPromptMode,
) -> bool:
    """
    判断当前请求是否需要读取近期自然 prompt 指纹。

    :param prompt_override: 用户提交的完整 prompt 覆盖
    :param mode: 未覆盖时使用的默认 prompt 表达模式
    :return: 仅默认自然模式返回 True
    """
    return not prompt_override and mode == "natural"


def normalize_claude_model_override(value: Optional[str]) -> Optional[str]:
    """
    规范化抓包 run 的一次性 Claude 模型覆盖。

    :param value: 用户提交的模型名或别名
    :return: trim 后的模型名；空值返回 None
    """
    try:
        return _normalize_claude_model_name(value, "model_override")
    except ValueError as e:
        raise HTTPException(400, str(e))


def _usage_window(value: object) -> Optional[dict]:
    """
    读取 usage 窗口对象，避免上游返回 null / 字符串时前端拿到不稳定结构。

    :param value: 原始 usage 窗口值
    :return: 合法窗口 dict；非法时返回 None
    """
    return value if isinstance(value, dict) else None


def _scoped_weekly_usage_window(usage: dict, model_name: str) -> Optional[dict]:
    """
    从新版 usage `limits` 数组里提取指定模型的周用量窗口。

    :param usage: OAuth usage API 返回对象
    :param model_name: `scope.model.display_name` 里的模型展示名
    :return: `{utilization, resets_at}` 窗口；未命中时返回 None
    """
    limits = usage.get("limits")
    if not isinstance(limits, list):
        return None
    expected = model_name.casefold()
    for item in limits:
        if not isinstance(item, dict):
            continue
        scope = item.get("scope")
        model = scope.get("model") if isinstance(scope, dict) else None
        if not isinstance(model, dict):
            continue
        display_name = model.get("display_name")
        model_id = model.get("id")
        matches_name = isinstance(display_name, str) and display_name.casefold() == expected
        matches_id = isinstance(model_id, str) and expected in model_id.casefold()
        if not (matches_name or matches_id):
            continue
        kind = item.get("kind")
        group = item.get("group")
        if kind != "weekly_scoped" and group != "weekly":
            continue
        percent = item.get("percent")
        if not isinstance(percent, (int, float)):
            continue
        reset_at = item.get("resets_at")
        return {
            "utilization": percent,
            "resets_at": reset_at if isinstance(reset_at, str) else None,
        }
    return None


def _usage_window_with_scoped_fallback(usage: dict, key: str, model_name: str) -> Optional[dict]:
    """
    优先读取顶层窗口，缺失时从 `limits` scoped 结构回填。

    :param usage: OAuth usage API 返回对象
    :param key: 顶层窗口字段名
    :param model_name: scoped limit 里的模型展示名
    :return: 前端可展示的用量窗口
    """
    return _usage_window(usage.get(key)) or _scoped_weekly_usage_window(usage, model_name)


def _format_quota_result(raw: dict) -> dict:
    """
    把 OAuth usage API 原始 JSON 转成前端稳定字段。

    :param raw: OAuth usage API 返回对象，或 worker 探测错误对象
    :return: 额度展示对象
    """
    if not isinstance(raw, dict):
        return {
            "ok": False,
            "message": "usage unavailable",
            "five_hour": None,
            "seven_day": None,
            "seven_day_sonnet": None,
            "seven_day_fable": None,
            "raw": raw,
        }
    usage = raw.get("usage") if isinstance(raw.get("usage"), dict) else raw
    if not isinstance(usage, dict):
        return {
            "ok": False,
            "message": raw.get("error") if isinstance(raw, dict) else "usage unavailable",
            "five_hour": None,
            "seven_day": None,
            "seven_day_sonnet": None,
            "seven_day_fable": None,
            "raw": raw,
        }
    if raw.get("error"):
        message = str(raw.get("error"))
        retry_after = raw.get("retry_after_sec")
        if isinstance(retry_after, int) and retry_after > 0:
            message = f"{message}；请等待约 {retry_after}s 后再查"
        return {
            "ok": False,
            "message": message,
            "five_hour": None,
            "seven_day": None,
            "seven_day_sonnet": None,
            "seven_day_fable": None,
            "raw": raw,
        }
    five_hour = _usage_window(usage.get("five_hour"))
    seven_day = _usage_window(usage.get("seven_day"))
    return {
        "ok": bool(five_hour or seven_day),
        "message": "" if five_hour or seven_day else "usage API 未返回 5h/7d 额度窗口",
        "five_hour": five_hour,
        "seven_day": seven_day,
        "seven_day_sonnet": _usage_window(usage.get("seven_day_sonnet")),
        "seven_day_fable": _usage_window_with_scoped_fallback(usage, "seven_day_fable", "Fable"),
        "raw": raw,
    }


def _quota_account_error(result: dict) -> str | None:
    """从手动额度失败的结构化错误中识别明确永久账号状态。

    :param result: 既有标准化查询结果，包含原始 error/status
    :return: account_on_hold、invalid_grant 或 None；普通状态码不推断封禁
    """
    raw = result.get("raw")
    if result.get("ok") or not isinstance(raw, dict):
        return None
    status = raw.get("status")
    if status is not None and (type(status) is not int or not 400 <= status < 500 or status == 429):
        return None
    error = raw.get("error")
    if isinstance(error, str) and error.startswith("HTTP "):
        try:
            body = json.loads(error.partition(": ")[2])
            error = body.get("error") if isinstance(body, dict) else None
        except ValueError:
            return None
    code = (error.get("code") or error.get("type")) if isinstance(error, dict) else error
    return code if code in ("account_on_hold", "invalid_grant") else None


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
_ACCOUNT_TIMEZONES = ["UTC", *_TZ_POOL]
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


def _normalize_account_timezone(value: Optional[str]) -> Optional[str]:
    """
    规范化账号显式时区，空值表示沿用账号名派生。

    :param value: 前端或 DB 传入的时区值
    :return: 允许列表内的 IANA 时区名；空值返回 None
    """
    if value is None:
        return None
    timezone = value.strip()
    if not timezone:
        return None
    if timezone not in _ACCOUNT_TIMEZONES:
        raise ValueError(
            "invalid account timezone: must be one of "
            + ", ".join(_ACCOUNT_TIMEZONES)
        )
    return timezone


def _effective_account_timezone(
    account_or_name: dict | str,
    explicit_timezone: Optional[str] = None,
) -> str:
    """
    计算账号实际用于 worker 环境变量的时区。

    :param account_or_name: accounts 表行字典或账号名
    :param explicit_timezone: 临时显式时区；None 时读取账号行 `timezone`
    :return: v3 已固化时区、首次默认或旧模式派生时区
    """
    if isinstance(account_or_name, str):
        account_name = account_or_name
        timezone = explicit_timezone
    else:
        account_name = str(account_or_name["name"])
        timezone = (
            explicit_timezone
            if explicit_timezone is not None
            else account_or_name.get("timezone")
        )
    normalized = _normalize_account_timezone(timezone)
    if account_runtime:
        # 页面和旧 Runner 的准备阶段只读已有记录，不能为展示创建新环境。
        connection = account_runtime.database()
        try:
            account_id = account_or_name.get("id") if isinstance(account_or_name, dict) else None
            row = connection.execute("SELECT fingerprint_json FROM account_environments WHERE account_id=? OR name=?",
                (account_id, account_name)).fetchone()
        finally:
            connection.close()
        return AccountRuntime.execution_environment(dict(row))["TZ"] if row else normalized or V3_DEFAULT_TIMEZONE
    return normalized or derive_fingerprint(account_name)["tz"]


def _wait_sidecar_ready(client: "docker.DockerClient", sidecar_id: str) -> None:
    """
    等 sidecar 自己的透明代理与通用 DNS resolver 就绪。

    :param client: Docker client
    :param sidecar_id: sidecar 容器 ID
    :return: None
    """
    deadline = time.monotonic() + SIDECAR_READY_TIMEOUT
    last_output = ""
    while time.monotonic() < deadline:
        try:
            ex = client.api.exec_create(
                sidecar_id,
                [
                    "sh",
                    "-lc",
                    (
                        "if [ -f /tmp/sidecar-ready ]; then exit 0; fi; "
                        f"if {_SIDECAR_DNS_READY_SH}; then exit 0; fi; "
                        "tail -30 /var/log/unbound.log 2>/dev/null || true; "
                        "tail -30 /var/log/mitmdump.log 2>/dev/null || true; "
                        "exit 1"
                    ),
                ],
                stdout=True,
                stderr=True,
                environment={"DNS_READY_HOST": DNS_READY_HOST},
            )
            raw = client.api.exec_start(ex["Id"])
            inspected = client.api.exec_inspect(ex["Id"])
            last_output = raw.decode("utf-8", errors="replace").strip()
            if inspected.get("ExitCode") == 0:
                return
        except Exception as exc:
            last_output = str(exc)
        time.sleep(1)
    raise RuntimeError(
        f"sidecar network/DNS not ready after {int(SIDECAR_READY_TIMEOUT)}s: "
        f"{last_output[-1000:]}"
    )

# ============== 被动额度状态 ==============
def _quota_identity(account: dict) -> str:
    """读取稳定账号身份；不把轮换中的 AT/RT 当成新账号。"""
    identity = {"account_id": int(account["id"]), "binding": account.get("cc2api_account_id")}
    try:
        top = json.loads((PROFILES_DIR / account["name"] / ".claude.json").read_text())
        oauth = top.get("oauthAccount") or {}
        if not oauth.get("accountUuid"):
            raise ValueError("账号身份暂不可读")
        identity.update(uuid=oauth.get("accountUuid"), org=oauth.get("organizationUuid"))
    except (OSError, ValueError, AttributeError):
        # 临时文件不可读时沿用同一绑定的已知身份，不能意外清空耗尽证据。
        conn = get_db()
        try:
            row = conn.execute("SELECT identity FROM account_quota_states WHERE account_id=?",
                               (account["id"],)).fetchone()
            previous = json.loads(row["identity"]) if row else {}
            if all(previous.get(key) == value for key, value in identity.items()):
                return row["identity"] if row else json.dumps(identity, sort_keys=True)
        finally:
            conn.close()
    return json.dumps(identity, sort_keys=True)


def _write_quota_json(path: Path, payload: dict) -> None:
    """原子发布内部额度文件，目录挂载使替换后的文件对子容器可见。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + f".{uuid.uuid4().hex}.tmp")
    try:
        temporary.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


class QuotaGuard:
    """
    消费真实响应并维护额度门禁，v3 自动执行只读取本地被动观察。

    :param runner: 既有容器运行器
    """

    def __init__(self, runner: Runner) -> None:
        """
        初始化消费锁与后台停止信号。

        :param runner: 既有运行器，仅用于恢复收口
        :return: None
        """
        self.runner = runner
        self._lock = threading.RLock()
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def snapshot(self, account: dict) -> dict:
        """
        读取被动状态及当前等待判定。

        :param account: 账号行
        :return: 不含凭据的额度摘要
        """
        identity = _quota_identity(account)
        conn = get_db()
        try:
            row = conn.execute("SELECT * FROM account_quota_states WHERE account_id=?",
                               (account["id"],)).fetchone()
            state = json.loads(row["state_json"]) if row and row["identity"] == identity else {}
            recovery_source = row["recovery_source"] if row and row["identity"] == identity else None
        finally:
            conn.close()
        decision = quota_decision(state, time.time())
        if state.get("account_error"):
            decision.update(blocked=True, retry_ready=False, resume_at=None, exhausted=[],
                            message=f"{state['account_error']}：账号异常，需重新授权或人工核实")
        return {**state, **decision, "source": state.get("source") or "passive", "identity": identity,
                "recovery_source": recovery_source, "known": bool(state.get("windows"))}

    def policy_snapshot(
        self,
        account: dict,
        workload: Literal["normal", "warmup"],
        source: Optional[str] = None,
        *,
        quota_state: Optional[dict] = None,
    ) -> dict:
        """读取普通任务或养号使用的账号级阈值判定。

        :param account: 当前账号及身份
        :param workload: `normal` 普通任务或 `warmup` 养号
        :param source: 实际启动来源；页面/触发检查不指定来源
        :param quota_state: 发布时复用的共用额度快照；省略时读取当前事实
        :return: 阈值判定；养号结果还包含内部持久许可
        """
        if workload not in ("normal", "warmup"):
            raise ValueError(f"不支持的额度策略工作负载：{workload}")
        state = self.snapshot(account) if quota_state is None else quota_state
        conn = get_db()
        try:
            row = conn.execute("SELECT warmup_quota_5h_limit_percent,warmup_quota_7d_limit_percent "
                               "FROM accounts WHERE id=?", (account["id"],)).fetchone()
            record = conn.execute("SELECT * FROM warmup_quota_admissions WHERE account_id=? AND identity=?",
                                  (account["id"], state["identity"])).fetchone()
        finally:
            conn.close()
        limits = {
            "five_hour": row["warmup_quota_5h_limit_percent"] if row else None,
            "seven_day": row["warmup_quota_7d_limit_percent"] if row else None,
        }
        return self._policy_decision(
            state,
            limits,
            workload,
            source,
            dict(record) if record else None,
        )

    def policy_snapshots(
        self,
        account: dict,
        *,
        quota_state: Optional[dict] = None,
    ) -> dict[str, dict]:
        """从同一额度、配置和许可快照生成普通任务与养号判定。

        :param account: 当前账号及身份
        :param quota_state: 可选的共用额度快照；省略时读取一次当前事实
        :return: 包含 `normal` 和 `warmup` 的判定字典
        """
        state = self.snapshot(account) if quota_state is None else quota_state
        conn = get_db()
        try:
            row = conn.execute(
                "SELECT warmup_quota_5h_limit_percent,warmup_quota_7d_limit_percent "
                "FROM accounts WHERE id=?",
                (account["id"],),
            ).fetchone()
            record = conn.execute(
                "SELECT * FROM warmup_quota_admissions WHERE account_id=? AND identity=?",
                (account["id"], state["identity"]),
            ).fetchone()
        finally:
            conn.close()
        limits = {
            "five_hour": row["warmup_quota_5h_limit_percent"] if row else None,
            "seven_day": row["warmup_quota_7d_limit_percent"] if row else None,
        }
        admission = dict(record) if record else None
        return {
            workload: self._policy_decision(
                state,
                limits,
                workload,
                admission=admission,
            )
            for workload in ("normal", "warmup")
        }

    def _policy_decision(
        self,
        state: dict,
        limits: dict,
        workload: Literal["normal", "warmup"],
        source: Optional[str] = None,
        admission: Optional[dict] = None,
    ) -> dict:
        """基于已固定事实计算单个工作负载的阈值判定。

        :param state: 同一账号身份的额度快照
        :param limits: 同一时点读取的 5h/7d 阈值
        :param workload: `normal` 普通任务或 `warmup` 养号
        :param source: 实际启动来源；页面摘要不指定
        :param admission: 同一时点读取的养号单次许可
        :return: 指定工作负载的阈值判定
        """
        decision = warmup_quota_decision(state, limits, time.time())
        if account_runtime:
            windows = state.get("windows") or {}
            renewal = [key for key in decision["unknown"] if limits.get(key) is not None
                and (windows.get(key, {}).get("reset_at") or float("inf")) <= time.time()
                and (windows.get(key, {}).get("utilization") or 0) >= limits[key]]
            periods = json.loads(decision["window_key"])
            for key, period in periods.items():
                period.append(limits[key])
            for key in ("five_hour", "seven_day", "unknown"):
                window = windows.get(key, {})
                reset = window.get("reset_at")
                if window.get("exhausted") and reset is not None and reset <= time.time():
                    renewal.append("common:" + key)
                    periods["common:" + key] = [reset]
            # 共同耗尽不受阈值开关影响；持久周期键也覆盖尚未取得新观察的恢复。
            decision.update(policy_key="v3-passive-recovery", window_key=json.dumps(periods, sort_keys=True))
            # 已命中阈值的旧窗口到期后，只让一个已有执行更新；首次未知不制造人工查询门禁。
            used = bool(renewal) and warmup_sample_used({**decision, "unknown": renewal}, admission)
            label = "普通任务" if workload == "normal" else "养号"
            decision.update(admission=admission, sample_used=bool(used), sample_required=bool(renewal),
                blocked=bool(decision["hit"]) or bool(used and (source is None or admission["source"] != source)),
                refresh_retry_at=None)
            if decision["hit"]:
                names = " / ".join("5h" if key == "five_hour" else "7d" for key in decision["hit"])
                decision["message"] = f"{names} 已用达到阈值，{label}等待窗口重置或被动额度更新"
            elif used:
                decision.update(resume_at=None, message="本窗口的正常恢复机会已使用，等待被动额度更新；可手动核实")
            elif decision["unknown"]:
                decision.update(resume_at=None, message="额度未知，将从正常任务响应更新")
            else:
                decision["message"] = ""
            return decision
        if workload == "normal":
            decision.update(admission=None, sample_used=False)
            if not decision["enabled"]:
                return decision
            if decision["hit"]:
                names = " / ".join(
                    "5h" if key == "five_hour" else "7d"
                    for key in decision["hit"]
                )
                decision["message"] = f"{names} 已用达到任务阈值，普通任务等待额度更新"
            elif decision["sample_required"]:
                # 普通任务不能借用养号的一次正式请求机会，否则门禁本身仍会产生消费。
                decision.update(
                    blocked=True,
                    resume_at=None,
                    message="任务额度未知或窗口已到期，请先手动查询额度",
                )
            return decision
        used = decision["sample_required"] and warmup_sample_used(decision, admission)
        decision.update(admission=admission, sample_used=bool(used))
        if used and (source is None or admission["source"] != source):
            decision.update(blocked=True, resume_at=None,
                            message="养号单次额度更新机会已使用，等待新的真实额度或调整阈值")
        return decision

    def warmup_snapshot(
        self,
        account: dict,
        source: Optional[str] = None,
        *,
        quota_state: Optional[dict] = None,
    ) -> dict:
        """兼容读取养号阈值和单次正式请求机会。

        :param account: 当前账号及身份
        :param source: 实际启动来源；页面/触发检查不指定来源
        :param quota_state: 发布时复用的共用额度快照；省略时读取当前事实
        :return: 养号判定及内部持久许可
        """
        return self.policy_snapshot(
            account,
            "warmup",
            source,
            quota_state=quota_state,
        )

    def _admit_warmup(self, account: dict, source: str, workload: Optional[str] = "warmup") -> bool:
        """复用持久许可认领正式执行更新；v3 普通任务与养号共享恢复机会。"""
        decision = self.policy_snapshot(account, workload or "normal", source)
        if workload is None and account_runtime:
            # 续聊／抓包忽略百分比阈值，但不能绕过共同耗尽的持久单次恢复。
            decision = self._policy_decision(self.snapshot(account),
                {"five_hour": None, "seven_day": None}, "normal", source, decision["admission"])
        if decision["blocked"]:
            return False
        if not decision["sample_required"] or decision["sample_used"]:
            return True
        identity = _quota_identity(account)
        with _db_lock:
            conn = get_db()
            try:
                with conn:
                    conn.execute("INSERT INTO warmup_quota_admissions(account_id,identity,policy_key,window_key,source,created_at) "
                                 "VALUES(?,?,?,?,?,?) ON CONFLICT(account_id) DO UPDATE SET identity=excluded.identity,"
                                 "policy_key=excluded.policy_key,window_key=excluded.window_key,source=excluded.source,created_at=excluded.created_at",
                                 (account["id"], identity, decision["policy_key"], decision["window_key"], source, time.time()))
            finally:
                conn.close()
        return True

    def _publish(self, account: dict) -> dict:
        """发布最新门禁和本地 AT 哈希；此文件不进入 API 响应。"""
        # 配置入口也会发布；读取到替换文件必须串行，防止旧快照覆盖新响应。
        with self._lock:
            snapshot = self.snapshot(account)
            path = BENCH_DATA / "quota" / str(account["id"]) / "state.json"
            hashes = set()
            try:
                previous = json.loads(path.read_text())
                if previous.get("identity") == snapshot["identity"]:
                    hashes.update(previous.get("token_hashes", []))
            except (OSError, ValueError):
                pass
            try:
                credentials = json.loads((PROFILES_DIR / account["name"] / ".credentials.json").read_text())
                token = (credentials.get("claudeAiOauth") or {}).get("accessToken")
                if isinstance(token, str) and token:
                    hashes.add(hashlib.sha256(token.encode()).hexdigest())
            except (OSError, ValueError, AttributeError):
                pass
            policies = self.policy_snapshots(account, quota_state=snapshot)
            _write_quota_json(path, {
                **snapshot,
                "token_hashes": sorted(hashes),
                "quota_policy": policies["normal"],
                "warmup_quota": policies["warmup"],
            })
            return snapshot

    def admit(
        self,
        account: dict,
        source: str,
        warmup: bool = False,
        workload: Optional[Literal["normal", "warmup"]] = None,
    ) -> bool:
        """
        认领启动机会；到期只放行一个已有正常执行，等待其真实响应。

        :param account: 锁内重读的账号行
        :param source: 执行来源及代次
        :param warmup: 兼容旧调用的养号标记
        :param workload: `normal` 检查普通任务阈值，`warmup` 检查养号阈值，None 只检查共同额度
        :return: 是否可以创建正式 worker
        """
        effective_workload = workload or ("warmup" if warmup else None)
        with self._lock:
            self.consume(account)
            snapshot = self.snapshot(account)
            if snapshot["blocked"]:
                self._publish(account)
                return False
            if snapshot["retry_ready"] and snapshot.get("recovery_source") not in (None, source):
                return False
            if effective_workload == "normal" and self.policy_snapshot(
                account,
                "normal",
                source,
                quota_state=snapshot,
            )["blocked"]:
                self._publish(account)
                return False
            if (account_runtime or effective_workload == "warmup") and not self._admit_warmup(account, source, effective_workload):
                self._publish(account)
                return False
            if snapshot["retry_ready"]:
                with _db_lock:
                    conn = get_db()
                    try:
                        with conn:
                            row = conn.execute("SELECT recovery_source FROM account_quota_states "
                                               "WHERE account_id=? AND identity=?",
                                               (account["id"], snapshot["identity"])).fetchone()
                            if row and row["recovery_source"] not in (None, source):
                                return False
                            conn.execute("UPDATE account_quota_states SET recovery_source=? "
                                         "WHERE account_id=? AND identity=?",
                                         (source, account["id"], snapshot["identity"]))
                    finally:
                        conn.close()
            self._publish(account)
            return True

    def release(self, account: dict, source: str) -> None:
        """
        执行退出后释放恢复认领，旧代次不能释放新执行的认领。

        :param account: 执行使用的账号
        :param source: 本次执行来源
        :return: None
        """
        with self._lock:
            with _db_lock:
                conn = get_db()
                try:
                    with conn:
                        conn.execute("UPDATE account_quota_states SET recovery_source=NULL "
                                     "WHERE account_id=? AND recovery_source=?", (account["id"], source))
                finally:
                    conn.close()
            self._publish(account)

    def prepare(self, account: dict, source: str, flows: Path, control: Path, warmup: bool = False) -> dict:
        """
        登记观察来源并创建只读门禁挂载；不创建任何探测流量。

        :param account: 当前账号
        :param source: run/continue 及其代次
        :param flows: 本次观察所在目录
        :param control: 本次执行独立控制目录
        :param warmup: 当前执行是否为养号；只影响 Recorder 的单次请求收尾协议
        :return: sidecar 的内部环境变量
        """
        with self._lock:
            flows.mkdir(parents=True, exist_ok=True)
            control.mkdir(parents=True, exist_ok=True)
            snapshot = self._publish(account)
            sample_required = bool(
                warmup
                and self.warmup_snapshot(
                    account,
                    source,
                    quota_state=snapshot,
                )["sample_required"]
            )
            paths = [(source, flows / "passive-quota.jsonl")]
            if account_runtime:
                paths.append(("cli:" + source, flows / "cli/cli-quota.jsonl"))
            with _db_lock:
                conn = get_db()
                try:
                    with conn:
                        for observation_source, path in paths:
                            offset = path.stat().st_size if path.exists() else 0
                            conn.execute("INSERT OR IGNORE INTO quota_observation_cursors"
                                         "(source,account_id,identity,path,byte_offset) VALUES(?,?,?,?,?)",
                                         (observation_source, account["id"], snapshot["identity"], str(path), offset))
                finally:
                    conn.close()
            return {"QUOTA_SOURCE": source, "QUOTA_IDENTITY": snapshot["identity"],
                    "QUOTA_WARMUP": "1" if warmup else "0",
                    "QUOTA_SAMPLE_REQUIRED": "1" if sample_required else "0",
                    "QUOTA_STATE_FILE": "/quota-account/state.json",
                    "QUOTA_SIGNAL_FILE": "/quota-control/pause.json",
                    "QUOTA_OBSERVATIONS_FILE": "/flows/passive-quota.jsonl",
                    "QUOTA_CREDENTIALS_FILE": "/quota-credentials/.credentials.json"}

    def _observe(self, account: dict, identity: str, observation: dict,
                 cursor: Optional[tuple[str, str, int]] = None) -> None:
        """在一个短事务中提交窗口和游标，允许响应只清理已到期的旧拒绝。"""
        with _db_lock:
            conn = get_db()
            try:
                with conn:
                    row = conn.execute("SELECT * FROM account_quota_states WHERE account_id=?",
                                       (account["id"],)).fetchone()
                    existing = json.loads(row["state_json"]) if row and row["identity"] == identity else {}
                    state = merge_quota_observation(existing, observation)
                    if float(observation["observed_at"]) >= float(existing.get("observed_at") or 0):
                        state["source"] = observation.get("origin") or "passive"
                    if observation.get("account_error") in ("account_on_hold", "invalid_grant"):
                        state["account_error"] = observation["account_error"]
                    observed = float(observation["observed_at"])
                    if observation.get("allowed"):
                        for key, window in state.get("windows", {}).items():
                            if (key not in observation.get("windows", {})
                                    and float(window.get("observed_at") or 0) < observed
                                    and (window.get("reset_at") is None or window["reset_at"] <= observed)):
                                window["exhausted"] = False
                                window["rejected"] = False
                                window["observed_at"] = observed
                    recovery = row["recovery_source"] if row and row["identity"] == identity else None
                    decision = quota_decision(state, observed)
                    if observation.get("allowed") and not decision["blocked"] and not decision["retry_ready"]:
                        recovery = None
                    conn.execute("INSERT INTO account_quota_states(account_id,identity,state_json,"
                                 "recovery_source,updated_at) VALUES(?,?,?,?,?) ON CONFLICT(account_id) "
                                 "DO UPDATE SET identity=excluded.identity,state_json=excluded.state_json,"
                                 "recovery_source=excluded.recovery_source,updated_at=excluded.updated_at",
                                 (account["id"], identity, json.dumps(state), recovery, time.time()))
                    if cursor:
                        source, file_identity, offset = cursor
                        conn.execute("UPDATE quota_observation_cursors SET file_identity=?,byte_offset=? "
                                     "WHERE source=?", (file_identity, offset, source))
            finally:
                conn.close()

    def consume(self, account: dict) -> None:
        """
        消费该账号登记的真实响应，半行留待下轮，旧身份样本忽略。

        :param account: 当前账号行
        :return: None
        """
        with self._lock:
            identity = _quota_identity(account)
            if account_runtime and account.get("cc2api_account_id") is not None:
                connection = get_db()
                try:
                    environment = connection.execute("SELECT * FROM account_environments WHERE account_id=?", (account["id"],)).fetchone()
                    if environment:
                        source = f"api:{environment['environment_id']}:{identity}"
                        path = account_runtime.data / "environments" / environment["environment_id"] / "flows" / "api" / "observations.jsonl"
                        with connection:
                            connection.execute("INSERT OR IGNORE INTO quota_observation_cursors(source,account_id,identity,path,byte_offset) VALUES(?,?,?,?,0)",
                                (source, account["id"], identity, str(path)))
                finally:
                    connection.close()
            conn = get_db()
            try:
                rows = conn.execute("SELECT * FROM quota_observation_cursors WHERE account_id=? AND identity=?",
                                    (account["id"], identity)).fetchall()
            finally:
                conn.close()
            for row in rows:
                path = Path(row["path"])
                if not path.exists():
                    continue
                stat = path.stat()
                file_identity = f"{stat.st_dev}:{stat.st_ino}"
                offset = int(row["byte_offset"])
                if (row["file_identity"] not in (None, file_identity) or offset > stat.st_size):
                    offset = 0
                with path.open("rb") as handle:
                    handle.seek(offset)
                    while True:
                        line = handle.readline()
                        if not line or not line.endswith(b"\n"):
                            break
                        offset = handle.tell()
                        observation = {"windows": {}, "observed_at": 0, "allowed": False}
                        try:
                            event = json.loads(line)
                            if event.get("source") == row["source"] and event.get("identity") == identity:
                                ts = float(event["ts"])
                                if 0 < ts <= time.time() + 5:
                                    if row["source"].startswith("cli:"):
                                        if event.get("origin") == "cli":
                                            observation = statusline_quota_observation(event.get("rate_limits"), ts)
                                    else:
                                        observation = quota_observation(event.get("headers") or {}, int(event["status"]), ts)
                                    if event.get("origin") == "api":
                                        observation["origin"] = "api"
                                    if not row["source"].startswith("cli:") and event.get("account_error") == "account_on_hold":
                                        observation["account_error"] = "account_on_hold"
                        except (ValueError, TypeError, KeyError, AttributeError):
                            pass
                        self._observe(account, identity, observation, (row["source"], file_identity, offset))
                        if observation.get("account_error"):
                            self.record_auth_failure(account, observation["account_error"])
            self._publish(account)

    def record_worker_limit(self, account: dict, window: str) -> None:
        """
        合成的明确额度错误作为拒绝补证；无可信 reset 时保持等待。

        :param account: 当前账号
        :param window: 已识别通用窗口或 unknown
        :return: None
        """
        with self._lock:
            now = time.time()
            if window == "unknown" and self.snapshot(account)["exhausted"]:
                return
            key = window if window in ("five_hour", "seven_day") else "unknown"
            self._observe(account, _quota_identity(account), {
                "windows": {key: {"observed_at": now, "rejected": True, "exhausted": True}},
                "observed_at": now, "allowed": False,
            })
            self._publish(account)

    def record_control_state(self, account: dict, source: str, payload: dict) -> None:
        """
        合并只读控制文件的补证，观察文件故障时仍保留等待事实。

        :param account: 当前账号
        :param source: 预期执行来源
        :param payload: sidecar 原子写入的控制对象
        :return: None
        """
        if not isinstance(payload, dict) or payload.get("source") != source or payload.get("status") != "quota_wait":
            return
        warmup_wait = False
        if payload.get("warmup_wait") is True and source.startswith("run:"):
            conn = get_db()
            try:
                run = conn.execute("SELECT run_kind,account_id,quota_attempt FROM runs WHERE id=?",
                                   (source.split(":")[1],)).fetchone()
            finally:
                conn.close()
            try:
                # workspace 的状态文件可写；只有 Recorder 私有控制补证才可跳过整体耗尽分类。
                control = json.loads((_quota_control(source.split(":")[1], source) / "pause.json").read_text())
                warmup_wait = bool(run and run["run_kind"] == "warmup" and run["account_id"] == account["id"]
                                   and source == _quota_source(source.split(":")[1], run["quota_attempt"])
                                   and control.get("source") == source and control.get("warmup_wait") is True
                                   and control.get("status") == "quota_wait")
                if warmup_wait:
                    payload = control
            except (OSError, ValueError, AttributeError):
                pass
        with self._lock:
            try:
                state = payload.get("quota_state") or {}
                if state.get("account_error") in ("account_on_hold", "invalid_grant"):
                    self.record_auth_failure(account, state["account_error"])
                    return
                observed = float(state.get("observed_at") or 0)
                if isinstance(state.get("windows"), dict) and 0 < observed <= time.time() + 5:
                    self._observe(account, _quota_identity(account), {**state, "allowed": False})
            except (ValueError, TypeError, AttributeError):
                pass
            snapshot = self.snapshot(account)
            if (not snapshot["exhausted"] and not snapshot.get("account_error")
                    and not warmup_wait):
                self.record_worker_limit(account, "unknown")
            self._publish(account)

    def record_auth_failure(self, account: dict, code: str) -> None:
        """
        固化不可自动恢复的账号错误并收口其它等待任务。

        :param account: 当前账号
        :param code: account_on_hold 或 invalid_grant
        :return: None
        """
        if code not in ("account_on_hold", "invalid_grant"):
            return
        with self._lock:
            identity = _quota_identity(account)
            with _db_lock:
                conn = get_db()
                try:
                    with conn:
                        row = conn.execute("SELECT state_json,identity FROM account_quota_states WHERE account_id=?", (account["id"],)).fetchone()
                        state = json.loads(row["state_json"]) if row and row["identity"] == identity else {}
                        state["account_error"] = code
                        conn.execute("INSERT INTO account_quota_states(account_id,identity,state_json,updated_at) VALUES(?,?,?,?) "
                                     "ON CONFLICT(account_id) DO UPDATE SET identity=excluded.identity,state_json=excluded.state_json,recovery_source=NULL,updated_at=excluded.updated_at",
                                     (account["id"], identity, json.dumps(state), time.time()))
                        conn.execute("UPDATE task_batches SET status='paused',next_launch_at=NULL WHERE account_id=? AND status IN ('active','quota_wait')", (account["id"],))
                        conn.execute("UPDATE task_batch_items SET status='auth_failed' WHERE run_id IN (SELECT id FROM runs WHERE account_id=? AND status='quota_wait')", (account["id"],))
                        conn.execute("UPDATE runs SET status='auth_failed',error=?,ended_at=? WHERE account_id=? AND status='quota_wait'", (code, time.time(), account["id"]))
                        conn.execute("UPDATE accounts SET warmup_enabled=0,warmup_next_run_at=NULL,warmup_last_status='paused',warmup_last_error=? "
                                     "WHERE id=? AND warmup_enabled=1", (code, account["id"]))
                finally:
                    conn.close()
            self._publish(account)

    def record_manual_usage(self, account: dict, usage: dict, source: str = "manual") -> dict:
        """
        合并用户手动 usage 查询的可信窗口。

        :param account: 查询对应账号
        :param usage: 已标准化的手动额度结果
        :param source: 观察来源；默认 manual，兼容历史导入来源
        :return: 本次有效窗口观察；失败结果返回空对象
        """
        if not usage.get("ok"):
            return {}
        headers = {}
        for key, name in (("five_hour", "5h"), ("seven_day", "7d"), ("seven_day_fable", "7d_oi")):
            window = usage.get(key)
            if isinstance(window, dict) and window.get("utilization") is not None:
                headers[f"anthropic-ratelimit-unified-{name}-utilization"] = str(float(window["utilization"]) / 100)
                headers[f"anthropic-ratelimit-unified-{name}-reset"] = window.get("resets_at")
        with self._lock:
            now = time.time()
            observation = quota_observation(headers, 200, now)
            for window in observation["windows"].values():
                window["usage_idle"] = False
            for key in ("five_hour", "seven_day", "seven_day_fable"):
                window = usage.get(key)
                if not isinstance(window, dict) or type(window.get("utilization")) not in (int, float) or window["utilization"] != 0:
                    continue
                reset = quota_timestamp(window.get("resets_at"))
                if window.get("resets_at") is None or (reset is not None and reset <= now):
                    # 不伪造未来重置时间，只记录本次人工查询确认的空闲窗口。
                    observation["windows"][key] = {"observed_at": now, "utilization": 0.0,
                        "reset_at": reset, "resets_at": window.get("resets_at"),
                        "rejected": False, "exhausted": False, "usage_idle": True}
            observation["origin"] = source
            self._observe(account, _quota_identity(account), observation)
            # 显式人工核实只影响未来新操作，已经收口的认证失败 run 不会自动重跑。
            if source == "manual" and all(key in observation["windows"] and not observation["windows"][key]["exhausted"] for key in ("five_hour", "seven_day")):
                with _db_lock:
                    conn = get_db()
                    try:
                        with conn:
                            row = conn.execute("SELECT state_json FROM account_quota_states WHERE account_id=?", (account["id"],)).fetchone()
                            state = json.loads(row["state_json"])
                            state.pop("account_error", None)
                            conn.execute("UPDATE account_quota_states SET state_json=? WHERE account_id=?", (json.dumps(state), account["id"]))
                    finally:
                        conn.close()
            self._publish(account)
            return observation

    def start(self) -> None:
        """启动被动观察后台，不执行任何主动额度请求。

        :return: None
        """
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """停止被动观察后台。

        :return: None
        """
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=5)

    def recover(self) -> None:
        """消费重启前观察并清理旧执行，恢复等待事实。

        :return: None
        """
        conn = get_db()
        try:
            accounts = [dict(row) for row in conn.execute("SELECT * FROM accounts WHERE deleted_at IS NULL")]
            runs = [dict(row) for row in conn.execute("SELECT * FROM runs WHERE deleted_at IS NULL "
                                                      "AND status IN ('quota_wait','queued','running','stopping')")]
            observed_runs = {row["source"].split(":")[1] for row in conn.execute("SELECT source FROM quota_observation_cursors WHERE source LIKE 'run:%'")}
        finally:
            conn.close()
        by_id = {account["id"]: account for account in accounts}
        for account in accounts:
            self.consume(account)
            state = self.snapshot(account)
            if state.get("account_error"):
                self.record_auth_failure(account, state["account_error"])
        for run in runs:
            account = by_id.get(run["account_id"])
            control_status = self._recover_control(account, run) if account else None
            state = self.snapshot(account) if account else {}
            threshold_guarded = False
            if account and run["run_kind"] == "warmup":
                threshold_guarded = bool(self.warmup_snapshot(account)["enabled"])
            elif account and run["run_kind"] == "normal":
                threshold_guarded = bool(self.policy_snapshot(account, "normal")["blocked"])
            if (run["status"] != "quota_wait" and not state.get("exhausted")
                    and not run["quota_attempt"] and run["id"] not in observed_runs and not control_status and not threshold_guarded):
                continue
            # 严格清理必须成功才启用自动恢复，覆盖容器已创建但 ID 尚未落库的崩溃点。
            self.runner.cleanup_quota_run(run["id"])
            if account and self._cancel_changed_identity(run, account):
                continue
            if account:
                self.consume(account)
                control_status = self._recover_control(account, run) or control_status
                state = self.snapshot(account)
            if control_status == "failed":
                # 原子控制文件损坏是执行失败，不能把未知门禁当成可恢复任务。
                with _db_lock:
                    conn = get_db()
                    try:
                        with conn:
                            conn.execute("UPDATE runs SET status=CASE WHEN stop_requested_at IS NOT NULL OR status='stopping' "
                                         "THEN 'stopped' ELSE 'failed' END,error='服务重启前额度门禁执行异常',ended_at=? "
                                         "WHERE id=? AND quota_attempt=? AND status IN ('queued','running','stopping','quota_wait')",
                                         (time.time(), run["id"], run["quota_attempt"]))
                    finally:
                        conn.close()
                if scheduler:
                    scheduler._update_batch_item_for_run(run["id"], scheduler._get_run_state(run["id"])["status"])
                continue
            if scheduler and run["status"] in ("queued", "running", "stopping"):
                if run["status"] == "stopping":
                    scheduler._update_attempt(run["id"], int(run["quota_attempt"]), status="stopped", ended_at=time.time())
                    scheduler._update_batch_item_for_run(run["id"], "stopped")
                elif account and (state.get("exhausted") or state.get("account_error") or run["quota_attempt"] or threshold_guarded):
                    scheduler._mark_quota_wait(run["id"], account, int(run["quota_attempt"]))
                else:
                    scheduler._update_attempt(run["id"], int(run["quota_attempt"]), status="failed", error="服务重启前执行已中断", ended_at=time.time())
                    scheduler._update_batch_item_for_run(run["id"], "failed")
                if warmup_scheduler:
                    warmup_scheduler.handle_run_terminal(run["id"], account.get("cc2api_account_id") if account else None)
        with _db_lock:
            conn = get_db()
            try:
                with conn:
                    conn.execute("UPDATE account_quota_states SET recovery_source=NULL")
            finally:
                conn.close()

    def _recover_control(self, account: dict, run: dict) -> Optional[str]:
        """恢复日志故障时留下的独立补证；身份和代次仍以原执行为准。"""
        if run.get("quota_identity") and run["quota_identity"] != _quota_identity(account):
            return None
        source = _quota_source(run["id"], int(run["quota_attempt"]))
        path = _quota_control(run["id"], source) / "pause.json"
        if not path.exists():
            return None
        try:
            payload = json.loads(path.read_text())
            if not isinstance(payload, dict) or payload.get("source") != source:
                return "failed"
            if payload.get("status") == "quota_wait":
                self.record_control_state(account, source, payload)
                return "quota_wait"
        except (OSError, ValueError):
            pass
        return "failed"

    def tick(self) -> None:
        """消费真实响应并恢复已有等待工作，不发送探测。

        :return: None
        """
        conn = get_db()
        try:
            accounts = [dict(row) for row in conn.execute("SELECT * FROM accounts WHERE deleted_at IS NULL")]
        finally:
            conn.close()
        for account in accounts:
            if self._stop.is_set():
                break
            try:
                self.consume(account)
                if continue_manager:
                    continue_manager.quota_tick(account)
                if not account["enabled"]:
                    continue
                self._resume_account(account)
            except Exception:
                # 文件或单账号容器异常不影响其它账号；下一轮仍保留门禁事实。
                continue

    def _loop(self) -> None:
        while not self._stop.is_set():
            if login_manager:
                login_manager.sweep_expired()
            self.tick()
            self._stop.wait(2)

    def _resume_account(self, account: dict) -> None:
        state = self.snapshot(account)
        if state["blocked"] or not scheduler:
            return
        conn = get_db()
        try:
            rows = [dict(row) for row in conn.execute(
                "SELECT r.*,t.prompt,t.timeout_sec FROM runs r JOIN tasks t ON r.task_id=t.id "
                "WHERE r.account_id=? AND r.status='quota_wait' AND r.deleted_at IS NULL AND t.deleted_at IS NULL "
                "AND r.stop_requested_at IS NULL ORDER BY r.created_at,r.id", (account["id"],))]
        finally:
            conn.close()
        for run in rows:
            if self._cancel_changed_identity(run, account):
                continue
            if scheduler.is_executing(run["id"], int(run["quota_attempt"])):
                continue
            if run["run_kind"] == "capture" and run["quota_resume_at"] is not None and run["quota_resume_at"] > time.time():
                continue
            if run["run_kind"] == "capture":
                if not self.capture_resume_ready(run["id"]):
                    continue
            if run["run_kind"] == "warmup" and not account.get("warmup_enabled"):
                continue
            attempt = int(run["quota_attempt"]) + 1
            source = _quota_source(run["id"], attempt)
            with _oauth_owner_lock(str(account["name"])):
                conn = get_db()
                try:
                    current = _get_available_account(conn, int(account["id"]))
                    parent = conn.execute("SELECT status,deleted_at FROM task_batches WHERE id=?", (run["batch_id"],)).fetchone() if run["batch_id"] else None
                finally:
                    conn.close()
                if not current or (parent and (parent["deleted_at"] or parent["status"] not in ("active", "quota_wait"))):
                    continue
                account = dict(current)
                workload = (
                    "warmup" if run["run_kind"] == "warmup"
                    else "normal" if run["run_kind"] == "normal"
                    else None
                )
                if workload == "warmup" and (
                        not account.get("warmup_enabled") or self.policy_snapshot(account, workload, source)["blocked"]):
                    continue
                if workload == "normal" and self.policy_snapshot(account, workload, source)["blocked"]:
                    continue
                self.runner.cleanup_quota_run(run["id"])
                if not self.admit(account, source, workload=workload):
                    continue
                with _db_lock:
                    conn = get_db()
                    try:
                        with conn:
                            cur = conn.execute("UPDATE runs SET status='queued',quota_attempt=?,quota_resume_at=NULL,error=NULL,"
                                               "worker_container=NULL,sidecar_container=NULL,ended_at=NULL WHERE id=? AND status='quota_wait' "
                                               "AND quota_attempt=? AND stop_requested_at IS NULL AND deleted_at IS NULL",
                                               (attempt, run["id"], run["quota_attempt"]))
                            if cur.rowcount:
                                conn.execute("UPDATE task_batch_items SET status='queued',updated_at=julianday('now') WHERE run_id=? AND status='quota_wait'", (run["id"],))
                    finally:
                        conn.close()
                if not cur.rowcount:
                    self.release(account, source)
                    continue
            task = {"id": run["task_id"], "prompt": run["prompt"], "timeout_sec": run["timeout_sec"],
                    "claude_code_version": run["claude_code_version"], "claude_effort_level": run["claude_effort_level"],
                    "quota_attempt": attempt, "model_override": run["execution_model"],
                    "capture_full_http": run["run_kind"] == "capture", "capture_mode": run["capture_mode"],
                    "capture_permission_mode": run["capture_permission_mode"]}
            scheduler.submit(run["id"], account, task)
        state = self.snapshot(account)
        if state["blocked"] or state["recovery_source"]:
            return
        normal_policy = self.policy_snapshot(account, "normal", quota_state=state)
        warmup_state = self.warmup_snapshot(account)
        with _db_lock:
            conn = get_db()
            try:
                with conn:
                    batches = [] if normal_policy["blocked"] else conn.execute(
                        "SELECT id FROM task_batches b WHERE account_id=? AND status='quota_wait' AND deleted_at IS NULL "
                        "AND NOT EXISTS(SELECT 1 FROM runs r WHERE r.batch_id=b.id AND r.status IN ('quota_wait','queued','running','stopping'))",
                        (account["id"],),
                    ).fetchall()
                    if state["retry_ready"]:
                        batches = batches[:1]
                    for batch in batches:
                        conn.execute("UPDATE task_batches SET status='active',next_launch_at=NULL WHERE id=? AND status='quota_wait'", (batch["id"],))
                    conn.execute("UPDATE accounts SET warmup_next_run_at=?,warmup_last_status='scheduled',warmup_last_error=NULL "
                                 "WHERE id=? AND warmup_enabled=1 AND warmup_last_status='quota_wait' "
                                 "AND ?=0 "
                                 "AND NOT EXISTS(SELECT 1 FROM runs WHERE account_id=? AND run_kind='warmup' AND status IN ('quota_wait','queued','running','stopping'))",
                                 (time.time(), account["id"], int(warmup_state["blocked"]), account["id"]))
            finally:
                conn.close()
        for batch in batches:
            scheduler.submit_batch(batch["id"])

    def capture_resume_ready(self, run_id: str) -> bool:
        """
        抓包 run 与抓包续聊共同遵守自动恢复的串行和启动间隔。

        :param run_id: 待恢复的原 run ID
        :return: 无其它抓包执行且距最近启动至少 120 秒时返回 True
        """
        conn = get_db()
        try:
            active = conn.execute("SELECT 1 FROM runs WHERE run_kind='capture' AND id!=? "
                                  "AND status IN ('queued','running','stopping') LIMIT 1", (run_id,)).fetchone()
            recent = conn.execute("SELECT MAX(started_at) FROM runs WHERE run_kind='capture'").fetchone()[0] or 0
        finally:
            conn.close()
        if continue_manager:
            with continue_manager._lock:
                if any(session.run.get("run_kind") == "capture" and session.status == "running"
                       for session in continue_manager.sessions.values()):
                    return False
                recent = max(recent, continue_manager._capture_started_at)
        return not active and recent + 120 <= time.time()

    def _cancel_changed_identity(self, run: dict, account: dict) -> bool:
        previous = run.get("quota_identity")
        if not previous or previous == _quota_identity(account):
            return False
        with _db_lock:
            conn = get_db()
            try:
                with conn:
                    cur = conn.execute("UPDATE runs SET status='auth_failed',error='账号身份已变化，请人工重新运行',ended_at=? "
                                       "WHERE id=? AND quota_attempt=? AND status IN ('queued','running','quota_wait') AND stop_requested_at IS NULL",
                                       (time.time(), run["id"], run["quota_attempt"]))
                    if cur.rowcount:
                        conn.execute("UPDATE task_batch_items SET status='auth_failed' WHERE run_id=? AND status!='paused'", (run["id"],))
                        conn.execute("UPDATE task_batches SET status='paused',next_launch_at=NULL WHERE id=? AND status IN ('active','quota_wait')", (run["batch_id"],))
            finally:
                conn.close()
        return True


# ============== Docker 运行器 ==============
def _public_quota(account: dict) -> dict:
    """读取页面可用的被动额度，参数为账号，返回不含身份或凭据哈希的摘要。"""
    snapshot = quota_guard.snapshot(account) if quota_guard else {}
    return {key: snapshot.get(key) for key in ("source", "known", "windows", "observed_at", "blocked", "exhausted", "resume_at", "retry_ready", "message", "account_error")}


def _public_quota_policy(account: dict, workload: Literal["normal", "warmup"] = "normal") -> dict:
    """返回页面需要的阈值和被动等待摘要，省略内部身份与许可。

    :param account: 当前账号
    :param workload: 普通任务或养号
    :return: 脱敏策略摘要
    """
    policy = quota_guard.policy_snapshot(account, workload) if quota_guard else {}
    return {key: policy.get(key) for key in (
        "enabled", "limits", "hit", "unknown", "blocked", "resume_at", "message", "refresh_retry_at")}


def _quota_source(run_id: str, attempt: int) -> str:
    """生成 run 的独立执行来源，参数为 run ID/代次，返回来源字符串。"""
    return f"run:{run_id}:{attempt}"


def _quota_control(run_id: str, source: str) -> Path:
    """生成不会被旧执行覆盖的控制目录，返回本地路径。"""
    # 独立于可写 workspace，避免生成项目清理目录或 worker chown 破坏只读控制契约。
    return BENCH_DATA / "quota-controls" / run_id / hashlib.sha256(source.encode()).hexdigest()[:20]


class Runner:
    """封装 sidecar + worker 的生命周期"""

    def __init__(self) -> None:
        self.client = docker.from_env()

    def _quota_mounts(self, account: dict, run_id: str, source: str, flows: Path, warmup: bool = False) -> tuple[dict, dict, dict]:
        if not quota_guard:
            return {}, {}, {}
        if account_runtime:
            flows = account_runtime.execution_flows(account, source, flows)
        control = _quota_control(run_id, source)
        env = quota_guard.prepare(account, source, flows, control, warmup=warmup)
        host_control = HOST_BENCH_DATA / control.relative_to(BENCH_DATA)
        return env, {
            str(HOST_BENCH_DATA / "quota" / str(account["id"])): {"bind": "/quota-account", "mode": "ro"},
            str(host_control): {"bind": "/quota-control", "mode": "rw"},
            str(HOST_BENCH_DATA / "workspaces" / run_id / ".claude-home"): {"bind": "/quota-credentials", "mode": "ro"},
        }, {str(host_control): {"bind": "/quota-control", "mode": "ro"}}

    def cleanup_quota_run(self, run_id: str) -> None:
        """
        严格清理原 run 容器，失败时阻止恢复，避免旧执行继续请求。

        :param run_id: 原 run ID
        :return: None
        """
        if account_runtime:
            with account_runtime.lock:
                jobs = [job for job in account_runtime.jobs.values() if job.get("run_id") == run_id]
            for job in jobs:
                account_runtime.cleanup(job["token"])
            return
        for name in (f"bench-worker-{run_id}", f"bench-sidecar-{run_id}"):
            try:
                container = self.client.containers.get(name)
            except NotFound:
                continue
            container.remove(force=True)

    def start_run(self, run_id: str, account: dict, task: dict) -> tuple[str, str]:
        """
        启动一次 run 的 sidecar 和 worker。

        :param run_id: runs.id
        :param account: accounts 表行
        :param task: 调度 payload，包含 run 创建时的版本、思考预算和权限模式快照
        :return: `(sidecar_id, worker_id)`
        """
        sidecar_name = f"bench-sidecar-{run_id}"
        worker_name = f"bench-worker-{run_id}"
        acc_name = account["name"]
        # 账号派生指纹:同账号每次 run 拿到一致的 hostname/MAC/LANG/machine-id,
        # TZ 允许显式覆盖；未配置时仍按账号名派生,跨账号保持差异化。
        fp = derive_fingerprint(acc_name)
        tz = _effective_account_timezone(account)

        # 容器内创建运行目录（docker 会按宿主路径挂载到子容器）
        (BENCH_DATA / "workspaces" / run_id).mkdir(parents=True, exist_ok=True)
        if not account_runtime:
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
        capture_full_http = bool(task.get("capture_full_http"))
        managed_oauth = account.get("cc2api_account_id") is not None
        claude_code_version = _resolve_run_claude_code_version(
            task.get("claude_code_version")
        )
        claude_effort_level = _resolve_run_claude_effort_level(
            task.get("claude_effort_level")
        )
        permission_mode = _resolve_capture_permission_mode(
            task.get("capture_permission_mode")
        )
        sidecar_env = _sidecar_proxy_env(account)
        sidecar_env.update({
            "DNS_READY_HOST": DNS_READY_HOST,
            # 抓包 run 是诊断模式，必须独立于全局默认值保存完整 flow。
            "SAVE_FULL_FLOWS": "1" if capture_full_http else SAVE_FULL_FLOWS,
        })
        if capture_full_http:
            sidecar_env.update({
                "CAPTURE_FULL_HTTP": "1",
                "CAPTURE_MODE": str(task.get("capture_mode") or "full_http"),
                "CAPTURE_SCOPE": "all",
                "CAPTURE_TARGETS": "anthropic.com,claude.com",
                "CAPTURE_MAX_BODY_BYTES": "0",
            })
        worker_env = {
            "TASK_PROMPT": task["prompt"],
            "RUN_ID": run_id,
            "TIMEOUT_SEC": str(task.get("timeout_sec", 1800)),
            "ACC_NAME": acc_name,
            "CLAUDE_CODE_VERSION": claude_code_version,
            "CLAUDE_CODE_EFFORT_LEVEL": claude_effort_level,
            "CLAUDE_PERMISSION_MODE": permission_mode,
            "PROFILE_CLAUDE_CODE_EFFORT_LEVEL": CLAUDE_CODE_EFFORT_LEVEL,
            "CLEAN_WORKSPACE_DEPS": CLEAN_WORKSPACE_DEPS,
            "TIMEOUT_WRAPUP_SEC": str(TIMEOUT_WRAPUP_SEC),
            "OAUTH_CREDENTIAL_SYNC_INTERVAL_SEC": str(OAUTH_CREDENTIAL_SYNC_INTERVAL_SEC),
            "OAUTH_401_PROFILE_WAIT_SEC": str(OAUTH_401_PROFILE_WAIT_SEC),
            "CLAUDE_API_STALL_WATCHDOG_SEC": str(CLAUDE_API_STALL_WATCHDOG_SEC),
            "CLAUDE_API_STALL_MAX_RECOVERIES": str(CLAUDE_API_STALL_MAX_RECOVERIES),
            "CLAUDE_BUSY_INTERRUPT_GRACE_SEC": str(CLAUDE_BUSY_INTERRUPT_GRACE_SEC),
            "CLAUDE_API_STALL_RECOVERY_PROMPT": CLAUDE_API_STALL_RECOVERY_PROMPT,
            "OAUTH_REFRESH_BUFFER_SEC": str(OAUTH_REFRESH_BUFFER_SEC),
            "TZ": tz,
            "LANG": fp["lang"],
            "LC_ALL": fp["lang"],
        }
        source = _quota_source(run_id, int(task.get("quota_attempt") or 0))
        quota_env, quota_sidecar_volumes, quota_worker_volumes = self._quota_mounts(
            account, run_id, source, FLOWS_DIR / acc_name / str(task["id"]) / run_id, warmup=bool(task.get("warmup")))
        sidecar_env.update(quota_env)
        worker_env.update({key: value for key, value in quota_env.items() if key in ("QUOTA_SOURCE", "QUOTA_SIGNAL_FILE", "QUOTA_WARMUP")})
        if task.get("resume_session_id"):
            worker_env["RESUME_SESSION_ID"] = task["resume_session_id"]
        if managed_oauth:
            worker_env["CC2API_MANAGED_OAUTH"] = "1"
            for marker_name in (
                ".cc2api-oauth-refresh-request.json",
                ".cc2api-oauth-refresh-result.json",
            ):
                try:
                    (WORKSPACES_DIR / run_id / marker_name).unlink()
                except FileNotFoundError:
                    pass
        model_override = task.get("model_override")
        if isinstance(model_override, str) and model_override:
            # 只给当前 worker 进程传一次性模型覆盖，避免污染账号 profile settings。
            worker_env["CLAUDE_MODEL_OVERRIDE"] = model_override
        elif not capture_full_http and "model_override" not in task:
            # 普通 / 批量 run 复用抓包的 --model 一次性覆盖链路；
            # 抓包 run 留空时必须沿用自身默认模型，不能被页面或环境全局配置带偏。
            worker_env["CLAUDE_MODEL_OVERRIDE"] = effective_runtime_model()

        if account_runtime:
            return account_runtime.start_run(account, task, run_id, worker_env, sidecar_env)
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
                    **quota_sidecar_volumes,
                },
                environment=sidecar_env,
            )
            sidecar_id = sidecar.id

            _wait_sidecar_ready(self.client, sidecar_id)

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
                    **quota_worker_volumes,
                },
                environment=worker_env,
            )
            worker_id = worker.id
            return sidecar_id, worker_id
        except Exception:
            # worker 创建失败时 sidecar 已经可能存在；外层拿不到 id，所以这里收口。
            self.cleanup(sidecar_id, worker_id)
            raise

    def persist_worker_profile(
        self,
        worker_id: Optional[str],
        profile_effort_level: str = CLAUDE_CODE_EFFORT_LEVEL,
    ) -> None:
        """
        在停止容器前尽量把运行时本地配置回写 profile。

        :param worker_id: worker 容器 ID
        :param profile_effort_level: 回写账号 profile 时保留的思考预算兜底值
        :return: None
        """
        if account_runtime or not worker_id:
            return
        try:
            api = self.client.api
            cmd = (
                "mkdir -p \"$HOME/.claude\"; "
                "cp \"$HOME/.claude.json\" \"$HOME/.claude/.claude.json\" 2>/dev/null || true; "
                "if [ -d /mnt/profile ] && [ -w /mnt/profile ]; then "
                "if [ -f \"$HOME/.claude/settings.json\" ]; then "
                "node - \"$HOME/.claude/settings.json\" \"$PROFILE_CLAUDE_CODE_EFFORT_LEVEL\" "
                "> /tmp/profile-settings.json <<'JS' || cp \"$HOME/.claude/settings.json\" /tmp/profile-settings.json\n"
                "const fs = require('fs');\n"
                "const path = process.argv[2];\n"
                "const effort = process.argv[3] || 'max';\n"
                "const data = JSON.parse(fs.readFileSync(path, 'utf8'));\n"
                "const settings = data && typeof data === 'object' ? data : {};\n"
                "const env = settings.env && typeof settings.env === 'object' ? settings.env : {};\n"
                "settings.env = {...env, CLAUDE_CODE_EFFORT_LEVEL: effort};\n"
                "process.stdout.write(`${JSON.stringify(settings, null, 2)}\\n`);\n"
                "JS\n"
                "cp /tmp/profile-settings.json /mnt/profile/settings.json 2>/dev/null || true; "
                "fi; "
                "cp \"$HOME/.claude/.claude.json\" /mnt/profile/.claude.json 2>/dev/null || true; "
                "chown node:node /mnt/profile/settings.json /mnt/profile/.claude.json 2>/dev/null || true; "
                "fi"
            )
            ex = api.exec_create(
                worker_id,
                ["sh", "-lc", cmd],
                stdout=True,
                stderr=True,
                environment={
                    "HOME": WORKER_HOME,
                    "PROFILE_CLAUDE_CODE_EFFORT_LEVEL": profile_effort_level,
                },
                workdir=WORKER_HOME,
            )
            api.exec_start(ex["Id"])
        except Exception:
            # 容器可能已经退出或被删除；停止路径不应被配置兜底阻断。
            pass

    def wait_worker(self, worker_id: str) -> int:
        if account_runtime:
            return account_runtime.wait_worker(worker_id)
        worker = self.client.containers.get(worker_id)
        result = worker.wait()
        return int(result.get("StatusCode", -1))

    def read_worker_status(self, run_id: str) -> dict:
        """
        读取 worker 写入的轻量状态文件，用于区分普通失败和认证失败。

        :param run_id: runs.id
        :return: 状态字典；文件缺失或格式异常时返回空 dict
        """
        path = account_runtime.run_artifact_path(run_id, "status.json") if account_runtime else (
            WORKSPACES_DIR / run_id / ".bench-status.json"
        )
        if not path.exists():
            return {}
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        return data if isinstance(data, dict) else {}

    def cleanup(self, sidecar_id: Optional[str], worker_id: Optional[str]) -> None:
        if account_runtime:
            if worker_id or sidecar_id:
                account_runtime.cleanup(worker_id or sidecar_id)
            return
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

    def watch_managed_oauth_refresh(
        self,
        run_id: str,
        account: dict,
        stop_event: threading.Event,
        worker_id: Optional[str] = None,
    ) -> None:
        """
        监听 managed worker 的单次 401 刷新请求并交给 cc2api 处理。

        :param run_id: 当前 runs.id
        :param account: 已绑定 cc2api 的 bench accounts 行
        :param stop_event: worker 收口后用于停止 watcher 的事件
        :param worker_id: v3 当前执行 token，阻止旧刷新回调覆盖新执行
        :return: None
        """
        if account_runtime:
            request_path = account_runtime.run_artifact_path(run_id, "oauth-refresh-request.json")
            result_path = account_runtime.run_artifact_path(run_id, "oauth-refresh-result.json")
        else:
            workspace = WORKSPACES_DIR / run_id
            request_path = workspace / ".cc2api-oauth-refresh-request.json"
            result_path = workspace / ".cc2api-oauth-refresh-result.json"
        while not stop_event.wait(1):
            if not request_path.exists():
                continue
            try:
                _sync_bound_account_credentials(account, 600, force_refresh=True)
                if stop_event.is_set():
                    return
                if account_runtime:
                    job = account_runtime.job_for_container(worker_id or "expired")
                    with account_runtime.environment_lock(job["row"]["environment_id"]):
                        account_runtime.job_for_container(worker_id or "expired")
                        _write_json_atomically(result_path, {"ok": True})
                    return
                _write_json_atomically(result_path, {"ok": True})
            except Exception as exc:
                if stop_event.is_set():
                    return
                if account_runtime:
                    try:
                        job = account_runtime.job_for_container(worker_id or "expired")
                    except ValueError:
                        return
                    with account_runtime.environment_lock(job["row"]["environment_id"]):
                        try:
                            account_runtime.job_for_container(worker_id or "expired")
                        except ValueError:
                            return
                        _write_json_atomically(result_path, {"ok": False, "error": _redact_cc2api_error(exc)})
                    return
                _write_json_atomically(
                    result_path,
                    {"ok": False, "error": _redact_cc2api_error(exc)},
                )
            return

    def sync_managed_credentials_to_worker(self, worker_id: str) -> None:
        """
        把 profile 最新 AT 同步到 continue worker，并从运行副本移除 RT。

        :param worker_id: continue worker 容器 ID
        :return: None
        """
        if account_runtime:
            job = account_runtime.job_for_container(worker_id)
            account_runtime.sync_credentials(job["row"], job["account"])
            return
        script = """
const fs = require('fs');
const src = '/mnt/profile/.credentials.json';
const dst = `${process.env.HOME}/.claude/.credentials.json`;
const data = JSON.parse(fs.readFileSync(src, 'utf8'));
const oauth = data && data.claudeAiOauth;
if (!oauth || typeof oauth.accessToken !== 'string' || !oauth.accessToken) {
  throw new Error('managed OAuth credentials invalid');
}
delete oauth.refreshToken;
const tmp = `${dst}.tmp.${process.pid}`;
fs.writeFileSync(tmp, `${JSON.stringify(data, null, 2)}\n`, 'utf8');
fs.renameSync(tmp, dst);
"""
        api = self.client.api
        ex = api.exec_create(
            worker_id,
            ["node", "-e", script],
            stdout=True,
            stderr=True,
            user=WORKER_USER,
            environment={"HOME": WORKER_HOME},
            workdir=WORKER_HOME,
        )
        api.exec_start(ex["Id"])
        inspected = api.exec_inspect(ex["Id"])
        if inspected.get("ExitCode") not in (0, None):
            raise ValueError("同步 managed OAuth 凭据到继续对话 worker 失败")

    def start_continue(self, sid: str, run: dict, account: dict, session_id: str) -> tuple[str, str]:
        """
        启动一个继续对话容器。

        :param sid: continue session id
        :param run: runs 表行
        :param account: accounts 表行
        :param session_id: Claude session id
        :return: (sidecar_id, worker_id)
        """
        if account_runtime:
            flows = FLOWS_DIR / account["name"] / str(run["task_id"]) / run["id"] / f"continue-{sid}"
            current = continue_manager.get(sid) if continue_manager else None
            source = f"continue:{sid}:{current.generation if current else 0}"
            quota_env, _, _ = self._quota_mounts(account, run["id"], source, flows)
            return account_runtime.begin_continue(account, run, sid, quota_env, flows)
        sidecar_name = f"bench-continue-sidecar-{sid}"
        worker_name = f"bench-continue-worker-{sid}"
        acc_name = account["name"]
        fp = derive_fingerprint(acc_name)
        tz = _effective_account_timezone(account)
        CA_DIR.mkdir(parents=True, exist_ok=True)
        workspace_dir = WORKSPACES_DIR / run["id"]
        claude_home_dir = workspace_dir / ".claude-home"
        profile_dir = PROFILES_DIR / acc_name
        managed_oauth = account.get("cc2api_account_id") is not None
        if managed_oauth:
            for marker_name in (
                ".cc2api-oauth-refresh-request.json",
                ".cc2api-oauth-refresh-result.json",
            ):
                try:
                    (workspace_dir / marker_name).unlink()
                except FileNotFoundError:
                    pass
        _copy_profile_whitelist_to_claude_home(profile_dir, claude_home_dir)
        top_config = claude_home_dir / ".claude.json"
        if top_config.exists():
            shutil.copy2(top_config, workspace_dir / ".claude.json")
        _make_worker_owned(workspace_dir)

        host_workspace = HOST_BENCH_DATA / "workspaces" / run["id"]
        host_claude_home = HOST_BENCH_DATA / "workspaces" / run["id"] / ".claude-home"
        host_profile = HOST_BENCH_DATA / "profiles" / acc_name
        host_ca = HOST_BENCH_DATA / "ca"
        continue_capture_dirs = _resolve_capture_flows_dirs(run, ensure_exists=True)
        sidecar_volumes = {str(host_ca): {"bind": "/ca", "mode": "rw"}}
        sidecar_env = _sidecar_proxy_env(account)
        sidecar_env.update({
            "DNS_READY_HOST": DNS_READY_HOST,
            "SAVE_FULL_FLOWS": SAVE_FULL_FLOWS,
        })
        flows = (continue_capture_dirs[0] if continue_capture_dirs else
                 FLOWS_DIR / acc_name / str(run["task_id"]) / run["id"] / f"continue-{sid}")
        flows.mkdir(parents=True, exist_ok=True)
        sidecar_volumes[str(HOST_BENCH_DATA / flows.relative_to(BENCH_DATA))] = {"bind": "/flows", "mode": "rw"}
        source = f"continue:{sid}:{int(run.get('continue_generation') or 0)}"
        quota_env, quota_sidecar_volumes, quota_worker_volumes = self._quota_mounts(account, run["id"], source, flows)
        sidecar_env.update(quota_env)
        sidecar_volumes.update(quota_sidecar_volumes)
        if continue_capture_dirs:
            _flows_dir, host_flows = continue_capture_dirs
            # capture run 的继续会话仍是诊断链路，必须追加保存到原 run flows 目录。
            sidecar_volumes[str(host_flows)] = {"bind": "/flows", "mode": "rw"}
            sidecar_env.update({
                "SAVE_FULL_FLOWS": "1",
                "CAPTURE_FULL_HTTP": "1",
                "CAPTURE_MODE": "continue_full_http",
                "CAPTURE_SCOPE": "all",
                "CAPTURE_TARGETS": "anthropic.com,claude.com",
                "CAPTURE_MAX_BODY_BYTES": "0",
            })
        claude_code_version = _resolve_run_claude_code_version(
            run.get("claude_code_version")
        )
        claude_effort_level = _resolve_run_claude_effort_level(
            run.get("claude_effort_level")
        )
        permission_mode = _resolve_capture_permission_mode(
            run.get("capture_permission_mode")
        )

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
                volumes=sidecar_volumes,
                environment=sidecar_env,
            )
            sidecar_id = sidecar.id
            _wait_sidecar_ready(self.client, sidecar_id)
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
                    **quota_worker_volumes,
                    **(
                        {str(host_profile): {"bind": "/mnt/profile", "mode": "rw"}}
                        if managed_oauth
                        else {}
                    ),
                },
                environment={
                    "WORKER_MODE": "login",
                    "USE_SIDECAR_DNS": "1",
                    "HOME": WORKER_HOME,
                    "ACC_NAME": acc_name,
                    "CLAUDE_CODE_VERSION": claude_code_version,
                    "CLAUDE_CODE_EFFORT_LEVEL": claude_effort_level,
                    "CLAUDE_PERMISSION_MODE": permission_mode,
                    "TZ": tz,
                    "LANG": fp["lang"],
                    "LC_ALL": fp["lang"],
                    "CONTINUE_SESSION_ID": session_id,
                    "CC2API_MANAGED_OAUTH": "1" if managed_oauth else "0",
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
        经账号代理查询 OAuth usage，v3 复用固定容器和原生 TLS。

        :param account: accounts 表行
        :return: 额度查询结果
        """
        if not account.get("upstream_socks5_host"):
            raise ValueError("account has no upstream proxy configured")
        if account_runtime:
            if account.get("cc2api_account_id") is None and _read_account_oauth_status(account["name"])["oauth_token_state"] in ("expiring", "expired"):
                self.refresh_account_oauth_token(account)
            row, container = account_runtime.ensure(account)
            job = account_runtime.claim(row, account, f"quota:{uuid.uuid4().hex}")
            try:
                if account.get("cc2api_account_id") is not None:
                    # 查询入口已持有不可重入的 owner 锁，不能再次进入外层同步包装。
                    _sync_bound_account_credentials_locked(account, 600)
                account_runtime.sync_credentials(row, account)
                return _format_quota_result(self._exec_quota_probe(container.id))
            finally:
                # 只读查询没有 CLI 子进程或检查上下文，不重启原生 TLS 监听。
                account_runtime.release(job)
        sid = uuid.uuid4().hex[:12]
        sidecar_name = f"bench-quota-sidecar-{sid}"
        worker_name = f"bench-quota-worker-{sid}"
        acc_name = account["name"]
        fp = derive_fingerprint(acc_name)
        tz = _effective_account_timezone(account)
        temp_run_id = f"quota-{sid}"
        temp_workspace = WORKSPACES_DIR / temp_run_id
        temp_home = temp_workspace / ".claude-home"
        temp_workspace.mkdir(parents=True, exist_ok=True)
        CA_DIR.mkdir(parents=True, exist_ok=True)
        claude_code_version = effective_claude_code_version()

        sidecar_id: Optional[str] = None
        worker_id: Optional[str] = None
        try:
            with _profile_lock(acc_name):
                _copy_profile_whitelist_to_claude_home(PROFILES_DIR / acc_name, temp_home)
                top_config = temp_home / ".claude.json"
                if top_config.exists():
                    shutil.copy2(top_config, temp_workspace / ".claude.json")
                _make_worker_owned(temp_workspace)
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
                        **_sidecar_proxy_env(account),
                        "DNS_READY_HOST": DNS_READY_HOST,
                    },
                )
                sidecar_id = sidecar.id
                _wait_sidecar_ready(self.client, sidecar_id)
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
                        "CLAUDE_CODE_VERSION": claude_code_version,
                        "CLAUDE_CODE_EFFORT_LEVEL": CLAUDE_CODE_EFFORT_LEVEL,
                        "TZ": tz,
                        "LANG": fp["lang"],
                        "LC_ALL": fp["lang"],
                    },
                )
                worker_id = worker.id
                raw = self._exec_oauth_refresh_probe(worker_id)
                if raw.get("refreshed"):
                    refreshed_credentials = temp_home / ".credentials.json"
                    if refreshed_credentials.exists():
                        _copy_file_atomically(refreshed_credentials, PROFILES_DIR / acc_name / ".credentials.json")
                    else:
                        raw = {"error": "OAuth token 刷新后未生成 .credentials.json"}
                if not raw.get("error"):
                    raw = self._exec_quota_probe(worker_id)
                workspace_top_config = temp_workspace / ".claude.json"
                if workspace_top_config.exists():
                    shutil.copy2(workspace_top_config, temp_home / ".claude.json")
                _copy_claude_home_config_to_profile(temp_home, PROFILES_DIR / acc_name)
            return _format_quota_result(raw)
        finally:
            self.cleanup(sidecar_id, worker_id)
            shutil.rmtree(temp_workspace, ignore_errors=True)

    def _exec_quota_probe(self, worker_id: str) -> dict:
        """
        在 quota worker 中通过 OAuth usage API 读取额度。

        :param worker_id: quota worker 容器 ID
        :return: usage API 原始 JSON，失败时返回 raw/error
        """
        script = r'''
set -eu
if [ -f /workspace/.claude.json ]; then
  cp /workspace/.claude.json "$HOME/.claude.json"
fi
DNS_READY_HOST="${DNS_READY_HOST:-example.com}"
for i in $(seq 1 45); do
  if grep -q '^nameserver 127[.]0[.]0[.]1' /etc/resolv.conf \
    && DNS_READY_HOST="$DNS_READY_HOST" node -e "require('dns').resolve4(process.env.DNS_READY_HOST || 'example.com', (err, addresses) => process.exit(!err && addresses && addresses.length ? 0 : 1))" >/dev/null 2>&1; then
    break
  fi
  sleep 1
done
node - <<'JS'
const fs = require('fs');
const os = require('os');
const path = require('path');

const USAGE_URL = 'https://api.anthropic.com/api/oauth/usage';
const credentialsPath = path.join(os.homedir(), '.claude', '.credentials.json');
const claudeCodeVersion = process.env.CLAUDE_CODE_VERSION || '2.1.280';

function emit(value) {
  process.stdout.write(`${JSON.stringify(value)}\n`);
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function loadCredentials() {
  if (!fs.existsSync(credentialsPath)) {
    throw new Error('.credentials.json 不存在，请先登录账号');
  }
  try {
    return JSON.parse(fs.readFileSync(credentialsPath, 'utf8'));
  } catch (error) {
    throw new Error(`.credentials.json 解析失败: ${error.message}`);
  }
}

function oauthSection(data) {
  const oauth = data && data.claudeAiOauth;
  if (!oauth || typeof oauth !== 'object') {
    throw new Error('.credentials.json 缺少 claudeAiOauth，无法查询 OAuth usage');
  }
  return oauth;
}

async function requestUsage(url, options) {
  let lastError = '';
  for (let attempt = 1; attempt <= 5; attempt += 1) {
    try {
      const response = await fetch(url, {...options, signal: AbortSignal.timeout(15000)});
      const text = await response.text();
      if (!response.ok) {
        const retryAfter = Number.parseInt(response.headers.get('retry-after') || '', 10);
        return {
          error: `HTTP ${response.status}: ${text.slice(0, 1000)}`,
          status: response.status,
          retry_after_sec: Number.isFinite(retryAfter) ? retryAfter : null,
        };
      }
      let payload;
      try {
        payload = JSON.parse(text);
      } catch (error) {
        return {error: `usage parse failed: ${error.message}`, raw: text.slice(0, 1000)};
      }
      return payload;
    } catch (error) {
      lastError = error && error.message ? error.message : String(error);
      // 已经拿到 HTTP 响应时不能重试，尤其 429 会被一次点击放大成多次上游请求。
      if (process.env.V3_NATIVE_USAGE === '1' || attempt === 5) break;
      await sleep(attempt * 1000);
    }
  }
  return {error: lastError || 'request failed after retries'};
}

async function currentAccessToken(data) {
  const oauth = oauthSection(data);
  if (typeof oauth.accessToken !== 'string' || !oauth.accessToken) {
    throw new Error('OAuth accessToken 为空，等待后台刷新器刷新或重新登录账号');
  }
  return oauth.accessToken;
}

(async () => {
  try {
    let credentials = loadCredentials();
    let token = await currentAccessToken(credentials);
    const usage = await requestUsage(USAGE_URL, {
      method: 'GET',
      headers: {
        'Authorization': `Bearer ${token}`,
        'Accept': 'application/json',
        'Content-Type': 'application/json',
        'anthropic-beta': 'oauth-2025-04-20',
        'User-Agent': `claude-code/${claudeCodeVersion}`,
      },
    });
    emit(usage);
    if (usage && usage.error) {
      process.exit(1);
    }
  } catch (error) {
    emit({error: error && error.message ? error.message : String(error)});
    process.exit(1);
  }
})();
JS
'''
        api = self.client.api
        ex = api.exec_create(
            account_runtime.job_for_container(worker_id)["row"]["container_id"] if account_runtime else worker_id,
            account_runtime.cli_command(["sh", "-c", script]) if account_runtime else ["sh", "-lc", script],
            stdout=True,
            stderr=True,
            user="root" if account_runtime else WORKER_USER,
            environment=_claude_exec_env(not account_runtime, {"V3_NATIVE_USAGE": "1" if account_runtime else "0",
                **(account_runtime.execution_environment(account_runtime.job_for_container(worker_id)["row"]) if account_runtime else {})}),
            workdir=WORKER_HOME,
        )
        raw = api.exec_start(ex["Id"])
        inspected = api.exec_inspect(ex["Id"])
        text = raw.decode("utf-8", errors="ignore").strip()
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            return {"error": "quota probe returned non-json output", "raw": text}
        if inspected.get("ExitCode") not in (0, None) and not parsed.get("error"):
            parsed["error"] = f"quota probe failed with exit {inspected.get('ExitCode')}"
        return parsed

    def refresh_account_oauth_token(self, account: dict) -> bool:
        """
        用账号代理刷新 OAuth access token，并回写账号 profile。

        :param account: accounts 表行
        :return: 发生刷新并成功回写时返回 True
        """
        if not _account_is_available(account):
            return False
        if not account.get("upstream_socks5_host"):
            raise ValueError("account has no upstream proxy configured")
        acc_name = account["name"]
        with _profile_lock(acc_name):
            status = _read_account_oauth_status(acc_name)
            if status["oauth_token_state"] == "valid" and int(status.get("oauth_expires_in_sec") or 0) > OAUTH_REFRESH_BUFFER_SEC:
                return False
            if account_runtime:
                version = effective_claude_code_version()
                source = f"oauth-refresh:{uuid.uuid4().hex}"
                row, container = account_runtime.ensure(account)
                job = account_runtime.claim(row, account, source, exclusive=True)
                try:
                    account_runtime.sync_credentials(row, account)
                    context = {"NETWORK_INSPECTION_MODE": "passthrough", "QUOTA_SOURCE": source}
                    atomic_json(account_runtime._root(row) / "runtime" / "context.json", context)
                    account_runtime._configure_network_context(container, context)
                    raw = self._exec_oauth_refresh_probe(job["token"], use_mitm=False)
                    if raw.get("skipped"):
                        return False
                    if raw.get("error"):
                        raise RuntimeError(str(raw["error"]))
                    credentials = account_runtime._root(row) / "home" / ".claude" / ".credentials.json"
                    if not credentials.exists():
                        raise RuntimeError("OAuth token 刷新后未生成 .credentials.json")
                    return True
                finally:
                    account_runtime.cleanup(job["token"])
            sid = uuid.uuid4().hex[:12]
            sidecar_name = f"bench-oauth-refresh-sidecar-{sid}"
            worker_name = f"bench-oauth-refresh-worker-{sid}"
            fp = derive_fingerprint(acc_name)
            tz = _effective_account_timezone(account)
            temp_run_id = f"oauth-refresh-{sid}"
            temp_workspace = WORKSPACES_DIR / temp_run_id
            temp_home = temp_workspace / ".claude-home"
            temp_workspace.mkdir(parents=True, exist_ok=True)
            claude_code_version = effective_claude_code_version()
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
                        **_sidecar_proxy_env(account),
                        "DNS_READY_HOST": DNS_READY_HOST,
                    },
                )
                sidecar_id = sidecar.id
                _wait_sidecar_ready(self.client, sidecar_id)
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
                        "CLAUDE_CODE_VERSION": claude_code_version,
                        "CLAUDE_CODE_EFFORT_LEVEL": CLAUDE_CODE_EFFORT_LEVEL,
                        "TZ": tz,
                        "LANG": fp["lang"],
                        "LC_ALL": fp["lang"],
                    },
                )
                worker_id = worker.id
                raw = self._exec_oauth_refresh_probe(worker_id)
                if raw.get("skipped"):
                    return False
                if raw.get("error"):
                    raise RuntimeError(str(raw["error"]))
                refreshed_credentials = temp_home / ".credentials.json"
                if not refreshed_credentials.exists():
                    raise RuntimeError("OAuth token 刷新后未生成 .credentials.json")
                _copy_file_atomically(refreshed_credentials, PROFILES_DIR / acc_name / ".credentials.json")
                _copy_claude_home_config_to_profile(temp_home, PROFILES_DIR / acc_name)
                return True
            finally:
                self.cleanup(sidecar_id, worker_id)
                shutil.rmtree(temp_workspace, ignore_errors=True)

    def _exec_oauth_refresh_probe(self, worker_id: str, use_mitm: bool = True) -> dict:
        """
        在临时 worker 内使用 refreshToken 刷新 accessToken。

        :param worker_id: refresh worker 容器 ID
        :param use_mitm: 是否为当前 exec 显式注入 Recorder CA
        :return: 刷新结果对象
        """
        script = r'''
set -eu
if [ -f /workspace/.claude.json ]; then
  cp /workspace/.claude.json "$HOME/.claude.json"
fi
DNS_READY_HOST="${DNS_READY_HOST:-example.com}"
for i in $(seq 1 45); do
  if grep -q '^nameserver 127[.]0[.]0[.]1' /etc/resolv.conf \
    && DNS_READY_HOST="$DNS_READY_HOST" node -e "require('dns').resolve4(process.env.DNS_READY_HOST || 'example.com', (err, addresses) => process.exit(!err && addresses && addresses.length ? 0 : 1))" >/dev/null 2>&1; then
    break
  fi
  sleep 1
done
node - <<'JS'
const fs = require('fs');
const os = require('os');
const path = require('path');

const TOKEN_URL = 'https://platform.claude.com/v1/oauth/token';
const CLIENT_ID = '9d1c250a-e61b-44d9-88ed-5944d1962f5e';
const credentialsPath = path.join(os.homedir(), '.claude', '.credentials.json');
const refreshBufferMs = Number(process.env.OAUTH_REFRESH_BUFFER_SEC || '600') * 1000;
const claudeCodeVersion = process.env.CLAUDE_CODE_VERSION || '2.1.280';

function emit(value) {
  process.stdout.write(`${JSON.stringify(value)}\n`);
}

function normalizeScopes(value) {
  const items = Array.isArray(value)
    ? value
    : (typeof value === 'string' ? value.split(/\s+/) : []);
  const seen = new Set();
  const scopes = [];
  for (const item of items) {
    if (typeof item !== 'string') {
      continue;
    }
    const scope = item.trim();
    if (!scope || seen.has(scope)) {
      continue;
    }
    seen.add(scope);
    scopes.push(scope);
  }
  return scopes;
}

function oauthErrorCode(text) {
  try {
    const payload = JSON.parse(text);
    const code = payload && typeof payload.error === 'string'
      ? payload.error.trim()
      : '';
    return /^[A-Za-z0-9_.:-]{1,80}$/.test(code) ? code : '';
  } catch {
    return '';
  }
}

function oauthErrorSummary(status, text, retryAfter) {
  const parts = [`OAuth token 刷新失败: HTTP ${status}`];
  const code = oauthErrorCode(text);
  if (code) {
    parts.push(code);
  }
  if (Number.isFinite(retryAfter)) {
    parts.push(`retry_after_sec=${retryAfter}`);
  }
  return parts.join('; ');
}

async function main() {
  let data;
  try {
    data = JSON.parse(fs.readFileSync(credentialsPath, 'utf8'));
  } catch (error) {
    throw new Error(`.credentials.json 读取失败: ${error.message}`);
  }
  const oauth = data && data.claudeAiOauth;
  if (!oauth || typeof oauth !== 'object') {
    throw new Error('.credentials.json 缺少 claudeAiOauth');
  }
  if (
    typeof oauth.accessToken === 'string' &&
    oauth.accessToken &&
    typeof oauth.expiresAt === 'number' &&
    oauth.expiresAt > Date.now() + refreshBufferMs
  ) {
    emit({skipped: true});
    return;
  }
  if (typeof oauth.refreshToken !== 'string' || !oauth.refreshToken) {
    throw new Error('OAuth refreshToken 为空，请重新登录账号');
  }
  const requestBody = {
    grant_type: 'refresh_token',
    refresh_token: oauth.refreshToken,
    client_id: CLIENT_ID,
  };
  const scopes = normalizeScopes(oauth.scopes);
  if (scopes.length) {
    // OAuth refresh 只能沿用现有授权，不能借刷新请求扩大 scope。
    requestBody.scope = scopes.join(' ');
  }
  const response = await fetch(TOKEN_URL, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Accept': 'application/json',
    },
    body: JSON.stringify(requestBody),
  });
  const text = await response.text();
  if (!response.ok) {
    const retryAfter = Number.parseInt(response.headers.get('retry-after') || '', 10);
    emit({
      error: oauthErrorSummary(response.status, text, retryAfter),
      status: response.status,
      retry_after_sec: Number.isFinite(retryAfter) ? retryAfter : null,
      oauth_error: oauthErrorCode(text) || null,
    });
    process.exit(1);
  }
  let payload;
  try {
    payload = JSON.parse(text);
  } catch (error) {
    throw new Error(`OAuth token 刷新响应不是 JSON: ${error.message}`);
  }
  if (typeof payload.access_token !== 'string' || !payload.access_token) {
    throw new Error('OAuth token 刷新响应缺少 access_token');
  }
  oauth.accessToken = payload.access_token;
  oauth.refreshToken = typeof payload.refresh_token === 'string' && payload.refresh_token
    ? payload.refresh_token
    : oauth.refreshToken;
  const responseScopes = normalizeScopes(payload.scope);
  if (responseScopes.length) {
    oauth.scopes = responseScopes;
  }
  const expiresIn = Number.isFinite(Number(payload.expires_in))
    ? Number(payload.expires_in)
    : 3600;
  oauth.expiresAt = Date.now() + Math.max(expiresIn, 60) * 1000;
  const tmp = `${credentialsPath}.tmp`;
  fs.writeFileSync(tmp, `${JSON.stringify(data, null, 2)}\n`, 'utf8');
  fs.renameSync(tmp, credentialsPath);
  emit({refreshed: true, expiresAt: oauth.expiresAt});
}

main().catch((error) => {
  emit({error: error && error.message ? error.message : String(error)});
  process.exit(1);
});
JS
'''
        api = self.client.api
        if account_runtime:
            job = account_runtime.job_for_container(worker_id)
            actual_worker = job["row"]["container_id"]
            command = account_runtime.cli_command(["sh", "-c", script])
            environment = _claude_exec_env(use_mitm, {
                "HOME": "/home/node",
                **account_runtime.execution_environment(job["row"]),
                "CLAUDE_CODE_VERSION": effective_claude_code_version(),
                "OAUTH_REFRESH_BUFFER_SEC": str(OAUTH_REFRESH_BUFFER_SEC),
            })
            workdir = "/home/node"
        else:
            actual_worker = worker_id
            command = ["sh", "-lc", script]
            environment = _claude_exec_env(use_mitm, {
                "OAUTH_REFRESH_BUFFER_SEC": str(OAUTH_REFRESH_BUFFER_SEC),
            })
            workdir = WORKER_HOME
        ex = api.exec_create(
            actual_worker,
            command,
            stdout=True,
            stderr=True,
            user="root" if account_runtime else WORKER_USER,
            environment=environment,
            workdir=workdir,
        )
        raw = api.exec_start(ex["Id"])
        inspected = api.exec_inspect(ex["Id"])
        text = raw.decode("utf-8", errors="ignore").strip()
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            return {"error": "oauth refresh probe returned non-json output", "raw": text}
        if inspected.get("ExitCode") not in (0, None) and not parsed.get("error"):
            parsed["error"] = f"oauth refresh probe failed with exit {inspected.get('ExitCode')}"
        return parsed


# ============== Login 会话管理 ==============
# OAuth 必须走 PTY（`claude auth login` 拒绝非 TTY 输入），所以在 worker 容器里
# `docker exec -it claude auth login`，把 PTY socket 桥到浏览器 xterm.js WebSocket。
# OAuth 流量必须走 sidecar（账号绑 IP），否则后续 API 调用会因换 IP 被风控。
_ACC_NAME_RE = re.compile(r"^[a-zA-Z0-9_-]+$")


class LoginSession:
    """单个 OAuth 引导会话：一对 sidecar+worker + 元数据"""

    __slots__ = ("sid", "name", "sidecar_id", "worker_id", "created_at",
                 "proxy", "profile_dir", "force_reauth", "committed", "home", "version",
                 "account_id", "binding_id", "identity", "commit_context", "phase", "import_payload", "authorization_url", "auth_method", "environment_id", "draft_generation", "code_receipts")

    def __init__(self, sid: str, name: str, sidecar_id: Optional[str],
                 worker_id: str, proxy: dict, profile_dir: Path,
                 force_reauth: bool) -> None:
        self.sid = sid
        self.name = name
        self.sidecar_id = sidecar_id
        self.worker_id = worker_id
        self.created_at = time.time()
        self.proxy = proxy
        self.profile_dir = profile_dir
        self.force_reauth = force_reauth
        self.committed = False
        self.home = WORKER_HOME
        self.version = effective_claude_code_version()
        self.account_id = None
        self.binding_id = None
        self.identity = {}
        self.commit_context = {}
        self.phase = "authorizing"
        self.import_payload = None
        self.authorization_url = None
        self.auth_method = None
        self.environment_id = None
        self.draft_generation = None
        self.code_receipts: dict[str, dict] = {}


class ContinueSession:
    """
    单个 run 的继续对话会话，保存容器、Claude session 和权限模式快照。

    :param sid: continue 会话 ID
    :param run_id: 原 runs.id
    :param account_id: 原 run 使用的账号 ID
    :param sidecar_id: continue sidecar 容器 ID
    :param worker_id: continue worker 容器 ID
    :param session_id: Claude session ID
    :param permission_mode: 原 run 的 Claude Code 权限模式
    """

    __slots__ = ("sid", "run_id", "account_id", "sidecar_id", "worker_id",
                 "session_id", "permission_mode", "created_at", "status", "generation",
                 "connected", "run", "identity", "guard_lock", "quota", "resume_not_before")

    def __init__(
        self,
        sid: str,
        run_id: str,
        account_id: int,
        sidecar_id: Optional[str],
        worker_id: Optional[str],
        session_id: str,
        permission_mode: str,
    ) -> None:
        self.sid = sid
        self.run_id = run_id
        self.account_id = account_id
        self.sidecar_id = sidecar_id
        self.worker_id = worker_id
        self.session_id = session_id
        self.permission_mode = permission_mode
        self.created_at = time.time()
        self.status = "running" if worker_id else "quota_wait"
        self.generation = 0
        self.connected = False
        self.run: dict = {}
        self.identity = ""
        self.guard_lock = threading.RLock()
        self.quota: dict = {}
        self.resume_not_before = 0.0


class LoginManager:
    def __init__(self, client: "docker.DockerClient") -> None:
        self.client = client
        self.sessions: dict[str, LoginSession] = {}
        # 同一个账号名同时只允许一个 login session（防并发覆盖 profile）
        self._name_locks: dict[str, str] = {}
        self._lock = threading.Lock()
        self.completed: dict[str, dict] = {}

    def sweep_expired(self) -> None:
        """收口到期的 v3 tmux 登录，包括没有浏览器连接的会话。

        :return: None
        """
        if not account_runtime:
            return
        with self._lock:
            expired = [sid for sid, session in self.sessions.items()
                if session.phase in ("authorizing", "ended", "ready_to_submit") and time.time() - session.created_at >= int(os.environ.get("V3_LOGIN_TTL_SECONDS", "1800"))]
            self.completed = {sid: value for sid, value in self.completed.items() if value["expires_at"] > time.time()}
        for sid in expired:
            try:
                session = self.get(sid)
                if session:
                    with _oauth_owner_lock(session.name):
                        self.cleanup(sid)
            except Exception:
                # AccountRuntime 已将不能证明收口的环境隔离；继续清理其它会话。
                pass

    def cleanup_stale(self) -> None:
        """启动时调用：清掉上次 orchestrator 进程残留的 bench-login-* 容器"""
        if account_runtime:
            return
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

    def has_active_name(self, name: str) -> bool:
        """
        判断账号名是否存在尚未收口的登录或重授权会话。

        :param name: bench 账号名
        :return: 存在活跃登录会话时返回 True
        """
        with self._lock:
            return name in self._name_locks

    def start(
        self,
        name: str,
        proxy: dict,
        force_reauth: bool = False,
        timezone: Optional[str] = None,
        version: Optional[str] = None,
    ) -> LoginSession:
        """
        启动账号 OAuth 登录容器。

        :param name: 账号 profile 名
        :param proxy: 上游代理配置
        :param force_reauth: 是否使用一次性 profile 副本强制重授权
        :param timezone: 登录 worker 显式时区；None 表示使用安全回退
        :param version: 恢复草稿时沿用首次选择的 CLI 版本
        :return: 登录会话对象
        """
        if not _ACC_NAME_RE.match(name):
            raise ValueError(
                "invalid account name: must match [a-zA-Z0-9_-]+"
            )
        # v3 时区来自显式账号配置，不能再把账号名 hash 当作设备画像来源。
        tz = _normalize_account_timezone(timezone) if account_runtime else _effective_account_timezone(name, timezone)
        with self._lock:
            if name in self._name_locks:
                raise ValueError(
                    f"login session already in progress for '{name}'; "
                    f"cancel it first"
                )
            sid = uuid.uuid4().hex[:12]
            self._name_locks[name] = sid

        draft_row, draft_registered = None, False
        try:
            if account_runtime:
                connection = get_db()
                try:
                    existing = connection.execute("SELECT * FROM accounts WHERE name=?", (name,)).fetchone()
                    environment = connection.execute("SELECT * FROM account_environments WHERE name=?", (name,)).fetchone()
                finally:
                    connection.close()
                if environment:
                    pending = _login_drafts().record(dict(environment))
                    if pending["phase"] in ("deleting", "submitting"):
                        raise ValueError("原登录仍在清理或保存，请先完成原草稿操作")
                account = dict(existing) if existing else {"name": name}
                binding_id = account.get("cc2api_account_id")
                configuration = cc2api_client._request("GET", f"/admin/runtime/accounts/{binding_id}/config") if binding_id is not None else None
                account.update(upstream_proxy_scheme=proxy.get("scheme"),
                    upstream_socks5_host=proxy.get("host"), upstream_socks5_port=proxy.get("port"),
                    upstream_socks5_user=proxy.get("user"), upstream_socks5_pass=proxy.get("pass"),
                    timezone=tz if timezone is not None else account.get("timezone"))
                version = version or effective_claude_code_version()
                if not existing:
                    drafts = _login_drafts()
                    draft_row = account_runtime._row(name, timezone=tz)
                    record = drafts.guard(draft_row)
                    if record["phase"] == "deleting":
                        raise ValueError("草稿正在清理，请先完成删除")
                    drafts.save(draft_row, sid=sid, generation=uuid.uuid4().hex, phase="preparing",
                        version=version, created_at=time.time(), home=f"/home/node/.v3-login/{sid}" if force_reauth else "/home/node")
                    draft_registered = True
                row, container, profile, home = account_runtime.begin_login(sid, account, version, force_reauth)
                session = LoginSession(sid, name, container.id, container.id, proxy, profile, force_reauth)
                session.home, session.version = home, version
                if draft_row:
                    record = drafts.save(row, phase="authorizing")
                    session.environment_id, session.draft_generation = row["environment_id"], record["generation"]
                if binding_id is not None:
                    session.account_id, session.binding_id = int(account["id"]), int(binding_id)
                    session.identity = {key: configuration.get(key) for key in ("email", "account_uuid", "organization_uuid")}
                    session.commit_context = account_runtime.login_commit_context(session)
                with self._lock:
                    self.sessions[sid] = session
                return session
            actual_host_profile = HOST_BENCH_DATA / "profiles" / name
            actual_local_profile = BENCH_DATA / "profiles" / name
            claude_code_version = effective_claude_code_version()
            actual_local_profile.mkdir(parents=True, exist_ok=True)
            _persist_default_claude_settings(actual_local_profile)
            _persist_default_claude_top_config(actual_local_profile)
            if force_reauth:
                # 重授权不能直接删除真实 profile 里的旧凭据；用户取消时历史账号仍要可用。
                # 因此给登录容器挂一个一次性 profile 副本，并移除副本里的 credentials，
                # 迫使 `claude auth login` 进入 OAuth 流程，commit 成功后再白名单覆盖回真实 profile。
                local_profile = BENCH_DATA / "login-sessions" / sid / "profile"
                host_profile = HOST_BENCH_DATA / "login-sessions" / sid / "profile"
                shutil.rmtree(local_profile.parent, ignore_errors=True)
                local_profile.mkdir(parents=True, exist_ok=True)
                _copy_profile_whitelist_to_claude_home(actual_local_profile, local_profile)
                try:
                    (local_profile / ".credentials.json").unlink()
                except FileNotFoundError:
                    pass
                _persist_default_claude_settings(local_profile)
                _persist_default_claude_top_config(local_profile)
            else:
                host_profile = actual_host_profile
                local_profile = actual_local_profile
            CA_DIR.mkdir(parents=True, exist_ok=True)
            host_ca = HOST_BENCH_DATA / "ca"

            sidecar_name = f"bench-login-sidecar-{sid}"
            worker_name = f"bench-login-worker-{sid}"
            sidecar_id: Optional[str] = None
            worker_network: str = "bridge"
            # login 模式与 task 模式共用同一派生指纹；TZ 使用同一套显式优先规则，
            # 确保 OAuth 时和后续 API 调用在 Anthropic 端看起来是同一台机器。
            fp = derive_fingerprint(name)

            # 有代理才起 sidecar；没填的话直走宿主默认网络（用户自担风险）
            if proxy.get("host"):
                sidecar_env = _sidecar_proxy_env(proxy)
                sidecar_env["DNS_READY_HOST"] = DNS_READY_HOST
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
                    environment=sidecar_env,
                )
                sidecar_id = sidecar.id
                _wait_sidecar_ready(self.client, sidecar_id)
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
                    "CLAUDE_CODE_VERSION": claude_code_version,
                    "TZ": tz,
                    "LANG": fp["lang"],
                    "LC_ALL": fp["lang"],
                },
            }
            if worker_network == "bridge":
                # 走 bridge 才能自己设 hostname;共享 netns 时继承 sidecar 的
                worker_kwargs["hostname"] = fp["hostname"]
            worker = self.client.containers.run(WORKER_IMAGE, **worker_kwargs)

            session = LoginSession(
                sid, name, sidecar_id, worker.id, proxy, local_profile,
                force_reauth,
            )
            with self._lock:
                self.sessions[sid] = session
            return session
        except Exception:
            try:
                if draft_registered:
                    if 'container' in locals():
                        account_runtime.cleanup(account_runtime.execution_token(container.id, f"login:{sid}"))
                    drafts.save(draft_row, phase="interrupted")
            finally:
                with self._lock:
                    self._name_locks.pop(name, None)
            if force_reauth:
                shutil.rmtree(BENCH_DATA / "login-sessions" / sid, ignore_errors=True)
            raise

    def get(self, sid: str) -> Optional[LoginSession]:
        return self.sessions.get(sid)

    def auth_status(self, sid: str) -> dict:
        s = self.get(sid)
        if not s:
            raise KeyError(sid)
        if account_runtime:
            result = account_runtime.exec_cli(account_runtime.execution_token(s.worker_id, f"login:{s.sid}"),
                ["claude", "auth", "status"], s.home, s.version)
            try:
                return json.loads(result.output)
            except (ValueError, TypeError):
                return {"loggedIn": False}
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
            environment={"HOME": s.home},
            workdir=s.home,
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

    def persist_profile_files(self, sid: str) -> None:
        """
        把登录容器写入的认证文件同步回真实账号 profile。

        :param sid: 登录会话 ID
        :return: None
        """
        s = self.get(sid)
        if not s:
            raise KeyError(sid)
        src_credentials = s.profile_dir / ".credentials.json"
        if not src_credentials.exists():
            raise ValueError("login session did not produce .credentials.json")
        dst_profile = BENCH_DATA / "profiles" / s.name
        dst_profile.mkdir(parents=True, exist_ok=True)
        for name in (".credentials.json", "settings.json"):
            src = s.profile_dir / name
            if not src.exists() or not src.is_file():
                continue
            dst = dst_profile / name
            if src.resolve() != dst.resolve():
                shutil.copy2(src, dst)
            _make_worker_owned(dst)

    def cleanup(self, sid: str) -> None:
        with self._lock:
            s = self.sessions.get(sid)
        if not s:
            return
        if account_runtime:
            account_runtime.cleanup(account_runtime.execution_token(s.worker_id, f"login:{sid}"))
            if s.binding_id is not None:
                pending_lease = cc2api_client._request("GET", f"/admin/runtime/accounts/{s.binding_id}/lease").get("lease")
                if pending_lease:
                    account_runtime.reconcile(s.commit_context["environment_id"])
                    if cc2api_client._request("GET", f"/admin/runtime/accounts/{s.binding_id}/lease").get("lease"):
                        raise ValueError("登录维护门禁仍需对账")
                s.commit_context["path"].unlink(missing_ok=True)
            if s.force_reauth:
                # 未提交草稿取消保留已写入产物；完整删除走独立归属校验路径。
                if not s.environment_id:
                    shutil.rmtree(s.profile_dir.parent, ignore_errors=True)
            if s.environment_id:
                drafts = _login_drafts()
                row = drafts.row(s.environment_id)
                if row and row["account_id"] is None and drafts.record(row)["phase"] != "deleting":
                    drafts.save(row, phase="cancelled")
            with self._lock:
                s.phase = "cancelled"
                s.import_payload, s.authorization_url = None, None
                self.sessions.pop(sid, None)
                if self._name_locks.get(s.name) == sid:
                    del self._name_locks[s.name]
            return
        with self._lock:
            self.sessions.pop(sid, None)
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
        if s.force_reauth:
            shutil.rmtree(s.profile_dir.parent, ignore_errors=True)
        with self._lock:
            if self._name_locks.get(s.name) == sid:
                del self._name_locks[s.name]

    def commit_bound(self, session: LoginSession) -> dict:
        """提交已绑定账号重授权；调用方须先取得账号所有权锁。

        :param session: 原固定环境的登录会话
        :return: 不含凭据的提交结果；结果未知时保留暂存与门禁
        """
        connection = get_db()
        try:
            row = connection.execute("SELECT * FROM accounts WHERE id=? AND deleted_at IS NULL", (session.account_id,)).fetchone()
        finally:
            connection.close()
        if not row or row["name"] != session.name or row["cc2api_account_id"] != session.binding_id:
            raise ValueError("原关联账号已改变，不能提交重授权")
        blocker = _oauth_owner_transition_blocker(dict(row), session.sid)
        if blocker:
            raise ValueError(f"账号仍有活动工作：{blocker}")
        path = session.commit_context["path"]
        snapshot = None
        if path.exists():
            record = json.loads(path.read_text())
            snapshot = cc2api_client.import_status(session.binding_id, record["operation_id"])
        else:
            status = self.auth_status(session.sid)
            if not status.get("loggedIn"):
                raise ValueError("尚未登录，请先在终端完成授权")
            session.auth_method = status.get("authMethod")
            identity = _read_bench_profile_identity(session.name, session.profile_dir, session.profile_dir.parent / ".claude.json")
            if session.identity.get("account_uuid") and not identity.get("account_uuid"):
                raise ValueError("新登录缺少账号 UUID，不能使用旧身份替代")
            _validate_cc2api_identity(identity, session.identity)
            if _normalize_identity_value(identity["email"]) != _normalize_identity_value(session.identity.get("email")):
                raise ValueError("新登录邮箱与原关联账号不匹配")
            organization = _normalize_identity_value(session.identity.get("organization_uuid"))
            if organization and organization != _normalize_identity_value(identity.get("organization_uuid")):
                raise ValueError("新登录组织与原关联账号不匹配")
            context = account_runtime.login_commit_context(session)
            if context["environment_id"] != session.commit_context["environment_id"] or context["generation"] != session.commit_context["generation"]:
                raise ValueError("原登录环境代次已改变")
            operation_id = uuid.uuid4().hex
            record = {"sid": session.sid, "name": session.name, "account_id": session.account_id,
                "cc2api_account_id": session.binding_id, "operation_id": operation_id,
                "environment_id": context["environment_id"], "generation": context["generation"],
                "lease": context["lease"], "phase": "submitting", "auth_method": status.get("authMethod"),
                "identity": {key: identity[key] for key in ("email", "account_uuid", "organization_uuid")}}
            session.import_payload = {key: identity[key] for key in ("email", "account_uuid", "organization_uuid", "access_token", "refresh_token", "expires_at")}
            session.import_payload.update(operation_id=operation_id, owner=context["lease"]["owner"], generation=context["lease"]["generation"])
            # 提交意图先落盘；HTTP 超时不能被误当成“尚未更新远端”。
            atomic_json(path, record)
            session.phase = "submitting"
        if snapshot is None:
            if session.import_payload is None:
                raise ValueError("提交结果需先对账，请在环境页执行对账")
            snapshot = cc2api_client.import_credentials(session.binding_id, session.import_payload)
        with _profile_lock(session.name):
            account_runtime.finish_bound_login(record, snapshot)
        result = {"id": session.account_id, "name": session.name, "auth_method": record.get("auth_method"),
            "cc2api_account_id": session.binding_id, "credentials_synced": True}
        try:
            account_runtime.login_commit_context(session)
        except ValueError:
            account_runtime.reconcile(record["environment_id"])
            if path.exists():
                raise ValueError("凭据已同步，但登录维护仍需对账") from None
        self.cleanup(session.sid)
        session.phase, session.import_payload = "committed", None
        with self._lock:
            self.completed[session.sid] = {"result": result, "expires_at": time.time() + 1800}
        return result

    def cleanup_reconciled(self, environment_id: str) -> None:
        """对账完成后解除遗留登录占用，让原页面可重试并允许重新登录。

        :param environment_id: 已完成对账的固定环境
        :return: None；未确认时保留会话
        """
        with self._lock:
            sessions = [session for session in self.sessions.values() if session.commit_context.get("environment_id") == environment_id
                or session.environment_id == environment_id]
        for session in sessions:
            with _oauth_owner_lock(session.name):
                if self.get(session.sid) is not session:
                    continue
                if session.binding_id is None:
                    drafts = _login_drafts()
                    row = drafts.row(environment_id)
                    if not row or row["account_id"] is not None or row["state"] != "stopped":
                        continue
                    record = drafts.guard(row, session.draft_generation)
                    if (record.get("sid") != session.sid or environment_id in account_runtime.jobs
                        or (account_runtime._root(row) / "runtime" / "execution.json").exists()):
                        continue
                    # 只收口本代已停止的未绑定会话，不让旧名称占用挡住恢复/重登。
                    self.cleanup(session.sid)
                    continue
                if environment_id in account_runtime.jobs or session.commit_context["path"].exists():
                    continue
                snapshot = cc2api_client.import_status(session.binding_id, session.import_payload["operation_id"]) if session.import_payload else None
                self.cleanup(session.sid)
                if snapshot is not None:
                    with self._lock:
                        self.completed[session.sid] = {"expires_at": time.time() + 1800, "result": {
                            "id": session.account_id, "name": session.name, "auth_method": session.auth_method,
                            "cc2api_account_id": session.binding_id, "credentials_synced": True}}


class ContinueManager:
    """管理 runs 的继续对话 PTY 会话"""

    def __init__(self, runner: Runner) -> None:
        self.runner = runner
        self.sessions: dict[str, ContinueSession] = {}
        self._run_locks: dict[str, str] = {}
        self._lock = threading.Lock()
        self._capture_started_at = 0.0

    def cleanup_stale(self) -> None:
        """启动时清掉上次残留的 bench-continue-* 容器"""
        if account_runtime:
            return
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

    def has_active_account(self, account_id: int) -> bool:
        """
        判断账号是否存在活跃的继续对话 worker。

        :param account_id: accounts.id
        :return: 存在活跃 continue 会话时返回 True
        """
        with self._lock:
            return any(
                session.account_id == account_id
                for session in self.sessions.values()
            )

    def start(self, run: dict, account: dict) -> ContinueSession:
        """
        为一个完成 run 启动继续对话会话。

        :param run: runs 表行
        :param account: accounts 表行
        :return: ContinueSession
        """
        if login_manager and login_manager.has_active_name(str(account["name"])):
            raise ValueError("账号正在重新授权，请完成后再继续对话")
        session_id = _find_latest_claude_session_id(run["id"])
        if not session_id:
            raise ValueError(
                f"运行 {run['id']} 未创建 Claude 会话，无法继续；"
                "该 run 没有可恢复记录，请重新运行任务"
            )
        with self._lock:
            if run["id"] in self._run_locks:
                raise ValueError(f"continue session already active for run {run['id']}")
            sid = uuid.uuid4().hex[:12]
            self._run_locks[run["id"]] = sid
        try:
            permission_mode = _resolve_capture_permission_mode(
                run.get("capture_permission_mode")
            )
            if quota_guard and quota_guard.snapshot(account).get("account_error"):
                raise ValueError("账号存在永久认证异常，需先人工核实")
            source = f"continue:{sid}:0"
            sidecar_id, worker_id = None, None
            if not quota_guard or quota_guard.admit(account, source):
                if account.get("cc2api_account_id") is not None:
                    _sync_bound_account_credentials_locked(account, 2400)
                sidecar_id, worker_id = self.runner.start_continue(sid, run, account, session_id)
            session = ContinueSession(
                sid,
                run["id"],
                int(account["id"]),
                sidecar_id,
                worker_id,
                session_id,
                permission_mode,
            )
            session.run = dict(run)
            session.identity = _quota_identity(account) if quota_guard else ""
            session.quota = quota_guard.snapshot(account) if quota_guard else {}
            with self._lock:
                self.sessions[sid] = session
                if run.get("run_kind") == "capture":
                    if worker_id:
                        self._capture_started_at = time.time()
                    else:
                        session.resume_not_before = time.time() + 900
            return session
        except Exception:
            if quota_guard:
                quota_guard.release(account, f"continue:{sid}:0")
            with self._lock:
                self._run_locks.pop(run["id"], None)
            raise

    def get(self, sid: str) -> Optional[ContinueSession]:
        """按 sid 返回继续对话会话。"""
        return self.sessions.get(sid)

    def cleanup(self, sid: str) -> None:
        """停止并清理继续对话容器，同时尽量回写本地配置。"""
        with self._lock:
            s = self.sessions.pop(sid, None)
        if not s:
            return
        with s.guard_lock:
            s.status = "closed"
            s.connected = False
            self.runner.persist_worker_profile(s.worker_id)
            self.runner.cleanup(s.sidecar_id, s.worker_id)
            if quota_guard:
                conn = get_db()
                try:
                    account_row = conn.execute("SELECT * FROM accounts WHERE id=?", (s.account_id,)).fetchone()
                finally:
                    conn.close()
                if account_row:
                    quota_guard.consume(dict(account_row))
                    quota_guard.release(dict(account_row), f"continue:{s.sid}:{s.generation}")
        if not account_runtime:
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

    def _suspend_quota(self, session: ContinueSession, account: dict) -> None:
        source = f"continue:{session.sid}:{session.generation}"
        session.status = "quota_wait"
        session.quota = quota_guard.snapshot(account)
        if session.run.get("run_kind") == "capture":
            session.resume_not_before = time.time() + 900
        self.runner.persist_worker_profile(session.worker_id)
        # 若删除失败，保留原 ID；下轮重试，绝不启动第二份执行。
        if account_runtime:
            self.runner.cleanup(session.sidecar_id, session.worker_id)
        else:
            for container_id in (session.worker_id, session.sidecar_id):
                if container_id:
                    try:
                        self.runner.client.containers.get(container_id).remove(force=True)
                    except NotFound:
                        pass
        session.sidecar_id = None
        session.worker_id = None
        quota_guard.release(account, source)
        session.generation += 1

    def _apply_control(self, session: ContinueSession, account: dict) -> bool:
        source = f"continue:{session.sid}:{session.generation}"
        path = _quota_control(session.run_id, source) / "pause.json"
        if not path.exists():
            return False
        try:
            payload = json.loads(path.read_text())
        except (OSError, ValueError):
            payload = {}
        if isinstance(payload, dict) and payload.get("source") == source and payload.get("status") == "quota_wait":
            quota_guard.record_control_state(account, source, payload)
            if quota_guard.snapshot(account).get("account_error"):
                session.quota = quota_guard.snapshot(account)
                self.cleanup(session.sid)
            else:
                self._suspend_quota(session, account)
        else:
            session.quota = {"message": "额度门禁执行异常，继续会话已停止"}
            self.cleanup(session.sid)
        return True

    def quota_tick(self, account: dict) -> None:
        """
        收口已耗尽的交互执行，到期恢复仍在线的原会话。

        :param account: 当前账号行
        :return: None
        """
        with self._lock:
            sessions = [session for session in self.sessions.values() if session.account_id == account["id"]]
        for session in sessions:
            with session.guard_lock:
                if self.get(session.sid) is not session or session.status == "closed":
                    continue
                if not account.get("enabled") or _quota_identity(account) != session.identity:
                    self.cleanup(session.sid)
                    continue
                source = f"continue:{session.sid}:{session.generation}"
                if quota_guard.snapshot(account).get("account_error"):
                    session.quota = quota_guard.snapshot(account)
                    self.cleanup(session.sid)
                    continue
                if session.status == "running" and self._apply_control(session, account):
                    continue
                if session.status != "quota_wait":
                    continue
                session.quota = quota_guard.snapshot(account)
                if session.worker_id or session.sidecar_id:
                    self._suspend_quota(session, account)
                    continue
                if not session.connected or time.time() < session.resume_not_before:
                    continue
                if session.run.get("run_kind") == "capture" and not quota_guard.capture_resume_ready(session.run_id):
                    continue
                with _oauth_owner_lock(str(account["name"])):
                    conn = get_db()
                    try:
                        current = _get_available_account(conn, session.account_id)
                        original = conn.execute("SELECT deleted_at FROM runs WHERE id=?", (session.run_id,)).fetchone()
                    finally:
                        conn.close()
                    if not current or not original or original["deleted_at"] is not None:
                        self.cleanup(session.sid)
                        continue
                    account = dict(current)
                    if not quota_guard.admit(account, source):
                        continue
                    try:
                        if account.get("cc2api_account_id") is not None:
                            _sync_bound_account_credentials_locked(account, 2400)
                        run = {**session.run, "continue_generation": session.generation}
                        session.sidecar_id, session.worker_id = self.runner.start_continue(
                            session.sid, run, account, session.session_id)
                        session.status = "running"
                        if session.run.get("run_kind") == "capture":
                            with self._lock:
                                self._capture_started_at = time.time()
                    except Exception:
                        # 非额度失败遵循失败收口，不在后台反复重建或重试认证。
                        quota_guard.release(account, source)
                        self.cleanup(session.sid)

    def send_input(self, session: ContinueSession, generation: int, raw, data: bytes) -> bool:
        """
        只向仍有效且允许输入的 PTY 发送，不缓存等待期输入。

        :param session: 当前继续会话
        :param generation: 浏览器桥对应执行代次
        :param raw: PTY socket
        :param data: 文本或二进制输入
        :return: 实际发送时返回 True
        """
        with session.guard_lock:
            if self.get(session.sid) is not session or session.status != "running" or generation != session.generation:
                return False
            if quota_guard:
                conn = get_db()
                try:
                    row = _get_available_account(conn, session.account_id)
                finally:
                    conn.close()
                if not row:
                    self.cleanup(session.sid)
                    return False
                account = dict(row)
                quota_guard.consume(account)
                if self._apply_control(session, account):
                    return False
                state = quota_guard.snapshot(account)
                if state["blocked"] or (state["retry_ready"] and state["recovery_source"] != f"continue:{session.sid}:{generation}"):
                    self._suspend_quota(session, account)
                    return False
            raw.send(data)
            return True


def _oauth_refresh_error_summary(error: object) -> str:
    """
    把后台 OAuth 刷新异常收敛成不含凭据的安全摘要。

    :param error: 原始异常或错误对象
    :return: 仅包含固定错误类别、HTTP 状态、OAuth 错误码和 retry-after 的摘要
    """
    raw = str(error)
    parts = ["OAuth token 刷新失败"]
    status_match = re.search(r"\bHTTP\s+(\d{3})\b", raw, re.IGNORECASE)
    if status_match:
        parts.append(f"HTTP {status_match.group(1)}")
    code_match = re.search(
        r"\b(invalid_scope|invalid_grant|invalid_request|temporarily_unavailable|"
        r"server_error|unsupported_grant_type)\b",
        raw,
        re.IGNORECASE,
    )
    if code_match:
        parts.append(code_match.group(1).lower())
    retry_match = re.search(r"\bretry_after_sec=(\d+)\b", raw, re.IGNORECASE)
    if retry_match:
        parts.append(f"retry_after_sec={retry_match.group(1)}")
    if len(parts) == 1:
        lowered = raw.lower()
        if "refresh token" in lowered and ("为空" in raw or "missing" in lowered):
            parts.append("refresh_token_missing")
        elif ".credentials.json" in raw or "claudeaioauth" in lowered:
            parts.append("credentials_invalid")
        elif "upstream proxy" in lowered:
            parts.append("proxy_missing")
        elif "响应不是 json" in raw.lower() or "缺少 access_token" in raw.lower():
            parts.append("invalid_response")
        else:
            parts.append("internal_error")
    return "; ".join(parts)


def _record_oauth_refresh_attempt(
    account_id: int,
    status: str,
    error: Optional[str] = None,
) -> None:
    """
    持久化未绑定账号最后一次真实 OAuth 刷新尝试的安全状态。

    :param account_id: accounts.id
    :param status: `success` 或 `failed`
    :param error: 已脱敏错误摘要；成功时传 None
    :return: None
    """
    if status not in {"success", "failed"}:
        raise ValueError("OAuth 刷新状态无效")
    with _db_lock:
        conn = get_db()
        try:
            with conn:
                conn.execute(
                    "UPDATE accounts SET oauth_refresh_last_attempt_at=?, "
                    "oauth_refresh_last_status=?, oauth_refresh_last_error=? "
                    "WHERE id=? AND cc2api_account_id IS NULL AND deleted_at IS NULL",
                    (time.time(), status, error if status == "failed" else None, account_id),
                )
        finally:
            conn.close()


class OAuthRefreshScheduler:
    """后台定时刷新账号 OAuth access token。"""

    def __init__(self, runner: Runner) -> None:
        self.runner = runner
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        """
        启动后台刷新线程。

        :return: None
        """
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def cleanup_stale(self) -> None:
        """
        启动时清掉上次残留的 bench-oauth-refresh-* 容器。

        :return: None
        """
        if account_runtime:
            return
        try:
            for c in self.runner.client.containers.list(
                all=True, filters={"name": "bench-oauth-refresh-"}
            ):
                try:
                    c.remove(force=True)
                except Exception:
                    pass
        except Exception:
            pass

    def stop(self) -> None:
        """
        请求后台刷新线程停止。

        :return: None
        """
        self._stop.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=3)

    def _loop(self) -> None:
        # 启动后立即 tick 一次，避免服务重启时 profile 已过期还要等 60 秒。
        while not self._stop.is_set():
            try:
                self._tick()
            except Exception:
                # 任意一次 tick 的意外异常都不能永久杀死后台刷新线程。
                pass
            self._stop.wait(OAUTH_REFRESH_INTERVAL_SEC)

    def _tick(self) -> None:
        conn = get_db()
        try:
            rows = conn.execute(
                "SELECT * FROM accounts WHERE enabled=1 AND deleted_at IS NULL ORDER BY id"
            ).fetchall()
            accounts = [dict(r) for r in rows]
        except Exception:
            return
        finally:
            conn.close()
        for account in accounts:
            if self._stop.is_set():
                return
            with _oauth_owner_lock(str(account["name"])):
                conn = get_db()
                try:
                    try:
                        current_row = _get_available_account(conn, int(account["id"]))
                        if not current_row:
                            continue
                        current = dict(current_row)
                    except Exception:
                        # 单账号重读失败时跳过本账号，后续账号仍需继续扫描。
                        continue
                finally:
                    conn.close()
                if current.get("cc2api_account_id") is not None:
                    try:
                        _sync_bound_account_credentials_locked(
                            current,
                            OAUTH_REFRESH_BUFFER_SEC,
                        )
                    except Exception:
                        # cc2api 是绑定账号唯一凭据所有者；同步失败时不能降级成本地 RT 刷新。
                        pass
                    continue
                try:
                    needs_refresh = self._needs_refresh(current["name"])
                except Exception:
                    continue
                if not needs_refresh:
                    continue
                try:
                    refreshed = self.runner.refresh_account_oauth_token(current)
                except Exception as exc:
                    # 本地 RT 刷新也持有 owner lock，避免首次绑定读取到轮换前的旧 RT。
                    try:
                        _record_oauth_refresh_attempt(
                            int(current["id"]),
                            "failed",
                            _oauth_refresh_error_summary(exc),
                        )
                    except Exception:
                        # 状态落库失败不能覆盖原刷新异常或中断后续账号。
                        pass
                    continue
                if refreshed:
                    try:
                        _record_oauth_refresh_attempt(int(current["id"]), "success")
                    except Exception:
                        pass

    def _needs_refresh(self, account_name: str) -> bool:
        """
        判断账号 access token 是否缺失、已过期或 10 分钟内过期。

        :param account_name: accounts.name 字段
        :return: 需要刷新时返回 True
        """
        status = _read_account_oauth_status(account_name)
        if status["oauth_token_state"] in {"missing", "expired", "expiring", "invalid"}:
            return True
        expires_in = status.get("oauth_expires_in_sec")
        return isinstance(expires_in, int) and expires_in <= OAUTH_REFRESH_BUFFER_SEC


def _find_latest_claude_session_id(run_id: str) -> Optional[str]:
    """
    从 run workspace 中找到最近的 Claude session jsonl。

    :param run_id: runs.id
    :return: session id，找不到则 None
    """
    base = account_runtime.run_session_path(run_id) if account_runtime else (
        WORKSPACES_DIR / run_id / ".claude-home" / "projects"
    )
    if not base.exists():
        return None
    files = [p for p in (base.glob("*.jsonl") if account_runtime else base.glob("*/*.jsonl")) if p.is_file()]
    try:
        baseline_path = account_runtime.run_artifact_path(run_id, "session-baseline.json") if account_runtime else (
            WORKSPACES_DIR / run_id / ".bench-session-baseline.json"
        )
        baseline = json.loads(baseline_path.read_text())
        files = [p for p in files if (account_runtime or p.parent.name == "-workspace")
            and p.stat().st_size > int(baseline.get(p.name, 0))]
    except (OSError, ValueError, TypeError, AttributeError):
        pass
    if not files:
        return None
    latest = max(files, key=lambda p: p.stat().st_mtime)
    return latest.stem


def _aggregate_claude_session_usage(run_id: str) -> dict[str, int | bool]:
    """
    从 Claude session JSONL 聚合 usage，作为 sidecar stats 缺失时的回退来源。

    :param run_id: runs.id
    :return: token / 请求数 / 可用性聚合结果
    """
    base = account_runtime.run_session_path(run_id) if account_runtime else (
        WORKSPACES_DIR / run_id / ".claude-home" / "projects"
    )
    if not base.exists():
        return {
            "tokens_in": 0,
            "tokens_out": 0,
            "requests": 0,
            "usage_available": False,
        }
    tokens_in = tokens_out = requests = 0
    seen_requests: set[str] = set()
    for path in sorted((p for p in base.rglob("*.jsonl") if p.is_file()), key=lambda p: p.stat().st_mtime):
        for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            message = rec.get("message")
            if not isinstance(message, dict) or message.get("role") != "assistant":
                continue
            if rec.get("type") not in (None, "assistant"):
                continue
            usage = message.get("usage")
            if not isinstance(usage, dict):
                continue
            request_key = rec.get("requestId")
            if not isinstance(request_key, str) or not request_key:
                request_key = json.dumps(usage, sort_keys=True, ensure_ascii=False)
            if request_key in seen_requests:
                continue
            seen_requests.add(request_key)
            tokens_in += _usage_input_tokens(usage)
            tokens_out += int(usage.get("output_tokens") or 0)
            requests += 1
    return {
        "tokens_in": tokens_in,
        "tokens_out": tokens_out,
        "requests": requests,
        "usage_available": requests > 0,
    }


_SENSITIVE_HEADER_RE = re.compile(
    r"(authorization|cookie|set-cookie|x-api-key|token|secret|credential|key)",
    re.IGNORECASE,
)


def _redact_capture_value(name: str, value: object) -> object:
    """
    对抓包索引预览里的敏感 header 值做脱敏。

    :param name: header 或字段名
    :param value: 原始值
    :return: 可安全展示的值
    """
    if _SENSITIVE_HEADER_RE.search(name):
        return "[redacted]"
    return value


def _redact_capture_headers(headers: object) -> dict[str, object]:
    """
    脱敏 header 对象，供 WebUI / API 预览使用。

    :param headers: header dict
    :return: 脱敏后的 header dict
    """
    if not isinstance(headers, dict):
        return {}
    return {
        str(k): _redact_capture_value(str(k), v)
        for k, v in headers.items()
    }


def _redact_capture_record(record: object) -> object:
    """
    对 capture_index.json 里的单条索引记录做浅层脱敏。

    :param record: 索引记录
    :return: 脱敏后的记录
    """
    if not isinstance(record, dict):
        return record
    out = dict(record)
    for section in ("request", "response"):
        value = out.get(section)
        if not isinstance(value, dict):
            continue
        copied = dict(value)
        copied["headers"] = _redact_capture_headers(copied.get("headers"))
        out[section] = copied
    analysis = out.get("analysis")
    if isinstance(analysis, dict):
        copied = dict(analysis)
        if "cch_headers" in copied:
            copied["cch_headers"] = _redact_capture_headers(copied.get("cch_headers"))
        out["analysis"] = copied
    return out


def _read_capture_index(path: Path) -> dict[str, object]:
    """
    读取并脱敏抓包索引。

    :param path: capture_index.json 路径
    :return: 索引内容；不存在或解析失败时返回可展示状态
    """
    if not path.exists():
        return {
            "available": False,
            "error": "capture_index.json not found",
            "entries": [],
        }
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {
            "available": False,
            "error": f"failed to read capture index: {exc}",
            "entries": [],
        }
    if not isinstance(data, dict):
        return {
            "available": False,
            "error": "capture index is not an object",
            "entries": [],
        }
    entries = data.get("entries")
    if isinstance(entries, list):
        data["entries"] = [_redact_capture_record(item) for item in entries]
    data["available"] = True
    return data


def _capture_files(base: Path) -> list[dict[str, object]]:
    """
    返回抓包目录下的文件列表。

    :param base: run flows 目录
    :return: 文件元信息列表
    """
    if not base.exists():
        return []
    files: list[dict[str, object]] = []
    paths = {p for p in base.rglob("*") if p.is_file()}
    for directory in base.glob("continue-*"):
        paths.update(p for p in directory.rglob("*") if p.is_file())
    for path in sorted(paths):
        rel = path.relative_to(base)
        files.append({
            "path": str(rel),
            "size": path.stat().st_size,
        })
    return files


# ============== 调度器：每账号 Semaphore(2) ==============
class Scheduler:
    def __init__(self, runner: Runner) -> None:
        self.runner = runner
        self._sems: dict[int, threading.Semaphore] = {}
        self._sems_lock = threading.Lock()
        self._batch_threads: dict[int, threading.Thread] = {}
        self._batch_restart: set[int] = set()
        self._batch_lock = threading.Lock()
        self._executing: set[tuple[str, int]] = set()
        self._execution_lock = threading.Lock()

    def is_executing(self, run_id: str, attempt: int) -> bool:
        """
        查询代次是否仍在收口。

        :param run_id: 原 run ID
        :param attempt: 执行代次
        :return: 仍在执行或收口时返回 True
        """
        with self._execution_lock:
            return (run_id, attempt) in self._executing

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
                self._batch_restart.add(batch_id)
                return
            t = threading.Thread(target=self._execute_batch, args=(batch_id,), daemon=True)
            self._batch_threads[batch_id] = t
            t.start()

    def recover_active_batches(self) -> None:
        """恢复 v3 服务重启前仍启用的活动批次，不恢复暂停或已结束批次。

        :return: None；原 item 状态和计划投放时间保持
        """
        connection = get_db()
        try:
            batches = connection.execute(
                "SELECT b.id FROM task_batches b JOIN accounts a ON a.id=b.account_id "
                "WHERE b.status='active' AND b.deleted_at IS NULL AND a.enabled=1 AND a.deleted_at IS NULL",
            ).fetchall()
        finally:
            connection.close()
        for batch in batches:
            self.submit_batch(int(batch["id"]))

    def _execute_batch(self, batch_id: int) -> None:
        try:
            conn = get_db()
            try:
                batch_row = conn.execute(
                    "SELECT * FROM task_batches WHERE id=? AND deleted_at IS NULL",
                    (batch_id,),
                ).fetchone()
                if not batch_row:
                    return
                account_row = conn.execute(
                    "SELECT * FROM accounts WHERE id=? AND enabled=1 AND deleted_at IS NULL",
                    (batch_row["account_id"],),
                ).fetchone()
                if not account_row:
                    self._pause_batch_for_unavailable_account(batch_id)
                    return
                items = conn.execute(
                    "SELECT bi.*, t.no AS topic_no, t.title, t.description "
                    "FROM task_batch_items bi JOIN topics t ON bi.topic_id=t.id "
                    "WHERE bi.batch_id=? AND bi.status IN ('pending','paused') ORDER BY bi.id",
                    (batch_id,),
                ).fetchall()
                batch = dict(batch_row)
                account = dict(account_row)
            finally:
                conn.close()

            # 重启恢复不能跳过此前保存的投放间隔；仍由原状态检查处理暂停和停止。
            if V3_ENABLED and batch.get("next_launch_at") and batch["next_launch_at"] > time.time():
                if not self._sleep_batch_delay(batch_id, batch["next_launch_at"] - time.time()):
                    return
            active_runs: list[str] = []
            for idx, item_row in enumerate(items):
                current = self._get_batch_status(batch_id)
                if current != "active":
                    break
                if quota_guard:
                    quota_guard.consume(account)
                    if (
                        quota_guard.snapshot(account)["blocked"]
                        or quota_guard.policy_snapshot(account, "normal")["blocked"]
                    ):
                        self._wait_batch_quota(batch_id, account)
                        break
                # 先投满并发窗口；之后每次等一个 run 收口再按随机间隔投放下一项。
                if len(active_runs) >= int(batch.get("concurrency") or 2):
                    self._wait_any_run_finished(active_runs)
                    if self._get_batch_status(batch_id) != "active":
                        break
                if idx >= int(batch.get("concurrency") or 2):
                    delay = self._random_batch_delay(batch)
                    if delay > 0:
                        self._set_batch_next_launch(batch_id, time.time() + delay)
                        if not self._sleep_batch_delay(batch_id, delay):
                            break
                item = dict(item_row)
                run_id = uuid.uuid4().hex[:12]
                created = self._create_batch_task_and_run(batch, account, item, run_id)
                if created is None:
                    if self._get_batch_status(batch_id) != "active":
                        break
                    continue
                task_id, claude_code_version, claude_effort_level = created
                task = {
                    "id": task_id,
                    "prompt": item["prompt"],
                    "timeout_sec": batch["timeout_sec"],
                    "batch_id": batch_id,
                    "topic_id": item["topic_id"],
                    "claude_code_version": claude_code_version,
                    "claude_effort_level": claude_effort_level,
                }
                self.submit(run_id, account, task)
                active_runs.append(run_id)

            self._wait_all_runs_finished(active_runs)
            self._finish_batch_when_done(batch_id)
        finally:
            with self._batch_lock:
                if self._batch_threads.get(batch_id) is threading.current_thread():
                    self._batch_threads.pop(batch_id, None)
                    should_restart = batch_id in self._batch_restart
                    self._batch_restart.discard(batch_id)
                    if should_restart and self._get_batch_status(batch_id) == "active":
                        t = threading.Thread(target=self._execute_batch, args=(batch_id,), daemon=True)
                        self._batch_threads[batch_id] = t
                        t.start()

    def _create_batch_task_and_run(
        self, batch: dict, account: dict, item: dict, run_id: str
    ) -> Optional[tuple[int, str, str]]:
        """
        为批次 item 创建兼容旧 runs 的 task + run。

        :param batch: task_batches 行
        :param account: accounts 行
        :param item: task_batch_items 行
        :param run_id: 新 run id
        :return: `(task_id, claude_code_version, claude_effort_level)`；批次不可执行时返回 None
        """
        claude_code_version = effective_claude_code_version()
        claude_effort_level = effective_runtime_effort()
        with _db_lock:
            conn = get_db()
            try:
                with conn:
                    current_batch = conn.execute(
                        "SELECT status FROM task_batches WHERE id=? AND deleted_at IS NULL",
                        (batch["id"],),
                    ).fetchone()
                    current_item = conn.execute(
                        "SELECT status FROM task_batch_items WHERE id=?",
                        (item["id"],),
                    ).fetchone()
                    current_account = _get_available_account(conn, int(account["id"]))
                    if (
                        not current_batch
                        or current_batch["status"] != "active"
                        or not current_item
                        or current_item["status"] not in ("pending", "paused")
                    ):
                        return None
                    if not current_account:
                        conn.execute(
                            "UPDATE task_batches SET status='paused', next_launch_at=NULL, "
                            "updated_at=julianday('now') WHERE id=? AND status='active'",
                            (batch["id"],),
                        )
                        return None
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
                        "INSERT INTO runs(id, task_id, account_id, batch_id, topic_id, status, "
                        "claude_code_version, claude_effort_level) VALUES(?,?,?,?,?,?,?,?)",
                        (
                            run_id,
                            task_id,
                            account["id"],
                            batch["id"],
                            item["topic_id"],
                            "queued",
                            claude_code_version,
                            claude_effort_level,
                        ),
                    )
                    conn.execute(
                        "UPDATE task_batch_items SET task_id=?, run_id=?, status='queued', "
                        "updated_at=julianday('now') WHERE id=?",
                        (task_id, run_id, item["id"]),
                    )
                    return task_id, claude_code_version, claude_effort_level
            finally:
                conn.close()

    def _pause_batch_for_unavailable_account(self, batch_id: int) -> None:
        """
        账号被删除或停用后暂停批次，避免后台继续投放新 run。

        :param batch_id: task_batches.id
        :return: None
        """
        with _db_lock:
            conn = get_db()
            try:
                with conn:
                    conn.execute(
                        "UPDATE task_batches SET status='paused', next_launch_at=NULL, "
                        "updated_at=julianday('now') WHERE id=? AND status='active'",
                        (batch_id,),
                    )
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

    def _sleep_batch_delay(self, batch_id: int, delay: int) -> bool:
        """
        按秒等待批次间隔，让暂停操作不必等完整随机间隔结束才生效。

        :param batch_id: task_batches.id
        :param delay: 需要等待的秒数
        :return: 等待结束后批次仍为 active 时返回 True
        """
        deadline = time.time() + max(0, delay)
        while time.time() < deadline:
            if self._get_batch_status(batch_id) != "active":
                return False
            time.sleep(min(1, max(0, deadline - time.time())))
        return self._get_batch_status(batch_id) == "active"

    def _finish_batch_when_done(self, batch_id: int) -> None:
        with _db_lock:
            conn = get_db()
            try:
                with conn:
                    row = conn.execute(
                        "SELECT COUNT(*) AS n FROM task_batch_items "
                        "WHERE batch_id=? AND status IN ('pending','paused','queued','running','quota_wait')",
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
            if any(status == "quota_wait" for status in statuses.values()):
                # 其它已在途执行由各自线程收口；批次等待不能占住一个永久等终态的调度线程。
                run_ids.clear()
                return
            done = [rid for rid in run_ids if statuses.get(rid) in _TERMINAL_RUN_STATUSES or statuses.get(rid) == "quota_wait"]
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
        attempt = int(task.get("quota_attempt") or 0)
        with self._execution_lock:
            if (run_id, attempt) in self._executing:
                return
            self._executing.add((run_id, attempt))
        sem = self._sem(account["id"])
        sem_acquired = False
        sid: Optional[str] = None
        wid: Optional[str] = None
        managed_refresh_stop = threading.Event()
        managed_refresh_thread: Optional[threading.Thread] = None
        attempt = int(task.get("quota_attempt") or 0)
        source = _quota_source(run_id, attempt)
        try:
            flows_path = FLOWS_DIR / account["name"] / str(task["id"]) / run_id
            capture_full_http = bool(task.get("capture_full_http"))
            initial_state = self._get_run_state(run_id)
            if not initial_state or initial_state.get("deleted_at") is not None:
                return
            if int(initial_state.get("quota_attempt") or 0) != attempt:
                return
            if initial_state["status"] in ("stopping", "stopped"):
                self._update_batch_item_for_run(run_id, "stopped")
                return
            if quota_guard and initial_state.get("run_kind") in ("normal", "warmup"):
                quota_guard.consume(account)
                if quota_guard.policy_snapshot(account, initial_state["run_kind"], source)["blocked"]:
                    if not initial_state.get("quota_identity"):
                        self._update_attempt(
                            run_id,
                            attempt,
                            quota_identity=_quota_identity(account),
                        )
                    self._mark_quota_wait(run_id, account, attempt)
                    return
            sem.acquire()
            sem_acquired = True
            with _oauth_owner_lock(str(account["name"])):
                conn = get_db()
                try:
                    current_account_row = _get_available_account(conn, int(account["id"]))
                    if not current_account_row:
                        self._update_attempt(
                            run_id, attempt,
                            status="failed",
                            error="账号不存在或已停用",
                            ended_at=time.time(),
                        )
                        self._update_batch_item_for_run(run_id, "failed")
                        return
                    account = dict(current_account_row)
                finally:
                    conn.close()
                current = self._get_run_state(run_id)
                if (not current or current["status"] != "queued" or current.get("stop_requested_at")
                        or int(current.get("quota_attempt") or 0) != attempt):
                    return
                if quota_guard and quota_guard._cancel_changed_identity(current, account):
                    return
                if quota_guard and not current.get("quota_identity"):
                    self._update_attempt(run_id, attempt, quota_identity=_quota_identity(account))
                if login_manager and login_manager.has_active_name(str(account["name"])):
                    if self._update_attempt(run_id, attempt, status="failed", error="账号正在重新授权，请完成后再次运行", ended_at=time.time()):
                        self._update_batch_item_for_run(run_id, "failed")
                    return
                conn = get_db()
                try:
                    parent_task = conn.execute("SELECT deleted_at FROM tasks WHERE id=?", (task["id"],)).fetchone()
                    parent_batch = conn.execute("SELECT status,deleted_at FROM task_batches WHERE id=?", (current["batch_id"],)).fetchone() if current["batch_id"] else None
                finally:
                    conn.close()
                if (not parent_task or parent_task["deleted_at"] is not None
                        or (parent_batch and (parent_batch["deleted_at"] is not None or parent_batch["status"] not in ("active", "quota_wait")))
                        or (current["run_kind"] == "warmup" and not account.get("warmup_enabled"))):
                    if self._update_attempt(run_id, attempt, status="stopped", ended_at=time.time()):
                        self._update_batch_item_for_run(run_id, "stopped")
                    return
                # 首次进入启动流程即固化模型；自动恢复读取原 run 的快照。
                model = current.get("execution_model")
                if model is None:
                    model = (task.get("model_override") or "") if capture_full_http else effective_runtime_model()
                    self._update_attempt(run_id, attempt, execution_model=model)
                task["model_override"] = model
                task["warmup"] = current.get("run_kind") == "warmup"
                workload = (
                    "warmup" if current["run_kind"] == "warmup"
                    else "normal" if current["run_kind"] == "normal"
                    else None
                )
                if quota_guard and not quota_guard.admit(
                    account,
                    source,
                    workload=workload,
                ):
                    state = quota_guard.snapshot(account)
                    if state.get("account_error"):
                        self._update_attempt(run_id, attempt, status="auth_failed", error=state["message"], ended_at=time.time())
                        self._update_batch_item_for_run(run_id, "auth_failed")
                    else:
                        self._mark_quota_wait(run_id, account, attempt)
                    return
                if attempt > 0:
                    task["resume_session_id"] = _find_latest_claude_session_id(run_id)
                if account.get("cc2api_account_id") is not None:
                    timeout_sec = max(60, int(task.get("timeout_sec") or 1800))
                    try:
                        _sync_bound_account_credentials_locked(account, timeout_sec + 600)
                    except Exception as exc:
                        error = _redact_cc2api_error(exc)
                        if quota_guard and "invalid_grant" in error:
                            quota_guard.record_auth_failure(account, "invalid_grant")
                        self._update_attempt(
                            run_id, attempt,
                            status="failed",
                            error=error,
                            ended_at=time.time(),
                        )
                        self._update_batch_item_for_run(run_id, "failed")
                        if warmup_scheduler:
                            warmup_scheduler.handle_run_sync_failure(run_id, account, exc)
                        return
                if not self._update_attempt(
                    run_id,
                    attempt,
                    status="running",
                    started_at=time.time(),
                    workspace_dir=str(WORKSPACES_DIR / run_id),
                    flows_dir=str(flows_path),
                    capture_summary_path=str(flows_path / "capture_index.json") if capture_full_http else None,
                ):
                    return
                if warmup_scheduler:
                    warmup_scheduler.handle_run_started(run_id)
                try:
                    sid, wid = self.runner.start_run(run_id, account, task)
                except Exception as exc:
                    deferred = bool(task.get("warmup") and isinstance(exc, RuntimeBusy))
                    self._update_attempt(
                        run_id, attempt,
                        status="stopped" if deferred else "failed",
                        error="养号顺延：" + str(exc) if deferred else str(exc),
                        ended_at=time.time(),
                    )
                    self._update_batch_item_for_run(run_id, "failed")
                    return
                self._update_attempt(run_id, attempt, sidecar_container=sid, worker_container=wid)
            try:
                if account.get("cc2api_account_id") is not None:
                    managed_refresh_thread = threading.Thread(
                        target=self.runner.watch_managed_oauth_refresh,
                        args=(run_id, account, managed_refresh_stop, wid),
                        daemon=True,
                    )
                    managed_refresh_thread.start()
                run_state = self._get_run_state(run_id)
                if run_state and run_state["status"] in ("stopping", "stopped"):
                    self.runner.persist_worker_profile(wid)
                    self.runner.cleanup(sid, wid)
                    self._update_attempt(run_id, attempt, status="stopped", ended_at=time.time())
                    self._update_batch_item_for_run(run_id, "stopped")
                    return
                exit_code = self.runner.wait_worker(wid)
                if quota_guard:
                    # 先消费最后的本地观察，再发布终态，让批次看到本次执行产生的额度。
                    quota_guard.consume(account)
                run_state = self._get_run_state(run_id)
                if run_state and run_state["status"] in ("stopping", "stopped"):
                    status = "stopped"
                elif exit_code == 0:
                    status = "success"
                elif exit_code == 124:
                    status = "timeout"
                elif exit_code == 42:
                    status = "auth_failed"
                else:
                    status = "failed"
                worker_status = self.runner.read_worker_status(run_id)
                error = worker_status.get("error") if isinstance(worker_status.get("error"), str) else None
                status_hint = worker_status.get("status")
                if status != "stopped" and (exit_code == 43 or status_hint == "quota_wait"):
                    if quota_guard:
                        quota_guard.record_control_state(account, source, worker_status)
                    if quota_guard and error and error.startswith("被动识别额度耗尽:"):
                        quota_guard.record_worker_limit(account, error.split(":", 1)[1])
                    self._mark_quota_wait(run_id, account, attempt)
                    return
                if status_hint == "auth_failed" and status != "stopped":
                    status = "auth_failed"
                    error = error or "OAuth 认证失败"
                    if quota_guard and ("account_on_hold" in error or "invalid_grant" in error):
                        quota_guard.record_auth_failure(account, "account_on_hold" if "account_on_hold" in error else "invalid_grant")
                elif status_hint in ("failed", "timeout") and status != "stopped":
                    status = status_hint
                update_fields = {
                    "status": status,
                    "exit_code": exit_code,
                    "ended_at": time.time(),
                }
                if error and status not in ("success", "stopped"):
                    update_fields["error"] = error
                if self._update_attempt(run_id, attempt, **update_fields):
                    self._update_batch_item_for_run(run_id, status)
            except Exception as e:
                run_state = self._get_run_state(run_id)
                status = "stopped" if run_state and run_state["status"] in ("stopping", "stopped") else "failed"
                self._update_attempt(run_id, attempt, status=status, error=str(e), ended_at=time.time())
                self._update_batch_item_for_run(run_id, status)
            finally:
                managed_refresh_stop.set()
                if managed_refresh_thread and managed_refresh_thread.is_alive():
                    managed_refresh_thread.join(timeout=2)
                self.runner.persist_worker_profile(wid)
                self.runner.cleanup(sid, wid)
                if wid and quota_guard:
                    quota_guard.consume(account)
                if (self._get_run_state(run_id) or {}).get("status") == "quota_wait":
                    archive = (account_runtime.run_artifact_path(run_id, "status.json").parent / "quota"
                        if account_runtime else WORKSPACES_DIR / run_id / ".quota") / f"attempt-{attempt}"
                    archive.mkdir(parents=True, exist_ok=True)
                    names = (("status.json", "status.json"), ("transcript.log", "transcript.log")) if account_runtime else (
                        (".bench-status.json", ".bench-status.json"), (".bench-transcript.log", ".bench-transcript.log"))
                    for source_name, target_name in names:
                        path = account_runtime.run_artifact_path(run_id, source_name) if account_runtime else WORKSPACES_DIR / run_id / source_name
                        if path.exists():
                            shutil.copy2(path, archive / target_name)
        finally:
            try:
                if quota_guard:
                    quota_guard.release(account, source)
                if warmup_scheduler:
                    warmup_scheduler.handle_run_terminal(run_id, account.get("cc2api_account_id"))
            finally:
                if sem_acquired:
                    sem.release()
                with self._execution_lock:
                    self._executing.discard((run_id, attempt))

    def _wait_batch_quota(self, batch_id: int, account: dict) -> None:
        state = quota_guard.snapshot(account)
        if not state.get("blocked"):
            policy = quota_guard.policy_snapshot(account, "normal", quota_state=state)
            if policy["blocked"]:
                state = {**state, **{
                    "resume_at": policy["resume_at"],
                    "message": policy["message"],
                }}
        with _db_lock:
            conn = get_db()
            try:
                with conn:
                    conn.execute("UPDATE task_batches SET status='quota_wait',next_launch_at=? "
                                 "WHERE id=? AND status='active'", (state["resume_at"], batch_id))
            finally:
                conn.close()

    def _update_attempt(self, run_id: str, attempt: int, **fields) -> bool:
        if not fields:
            return False
        cols = ", ".join(f"{key}=?" for key in fields)
        with _db_lock:
            conn = get_db()
            try:
                with conn:
                    cur = conn.execute(f"UPDATE runs SET {cols} WHERE id=? AND quota_attempt=? "
                                       "AND status IN ('queued','running','stopping') AND deleted_at IS NULL "
                                       "AND (stop_requested_at IS NULL OR ?='stopped')",
                                       [*fields.values(), run_id, attempt, fields.get("status")])
                    return cur.rowcount == 1
            finally:
                conn.close()

    def _mark_quota_wait(self, run_id: str, account: dict, attempt: int) -> None:
        state = quota_guard.snapshot(account) if quota_guard else {}
        if state.get("account_error"):
            if self._update_attempt(run_id, attempt, status="auth_failed", error=state["message"], ended_at=time.time()):
                self._update_batch_item_for_run(run_id, "auth_failed")
            return
        resume_at = state.get("resume_at")
        current = self._get_run_state(run_id) or {}
        if quota_guard and not state.get("blocked"):
            workload = current.get("run_kind")
            if workload in ("normal", "warmup"):
                policy = quota_guard.policy_snapshot(account, workload)
                if policy["enabled"] and (
                    workload == "warmup" or policy["blocked"]
                ):
                    fallback = "等待原养号会话恢复" if workload == "warmup" else "等待任务额度更新"
                    state = {
                        **state,
                        "message": policy["message"] or fallback,
                        "resume_at": policy["resume_at"],
                    }
                resume_at = state["resume_at"]
        if current.get("run_kind") == "capture" and resume_at is not None:
            resume_at = max(resume_at, time.time() + 900)
        if not self._update_attempt(run_id, attempt, status="quota_wait", ended_at=None,
                                    quota_identity=current.get("quota_identity") or _quota_identity(account),
                                    quota_resume_at=resume_at, error=state.get("message") or "额度耗尽，等待可信恢复时间"):
            return
        self._update_batch_item_for_run(run_id, "quota_wait")
        with _db_lock:
            conn = get_db()
            try:
                with conn:
                    conn.execute("UPDATE task_batches SET status='quota_wait',next_launch_at=?,updated_at=julianday('now') "
                                 "WHERE id=(SELECT batch_id FROM runs WHERE id=?) AND status='active'", (resume_at, run_id))
                    conn.execute("UPDATE accounts SET warmup_last_status='quota_wait',warmup_next_run_at=?,warmup_last_error=? "
                                 "WHERE id=? AND warmup_enabled=1 AND warmup_last_run_id=?",
                                 (resume_at, state.get("message"), account["id"], run_id))
            finally:
                conn.close()

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
                "SELECT * FROM runs WHERE id=?",
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
                    if status == "stopped":
                        conn.execute(
                            "UPDATE task_batch_items SET status=?, updated_at=julianday('now') "
                            "WHERE run_id=? AND status!='paused'",
                            (status, run_id),
                        )
                        return
                    conn.execute(
                        "UPDATE task_batch_items SET status=?, updated_at=julianday('now') "
                        "WHERE run_id=?",
                        (status, run_id),
                    )
            finally:
                conn.close()


class WarmupScheduler:
    """按账号随机小时区间创建真实养号 run。"""

    def __init__(self, scheduler: Scheduler) -> None:
        """
        初始化养号调度器。

        :param scheduler: 现有真实 run 调度器
        :return: None
        """
        self.scheduler = scheduler
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        """
        恢复重启前的养号状态并启动后台扫描线程。

        :return: None
        """
        if self._thread and self._thread.is_alive():
            return
        self._recover_stale_runs()
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """
        请求养号后台线程停止。

        :return: None
        """
        self._stop.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=3)

    def trigger_account(self, account_id: int, require_due: bool = False) -> dict:
        """
        原子认领账号并创建一次真实养号 task/run。

        :param account_id: bench accounts.id
        :param require_due: 是否要求 `warmup_next_run_at` 已到期
        :return: 是否启动及新 run id
        """
        if account_runtime:
            connection = get_db()
            try:
                row = _get_available_account(connection, account_id)
                candidate = dict(row) if row else None
                formal = connection.execute("SELECT 1 FROM runs WHERE account_id=? AND run_kind!='warmup' "
                    "AND status IN ('queued','running','stopping','quota_wait') LIMIT 1", (account_id,)).fetchone()
            finally:
                connection.close()
            with account_runtime.lock:
                busy = bool(formal) or any(job["row"]["account_id"] == account_id for job in account_runtime.jobs.values())
            if candidate and candidate.get("cc2api_account_id") is not None and not busy:
                try:
                    snapshot = cc2api_client._request("GET", f"/admin/runtime/accounts/{candidate['cc2api_account_id']}/lease")
                    busy = bool(snapshot["lease"])
                except Exception:
                    busy = True
            if busy:
                connection = get_db()
                try:
                    with connection:
                        connection.execute("UPDATE accounts SET warmup_next_run_at=?,warmup_last_status='scheduled' "
                            "WHERE id=? AND warmup_enabled=1", (time.time() + 60, account_id))
                finally:
                    connection.close()
                return {"started": False, "run_id": None}
        if quota_guard:
            conn = get_db()
            try:
                row = _get_available_account(conn, account_id)
                candidate = dict(row) if row else None
                active = conn.execute("SELECT 1 FROM runs WHERE account_id=? AND run_kind='warmup' "
                                      "AND status IN ('queued','running','stopping','quota_wait') LIMIT 1", (account_id,)).fetchone()
            finally:
                conn.close()
            if active:
                return {"started": False, "run_id": None}
            if candidate and candidate.get("warmup_enabled") and (account_runtime or candidate.get("cc2api_account_id") is not None):
                quota_guard.consume(candidate)
                state = quota_guard.snapshot(candidate)
                warmup_state = quota_guard.warmup_snapshot(candidate)
                if not state["blocked"] and warmup_state["blocked"]:
                    state = {**state, "blocked": True, "resume_at": warmup_state["resume_at"],
                             "message": warmup_state["message"]}
                if state["blocked"] or state.get("recovery_source"):
                    with _db_lock:
                        conn = get_db()
                        try:
                            with conn:
                                conn.execute("UPDATE accounts SET warmup_last_status='quota_wait',warmup_next_run_at=?,warmup_last_error=? "
                                             "WHERE id=? AND warmup_enabled=1", (state["resume_at"], state["message"], account_id))
                        finally:
                            conn.close()
                    return {"started": False, "run_id": None}
        account = self._claim_account(account_id, require_due)
        if not account:
            return {"started": False, "run_id": None}
        try:
            if account.get("cc2api_account_id") is not None:
                _sync_bound_account_credentials(account, 2400)
        except Exception as exc:
            self._record_sync_failure(account, exc)
            return {"started": False, "run_id": None}

        topic = self._select_topic(account_id)
        if not topic:
            self._pause_account(
                account,
                "题库没有可用题目，养号已暂停",
            )
            return {"started": False, "run_id": None}

        conn = get_db()
        try:
            recent_fingerprints = _load_recent_topic_prompt_fingerprints(conn)
        finally:
            conn.close()
        prompt = build_topic_prompt(topic, "natural", recent_fingerprints)
        created = self._create_task_and_run(account, topic, prompt)
        if not created:
            return {"started": False, "run_id": None}
        run_id, task_id, claude_code_version, claude_effort_level = created
        task = {
            "id": task_id,
            "prompt": prompt,
            "timeout_sec": 1800,
            "topic_id": topic["id"],
            "claude_code_version": claude_code_version,
            "claude_effort_level": claude_effort_level,
        }
        self.scheduler.submit(run_id, account, task)
        return {"started": True, "run_id": run_id, "task_id": task_id}

    def handle_run_started(self, run_id: str) -> None:
        """
        把已进入真实执行链路的养号 run 同步到账号最近状态。

        :param run_id: runs.id
        :return: None
        """
        with _db_lock:
            conn = get_db()
            try:
                with conn:
                    run_row = conn.execute(
                        "SELECT account_id, run_kind, status FROM runs WHERE id=?",
                        (run_id,),
                    ).fetchone()
                    if (
                        not run_row
                        or run_row["run_kind"] != "warmup"
                        or run_row["status"] != "running"
                    ):
                        return
                    conn.execute(
                        "UPDATE accounts SET warmup_last_status='running' "
                        "WHERE id=? AND warmup_enabled=1 AND warmup_last_run_id=?",
                        (run_row["account_id"], run_id),
                    )
            finally:
                conn.close()

    def handle_run_sync_failure(
        self,
        run_id: str,
        account: dict,
        exc: Exception,
    ) -> None:
        """
        把养号 run 启动前的凭据同步失败写回账号调度状态。

        :param run_id: 同步失败的 runs.id
        :param account: worker 启动前锁内重读的 accounts 行
        :param exc: cc2api 同步异常
        :return: None
        """
        conn = get_db()
        try:
            run_row = conn.execute(
                "SELECT account_id, run_kind FROM runs WHERE id=?",
                (run_id,),
            ).fetchone()
        finally:
            conn.close()
        if (
            not run_row
            or run_row["run_kind"] != "warmup"
            or int(run_row["account_id"]) != int(account["id"])
        ):
            return
        self._record_sync_failure(account, exc)

    def handle_run_terminal(
        self,
        run_id: str,
        expected_cc2api_account_id: Optional[int] = None,
    ) -> None:
        """
        在养号 run 终态后更新失败计数并安排下一次随机触发。

        :param run_id: runs.id
        :param expected_cc2api_account_id: 本次 run 启动时绑定的 cc2api 账号 ID
        :return: None
        """
        conn = get_db()
        try:
            run_row = conn.execute(
                "SELECT id, account_id, run_kind, status, error FROM runs WHERE id=?",
                (run_id,),
            ).fetchone()
            if (
                not run_row
                or run_row["run_kind"] != "warmup"
                or run_row["status"] not in _TERMINAL_RUN_STATUSES
            ):
                return
            run = dict(run_row)
        finally:
            conn.close()

        with _db_lock:
            conn = get_db()
            try:
                with conn:
                    account_row = conn.execute(
                        "SELECT * FROM accounts WHERE id=?",
                        (run["account_id"],),
                    ).fetchone()
                    if not account_row:
                        return
                    account = dict(account_row)
                    if (
                        (not account_runtime and account.get("cc2api_account_id") is None)
                        or account.get("warmup_last_run_id") != run_id
                    ):
                        return
                    if (
                        expected_cc2api_account_id is not None
                        and account["cc2api_account_id"] != expected_cc2api_account_id
                    ):
                        # run 进入终态后可能立即发生改绑；旧 run 不能把认证结果写到新绑定上。
                        return
                    current_last_status = str(account.get("warmup_last_status") or "")
                    currently_enabled = int(account.get("warmup_enabled") or 0) == 1
                    if current_last_status == run["status"] and (
                        account.get("warmup_next_run_at") is not None
                        or not currently_enabled
                    ):
                        return
                    if not currently_enabled and current_last_status in ("off", "paused"):
                        return
                    if (
                        current_last_status == "sync_failed"
                        and account.get("warmup_next_run_at") is not None
                    ):
                        # 排队后同步失败已经按临时故障安排短重试，不能再被普通 failed 终态覆盖。
                        return

                    if (run.get("error") or "").startswith("养号顺延："):
                        conn.execute("UPDATE accounts SET warmup_last_status='scheduled',warmup_next_run_at=?,warmup_last_error=NULL WHERE id=? AND warmup_enabled=1",
                            (time.time() + 60, account["id"]))
                        return

                    auth_failures = int(account.get("warmup_auth_failures") or 0)
                    enabled = currently_enabled
                    error = _redact_cc2api_error(run.get("error")) if run.get("error") else None
                    permanent_auth_error = bool(
                        run["status"] == "auth_failed"
                        and error
                        and _cc2api_error_detail_is_permanent(error)
                    )
                    if permanent_auth_error:
                        auth_failures += 1
                        enabled = False
                        error = f"cc2api 凭据错误，养号已自动暂停：{error}"
                    elif run["status"] == "auth_failed":
                        auth_failures += 1
                        if auth_failures >= 3:
                            enabled = False
                            error = "连续 3 次养号认证失败，已自动暂停"
                    else:
                        auth_failures = 0
                    next_run_at = self._next_run_at(account) if enabled else None
                    last_status = run["status"] if enabled else "paused"
                    conn.execute(
                        "UPDATE accounts SET warmup_enabled=?, warmup_next_run_at=?, "
                        "warmup_last_status=?, warmup_last_error=?, warmup_auth_failures=? "
                        "WHERE id=? AND cc2api_account_id IS ?",
                        (
                            int(enabled),
                            next_run_at,
                            last_status,
                            error,
                            auth_failures,
                            account["id"],
                            account["cc2api_account_id"],
                        ),
                    )
            finally:
                conn.close()

    def _loop(self) -> None:
        while not self._stop.is_set():
            self._tick()
            self._stop.wait(max(1.0, WARMUP_SCHEDULER_TICK_SEC))

    def _tick(self) -> None:
        now = time.time()
        conn = get_db()
        try:
            rows = conn.execute(
                "SELECT id FROM accounts WHERE enabled=1 AND deleted_at IS NULL "
                "AND warmup_enabled=1 "
                "AND warmup_next_run_at IS NOT NULL AND warmup_next_run_at<=? ORDER BY id",
                (now,),
            ).fetchall()
            account_ids = [int(row["id"]) for row in rows]
        finally:
            conn.close()
        for account_id in account_ids:
            if self._stop.is_set():
                return
            try:
                self.trigger_account(account_id, require_due=True)
            except Exception:
                # 单账号异常不能中断其他账号扫描；具体错误在账号状态中收口。
                continue

    def _claim_account(self, account_id: int, require_due: bool) -> Optional[dict]:
        now = time.time()
        with _db_lock:
            conn = get_db()
            try:
                with conn:
                    row = conn.execute(
                        "SELECT * FROM accounts WHERE id=? AND enabled=1 AND deleted_at IS NULL "
                        "AND warmup_enabled=1",
                        (account_id,),
                    ).fetchone()
                    if not row:
                        return None
                    account = dict(row)
                    next_run_at = account.get("warmup_next_run_at")
                    if require_due and (
                        next_run_at is None or float(next_run_at) > now
                    ):
                        return None
                    active = conn.execute(
                        "SELECT id, status FROM runs WHERE account_id=? AND run_kind='warmup' "
                        "AND status IN ('queued','running','stopping','quota_wait') "
                        "ORDER BY created_at DESC LIMIT 1",
                        (account_id,),
                    ).fetchone()
                    if active:
                        conn.execute(
                            "UPDATE accounts SET warmup_next_run_at=NULL, warmup_last_run_id=?, "
                            "warmup_last_status=? WHERE id=?",
                            (active["id"], active["status"], account_id),
                        )
                        return None
                    conn.execute(
                        "UPDATE accounts SET warmup_next_run_at=NULL, warmup_last_attempt_at=?, "
                        "warmup_last_status='preparing', warmup_last_error=NULL WHERE id=?",
                        (now, account_id),
                    )
                    account["warmup_next_run_at"] = None
                    account["warmup_last_attempt_at"] = now
                    return account
            finally:
                conn.close()

    def _select_topic(self, account_id: int) -> Optional[dict]:
        conn = get_db()
        try:
            topics = [
                dict(row)
                for row in conn.execute(
                    "SELECT * FROM topics WHERE enabled=1 AND deleted_at IS NULL ORDER BY id"
                ).fetchall()
            ]
            recent_rows = conn.execute(
                "SELECT topic_id FROM runs WHERE account_id=? AND run_kind='warmup' "
                "AND topic_id IS NOT NULL ORDER BY created_at DESC LIMIT 20",
                (account_id,),
            ).fetchall()
        finally:
            conn.close()
        if not topics:
            return None
        recent_ids = [int(row["topic_id"]) for row in recent_rows]
        recent_set = set(recent_ids)
        candidates = [topic for topic in topics if int(topic["id"]) not in recent_set]
        if not candidates and recent_ids:
            # 题库不足时缩小窗口，但只要存在第二题就仍避免连续重复。
            candidates = [topic for topic in topics if int(topic["id"]) != recent_ids[0]]
        return random.choice(candidates or topics)

    def _create_task_and_run(
        self,
        account: dict,
        topic: dict,
        prompt: str,
    ) -> Optional[tuple[str, int, str, str]]:
        """
        为养号创建 task 和 run，并保存已生成的 prompt。

        :param account: 已认领的账号行
        :param topic: 本次养号选择的 topic 行
        :param prompt: 已生成且将实际下发给 worker 的 prompt
        :return: `(run_id, task_id, claude_code_version, claude_effort_level)`；不可创建时返回 None
        """
        run_id = uuid.uuid4().hex[:12]
        claude_code_version = effective_claude_code_version()
        claude_effort_level = effective_runtime_effort()
        with _db_lock:
            conn = get_db()
            try:
                with conn:
                    current = conn.execute(
                        "SELECT * FROM accounts WHERE id=? AND enabled=1 AND deleted_at IS NULL "
                        "AND warmup_enabled=1 AND cc2api_account_id IS ?",
                        (account["id"], account["cc2api_account_id"]),
                    ).fetchone()
                    if not current:
                        return None
                    active = conn.execute(
                        "SELECT id FROM runs WHERE account_id=? AND run_kind='warmup' "
                        "AND status IN ('queued','running','stopping','quota_wait') LIMIT 1",
                        (account["id"],),
                    ).fetchone()
                    if active:
                        return None
                    cur = conn.execute(
                        "INSERT INTO tasks(topic_no, title, prompt, account_id, topic_id, "
                        "timeout_sec, repeat_n) VALUES(?,?,?,?,?,?,?)",
                        (
                            topic["no"],
                            f"[warmup] {topic['title']}",
                            prompt,
                            account["id"],
                            topic["id"],
                            1800,
                            1,
                        ),
                    )
                    task_id = int(cur.lastrowid)
                    conn.execute(
                        "INSERT INTO runs(id, task_id, account_id, topic_id, status, run_kind, "
                        "claude_code_version, claude_effort_level) VALUES(?,?,?,?,?,?,?,?)",
                        (
                            run_id,
                            task_id,
                            account["id"],
                            topic["id"],
                            "queued",
                            "warmup",
                            claude_code_version,
                            claude_effort_level,
                        ),
                    )
                    conn.execute(
                        "UPDATE accounts SET warmup_last_run_id=?, warmup_last_status='queued', "
                        "warmup_last_error=NULL WHERE id=?",
                        (run_id, account["id"]),
                    )
                    return run_id, task_id, claude_code_version, claude_effort_level
            finally:
                conn.close()

    def _record_sync_failure(self, account: dict, exc: Exception) -> None:
        error = _redact_cc2api_error(exc)
        permanent = _cc2api_error_is_permanent(exc)
        with _db_lock:
            conn = get_db()
            try:
                with conn:
                    conn.execute(
                        "UPDATE accounts SET warmup_enabled=?, warmup_next_run_at=?, "
                        "warmup_last_status=?, warmup_last_error=? "
                        "WHERE id=? AND cc2api_account_id IS ?",
                        (
                            0 if permanent else 1,
                            None if permanent else time.time() + WARMUP_SYNC_RETRY_SEC,
                            "paused" if permanent else "sync_failed",
                            error,
                            account["id"],
                            account["cc2api_account_id"],
                        ),
                    )
            finally:
                conn.close()

    def _pause_account(self, account: dict, error: str) -> None:
        with _db_lock:
            conn = get_db()
            try:
                with conn:
                    conn.execute(
                        "UPDATE accounts SET warmup_enabled=0, warmup_next_run_at=NULL, "
                        "warmup_last_status='paused', warmup_last_error=? "
                        "WHERE id=? AND cc2api_account_id IS ?",
                        (
                            _redact_cc2api_error(error),
                            account["id"],
                            account["cc2api_account_id"],
                        ),
                    )
            finally:
                conn.close()

    def _next_run_at(self, account: dict) -> float:
        low = max(1, int(account.get("warmup_interval_min_hours") or 3))
        high = max(low, int(account.get("warmup_interval_max_hours") or low))
        return time.time() + random.uniform(low * 3600, high * 3600)

    def _recover_stale_runs(self) -> None:
        stale_runs: list[tuple[str, Optional[int]]] = []
        with _db_lock:
            conn = get_db()
            try:
                with conn:
                    rows = conn.execute(
                        "SELECT r.id, a.cc2api_account_id FROM runs r "
                        "LEFT JOIN accounts a ON a.id=r.account_id "
                        "WHERE r.run_kind='warmup' "
                        "AND r.status IN ('queued','running','stopping')"
                    ).fetchall()
                    stale_runs = [
                        (str(row["id"]), row["cc2api_account_id"])
                        for row in rows
                    ]
                    run_ids = [run_id for run_id, _binding_id in stale_runs]
                    if run_ids:
                        placeholders = ",".join("?" for _ in run_ids)
                        conn.execute(
                            f"UPDATE runs SET status='failed', ended_at=?, "
                            f"error='orchestrator 重启，旧养号 run 已收口' "
                            f"WHERE id IN ({placeholders})",
                            (time.time(), *run_ids),
                        )
            finally:
                conn.close()
        for run_id, binding_id in stale_runs:
            self.handle_run_terminal(run_id, binding_id)


# ============== FastAPI ==============
runner: Optional[Runner] = None
scheduler: Optional[Scheduler] = None
login_manager: Optional[LoginManager] = None
continue_manager: Optional[ContinueManager] = None
oauth_refresh_scheduler: Optional[OAuthRefreshScheduler] = None
warmup_scheduler: Optional[WarmupScheduler] = None
quota_guard: Optional[QuotaGuard] = None
account_runtime: Optional[AccountRuntime] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global runner, scheduler, login_manager, continue_manager, oauth_refresh_scheduler, warmup_scheduler, quota_guard, account_runtime
    init_db()
    PROFILES_DIR.mkdir(parents=True, exist_ok=True)
    FLOWS_DIR.mkdir(parents=True, exist_ok=True)
    WORKSPACES_DIR.mkdir(parents=True, exist_ok=True)
    CA_DIR.mkdir(parents=True, exist_ok=True)
    runner = Runner()
    if V3_ENABLED:
        account_runtime = AccountRuntime(runner.client, BENCH_DATA, HOST_BENCH_DATA, get_db, derive_v3_fingerprint, cc2api_client, _quota_identity)
        account_runtime.reconcile()
        account_runtime.start()
    scheduler = Scheduler(runner)
    login_manager = LoginManager(runner.client)
    continue_manager = ContinueManager(runner)
    oauth_refresh_scheduler = OAuthRefreshScheduler(runner)
    warmup_scheduler = WarmupScheduler(scheduler)
    quota_guard = QuotaGuard(runner)
    quota_guard.recover()
    # 清掉上次进程残留的 login 容器，避免重启后僵尸容器堆积
    login_manager.cleanup_stale()
    continue_manager.cleanup_stale()
    oauth_refresh_scheduler.cleanup_stale()
    oauth_refresh_scheduler.start()
    warmup_scheduler.start()
    quota_guard.start()
    if V3_ENABLED:
        scheduler.recover_active_batches()
    try:
        yield
    finally:
        quota_guard.stop()
        warmup_scheduler.stop()
        oauth_refresh_scheduler.stop()
        if account_runtime:
            account_runtime.stop()


app = FastAPI(title="vibecoding-bench", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ===== Cookie-Session 鉴权工具 + 中间件 =====
def _session_signature(payload: str) -> str:
    """v3 会话同时绑定当前管理密码，密码轮换后旧会话立即失效。"""
    key = _SESSION_SECRET + ("\0" + WEBUI_PASS if V3_ENABLED else "")
    return hmac.new(key.encode(), payload.encode(), hashlib.sha256).hexdigest()


def _v3_session_store():
    """打开独立会话登记，仅保存 token 摘要和过期时间。"""
    connection = get_db()
    with connection:
        connection.execute("CREATE TABLE IF NOT EXISTS v3_management_sessions (token_hash TEXT PRIMARY KEY, expires_at INTEGER NOT NULL)")
    return connection


def _make_session_token(user: str) -> str:
    """
    签发管理会话；v3 增加随机代次和服务端撤销记录。

    :param user: 当前管理用户名
    :return: 不含密码的签名 token
    """
    exp = int(time.time()) + _SESSION_TTL
    payload = f"{user}|{exp}"
    if V3_ENABLED:
        payload += "|" + secrets.token_hex(16)
    sig = _session_signature(payload)
    raw = f"{payload}|{sig}".encode()
    token = base64.urlsafe_b64encode(raw).decode().rstrip("=")
    if V3_ENABLED:
        connection = _v3_session_store()
        try:
            with connection:
                connection.execute("DELETE FROM v3_management_sessions WHERE expires_at<?", (int(time.time()),))
                connection.execute("INSERT INTO v3_management_sessions VALUES(?,?)", (hashlib.sha256(token.encode()).hexdigest(), exp))
        finally:
            connection.close()
    return token


def _verify_session_token(token: str) -> Optional[str]:
    """合法返回用户名,非法/过期返回 None"""
    if not token:
        return None
    try:
        # 补回 base64 padding
        padded = token + "=" * (-len(token) % 4)
        raw = base64.urlsafe_b64decode(padded).decode("utf-8")
        parts = raw.split("|")
        if len(parts) != (4 if V3_ENABLED else 3):
            return None
        user, exp_str, sig = parts[0], parts[1], parts[-1]
        if int(exp_str) < int(time.time()):
            return None
        expected = _session_signature("|".join(parts[:-1]))
        if not secrets.compare_digest(sig, expected):
            return None
        # 用户名必须仍有效；v3 签名还绑定当前密码，轮换密码即撤销旧签名。
        if not secrets.compare_digest(user, WEBUI_USER):
            return None
        if V3_ENABLED:
            connection = get_db()
            try:
                record = connection.execute("SELECT expires_at FROM v3_management_sessions WHERE token_hash=?",
                    (hashlib.sha256(token.encode()).hexdigest(),)).fetchone()
                if not record or record["expires_at"] != int(exp_str):
                    return None
            finally:
                connection.close()
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
    if V3_ENABLED:
        expected = os.environ.get("V3_INTERNAL_TOKEN", "")
        actual = request.headers.get("authorization", "").removeprefix("Bearer ")
        if len(expected) < 32 or not secrets.compare_digest(actual, expected):
            return JSONResponse(status_code=401, content={"detail": "内部服务鉴权失败"})
        if request.url.path == "/api/auth/login":
            return JSONResponse(status_code=403, content={"detail": "请从统一后台登录"})
        return await call_next(request)
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


class RuntimeModelIn(BaseModel):
    """
    WebUI 保存普通 / 批量 run 默认模型的请求体。

    :param default_model: 模型名；空值表示清除页面覆盖并回退到 `.env`
    """

    default_model: Optional[str] = None


class RuntimeEffortIn(BaseModel):
    """
    WebUI 保存普通 / 批量 run 思考预算的请求体。

    :param effort_level: 思考预算枚举；空值表示清除页面覆盖并回退到 `.env`
    """

    effort_level: Optional[str] = None


class ClaudeCodeVersionIn(BaseModel):
    """
    WebUI 保存 Claude Code CLI 版本的请求体。

    :param claude_code_version: 版本号；空值表示清除页面覆盖并回退到 `.env`
    """

    claude_code_version: Optional[str] = None


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
def auth_logout(request: Request, response: Response):
    """撤销 v3 会话并清除 Cookie；旧版继续只清除 Cookie。

    :param request: 含待撤销会话的请求
    :param response: 写入清除 Cookie 的响应
    :return: 幂等退出结果
    """
    if V3_ENABLED:
        connection = _v3_session_store()
        try:
            with connection:
                connection.execute("DELETE FROM v3_management_sessions WHERE token_hash=?",
                    (hashlib.sha256(request.cookies.get(_SESSION_COOKIE, "").encode()).hexdigest(),))
        finally:
            connection.close()
    response.delete_cookie(_SESSION_COOKIE, path="/runtime" if V3_ENABLED else "/")
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


# ---------- settings ----------
def runtime_model_response() -> dict:
    """
    组装普通 / 批量 run 默认模型设置响应。

    :return: 页面覆盖值、环境兜底值和当前生效值
    """
    try:
        configured_model = get_runtime_model_setting()
    except ValueError as e:
        raise HTTPException(500, str(e))
    return {
        "configured_model": configured_model,
        "env_default_model": CLAUDE_DEFAULT_MODEL,
        "effective_model": configured_model or CLAUDE_DEFAULT_MODEL,
    }


def runtime_effort_response() -> dict:
    """
    组装普通 / 批量 run 思考预算设置响应。

    :return: 页面覆盖值、环境兜底值、当前生效值和允许枚举
    """
    try:
        configured_effort = get_runtime_effort_setting()
    except ValueError as e:
        raise HTTPException(500, str(e))
    return {
        "configured_effort": configured_effort,
        "env_default_effort": CLAUDE_CODE_EFFORT_LEVEL,
        "effective_effort": configured_effort or CLAUDE_CODE_EFFORT_LEVEL,
        "allowed_efforts": list(_CLAUDE_EFFORT_LEVELS),
    }


def claude_code_version_response() -> dict:
    """
    组装 Claude Code CLI 版本设置响应。

    :return: 页面覆盖值、环境兜底值和当前生效值
    """
    try:
        configured_version = get_runtime_claude_code_version_setting()
    except ValueError as e:
        raise HTTPException(500, str(e))
    return {
        "configured_version": configured_version,
        "env_default_version": CLAUDE_CODE_VERSION,
        "effective_version": configured_version or CLAUDE_CODE_VERSION,
    }


@app.get("/api/settings/runtime-model")
def get_runtime_model():
    """
    返回普通 / 批量 run 当前默认模型设置。

    :return: 页面覆盖值、环境兜底值和当前生效值
    """
    return runtime_model_response()


@app.put("/api/settings/runtime-model")
def update_runtime_model(body: RuntimeModelIn):
    """
    保存普通 / 批量 run 默认模型覆盖值；空值表示回退到 `.env`。

    :param body: 默认模型设置请求体
    :return: 保存后的当前模型设置
    """
    save_runtime_model_setting(body.default_model)
    return runtime_model_response()


@app.get("/api/settings/runtime-effort")
def get_runtime_effort():
    """
    返回普通 / 批量 run 当前思考预算设置。

    :return: 页面覆盖值、环境兜底值、当前生效值和允许枚举
    """
    return runtime_effort_response()


@app.put("/api/settings/runtime-effort")
def update_runtime_effort(body: RuntimeEffortIn):
    """
    保存普通 / 批量 run 思考预算覆盖值；空值表示回退到 `.env`。

    :param body: 思考预算设置请求体
    :return: 保存后的当前思考预算设置
    """
    save_runtime_effort_setting(body.effort_level)
    return runtime_effort_response()


@app.get("/api/settings/claude-code-version")
def get_claude_code_version():
    """
    返回新 worker 当前使用的 Claude Code CLI 版本设置。

    :return: 页面覆盖值、环境兜底值和当前生效值
    """
    return claude_code_version_response()


@app.put("/api/settings/claude-code-version")
def update_claude_code_version(body: ClaudeCodeVersionIn):
    """
    保存 Claude Code CLI 版本覆盖值；空值表示回退到 `.env`。

    :param body: Claude Code 版本设置请求体
    :return: 保存后的当前版本设置
    """
    save_runtime_claude_code_version_setting(body.claude_code_version)
    return claude_code_version_response()


# ---------- accounts ----------
class AccountIn(BaseModel):
    """账号创建请求体，包含兼容旧字段名的上游代理配置。"""

    name: str
    timezone: Optional[str] = None
    upstream_proxy_scheme: Optional[str] = None
    upstream_socks5_host: Optional[str] = None
    upstream_socks5_port: Optional[int] = None
    upstream_socks5_user: Optional[str] = None
    upstream_socks5_pass: Optional[str] = None
    enabled: bool = True


class WarmupConfigIn(BaseModel):
    """账号 cc2api 绑定、养号间隔与普通任务/养号共用额度阈值。

    :param cc2api_account_id: 可选网关账号；省略或 null 表示保留当前绑定
    :param enabled: 是否启用养号
    :param interval_min_hours: 最小随机间隔小时数
    :param interval_max_hours: 最大随机间隔小时数
    :param warmup_quota_5h_limit_percent: 兼容字段名；5h 已用整数阈值，null 关闭，省略保留
    :param warmup_quota_7d_limit_percent: 兼容字段名；7d 已用整数阈值，null 关闭，省略保留
    """

    cc2api_account_id: Optional[StrictInt] = None
    enabled: bool = False
    interval_min_hours: int = 3
    interval_max_hours: int = 5
    warmup_quota_5h_limit_percent: Optional[StrictInt] = None
    warmup_quota_7d_limit_percent: Optional[StrictInt] = None


def _oauth_owner_transition_blocker(account: dict, login_sid: Optional[str] = None) -> Optional[str]:
    """
    查找会让 AT/RT 所有权切换不安全的活跃工作。

    :param account: accounts 表行
    :param login_sid: 提交时允许的当前登录会话；其他登录仍阻塞
    :return: 阻塞原因；账号空闲时返回 None
    """
    conn = get_db()
    try:
        active_run = conn.execute(
            "SELECT id, status FROM runs WHERE account_id=? "
            "AND status IN ('queued','running','stopping','quota_wait') ORDER BY created_at LIMIT 1",
            (account["id"],),
        ).fetchone()
    finally:
        conn.close()
    if active_run:
        return f"run {active_run['id']} 当前为 {active_run['status']}"
    if continue_manager and continue_manager.has_active_account(int(account["id"])):
        return "账号存在活跃的继续对话会话"
    if login_manager and login_manager.has_active_name(str(account["name"])):
        own_login = login_manager.get(login_sid) if login_sid else None
        if not own_login or own_login.name != account["name"]:
            return "账号存在活跃的登录或重授权会话"
    return None


def _require_oauth_owner_transition_idle(account: dict) -> None:
    """
    要求账号在 cc2api 绑定所有权切换前没有活跃 worker。

    :param account: accounts 表行
    :return: None
    """
    blocker = _oauth_owner_transition_blocker(account)
    if blocker:
        raise HTTPException(409, f"账号凭据所有权暂不能切换：{blocker}，请先停止并收口")


@contextmanager
def _runtime_owner_transition(account: dict, target_id: Optional[int], needed: bool = True):
    """在所有权事务期间协调固定环境和两端 API 门禁。

    :param account: 修改前账号
    :param target_id: 修改后绑定，None 表示解绑或删除
    :param needed: 是否实际修改所有权
    :return: 持有相应门禁的上下文
    """
    if not account_runtime or not needed:
        yield
        return
    try:
        with account_runtime.owner_transition(account, target_id):
            yield
    except (ValueError, ConnectionError) as exc:
        raise HTTPException(409, _redact_cc2api_error(exc))


def _require_cc2api_binding_available(
    bench_account_id: int,
    cc2api_account_id: int,
) -> None:
    """
    要求 cc2api 账号尚未绑定到其他可见 bench 账号。

    :param bench_account_id: 当前 bench accounts.id
    :param cc2api_account_id: 待绑定的 cc2api 账号 ID
    :return: None
    """
    conn = get_db()
    try:
        bound = conn.execute(
            "SELECT id FROM accounts WHERE cc2api_account_id=? AND id!=? "
            "AND deleted_at IS NULL LIMIT 1",
            (cc2api_account_id, bench_account_id),
        ).fetchone()
    finally:
        conn.close()
    if bound:
        raise HTTPException(409, "该 cc2api 账号已绑定其他 bench 账号")


@app.post("/api/accounts")
def create_account(body: AccountIn):
    """创建已有 profile 对应的账号记录。"""
    pp = PROFILES_DIR / body.name
    if not pp.exists() or not any(pp.iterdir()):
        raise HTTPException(
            400,
            f"profile empty or missing: {pp}. "
            f"Run scripts/init-account.sh {body.name} first.",
        )
    try:
        proxy_scheme = _normalize_upstream_proxy_scheme(body.upstream_proxy_scheme)
        timezone = _normalize_account_timezone(body.timezone)
    except ValueError as e:
        raise HTTPException(400, str(e))
    with _db_lock:
        conn = get_db()
        try:
            with conn:
                soft_deleted_row = conn.execute(
                    "SELECT id FROM accounts WHERE name=? AND deleted_at IS NOT NULL",
                    (body.name,),
                ).fetchone()
                if soft_deleted_row:
                    account_id = _restore_deleted_account(
                        conn,
                        int(soft_deleted_row["id"]),
                        body.name,
                        proxy_scheme,
                        body.upstream_socks5_host,
                        body.upstream_socks5_port,
                        body.upstream_socks5_user,
                        body.upstream_socks5_pass,
                        timezone,
                        int(body.enabled),
                    )
                    return {"id": account_id, "restored": True}
                restored_account_id = _infer_deleted_account_id(conn, body.name)
                columns = (
                    "id, name, profile_path, upstream_proxy_scheme, "
                    "upstream_socks5_host, upstream_socks5_port, "
                    "upstream_socks5_user, upstream_socks5_pass, timezone, enabled"
                ) if restored_account_id is not None else (
                    "name, profile_path, upstream_proxy_scheme, "
                    "upstream_socks5_host, upstream_socks5_port, "
                    "upstream_socks5_user, upstream_socks5_pass, timezone, enabled"
                )
                values_sql = "(?,?,?,?,?,?,?,?,?,?)" if restored_account_id is not None else "(?,?,?,?,?,?,?,?,?)"
                base_values = (
                    body.name,
                    f"profiles/{body.name}",
                    proxy_scheme,
                    body.upstream_socks5_host,
                    body.upstream_socks5_port,
                    body.upstream_socks5_user,
                    body.upstream_socks5_pass,
                    timezone,
                    int(body.enabled),
                )
                values = ((restored_account_id,) + base_values) if restored_account_id is not None else base_values
                cur = conn.execute(
                    f"INSERT INTO accounts({columns}) VALUES{values_sql}",
                    values,
                )
                return {"id": restored_account_id if restored_account_id is not None else cur.lastrowid}
        except sqlite3.IntegrityError as e:
            raise HTTPException(400, f"account exists: {e}")
        finally:
            conn.close()


@app.get("/api/accounts")
def list_accounts():
    """返回账号列表，并补充 OAuth token 状态。"""
    conn = get_db()
    try:
        rows = conn.execute(
            "SELECT * FROM accounts WHERE deleted_at IS NULL ORDER BY id"
        ).fetchall()
        accounts = []
        for row in rows:
            if _login_save_pending(conn, row["name"]):
                continue
            account = dict(row)
            account["upstream_proxy_scheme"] = _normalize_upstream_proxy_scheme(
                account.get("upstream_proxy_scheme")
            )
            timezone = _normalize_account_timezone(account.get("timezone"))
            account["timezone"] = timezone
            account["effective_timezone"] = _effective_account_timezone(
                account,
                timezone,
            )
            account["timezone_mode"] = "manual" if timezone else "auto"
            account.update(_read_account_oauth_status(account["name"]))
            account["passive_quota"] = _public_quota(account)
            policies = quota_guard.policy_snapshots(account) if quota_guard else {}
            quota_policy = policies.get("normal", {})
            account["quota_policy"] = {key: quota_policy.get(key) for key in (
                "enabled", "limits", "hit", "unknown", "blocked", "resume_at", "message", "refresh_retry_at")}
            warmup_state = policies.get("warmup", {})
            account["warmup_quota"] = {key: warmup_state.get(key) for key in (
                "enabled", "limits", "hit", "unknown", "blocked", "sample_used", "resume_at", "message")}
            accounts.append(account)
        return accounts
    finally:
        conn.close()


@app.get("/api/cc2api/accounts")
def list_cc2api_accounts():
    """
    返回可绑定的 active OAuth cc2api 账号脱敏摘要。

    :return: 不含任何凭据的账号摘要列表
    """
    try:
        accounts = cc2api_client.list_accounts()
    except ConnectionError as exc:
        raise HTTPException(502, _redact_cc2api_error(exc))
    except ValueError as exc:
        raise HTTPException(400, _redact_cc2api_error(exc))
    return [
        _cc2api_account_summary(account)
        for account in accounts
        if _cc2api_account_is_active_oauth(account)
    ]


def _v3_cli_identity(account: dict) -> dict:
    """在既有账号 owner 锁内保护 profile 与固定环境的身份导出。

    :param account: 当前 bench 账号
    :return: 已核验的无凭据 CLI 身份载荷
    """
    with _profile_lock(account["name"]):
        return account_runtime.identity_import(account, effective_claude_code_version())


@app.post("/api/accounts/{aid}/cc2api/sync")
def sync_account_to_cc2api(aid: int):
    """
    把单个 bench 账号安全创建或关联到 cc2api。

    :param aid: bench accounts.id
    :return: 绑定结果和脱敏 cc2api 账号摘要
    """
    return _associate_account_to_cc2api(aid, "sync")


class Cc2apiBindingIn(BaseModel):
    """显式关联已有账号的请求体，仅接受目标账号 ID。"""

    model_config = ConfigDict(extra="forbid")
    cc2api_account_id: StrictInt


@app.post("/api/accounts/{aid}/cc2api/create")
def create_account_in_cc2api(aid: int) -> dict:
    """仅创建并关联新 cc2api 账号，不自动改为关联已有账号。

    :param aid: bench 账号 ID。
    :return: 新建账号的脱敏结果。
    """
    return _associate_account_to_cc2api(aid, "create")


@app.post("/api/accounts/{aid}/cc2api/bind")
def bind_account_to_cc2api(aid: int, body: Cc2apiBindingIn) -> dict:
    """仅关联显式选择的已有账号，不创建账号或修改养号设置。

    :param aid: bench 账号 ID。
    :param body: 目标 cc2api 账号 ID。
    :return: 已关联账号的脱敏结果。
    """
    if body.cc2api_account_id <= 0:
        raise HTTPException(400, "请选择有效的 cc2api 账号")
    return _associate_account_to_cc2api(aid, "bind", body.cc2api_account_id)


@app.post("/api/accounts/{aid}/cc2api/process")
def update_account_process(aid: int) -> dict:
    """只更新原关联账号的进程指标，不解析或刷新凭据。

    :param aid: bench 账号 ID。
    :return: 指标更新结果，不包含秘密。
    """
    if not account_runtime:
        raise HTTPException(409, "进程实测仅支持 v3 固定账号环境")
    connection = get_db()
    try:
        account = _get_available_account(connection, aid)
        if not account:
            raise HTTPException(404, "账号不存在或已停用")
        account = dict(account)
    finally:
        connection.close()
    with _oauth_owner_lock(account["name"]):
        connection = get_db()
        try:
            account = dict(_get_available_account(connection, aid) or {})
        finally:
            connection.close()
        if not account:
            raise HTTPException(404, "账号不存在或已停用")
        if account.get("cc2api_account_id") is None:
            raise HTTPException(409, "账号尚未关联 cc2api，无法更新进程指标")
        _require_oauth_owner_transition_idle(account)
        try:
            with _profile_lock(account["name"]):
                payload = account_runtime.process_identity_import(account, effective_claude_code_version())
            result = cc2api_client._request("POST",
                f"/admin/accounts/{int(account['cc2api_account_id'])}/cli-process/import", payload)
        except ConnectionError as exc:
            raise HTTPException(502, _redact_cc2api_error(exc))
        except (ValueError, RuntimeError) as exc:
            raise HTTPException(409, _redact_cc2api_error(exc))
    return {"ok": True, "cc2api_account_id": account["cc2api_account_id"],
        "canonical_process": result["canonical_process"]}


def _associate_account_to_cc2api(aid: int, action: str, target_id: Optional[int] = None) -> dict:
    """复用创建/关联的所有权保护，由入口显式限定动作。

    :param aid: bench 账号 ID。
    :param action: create、bind 或旧接口 sync。
    :param target_id: 显式关联的目标 ID。
    :return: 绑定结果与脱敏账号摘要。
    """
    conn = get_db()
    try:
        row = _get_available_account(conn, aid)
        if not row:
            raise HTTPException(404, "账号不存在或已停用")
        account = dict(row)
    finally:
        conn.close()
    with _oauth_owner_lock(str(account["name"])):
        with _cc2api_binding_lock:
            conn = get_db()
            try:
                current_row = _get_available_account(conn, aid)
                if not current_row:
                    raise HTTPException(404, "账号不存在或已停用")
                account = dict(current_row)
            finally:
                conn.close()
            existing_binding = account.get("cc2api_account_id")
            if existing_binding is not None and action != "sync":
                raise HTTPException(409, "账号已经关联 cc2api，无需再次创建或关联")
            if existing_binding is None:
                _require_oauth_owner_transition_idle(account)
            try:
                profile = _read_bench_profile_identity(account["name"])
            except ValueError as exc:
                raise HTTPException(400, str(exc))
            try:
                cc2api_accounts = cc2api_client.list_accounts()
                if existing_binding is not None:
                    matched = next(
                        (
                            item
                            for item in cc2api_accounts
                            if int(item.get("id") or 0) == int(existing_binding)
                        ),
                        None,
                    )
                    if not matched:
                        raise ValueError("当前绑定的 cc2api 账号不存在")
                    created = False
                else:
                    if action == "bind":
                        matched = next((item for item in cc2api_accounts if int(item.get("id") or 0) == target_id), None)
                        if matched is None:
                            raise ValueError("所选 cc2api 账号不存在，未创建或关联任何账号")
                    else:
                        matched = _find_cc2api_account_for_profile(profile, cc2api_accounts)
                        if action == "create" and matched is not None:
                            raise ValueError("已有匹配的 cc2api 账号，请使用“关联已有账号”")
                    created = matched is None
                    if matched is None:
                        matched = cc2api_client.create_account({
                            **({"cli_identity": _v3_cli_identity(account)} if account_runtime else {}),
                            "name": account["name"],
                            "email": profile["email"],
                            "auth_type": "oauth",
                            "access_token": profile["access_token"],
                            "refresh_token": profile["refresh_token"],
                            "expires_at": profile["expires_at"],
                            "proxy_url": _account_proxy_url(account),
                            "account_uuid": profile.get("account_uuid"),
                            "organization_uuid": profile.get("organization_uuid"),
                            "subscription_type": profile.get("subscription_type"),
                            "allow_fast_mode": False,
                            "billing_mode": "rewrite",
                            "upstream_session_pool_enabled": True,
                            "upstream_session_pool_size": 4,
                            "upstream_session_refresh_policy": "owner_only",
                            "concurrency": 4,
                            "rpm_limit": 50,
                        })
                if not _cc2api_account_is_active_oauth(matched):
                    raise ValueError("匹配到的 cc2api 账号不是 active OAuth 账号")
                _validate_cc2api_identity(profile, matched)
                if account_runtime and existing_binding is None and not created:
                    observed = _v3_cli_identity(account)
                    if matched.get("device_id") != observed["device_id"]:
                        raise ValueError("已有 cc2api 设备身份与 CLI 观测不一致，保留已有身份并阻止绑定")
                cc2api_account_id = int(matched.get("id") or 0)
                if cc2api_account_id <= 0:
                    raise ValueError("cc2api 账号 ID 无效")
                _require_cc2api_binding_available(aid, cc2api_account_id)
                _resolve_and_sync_cc2api_credentials(
                    account["name"],
                    cc2api_account_id,
                    2400,
                )
            except ConnectionError as exc:
                raise HTTPException(502, _redact_cc2api_error(exc))
            except ValueError as exc:
                raise HTTPException(409, _redact_cc2api_error(exc))

            with _runtime_owner_transition(account, cc2api_account_id, existing_binding is None):
                with _db_lock:
                    conn = get_db()
                    try:
                        with conn:
                            current = _get_available_account(conn, aid)
                            if not current:
                                raise HTTPException(404, "账号不存在或已停用")
                            current_binding = current["cc2api_account_id"]
                            if current_binding is not None and int(current_binding) != cc2api_account_id:
                                raise HTTPException(409, "bench 账号已绑定其他 cc2api 账号")
                            if current_binding is None:
                                if action == "sync":
                                    conn.execute(
                                        "UPDATE accounts SET cc2api_account_id=?, warmup_enabled=0, "
                                        "warmup_next_run_at=NULL, warmup_last_status='off', warmup_last_error=NULL "
                                        "WHERE id=?", (cc2api_account_id, aid))
                                else:
                                    conn.execute("UPDATE accounts SET cc2api_account_id=? WHERE id=?", (cc2api_account_id, aid))
                    except sqlite3.IntegrityError:
                        raise HTTPException(409, "该 cc2api 账号已绑定其他 bench 账号")
                    finally:
                        conn.close()
    if account_runtime:
        current_account = dict(account, cc2api_account_id=cc2api_account_id)
        row = account_runtime._row(account["name"], aid)
        account_runtime.sync_credentials(row, current_account)
    return {
        "ok": True,
        "created": created,
        "cc2api_account": _cc2api_account_summary(matched),
    }


@app.put("/api/accounts/{aid}/warmup")
def update_account_warmup(aid: int, body: WarmupConfigIn):
    """
    保存可选 cc2api 绑定、养号随机间隔与普通任务额度阈值。

    :param aid: bench accounts.id
    :param body: 可选 cc2api 账号 ID、开关、小时区间和阈值
    :return: 保存后的调度状态
    """
    low = int(body.interval_min_hours)
    high = int(body.interval_max_hours)
    if low < 1 or high < 1 or low > 720 or high > 720:
        raise HTTPException(400, "养号间隔必须为 1-720 小时")
    if high < low:
        raise HTTPException(400, "最大养号间隔不能小于最小间隔")
    threshold_fields = ("warmup_quota_5h_limit_percent", "warmup_quota_7d_limit_percent")
    for field in threshold_fields:
        value = getattr(body, field)
        if value is not None and not 1 <= value <= 100:
            raise HTTPException(400, "任务与养号额度阈值必须为 1-100 的已用百分比整数")
    conn = get_db()
    try:
        row = _get_available_account(conn, aid)
        if not row:
            raise HTTPException(404, "账号不存在或已停用")
        account = dict(row)
    finally:
        conn.close()
    with _oauth_owner_lock(str(account["name"])):
        with _cc2api_binding_lock:
            conn = get_db()
            try:
                current_row = _get_available_account(conn, aid)
                if not current_row:
                    raise HTTPException(404, "账号不存在或已停用")
                account = dict(current_row)
            finally:
                conn.close()
            current_binding = account.get("cc2api_account_id")
            target_binding = int(body.cc2api_account_id) if body.cc2api_account_id is not None else current_binding
            binding_changes = body.cc2api_account_id is not None and current_binding != target_binding
            if binding_changes:
                _require_oauth_owner_transition_idle(account)

            enabled = bool(body.enabled)
            if enabled and target_binding is None and not account_runtime:
                raise HTTPException(409, "启用定时养号前请先同步并绑定 cc2api OAuth 账号")
            if enabled and target_binding is None:
                try:
                    _read_bench_profile_identity(account["name"])
                except ValueError:
                    raise HTTPException(409, "本地 OAuth 凭据不完整，请先完成该账号 CLI 登录") from None
            if binding_changes or (enabled and target_binding is not None):
                try:
                    profile = _read_bench_profile_identity(account["name"])
                    cc2api_accounts = cc2api_client.list_accounts()
                    selected = next(
                        (
                            item
                            for item in cc2api_accounts
                            if int(item.get("id") or 0) == int(target_binding)
                        ),
                        None,
                    )
                    if not selected or not _cc2api_account_is_active_oauth(selected):
                        raise ValueError("选择的 cc2api 账号不可用")
                    _validate_cc2api_identity(profile, selected)
                    if account_runtime and binding_changes:
                        observed = _v3_cli_identity(account)
                        if selected.get("device_id") != observed["device_id"]:
                            raise ValueError("已有 cc2api 设备身份与 CLI 观测不一致，保留已有身份并阻止绑定")
                    _require_cc2api_binding_available(aid, int(target_binding))
                    _resolve_and_sync_cc2api_credentials(
                        account["name"],
                        int(target_binding),
                        2400,
                    )
                except ConnectionError as exc:
                    raise HTTPException(502, _redact_cc2api_error(exc))
                except ValueError as exc:
                    raise HTTPException(409, _redact_cc2api_error(exc))

            next_run_at = time.time() + random.uniform(low * 3600, high * 3600) if enabled else None
            with _runtime_owner_transition(account, target_binding, binding_changes):
                with _db_lock:
                    conn = get_db()
                    try:
                        with conn:
                            current = _get_available_account(conn, aid)
                            if not current:
                                raise HTTPException(404, "账号不存在或已停用")
                            active = conn.execute(
                                "SELECT id, status FROM runs WHERE account_id=? AND run_kind='warmup' "
                                "AND status IN ('queued','running','stopping','quota_wait') LIMIT 1",
                                (aid,),
                            ).fetchone()
                            conn.execute(
                                "UPDATE accounts SET warmup_enabled=?, "
                                "warmup_interval_min_hours=?, warmup_interval_max_hours=?, "
                                "warmup_next_run_at=?, warmup_last_status=?, warmup_last_error=NULL, "
                                "warmup_auth_failures=0 WHERE id=?",
                                (
                                    int(enabled),
                                    low,
                                    high,
                                    None if active else next_run_at,
                                    active["status"] if active and enabled else ("scheduled" if enabled else "off"),
                                    aid,
                                ),
                            )
                            if binding_changes:
                                conn.execute("UPDATE accounts SET cc2api_account_id=? WHERE id=?", (target_binding, aid))
                            # 旧客户端省略新字段时保留策略，null 才明确关闭某个窗口。
                            for field in threshold_fields:
                                if field in body.model_fields_set:
                                    conn.execute(f"UPDATE accounts SET {field}=? WHERE id=?", (getattr(body, field), aid))
                            if not enabled and active and active["status"] == "quota_wait":
                                conn.execute("UPDATE runs SET status='stopped',stop_requested_at=?,ended_at=? WHERE id=? AND status='quota_wait'",
                                             (time.time(), time.time(), active["id"]))
                    except sqlite3.IntegrityError:
                        raise HTTPException(409, "该 cc2api 账号已绑定其他 bench 账号")
                    finally:
                        conn.close()
            if quota_guard:
                connection = get_db()
                try:
                    current = connection.execute("SELECT * FROM accounts WHERE id=?", (aid,)).fetchone()
                finally:
                    connection.close()
                quota_guard._publish(dict(current))
    return {"ok": True, "enabled": enabled, "next_run_at": None if active else next_run_at}


@app.post("/api/accounts/{aid}/warmup/run")
def run_account_warmup_now(aid: int):
    """
    立即为已启用账号触发一次养号 run。

    :param aid: bench accounts.id
    :return: 是否成功创建 run 及最近养号状态
    """
    if not warmup_scheduler:
        raise HTTPException(500, "养号调度器尚未就绪")
    result = warmup_scheduler.trigger_account(aid)
    if result.get("started"):
        return result
    conn = get_db()
    try:
        row = conn.execute(
            "SELECT warmup_last_status, warmup_last_error, warmup_last_run_id "
            "FROM accounts WHERE id=? AND deleted_at IS NULL",
            (aid,),
        ).fetchone()
        if not row:
            raise HTTPException(404, "账号不存在")
        return {**result, **dict(row)}
    finally:
        conn.close()


@app.post("/api/accounts/{aid}/warmup/resume")
def resume_account_warmup(aid: int):
    """
    清除暂停原因并重新安排账号下一次养号。

    :param aid: bench accounts.id
    :return: 新的下次触发时间
    """
    with _db_lock:
        conn = get_db()
        try:
            with conn:
                row = conn.execute(
                    "SELECT * FROM accounts WHERE id=? AND enabled=1 AND deleted_at IS NULL",
                    (aid,),
                ).fetchone()
                if not row:
                    raise HTTPException(404, "已绑定账号不存在或已停用")
                account = dict(row)
                active = conn.execute(
                    "SELECT id, status FROM runs WHERE account_id=? AND run_kind='warmup' "
                    "AND status IN ('queued','running','stopping','quota_wait') LIMIT 1",
                    (aid,),
                ).fetchone()
                next_run_at = None if active else warmup_scheduler._next_run_at(account) if warmup_scheduler else None
                conn.execute(
                    "UPDATE accounts SET warmup_enabled=1, warmup_next_run_at=?, "
                    "warmup_last_status=?, warmup_last_error=NULL, warmup_auth_failures=0 WHERE id=?",
                    (next_run_at, active["status"] if active else "scheduled", aid),
                )
        finally:
            conn.close()
    return {"ok": True, "next_run_at": next_run_at}


@app.delete("/api/accounts/{aid}/cc2api-binding")
def delete_account_cc2api_binding(aid: int):
    """
    解除 bench 与 cc2api 绑定并停止未来养号调度。

    :param aid: bench accounts.id
    :return: 解绑成功标记
    """
    conn = get_db()
    try:
        row = conn.execute(
            "SELECT * FROM accounts WHERE id=? AND deleted_at IS NULL",
            (aid,),
        ).fetchone()
        if not row:
            raise HTTPException(404, "账号不存在")
        account = dict(row)
    finally:
        conn.close()
    with _oauth_owner_lock(str(account["name"])):
        conn = get_db()
        try:
            current = conn.execute(
                "SELECT * FROM accounts WHERE id=? AND deleted_at IS NULL",
                (aid,),
            ).fetchone()
            if not current:
                raise HTTPException(404, "账号不存在")
            account = dict(current)
        finally:
            conn.close()
        if account.get("cc2api_account_id") is not None:
            _require_oauth_owner_transition_idle(account)
        with _runtime_owner_transition(account, None):
            with _db_lock:
                conn = get_db()
                try:
                    with conn:
                        cur = conn.execute(
                            "UPDATE accounts SET cc2api_account_id=NULL, warmup_enabled=0, "
                            "warmup_next_run_at=NULL, warmup_last_status='off', warmup_last_error=NULL, "
                            "warmup_auth_failures=0 WHERE id=? AND deleted_at IS NULL",
                            (aid,),
                        )
                        if cur.rowcount == 0:
                            raise HTTPException(404, "账号不存在")
                finally:
                    conn.close()
    return {"ok": True}


@app.delete("/api/accounts/{aid}")
def delete_account(aid: int):
    """
    删除账号；已有历史引用时软删除并退出可用集合。

    :param aid: bench accounts.id
    :return: 删除方式和历史引用计数
    """
    conn = get_db()
    try:
        row = conn.execute(
            "SELECT * FROM accounts WHERE id=? AND deleted_at IS NULL",
            (aid,),
        ).fetchone()
        if not row:
            raise HTTPException(404, "账号不存在")
        account = dict(row)
    finally:
        conn.close()
    with _oauth_owner_lock(str(account["name"])):
        conn = get_db()
        try:
            current = conn.execute(
                "SELECT * FROM accounts WHERE id=? AND deleted_at IS NULL",
                (aid,),
            ).fetchone()
            if not current:
                raise HTTPException(404, "账号不存在")
            account = dict(current)
        finally:
            conn.close()
        if account.get("cc2api_account_id") is not None:
            _require_oauth_owner_transition_idle(account)
        with _runtime_owner_transition(account, None):
            with _db_lock:
                conn = get_db()
                try:
                    with conn:
                        current = conn.execute(
                            "SELECT * FROM accounts WHERE id=? AND deleted_at IS NULL",
                            (aid,),
                        ).fetchone()
                        if not current:
                            raise HTTPException(404, "账号不存在")
                        counts = _account_reference_counts(conn, aid)
                        if sum(counts.values()) > 0:
                            # 任务、批次和 run 都按 account_id 保存历史引用；软删除能保留
                            # 历史语义，同时让后台刷新器和新运行入口都不再选中该账号。
                            conn.execute(
                                "UPDATE accounts SET enabled=0, deleted_at=?, cc2api_account_id=NULL, "
                                "warmup_enabled=0, warmup_next_run_at=NULL, warmup_last_status='off' "
                                "WHERE id=?",
                                (time.time(), aid),
                            )
                            return {
                                "ok": True,
                                "deleted": True,
                                "soft_deleted": True,
                                "references": counts,
                            }
                        conn.execute("DELETE FROM warmup_quota_admissions WHERE account_id=?", (aid,))
                        conn.execute("DELETE FROM accounts WHERE id=?", (aid,))
                finally:
                    conn.close()
    return {"ok": True, "deleted": True, "soft_deleted": False}


@app.post("/api/accounts/{aid}/quota")
def query_account_quota(aid: int):
    """
    按账号代理或 cc2api 绑定链路查询 Claude Code 额度。

    :param aid: bench accounts.id
    :return: 前端可展示的标准化额度结果
    """
    if not runner:
        raise HTTPException(500, "runner not ready")
    conn = get_db()
    try:
        row = _get_available_account(conn, aid)
        if not row:
            raise HTTPException(404, "账号不存在或已停用")
        account = dict(row)
    finally:
        conn.close()
    with _oauth_owner_lock(str(account["name"])):
        conn = get_db()
        try:
            current_row = _get_available_account(conn, aid)
            if not current_row:
                raise HTTPException(404, "账号不存在或已停用")
            current = dict(current_row)
        finally:
            conn.close()
        current_binding = current.get("cc2api_account_id")
        if account_runtime:
            try:
                result = runner.query_quota(current)
                if quota_guard:
                    account_error = _quota_account_error(result)
                    if account_error:
                        quota_guard.record_auth_failure(current, account_error)
                    else:
                        quota_guard.record_manual_usage(current, result)
                return result
            except (ValueError, ConnectionError) as exc:
                raise HTTPException(409, _redact_cc2api_error(exc))
        if current_binding is not None:
            try:
                _sync_bound_account_credentials_locked(current, OAUTH_REFRESH_BUFFER_SEC)
                raw = cc2api_client.refresh_usage(int(current_binding))
                _sync_bound_account_credentials_locked(current, OAUTH_REFRESH_BUFFER_SEC)
                result = _format_quota_result(raw)
                if quota_guard:
                    quota_guard.record_manual_usage(current, result)
                return result
            except ConnectionError as exc:
                raise HTTPException(502, _redact_cc2api_error(exc))
            except ValueError as exc:
                raise HTTPException(400, _redact_cc2api_error(exc))
        try:
            result = runner.query_quota(current)
            if quota_guard:
                quota_guard.record_manual_usage(current, result)
            return result
        except ValueError as exc:
            raise HTTPException(400, str(exc))
        except Exception as exc:
            raise HTTPException(500, f"额度查询失败：{exc}")


# ---------- accounts: 内嵌 OAuth 登录（WebUI 用） ----------
class LoginStartIn(BaseModel):
    """添加账号第一步：起 login 会话，配置代理走 OAuth。"""

    name: str
    timezone: Optional[str] = None
    upstream_proxy_scheme: Optional[str] = None
    upstream_socks5_host: Optional[str] = None
    upstream_socks5_port: Optional[int] = None
    upstream_socks5_user: Optional[str] = None
    upstream_socks5_pass: Optional[str] = None
    force_reauth: bool = False


class LoginDraftActionIn(BaseModel):
    """草稿操作必须携带页面看到的代次，防止旧页面操作新登录。

    :param generation: 页面最后读取的草稿代次
    """

    model_config = ConfigDict(extra="forbid")
    generation: str


class LoginCodeIn(BaseModel):
    """授权码投递输入；手动校验避免默认 422 回显秘密。

    :param request_id: 本次投递的幂等标识
    :param code: 完整授权码
    """

    model_config = ConfigDict(extra="forbid")
    request_id: StrictStr
    code: StrictStr


def _login_drafts() -> LoginDraftStore:
    if not account_runtime or not login_manager:
        raise HTTPException(409, "登录草稿管理仅在 v3 固定环境中可用")
    return LoginDraftStore(account_runtime, get_db, _db_lock)


def _draft_session(row: dict) -> Optional[LoginSession]:
    with login_manager._lock:
        return next((session for session in login_manager.sessions.values() if session.name == row["name"]), None)


def _login_response(session: LoginSession) -> dict:
    return {"session_id": session.sid, "ws_path": f"/api/accounts/login/ws/{session.sid}",
        "has_sidecar": session.sidecar_id is not None, "name": session.name,
        "reconnectable": bool(account_runtime) and session.phase == "authorizing",
        "cc2api_account_id": session.binding_id, "environment_id": session.environment_id,
        "draft_generation": session.draft_generation}


def _unverified_login_draft(row: dict) -> dict:
    return {"draft_id": row["environment_id"], "environment_id": row["environment_id"],
        "name": row["name"], "generation": "unverified", "state": "reconcile",
        "session_id": None, "reconnectable": False, "credentials_ready": False,
        "credentials_present": False, "container_status": "unknown",
        "message": "草稿记录损坏或归属不一致，请检查环境；自动操作已禁用",
        "can_resume": False, "can_restart": False, "can_delete": False,
        "can_reconcile": False, "proxy_known": False, "proxy_summary": None}


@app.get("/api/accounts/login-drafts")
def list_login_drafts() -> list[dict]:
    """仅为账号页展示未提交环境，不提供正式账号 ID 或凭据。

    :return: 草稿状态和受控操作许可
    """
    if not account_runtime:
        return []
    drafts = _login_drafts()
    result = []
    for row in drafts.rows():
        owner_lock = _oauth_owner_lock(row["name"])
        acquired = owner_lock.acquire(blocking=False)
        try:
            try:
                current = drafts.row(row["environment_id"])
                if not current:
                    continue
                initial_record = drafts.record(current)
            except (ValueError, KeyError, TypeError, OSError):
                # 单条私有记录损坏不能遮住其它账号；未知归属只展示，不开放清理。
                result.append(_unverified_login_draft(row))
                continue
            pending = initial_record["phase"] == "submitting"
            if current["account_id"] is not None and not pending:
                continue
            message, allowed = "", True
            try:
                record = drafts.guard(current, allow_submitting=pending)
            except ValueError as error:
                record = initial_record
                message, allowed = str(error), False
            session = _draft_session(current)
            if session and allowed and record["phase"] != "deleting" and acquired:
                try:
                    _login_status_snapshot(session)
                except HTTPException as error:
                    if error.status_code == 410:
                        message = "原登录已过期，请重新登录"
                        session.phase = "ended"
                    else:
                        message, allowed = "暂时无法确认登录状态，请稍后重试", False
            phase = record["phase"]
            if pending:
                phase, message = "submitting", "账号保存尚未完成，请继续登录并重试提交"
            elif not allowed:
                phase = "reconcile"
            elif phase != "deleting":
                phase = session.phase if session else ("preparing" if login_manager.has_active_name(current["name"]) else
                    (phase if phase in ("cancelled", "ended") else "interrupted"))
            profile, _ = drafts.profile(current, record)
            container_status = "missing"
            if current["container_id"]:
                try:
                    container = account_runtime._container(current)
                    container.reload()
                    container_status = container.status
                except NotFound:
                    pass
                except Exception:
                    message, allowed, phase = "无法确认专属容器归属，请检查环境", False, "reconcile"
                    container_status = "unknown"
            if not acquired:
                # 初始化/提交可持续较久；列表只读快照，不等待操作锁或改写会话状态。
                message, allowed = "登录操作进行中，请稍候刷新", False
            can_reconcile = False
            if acquired and not pending and phase == "reconcile":
                try:
                    drafts.recovery_record(current, record["generation"])
                    can_reconcile = True
                except Exception:
                    # 网络状态未知只禁用该草稿恢复，不能遮住其它账号列表。
                    pass
            result.append({"draft_id": current["environment_id"], "environment_id": current["environment_id"],
                "name": current["name"], "generation": record["generation"], "state": phase,
                "session_id": session.sid if session else None,
                "reconnectable": bool(session and session.phase == "authorizing"),
                "credentials_ready": bool(session and session.phase == "ready_to_submit"),
                "credentials_present": (profile / ".credentials.json").is_file(),
                "container_status": container_status, "message": message,
                "can_resume": allowed and phase not in ("preparing", "deleting") and bool(session or (profile / ".credentials.json").is_file()),
                "can_restart": allowed and phase not in ("preparing", "deleting", "submitting"),
                "can_delete": allowed and phase not in ("preparing", "submitting"),
                "can_reconcile": can_reconcile, **drafts.proxy_summary(current)})
        finally:
            if acquired:
                owner_lock.release()
    return result


def _require_login_draft(environment_id: str, generation: str) -> tuple[LoginDraftStore, dict, dict]:
    drafts = _login_drafts()
    row = drafts.row(environment_id)
    if not row:
        raise HTTPException(404, "登录草稿已不存在")
    record = drafts.guard(row, generation)
    if record["phase"] == "deleting":
        raise ValueError("草稿正在清理，请先完成删除")
    return drafts, row, record


@app.post("/api/accounts/login-drafts/{environment_id}/reconcile")
def reconcile_login_draft(environment_id: str, body: LoginDraftActionIn) -> dict:
    """受控恢复未绑定草稿，保留 HOME 和未提交授权产物。

    :param environment_id: 原草稿环境 ID
    :param body: 页面读取的草稿代次
    :return: 对账完成；冲突或未知结果保持保护
    """
    drafts = _login_drafts()
    row = drafts.row(environment_id)
    if not row:
        raise HTTPException(404, "草稿已不存在")
    try:
        with _oauth_owner_lock(row["name"]), _profile_lock(row["name"]), account_runtime.environment_lock(environment_id):
            row = drafts.row(environment_id)
            if not row:
                raise ValueError("草稿已不存在")
            drafts.recovery_record(row, body.generation)
            account_runtime.maintenance(environment_id, "reconcile")
        # 收口方法自行取得非重入 owner 锁，代次在内部再次核对。
        login_manager.cleanup_reconciled(environment_id)
        return {"ok": True}
    except (ValueError, KeyError, TypeError):
        raise HTTPException(409, "草稿有活动工作、保存意图或归属冲突，请刷新或查看环境") from None
    except Exception:
        raise HTTPException(503, "恢复检查尚未完成，草稿与产物已保留，请重试") from None


@app.post("/api/accounts/login-drafts/{environment_id}/resume")
def resume_login_draft(environment_id: str, body: LoginDraftActionIn) -> dict:
    """继续活跃原会话，或验证重启后保留的凭据后提供提交入口。

    :param environment_id: 固定草稿环境
    :param body: 页面草稿代次
    :return: 可恢复的会话信息；不返回代理密码
    """
    drafts = _login_drafts()
    row = drafts.row(environment_id)
    if not row:
        raise HTTPException(404, "登录草稿已不存在")
    with _oauth_owner_lock(row["name"]), _profile_lock(row["name"]):
        try:
            row = drafts.row(environment_id)
            if not row:
                raise HTTPException(404, "登录草稿已不存在")
            record = drafts.guard(row, body.generation, allow_submitting=True)
            if record["phase"] == "deleting":
                raise ValueError("草稿正在清理，请先完成删除")
            pending = record["phase"] == "submitting"
            session = _draft_session(row)
            if session:
                if record.get("sid") != session.sid:
                    # 兼容升级前只有内存会话的环境，继续时补齐当前登录的持久归属。
                    record = drafts.save(row, sid=session.sid, generation=uuid.uuid4().hex, phase=session.phase,
                        version=session.version, home=session.home, created_at=session.created_at)
                session.environment_id, session.draft_generation = environment_id, record["generation"]
                _login_status_snapshot(session)
                return _login_response(session)
            profile, home = drafts.profile(row, record)
            if not (profile / ".credentials.json").is_file():
                raise ValueError("原登录已中断且没有凭据，请选择重新登录")
            account = drafts.account(row)
            version = record.get("version") or effective_claude_code_version()
            if not _CLAUDE_CODE_VERSION_RE.fullmatch(version):
                raise ValueError("草稿 CLI 版本无效")
            sid = uuid.uuid4().hex[:12]
            _, container = account_runtime.recover_login(sid, account, version, home)
            session = LoginSession(sid, row["name"], container.id, container.id, {}, profile, home != "/home/node")
            session.home, session.version = home, version
            session.environment_id, session.draft_generation = environment_id, uuid.uuid4().hex
            session.phase = "submitting" if pending else "ready_to_submit"
            with login_manager._lock:
                login_manager.sessions[sid] = session
                login_manager._name_locks[session.name] = sid
            drafts.save(row, sid=sid, generation=session.draft_generation, phase=session.phase,
                version=version, home=home, created_at=session.created_at)
            if not login_manager.auth_status(sid).get("loggedIn"):
                if not pending:
                    login_manager.cleanup(sid)
                raise ValueError("保留产物未通过 CLI 认证检查，请重新登录")
            return _login_response(session)
        except ValueError as error:
            raise HTTPException(409, str(error)) from None
        except HTTPException:
            raise
        except Exception:
            raise HTTPException(503, "暂时无法继续登录，草稿和产物已保留，请重试或检查环境") from None


@app.post("/api/accounts/login-drafts/{environment_id}/restart")
def restart_login_draft(environment_id: str, body: LoginDraftActionIn) -> dict:
    """在原固定环境重新授权，明确创建新 SID 和草稿代次。

    :param environment_id: 原草稿环境
    :param body: 页面草稿代次
    :return: 新登录终端信息
    """
    drafts = _login_drafts()
    row = drafts.row(environment_id)
    if not row:
        raise HTTPException(404, "登录草稿已不存在")
    with _oauth_owner_lock(row["name"]), _profile_lock(row["name"]):
        try:
            drafts, row, record = _require_login_draft(environment_id, body.generation)
            account = drafts.account(row)
            session = _draft_session(row)
            if session:
                login_manager.cleanup(session.sid)
            proxy = {"scheme": account["upstream_proxy_scheme"], "host": account["upstream_socks5_host"],
                "port": account["upstream_socks5_port"], "user": account["upstream_socks5_user"], "pass": account["upstream_socks5_pass"]}
            session = login_manager.start(row["name"], proxy, True, account["timezone"], record.get("version"))
            return _login_response(session)
        except ValueError as error:
            raise HTTPException(409, str(error)) from None
        except HTTPException:
            raise
        except Exception:
            raise HTTPException(503, "重新登录尚未完成，草稿仍保留，请重试或检查环境") from None


@app.delete("/api/accounts/login-drafts/{environment_id}")
def delete_login_draft(environment_id: str, generation: str) -> dict:
    """完整删除未提交草稿，失败保留可重试状态。

    :param environment_id: 专属固定环境 ID
    :param generation: 页面看到的草稿代次
    :return: 仅完整清理或已经不存在时返回 ok
    """
    drafts = _login_drafts()
    try:
        row = drafts.row(environment_id)
        if row:
            with _oauth_owner_lock(row["name"]), _profile_lock(row["name"]):
                drafts.delete(row, generation, login_manager)
        return {"ok": True}
    except ValueError as error:
        raise HTTPException(409, str(error)) from None
    except Exception:
        raise HTTPException(503, "清理未完成，草稿已保留，请刷新列表后重试删除") from None


@app.post("/api/accounts/login/start")
def login_start(body: LoginStartIn):
    """启动一个 OAuth 引导会话；前端拿到 session_id 后开 WS 拿 PTY"""
    if not login_manager:
        raise HTTPException(500, "登录管理器尚未就绪")
    with _oauth_owner_lock(body.name):
        conn = get_db()
        try:
            bound = conn.execute(
                "SELECT * FROM accounts WHERE name=? AND deleted_at IS NULL",
                (body.name,),
            ).fetchone()
        finally:
            conn.close()
        if bound and bound["cc2api_account_id"] is not None:
            if not account_runtime or not body.force_reauth:
                raise HTTPException(409, "已绑定账号须使用 v3 的显式重授权入口")
            # 关联重授权不接受顺便改代理/时区，继续沿用权威关联配置。
            body = LoginStartIn(name=body.name, force_reauth=True, timezone=bound["timezone"],
                **{key: bound[key] for key in ("upstream_proxy_scheme", "upstream_socks5_host", "upstream_socks5_port", "upstream_socks5_user", "upstream_socks5_pass")})
        if bound:
            _require_oauth_owner_transition_idle(dict(bound))
        try:
            proxy_scheme = _normalize_upstream_proxy_scheme(body.upstream_proxy_scheme)
            timezone = _normalize_account_timezone(body.timezone)
            session = login_manager.start(
                body.name,
                {
                    "scheme": proxy_scheme,
                    "host": body.upstream_socks5_host,
                    "port": body.upstream_socks5_port,
                    "user": body.upstream_socks5_user,
                    "pass": body.upstream_socks5_pass,
                },
                body.force_reauth,
                timezone,
            )
        except ValueError as e:
            raise HTTPException(400, str(e))
        except Exception as e:
            raise HTTPException(500, f"启动登录会话失败：{e}")
    return _login_response(session)


def _send_login_code(sid: str, body: LoginCodeIn) -> dict:
    session = login_manager.get(sid) if login_manager else None
    if not account_runtime or not session:
        raise HTTPException(404, "原登录会话不可用，发送结果不能确认")
    with _oauth_owner_lock(session.name):
        if login_manager.get(sid) is not session:
            raise HTTPException(404, "原登录会话已结束，发送结果不能确认")
        if body.request_id in session.code_receipts:
            return dict(session.code_receipts[body.request_id])
        if session.phase != "authorizing" or time.time() >= session.created_at + int(os.environ.get("V3_LOGIN_TTL_SECONDS", "1800")):
            raise HTTPException(409, "原登录已结束或过期，授权码未发送")
        if len(session.code_receipts) >= 32:
            raise HTTPException(409, "本会话发送次数已达上限，请检查登录状态")
        if session.environment_id:
            drafts = _login_drafts()
            row = drafts.row(session.environment_id)
            if not row:
                raise HTTPException(409, "草稿已不存在，授权码未发送")
            try:
                drafts.guard(row, session.draft_generation)
            except ValueError:
                raise HTTPException(409, "草稿正在保存、清理或已换代，授权码未发送") from None
        receipt = {"request_id": body.request_id, "status": "sending", "message": "正在发送授权码"}
        session.code_receipts[body.request_id] = receipt
        try:
            account_runtime.send_login_code(session, body.request_id, body.code.strip())
            receipt.update(status="delivered", message="已送到 CLI，等待认证检查；这不代表登录成功")
        except ValueError:
            receipt.update(status="rejected", message="原登录终端或环境不可用，授权码未发送，请刷新状态")
        except Exception:
            receipt.update(status="uncertain", message="发送结果未知，请查询本次回执并检查 CLI，勿重复发送")
        return dict(receipt)


@app.post("/api/accounts/login/{sid}/code")
async def login_code(sid: str, request: Request, response: Response) -> dict:
    """有界接收授权码，返回不包含秘密的投递回执。

    :param sid: 原登录会话
    :param request: 含请求标识与授权码的正文
    :param response: 禁止缓存回执
    :return: 本次投递状态；验证失败只返回固定说明
    """
    response.headers["Cache-Control"] = "no-store"
    payload = bytearray()
    async for chunk in request.stream():
        if len(payload) + len(chunk) > 65536:
            raise HTTPException(413, "授权码请求过长，未发送")
        payload.extend(chunk)
    try:
        body = LoginCodeIn.model_validate(json.loads(payload))
        if (not re.fullmatch(r"[a-f0-9]{32}", body.request_id) or not 1 <= len(body.code.strip()) <= 8192
            or any(ord(character) < 32 or ord(character) == 127 for character in body.code)):
            raise ValueError
    except (ValueError, TypeError, ValidationError):
        raise HTTPException(422, "请输入完整授权码；不允许空码、控制字符或超长内容") from None
    finally:
        payload.clear()
    return await asyncio.to_thread(_send_login_code, sid, body)


@app.get("/api/accounts/login/{sid}/code/{request_id}")
def login_code_receipt(sid: str, request_id: str, response: Response) -> dict:
    """查询已有回执，绝不重新注入授权码。

    :param sid: 原登录会话
    :param request_id: 原投递请求标识
    :param response: 禁止缓存回执
    :return: 已有投递状态；无回执时不能推断未发送
    """
    response.headers["Cache-Control"] = "no-store"
    session = login_manager.get(sid) if login_manager else None
    if not session or not re.fullmatch(r"[a-f0-9]{32}", request_id):
        raise HTTPException(404, "原回执不可查，发送结果未知，请检查 CLI 状态")
    with _oauth_owner_lock(session.name):
        receipt = session.code_receipts.get(request_id) if login_manager.get(sid) is session else None
        if receipt is None:
            raise HTTPException(404, "原回执不可查，发送结果未知，请检查 CLI 状态")
        return dict(receipt)


@app.get("/api/accounts/login/{sid}/status")
def login_status(sid: str, response: Response) -> dict:
    """提供不含凭据的登录状态与实际授权链接。

    :param sid: 当前登录会话
    :param response: 设置禁止缓存的响应
    :return: 登录阶段、可重连性与已验证链接
    """
    response.headers["Cache-Control"] = "no-store"
    session = login_manager.get(sid) if login_manager else None
    if not session:
        completed = login_manager.completed.get(sid) if login_manager else None
        if completed and completed["expires_at"] > time.time():
            return {"phase": "committed", "reconnectable": False, "authorization_url": None}
        raise HTTPException(404, "登录会话已结束或过期，请重新授权")
    with _oauth_owner_lock(session.name):
        if login_manager.get(sid) is not session:
            raise HTTPException(404, "登录会话已结束，请刷新账号列表")
        return _login_status_snapshot(session)


def _login_status_snapshot(session: LoginSession) -> dict:
    expires_at = session.created_at + int(os.environ.get("V3_LOGIN_TTL_SECONDS", "1800"))
    if session.phase in ("authorizing", "ended", "ready_to_submit") and time.time() >= expires_at:
        raise HTTPException(410, "登录会话已过期，请从账号列表继续或重新授权")
    ready = not account_runtime and (session.profile_dir / ".credentials.json").is_file()
    if account_runtime and session.phase in ("authorizing", "ended", "ready_to_submit"):
        try:
            if (session.profile_dir / ".credentials.json").is_file():
                ready = bool(login_manager.auth_status(session.sid).get("loggedIn"))
            if ready:
                session.phase = "ready_to_submit"
            elif session.phase == "ready_to_submit":
                session.phase = "ended"
            elif session.phase == "authorizing":
                session.authorization_url = authorization_url(account_runtime.capture_login_pane(session)) or session.authorization_url
                if not account_runtime.login_terminal_alive(session):
                    session.phase = "ended"
        except ValueError:
            session.phase = "ended"
        except Exception:
            raise HTTPException(503, "暂时无法读取登录终端，请稍后重试") from None
    if session.phase != "authorizing":
        session.authorization_url = None
    if session.environment_id:
        drafts = _login_drafts()
        row = drafts.row(session.environment_id)
        if row:
            record = drafts.guard(row, session.draft_generation, allow_submitting=session.phase == "submitting")
            if record["phase"] == "deleting":
                raise HTTPException(409, "草稿正在清理")
            drafts.save(row, phase=session.phase)
    message = {"authorizing": "终端正在等待授权", "ended": "登录终端已结束，请重新登录",
        "ready_to_submit": "CLI 认证检查通过，可以提交保存", "submitting": "凭据同步待确认，可重试提交或在环境页对账",
        "committed": "登录已完成"}.get(session.phase, "登录会话已结束")
    return {"phase": session.phase, "credentials_ready": ready, "expires_at": expires_at,
        "reconnectable": bool(account_runtime) and session.phase == "authorizing",
        "authorization_url": session.authorization_url, "message": message,
        "restartable": session.phase == "ended"}


@app.websocket("/api/accounts/login/ws/{sid}")
async def login_ws(websocket: WebSocket, sid: str):
    """PTY 桥：把 worker 里 `claude auth login` 的 PTY 双向接到浏览器 xterm"""
    if V3_ENABLED and not _v3_websocket_authorized(websocket):
        await websocket.close(code=4401)
        return
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
    if session.phase != "authorizing" or time.time() >= session.created_at + int(os.environ.get("V3_LOGIN_TTL_SECONDS", "1800")):
        await websocket.close(code=4404)
        return

    api = login_manager.client.api
    try:
        execution = await asyncio.to_thread(api.exec_create,
            session.worker_id,
            (["tmux", "-S", f"/tmp/v3-login-{sid}.sock", "attach-session", "-d", "-t", sid]
             if account_runtime else ["claude", "auth", "login"]),
            stdin=True,
            tty=True,
            user="root" if account_runtime else WORKER_USER,
            environment=_claude_exec_env(session.sidecar_id is not None, {
                "TERM": "xterm-256color",
                "COLUMNS": "120",
                "LINES": "36",
            }),
            workdir=session.home,
        )
        exec_id = execution["Id"]
        sock = await asyncio.to_thread(api.exec_start,
            exec_id, detach=False, tty=True,
            stream=False, socket=True, demux=False,
        )
    except Exception:
        await websocket.send_text(json.dumps(
            {"type": "error", "msg": "暂时无法连接登录终端，请重连或检查环境状态"}))
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
            while not closed.is_set() and session.phase == "authorizing":
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
                if session.phase != "authorizing":
                    break
                if msg.get("bytes"):
                    if not account_runtime:
                        await loop.sock_sendall(raw, msg["bytes"])
                    continue
                txt = msg.get("text")
                if not txt:
                    continue
                # text 消息约定 JSON：{type:input|resize, ...}
                try:
                    ev = json.loads(txt)
                except json.JSONDecodeError:
                    if not account_runtime:
                        await loop.sock_sendall(raw, txt.encode())
                    continue
                if not isinstance(ev, dict) or session.phase != "authorizing":
                    continue
                if ev.get("type") == "ping":
                    await websocket.send_text(json.dumps({"type": "pong"}))
                elif ev.get("type") == "resize":
                    try:
                        await asyncio.to_thread(api.exec_resize,
                            exec_id,
                            height=int(ev.get("rows") or 36),
                            width=int(ev.get("cols") or 120),
                        )
                    except Exception:
                        pass
                elif ev.get("type") == "input":
                    data = ev.get("data")
                    if isinstance(data, str) and data:
                        # 独立授权码输入框负责可见回执；终端仍需透传其它 CLI 确认和选择。
                        await loop.sock_sendall(raw, data.encode())
        except WebSocketDisconnect:
            pass
        except Exception:
            pass
        finally:
            closed.set()

    pumps = [asyncio.create_task(pump_container_to_ws()), asyncio.create_task(pump_ws_to_container())]
    try:
        # 任一方向结束即关闭 attach；gather 两条永久等待会遗留半开连接。
        await asyncio.wait(pumps, return_when=asyncio.FIRST_COMPLETED)
    finally:
        for pump in pumps:
            pump.cancel()
        await asyncio.gather(*pumps, return_exceptions=True)
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
    """与草稿删除、取消和重登互斥地校验并保存登录。

    :param sid: 本次登录会话
    :param body: 账号名及原登录配置
    :return: 已保存账号的结果，不含凭据
    """
    session = login_manager.get(sid) if login_manager else None
    with _oauth_owner_lock(session.name if session else body.name):
        return _login_commit_locked(sid, body)


def _login_commit_locked(sid: str, body: LoginStartIn):
    if not login_manager:
        raise HTTPException(500)
    session = login_manager.get(sid)
    if not session:
        completed = login_manager.completed.get(sid)
        if completed and completed["expires_at"] > time.time() and completed["result"]["name"] == body.name:
            return completed["result"]
        raise HTTPException(404, "session not found")
    if session.name != body.name:
        raise HTTPException(400, "name mismatch with session")
    if account_runtime and session.binding_id is not None:
        try:
            return login_manager.commit_bound(session)
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from None
        except ConnectionError:
            raise HTTPException(503, "凭据同步结果尚未确认，请重试提交；暂存和维护门禁已保留") from None
        except Exception:
            raise HTTPException(500, "重授权未完成，请重试提交或在环境页对账") from None
    if session.environment_id:
        try:
            drafts = _login_drafts()
            row = drafts.row(session.environment_id)
            if not row:
                raise ValueError("原登录草稿已不存在")
            record = drafts.record(row)
            if record.get("sid") != sid or record["generation"] != session.draft_generation:
                raise ValueError("登录草稿已换代")
            drafts.guard(row, session.draft_generation, allow_submitting=record["phase"] == "submitting")
            body = LoginStartIn(**drafts.account(row))
        except ValueError as error:
            raise HTTPException(409, str(error)) from None
    conn = get_db()
    try:
        bound = conn.execute(
            "SELECT id FROM accounts WHERE name=? AND deleted_at IS NULL "
            "AND cc2api_account_id IS NOT NULL",
            (session.name,),
        ).fetchone()
    finally:
        conn.close()
    if bound:
        raise HTTPException(409, "账号已绑定 cc2api，请先解绑后再提交重授权")
    try:
        proxy_scheme = _normalize_upstream_proxy_scheme(body.upstream_proxy_scheme)
        timezone = _normalize_account_timezone(body.timezone)
    except ValueError as e:
        raise HTTPException(400, str(e))

    # 撞 in-flight run 直接拒绝:此时若 commit 继续往下走会清 telemetry/backups,
    # 与正在跑的 run 复制 profile 的窗口发生竞态。让用户主动决定何时重登。
    # 首次登录场景下 account 还没入库,COUNT 必为 0,自然通过。
    name = session.name
    conn = get_db()
    try:
        inflight = conn.execute(
            "SELECT COUNT(*) AS n FROM runs r "
            "JOIN accounts a ON r.account_id = a.id "
            "WHERE a.name = ? AND r.status IN ('queued','running','stopping','quota_wait')",
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
    if continue_manager:
        conn = get_db()
        try:
            account = conn.execute("SELECT id FROM accounts WHERE name=?", (name,)).fetchone()
        finally:
            conn.close()
        if account and continue_manager.has_active_account(account["id"]):
            raise HTTPException(409, "账号仍有继续对话会话，请先关闭再重新授权")

    try:
        status = login_manager.auth_status(sid)
    except KeyError:
        raise HTTPException(404, "session not found")
    except Exception as e:
        raise HTTPException(500, f"auth status check failed: {e}")
    if not status.get("loggedIn"):
        # 不清容器：让用户继续 retry。返回错误细节给前端展示。
        raise HTTPException(400, f"not logged in yet: {status}")

    if session.environment_id:
        # 本地保存也可能在 DB/HOME 之间中断；先记意图，取消/删除不得丢掉维护材料。
        drafts.save(row, phase="submitting")
        session.phase = "submitting"

    try:
        login_manager.persist_profile_files(sid)
        login_manager.persist_top_config(sid)
    except Exception as e:
        raise HTTPException(500, f"failed to persist claude profile: {e}")

    _persist_default_claude_settings(BENCH_DATA / "profiles" / name)
    _persist_default_claude_top_config(BENCH_DATA / "profiles" / name)

    # 清理 profile 残留遥测痕迹:OAuth 启动那次 claude 写到 telemetry/ 和
    # backups/ 的内容对后续 task run 无用,反而会被一路重放 → 入库前清掉。
    # 路径只用 session.name(_ACC_NAME_RE 已校验),且必须用 BENCH_DATA
    # (orchestrator 容器内路径),不能用 HOST_BENCH_DATA(那是给 docker daemon
    # 报告挂载点的宿主路径,在 orchestrator 容器里访问不到)。
    profile_dir = BENCH_DATA / "profiles" / name
    if not account_runtime:
        shutil.rmtree(profile_dir / "telemetry", ignore_errors=True)
        shutil.rmtree(profile_dir / "backups", ignore_errors=True)

    with _db_lock:
        conn = get_db()
        try:
            with conn:
                try:
                    restored_account_id = _infer_deleted_account_id(conn, name)
                    columns = (
                        "id, name, profile_path, upstream_proxy_scheme, "
                        "upstream_socks5_host, upstream_socks5_port, "
                        "upstream_socks5_user, upstream_socks5_pass, timezone, enabled"
                    ) if restored_account_id is not None else (
                        "name, profile_path, upstream_proxy_scheme, "
                        "upstream_socks5_host, upstream_socks5_port, "
                        "upstream_socks5_user, upstream_socks5_pass, timezone, enabled"
                    )
                    values_sql = "(?,?,?,?,?,?,?,?,?,?)" if restored_account_id is not None else "(?,?,?,?,?,?,?,?,?)"
                    values: tuple[object, ...]
                    base_values = (
                        name,
                        f"profiles/{name}",
                        proxy_scheme,
                        body.upstream_socks5_host,
                        body.upstream_socks5_port,
                        body.upstream_socks5_user,
                        body.upstream_socks5_pass,
                        timezone,
                        0 if session.environment_id else 1,
                    )
                    values = ((restored_account_id,) + base_values) if restored_account_id is not None else base_values
                    cur = conn.execute(
                        f"INSERT INTO accounts({columns}) VALUES{values_sql}",
                        values,
                    )
                    account_id = restored_account_id if restored_account_id is not None else cur.lastrowid
                except sqlite3.IntegrityError:
                    # 同名账号已存在 → 视为"重新登录"：覆盖代理配置，并重新启用账号。
                    conn.execute(
                        "UPDATE accounts SET profile_path=?, upstream_proxy_scheme=?, upstream_socks5_host=?, "
                        "upstream_socks5_port=?, upstream_socks5_user=?, "
                        "upstream_socks5_pass=?, timezone=?, enabled=?, deleted_at=NULL WHERE name=?",
                        (
                            f"profiles/{name}",
                            proxy_scheme,
                            body.upstream_socks5_host,
                            body.upstream_socks5_port,
                            body.upstream_socks5_user,
                            body.upstream_socks5_pass,
                            timezone,
                            0 if session.environment_id else 1,
                            name,
                        ),
                    )
                    r = conn.execute(
                        "SELECT id FROM accounts WHERE name=?", (name,)
                    ).fetchone()
                    account_id = r["id"]
                # 已完成显式重授权且没有活跃工作；旧身份的拒绝和游标不能污染新会话。
                conn.execute("DELETE FROM account_quota_states WHERE account_id=?", (account_id,))
                conn.execute("DELETE FROM quota_observation_cursors WHERE account_id=?", (account_id,))
        finally:
            conn.close()

    if account_runtime:
        if session.environment_id:
            drafts.save(row, saved_account_id=account_id)
        account_runtime.commit_login(session, account_id)
        if session.environment_id:
            cleanup_home = record.get("cleanup_home") or (session.home if session.force_reauth else None)
            # HOME 已原子镜像成功；先更新恢复入口，清理暂存失败也能从主 HOME 重试。
            drafts.save(row, home="/home/node", cleanup_home=cleanup_home)
    login_manager.cleanup(sid)
    result = {
        "id": account_id,
        "name": name,
        "auth_method": status.get("authMethod"),
    }
    if account_runtime:
        result.update(cc2api_account_id=None, credentials_synced=False)
    if session.environment_id:
        if cleanup_home:
            if not re.fullmatch(r"/home/node/\.v3-login/[a-f0-9]{12}", cleanup_home):
                raise ValueError("暂存 HOME 归属无效，账号已保存但清理需检查")
            staged_profile, _ = drafts.profile(row, {"home": cleanup_home})
            drafts._safe_tree(staged_profile.parent, account_runtime._root(row) / "home" / ".v3-login")
            if staged_profile.parent.exists():
                shutil.rmtree(staged_profile.parent)
        with _db_lock:
            connection = get_db()
            try:
                with connection:
                    connection.execute("UPDATE accounts SET enabled=1 WHERE id=? AND name=? AND cc2api_account_id IS NULL AND deleted_at IS NULL", (account_id, name))
            finally:
                connection.close()
        _login_drafts()._path(session.environment_id).unlink(missing_ok=True)
    with login_manager._lock:
        login_manager.completed[sid] = {"result": result, "expires_at": time.time() + 1800}
    return result


@app.delete("/api/accounts/login/{sid}")
def login_cancel(sid: str):
    """放弃登录：停容器 + 清状态。可重复调用幂等。"""
    if login_manager:
        session = login_manager.get(sid)
        if session:
            with _oauth_owner_lock(session.name):
                if session.binding_id is not None and session.commit_context["path"].exists():
                    account_runtime.reconcile(session.commit_context["environment_id"])
                    if session.commit_context["path"].exists():
                        raise HTTPException(409, "提交结果仍需对账，暂存凭据和维护门禁已保留")
                if session.environment_id:
                    drafts = _login_drafts()
                    row = drafts.row(session.environment_id)
                    if row and drafts.record(row)["phase"] == "submitting":
                        raise HTTPException(409, "账号保存尚未完成，请先重试提交，不能取消并丢弃产物")
                try:
                    login_manager.cleanup(sid)
                except Exception:
                    raise HTTPException(503, "取消清理未完成，草稿与产物已保留；请刷新账号列表后恢复检查") from None
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
    """
    创建单个 topic 任务的请求体。

    :param topic_no: topic 编号
    :param account_id: 执行账号 ID
    :param prompt: 可选完整 prompt 覆盖
    :param prompt_mode: 默认 prompt 的表达模式
    :param timeout_sec: 单次运行超时秒数
    :param repeat_n: 运行次数
    """

    topic_no: int
    account_id: int
    prompt: Optional[str] = None
    prompt_mode: TopicPromptMode = "natural"
    timeout_sec: int = 1800
    repeat_n: int = 1


class BatchIn(BaseModel):
    """
    按账号批量调度 topic 的请求体。

    :param account_id: 执行账号 ID
    :param topic_ids: 需要运行的 topic ID 列表
    :param prompt: 可选批次统一 prompt 覆盖
    :param prompt_mode: 默认 prompt 的表达模式
    :param concurrency: 批次并发数
    :param interval_min_sec: 相邻投放的最小间隔秒数
    :param interval_max_sec: 相邻投放的最大间隔秒数
    :param timeout_sec: 单项运行超时秒数
    """

    account_id: int
    topic_ids: list[int]
    prompt: Optional[str] = None
    prompt_mode: TopicPromptMode = "natural"
    concurrency: int = 2
    interval_min_sec: int = 0
    interval_max_sec: int = 0
    timeout_sec: int = 1800


class CaptureRunIn(BaseModel):
    """
    启动单次完整 HTTP 抓包 run 的请求体。

    :param account_id: 账号 ID
    :param topic_id: topic ID
    :param prompt: 可选 prompt 覆盖
    :param prompt_mode: 默认 prompt 的表达模式
    :param timeout_sec: 本次 run 超时时间
    :param model_override: 本次抓包 run 的 Claude Code `--model` 覆盖
    :param effort_level: 本次抓包 run 的思考预算；空值回退 `.env`
    :param permission_mode: 本次抓包 run 的 Claude Code 权限模式
    """

    model_config = ConfigDict(protected_namespaces=())

    account_id: int
    topic_id: int
    prompt: Optional[str] = None
    prompt_mode: TopicPromptMode = "canonical"
    timeout_sec: int = 1800
    model_override: Optional[str] = None
    effort_level: Optional[str] = None
    permission_mode: CapturePermissionMode = "bypassPermissions"


@app.post("/api/tasks")
def create_task(body: TaskIn):
    """
    创建单个 topic 任务定义并返回任务 ID。

    :param body: 单任务创建参数
    :return: 包含新任务 ID 的响应字典
    """
    conn = get_db()
    try:
        topic_row = conn.execute(
            "SELECT * FROM topics WHERE no=? AND deleted_at IS NULL",
            (body.topic_no,),
        ).fetchone()
        if not topic_row:
            raise HTTPException(404, f"topic {body.topic_no} not found")
        topic = dict(topic_row)
        recent_fingerprints = (
            _load_recent_topic_prompt_fingerprints(conn)
            if _should_load_topic_prompt_history(body.prompt, body.prompt_mode)
            else None
        )
    finally:
        conn.close()
    prompt = _resolve_topic_prompt(
        topic,
        body.prompt,
        body.prompt_mode,
        recent_fingerprints,
    )
    with _db_lock:
        conn = get_db()
        try:
            with conn:
                account_row = _get_available_account(conn, body.account_id)
                if not account_row:
                    raise HTTPException(404, "account not found or disabled")
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
    """
    创建账号维度 topic 批次，并启动后台随机间隔调度。

    :param body: 批次创建参数
    :return: 包含新批次 ID 的响应字典
    """
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
        account = _get_available_account(conn, body.account_id)
        if not account:
            raise HTTPException(404, "account not found or disabled")
        placeholders = ",".join("?" for _ in topic_ids)
        topics = conn.execute(
            f"SELECT * FROM topics WHERE id IN ({placeholders}) AND deleted_at IS NULL",
            topic_ids,
        ).fetchall()
        if len(topics) != len(set(topic_ids)):
            raise HTTPException(404, "one or more topics not found")
        topics = [dict(topic) for topic in topics]
        recent_fingerprints = (
            _load_recent_topic_prompt_fingerprints(conn)
            if _should_load_topic_prompt_history(body.prompt, body.prompt_mode)
            else None
        )
    finally:
        conn.close()
    # 相似度计算是纯 CPU 工作，提前在写锁外完成，避免阻塞其他任务落库。
    random.shuffle(topics)
    prepared_items: list[tuple[dict, str]] = []
    for topic in topics:
        prompt = _resolve_topic_prompt(
            topic,
            body.prompt,
            body.prompt_mode,
            recent_fingerprints,
        )
        prepared_items.append((topic, prompt))
        if recent_fingerprints is not None:
            recent_fingerprints.append(_topic_prompt_fingerprint(prompt, topic))
    name = f"batch acc#{body.account_id} · {len(topic_ids)} topics"
    with _db_lock:
        conn = get_db()
        try:
            with conn:
                account_row = _get_available_account(conn, body.account_id)
                if not account_row:
                    raise HTTPException(404, "account not found or disabled")
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
                # prepared_items 的随机顺序由 item id 固化，便于运行追踪和恢复。
                for topic, prompt in prepared_items:
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
            "(SELECT COUNT(*) FROM task_batch_items i WHERE i.batch_id=b.id AND i.status IN ('success','failed','timeout','auth_failed')) AS done_count "
            "FROM task_batches b WHERE b.deleted_at IS NULL ORDER BY b.id DESC"
        ).fetchall()
        items = [dict(r) for r in rows]
        for item in items:
            account = conn.execute("SELECT * FROM accounts WHERE id=?", (item["account_id"],)).fetchone()
            item["passive_quota"] = _public_quota(dict(account)) if account else {}
            item["quota_policy"] = _public_quota_policy(dict(account)) if account else {}
        return items
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


@app.post("/api/task-batches/{batch_id}/pause")
@app.post("/api/task-batches/{batch_id}/stop")
def pause_task_batch(batch_id: int):
    """暂停批次调度，并停止已生成的 queued/running runs 以便后续重新投放。"""
    if not runner:
        raise HTTPException(500, "runner not ready")
    with _db_lock:
        conn = get_db()
        try:
            with conn:
                row = conn.execute(
                    "SELECT id, status FROM task_batches WHERE id=? AND deleted_at IS NULL",
                    (batch_id,),
                ).fetchone()
                if not row:
                    raise HTTPException(404, "batch not found")
                if row["status"] in ("done", "deleted"):
                    return {"ok": True, "paused_runs": 0}
                if row["status"] == "paused":
                    return {"ok": True, "paused_runs": 0}
                conn.execute(
                    "UPDATE task_batches SET status='paused', next_launch_at=NULL, "
                    "updated_at=julianday('now') WHERE id=?",
                    (batch_id,),
                )
                conn.execute(
                    "UPDATE task_batch_items SET status='paused', updated_at=julianday('now') "
                    "WHERE batch_id=? AND status IN ('queued','running','quota_wait') AND run_id IS NOT NULL",
                    (batch_id,),
                )
        finally:
            conn.close()
    conn = get_db()
    try:
        runs = conn.execute(
            "SELECT * FROM runs WHERE batch_id=? AND deleted_at IS NULL "
            "AND status IN ('queued','running','quota_wait')",
            (batch_id,),
        ).fetchall()
        run_rows = [dict(r) for r in runs]
    finally:
        conn.close()
    now = time.time()
    for run in run_rows:
        runner.persist_worker_profile(run.get("worker_container"))
        with _db_lock:
            conn = get_db()
            try:
                with conn:
                    conn.execute(
                        "UPDATE runs SET status='stopping', stop_requested_at=? WHERE id=? "
                        "AND status IN ('queued','running','quota_wait')",
                        (now, run["id"]),
                    )
            finally:
                conn.close()
        runner.cleanup(run.get("sidecar_container"), run.get("worker_container"))
        with _db_lock:
            conn = get_db()
            try:
                with conn:
                    row = conn.execute(
                        "SELECT status FROM runs WHERE id=?",
                        (run["id"],),
                    ).fetchone()
                    if row and row["status"] == "stopping":
                        conn.execute(
                            "UPDATE runs SET status='stopped', ended_at=? WHERE id=?",
                            (time.time(), run["id"]),
                        )
                    conn.execute(
                        "UPDATE task_batch_items SET status='paused', updated_at=julianday('now') "
                        "WHERE run_id=?",
                        (run["id"],),
                    )
            finally:
                conn.close()
    return {"ok": True, "paused_runs": len(run_rows)}


@app.post("/api/task-batches/{batch_id}/resume")
def resume_task_batch(batch_id: int):
    """继续已暂停的批次，把暂停项重新排队并启动后台调度。"""
    if not scheduler:
        raise HTTPException(500, "scheduler not ready")
    with _db_lock:
        conn = get_db()
        try:
            with conn:
                row = conn.execute(
                    "SELECT id, status, account_id FROM task_batches WHERE id=? AND deleted_at IS NULL",
                    (batch_id,),
                ).fetchone()
                if not row:
                    raise HTTPException(404, "batch not found")
                if row["status"] in ("done", "deleted"):
                    return {"ok": True, "resumed": False}
                if not _get_available_account(conn, int(row["account_id"])):
                    raise HTTPException(404, "account not found or disabled")
                conn.execute(
                    "UPDATE task_batch_items SET task_id=NULL, run_id=NULL, status='pending', "
                    "updated_at=julianday('now') "
                    "WHERE batch_id=? AND status IN ('paused','stopped')",
                    (batch_id,),
                )
                conn.execute(
                    "UPDATE task_batches SET status='active', next_launch_at=NULL, "
                    "updated_at=julianday('now') WHERE id=?",
                    (batch_id,),
                )
        finally:
            conn.close()
    scheduler.submit_batch(batch_id)
    return {"ok": True, "resumed": True}


# ---------- captures ----------
@app.post("/api/captures/run")
def start_capture_run(body: CaptureRunIn):
    """
    选择一个账号和 topic，启动完整 HTTP 抓包分析 run。

    :param body: 抓包 run 创建参数
    :return: run id、task id、抓包模式、权限模式和运行身份快照
    """
    if not scheduler:
        raise HTTPException(500, "scheduler not ready")
    timeout_sec = max(60, int(body.timeout_sec or 1800))
    model_override = normalize_claude_model_override(body.model_override)
    permission_mode = _resolve_capture_permission_mode(body.permission_mode)
    claude_code_version = effective_claude_code_version()
    try:
        claude_effort_level = _resolve_run_claude_effort_level(body.effort_level)
    except ValueError as e:
        raise HTTPException(400, str(e))
    conn = get_db()
    try:
        account_row = conn.execute(
            "SELECT * FROM accounts WHERE id=? AND enabled=1 AND deleted_at IS NULL",
            (body.account_id,),
        ).fetchone()
        if not account_row:
            raise HTTPException(404, "account not found or disabled")
        topic_row = conn.execute(
            "SELECT * FROM topics WHERE id=? AND deleted_at IS NULL",
            (body.topic_id,),
        ).fetchone()
        if not topic_row:
            raise HTTPException(404, "topic not found")
        account = dict(account_row)
        topic = dict(topic_row)
        recent_fingerprints = (
            _load_recent_topic_prompt_fingerprints(conn)
            if _should_load_topic_prompt_history(body.prompt, body.prompt_mode)
            else None
        )
    finally:
        conn.close()

    prompt = _resolve_topic_prompt(
        topic,
        body.prompt,
        body.prompt_mode,
        recent_fingerprints,
    )
    run_id = uuid.uuid4().hex[:12]
    with _db_lock:
        conn = get_db()
        try:
            with conn:
                cur = conn.execute(
                    "INSERT INTO tasks(topic_no, title, prompt, account_id, topic_id, "
                    "timeout_sec, repeat_n) VALUES(?,?,?,?,?,?,?)",
                    (
                        topic["no"],
                        f"[capture] {topic['title']}",
                        prompt,
                        account["id"],
                        topic["id"],
                        timeout_sec,
                        1,
                    ),
                )
                task_id = int(cur.lastrowid)
                flows_path = FLOWS_DIR / account["name"] / str(task_id) / run_id
                conn.execute(
                    "INSERT INTO runs(id, task_id, account_id, topic_id, status, "
                    "run_kind, capture_mode, capture_summary_path, capture_model_override, "
                    "capture_permission_mode, claude_code_version, claude_effort_level) "
                    "VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        run_id,
                        task_id,
                        account["id"],
                        topic["id"],
                        "queued",
                        "capture",
                        "full_http",
                        str(flows_path / "capture_index.json"),
                        model_override,
                        permission_mode,
                        claude_code_version,
                        claude_effort_level,
                    ),
                )
        finally:
            conn.close()

    task = {
        "id": task_id,
        "prompt": prompt,
        "timeout_sec": timeout_sec,
        "topic_id": topic["id"],
        "capture_full_http": True,
        "capture_mode": "full_http",
        "model_override": model_override,
        "capture_permission_mode": permission_mode,
        "claude_code_version": claude_code_version,
        "claude_effort_level": claude_effort_level,
    }
    scheduler.submit(run_id, account, task)
    return {
        "run_id": run_id,
        "task_id": task_id,
        "capture_mode": "full_http",
        "model_override": model_override,
        "permission_mode": permission_mode,
        "claude_code_version": claude_code_version,
        "claude_effort_level": claude_effort_level,
    }


# ---------- runs ----------
@app.post("/api/tasks/{tid}/run")
def run_task(tid: int):
    """
    按任务配置创建并调度一个或多个新 run。

    :param tid: tasks.id
    :return: 新建 run id 列表
    """
    conn = get_db()
    try:
        task_row = conn.execute(
            "SELECT * FROM tasks WHERE id=? AND deleted_at IS NULL",
            (tid,),
        ).fetchone()
        if not task_row:
            raise HTTPException(404, "task not found")
        task = dict(task_row)
        account_row = _get_available_account(conn, int(task["account_id"]))
        if not account_row:
            raise HTTPException(404, "account not found or disabled")
        account = dict(account_row)
    finally:
        conn.close()

    run_ids: list[str] = []
    for _ in range(int(task.get("repeat_n", 1))):
        rid = uuid.uuid4().hex[:12]
        claude_code_version = effective_claude_code_version()
        claude_effort_level = effective_runtime_effort()
        with _db_lock:
            conn = get_db()
            try:
                with conn:
                    conn.execute(
                        "INSERT INTO runs(id, task_id, account_id, batch_id, topic_id, status, "
                        "claude_code_version, claude_effort_level) VALUES(?,?,?,?,?,?,?,?)",
                        (
                            rid,
                            tid,
                            account["id"],
                            task.get("batch_id"),
                            task.get("topic_id"),
                            "queued",
                            claude_code_version,
                            claude_effort_level,
                        ),
                    )
            finally:
                conn.close()
        if not scheduler:
            raise HTTPException(500, "scheduler not ready")
        run_task_payload = dict(task)
        run_task_payload["claude_code_version"] = claude_code_version
        run_task_payload["claude_effort_level"] = claude_effort_level
        scheduler.submit(rid, account, run_task_payload)
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
        items = [dict(r) for r in rows]
        for item in items:
            account = conn.execute("SELECT * FROM accounts WHERE id=?", (item["account_id"],)).fetchone()
            item["passive_quota"] = _public_quota(dict(account)) if account else {}
            item["quota_policy"] = _public_quota_policy(dict(account), "warmup" if item["run_kind"] == "warmup" else "normal") if account else {}
        return items
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
        result = dict(row)
        account = conn.execute("SELECT * FROM accounts WHERE id=?", (result["account_id"],)).fetchone()
        result["passive_quota"] = _public_quota(dict(account)) if account else {}
        result["quota_policy"] = _public_quota_policy(dict(account), "warmup" if result["run_kind"] == "warmup" else "normal") if account else {}
        return result
    finally:
        conn.close()


@app.get("/api/runs/{rid}/transcript")
def get_transcript(rid: str):
    """
    返回 run workspace 中当前可读的 transcript 文本。

    :param rid: runs.id
    :return: 当前运行 transcript 文本响应
    """
    _require_visible_run(rid)
    p = account_runtime.run_artifact_path(rid, "transcript.log") if account_runtime else (
        WORKSPACES_DIR / rid / ".bench-transcript.log"
    )
    if not p.exists():
        raise HTTPException(404, "transcript not yet available")
    return FileResponse(p, media_type="text/plain")


@app.get("/api/runs/{rid}/files")
def list_workspace(rid: str):
    """
    列出 run workspace 中的产物文件树。

    :param rid: runs.id
    :return: 文件/目录条目列表
    """
    _require_visible_run(rid)
    base = WORKSPACES_DIR / rid
    if not base.exists():
        raise HTTPException(404)
    out: list[dict] = []
    for p in sorted(base.rglob("*")):
        rel = p.relative_to(base)
        if str(rel).startswith(".bench-") or (account_runtime and rel.parts[0] in {
                ".claude-home", ".cc2api-oauth-refresh-request.json", ".cc2api-oauth-refresh-result.json"}):
            continue
        if p.is_dir():
            out.append({"path": str(rel), "type": "dir"})
        else:
            out.append({"path": str(rel), "type": "file", "size": p.stat().st_size})
    return out


@app.get("/api/runs/{rid}/stats")
def get_stats(rid: str):
    """
    聚合 run 的 token、请求数和采集可用性。

    :param rid: runs.id
    :return: token / request 聚合结果及 available / usage_available 状态
    """
    _require_visible_run(rid)
    base = FLOWS_DIR
    # flows 目录按 account/task/run 分层，扫描所有匹配
    matches = list(base.rglob(f"{rid}/stats.jsonl"))
    # 兼容入口是固定链接；按 run 目录列出分代文件，排除续聊/API，避免扫描账号 HOME。
    for directory in base.glob(f"*/*/{rid}"):
        if (directory / "stats.jsonl").is_file():
            matches.append(directory / "stats.jsonl")
        matches.extend(sorted((directory / "executions").glob("*/stats.jsonl")))
    matches = list({path.resolve(): path for path in matches}.values())
    if not matches:
        session_stats = _aggregate_claude_session_usage(rid)
        return {
            "tokens_in": session_stats["tokens_in"],
            "tokens_out": session_stats["tokens_out"],
            "requests": session_stats["requests"],
            "errors": 0,
            "available": bool(session_stats["usage_available"]),
            "usage_available": bool(session_stats["usage_available"]),
            "source": "claude_session" if session_stats["usage_available"] else "none",
        }
    tokens_in = tokens_out = errors = 0
    request_ids: set[str] = set()
    response_ids: set[str] = set()
    fallback_requests = 0
    usage_available = False
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
            if not isinstance(u, dict):
                u = {}
            if isinstance(u, dict) and ("input_tokens" in u or "output_tokens" in u):
                usage_available = True
            tokens_in += _usage_input_tokens(u)
            tokens_out += int(u.get("output_tokens") or 0)
    requests = len(request_ids | response_ids) + fallback_requests
    source = "sidecar"
    if not usage_available:
        session_stats = _aggregate_claude_session_usage(rid)
        if session_stats["usage_available"]:
            tokens_in = int(session_stats["tokens_in"])
            tokens_out = int(session_stats["tokens_out"])
            usage_available = True
            source = "claude_session"
    return {
        "tokens_in": tokens_in,
        "tokens_out": tokens_out,
        "requests": requests,
        "errors": errors,
        "available": requests > 0 or usage_available,
        "usage_available": usage_available,
        "source": source,
    }


@app.get("/api/runs/{rid}/capture")
def get_capture(rid: str):
    """
    返回抓包 run 的索引和文件列表。

    :param rid: runs.id
    :return: 脱敏后的抓包索引与文件元信息
    """
    _require_visible_run(rid)
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
    if (run.get("run_kind") or "normal") != "capture":
        raise HTTPException(404, "capture data not available for this run")

    try:
        capture_dirs = _resolve_capture_flows_dirs(run)
    except ValueError:
        capture_dirs = None
    flows_dir = capture_dirs[0] if capture_dirs else FLOWS_DIR / "_missing" / rid
    index_path = Path(run["capture_summary_path"]) if run.get("capture_summary_path") else flows_dir / "capture_index.json"
    index = _read_capture_index(index_path)
    # 分代索引只读聚合，原始 HTTP/flow 保持原目录，原平铺索引仍可读取。
    indexes = [index] if index.get("available") else []
    for path in sorted(flows_dir.glob("executions/*/capture_index.json")):
        item = _read_capture_index(path)
        if item.get("available"):
            indexes.append(item)
    for directory in sorted(flows_dir.glob("continue-*")):
        for path in sorted(directory.glob("executions/*/capture_index.json")):
            item = _read_capture_index(path)
            if item.get("available"):
                indexes.append(item)
    if indexes:
        index = dict(indexes[-1], entries=[entry for item in indexes for entry in item.get("entries", [])])
        index["total_flows"] = len(index["entries"])
        index["cc_versions"] = sorted({version for item in indexes for version in item.get("cc_versions", [])})
        index["updated_at"] = max(float(item.get("updated_at") or 0) for item in indexes)
    return {
        "run_id": rid,
        "mode": run.get("capture_mode") or "full_http",
        "model_override": run.get("capture_model_override"),
        "permission_mode": _resolve_capture_permission_mode(
            run.get("capture_permission_mode")
        ),
        "claude_code_version": run.get("claude_code_version"),
        "claude_effort_level": run.get("claude_effort_level"),
        "available": bool(index.get("available")),
        "flows_dir": str(flows_dir),
        "index_path": str(index_path),
        "files": _capture_files(flows_dir),
        "index": index,
    }


@app.post("/api/runs/{rid}/stop")
def stop_run(rid: str):
    """请求停止 queued/running run，并尽量先回写运行时凭据。"""
    if not runner:
        raise HTTPException(500, "运行器尚未就绪")
    warmup_binding_id: Optional[int] = None
    conn = get_db()
    try:
        row = conn.execute(
            "SELECT * FROM runs WHERE id=? AND deleted_at IS NULL",
            (rid,),
        ).fetchone()
        if not row:
            raise HTTPException(404, "运行记录不存在")
        run = dict(row)
        if run.get("run_kind") == "warmup":
            account_row = conn.execute(
                "SELECT cc2api_account_id FROM accounts WHERE id=?",
                (run["account_id"],),
            ).fetchone()
            if account_row:
                warmup_binding_id = account_row["cc2api_account_id"]
    finally:
        conn.close()
    if run["status"] not in ("queued", "running", "quota_wait"):
        raise HTTPException(400, f"运行 {rid} 当前不是 queued/running 状态")
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
    if warmup_scheduler:
        warmup_scheduler.handle_run_terminal(rid, warmup_binding_id)
    return {"ok": True}


@app.delete("/api/runs/{rid}")
def delete_run(rid: str):
    """
    软删除终态 run；workspace、flow 和 transcript 保留。

    :param rid: runs.id
    :return: 删除成功标记
    """
    with _db_lock:
        conn = get_db()
        try:
            with conn:
                row = conn.execute(
                    "SELECT status FROM runs WHERE id=? AND deleted_at IS NULL",
                    (rid,),
                ).fetchone()
                if not row:
                    raise HTTPException(404, "运行记录不存在")
                if row["status"] in ("queued", "running", "stopping", "quota_wait"):
                    raise HTTPException(409, f"运行 {rid} 仍处于 {row['status']} 状态，请先停止并收口")
                cur = conn.execute(
                    "UPDATE runs SET deleted_at=? WHERE id=? AND deleted_at IS NULL",
                    (time.time(), rid),
                )
                if cur.rowcount == 0:
                    raise HTTPException(404, "运行记录不存在")
        finally:
            conn.close()
    return {"ok": True}


@app.post("/api/runs/{rid}/continue/start")
def continue_run_start(rid: str):
    """
    启动 run 继续对话会话，前端随后连接返回的 WebSocket。

    :param rid: runs.id
    :return: 继续会话 ID、Claude session ID 和 WebSocket 路径
    """
    if not continue_manager:
        raise HTTPException(500, "继续对话管理器尚未就绪")
    conn = get_db()
    try:
        run_row = conn.execute(
            "SELECT * FROM runs WHERE id=? AND deleted_at IS NULL",
            (rid,),
        ).fetchone()
        if not run_row:
            raise HTTPException(404, "运行记录不存在")
        run = dict(run_row)
        if run["status"] not in _TERMINAL_RUN_STATUSES:
            raise HTTPException(400, f"运行 {rid} 尚未结束")
        account_row = conn.execute(
            "SELECT * FROM accounts WHERE id=? AND enabled=1 AND deleted_at IS NULL",
            (run["account_id"],),
        ).fetchone()
        if not account_row:
            raise HTTPException(404, "账号不存在或已停用")
        account = dict(account_row)
    finally:
        conn.close()
    try:
        _ensure_run_claude_code_version(run)
        _ensure_run_claude_effort_level(run)
    except ValueError as e:
        raise HTTPException(400, str(e))
    with _oauth_owner_lock(str(account["name"])):
        conn = get_db()
        try:
            current_account_row = _get_available_account(conn, int(account["id"]))
            if not current_account_row:
                raise HTTPException(404, "账号不存在或已停用")
            account = dict(current_account_row)
        finally:
            conn.close()
        try:
            session = continue_manager.start(run, account)
        except ValueError as e:
            raise HTTPException(400, str(e))
        except Exception as e:
            raise HTTPException(500, f"启动继续对话会话失败：{e}")
    return {
        "session_id": session.sid,
        "run_id": session.run_id,
        "claude_session_id": session.session_id,
        "ws_path": f"/api/run-continue/ws/{session.sid}",
        "status": session.status,
        "quota": _public_quota(account),
    }


@app.websocket("/api/run-continue/ws/{sid}")
async def continue_run_ws(websocket: WebSocket, sid: str):
    """
    按原 run 权限模式恢复 Claude 会话，并通过 PTY 双向连接浏览器 xterm。

    :param websocket: 浏览器 WebSocket 连接
    :param sid: continue 会话 ID
    :return: None
    """
    if V3_ENABLED and not _v3_websocket_authorized(websocket):
        await websocket.close(code=4401)
        return
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
    loop = asyncio.get_running_loop()
    closed = asyncio.Event()
    bridge = {"raw": None, "exec_id": None, "generation": -1}
    session.connected = True
    auth_tail = ""
    auth_refresh_task: Optional[asyncio.Task] = None

    def close_bridge() -> None:
        """断开旧 PTY，返回 None；不保留用户输入。"""
        raw = bridge["raw"]
        bridge.update(raw=None, exec_id=None, generation=-1)
        if raw is not None:
            try:
                raw.close()
            except Exception:
                pass

    def open_bridge() -> None:
        """锁内为当前代次恢复 Claude exec；返回 None。"""
        with session.guard_lock:
            if session.status != "running" or continue_manager.get(sid) is not session:
                return
            cwd = "/workspace"
            command = ["sh", "-lc", "if [ -f /workspace/.claude.json ] && [ ! -f \"$HOME/.claude.json\" ]; then "
                 "cp /workspace/.claude.json \"$HOME/.claude.json\"; fi; "
                 "if [ -n \"${CLAUDE_MODEL_OVERRIDE:-}\" ]; then "
                 "claude --permission-mode \"$CLAUDE_PERMISSION_MODE\" --resume \"$CONTINUE_SESSION_ID\" --model \"$CLAUDE_MODEL_OVERRIDE\"; "
                 "else claude --permission-mode \"$CLAUDE_PERMISSION_MODE\" --resume \"$CONTINUE_SESSION_ID\"; fi"]
            actual_worker = session.worker_id
            if account_runtime:
                job = account_runtime.job_for_container(session.worker_id)
                cwd = job["cwd"]
                actual_worker = job["row"]["container_id"]
                command[2] = command[2].replace("/workspace", cwd)
                command = ["setsid", "--wait", "sh", "-c", f"echo $$ > /run/v3/job-{job['handle']}.pid; exec " + shlex.join(account_runtime.cli_command(["sh", "-c", command[2]]))]
            exec_id = api.exec_create(
                actual_worker,
                command,
                stdin=True, tty=True, user="root" if account_runtime else WORKER_USER,
                environment=_claude_exec_env(not account_runtime or job["network_inspection_mode"] != "passthrough", {
                    "TERM": "xterm-256color", "COLUMNS": "120", "LINES": "36",
                    **({"PATH": f"/cli/{job['version']}/node_modules/.bin:/usr/local/bin:/usr/bin:/bin"} if account_runtime else {}),
                    **({"NETWORK_INSPECTION_MODE": job["network_inspection_mode"]} if account_runtime else {}),
                    **(account_runtime.execution_environment(job["row"]) if account_runtime else {}),
                    "CONTINUE_SESSION_ID": session.session_id, "CLAUDE_PERMISSION_MODE": session.permission_mode,
                    **({"CLAUDE_MODEL_OVERRIDE": session.run.get("execution_model") or session.run.get("capture_model_override")}
                       if session.run.get("execution_model") or session.run.get("capture_model_override") else {}),
                }), workdir=cwd,
            )["Id"]
            if account_runtime:
                account_runtime.register_exec(session.worker_id, exec_id)
            sock = api.exec_start(exec_id, detach=False, tty=True, stream=False, socket=True, demux=False)
            raw = getattr(sock, "_sock", None) or sock
            raw.setblocking(False)
            bridge.update(raw=raw, exec_id=exec_id, generation=session.generation)

    async def recover_managed_oauth_once(generation: int) -> None:
        """仅向原代次交互执行回写 cc2api 凭据，等待和关闭时禁止重试。"""
        conn = get_db()
        try:
            row = _get_available_account(conn, session.account_id)
            account = dict(row) if row else None
        finally:
            conn.close()
        if not account or account.get("cc2api_account_id") is None:
            return
        try:
            if session.status != "running" or session.generation != generation:
                return
            if quota_guard and quota_guard.snapshot(account)["blocked"]:
                return
            await asyncio.to_thread(_sync_bound_account_credentials, account, 600, True)
            def sync_worker() -> None:
                """锁内同步原代次凭据，返回 None。"""
                with session.guard_lock:
                    if session.status == "running" and session.generation == generation:
                        continue_manager.runner.sync_managed_credentials_to_worker(session.worker_id)
            if session.status != "running" or session.generation != generation:
                return
            await asyncio.to_thread(sync_worker)
            if bridge["raw"] is not None:
                await asyncio.to_thread(continue_manager.send_input, session, generation, bridge["raw"], b"\x03")
                await asyncio.sleep(1)
                await asyncio.to_thread(continue_manager.send_input, session, generation, bridge["raw"],
                    "检测到认证失败，cc2api 已刷新凭据。请重试刚才失败的请求；若仍失败请停止。\r".encode())
        except Exception as exc:
            if websocket.client_state == WebSocketState.CONNECTED:
                await websocket.send_text(json.dumps({"type": "error", "msg": _redact_cc2api_error(exc)}))

    async def pump_container_to_ws() -> None:
        """跟随会话代次替换 PTY，等待时保持 WS。返回 None。"""
        nonlocal auth_tail, auth_refresh_task
        last_state = None
        try:
            while not closed.is_set():
                if continue_manager.get(sid) is not session or session.status == "closed":
                    if session.quota.get("message"):
                        await websocket.send_text(json.dumps({"type": "error", "msg": session.quota["message"]}))
                    break
                if session.status == "running" and bridge["generation"] != session.generation:
                    close_bridge()
                    auth_tail = ""
                    if auth_refresh_task and not auth_refresh_task.done():
                        auth_refresh_task.cancel()
                    auth_refresh_task = None
                    await asyncio.to_thread(open_bridge)
                event = {"type": "quota_state", "status": session.status,
                         "message": session.quota.get("message", ""),
                         "resume_at": session.quota.get("resume_at"), "generation": session.generation}
                signature = json.dumps(event)
                if signature != last_state:
                    await websocket.send_text(signature)
                    last_state = signature
                if session.status == "quota_wait":
                    close_bridge()
                    await asyncio.sleep(0.2)
                    continue
                raw = bridge["raw"]
                if raw is None:
                    await asyncio.sleep(0.2)
                    continue
                try:
                    data = await asyncio.wait_for(loop.sock_recv(raw, 4096), timeout=1)
                except asyncio.TimeoutError:
                    continue
                except (OSError, ValueError):
                    if session.status == "quota_wait":
                        continue
                    raise
                if not data:
                    # 额度暂停清理容器可能先于下一次轮询；只在同代次仍运行时结束 WS。
                    if session.status == "quota_wait" or bridge["generation"] != session.generation:
                        continue
                    break
                await websocket.send_bytes(data)
                auth_tail = (auth_tail + data.decode("utf-8", errors="ignore"))[-6000:]
                if (auth_refresh_task is None and "account_on_hold" not in auth_tail and "on hold" not in auth_tail.lower()
                        and any(marker in auth_tail for marker in ("Please run /login", "API Error: 401", "Invalid authentication credentials", "OAuth token has expired"))):
                    auth_refresh_task = asyncio.create_task(recover_managed_oauth_once(session.generation))
        except Exception as exc:
            if websocket.client_state == WebSocketState.CONNECTED:
                await websocket.send_text(json.dumps({"type": "error", "msg": f"继续会话执行失败：{type(exc).__name__}"}))
        finally:
            closed.set()

    async def pump_ws_to_container() -> None:
        """后端同时拦截文本和二进制输入，等待期没有重放队列。返回 None。"""
        try:
            while not closed.is_set():
                msg = await websocket.receive()
                if msg["type"] == "websocket.disconnect":
                    break
                data = msg.get("bytes")
                text = msg.get("text")
                if text:
                    try:
                        event = json.loads(text)
                    except ValueError:
                        event = {"type": "input", "data": text}
                    if not isinstance(event, dict):
                        continue
                    if event.get("type") == "resize":
                        if bridge["exec_id"] and session.status == "running":
                            try:
                                api.exec_resize(bridge["exec_id"], height=int(event.get("rows") or 36), width=int(event.get("cols") or 120))
                            except Exception:
                                pass
                        continue
                    if event.get("type") == "input":
                        data = str(event.get("data") or "").encode()
                if data and bridge["raw"] is not None:
                    await asyncio.to_thread(continue_manager.send_input, session, bridge["generation"], bridge["raw"], data)
        except WebSocketDisconnect:
            pass
        finally:
            closed.set()

    output = asyncio.create_task(pump_container_to_ws())
    incoming = asyncio.create_task(pump_ws_to_container())
    try:
        await asyncio.wait((output, incoming), return_when=asyncio.FIRST_COMPLETED)
    finally:
        session.connected = False
        closed.set()
        for task in (output, incoming, auth_refresh_task):
            if task and not task.done():
                task.cancel()
        await asyncio.gather(output, incoming, return_exceptions=True)
        close_bridge()
        await asyncio.to_thread(continue_manager.cleanup, sid)
        if websocket.client_state == WebSocketState.CONNECTED:
            await websocket.close()


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
            rows = await asyncio.to_thread(list_runs, 100)
            payload = json.dumps(rows, default=str, ensure_ascii=False)
            if payload != last_payload:
                last_payload = payload
                yield {"event": "runs", "data": payload}
            await asyncio.sleep(1)
    return EventSourceResponse(gen())


def _v3_websocket_authorized(websocket: WebSocket) -> bool:
    """同时验证服务来源、浏览器会话及短期路径票据。"""
    secret = os.environ.get("V3_INTERNAL_TOKEN", "")
    actual = websocket.headers.get("authorization", "").removeprefix("Bearer ")
    if len(secret) < 32 or not secrets.compare_digest(secret, actual):
        return False
    cookie = websocket.cookies.get(_SESSION_COOKIE, "")
    if not _verify_session_token(cookie):
        return False
    try:
        ticket = websocket.query_params.get("ticket", "")
        raw = base64.urlsafe_b64decode(ticket + "=" * (-len(ticket) % 4)).decode()
        path, expires, digest, signature = raw.split("|")
        expected = hmac.new(_SESSION_SECRET.encode(), f"{path}|{expires}|{digest}".encode(), hashlib.sha256).hexdigest()
        return (int(expires) >= time.time() and int(expires) <= time.time() + 120
            and path == websocket.url.path
            and digest == hashlib.sha256(cookie.encode()).hexdigest()
            and secrets.compare_digest(signature, expected))
    except (ValueError, UnicodeError):
        return False


@app.post("/internal/v3/session")
def v3_session_grant():
    """受控管理桥交换独立 HttpOnly 会话，不返回管理密码。"""
    if not V3_ENABLED:
        raise HTTPException(404)
    response = JSONResponse({"ok": True})
    response.set_cookie(_SESSION_COOKIE, _make_session_token(WEBUI_USER), httponly=True,
        samesite="strict", path="/runtime", max_age=_SESSION_TTL)
    return response


@app.get("/internal/v3/session/verify")
def v3_session_verify(request: Request):
    """验证浏览器会话；仅内部桥可调用。"""
    if not V3_ENABLED or not _verify_session_token(request.cookies.get(_SESSION_COOKIE, "")):
        raise HTTPException(401)
    return {"ok": True}


@app.post("/api/terminal-ticket")
def v3_terminal_ticket(request: Request, body: dict):
    """签发一分钟且绑定会话及具体 WS 路径的票据。"""
    cookie = request.cookies.get(_SESSION_COOKIE, "")
    if not V3_ENABLED or not _verify_session_token(cookie):
        raise HTTPException(401)
    path = body.get("path", "")
    if not re.fullmatch(r"/api/(?:accounts/login/ws|run-continue/ws)/[a-f0-9]{12}", path):
        raise HTTPException(400, "终端路径不合法")
    payload = f"{path}|{int(time.time()) + 60}|{hashlib.sha256(cookie.encode()).hexdigest()}"
    signature = hmac.new(_SESSION_SECRET.encode(), payload.encode(), hashlib.sha256).hexdigest()
    return {"ticket": base64.urlsafe_b64encode(f"{payload}|{signature}".encode()).decode().rstrip("=")}


@app.post("/internal/v3/quiesce/{account_id}")
def v3_quiesce(account_id: int, body: dict):
    """凭配置事务的门禁证明收口固定实例，避免配置修改后仍发送旧请求。

    :param account_id: cc2api 账号 ID
    :param body: 当前 owner 与 generation
    :return: 已确认空闲并停止的结果
    """
    if not account_runtime:
        raise HTTPException(404)
    connection = get_db()
    try:
        account = connection.execute("SELECT * FROM accounts WHERE cc2api_account_id=? AND deleted_at IS NULL", (account_id,)).fetchone()
    finally:
        connection.close()
    if not account:
        return {"ok": True}
    account = dict(account)
    with account_runtime._account_lock(account):
        snapshot = cc2api_client._request("GET", f"/admin/runtime/accounts/{account_id}/lease")
        lease = snapshot.get("lease")
        if not lease or not lease.get("exclusive", True) or lease["owner"] != body.get("owner") or lease["generation"] != body.get("generation") or snapshot["active"]:
            raise HTTPException(409, "配置门禁证明无效")
        row = account_runtime._row(account["name"], account["id"])
        with account_runtime.lock:
            busy = row["environment_id"] in account_runtime.jobs
        if busy or account_runtime._running_sender_active(row):
            raise HTTPException(409, "账号环境仍有工作或发送连接")
        if row["container_id"]:
            try:
                account_runtime._container(row).stop(timeout=5)
            except NotFound:
                pass
        account_runtime._update(row, state="stopped")
    return {"ok": True}


@app.get("/internal/v3/transport/{account_id}")
def v3_transport(account_id: int):
    """解析唯一绑定账号并返回受限发送实例，浏览器无法直接调用。"""
    if not account_runtime:
        raise HTTPException(404)
    connection = get_db()
    try:
        rows = connection.execute("SELECT * FROM accounts WHERE cc2api_account_id=? AND deleted_at IS NULL",
            (account_id,)).fetchall()
    finally:
        connection.close()
    if len(rows) != 1:
        raise HTTPException(409, "账号没有唯一的 v3 环境绑定")
    try:
        return account_runtime.transport(dict(rows[0]), effective_claude_code_version())
    except (ValueError, RuntimeError):
        raise HTTPException(503, "账号环境未就绪或需要维护")


@app.get("/api/environments")
def v3_environments() -> list[dict]:
    """列出未删除账号和登录草稿的环境，排除服务秘密和凭据。

    :return: 按名称排序的环境状态及固化基础参数
    """
    if not account_runtime:
        return []
    connection = get_db()
    try:
        # 已删除账号的环境仅保留历史；未绑定草稿和未删除的停用账号仍需可见。
        rows = [dict(row) for row in connection.execute(
            "SELECT e.* FROM account_environments e "
            "WHERE e.account_id IS NULL OR EXISTS ("
            "SELECT 1 FROM accounts a WHERE a.id=e.account_id AND a.deleted_at IS NULL) "
            "ORDER BY e.name"
        )]
    finally:
        connection.close()
    for row in rows:
        blocker = account_runtime.reprofile_blocker(row)
        row["fingerprint"] = json.loads(row.pop("fingerprint_json"))
        with account_runtime.lock:
            row["busy"] = row["environment_id"] in account_runtime.jobs
        try:
            with ExitStack() as locks:
                # 列表只取可立即获得的一致快照，不能等待登录或同步持有的维护锁。
                for guard in (_oauth_owner_lock(row["name"]), _profile_lock(row["name"]),
                        account_runtime.environment_lock(row["environment_id"])):
                    if not guard.acquire(blocking=False):
                        raise RuntimeBusy("账号正在维护，设备身份待核对")
                    locks.callback(guard.release)
                identity = account_runtime.read_cli_identity(row, effective_claude_code_version())
            row["identity_status"] = ("已确认 CLI 本地设备身份" if ":config.userID" in identity["source"]
                else "已观测 CLI 设备身份")
        except ValueError as error:
            row["identity_status"] = str(error)
        row["can_reprofile"] = blocker is None
        row["reprofile_message"] = blocker
        row["runtime_release"] = account_runtime.release_id
        row["cli_versions"] = sorted(path.name for path in (account_runtime._root(row) / "cli").glob("*/.ready") for path in [path.parent])
    return rows


@app.post("/api/environments/{environment_id}/maintenance")
def v3_environment_maintenance(environment_id: str, body: dict):
    """空闲维护或对账待确认的重授权，不中断正式运行。

    :param environment_id: 不可变环境 ID
    :param body: 维护操作
    :return: 成功结果；占用或归属异常返回冲突
    """
    if not account_runtime:
        raise HTTPException(404)
    connection = get_db()
    try:
        environment = connection.execute("SELECT COALESCE(a.name,e.name) AS name FROM account_environments e "
            "LEFT JOIN accounts a ON a.id=e.account_id WHERE e.environment_id=?", (environment_id,)).fetchone()
    finally:
        connection.close()
    if not environment:
        raise HTTPException(404, "环境不存在")
    try:
        # 对账会镜像已提交凭据，必须与提交/绑定共用 owner → profile → environment 锁顺序。
        with _oauth_owner_lock(environment["name"]):
            with _profile_lock(environment["name"]):
                account_runtime.maintenance(environment_id, body.get("operation", ""))
        # 该方法自行领取 owner 锁；不可在上面的非重入锁内调用。
        if body.get("operation") == "reconcile" and login_manager:
            login_manager.cleanup_reconciled(environment_id)
    except (ValueError, RuntimeError) as exc:
        if body.get("operation") == "reprofile":
            raise HTTPException(409, str(exc)) from None
        raise HTTPException(409, "环境有活动请求、归属冲突或需进一步对账")
    except ConnectionError:
        raise HTTPException(503, "对账结果尚未确认，请稍后重试") from None
    return {"ok": True}


# ---------- 静态 WebUI ----------
class NoStoreStaticFiles(StaticFiles):
    """为 WebUI 静态文件统一附加禁用缓存响应头。"""

    async def get_response(self, path: str, scope) -> Response:
        """
        返回静态文件响应，并阻止浏览器复用旧前端资源。

        :param path: StaticFiles 解析到的相对路径
        :param scope: ASGI 请求上下文
        :return: 带 no-store 响应头的静态文件响应
        """
        response = await super().get_response(path, scope)
        response.headers["Cache-Control"] = "no-store"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
        return response


if WEBUI_DIR.exists():
    app.mount("/", NoStoreStaticFiles(directory=str(WEBUI_DIR), html=True), name="ui")
