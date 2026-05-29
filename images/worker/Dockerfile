# =======================================================================
# Worker 镜像：跑真实交互式 Claude Code 完成一道题
# =======================================================================
# - 基础：node 22（Claude Code 是 Node CLI）
# - 工具链：python / git / build-essential，覆盖大部分题目所需运行时
# - MITM CA：由 entrypoint 在容器启动时注入到系统证书库 + 各语言运行时
# - 驱动：tmux session 内启动 `claude`，通过粘贴缓冲注入题目 prompt
# - 完成判定：Stop hook 只记录回合结束，最终以稳定的 JSONL assistant 文本为准
# =======================================================================
FROM node:22-bookworm-slim

ENV DEBIAN_FRONTEND=noninteractive
ENV CLAUDE_CODE_VERSION=2.1.156

RUN apt-get update && apt-get install -y --no-install-recommends \
      python3 python3-pip python3-venv pipx \
      build-essential pkg-config \
      git curl wget unzip \
      ca-certificates \
      tmux jq ripgrep \
      tini \
    && rm -rf /var/lib/apt/lists/*

# 安装 Claude Code CLI。版本要和 orchestrator/worker 里 usage 请求的 UA 保持一致。
RUN npm install -g @anthropic-ai/claude-code@${CLAUDE_CODE_VERSION} \
    && claude --version || true

# 默认非 root 跑可能更安全，但 OAuth profile / CA 安装都要 root 权限，先用 root
WORKDIR /workspace

COPY entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh

# tini 当 init，处理孤儿进程
ENTRYPOINT ["/usr/bin/tini", "--", "/usr/local/bin/entrypoint.sh"]
