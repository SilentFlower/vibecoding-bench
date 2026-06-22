#!/usr/bin/env bash
# =======================================================================
# Worker 入口脚本
# 模式：
#   WORKER_MODE=task  （默认）跑题：注入 prompt → 等最终 assistant 回复 → 抓 transcript
#   WORKER_MODE=login OAuth 引导：装 CA 后空转，等 orchestrator 用
#                     docker exec 启动 `claude auth login` 走 PTY 桥到 WebUI
# 必备环境变量（task 模式）：
#   TASK_PROMPT     题目 prompt（字面文本）
#   RUN_ID          本次运行的唯一 ID（用于会话名 / 日志归档）
#   TIMEOUT_SEC     超时（秒），默认 1800
#   TIMEOUT_WRAPUP_SEC  临近超时前自动注入收尾提示的秒数，默认 600；0 表示关闭
#   OAUTH_401_PROFILE_WAIT_SEC  检测到 401 后等待后台刷新 profile 的秒数，默认 90
#   CLAUDE_API_STALL_WATCHDOG_SEC  API 连接错误后无进展多久自动中断续跑，默认 400；0 表示关闭
# 挂载约定：
#   task 模式：
#     /mnt/profile  账号 ~/.claude profile（rw，仅回写关键配置文件）
#     /etc/mitm     MITM CA 目录
#     /workspace    claude 工作目录（每个 run 独立）
#   login 模式：
#     /home/node/.claude 直接挂宿主 data/profiles/<name>/（rw）
#     /etc/mitm     同上
# 退出码（task 模式）：
#   0    Claude session JSONL 以稳定的最终 assistant 文本结束
#   124  达到 TIMEOUT_SEC 超时
#   42   OAuth / 401 认证失败
#   其它 启动失败
# =======================================================================
set -euo pipefail

WORKER_MODE="${WORKER_MODE:-task}"
CLAUDE_CODE_VERSION="${CLAUDE_CODE_VERSION:-2.1.185}"
CLAUDE_CODE_EFFORT_LEVEL="${CLAUDE_CODE_EFFORT_LEVEL:-max}"
log() { echo "[entrypoint $(date +%H:%M:%S)] $*"; }
CLAUDE_USER=node
CLAUDE_HOME=/home/node
CLAUDE_DIR="$CLAUDE_HOME/.claude"

write_default_settings() {
  # settings.json 既要补齐默认值，又不能覆盖 Claude 自己写入的隐藏 gate。
  # 用 jq 递归合并：已有字段保留，默认字段补齐；同名字段以默认值为准。
  node - "$CLAUDE_CODE_EFFORT_LEVEL" > /tmp/default-settings.json <<'JS'
const effort = process.argv[2] || 'max';
process.stdout.write(`${JSON.stringify({
  env: {
    CLAUDE_CODE_EFFORT_LEVEL: effort,
  },
  permissions: {
    defaultMode: 'bypassPermissions',
    allow: [
      'Bash', 'BashOutput', 'Edit', 'Glob', 'Grep',
      'KillShell', 'NotebookEdit', 'Read', 'SlashCommand',
      'Task', 'TodoWrite', 'WebFetch', 'WebSearch', 'Write',
    ],
    deny: [],
  },
  skipDangerousModePermissionPrompt: true,
  autoMemoryEnabled: false,
  theme: 'dark',
  model: 'opus[1m]',
}, null, 2)}\n`);
JS
  if [ -f "$CLAUDE_DIR/settings.json" ]; then
    jq -s '(.[0] | del(.hooks, .statusLine)) * .[1]' "$CLAUDE_DIR/settings.json" /tmp/default-settings.json > "$CLAUDE_DIR/settings.json.tmp" \
      && mv "$CLAUDE_DIR/settings.json.tmp" "$CLAUDE_DIR/settings.json"
  else
    cp /tmp/default-settings.json "$CLAUDE_DIR/settings.json"
  fi
}

patch_top_config_gates() {
  # 这些 gate 属于顶层 ~/.claude.json，不属于 ~/.claude/settings.json。
  # 旧 profile 缺字段时，交互 TUI 会重走 onboarding 或 bypassPermissions 确认页。
  local path="$CLAUDE_HOME/.claude.json"
  if [ ! -f "$path" ]; then
    return 0
  fi
  jq '. + {
    "hasCompletedOnboarding": true,
    "bypassPermissionsModeAccepted": true
  }' "$path" > "$path.tmp" && mv "$path.tmp" "$path"
}

handle_claude_startup_gates() {
  # Claude 2.x 的首次启动主题菜单和 bypassPermissions 免责声明都可能拦在首屏。
  # prompt 注入前只检测当前可见 pane；不能用 scrollback，否则菜单清掉后
  # 旧文本还在历史里，会误判为仍卡在 first-run。
  local theme_sent=0
  local bypass_sent=0
  local clear_ticks=0
  local pane
  for i in $(seq 1 75); do
    if [ -f /tmp/claude-exited ]; then
      return 1
    fi
    pane="$(tmux capture-pane -t "$SESSION" -p 2>/dev/null || true)"
    if printf '%s' "$pane" | grep -q "Choose the text style that looks best with your terminal"; then
      if [ "$theme_sent" -eq 0 ]; then
        log "Detected Claude first-run theme menu; accepting default dark theme"
        tmux send-keys -t "$SESSION" Enter
        theme_sent=1
      fi
      clear_ticks=0
      sleep 1
      continue
    fi
    if printf '%s' "$pane" | grep -q "Claude Code running in Bypass Permissions mode"; then
      if [ "$bypass_sent" -eq 0 ]; then
        log "Detected Claude bypassPermissions disclaimer; accepting bypass permissions mode"
        tmux send-keys -t "$SESSION" Down Enter
        bypass_sent=1
      fi
      clear_ticks=0
      sleep 1
      continue
    fi
    if printf '%s' "$pane" | grep -Eiq "Browser didn't open|Paste code here|Use the url below to sign in|claude\.ai/oauth|org:create_api_key|setup-token|Choose how you want to log in"; then
      log "WARN: Claude opened an auth/onboarding gate; refusing to inject task prompt"
      echo "auth/onboarding gate" > /tmp/claude-startup-gate
      return 1
    fi
    if [ "$theme_sent" -eq 1 ] || [ "$bypass_sent" -eq 1 ]; then
      clear_ticks=$((clear_ticks + 1))
      if [ "$clear_ticks" -ge 3 ]; then
        log "Claude startup gates cleared"
        return 0
      fi
      sleep 1
      continue
    fi
    if [ "$i" -lt 20 ]; then
      sleep 1
      continue
    fi
    return 0
  done
  if [ "$theme_sent" -eq 1 ] || [ "$bypass_sent" -eq 1 ]; then
    log "WARN: Claude startup gate did not clear; skip prompt injection"
    return 1
  fi
  return 0
}

check_claude_auth_status() {
  # task 模式不消耗 refreshToken；这里只做本地 credentials 形态检查，
  # 真正 AT 刷新统一交给 orchestrator 后台刷新器。即将过期 / 已过期
  # 不在启动阶段拒绝，避免撞上后台定时刷新窗口时还没运行就失败。
  local credentials_path="$CLAUDE_DIR/.credentials.json"
  if ! node - "$credentials_path" <<'JS' >/tmp/claude-auth-status.json 2>/tmp/claude-auth-status.err
const fs = require('fs');
const path = process.argv[2];

function fail(message) {
  console.error(message);
  process.exit(1);
}

let data;
try {
  data = JSON.parse(fs.readFileSync(path, 'utf8'));
} catch (error) {
  fail(`读取 .credentials.json 失败: ${error.message}`);
}
const oauth = data && data.claudeAiOauth;
if (!oauth || typeof oauth !== 'object') {
  fail('.credentials.json 缺少 claudeAiOauth');
}
if (typeof oauth.accessToken !== 'string' || !oauth.accessToken) {
  fail('OAuth accessToken 为空，请等待后台刷新器或重新登录账号');
}
if (typeof oauth.expiresAt !== 'number') {
  fail('OAuth expiresAt 缺失或格式错误');
}
process.stdout.write(JSON.stringify({
  loggedIn: true,
  expiresAt: oauth.expiresAt,
  expiresInSec: Math.floor((oauth.expiresAt - Date.now()) / 1000),
}) + '\n');
JS
  then
    {
      echo "[entrypoint] Claude profile OAuth access token 不可用，拒绝在 task 模式打开登录流"
      echo "--- local auth status stdout ---"
      cat /tmp/claude-auth-status.json 2>/dev/null || true
      echo "--- local auth status stderr ---"
      cat /tmp/claude-auth-status.err 2>/dev/null || true
    } > /workspace/.bench-transcript.log
    persist_runtime_claude_state
    log "Claude local auth status check failed; not injecting task prompt into login flow"
    exit 1
  fi
}

wait_for_sidecar_dns() {
  # sidecar 的 unbound 配的是通配 forward-zone "."，这里验证通用 resolver
  # 已经能工作，而不是为每个业务目标域名维护白名单。
  local probe_host="${DNS_READY_HOST:-example.com}"
  log "Verifying sidecar DNS from worker namespace..."
  for i in $(seq 1 10); do
    # getent 在启动瞬间可能受 NSS/IPv6 查询策略影响;这里用 Node 做 A 记录探测,
    # 与 Claude Code 的运行时更接近,也避免给 worker 镜像额外安装 dig。
    if DNS_READY_HOST="$probe_host" node -e "require('dns').resolve4(process.env.DNS_READY_HOST || 'example.com', (err, addresses) => process.exit(!err && addresses && addresses.length ? 0 : 1))" >/dev/null 2>&1; then
      log "Sidecar network ready (DNS ok after ${i}s)"
      return 0
    fi
    sleep 1
  done
  log "WARN: DNS resolver still not ready after worker fallback wait; claude may fail"
  DNS_READY_HOST="$probe_host" node -e "require('dns').resolve4(process.env.DNS_READY_HOST || 'example.com', (err, addresses) => process.exit(!err && addresses && addresses.length ? 0 : 1))" >/dev/null 2>&1 || log "WARN: unresolved DNS probe host: $probe_host"
  return 1
}

persist_runtime_claude_state() {
  # task 模式里 Claude 跑在 $HOME 的运行时副本中；OAuth token 统一由
  # orchestrator 后台刷新器维护，run 结束不能把旧 credentials 覆盖回 profile。
  if [ ! -d /mnt/profile ] || [ ! -w /mnt/profile ]; then
    return 0
  fi
  if [ -f "$CLAUDE_HOME/.claude.json" ]; then
    patch_top_config_gates
    cp "$CLAUDE_HOME/.claude.json" /mnt/profile/.claude.json || true
  fi
  if [ -f "$CLAUDE_DIR/settings.json" ]; then
    cp "$CLAUDE_DIR/settings.json" /mnt/profile/settings.json || true
  fi
  chown "$CLAUDE_USER:$CLAUDE_USER" \
    /mnt/profile/.claude.json \
    /mnt/profile/settings.json 2>/dev/null || true
}

write_bench_status() {
  local status="$1"
  local error="$2"
  local api_stall_recoveries="${3:-}"
  node - "$status" "$error" "$api_stall_recoveries" > /workspace/.bench-status.json.tmp <<'JS'
const status = process.argv[2] || 'failed';
const error = process.argv[3] || '';
const payload = {status, error};
const apiStallRecoveriesRaw = process.argv[4] || '';
const apiStallRecoveries = Number(apiStallRecoveriesRaw);
if (apiStallRecoveriesRaw !== '' && Number.isFinite(apiStallRecoveries)) {
  payload.api_stall_recoveries = apiStallRecoveries;
}
process.stdout.write(`${JSON.stringify(payload, null, 2)}\n`);
JS
  mv /workspace/.bench-status.json.tmp /workspace/.bench-status.json
}

sync_profile_credentials_once() {
  # 后台刷新器只更新账号 profile；运行中的 Claude 读本地副本。
  # 这里单向同步 profile -> 本地，避免 run 结束时旧 credentials 覆盖新 token。
  local src="/mnt/profile/.credentials.json"
  local dst="$CLAUDE_DIR/.credentials.json"
  [ -f "$src" ] || return 1
  set +e
  node - "$src" "$dst" "$CLAUDE_USER" <<'JS'
const fs = require('fs');
const path = require('path');
const src = process.argv[2];
const dst = process.argv[3];

function readJson(file) {
  return JSON.parse(fs.readFileSync(file, 'utf8'));
}

let source;
try {
  source = readJson(src);
} catch {
  process.exit(1);
}
if (!source || typeof source !== 'object' || !source.claudeAiOauth) {
  process.exit(1);
}
let current = null;
try {
  current = readJson(dst);
} catch {}
const sourceOauth = source.claudeAiOauth || {};
const currentOauth = current && current.claudeAiOauth ? current.claudeAiOauth : {};
if (
  currentOauth.accessToken === sourceOauth.accessToken &&
  currentOauth.expiresAt === sourceOauth.expiresAt
) {
  process.exit(2);
}
fs.mkdirSync(path.dirname(dst), {recursive: true});
const tmp = `${dst}.tmp.${process.pid}`;
fs.writeFileSync(tmp, `${JSON.stringify(source, null, 2)}\n`, 'utf8');
fs.renameSync(tmp, dst);
JS
  local rc=$?
  set -e
  if [ "$rc" -eq 0 ]; then
    chown "$CLAUDE_USER:$CLAUDE_USER" "$dst" 2>/dev/null || true
    chmod 600 "$dst" 2>/dev/null || true
    log "Synced refreshed OAuth credentials from profile"
    return 0
  fi
  return "$rc"
}

credential_fingerprint() {
  local path="${1:-$CLAUDE_DIR/.credentials.json}"
  node - "$path" <<'JS'
const crypto = require('crypto');
const fs = require('fs');
const path = process.argv[2];
let data;
try {
  data = JSON.parse(fs.readFileSync(path, 'utf8'));
} catch {
  process.exit(1);
}
const oauth = data && data.claudeAiOauth;
if (!oauth || typeof oauth !== 'object') {
  process.exit(1);
}
const payload = JSON.stringify({
  accessToken: typeof oauth.accessToken === 'string' ? oauth.accessToken : '',
  expiresAt: typeof oauth.expiresAt === 'number' ? oauth.expiresAt : 0,
});
process.stdout.write(crypto.createHash('sha256').update(payload).digest('hex'));
JS
}

local_credentials_fresh_enough() {
  # 401 后只有拿到明显越过刷新缓冲区的新 token 才直接重试；临期 token
  # 继续等待后台刷新器，避免用同一份旧 credentials 立即二次失败。
  local buffer_sec="${OAUTH_REFRESH_BUFFER_SEC:-600}"
  node - "$CLAUDE_DIR/.credentials.json" "$buffer_sec" <<'JS' >/dev/null 2>&1
const fs = require('fs');
const path = process.argv[2];
const bufferMs = Number(process.argv[3] || '600') * 1000;
let data;
try {
  data = JSON.parse(fs.readFileSync(path, 'utf8'));
} catch {
  process.exit(1);
}
const oauth = data && data.claudeAiOauth;
if (
  !oauth ||
  typeof oauth !== 'object' ||
  typeof oauth.accessToken !== 'string' ||
  !oauth.accessToken ||
  typeof oauth.expiresAt !== 'number'
) {
  process.exit(1);
}
process.exit(oauth.expiresAt > Date.now() + bufferMs ? 0 : 1);
JS
}

wait_for_profile_credentials_refresh() {
  local base_fingerprint="${1:-}"
  local wait_sec="${OAUTH_401_PROFILE_WAIT_SEC:-90}"
  case "$wait_sec" in
    ''|*[!0-9]*) wait_sec=90 ;;
  esac
  if [ "$wait_sec" -le 0 ] 2>/dev/null; then
    return 1
  fi
  local deadline=$(( $(date +%s) + wait_sec ))
  while [ "$(date +%s)" -lt "$deadline" ]; do
    sync_profile_credentials_once >/dev/null 2>&1 || true
    if local_credentials_fresh_enough; then
      local current_fingerprint=""
      current_fingerprint="$(credential_fingerprint "$CLAUDE_DIR/.credentials.json" 2>/dev/null || true)"
      if [ -z "$base_fingerprint" ] || [ "$current_fingerprint" != "$base_fingerprint" ]; then
        return 0
      fi
    fi
    sleep 2
  done
  return 1
}

start_profile_credentials_sync() {
  if [ ! -f /mnt/profile/.credentials.json ]; then
    return 0
  fi
  local interval="${OAUTH_CREDENTIAL_SYNC_INTERVAL_SEC:-15}"
  if [ "$interval" -le 0 ] 2>/dev/null; then
    return 0
  fi
  (
    while true; do
      sync_profile_credentials_once >/dev/null 2>&1 || true
      sleep "$interval"
    done
  ) &
  CREDENTIAL_SYNC_PID=$!
}

stop_profile_credentials_sync() {
  if [ -n "${CREDENTIAL_SYNC_PID:-}" ]; then
    kill "$CREDENTIAL_SYNC_PID" 2>/dev/null || true
    wait "$CREDENTIAL_SYNC_PID" 2>/dev/null || true
    CREDENTIAL_SYNC_PID=""
  fi
}

cleanup_workspace_dependencies() {
  # 运行产物要留给详情页查看，但依赖目录很容易吞掉磁盘，结束后默认清理。
  if [ "${CLEAN_WORKSPACE_DEPS:-1}" != "1" ]; then
    return 0
  fi
  find /workspace \
    \( -path /workspace/.claude-home -o -path /workspace/.claude-home/\* \) -prune \
    -o -type d \( \
      -name node_modules \
      -o -name .venv \
      -o -name venv \
      -o -name __pycache__ \
      -o -name .pytest_cache \
      -o -name .mypy_cache \
      -o -name .ruff_cache \
      -o -name .tox \
      -o -name target \
      -o -name dist \
      -o -name build \
      -o -name .next \
      -o -name .cache \
    \) -prune -exec rm -rf {} + 2>/dev/null || true
}

_CLEANUP_TASK_MODE_DONE=0
cleanup_task_mode() {
  # 成功、失败、timeout、SIGTERM 都会走这里；Claude 刚好刷新 token 时也尽量落回账号 profile。
  if [ "$_CLEANUP_TASK_MODE_DONE" = "1" ]; then
    return 0
  fi
  _CLEANUP_TASK_MODE_DONE=1
  if [ "$WORKER_MODE" = "task" ]; then
    stop_profile_credentials_sync || true
    persist_runtime_claude_state || true
    cleanup_workspace_dependencies || true
  fi
}

terminate_task_mode() {
  local code="$1"
  cleanup_task_mode || true
  exit "$code"
}

capture_transcript_snapshot() {
  # running 详情页复用最终 transcript 文件；用临时文件替换避免前端读到半截内容。
  if [ -z "${SESSION:-}" ]; then
    return 0
  fi
  tmux has-session -t "$SESSION" 2>/dev/null || return 0
  tmux capture-pane -t "$SESSION" -p -S - > /workspace/.bench-transcript.log.tmp 2>/dev/null \
    && mv /workspace/.bench-transcript.log.tmp /workspace/.bench-transcript.log \
    || true
}

classify_claude_completion() {
  # Stop hook 只能说明 Claude 结束了一次回合；真正成功必须看 session JSONL
  # 最后一条对话消息是否为稳定的纯文本 assistant 回复，不能停在 tool_use/tool_result。
  local idle_sec="$1"
  python3 - "$CLAUDE_DIR/projects/-workspace" "$idle_sec" <<'PY'
import json
import sys
import time
from pathlib import Path

project_dir = Path(sys.argv[1])
idle_sec = float(sys.argv[2])


def message_role(entry):
    message = entry.get("message")
    if isinstance(message, dict):
        return message.get("role")
    return entry.get("role")


def message_stop_reason(entry):
    message = entry.get("message")
    if isinstance(message, dict):
        return message.get("stop_reason")
    return entry.get("stop_reason")


def message_content(entry):
    message = entry.get("message")
    if isinstance(message, dict):
        return message.get("content")
    return entry.get("content")


def content_text(content):
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                parts.append(str(item.get("text") or ""))
        return "\n".join(parts)
    return ""


def content_has_tool_use(content):
    if not isinstance(content, list):
        return False
    return any(isinstance(item, dict) and item.get("type") == "tool_use" for item in content)


jsonl_files = sorted(project_dir.glob("*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)
if not jsonl_files:
    sys.exit(1)

latest_entry = None
latest_path = jsonl_files[0]
latest_stat = latest_path.stat()
if time.time() - latest_stat.st_mtime < idle_sec:
    sys.exit(1)

with latest_path.open("r", encoding="utf-8", errors="replace") as handle:
    for line in handle:
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        if message_role(entry) in {"assistant", "user"}:
            latest_entry = entry

if not latest_entry:
    sys.exit(1)

role = message_role(latest_entry)
content = message_content(latest_entry)
text = content_text(content)
stop_reason = message_stop_reason(latest_entry)

if role != "assistant":
    sys.exit(1)
if content_has_tool_use(content):
    sys.exit(1)
if stop_reason == "tool_use":
    sys.exit(1)
lines = [line.strip() for line in text.splitlines() if line.strip()]
if not lines:
    sys.exit(1)

auth_error_markers = [
    "Please run /login",
    "API Error: 401",
    "Invalid authentication credentials",
    "OAuth token has expired",
]
if any(marker in text for marker in auth_error_markers):
    print("fatal_auth_error")
    sys.exit(2)

print("complete")
PY
}

detect_claude_auth_error() {
  # 认证错误可能出现在最终 assistant 文本、tool_result 或 TUI transcript 中。
  # 只匹配明确 OAuth/401 标记，避免把普通失败误判为账号失效。
  # 发生过一次恢复后只扫描恢复时间之后的新 JSONL 事件，避免旧 transcript
  # 中残留的 401 文本让下一轮立刻误判为再次失败。
  local since_epoch="${1:-0}"
  local transcript_offset="${2:-0}"
  python3 - "$CLAUDE_DIR/projects/-workspace" "/workspace/.bench-transcript.log" "$since_epoch" "$transcript_offset" <<'PY'
import json
import sys
import datetime as dt
from pathlib import Path

project_dir = Path(sys.argv[1])
transcript_path = Path(sys.argv[2])
since_epoch = float(sys.argv[3] or 0)
transcript_offset = max(0, int(float(sys.argv[4] or 0)))
markers = (
    "Please run /login",
    "API Error: 401",
    "Invalid authentication credentials",
    "OAuth token has expired",
)

def content_text(content):
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if not isinstance(item, dict):
                continue
            if item.get("type") == "text":
                parts.append(str(item.get("text") or ""))
            elif item.get("type") == "tool_result":
                parts.append(content_text(item.get("content")))
        return "\n".join(parts)
    return ""

def entry_text(entry):
    message = entry.get("message")
    if isinstance(message, dict):
        return content_text(message.get("content"))
    return content_text(entry.get("content"))

def entry_epoch(entry):
    raw = entry.get("timestamp")
    if not isinstance(raw, str) or not raw:
        return None
    try:
        return dt.datetime.fromisoformat(raw.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None

texts = []
if project_dir.exists():
    files = sorted(project_dir.glob("*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)
    for path in files[:2]:
        try:
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()[-80:]
        except OSError:
            continue
        for line in lines:
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            if since_epoch > 0:
                ts = entry_epoch(entry)
                if ts is None or ts < since_epoch:
                    continue
            texts.append(entry_text(entry))
try:
    data = transcript_path.read_bytes()
    if since_epoch > 0:
        data = data[transcript_offset:]
    else:
        data = data[-12000:]
    texts.append(data.decode("utf-8", errors="replace"))
except OSError:
    pass

haystack = "\n".join(texts)
for marker in markers:
    if marker in haystack:
        print(marker)
        sys.exit(0)
sys.exit(1)
PY
}

detect_claude_api_stall() {
  # Claude Code 偶发会在 /v1/messages ECONNRESET 后长期卡在 busy 状态。
  # 这里只在“明确 API 连接错误 + 长时间没有对话/产物进展”同时成立时触发，
  # 避免把正常长思考或普通工具失败误判成卡死。
  local watchdog_sec="${1:-0}"
  local since_epoch="${2:-0}"
  python3 - "$CLAUDE_DIR/projects/-workspace" "/workspace" "$watchdog_sec" "$since_epoch" <<'PY'
import json
import os
import sys
import time
import datetime as dt
from pathlib import Path

project_dir = Path(sys.argv[1])
workspace = Path(sys.argv[2])
watchdog_sec = float(sys.argv[3] or 0)
since_epoch = float(sys.argv[4] or 0)

if watchdog_sec <= 0:
    sys.exit(1)

markers = (
    "econnreset",
    "connection error",
    "unable to connect to api",
    "failedtoopensocket",
)


def entry_epoch(entry):
    raw = entry.get("timestamp")
    if not isinstance(raw, str) or not raw:
        return None
    try:
        return dt.datetime.fromisoformat(raw.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def message_role(entry):
    message = entry.get("message")
    if isinstance(message, dict):
        return message.get("role")
    return entry.get("role")


def message_content(entry):
    message = entry.get("message")
    if isinstance(message, dict):
        return message.get("content")
    return entry.get("content")


def message_stop_reason(entry):
    message = entry.get("message")
    if isinstance(message, dict):
        return message.get("stop_reason")
    return entry.get("stop_reason")


def content_text(content):
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if not isinstance(item, dict):
                continue
            if item.get("type") == "text":
                parts.append(str(item.get("text") or ""))
            elif item.get("type") == "tool_result":
                parts.append(content_text(item.get("content")))
        return "\n".join(parts)
    return ""


def content_has_tool_use(content):
    if not isinstance(content, list):
        return False
    return any(isinstance(item, dict) and item.get("type") == "tool_use" for item in content)


def api_error_text(entry):
    pieces = []
    error = entry.get("error")
    if isinstance(error, dict):
        for key in ("message", "formatted"):
            value = error.get(key)
            if isinstance(value, str):
                pieces.append(value)
        connection = error.get("connection")
        if isinstance(connection, dict):
            for key in ("code", "message"):
                value = connection.get(key)
                if isinstance(value, str):
                    pieces.append(value)
    for key in ("message", "formatted"):
        value = entry.get(key)
        if isinstance(value, str):
            pieces.append(value)
    return "\n".join(pieces).lower()


def is_api_error(entry):
    if entry.get("type") != "system" or entry.get("subtype") != "api_error":
        return False
    text = api_error_text(entry)
    return any(marker in text for marker in markers)


def is_final_assistant(entry):
    if message_role(entry) != "assistant":
        return False
    content = message_content(entry)
    if content_has_tool_use(content):
        return False
    if message_stop_reason(entry) == "tool_use":
        return False
    return bool(content_text(content).strip())


def workspace_progress_epoch():
    latest = 0.0
    excluded_dirs = {".claude-home", ".claude", ".git", "node_modules", ".venv", "venv", "__pycache__"}
    excluded_files = {".bench-transcript.log", ".bench-status.json"}
    try:
        for root, dirs, files in os.walk(workspace):
            dirs[:] = [name for name in dirs if name not in excluded_dirs]
            for name in files:
                if name in excluded_files or name.startswith("."):
                    continue
                path = Path(root) / name
                try:
                    mtime = path.stat().st_mtime
                except OSError:
                    continue
                if mtime >= since_epoch:
                    latest = max(latest, mtime)
    except OSError:
        pass
    return latest


latest_error = 0.0
latest_progress = workspace_progress_epoch()
latest_entry = None

if project_dir.exists():
    files = sorted(project_dir.glob("*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)
    for path in files[:3]:
        try:
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        for line in lines:
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            ts = entry_epoch(entry)
            if ts is None or ts < since_epoch:
                continue
            if message_role(entry) in {"assistant", "user"}:
                latest_entry = entry
                latest_progress = max(latest_progress, ts)
            if is_api_error(entry):
                latest_error = max(latest_error, ts)

if latest_entry and is_final_assistant(latest_entry):
    sys.exit(1)
if latest_error <= 0 or latest_error <= latest_progress:
    sys.exit(1)

now = time.time()
idle_from = max(latest_progress, since_epoch)
idle_sec = now - idle_from
if idle_sec < watchdog_sec:
    sys.exit(1)

print(json.dumps({
    "latest_error_epoch": latest_error,
    "latest_progress_epoch": latest_progress,
    "idle_sec": int(idle_sec),
}, ensure_ascii=False))
PY
}

api_stall_recovery_count() {
  local value="0"
  if [ -f /tmp/claude-api-stall-recoveries ]; then
    value="$(cat /tmp/claude-api-stall-recoveries 2>/dev/null || echo 0)"
  fi
  case "$value" in
    ''|*[!0-9]*) value=0 ;;
  esac
  echo "$value"
}

api_stall_last_recovery_epoch() {
  local value="0"
  if [ -f /tmp/claude-api-stall-last-recovery ]; then
    value="$(cat /tmp/claude-api-stall-last-recovery 2>/dev/null || echo 0)"
  fi
  case "$value" in
    ''|*[!0-9]*) value=0 ;;
  esac
  echo "$value"
}

busy_interrupt_count() {
  local value="0"
  if [ -f /tmp/claude-busy-interrupts ]; then
    value="$(cat /tmp/claude-busy-interrupts 2>/dev/null || echo 0)"
  fi
  case "$value" in
    ''|*[!0-9]*) value=0 ;;
  esac
  echo "$value"
}

record_api_stall_recovery() {
  local count
  count="$(api_stall_recovery_count)"
  count=$((count + 1))
  echo "$count" > /tmp/claude-api-stall-recoveries
  date +%s > /tmp/claude-api-stall-last-recovery
  echo "$count"
}

record_busy_interrupt() {
  local count
  count="$(busy_interrupt_count)"
  count=$((count + 1))
  echo "$count" > /tmp/claude-busy-interrupts
  echo "$count"
}

interrupt_budget_used_count() {
  echo $(( $(api_stall_recovery_count) + $(busy_interrupt_count) ))
}

can_interrupt_for_recovery() {
  local max_recoveries="${CLAUDE_API_STALL_MAX_RECOVERIES:-1}"
  case "$max_recoveries" in
    ''|*[!0-9]*) max_recoveries=1 ;;
  esac
  if [ "$max_recoveries" -le 0 ] 2>/dev/null; then
    return 1
  fi
  [ "$(interrupt_budget_used_count)" -lt "$max_recoveries" ]
}

is_claude_tui_busy() {
  tmux has-session -t "$SESSION" 2>/dev/null || return 1
  local pane
  pane="$(tmux capture-pane -t "$SESSION" -p 2>/dev/null || true)"
  printf '%s' "$pane" | grep -Eiq "Beboppin|Herding|Frosting|Thinking|Retrying in|Running [0-9]+ shell command|tokens\\)"
}

inject_tmux_prompt() {
  local buffer="$1"
  local text="$2"
  tmux has-session -t "$SESSION" 2>/dev/null || return 1
  printf '%s' "$text" > "/tmp/${buffer}.txt"
  tmux load-buffer -b "$buffer" "/tmp/${buffer}.txt"
  tmux paste-buffer -t "$SESSION" -b "$buffer" -d -p
  sleep 1
  tmux send-keys -t "$SESSION" Enter
}

interrupt_and_inject_tmux_prompt() {
  local kind="$1"
  local text="$2"
  local grace="${CLAUDE_BUSY_INTERRUPT_GRACE_SEC:-8}"
  case "$grace" in
    ''|*[!0-9]*) grace=8 ;;
  esac
  tmux has-session -t "$SESSION" 2>/dev/null || return 1
  log "中断 Claude TUI 后注入 ${kind} 提示"
  tmux send-keys -t "$SESSION" C-c
  for _ in $(seq 1 "$grace"); do
    capture_transcript_snapshot
    sleep 1
  done
  inject_tmux_prompt "$kind" "$text"
}

write_api_stall_status() {
  local status="$1"
  local error="$2"
  write_bench_status "$status" "$error" "$(api_stall_recovery_count)"
}

# ---------- 0) /etc/machine-id 按账号名 hash 写入 ----------
# 让 Claude Code / Node 通过系统接口读到的 machine-id 是按账号派生的稳定值:
#   - 同账号每次 run → 同 machine-id(Anthropic 端看作同一台稳定设备)
#   - 跨账号 → 不同 machine-id(避免被关联识别为同台机器开多份)
# ACC_NAME 由 orchestrator 注入(task/login 模式都注入);未注入(如 legacy CLI
# init-account.sh)时跳过,保持向下兼容,不影响功能。
if [ -n "${ACC_NAME:-}" ]; then
  printf %s "$ACC_NAME" | sha256sum | cut -c1-32 > /etc/machine-id
  log "Wrote /etc/machine-id from ACC_NAME hash"
fi

# ---------- 1) MITM CA 注入 ----------
CA_PEM=/etc/mitm/mitmproxy-ca-cert.pem
if [ -f "$CA_PEM" ]; then
  log "Installing MITM CA into system + runtime trust stores"
  cp "$CA_PEM" /usr/local/share/ca-certificates/mitm.crt
  update-ca-certificates >/dev/null
  export NODE_EXTRA_CA_CERTS="$CA_PEM"
  export SSL_CERT_FILE="$CA_PEM"
  export REQUESTS_CA_BUNDLE="$CA_PEM"
  export CURL_CA_BUNDLE="$CA_PEM"
  export GIT_SSL_CAINFO="$CA_PEM"
else
  log "WARN: no MITM CA at $CA_PEM, traffic will NOT be decrypted"
fi

# ---------- 1.5) DNS 指向 sidecar netns 内的 unbound(127.0.0.1:53) ----------
# worker 与 sidecar 共享 network namespace,所以 127.0.0.1:53 = sidecar 的 unbound。
# 但 mount namespace 不共享,sidecar 写自己的 /etc/resolv.conf 不影响 worker。
# Docker daemon 默认会在 worker 容器写一份 /etc/resolv.conf(指向宿主 DNS,例如
# 192.168.x.1),那个 DNS 在 sidecar netns 里压根不可达 → 解析全坏。
# 这里强制覆盖,让 worker 的所有 UDP 53 落到 unbound,unbound 再用 TCP 53 出口
# (走 tun → hev → SOCKS5 TCP),解决商用 SOCKS5 不支持 UDP relay 的问题。
# login 模式允许用户不填 SOCKS5 直连 bridge 网络；这种情况下没有 sidecar /
# unbound，不能把 DNS 改到 127.0.0.1。task 模式恒定共享 sidecar netns。
if [ "$WORKER_MODE" != "login" ] || [ "${USE_SIDECAR_DNS:-0}" = "1" ]; then
  echo "nameserver 127.0.0.1" > /etc/resolv.conf
  log "Overrode /etc/resolv.conf to use sidecar unbound (127.0.0.1)"
else
  log "Login mode without sidecar DNS: keeping Docker-provided /etc/resolv.conf"
fi

# ---------- login 模式：CA 已装好，profile 目录直接挂在 node HOME，空转待 exec ----------
if [ "$WORKER_MODE" = "login" ]; then
  mkdir -p "$CLAUDE_DIR"
  if [ -f "$CLAUDE_DIR/.claude.json" ] && [ ! -f "$CLAUDE_HOME/.claude.json" ]; then
    cp "$CLAUDE_DIR/.claude.json" "$CLAUDE_HOME/.claude.json"
    patch_top_config_gates
    log "Restored top-level ~/.claude.json from profile"
  fi
  write_default_settings
  chown -R "$CLAUDE_USER:$CLAUDE_USER" "$CLAUDE_HOME" || true
  log "Login mode: idling; orchestrator will docker exec 'claude auth login' as $CLAUDE_USER."
  log "  profile dir contents at start:"
  ls -la "$CLAUDE_DIR" 2>/dev/null | head -20
  # 用 tail -f /dev/null 替代 sleep infinity（更可控，收到 SIGTERM 立刻退出）
  exec tail -f /dev/null
fi

# ---------- 以下是 task 模式 ----------
: "${TASK_PROMPT:?TASK_PROMPT required in task mode}"
: "${RUN_ID:?RUN_ID required in task mode}"
TIMEOUT_SEC="${TIMEOUT_SEC:-1800}"
trap cleanup_task_mode EXIT
trap 'terminate_task_mode 143' TERM
trap 'terminate_task_mode 130' INT

# ---------- 2) 复制账号 profile 到 node HOME + 还原顶层 .claude.json ----------
# claude 启动时读两份配置:
#   ~/.claude.json       顶层文件,含 oauthAccount / migrationVersion / userID
#                        等"已登录、已 onboarded"的标志(没它就重走 first-run)
#   ~/.claude/...        子目录,含 .credentials.json / settings.json / sessions/
# orchestrator 在 login commit 时把顶层 ~/.claude.json 复制回 profile:
#   data/profiles/<name>/.claude.json    ← 顶层配置的持久化副本
#   data/profiles/<name>/<其它>           ← /home/node/.claude/ 目录挂载落盘
# task 模式 worker 拿到的 /mnt/profile 是同一个目录,所以 /mnt/profile/.claude.json
# 就是当时 OAuth 完成时的顶层文件;复制时要单独 mv 到 /home/node/.claude.json,
# 不能让它躺在 $HOME/.claude/ 子目录里(那里 claude 不会读顶层配置)。
mkdir -p "$CLAUDE_DIR"
if [ -d /mnt/profile ]; then
  log "Copying account profile from /mnt/profile -> $CLAUDE_DIR"
  cp -a /mnt/profile/. "$CLAUDE_DIR/"
  # 历史 telemetry / backups 不让重放
  rm -rf "$CLAUDE_DIR/telemetry" "$CLAUDE_DIR/backups"
  # 把顶层 .claude.json 还原到 $HOME/.claude.json(claude 只在 $HOME 根读它)
  if [ -f "$CLAUDE_DIR/.claude.json" ]; then
    mv "$CLAUDE_DIR/.claude.json" "$CLAUDE_HOME/.claude.json"
    patch_top_config_gates
    log "Restored top-level ~/.claude.json from profile"
  else
    log "WARN: no .claude.json in profile; first-run dialogs likely to appear"
  fi
else
  log "WARN: no profile mounted at /mnt/profile, claude likely not authenticated"
fi
chown -R "$CLAUDE_USER:$CLAUDE_USER" "$CLAUDE_HOME" /workspace || true

# ---------- 3) 注入 settings 文件 ----------
# settings.json:用户偏好 + permissions allowlist + model 默认值。即使 .claude.json
# 在场,settings.json 也仍生效(两个文件互不替代)。
write_default_settings

# Stop hook 放到当前 workspace 的 project-local settings。
# 官方 user-local 路径不是 ~/.claude/settings.local.json；放错位置会导致 hook
# 不加载，worker 只能等 timeout。workspace 是每个 run 独立目录，不污染 profile。
# hook 只作为“Claude 停过一轮”的观测信号，成功仍由 JSONL 最新对话消息判断，
# 避免工具调用中间态被误判为 success。
mkdir -p /workspace/.claude
cat > /workspace/.claude/settings.local.json <<'EOF'
{
  "hooks": {
    "Stop": [
      {
        "matcher": "",
        "hooks": [
          { "type": "command", "command": "date +%s >> /tmp/claude-stop-seen" }
        ]
      }
    ]
  }
}
EOF
chown -R "$CLAUDE_USER:$CLAUDE_USER" "$CLAUDE_HOME" /workspace || true
rm -f /tmp/claude-done /tmp/claude-stop-seen
rm -f /tmp/claude-exited /tmp/claude-exit-code
rm -f /tmp/claude-fatal-error /tmp/claude-completion-state
rm -f /tmp/claude-auth-recovered-once /tmp/claude-wrapup-sent
rm -f /tmp/claude-api-stall-recoveries /tmp/claude-api-stall-last-recovery /tmp/claude-busy-interrupts
rm -f /workspace/.bench-status.json /workspace/.bench-status.json.tmp

start_profile_credentials_sync

# ---------- 4) 启动 tmux + claude (node 用户 + bypassPermissions) ----------
# Claude Code 的 bypassPermissions 不能以 root 跑，所以入口脚本只用 root
# 做 CA/DNS/文件属主准备，真正的 TUI 进程切到 node 用户、同一 HOME。
#
# CA 环境变量必须显式带进 send-keys 的命令行:tmux 启的 shell 是新 bash 进程,
# entrypoint 当前 shell 里 export 的 NODE_EXTRA_CA_CERTS 等不会自动继承(它们没有
# 写到 /etc/profile)。Node 默认不读系统 ca-certificates,只信 NODE_EXTRA_CA_CERTS;
# 不带的话 claude 一连 api.anthropic.com 就 UNABLE_TO_VERIFY_LEAF_SIGNATURE → 表现
# 为 TUI 上的 "FailedToOpenSocket"。
#
# orchestrator 已在创建 worker 前 exec 进 sidecar 等待通用 DNS resolver 就绪。
# 这里保留短兜底,防止 worker /etc/resolv.conf 覆盖后仍遇到极短瞬时竞态。
wait_for_sidecar_dns || true

check_claude_auth_status

SESSION="claude-${RUN_ID}"
log "Launching tmux session: $SESSION ($CLAUDE_USER bypassPermissions mode)"
claude_args=(claude)
if [ -n "${CLAUDE_MODEL_OVERRIDE:-}" ]; then
  # 后端已校验模型名字符集；这里用数组参数传递，避免把用户输入拼进 shell。
  claude_args+=(--model "$CLAUDE_MODEL_OVERRIDE")
  log "Using one-shot Claude model override: $CLAUDE_MODEL_OVERRIDE"
fi
tmux new-session -d -s "$SESSION" -x 220 -y 60
tmux send-keys -t "$SESSION" \
  "export NODE_EXTRA_CA_CERTS='$CA_PEM' SSL_CERT_FILE='$CA_PEM' REQUESTS_CA_BUNDLE='$CA_PEM' CURL_CA_BUNDLE='$CA_PEM' GIT_SSL_CAINFO='$CA_PEM' HOME='$CLAUDE_HOME' && cd /workspace && runuser -u '$CLAUDE_USER' -- env HOME='$CLAUDE_HOME' NODE_EXTRA_CA_CERTS='$CA_PEM' SSL_CERT_FILE='$CA_PEM' REQUESTS_CA_BUNDLE='$CA_PEM' CURL_CA_BUNDLE='$CA_PEM' GIT_SSL_CAINFO='$CA_PEM' $(printf '%q ' "${claude_args[@]}"); code=\$?; echo; echo \"[entrypoint] claude exited with code \$code\"; echo \$code >/tmp/claude-exit-code; touch /tmp/claude-exited; sleep 3600" Enter

# 等 claude TUI 就绪
sleep 6
if [ -f /tmp/claude-exited ]; then
  log "Claude exited before prompt injection"
fi
startup_ready=1
handle_claude_startup_gates || startup_ready=0

# ---------- 5) 注入 prompt(用 bracketed paste,避免逐字符触发 TUI 行为) ----------
if [ ! -f /tmp/claude-exited ] && [ "$startup_ready" = "1" ]; then
  log "Injecting prompt (${#TASK_PROMPT} chars)"
  inject_tmux_prompt prompt "$TASK_PROMPT"
elif [ ! -f /tmp/claude-exited ]; then
  log "Prompt injection skipped because Claude startup gates are still visible"
  capture_transcript_snapshot
  persist_runtime_claude_state
  tmux kill-session -t "$SESSION" 2>/dev/null || true
  exit 1
fi

# ---------- 6) 等最终 assistant 回复 / Claude 退出 / 超时 ----------
COMPLETION_IDLE_SEC="${COMPLETION_IDLE_SEC:-10}"
TIMEOUT_WRAPUP_SEC="${TIMEOUT_WRAPUP_SEC:-600}"
TIMEOUT_WRAPUP_PROMPT="${TIMEOUT_WRAPUP_PROMPT:-时间快到，请停止扩展功能和长时间验证，优先补齐最小可运行交付。请整理当前已完成内容，必要时说明未完成项和验证降级原因，然后输出最终总结。}"
AUTH_RECOVERY_PROMPT="${AUTH_RECOVERY_PROMPT:-检测到 OAuth access token 可能刚刷新。请重试刚才失败的请求；如果仍失败，不要打开登录流，请说明认证失败并输出最终总结。}"
CLAUDE_API_STALL_WATCHDOG_SEC="${CLAUDE_API_STALL_WATCHDOG_SEC:-400}"
CLAUDE_API_STALL_RECOVERY_PROMPT="${CLAUDE_API_STALL_RECOVERY_PROMPT:-刚才 Claude API 连接异常导致当前回合卡住。请从当前文件状态继续，优先完成最小可运行版本；不要重新做环境调研，不要安装大型依赖。若时间不足，请立即整理已完成内容、验证方式、未完成项并输出最终总结。}"
log "Waiting for final assistant message or timeout (${TIMEOUT_SEC}s)"
run_started_at=$(date +%s)
deadline=$(( $(date +%s) + TIMEOUT_SEC ))
completion_done=0
capture_transcript_snapshot
while [ "$(date +%s)" -lt "$deadline" ]; do
  now=$(date +%s)
  capture_transcript_snapshot
  if [ "$TIMEOUT_WRAPUP_SEC" -gt 0 ] 2>/dev/null \
    && [ ! -f /tmp/claude-wrapup-sent ] \
    && [ $(( deadline - now )) -le "$TIMEOUT_WRAPUP_SEC" ]; then
    log "Injecting timeout wrap-up prompt (${TIMEOUT_WRAPUP_SEC}s before deadline)"
    if is_claude_tui_busy && can_interrupt_for_recovery; then
      busy_interrupts="$(record_busy_interrupt)"
      write_api_stall_status "running" "临近超时且 Claude TUI 仍忙，已中断并注入收尾提示 ${busy_interrupts} 次"
      interrupt_and_inject_tmux_prompt wrapup "$TIMEOUT_WRAPUP_PROMPT" || true
    else
      inject_tmux_prompt wrapup "$TIMEOUT_WRAPUP_PROMPT" || true
    fi
    touch /tmp/claude-wrapup-sent
  fi
  auth_since=0
  auth_transcript_offset=0
  if [ -f /tmp/claude-auth-recovered-once ]; then
    auth_since="$(sed -n '1p' /tmp/claude-auth-recovered-once 2>/dev/null || echo 0)"
    auth_transcript_offset="$(sed -n '2p' /tmp/claude-auth-recovered-once 2>/dev/null || echo 0)"
  fi
  auth_marker=""
  auth_status=0
  auth_marker="$(detect_claude_auth_error "$auth_since" "$auth_transcript_offset" 2>/dev/null)" || auth_status=$?
  if [ "$auth_status" -eq 0 ]; then
    credential_before=""
    credential_before="$(credential_fingerprint "$CLAUDE_DIR/.credentials.json" 2>/dev/null || true)"
    sync_profile_credentials_once >/dev/null 2>&1 || true
    if [ ! -f /tmp/claude-auth-recovered-once ]; then
      log "Detected Claude auth error (${auth_marker}); waiting for refreshed profile credentials"
      if ! wait_for_profile_credentials_refresh "$credential_before"; then
        log "No refreshed OAuth credentials appeared within ${OAUTH_401_PROFILE_WAIT_SEC:-90}s"
        echo "auth_error" > /tmp/claude-fatal-error
        write_bench_status "auth_failed" "OAuth 认证失败: ${auth_marker}，等待后台刷新凭据超时"
        break
      fi
      log "Refreshed OAuth credentials synced; prompting one retry"
      inject_tmux_prompt auth-retry "$AUTH_RECOVERY_PROMPT" || true
      {
        date +%s
        wc -c < /workspace/.bench-transcript.log 2>/dev/null || echo 0
      } > /tmp/claude-auth-recovered-once
      sleep 5
      continue
    fi
    echo "auth_error" > /tmp/claude-fatal-error
    write_bench_status "auth_failed" "OAuth 认证失败: ${auth_marker}"
    break
  fi
  api_stall_status=0
  api_stall_since="$(api_stall_last_recovery_epoch)"
  if [ "$api_stall_since" -le 0 ] 2>/dev/null; then
    api_stall_since="$run_started_at"
  fi
  detect_claude_api_stall "$CLAUDE_API_STALL_WATCHDOG_SEC" "$api_stall_since" >/dev/null 2>&1 || api_stall_status=$?
  if [ "$api_stall_status" -eq 0 ]; then
    if can_interrupt_for_recovery; then
      recovery_count="$(record_api_stall_recovery)"
      log "检测到 Claude API 卡死，准备自动中断并继续（第 ${recovery_count} 次）"
      write_api_stall_status "running" "检测到 Claude API 连接卡死，已自动中断并继续 ${recovery_count} 次"
      interrupt_and_inject_tmux_prompt api-stall "$CLAUDE_API_STALL_RECOVERY_PROMPT" || true
      sleep 5
      continue
    fi
    write_api_stall_status "running" "检测到 Claude API 连接卡死，但自动恢复次数已用完"
  fi
  completion_status=0
  classify_claude_completion "$COMPLETION_IDLE_SEC" >/tmp/claude-completion-state 2>/dev/null || completion_status=$?
  if [ "$completion_status" -eq 0 ]; then
    completion_done=1
    break
  fi
  if [ "$completion_status" -eq 2 ]; then
    echo "auth_error" > /tmp/claude-fatal-error
    write_bench_status "auth_failed" "OAuth 认证失败"
    break
  fi
  if [ -f /tmp/claude-exited ]; then
    completion_status=0
    classify_claude_completion 0 >/tmp/claude-completion-state 2>/dev/null || completion_status=$?
    if [ "$completion_status" -eq 0 ]; then
      completion_done=1
    fi
    if [ "$completion_status" -eq 2 ]; then
      echo "auth_error" > /tmp/claude-fatal-error
      write_bench_status "auth_failed" "OAuth 认证失败"
    fi
    break
  fi
  sleep 2
done

# ---------- 7) 抓取 transcript,关掉 tmux ----------
capture_transcript_snapshot
persist_runtime_claude_state
tmux kill-session -t "$SESSION" 2>/dev/null || true
if [ "$completion_done" -ne 1 ] && [ ! -f /tmp/claude-fatal-error ]; then
  completion_status=0
  classify_claude_completion 0 >/tmp/claude-completion-state 2>/dev/null || completion_status=$?
  if [ "$completion_status" -eq 0 ]; then
    completion_done=1
  elif [ "$completion_status" -eq 2 ]; then
    echo "auth_error" > /tmp/claude-fatal-error
    write_bench_status "auth_failed" "OAuth 认证失败"
  fi
fi

if [ "$completion_done" -eq 1 ]; then
  log "Claude finished with final assistant message"
  exit 0
elif [ -f /tmp/claude-fatal-error ]; then
  log "Claude returned a fatal authentication error"
  if [ ! -f /workspace/.bench-status.json ]; then
    write_bench_status "auth_failed" "OAuth 认证失败"
  fi
  exit 42
elif [ -f /tmp/claude-exited ]; then
  code=$(cat /tmp/claude-exit-code 2>/dev/null || echo 1)
  if [ "$code" = "0" ]; then
    log "Claude exited without final assistant message"
    exit 1
  else
    log "Claude exited early with code ${code}"
    exit "$code"
  fi
else
  log "Timeout after ${TIMEOUT_SEC}s without final assistant message"
  if [ "$(api_stall_recovery_count)" -gt 0 ] 2>/dev/null; then
    write_api_stall_status "timeout" "Claude API 连接卡死后仍未在超时前完成，已自动恢复 $(api_stall_recovery_count) 次"
  elif [ "$(busy_interrupt_count)" -gt 0 ] 2>/dev/null; then
    write_api_stall_status "timeout" "临近超时抢占 busy TUI 后仍未在超时前完成，已中断并注入收尾提示 $(busy_interrupt_count) 次"
  fi
  exit 124
fi
