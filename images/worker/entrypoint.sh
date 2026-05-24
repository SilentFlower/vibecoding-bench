#!/usr/bin/env bash
# =======================================================================
# Worker 入口脚本
# 必备环境变量：
#   TASK_PROMPT     题目 prompt（字面文本）
#   RUN_ID          本次运行的唯一 ID（用于会话名 / 日志归档）
#   TIMEOUT_SEC     超时（秒），默认 1800
# 挂载约定：
#   /mnt/profile    账号 ~/.claude profile（OAuth token 等），只读复制到 /root/.claude
#   /etc/mitm       MITM CA 目录，含 mitmproxy-ca-cert.pem
#   /workspace      claude 工作目录（每个 run 独立）
# 退出码：
#   0    Stop hook 正常触发
#   124  达到 TIMEOUT_SEC 超时
#   其它 启动失败
# =======================================================================
set -euo pipefail

: "${TASK_PROMPT:?TASK_PROMPT required}"
: "${RUN_ID:?RUN_ID required}"
TIMEOUT_SEC="${TIMEOUT_SEC:-1800}"

log() { echo "[entrypoint $(date +%H:%M:%S)] $*"; }

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

# ---------- 2) 复制账号 profile 到 /root/.claude ----------
mkdir -p /root/.claude
if [ -d /mnt/profile ]; then
  log "Copying account profile from /mnt/profile -> /root/.claude"
  cp -a /mnt/profile/. /root/.claude/
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
