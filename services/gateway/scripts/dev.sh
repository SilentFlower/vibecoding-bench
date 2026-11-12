#!/bin/bash
# 本地开发：构建前端 + 运行 Rust 后端
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_DIR"
WEB_DIR="$PROJECT_DIR/../../apps/web"

# 安装前端依赖（如果缺失）
if [ ! -d "$WEB_DIR/node_modules/@vue/tsconfig" ]; then
    echo "Installing frontend dependencies..."
    (cd "$WEB_DIR" && npm ci)
fi

# 检测前端源码是否比 dist 更新
NEED_BUILD=0
if [ ! -d "$WEB_DIR/dist" ]; then
    NEED_BUILD=1
else
    # 找到 web/src 下最新修改的文件时间戳
    LATEST_SRC=$(find "$WEB_DIR/src" -type f -newer "$WEB_DIR/dist" -print -quit 2>/dev/null)
    # 同时检查 web 根目录的配置文件
    for f in "$WEB_DIR/index.html" "$WEB_DIR/vite.config.ts" "$WEB_DIR/tsconfig.json" "$WEB_DIR/package.json"; do
        if [ -f "$f" ] && [ "$f" -nt "$WEB_DIR/dist" ]; then
            LATEST_SRC="$f"
            break
        fi
    done
    if [ -n "$LATEST_SRC" ]; then
        NEED_BUILD=1
    fi
fi

if [ "$NEED_BUILD" -eq 1 ]; then
    echo "Frontend changed, rebuilding..."
    (cd "$WEB_DIR" && npm run build)
else
    echo "Frontend up to date, skipping build."
fi

# 运行
cargo run "$@"
