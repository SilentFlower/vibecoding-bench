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
import sqlite3
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from collections import deque
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal, Optional, Sequence

import docker
from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict
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
    os.environ.get("CLAUDE_CODE_VERSION") or "2.1.260",
    "CLAUDE_CODE_VERSION",
) or "2.1.260"
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
_SESSION_COOKIE = "vb_session"
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

    def list_accounts(self) -> list[dict]:
        """
        分页读取全部 cc2api 账号。

        :return: cc2api Account object 列表
        """
        page = 1
        accounts: list[dict] = []
        while True:
            data = self._request("GET", f"/admin/accounts?page={page}&page_size=100")
            rows = data.get("data")
            if not isinstance(rows, list):
                raise ValueError("cc2api 账号列表响应无效")
            accounts.extend(row for row in rows if isinstance(row, dict))
            total_pages = int(data.get("total_pages") or 1)
            if page >= total_pages:
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


cc2api_client = Cc2ApiClient(
    CC2API_BASE_URL,
    CC2API_ADMIN_PASSWORD,
    CC2API_REQUEST_TIMEOUT_SEC,
)


def _read_bench_profile_identity(account_name: str) -> dict:
    """
    读取同步 cc2api 所需的 bench OAuth profile 字段。

    :param account_name: bench accounts.name
    :return: 经过结构校验的身份与凭据字段
    """
    profile_dir = PROFILES_DIR / account_name
    credentials_path = profile_dir / ".credentials.json"
    top_config_path = profile_dir / ".claude.json"
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
    return _resolve_and_sync_cc2api_credentials(
        str(account["name"]),
        int(cc2api_account_id),
        min_validity_seconds,
        force_refresh,
    )


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
  claude_code_version TEXT,
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
            _ensure_column(conn, "runs", "claude_code_version", "TEXT")
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
_CAT_RE = re.compile(r"^##\s+[一二三四五六七八九十百零\d]+、(.+?)（")
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
    return conn.execute(
        "SELECT * FROM accounts WHERE id=? AND enabled=1 AND deleted_at IS NULL",
        (account_id,),
    ).fetchone()


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

_NATURAL_TOPIC_PROMPT_CANDIDATE_COUNT = 12
_NATURAL_TOPIC_PROMPT_HISTORY_LIMIT = 64
_NATURAL_TOPIC_PROMPT_NGRAM_SIZE = 4

_NATURAL_TOPIC_PROMPT_STYLE_KEYWORDS = (
    ("data_ai", ("AI 集成", "AI Agent", "数据可视化", "数据运营", "Dashboard")),
    ("creative", ("小游戏", "内容创作", "教育", "创意")),
    (
        "engineering",
        ("命令行", "自动化与脚本", "开发者工具", "硬件", "边缘", "安全", "运维"),
    ),
    (
        "product",
        ("Web", "浏览器插件", "协作", "商业", "行业", "团队知识", "社区运营"),
    ),
)

_NATURAL_TOPIC_PROMPT_STYLE_OPENERS = {
    "engineering": (
        "想做个「{title}」，属于{category}这类工具。",
        "这次要实现的是「{title}」，方向归在{category}。",
        "手头需要一个{category}项目：「{title}」。",
        "先做一个能用的「{title}」，场景是{category}。",
    ),
    "product": (
        "想把一个{category}方向的想法做成「{title}」。",
        "这次准备落地「{title}」，它属于{category}场景。",
        "有个产品需求叫「{title}」，主要面向{category}。",
        "先做「{title}」的首版，定位是{category}。",
    ),
    "data_ai": (
        "需要做一个「{title}」，用于{category}方向的数据或智能处理。",
        "这次的数据或智能项目是「{title}」，归在{category}。",
        "想把「{title}」这个{category}需求先跑通。",
        "准备实现一个{category}项目，名字是「{title}」。",
    ),
    "creative": (
        "想做一个可以实际体验的「{title}」，属于{category}。",
        "这次先把「{title}」这个{category}创意做出来。",
        "有个{category}方向的小项目：「{title}」。",
        "准备实现「{title}」，先做成能演示的{category}作品。",
    ),
    "generic": (
        "我想实现「{title}」，项目分类是{category}。",
        "这次要做的项目叫「{title}」，属于{category}。",
        "有个需求想直接落地：「{title}」（{category}）。",
        "先完成一个「{title}」，场景归在{category}。",
    ),
}

_NATURAL_TOPIC_PROMPT_REQUIREMENTS = (
    "主要要解决的是：{description}",
    "核心需求大致是：{description}",
    "希望它能覆盖这些事情：{description}",
    "具体想实现的能力包括：{description}",
    "需求可以概括为：{description}",
)

_NATURAL_TOPIC_PROMPT_DELIVERIES = (
    "请先在当前工作区把核心流程真正跑通，交付一个可以实际运行的首版。",
    "代码直接落在现有目录，先做到主要流程可以实际使用。",
    "先把能启动演示的版本完成在这个工作区里。",
    "以当前项目中能够跑起来的首版为交付。",
    "请在手头目录完成可运行版本，优先保证核心流程闭环。",
)

_NATURAL_TOPIC_PROMPT_REPORTS = (
    "完成后附上启动命令、实际验证过的场景，以及控制范围时做出的取舍。",
    "最后写清怎么运行、哪些输入输出已经自测，还有哪些能力被有意留到后续。",
    "交付时说明运行步骤、检查结果和实现中的关键权衡。",
    "收尾时给出使用命令、测试情况，并解释首版舍弃了什么。",
    "做完后告诉我如何把它跑起来、实际检查了哪些路径，以及范围是怎样控制的。",
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
    category = str(topic.get("category") or "未分类").strip()
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
        normalized = normalized.replace(value, "topic内容")
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
            f"题目：{title}\n"
            f"分类：{category}\n"
            f"描述：{description}\n\n"
            "请在当前目录下实现一个可运行的 MVP。\n"
            "完成后请说明启动方式、验证方式和主要取舍。"
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
    if timezone not in _TZ_POOL:
        raise ValueError(
            "invalid account timezone: must be one of "
            + ", ".join(_TZ_POOL)
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
    :return: 显式时区或账号名派生时区
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

# ============== Docker 运行器 ==============
class Runner:
    """封装 sidecar + worker 的生命周期"""

    def __init__(self) -> None:
        self.client = docker.from_env()

    def start_run(self, run_id: str, account: dict, task: dict) -> tuple[str, str]:
        """
        启动一次 run 的 sidecar 和 worker。

        :param run_id: runs.id
        :param account: accounts 表行
        :param task: 调度任务 payload，包含 run 创建时的版本快照
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
            # 抓包 run 是协议诊断路径，必须独立于页面运行时覆盖值；
            # 普通 / 批量 run 才读取 SQLite 中的动态思考预算配置。
            "CLAUDE_CODE_EFFORT_LEVEL": (
                CLAUDE_CODE_EFFORT_LEVEL if capture_full_http else effective_runtime_effort()
            ),
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
        elif not capture_full_http:
            # 普通 / 批量 run 复用抓包的 --model 一次性覆盖链路；
            # 抓包 run 留空时必须沿用自身默认模型，不能被页面或环境全局配置带偏。
            worker_env["CLAUDE_MODEL_OVERRIDE"] = effective_runtime_model()

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
        if not worker_id:
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
        worker = self.client.containers.get(worker_id)
        result = worker.wait()
        return int(result.get("StatusCode", -1))

    def read_worker_status(self, run_id: str) -> dict:
        """
        读取 worker 写入的轻量状态文件，用于区分普通失败和认证失败。

        :param run_id: runs.id
        :return: 状态字典；文件缺失或格式异常时返回空 dict
        """
        path = WORKSPACES_DIR / run_id / ".bench-status.json"
        if not path.exists():
            return {}
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        return data if isinstance(data, dict) else {}

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

    def watch_managed_oauth_refresh(
        self,
        run_id: str,
        account: dict,
        stop_event: threading.Event,
    ) -> None:
        """
        监听 managed worker 的单次 401 刷新请求并交给 cc2api 处理。

        :param run_id: 当前 runs.id
        :param account: 已绑定 cc2api 的 bench accounts 行
        :param stop_event: worker 收口后用于停止 watcher 的事件
        :return: None
        """
        workspace = WORKSPACES_DIR / run_id
        request_path = workspace / ".cc2api-oauth-refresh-request.json"
        result_path = workspace / ".cc2api-oauth-refresh-result.json"
        while not stop_event.wait(1):
            if not request_path.exists():
                continue
            try:
                _sync_bound_account_credentials(account, 600, force_refresh=True)
                _write_json_atomically(result_path, {"ok": True})
            except Exception as exc:
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
                    "CLAUDE_CODE_EFFORT_LEVEL": CLAUDE_CODE_EFFORT_LEVEL,
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
        用账号代理启动临时 worker，经 sidecar 网络查询 OAuth usage API。

        :param account: accounts 表行
        :return: 额度查询结果
        """
        if not account.get("upstream_socks5_host"):
            raise ValueError("account has no upstream proxy configured")
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
const claudeCodeVersion = process.env.CLAUDE_CODE_VERSION || '2.1.260';

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
      const response = await fetch(url, options);
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
      if (attempt === 5) break;
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
            worker_id,
            ["sh", "-lc", script],
            stdout=True,
            stderr=True,
            user=WORKER_USER,
            environment=_claude_exec_env(True),
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

    def _exec_oauth_refresh_probe(self, worker_id: str) -> dict:
        """
        在临时 worker 内使用 refreshToken 刷新 accessToken。

        :param worker_id: refresh worker 容器 ID
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
const claudeCodeVersion = process.env.CLAUDE_CODE_VERSION || '2.1.260';

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
        ex = api.exec_create(
            worker_id,
            ["sh", "-lc", script],
            stdout=True,
            stderr=True,
            user=WORKER_USER,
            environment=_claude_exec_env(True, {
                "OAUTH_REFRESH_BUFFER_SEC": str(OAUTH_REFRESH_BUFFER_SEC),
            }),
            workdir=WORKER_HOME,
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
                 "proxy", "profile_dir", "force_reauth", "committed")

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
    ) -> LoginSession:
        """
        启动账号 OAuth 登录容器。

        :param name: 账号 profile 名
        :param proxy: 上游代理配置
        :param force_reauth: 是否使用一次性 profile 副本强制重授权
        :param timezone: 登录 worker 显式时区；None 表示按账号名自动派生
        :return: 登录会话对象
        """
        if not _ACC_NAME_RE.match(name):
            raise ValueError(
                "invalid account name: must match [a-zA-Z0-9_-]+"
            )
        tz = _effective_account_timezone(name, timezone)
        with self._lock:
            if name in self._name_locks:
                raise ValueError(
                    f"login session already in progress for '{name}'; "
                    f"cancel it first"
                )
            sid = uuid.uuid4().hex[:12]
            self._name_locks[name] = sid

        try:
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
        if s.force_reauth:
            shutil.rmtree(s.profile_dir.parent, ignore_errors=True)
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
        """停止并清理继续对话容器，同时尽量回写本地配置。"""
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
    base = WORKSPACES_DIR / run_id / ".claude-home" / "projects"
    if not base.exists():
        return None
    files = [p for p in base.rglob("*.jsonl") if p.is_file()]
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
    base = WORKSPACES_DIR / run_id / ".claude-home" / "projects"
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
    for path in sorted(p for p in base.rglob("*") if p.is_file()):
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

            active_runs: list[str] = []
            for idx, item_row in enumerate(items):
                current = self._get_batch_status(batch_id)
                if current != "active":
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
                task_id, claude_code_version = created
                task = {
                    "id": task_id,
                    "prompt": item["prompt"],
                    "timeout_sec": batch["timeout_sec"],
                    "batch_id": batch_id,
                    "topic_id": item["topic_id"],
                    "claude_code_version": claude_code_version,
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
    ) -> Optional[tuple[int, str]]:
        """
        为批次 item 创建兼容旧 runs 的 task + run。

        :param batch: task_batches 行
        :param account: accounts 行
        :param item: task_batch_items 行
        :param run_id: 新 run id
        :return: `(task_id, claude_code_version)`；批次已暂停或 item 已被其他线程处理时返回 None
        """
        claude_code_version = effective_claude_code_version()
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
                        "claude_code_version) VALUES(?,?,?,?,?,?,?)",
                        (
                            run_id,
                            task_id,
                            account["id"],
                            batch["id"],
                            item["topic_id"],
                            "queued",
                            claude_code_version,
                        ),
                    )
                    conn.execute(
                        "UPDATE task_batch_items SET task_id=?, run_id=?, status='queued', "
                        "updated_at=julianday('now') WHERE id=?",
                        (task_id, run_id, item["id"]),
                    )
                    return task_id, claude_code_version
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
                        "WHERE batch_id=? AND status IN ('pending','paused','queued','running')",
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
        managed_refresh_stop = threading.Event()
        managed_refresh_thread: Optional[threading.Thread] = None
        try:
            flows_path = FLOWS_DIR / account["name"] / str(task["id"]) / run_id
            capture_full_http = bool(task.get("capture_full_http"))
            initial_state = self._get_run_state(run_id)
            if not initial_state or initial_state.get("deleted_at") is not None:
                return
            if initial_state["status"] in ("stopping", "stopped"):
                self._update_batch_item_for_run(run_id, "stopped")
                return
            with _oauth_owner_lock(str(account["name"])):
                conn = get_db()
                try:
                    current_account_row = _get_available_account(conn, int(account["id"]))
                    if not current_account_row:
                        self._update(
                            run_id,
                            status="failed",
                            error="账号不存在或已停用",
                            ended_at=time.time(),
                        )
                        self._update_batch_item_for_run(run_id, "failed")
                        return
                    account = dict(current_account_row)
                finally:
                    conn.close()
                if account.get("cc2api_account_id") is not None:
                    timeout_sec = max(60, int(task.get("timeout_sec") or 1800))
                    try:
                        _sync_bound_account_credentials_locked(account, timeout_sec + 600)
                    except Exception as exc:
                        error = _redact_cc2api_error(exc)
                        self._update(
                            run_id,
                            status="failed",
                            error=error,
                            ended_at=time.time(),
                        )
                        self._update_batch_item_for_run(run_id, "failed")
                        if warmup_scheduler:
                            warmup_scheduler.handle_run_sync_failure(run_id, account, exc)
                        return
                self._update(
                    run_id,
                    status="running",
                    started_at=time.time(),
                    workspace_dir=str(WORKSPACES_DIR / run_id),
                    flows_dir=str(flows_path),
                    capture_summary_path=str(flows_path / "capture_index.json") if capture_full_http else None,
                )
                if warmup_scheduler:
                    warmup_scheduler.handle_run_started(run_id)
                try:
                    sid, wid = self.runner.start_run(run_id, account, task)
                except Exception as exc:
                    self._update(
                        run_id,
                        status="failed",
                        error=str(exc),
                        ended_at=time.time(),
                    )
                    self._update_batch_item_for_run(run_id, "failed")
                    return
                self._update(run_id, sidecar_container=sid, worker_container=wid)
            try:
                if account.get("cc2api_account_id") is not None:
                    managed_refresh_thread = threading.Thread(
                        target=self.runner.watch_managed_oauth_refresh,
                        args=(run_id, account, managed_refresh_stop),
                        daemon=True,
                    )
                    managed_refresh_thread.start()
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
                elif exit_code == 42:
                    status = "auth_failed"
                else:
                    status = "failed"
                worker_status = self.runner.read_worker_status(run_id)
                error = worker_status.get("error") if isinstance(worker_status.get("error"), str) else None
                status_hint = worker_status.get("status")
                if status_hint == "auth_failed" and status not in ("stopped", "success"):
                    status = "auth_failed"
                    error = error or "OAuth 认证失败"
                update_fields = {
                    "status": status,
                    "exit_code": exit_code,
                    "ended_at": time.time(),
                }
                if error and status not in ("success", "stopped"):
                    update_fields["error"] = error
                self._update(run_id, **update_fields)
                self._update_batch_item_for_run(run_id, status)
            except Exception as e:
                run_state = self._get_run_state(run_id)
                status = "stopped" if run_state and run_state["status"] in ("stopping", "stopped") else "failed"
                self._update(run_id, status=status, error=str(e), ended_at=time.time())
                self._update_batch_item_for_run(run_id, status)
            finally:
                managed_refresh_stop.set()
                if managed_refresh_thread and managed_refresh_thread.is_alive():
                    managed_refresh_thread.join(timeout=2)
                self.runner.persist_worker_profile(wid)
                self.runner.cleanup(sid, wid)
        finally:
            if warmup_scheduler:
                warmup_scheduler.handle_run_terminal(
                    run_id,
                    account.get("cc2api_account_id"),
                )
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
        account = self._claim_account(account_id, require_due)
        if not account:
            return {"started": False, "run_id": None}
        try:
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
        run_id, task_id, claude_code_version = created
        task = {
            "id": task_id,
            "prompt": prompt,
            "timeout_sec": 1800,
            "topic_id": topic["id"],
            "claude_code_version": claude_code_version,
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
                        account.get("cc2api_account_id") is None
                        or account.get("warmup_last_run_id") != run_id
                    ):
                        return
                    if (
                        expected_cc2api_account_id is not None
                        and int(account["cc2api_account_id"])
                        != int(expected_cc2api_account_id)
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
                        "WHERE id=? AND cc2api_account_id=?",
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
                "AND warmup_enabled=1 AND cc2api_account_id IS NOT NULL "
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
                        "AND warmup_enabled=1 AND cc2api_account_id IS NOT NULL",
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
                        "AND status IN ('queued','running','stopping') "
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
    ) -> Optional[tuple[str, int, str]]:
        """
        为养号创建 task 和 run，并保存已生成的 prompt。

        :param account: 已认领的账号行
        :param topic: 本次养号选择的 topic 行
        :param prompt: 已生成且将实际下发给 worker 的 prompt
        :return: `(run_id, task_id, claude_code_version)`；账号状态失效或已有运行时返回 None
        """
        run_id = uuid.uuid4().hex[:12]
        claude_code_version = effective_claude_code_version()
        with _db_lock:
            conn = get_db()
            try:
                with conn:
                    current = conn.execute(
                        "SELECT * FROM accounts WHERE id=? AND enabled=1 AND deleted_at IS NULL "
                        "AND warmup_enabled=1 AND cc2api_account_id=?",
                        (account["id"], account["cc2api_account_id"]),
                    ).fetchone()
                    if not current:
                        return None
                    active = conn.execute(
                        "SELECT id FROM runs WHERE account_id=? AND run_kind='warmup' "
                        "AND status IN ('queued','running','stopping') LIMIT 1",
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
                        "claude_code_version) VALUES(?,?,?,?,?,?,?)",
                        (
                            run_id,
                            task_id,
                            account["id"],
                            topic["id"],
                            "queued",
                            "warmup",
                            claude_code_version,
                        ),
                    )
                    conn.execute(
                        "UPDATE accounts SET warmup_last_run_id=?, warmup_last_status='queued', "
                        "warmup_last_error=NULL WHERE id=?",
                        (run_id, account["id"]),
                    )
                    return run_id, task_id, claude_code_version
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
                        "WHERE id=? AND cc2api_account_id=?",
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
                        "WHERE id=? AND cc2api_account_id=?",
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


@asynccontextmanager
async def lifespan(app: FastAPI):
    global runner, scheduler, login_manager, continue_manager, oauth_refresh_scheduler, warmup_scheduler
    init_db()
    PROFILES_DIR.mkdir(parents=True, exist_ok=True)
    FLOWS_DIR.mkdir(parents=True, exist_ok=True)
    WORKSPACES_DIR.mkdir(parents=True, exist_ok=True)
    CA_DIR.mkdir(parents=True, exist_ok=True)
    runner = Runner()
    scheduler = Scheduler(runner)
    login_manager = LoginManager(runner.client)
    continue_manager = ContinueManager(runner)
    oauth_refresh_scheduler = OAuthRefreshScheduler(runner)
    warmup_scheduler = WarmupScheduler(scheduler)
    # 清掉上次进程残留的 login 容器，避免重启后僵尸容器堆积
    login_manager.cleanup_stale()
    continue_manager.cleanup_stale()
    oauth_refresh_scheduler.cleanup_stale()
    oauth_refresh_scheduler.start()
    warmup_scheduler.start()
    try:
        yield
    finally:
        warmup_scheduler.stop()
        oauth_refresh_scheduler.stop()


app = FastAPI(title="vibecoding-bench", lifespan=lifespan)
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
    """账号 cc2api 绑定与养号随机间隔配置。"""

    cc2api_account_id: int
    enabled: bool = False
    interval_min_hours: int = 3
    interval_max_hours: int = 5


def _oauth_owner_transition_blocker(account: dict) -> Optional[str]:
    """
    查找会让 AT/RT 所有权切换不安全的活跃工作。

    :param account: accounts 表行
    :return: 阻塞原因；账号空闲时返回 None
    """
    conn = get_db()
    try:
        active_run = conn.execute(
            "SELECT id, status FROM runs WHERE account_id=? "
            "AND status IN ('queued','running','stopping') ORDER BY created_at LIMIT 1",
            (account["id"],),
        ).fetchone()
    finally:
        conn.close()
    if active_run:
        return f"run {active_run['id']} 当前为 {active_run['status']}"
    if continue_manager and continue_manager.has_active_account(int(account["id"])):
        return "账号存在活跃的继续对话会话"
    if login_manager and login_manager.has_active_name(str(account["name"])):
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


@app.post("/api/accounts/{aid}/cc2api/sync")
def sync_account_to_cc2api(aid: int):
    """
    把单个 bench 账号安全创建或关联到 cc2api。

    :param aid: bench accounts.id
    :return: 绑定结果和脱敏 cc2api 账号摘要
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
                    matched = _find_cc2api_account_for_profile(profile, cc2api_accounts)
                    created = matched is None
                    if matched is None:
                        matched = cc2api_client.create_account({
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
                        })
                if not _cc2api_account_is_active_oauth(matched):
                    raise ValueError("匹配到的 cc2api 账号不是 active OAuth 账号")
                _validate_cc2api_identity(profile, matched)
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
                            conn.execute(
                                "UPDATE accounts SET cc2api_account_id=?, warmup_enabled=0, "
                                "warmup_next_run_at=NULL, warmup_last_status='off', warmup_last_error=NULL "
                                "WHERE id=?",
                                (cc2api_account_id, aid),
                            )
                except sqlite3.IntegrityError:
                    raise HTTPException(409, "该 cc2api 账号已绑定其他 bench 账号")
                finally:
                    conn.close()
    return {
        "ok": True,
        "created": created,
        "cc2api_account": _cc2api_account_summary(matched),
    }


@app.put("/api/accounts/{aid}/warmup")
def update_account_warmup(aid: int, body: WarmupConfigIn):
    """
    显式绑定 cc2api 账号并保存养号随机间隔。

    :param aid: bench accounts.id
    :param body: cc2api 账号 ID、开关和小时区间
    :return: 保存后的调度状态
    """
    low = int(body.interval_min_hours)
    high = int(body.interval_max_hours)
    if low < 1 or high < 1 or low > 720 or high > 720:
        raise HTTPException(400, "养号间隔必须为 1-720 小时")
    if high < low:
        raise HTTPException(400, "最大养号间隔不能小于最小间隔")
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
            binding_changes = account.get("cc2api_account_id") != body.cc2api_account_id
            if binding_changes:
                _require_oauth_owner_transition_idle(account)

            enabled = bool(body.enabled)
            if binding_changes or enabled:
                try:
                    profile = _read_bench_profile_identity(account["name"])
                    cc2api_accounts = cc2api_client.list_accounts()
                    selected = next(
                        (
                            item
                            for item in cc2api_accounts
                            if int(item.get("id") or 0) == int(body.cc2api_account_id)
                        ),
                        None,
                    )
                    if not selected or not _cc2api_account_is_active_oauth(selected):
                        raise ValueError("选择的 cc2api 账号不可用")
                    _validate_cc2api_identity(profile, selected)
                    _require_cc2api_binding_available(aid, int(body.cc2api_account_id))
                    _resolve_and_sync_cc2api_credentials(
                        account["name"],
                        int(body.cc2api_account_id),
                        2400,
                    )
                except ConnectionError as exc:
                    raise HTTPException(502, _redact_cc2api_error(exc))
                except ValueError as exc:
                    raise HTTPException(409, _redact_cc2api_error(exc))

            next_run_at = time.time() + random.uniform(low * 3600, high * 3600) if enabled else None
            with _db_lock:
                conn = get_db()
                try:
                    with conn:
                        current = _get_available_account(conn, aid)
                        if not current:
                            raise HTTPException(404, "账号不存在或已停用")
                        active = conn.execute(
                            "SELECT id, status FROM runs WHERE account_id=? AND run_kind='warmup' "
                            "AND status IN ('queued','running','stopping') LIMIT 1",
                            (aid,),
                        ).fetchone()
                        conn.execute(
                            "UPDATE accounts SET cc2api_account_id=?, warmup_enabled=?, "
                            "warmup_interval_min_hours=?, warmup_interval_max_hours=?, "
                            "warmup_next_run_at=?, warmup_last_status=?, warmup_last_error=NULL, "
                            "warmup_auth_failures=0 WHERE id=?",
                            (
                                int(body.cc2api_account_id),
                                int(enabled),
                                low,
                                high,
                                None if active else next_run_at,
                                active["status"] if active and enabled else ("scheduled" if enabled else "off"),
                                aid,
                            ),
                        )
                except sqlite3.IntegrityError:
                    raise HTTPException(409, "该 cc2api 账号已绑定其他 bench 账号")
                finally:
                    conn.close()
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
                    "SELECT * FROM accounts WHERE id=? AND enabled=1 AND deleted_at IS NULL "
                    "AND cc2api_account_id IS NOT NULL",
                    (aid,),
                ).fetchone()
                if not row:
                    raise HTTPException(404, "已绑定账号不存在或已停用")
                account = dict(row)
                active = conn.execute(
                    "SELECT id, status FROM runs WHERE account_id=? AND run_kind='warmup' "
                    "AND status IN ('queued','running','stopping') LIMIT 1",
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
        if current_binding is not None:
            try:
                _sync_bound_account_credentials_locked(current, OAUTH_REFRESH_BUFFER_SEC)
                raw = cc2api_client.refresh_usage(int(current_binding))
                _sync_bound_account_credentials_locked(current, OAUTH_REFRESH_BUFFER_SEC)
                return _format_quota_result(raw)
            except ConnectionError as exc:
                raise HTTPException(502, _redact_cc2api_error(exc))
            except ValueError as exc:
                raise HTTPException(400, _redact_cc2api_error(exc))
        try:
            return runner.query_quota(current)
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


@app.post("/api/accounts/login/start")
def login_start(body: LoginStartIn):
    """启动一个 OAuth 引导会话；前端拿到 session_id 后开 WS 拿 PTY"""
    if not login_manager:
        raise HTTPException(500, "登录管理器尚未就绪")
    with _oauth_owner_lock(body.name):
        conn = get_db()
        try:
            bound = conn.execute(
                "SELECT id FROM accounts WHERE name=? AND deleted_at IS NULL "
                "AND cc2api_account_id IS NOT NULL",
                (body.name,),
            ).fetchone()
        finally:
            conn.close()
        if bound:
            raise HTTPException(409, "账号已绑定 cc2api，请先解绑后再重新授权")
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
                        1,
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
                        "upstream_socks5_pass=?, timezone=?, enabled=1, deleted_at=NULL WHERE name=?",
                        (
                            f"profiles/{name}",
                            proxy_scheme,
                            body.upstream_socks5_host,
                            body.upstream_socks5_port,
                            body.upstream_socks5_user,
                            body.upstream_socks5_pass,
                            timezone,
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
    """

    model_config = ConfigDict(protected_namespaces=())

    account_id: int
    topic_id: int
    prompt: Optional[str] = None
    prompt_mode: TopicPromptMode = "canonical"
    timeout_sec: int = 1800
    model_override: Optional[str] = None


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
                    "WHERE batch_id=? AND status IN ('queued','running') AND run_id IS NOT NULL",
                    (batch_id,),
                )
        finally:
            conn.close()
    conn = get_db()
    try:
        runs = conn.execute(
            "SELECT * FROM runs WHERE batch_id=? AND deleted_at IS NULL "
            "AND status IN ('queued','running')",
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
                        "AND status IN ('queued','running')",
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
    :return: run id、task id 和抓包模式
    """
    if not scheduler:
        raise HTTPException(500, "scheduler not ready")
    timeout_sec = max(60, int(body.timeout_sec or 1800))
    model_override = normalize_claude_model_override(body.model_override)
    claude_code_version = effective_claude_code_version()
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
                    "claude_code_version) VALUES(?,?,?,?,?,?,?,?,?,?)",
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
                        claude_code_version,
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
        "claude_code_version": claude_code_version,
    }
    scheduler.submit(run_id, account, task)
    return {
        "run_id": run_id,
        "task_id": task_id,
        "capture_mode": "full_http",
        "model_override": model_override,
        "claude_code_version": claude_code_version,
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
        with _db_lock:
            conn = get_db()
            try:
                with conn:
                    conn.execute(
                        "INSERT INTO runs(id, task_id, account_id, batch_id, topic_id, status, "
                        "claude_code_version) VALUES(?,?,?,?,?,?,?)",
                        (
                            rid,
                            tid,
                            account["id"],
                            task.get("batch_id"),
                            task.get("topic_id"),
                            "queued",
                            claude_code_version,
                        ),
                    )
            finally:
                conn.close()
        if not scheduler:
            raise HTTPException(500, "scheduler not ready")
        run_task_payload = dict(task)
        run_task_payload["claude_code_version"] = claude_code_version
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
    """
    返回 run workspace 中当前可读的 transcript 文本。

    :param rid: runs.id
    :return: `.bench-transcript.log` 文本响应
    """
    _require_visible_run(rid)
    p = WORKSPACES_DIR / rid / ".bench-transcript.log"
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
        if str(rel).startswith(".bench-"):
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
    return {
        "run_id": rid,
        "mode": run.get("capture_mode") or "full_http",
        "model_override": run.get("capture_model_override"),
        "claude_code_version": run.get("claude_code_version"),
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
    if run["status"] not in ("queued", "running"):
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
                if row["status"] in ("queued", "running", "stopping"):
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
        if account.get("cc2api_account_id") is not None:
            try:
                _sync_bound_account_credentials_locked(account, 2400)
            except ConnectionError as exc:
                raise HTTPException(502, _redact_cc2api_error(exc))
            except ValueError as exc:
                raise HTTPException(400, _redact_cc2api_error(exc))
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
    auth_tail = ""
    auth_refresh_task: Optional[asyncio.Task] = None

    async def recover_managed_oauth_once() -> None:
        """首次检测到 continue 401 时交给 cc2api 刷新并提示 Claude 重试。"""
        conn = get_db()
        try:
            account_row = _get_available_account(conn, session.account_id)
            account = dict(account_row) if account_row else None
        finally:
            conn.close()
        if not account or account.get("cc2api_account_id") is None:
            return
        try:
            await asyncio.to_thread(
                _sync_bound_account_credentials,
                account,
                600,
                True,
            )
            await asyncio.to_thread(
                continue_manager.runner.sync_managed_credentials_to_worker,
                session.worker_id,
            )
            raw.send(b"\x03")
            await asyncio.sleep(1)
            raw.send(
                "检测到认证失败，cc2api 已刷新凭据。请重试刚才失败的请求；若仍失败请停止。\r".encode(
                    "utf-8"
                )
            )
        except Exception as exc:
            if websocket.client_state == WebSocketState.CONNECTED:
                await websocket.send_bytes(
                    f"\r\n[bench] cc2api 凭据刷新失败：{_redact_cc2api_error(exc)}\r\n".encode(
                        "utf-8"
                    )
                )

    async def pump_container_to_ws():
        """worker PTY → ws"""
        nonlocal auth_tail, auth_refresh_task
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
                auth_tail = (auth_tail + data.decode("utf-8", errors="ignore"))[-6000:]
                if auth_refresh_task is None and any(
                    marker in auth_tail
                    for marker in (
                        "Please run /login",
                        "API Error: 401",
                        "Invalid authentication credentials",
                        "OAuth token has expired",
                    )
                ):
                    auth_refresh_task = asyncio.create_task(recover_managed_oauth_once())
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
        if auth_refresh_task and not auth_refresh_task.done():
            auth_refresh_task.cancel()
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
