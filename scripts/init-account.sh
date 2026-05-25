#!/usr/bin/env bash
# =======================================================================
# OAuth profile 引导脚本 (LEGACY · CLI fallback)
# =======================================================================
# 推荐：直接在 WebUI 「accounts」页点 [ + 添加账号 ]，里面有内嵌 PTY 终端，
#       会自动起带 SOCKS5 sidecar 的 worker，OAuth 走代理，登完一键入库。
#
# 本脚本仅保留给「不想跑 orchestrator」的纯 CLI 场景。
# ⚠ 已知限制：本脚本不走 sidecar，OAuth 流量直接走宿主默认网络，
#   与后续 API 调用的出口 IP 不一致，可能被 Anthropic 风控。
#
# 用法：./scripts/init-account.sh <account_name>
#
# 在一个临时 worker 容器里启动交互式 claude，用户跟着 TUI 提示完成
# /login 流程（复制 URL → 浏览器授权 → 粘贴授权码回 TUI）。
# 完成后退出 claude，OAuth token 已经落到 data/profiles/<account_name>/。
# =======================================================================
set -euo pipefail

if [ $# -lt 1 ]; then
  echo "Usage: $0 <account_name>"
  echo "Example: $0 main"
  exit 1
fi

ACCOUNT_NAME="$1"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
BENCH_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
PROFILE_DIR="$BENCH_ROOT/data/profiles/$ACCOUNT_NAME"

# 校验账号名（避免奇怪字符）
if ! [[ "$ACCOUNT_NAME" =~ ^[a-zA-Z0-9_-]+$ ]]; then
  echo "ERROR: account name must match [a-zA-Z0-9_-]+"
  exit 1
fi

if [ -d "$PROFILE_DIR" ] && [ -n "$(ls -A "$PROFILE_DIR" 2>/dev/null)" ]; then
  echo "Profile already exists at $PROFILE_DIR"
  read -r -p "Re-login and overwrite? [y/N] " yn
  if [[ ! "$yn" =~ ^[Yy]$ ]]; then
    echo "Aborted."
    exit 0
  fi
  rm -rf "$PROFILE_DIR"
fi

mkdir -p "$PROFILE_DIR"

# 校验 worker 镜像存在
if ! docker image inspect vibebench-worker:latest >/dev/null 2>&1; then
  echo "ERROR: vibebench-worker:latest image not found. Build it first:"
  echo "  cd $BENCH_ROOT && docker compose build worker-image"
  exit 1
fi

echo
echo "================================================================"
echo " Launching interactive claude for OAuth login."
echo " 1. Run '/login' inside claude TUI."
echo " 2. Copy the URL it prints to your browser, finish OAuth there."
echo " 3. Paste the auth code back into the TUI."
echo " 4. Type '/exit' (or press Ctrl+D) to leave when done."
echo " Profile target: $PROFILE_DIR"
echo "================================================================"
echo

docker run -it --rm \
  --name "claude-login-$ACCOUNT_NAME-$$" \
  --entrypoint bash \
  -v "$PROFILE_DIR:/root/.claude" \
  vibebench-worker:latest \
  -c 'cd /tmp && claude || true; echo; echo "Login session ended. Profile contents:"; ls -la /root/.claude'

# 简单校验：profile 目录里应该有东西（最常见是 .credentials.json 或 config.json）
if [ -z "$(ls -A "$PROFILE_DIR" 2>/dev/null)" ]; then
  echo
  echo "WARNING: $PROFILE_DIR is empty. Login likely did not complete."
  exit 2
fi

echo
echo "================================================================"
echo " Profile saved: $PROFILE_DIR"
echo " Next: add this account in the WebUI"
echo "   - name: $ACCOUNT_NAME"
echo "   - profile_path: data/profiles/$ACCOUNT_NAME"
echo "================================================================"
