#!/usr/bin/env python3
"""由当前 v3 CI 发布完整平台发行，再原子推进签名目录分支。"""
from __future__ import annotations

import hashlib
import argparse
import json
import os
import subprocess
import tempfile
from pathlib import Path

from system_release import REPO, create_index, create_release, sign_file
from platform_version import ensure_forward_version, read_version, signed_changes
from release_ci import validate_publish_source
from datetime import datetime, timedelta, timezone
from system_update_contract import INDEX_LIMIT, MANIFEST_LIMIT, REPOSITORY, strict_json, verify_signed, utc_now, validate_index, validate_release


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


def publish(manifest: Path, bundle: Path, private_key: str, migration_evidence: Path | None = None) -> dict:
    """发布当前 Action 的精确发行和有界目录，私钥只存临时私有文件。

    :param manifest: 已完成的联合发布清单。
    :param bundle: 同批完整镜像包。
    :param private_key: CI 私有 Ed25519 PEM。
    :param migration_evidence: 真实镜像兼容验收证据；正式入口必需。
    :return: 本次发布事实。
    """
    build = strict_json(manifest.read_bytes())
    metadata = read_version(Path(__file__).with_name('platform-release.json'))
    validate_publish_source(build)
    if not os.environ.get('GH_TOKEN'):
        raise ValueError('系统发行缺少当前 Action 的发布令牌')
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
        channel = 'updates/v3-migrations' if migration_evidence is not None else 'updates/v3'
        catalogs = {}
        for name in dict.fromkeys((channel, 'updates/v3')):
            catalogs[name] = _read_catalog(name, public)
        # 工作流拆分会重置 run_number；序号从已验签历史连续推进。
        highest = max((entry[0]['sequence'][0] for entry in catalogs.values() if entry), default=0)
        if highest >= 2 ** 53 - 1:
            raise ValueError('发行顺序已到达安全整数上限')
        release = create_release(manifest, Path(__file__).with_name('system-update-policy.json'), root / 'release', key,
            [highest + 1, int(os.environ['GITHUB_RUN_ATTEMPT'])],
            signed_changes(metadata), migration_evidence=migration_evidence)
        previous, parent = None, None
        selected = catalogs[channel] or catalogs['updates/v3']
        if catalogs[channel]:
            parent = catalogs[channel][2]
        if selected:
            _, raw, _ = selected
            previous = root / 'previous.json'
            previous.write_bytes(raw)
        if previous:
            # 沿原已签目录定位完整旧清单；版本属于说明展示，安装身份仍以原摘要为准。
            previous_value = strict_json(previous.read_bytes(), INDEX_LIMIT)
            # 发布需要更新过期通道；历史签名目录按其签发时刻校验原合同。
            previous_index = validate_index(previous_value,
                now=datetime.fromisoformat(previous_value['issued_at'].replace('Z', '+00:00')).timestamp())
            latest = previous_index['releases'][0]
            previous_folder = root / 'previous-release'
            previous_folder.mkdir()
            run('gh', 'release', 'download', latest['release'], '--repo', REPOSITORY,
                '--pattern', 'system-release.json', '--dir', str(previous_folder))
            previous_raw = (previous_folder / 'system-release.json').read_bytes()
            if len(previous_raw) != latest['manifest']['size'] or hashlib.sha256(previous_raw).hexdigest() != latest['manifest']['sha256']:
                raise ValueError('原平台版本清单摘要不符')
            ensure_forward_version(release, validate_release(strict_json(previous_raw, MANIFEST_LIMIT)))
        index = root / 'index.json'
        create_index(root / 'release/system-release.json', previous, index, key)
        notes = root / 'notes.md'
        notes.write_text(f'{signed_changes(metadata)}\n\n发行：{release["release"]}\n来源：{build["parent_revision"]}\n\n安装与回退兼容条件见 system-release.json。\n')
        tag = release['release']
        run('gh', 'release', 'create', tag, '--repo', REPOSITORY, '--target', build['parent_revision'],
            '--draft', '--title', metadata['version'], '--notes-file', str(notes))
        run('gh', 'release', 'upload', tag, '--repo', REPOSITORY,
            str(root / 'release/system-release.json'), str(root / 'release/system-release.sig'),
            str(root / 'release/v3.json'), str(bundle))
        if release['schema_version'] == 2:
            run('gh', 'release', 'upload', tag, '--repo', REPOSITORY, str(root / 'release/database-migrations.json'), str(root / 'release/database-compatibility.json'))
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
        run('git', 'push', 'origin', commit + ':refs/heads/' + channel)
        if release['schema_version'] == 2:
            refresh_legacy_catalog(root, key, public, release['sequence'])
        return {'status': 'published', 'release': tag, 'catalog_commit': commit}


def _read_catalog(channel: str, public_key: str) -> tuple[dict, bytes, str] | None:
    """按原信任根读取目录，并在签发时刻核对历史合同。"""
    reference = run('git', 'ls-remote', 'origin', 'refs/heads/' + channel).decode().strip()
    if not reference:
        return None
    run('git', 'fetch', '--depth=1', 'origin', 'refs/heads/' + channel)
    parent = run('git', 'rev-parse', 'FETCH_HEAD').decode().strip()
    raw = run('git', 'show', parent + ':index.json')
    value = verify_signed(raw, run('git', 'show', parent + ':index.sig'), public_key, INDEX_LIMIT)
    value = validate_index(value, now=datetime.fromisoformat(value['issued_at'].replace('Z', '+00:00')).timestamp())
    return value, raw, parent


def check_signing_key() -> None:
    """在构建前核对手动来源及 Ed25519 签名材料。

    :return: None；私钥缺失或类型不符时抛出 ValueError。
    """
    validate_publish_source()
    private_key = os.environ.get('V3_SYSTEM_RELEASE_PRIVATE_KEY', '')
    if not private_key.strip():
        raise ValueError('正式发布需要配置 V3_SYSTEM_RELEASE_PRIVATE_KEY')
    with tempfile.TemporaryDirectory(prefix='v3-signing-check-') as temporary:
        key = Path(temporary) / 'key.pem'
        with key.open('x') as stream:
            os.fchmod(stream.fileno(), 0o600)
            stream.write(private_key)
        public = run('openssl', 'pkey', '-in', str(key), '-pubout', '-outform', 'DER')
        if len(public) != 44 or not public.startswith(bytes.fromhex('302a300506032b6570032100')):
            raise ValueError('平台发行签名密钥必须为 Ed25519')


def refresh_legacy_catalog(root: Path, key: Path, public_key: str, sequence: list[int]) -> None:
    """刷新旧通道已支持发行的有效期，保持旧格式目录可用。

    :param root: 本次私有临时根。
    :param key: 本次私有签名文件。
    :param public_key: 原信任根公钥。
    :param sequence: 本批目录顺序。
    :return: None；外来后来目录保持 fast-forward 保护。
    """
    reference = run('git', 'ls-remote', 'origin', 'refs/heads/updates/v3').decode().strip()
    if not reference:
        return
    run('git', 'fetch', '--depth=1', 'origin', 'refs/heads/updates/v3')
    parent = run('git', 'rev-parse', 'FETCH_HEAD').decode().strip()
    value = verify_signed(run('git', 'show', parent + ':index.json'), run('git', 'show', parent + ':index.sig'), public_key, INDEX_LIMIT)
    if value['sequence'] >= sequence:
        return
    # v1 序号必须对应目录内最新发行；刷新有效期继续使用原发行序号。
    value.update(issued_at=utc_now(), expires_at=(datetime.now(timezone.utc)+timedelta(days=30)).isoformat(timespec='seconds').replace('+00:00','Z'))
    validate_index(value)
    folder = root / 'legacy'
    folder.mkdir()
    (folder / 'index.json').write_text(json.dumps(value, ensure_ascii=False, separators=(',', ':')))
    sign_file(folder / 'index.json', key)
    blobs = {name: run('git', 'hash-object', '-w', '--stdin', data=(folder / name).read_bytes()).decode().strip() for name in ('index.json','index.sig')}
    tree = run('git', 'mktree', data=''.join(f'100644 blob {digest}\t{name}\n' for name,digest in sorted(blobs.items())).encode()).decode().strip()
    environment = {**os.environ, 'GIT_AUTHOR_NAME':'v3-system-release','GIT_AUTHOR_EMAIL':'v3-system-release@users.noreply.github.com',
        'GIT_COMMITTER_NAME':'v3-system-release','GIT_COMMITTER_EMAIL':'v3-system-release@users.noreply.github.com'}
    commit = run('git','commit-tree',tree,'-p',parent,data='刷新旧受信目录有效期\n'.encode(),environment=environment).decode().strip()
    run('git','push','origin',commit+':refs/heads/updates/v3')


def main() -> None:
    """预检签名材料或执行已确认的同批签名发布。

    :return: None。
    """
    parser = argparse.ArgumentParser(description='平台手动签名发行')
    parser.add_argument('--check-signing', action='store_true')
    arguments = parser.parse_args()
    check_signing_key()
    if arguments.check_signing:
        print(json.dumps({'status': 'signing_ready'}))
        return
    key = os.environ['V3_SYSTEM_RELEASE_PRIVATE_KEY']
    evidence = REPO / 'releases/database-compatibility.json'
    if not evidence.is_file():
        raise ValueError('真实数据库升级与回退演练证据缺失，停止签名发布')
    print(json.dumps(publish(REPO / 'releases/v3.json', REPO / 'releases/v3-images.tar.gz', key, evidence), ensure_ascii=False))


if __name__ == '__main__':
    main()
