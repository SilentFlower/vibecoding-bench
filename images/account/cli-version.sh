#!/usr/bin/env bash
# 按精确版本缓存官方 CLI；完成标记只在版本检查通过后写入。
set -euo pipefail
# root 安装工具使用私有缓存，不能把账号用户的 HOME 缓存写成 root 所有。
export HOME=/root
export NPM_CONFIG_CACHE=/cli/.npm-cache
version="${1:?需要 CLI 版本}"
[[ "$version" =~ ^[0-9]+\.[0-9]+\.[0-9]+([-+][A-Za-z0-9._-]+)?$ ]] || exit 2
[[ ! -L /cli && ! -L /cli/.npm-cache ]] || exit 4
mkdir -p /cli
chmod 755 /cli
exec 9>/run/v3/cli-install.lock
flock 9
prefix="/cli/$version"
[[ ! -L "$prefix" && ! -L "$prefix/.ready" ]] || exit 4
cli_stage_dir=""
cli_previous_dir=""

# 保留原失败码和旧就绪版本，避免重装时改写其他账号共享的程序 inode。
# @return 原安装退出码；已验证程序不因可重建缓存回收失败而停用。
_cleanup_install() {
  cli_result=$?
  cli_install_result=$cli_result
  trap - EXIT
  if [[ -n "$cli_previous_dir" && ! -e "$prefix" ]]; then
    mv -T -- "$cli_previous_dir" "$prefix" || cli_result=1
    cli_previous_dir=""
  fi
  if [[ -n "$cli_stage_dir" ]]; then
    rm -rf -- "$cli_stage_dir" || cli_result=1
  fi
  if [[ -n "$cli_previous_dir" && -f "$prefix/.ready" ]]; then
    rm -rf -- "$cli_previous_dir" || cli_result=1
  fi
  rm -rf -- "$NPM_CONFIG_CACHE/_cacache" "$NPM_CONFIG_CACHE/_logs" || cli_result=1
  if [[ "$cli_install_result" -eq 0 && -f "$prefix/.ready" ]]; then
    exit 0
  fi
  if [[ "$cli_install_result" -ne 0 ]]; then
    exit "$cli_install_result"
  fi
  exit "$cli_result"
}

trap _cleanup_install EXIT
# 取得安装锁后旧子进程已退出，SIGKILL 遗留的同版本暂存仅是可重建程序。
for cli_orphan in "/cli/.install-$version."???????? "/cli/.previous-$version."????????; do
  if [[ -d "$cli_orphan" && ! -L "$cli_orphan" ]]; then
    rm -rf -- "$cli_orphan" || true
  fi
done
if [ ! -f "$prefix/.ready" ]; then
  cli_stage_dir="$(mktemp -d "/cli/.install-$version.XXXXXXXX")"
  npm install --prefix "$cli_stage_dir" --save-exact --no-audit --no-fund "@anthropic-ai/claude-code@$version" >/var/log/v3-cli-install.log 2>&1
  actual="$("$cli_stage_dir/node_modules/.bin/claude" --version)"
  [[ "$actual" == "$version "* || "$actual" == "$version" ]] || exit 3
  python3 - "$cli_stage_dir" "$version" <<'PY'
import hashlib
import json
import os
from pathlib import Path
import sys

root = Path(sys.argv[1]).resolve()
program = (root / 'node_modules/.bin/claude').resolve(strict=True)
if not program.is_relative_to(root):
    raise ValueError('CLI 安装程序越过暂存目录')
digests = {}
for label, path in [('program_sha256', program), ('lock_sha256', root / 'package-lock.json'),
                    ('package_sha256', root / 'package.json')]:
    with path.open('rb') as source:
        digests[label] = hashlib.file_digest(source, 'sha256').hexdigest()
descriptor = os.open(root / '.v3-cli-install.json', os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
with os.fdopen(descriptor, 'w') as output:
    json.dump({'schema': 1, 'protocol': 2, 'version': sys.argv[2], **digests}, output)
    output.flush()
    os.fsync(output.fileno())
PY
  chmod -R go-w "$cli_stage_dir"
  chmod 755 "$cli_stage_dir"
  touch "$cli_stage_dir/.ready"
  if [[ -e "$prefix" ]]; then
    cli_previous_dir="$(mktemp -d "/cli/.previous-$version.XXXXXXXX")"
    rmdir -- "$cli_previous_dir"
    mv -T -- "$prefix" "$cli_previous_dir"
  fi
  mv -T -- "$cli_stage_dir" "$prefix"
  cli_stage_dir=""
fi
