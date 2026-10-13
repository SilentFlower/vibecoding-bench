#!/usr/bin/env bash
# 按精确版本缓存官方 CLI；完成标记只在版本检查通过后写入。
set -euo pipefail
# root 安装工具使用私有缓存，不能把账号用户的 HOME 缓存写成 root 所有。
export HOME=/root
export NPM_CONFIG_CACHE=/cli/.npm-cache
version="${1:?需要 CLI 版本}"
[[ "$version" =~ ^[0-9]+\.[0-9]+\.[0-9]+([-+][A-Za-z0-9._-]+)?$ ]] || exit 2
mkdir -p /cli
chmod 755 /cli
exec 9>/run/v3/cli-install.lock
flock 9
prefix="/cli/$version"
if [ ! -f "$prefix/.ready" ]; then
  mkdir -p "$prefix"
  npm install --prefix "$prefix" --no-audit --no-fund "@anthropic-ai/claude-code@$version" >/var/log/v3-cli-install.log 2>&1
  actual="$($prefix/node_modules/.bin/claude --version)"
  [[ "$actual" == "$version "* || "$actual" == "$version" ]] || exit 3
  chmod -R go-w "$prefix"
  touch "$prefix/.ready"
fi
