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
#   其它 启动失败
# =======================================================================
set -euo pipefail

WORKER_MODE="${WORKER_MODE:-task}"
log() { echo "[entrypoint $(date +%H:%M:%S)] $*"; }
CLAUDE_USER=node
CLAUDE_HOME=/home/node
CLAUDE_DIR="$CLAUDE_HOME/.claude"

write_default_settings() {
  # settings.json 既要补齐默认值，又不能覆盖 Claude 自己写入的隐藏 gate。
  # 用 jq 递归合并：已有字段保留，默认字段补齐；同名字段以默认值为准。
  cat > /tmp/default-settings.json <<'EOF'
{
  "env": {
    "CLAUDE_CODE_EFFORT_LEVEL": "max"
  },
  "permissions": {
    "defaultMode": "bypassPermissions",
    "allow": [
      "Bash", "BashOutput", "Edit", "Glob", "Grep",
      "KillShell", "NotebookEdit", "Read", "SlashCommand",
      "Task", "TodoWrite", "WebFetch", "WebSearch", "Write"
    ],
    "deny": []
  },
  "skipDangerousModePermissionPrompt": true,
  "autoMemoryEnabled": false,
  "theme": "dark",
  "model": "opus[1m]"
}
EOF
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
  # 先用非 TUI 的 auth status 验证 profile，不把题目 prompt 粘进登录流。
  # 这不是任务执行路径；真正做题仍走下方 tmux 交互 TUI。
  log "Checking Claude auth status before interactive task run"
  set +e
  runuser -u "$CLAUDE_USER" -- env \
    HOME="$CLAUDE_HOME" \
    NODE_EXTRA_CA_CERTS="$CA_PEM" \
    SSL_CERT_FILE="$CA_PEM" \
    REQUESTS_CA_BUNDLE="$CA_PEM" \
    CURL_CA_BUNDLE="$CA_PEM" \
    GIT_SSL_CAINFO="$CA_PEM" \
    claude auth status > /tmp/claude-auth-status.json 2> /tmp/claude-auth-status.err
  local auth_code=$?
  set -e
  if [ "$auth_code" -ne 0 ] || ! jq -e '.loggedIn == true' /tmp/claude-auth-status.json >/dev/null 2>&1; then
    {
      echo "[entrypoint] Claude profile is not logged in; refusing to open OAuth prompt in task mode"
      echo "--- auth status stdout ---"
      cat /tmp/claude-auth-status.json 2>/dev/null || true
      echo "--- auth status stderr ---"
      cat /tmp/claude-auth-status.err 2>/dev/null || true
    } > /workspace/.bench-transcript.log
    persist_runtime_claude_state
    log "Claude auth status check failed; not injecting task prompt into login flow"
    exit 1
  fi
}

refresh_oauth_credentials() {
  # `claude auth status` 只验证本地 profile 形态，access token 失效时仍可能显示已登录。
  # 跑题前先看 expiresAt；只有 token 缺失/已过期/快过期才 refresh，避免每次 run 都打 OAuth 端点。
  local credentials_path="$CLAUDE_DIR/.credentials.json"
  if [ ! -f "$credentials_path" ]; then
    return 0
  fi
  set +e
  runuser -u "$CLAUDE_USER" -- env \
    HOME="$CLAUDE_HOME" \
    SSL_CERT_FILE="${SSL_CERT_FILE:-}" \
    REQUESTS_CA_BUNDLE="${REQUESTS_CA_BUNDLE:-}" \
    python3 - "$credentials_path" <<'PY'
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

TOKEN_URL = "https://platform.claude.com/v1/oauth/token"
CLIENT_ID = "9d1c250a-e61b-44d9-88ed-5944d1962f5e"
SCOPES = [
    "user:profile",
    "user:inference",
    "user:sessions:claude_code",
    "user:mcp_servers",
    "user:file_upload",
]

path = Path(sys.argv[1])
try:
    data = json.loads(path.read_text(encoding="utf-8"))
except Exception as exc:
    print(f"读取 .credentials.json 失败: {exc}", file=sys.stderr)
    sys.exit(1)

oauth = data.get("claudeAiOauth")
if not isinstance(oauth, dict):
    sys.exit(0)

access_token = oauth.get("accessToken")
expires_at = oauth.get("expiresAt")
now_ms = int(time.time() * 1000)
refresh_buffer_ms = 10 * 60 * 1000
if (
    isinstance(access_token, str)
    and access_token
    and isinstance(expires_at, (int, float))
    and expires_at > now_ms + refresh_buffer_ms
):
    sys.exit(0)

refresh_token = oauth.get("refreshToken")
if not isinstance(refresh_token, str) or not refresh_token:
    print("OAuth refreshToken 为空，access token 已缺失或接近过期，请重新登录账号", file=sys.stderr)
    sys.exit(1)

body = json.dumps({
    "grant_type": "refresh_token",
    "refresh_token": refresh_token,
    "client_id": CLIENT_ID,
    "scope": " ".join(SCOPES),
}).encode("utf-8")
request = urllib.request.Request(
    TOKEN_URL,
    data=body,
    headers={
        "Content-Type": "application/json",
        "Accept": "application/json",
    },
    method="POST",
)
try:
    with urllib.request.urlopen(request, timeout=30) as response:
        payload = json.loads(response.read().decode("utf-8"))
except urllib.error.HTTPError as exc:
    text = exc.read().decode("utf-8", errors="replace")
    print(f"OAuth token 刷新失败: HTTP {exc.code} {text[:500]}", file=sys.stderr)
    sys.exit(1)
except Exception as exc:
    print(f"OAuth token 刷新失败: {exc}", file=sys.stderr)
    sys.exit(1)

access_token = payload.get("access_token")
if not isinstance(access_token, str) or not access_token:
    print("OAuth token 刷新响应缺少 access_token", file=sys.stderr)
    sys.exit(1)

oauth["accessToken"] = access_token
new_refresh_token = payload.get("refresh_token")
if isinstance(new_refresh_token, str) and new_refresh_token:
    oauth["refreshToken"] = new_refresh_token
expires_in = payload.get("expires_in")
try:
    expires_in_sec = int(expires_in)
except (TypeError, ValueError):
    expires_in_sec = 3600
oauth["expiresAt"] = int(time.time() * 1000) + max(expires_in_sec, 60) * 1000

tmp = path.with_suffix(path.suffix + ".tmp")
tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
tmp.replace(path)
PY
  local refresh_code=$?
  set -e
  if [ "$refresh_code" -ne 0 ]; then
    {
      echo "[entrypoint] OAuth token 刷新失败，拒绝继续跑题以免 401 被误判成功"
      echo "--- oauth refresh stderr 已见容器日志 ---"
    } > /workspace/.bench-transcript.log
    persist_runtime_claude_state
    exit 1
  fi
}

persist_runtime_claude_state() {
  # task 模式里 Claude 跑在 $HOME 的运行时副本中；这里只按白名单回写会影响
  # 下次启动/认证的文件，避免 sessions/telemetry/backups 被并发 run 污染。
  if [ ! -d /mnt/profile ] || [ ! -w /mnt/profile ]; then
    return 0
  fi
  if [ -f "$CLAUDE_DIR/.credentials.json" ]; then
    cp "$CLAUDE_DIR/.credentials.json" /mnt/profile/.credentials.json || true
  fi
  if [ -f "$CLAUDE_HOME/.claude.json" ]; then
    patch_top_config_gates
    cp "$CLAUDE_HOME/.claude.json" /mnt/profile/.claude.json || true
  fi
  if [ -f "$CLAUDE_DIR/settings.json" ]; then
    cp "$CLAUDE_DIR/settings.json" /mnt/profile/settings.json || true
  fi
  chown "$CLAUDE_USER:$CLAUDE_USER" \
    /mnt/profile/.credentials.json \
    /mnt/profile/.claude.json \
    /mnt/profile/settings.json 2>/dev/null || true
}

_CLEANUP_TASK_MODE_DONE=0
cleanup_task_mode() {
  # 成功、失败、timeout、SIGTERM 都会走这里；Claude 刚好刷新 token 时也尽量落回账号 profile。
  if [ "$_CLEANUP_TASK_MODE_DONE" = "1" ]; then
    return 0
  fi
  _CLEANUP_TASK_MODE_DONE=1
  if [ "$WORKER_MODE" = "task" ]; then
    persist_runtime_claude_state || true
  fi
}

terminate_task_mode() {
  local code="$1"
  cleanup_task_mode || true
  exit "$code"
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
# 启动前先等 sidecar 网络链路真正可用(DNS 通即可证明 tun→hev→mitm→上游全通):
# orchestrator 的 SIDECAR_BOOT_WAIT 是固定常量,但 sidecar race-fix 后路由稳定要
# 9-10s,常量不够。worker 自查 DNS 比依赖 orchestrator 估算更稳。
log "Waiting for sidecar network to stabilize (DNS resolvable)..."
for i in $(seq 1 30); do
  if getent hosts api.anthropic.com >/dev/null 2>&1; then
    log "Sidecar network ready (DNS ok after ${i}s)"
    break
  fi
  sleep 1
done
if ! getent hosts api.anthropic.com >/dev/null 2>&1; then
  log "WARN: DNS still not ready after 30s; claude may fail"
fi

refresh_oauth_credentials
check_claude_auth_status

SESSION="claude-${RUN_ID}"
log "Launching tmux session: $SESSION ($CLAUDE_USER bypassPermissions mode)"
tmux new-session -d -s "$SESSION" -x 220 -y 60
tmux send-keys -t "$SESSION" \
  "export NODE_EXTRA_CA_CERTS='$CA_PEM' SSL_CERT_FILE='$CA_PEM' REQUESTS_CA_BUNDLE='$CA_PEM' CURL_CA_BUNDLE='$CA_PEM' GIT_SSL_CAINFO='$CA_PEM' HOME='$CLAUDE_HOME' && cd /workspace && runuser -u '$CLAUDE_USER' -- env HOME='$CLAUDE_HOME' NODE_EXTRA_CA_CERTS='$CA_PEM' SSL_CERT_FILE='$CA_PEM' REQUESTS_CA_BUNDLE='$CA_PEM' CURL_CA_BUNDLE='$CA_PEM' GIT_SSL_CAINFO='$CA_PEM' claude; code=\$?; echo; echo \"[entrypoint] claude exited with code \$code\"; echo \$code >/tmp/claude-exit-code; touch /tmp/claude-exited; sleep 3600" Enter

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
  printf '%s' "$TASK_PROMPT" > /tmp/task-prompt.txt
  tmux load-buffer -b prompt /tmp/task-prompt.txt
  tmux paste-buffer -t "$SESSION" -b prompt -d -p
  sleep 1
  tmux send-keys -t "$SESSION" Enter
elif [ ! -f /tmp/claude-exited ]; then
  log "Prompt injection skipped because Claude startup gates are still visible"
  tmux capture-pane -t "$SESSION" -p -S - > /workspace/.bench-transcript.log 2>/dev/null || true
  persist_runtime_claude_state
  tmux kill-session -t "$SESSION" 2>/dev/null || true
  exit 1
fi

# ---------- 6) 等最终 assistant 回复 / Claude 退出 / 超时 ----------
COMPLETION_IDLE_SEC="${COMPLETION_IDLE_SEC:-10}"
log "Waiting for final assistant message or timeout (${TIMEOUT_SEC}s)"
deadline=$(( $(date +%s) + TIMEOUT_SEC ))
completion_done=0
while [ "$(date +%s)" -lt "$deadline" ]; do
  completion_status=0
  classify_claude_completion "$COMPLETION_IDLE_SEC" >/tmp/claude-completion-state 2>/dev/null || completion_status=$?
  if [ "$completion_status" -eq 0 ]; then
    completion_done=1
    break
  fi
  if [ "$completion_status" -eq 2 ]; then
    echo "auth_error" > /tmp/claude-fatal-error
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
    fi
    break
  fi
  sleep 2
done

# ---------- 7) 抓取 transcript,关掉 tmux ----------
tmux capture-pane -t "$SESSION" -p -S - > /workspace/.bench-transcript.log 2>/dev/null || true
persist_runtime_claude_state
tmux kill-session -t "$SESSION" 2>/dev/null || true
if [ "$completion_done" -ne 1 ] && [ ! -f /tmp/claude-fatal-error ]; then
  completion_status=0
  classify_claude_completion 0 >/tmp/claude-completion-state 2>/dev/null || completion_status=$?
  if [ "$completion_status" -eq 0 ]; then
    completion_done=1
  elif [ "$completion_status" -eq 2 ]; then
    echo "auth_error" > /tmp/claude-fatal-error
  fi
fi

if [ "$completion_done" -eq 1 ]; then
  log "Claude finished with final assistant message"
  exit 0
elif [ -f /tmp/claude-fatal-error ]; then
  log "Claude returned a fatal authentication error"
  exit 1
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
  exit 124
fi
