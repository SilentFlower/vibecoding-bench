#!/usr/bin/env bash
# =======================================================================
# Worker 入口脚本
# 模式：
#   WORKER_MODE=task  （默认）跑题：注入 prompt → 等 Stop hook → 抓 transcript
#   WORKER_MODE=login OAuth 引导：装 CA 后空转，等 orchestrator 用
#                     docker exec 启动 `claude auth login` 走 PTY 桥到 WebUI
# 必备环境变量（task 模式）：
#   TASK_PROMPT     题目 prompt（字面文本）
#   RUN_ID          本次运行的唯一 ID（用于会话名 / 日志归档）
#   TIMEOUT_SEC     超时（秒），默认 1800
# 挂载约定：
#   task 模式：
#     /mnt/profile  账号 ~/.claude profile（只读复制到 /root/.claude）
#     /etc/mitm     MITM CA 目录
#     /workspace    claude 工作目录（每个 run 独立）
#   login 模式：
#     /root/.claude 直接挂宿主 data/profiles/<name>/（rw），claude auth login 直接落盘
#     /etc/mitm     同上
# 退出码（task 模式）：
#   0    Stop hook 正常触发
#   124  达到 TIMEOUT_SEC 超时
#   其它 启动失败
# =======================================================================
set -euo pipefail

WORKER_MODE="${WORKER_MODE:-task}"
log() { echo "[entrypoint $(date +%H:%M:%S)] $*"; }

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

# ---------- login 模式：CA 已装好，profile 目录直接挂在 /root/.claude，空转待 exec ----------
if [ "$WORKER_MODE" = "login" ]; then
  mkdir -p /root/.claude
  log "Login mode: idling; orchestrator will docker exec 'claude auth login'."
  log "  profile dir contents at start:"
  ls -la /root/.claude 2>/dev/null | head -20
  # 用 tail -f /dev/null 替代 sleep infinity（更可控，收到 SIGTERM 立刻退出）
  exec tail -f /dev/null
fi

# ---------- 以下是 task 模式 ----------
: "${TASK_PROMPT:?TASK_PROMPT required in task mode}"
: "${RUN_ID:?RUN_ID required in task mode}"
TIMEOUT_SEC="${TIMEOUT_SEC:-1800}"

# ---------- 2) 复制账号 profile 到 /root/.claude ----------
mkdir -p /root/.claude
if [ -d /mnt/profile ]; then
  log "Copying account profile from /mnt/profile -> /root/.claude"
  cp -a /mnt/profile/. /root/.claude/
  # 不让历史 telemetry / backups 在每次 run 重放:
  # - telemetry/1p_failed_events.*.json 会被 Claude Code 启动时重试上传,等于
  #   把上次没传上去的事件每次都重放;
  # - backups/.claude.json.backup.* 是旧 config 备份,运行时无用,且每次重 login
  #   都会累积。
  # 这里只清运行时副本(/root/.claude),不动只读源(/mnt/profile),并发安全。
  rm -rf /root/.claude/telemetry /root/.claude/backups
else
  log "WARN: no profile mounted at /mnt/profile, claude likely not authenticated"
fi

# ---------- 3) 注入 Stop hook（settings.local.json 优先级最高，不污染 profile）----------
cat > /root/.claude/settings.local.json <<'EOF'
{
  "hooks": {
    "Stop": [
      {
        "matcher": "",
        "hooks": [
          { "type": "command", "command": "touch /tmp/claude-done" }
        ]
      }
    ]
  }
}
EOF
rm -f /tmp/claude-done

# ---------- 4) 启动 tmux + claude ----------
SESSION="claude-${RUN_ID}"
log "Launching tmux session: $SESSION"
tmux new-session -d -s "$SESSION" -x 220 -y 60
# claude 启动；进入 /workspace
tmux send-keys -t "$SESSION" "cd /workspace && claude" Enter

# 等 claude TUI 就绪（无可靠信号，sleep 兜底）
sleep 4

# ---------- 5) 注入 prompt（用 bracketed paste，避免逐字符触发 TUI 行为）----------
log "Injecting prompt (${#TASK_PROMPT} chars)"
printf '%s' "$TASK_PROMPT" > /tmp/task-prompt.txt
tmux load-buffer -b prompt /tmp/task-prompt.txt
tmux paste-buffer -t "$SESSION" -b prompt -d -p
sleep 1
tmux send-keys -t "$SESSION" Enter

# ---------- 6) 等 Stop hook 触发 / 超时 ----------
log "Waiting for Stop hook or timeout (${TIMEOUT_SEC}s)"
deadline=$(( $(date +%s) + TIMEOUT_SEC ))
while [ ! -f /tmp/claude-done ] && [ "$(date +%s)" -lt "$deadline" ]; do
  sleep 2
done

# ---------- 7) 抓取 transcript，关掉 tmux ----------
tmux capture-pane -t "$SESSION" -p -S - > /workspace/.bench-transcript.log 2>/dev/null || true
tmux kill-session -t "$SESSION" 2>/dev/null || true

if [ -f /tmp/claude-done ]; then
  log "Claude finished normally"
  exit 0
else
  log "Timeout after ${TIMEOUT_SEC}s"
  exit 124
fi
