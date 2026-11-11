#!/usr/bin/env python3
"""由当前 v3 CI 发布完整平台发行，再原子推进签名目录分支。"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import tempfile
from pathlib import Path

from system_release import REPO, create_index, create_release
from system_update_contract import INDEX_LIMIT, REPOSITORY, strict_json, verify_signed


def run(*arguments: str, data: bytes | None = None, environment: dict | None = None) -> bytes:
    """执行固定 CI 命令，隐藏底层鉴权输出。

    :param arguments: 完整 argv。
    :param data: 可选 stdin 原字节。
    :param environment: Git 作者等环境。
    :return: 捕获输出。
    """
    result = subprocess.run(arguments, input=data, cwd=REPO, env=environment,
        capture_output=True, check=False, timeout=1800)
    if result.returncode:
        raise RuntimeError('受信系统发行发布失败，保留当前目录和已完成事实')
    return result.stdout


def publish(manifest: Path, bundle: Path, private_key: str) -> dict:
    """发布当前 Action 的精确发行和有界目录，私钥只存临时私有文件。

    :param manifest: 已完成的联合发布清单。
    :param bundle: 同批完整镜像包。
    :param private_key: CI 私有 Ed25519 PEM。
    :return: 本次发布事实。
    """
    build = strict_json(manifest.read_bytes())
    expected = f'ci-{os.environ.get("GITHUB_RUN_ID", "")}-{os.environ.get("GITHUB_RUN_ATTEMPT", "")}'
    if (os.environ.get('GITHUB_ACTIONS') != 'true' or os.environ.get('GITHUB_REF') != 'refs/heads/v3'
            or os.environ.get('GITHUB_REPOSITORY', '').lower() != REPOSITORY.lower()
            or build.get('release') != expected or build.get('parent_revision') != os.environ.get('GITHUB_SHA')
            or build.get('dirty_worktree') is not False or not os.environ.get('GH_TOKEN')):
        raise ValueError('系统发行只能发布当前 v3 Action 的完整同批来源')
    if build['bundle']['name'] != bundle.name or build['bundle']['size'] != bundle.stat().st_size:
        raise ValueError('系统发行镜像包身份不匹配')
    with bundle.open('rb') as stream:
        if hashlib.file_digest(stream, 'sha256').hexdigest() != build['bundle']['sha256']:
            raise ValueError('系统发行镜像包摘要不符')
    with tempfile.TemporaryDirectory(prefix='v3-system-publish-') as temporary:
        root = Path(temporary)
        key = root / 'key.pem'
        with key.open('x') as stream:
            os.fchmod(stream.fileno(), 0o600)
            stream.write(private_key)
        public = run('openssl', 'pkey', '-in', str(key), '-pubout', '-outform', 'DER')[-32:].hex()
        release = create_release(manifest, Path(__file__).with_name('system-update-policy.json'), root / 'release', key,
            [int(os.environ['GITHUB_RUN_NUMBER']), int(os.environ['GITHUB_RUN_ATTEMPT'])],
            '平台联合更新。组件变化与回退条件由受信清单核验。')
        reference = run('git', 'ls-remote', 'origin', 'refs/heads/updates/v3').decode().strip()
        previous, parent = None, None
        if reference:
            run('git', 'fetch', '--depth=1', 'origin', 'refs/heads/updates/v3')
            parent = run('git', 'rev-parse', 'FETCH_HEAD').decode().strip()
            raw = run('git', 'show', parent + ':index.json')
            signature = run('git', 'show', parent + ':index.sig')
            old = verify_signed(raw, signature, public, INDEX_LIMIT)
            if old.get('sequence', []) >= release['sequence']:
                return {'status': 'skipped', 'reason': '通道已有更新的完整发行', 'release': release['release']}
            previous = root / 'previous.json'
            previous.write_bytes(raw)
        index = root / 'index.json'
        create_index(root / 'release/system-release.json', previous, index, key)
        notes = root / 'notes.md'
        notes.write_text(f'平台发行 {release["release"]}\n\n来源：{build["parent_revision"]}\n\n安装与回退兼容条件见 system-release.json。\n')
        tag = release['release']
        run('gh', 'release', 'create', tag, '--repo', REPOSITORY, '--target', build['parent_revision'],
            '--draft', '--title', tag, '--notes-file', str(notes))
        run('gh', 'release', 'upload', tag, '--repo', REPOSITORY,
            str(root / 'release/system-release.json'), str(root / 'release/system-release.sig'),
            str(root / 'release/v3.json'), str(bundle))
        run('gh', 'release', 'edit', tag, '--repo', REPOSITORY, '--draft=false', '--latest=false')
        blobs = {}
        for name in ('index.json', 'index.sig'):
            blobs[name] = run('git', 'hash-object', '-w', '--stdin', data=(root / name).read_bytes()).decode().strip()
        tree = run('git', 'mktree', data=''.join(f'100644 blob {digest}\t{name}\n' for name, digest in sorted(blobs.items())).encode()).decode().strip()
        environment = {**os.environ, 'GIT_AUTHOR_NAME': 'v3-system-release', 'GIT_AUTHOR_EMAIL': 'v3-system-release@users.noreply.github.com',
            'GIT_COMMITTER_NAME': 'v3-system-release', 'GIT_COMMITTER_EMAIL': 'v3-system-release@users.noreply.github.com'}
        commit = run('git', 'commit-tree', tree, *(['-p', parent] if parent else []),
            data=f'更新受信平台目录 {tag}\n'.encode(), environment=environment).decode().strip()
        # 普通 fast-forward push 保留竞争保护；发布失败不能 force 覆盖后来目录。
        run('git', 'push', 'origin', commit + ':refs/heads/updates/v3')
        return {'status': 'published', 'release': tag, 'catalog_commit': commit}


def main() -> None:
    """在配置独立私钥后启用发布，缺少密钥时保留现有镜像交付。

    :return: None。
    """
    key = os.environ.get('V3_SYSTEM_RELEASE_PRIVATE_KEY', '')
    if not key:
        print(json.dumps({'status': 'skipped', 'reason': 'signing_not_configured'}))
        return
    print(json.dumps(publish(REPO / 'releases/v3.json', REPO / 'releases/v3-images.tar.gz', key), ensure_ascii=False))


if __name__ == '__main__':
    main()
