"""用隔离、无网络工具探针证明精简备份的可重建程序来源。"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
from stat import S_ISREG
import subprocess
import tempfile
from urllib.parse import urlsplit
import uuid

from storage_maintenance import read_storage_json, tree_inventory


def _document(path: Path) -> dict:
    value = read_storage_json(path, maximum_bytes=4 * 1024**2, private=False)
    if not isinstance(value, dict):
        raise ValueError('程序恢复元数据不是对象')
    return value


def _probe(reference: str, directory: Path, script: str, *, cache: Path | None = None) -> str:
    name = 'v3-storage-probe-' + uuid.uuid4().hex
    arguments = ['docker', 'run', '--rm', '--pull=never', '--name', name, '--label', 'vibebench.storage-probe=' + name,
        '--network=none', '--read-only', '--cap-drop=ALL', '--security-opt=no-new-privileges',
        '--memory=768m', '--pids-limit=128', '--tmpfs', '/tmp:rw,nosuid,nodev,size=64m',
        '--tmpfs', '/root:rw,nosuid,nodev,size=32m', '--volume', str(directory) + ':/storage:rw']
    if cache is None:
        arguments.extend(['--entrypoint', 'python3', reference, '-B', '-c', script])
    else:
        arguments.extend(['--volume', str(cache) + ':/cache:ro', '--entrypoint', '/bin/sh',
            reference, '-eu', '-c', script])
    try:
        return subprocess.run(arguments, capture_output=True, text=True, check=True, timeout=180).stdout
    finally:
        # Docker 客户端超时不代表容器已退出；只收口带本次唯一标记的探针。
        inspected = subprocess.run(['docker', 'inspect', '--format',
            '{{index .Config.Labels "vibebench.storage-probe"}}', name], capture_output=True, text=True, timeout=15)
        if inspected.returncode == 0 and inspected.stdout.strip() == name:
            subprocess.run(['docker', 'rm', '-f', name], capture_output=True, check=True, timeout=30)


def _directory(root: Path, relative: str) -> Path | None:
    current = root
    for part in relative.split('/'):
        if part in ('', '.', '..'):
            raise ValueError('恢复程序目录路径无效')
        current = current / part
        if current.is_symlink() or not current.is_dir():
            return None
    return current


def cli_recovery_recipe(version: Path) -> dict:
    """核对精确 CLI 安装和公开依赖锁，读取可信安装回执。

    :param version: 一个受保护的已就绪版本目录。
    :return: 依赖锁、逻辑文件清单及可选的 root 安装证明。
    """
    name = version.name
    if not re.fullmatch(r'\d+\.\d+\.\d+(?:[-+][A-Za-z0-9._-]+)?', name):
        raise ValueError('CLI 版本目录名不合法')
    ready = version / '.ready'
    if ready.is_symlink() or not ready.is_file():
        raise ValueError('CLI 版本尚未就绪')
    package = _document(version / 'package.json')
    lock = _document(version / 'package-lock.json')
    definition = _document(version / 'node_modules/@anthropic-ai/claude-code/package.json')
    entry = lock.get('packages', {}).get('node_modules/@anthropic-ai/claude-code', {})
    if definition.get('name') != '@anthropic-ai/claude-code' or definition.get('version') != name or entry.get('version') != name:
        raise ValueError('CLI 安装元数据版本不一致')
    for value in lock.get('packages', {}).values():
        if 'resolved' not in value:
            continue
        source = urlsplit(value['resolved'])
        if (source.scheme != 'https' or source.hostname != 'registry.npmjs.org' or source.username
                or source.password or not re.fullmatch(r'sha512-[A-Za-z0-9+/=]+', value.get('integrity', ''))):
            raise ValueError('CLI 依赖没有固定的公开来源和完整性摘要')
    executable = (version / 'node_modules/.bin/claude').resolve(strict=True)
    if not executable.is_relative_to(version.resolve()) or not executable.is_file():
        raise ValueError('CLI 程序入口越过版本目录')
    inventory = tree_inventory(version)
    item = inventory[str(executable.relative_to(version.resolve()))]
    receipt_path = version / '.v3-cli-install.json'
    receipt = None
    if receipt_path.exists():
        value = _document(receipt_path)
        if (receipt_path.stat().st_uid == 0 and receipt_path.stat().st_mode & 0o077 == 0
                and value.get('schema') == 1 and value.get('protocol') == 2 and value.get('version') == name
                and value.get('program_sha256') == item['sha256']
                and value.get('lock_sha256') == inventory['package-lock.json']['sha256']
                and value.get('package_sha256') == inventory['package.json']['sha256']):
            receipt = value
    return {'kind': 'npm-cli', 'version': name, 'package': package, 'lock': lock, 'install_receipt': receipt,
        'executable_sha256': item['sha256'], 'files': inventory}


def _recipe_key(recipe: dict) -> tuple:
    return (recipe['version'], recipe['executable_sha256'],
        hashlib.sha256(json.dumps(recipe['lock'], sort_keys=True).encode()).hexdigest())


def _completed_cli_proofs(root: Path, manifest: dict, parent: Path, deployment: str | None) -> dict:
    proofs = {}
    if deployment is None:
        return proofs
    platform = manifest.get('images', {}).get('account', {}).get('platform')
    for previous in parent.iterdir():
        if (previous.is_symlink() or not previous.is_dir() or previous.stat().st_mode & 0o077
                or previous.stat().st_uid != os.geteuid()):
            continue
        try:
            marker = read_storage_json(previous / '.v3-backup.json')
            if (marker.get('schema') != 2 or marker.get('source_root') != str(root)
                    or marker.get('deployment') != deployment or marker.get('verified', {}).get('status') != 'passed'
                    or marker.get('verified', {}).get('isolated_restore') is not True):
                continue
            metadata_path = previous / 'backup-files.json'
            document = read_storage_json(metadata_path)
            descriptor = os.open(metadata_path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
            with os.fdopen(descriptor, 'rb') as source:
                metadata = os.fstat(source.fileno())
                if not S_ISREG(metadata.st_mode) or metadata.st_size > 64 * 1024**2:
                    continue
                metadata_hash = hashlib.file_digest(source, 'sha256').hexdigest()
            if marker.get('files_manifest_sha256') != metadata_hash:
                continue
            previous_release = read_storage_json(previous / 'release.json')
            if previous_release.get('images', {}).get('account', {}).get('platform') != platform:
                continue
            for recipe in document.get('excluded', {}).values():
                verification = recipe.get('source_verification')
                if recipe.get('kind') == 'npm-cli' and verification in ('root-install-receipt-v2', 'offline-npm-rebuild'):
                    proofs[_recipe_key(recipe)] = verification
        except (OSError, ValueError, KeyError, AttributeError, TypeError):
            continue
    return proofs


def essential_exclusions(root: Path, manifest: dict, *, temporary_parent: Path,
                         deployment: str | None = None) -> dict[str, dict]:
    """证明可重建程序后生成精确排除项，证据不足时保留原文件。

    :param root: 停机且归属已验证的数据根。
    :param manifest: 已校验的同批正式镜像清单。
    :param temporary_parent: 本次私有备份的受控父目录。
    :param deployment: 可选的已验证部署归属，用于复用最近完整恢复点的程序来源证明。
    :return: 相对路径到恢复来源的映射，不包含凭据内容。
    """
    excluded = {}
    environments = _directory(root, 'bench/environments')
    account = manifest.get('images', {}).get('account', {}).get('reference')
    control = manifest.get('images', {}).get('control', {}).get('reference')
    # 已清理下载缓存后仍可复用同部署已完成恢复点的证明，避免后续又整套复制程序。
    verified_programs = _completed_cli_proofs(root, manifest, temporary_parent, deployment)
    if environments is not None:
        for environment in sorted(environments.iterdir()):
            if environment.is_symlink() or not environment.is_dir():
                continue
            for relative in ('home/.npm/_cacache', 'cli/.npm-cache/_cacache'):
                path = _directory(environment, relative)
                if path is not None:
                    excluded[str(path.relative_to(root))] = {'kind': 'npm-download-cache', 'recovery': '按原依赖锁重新下载'}
            cli = _directory(environment, 'cli')
            if cli is None or not account:
                continue
            for version in sorted(cli.iterdir()):
                if version.is_symlink() or not version.is_dir() or version.name.startswith('.'):
                    continue
                try:
                    recipe = cli_recovery_recipe(version)
                    key = _recipe_key(recipe)
                    if recipe['install_receipt'] is not None:
                        verified_programs[key] = 'root-install-receipt-v2'
                    if key not in verified_programs:
                        cache = _directory(environment, 'cli/.npm-cache')
                        if cache is None:
                            continue
                        with tempfile.TemporaryDirectory(prefix='.v3-cli-recovery-', dir=temporary_parent) as scratch:
                            prepared = Path(scratch)
                            install = prepared / 'install'
                            install.mkdir()
                            (install / 'package.json').write_text(json.dumps(recipe['package']))
                            (install / 'package-lock.json').write_text(json.dumps(recipe['lock']))
                            script = "npm ci --prefix /storage/install --offline --ignore-scripts --cache /cache --logs-dir /tmp/npm-logs --no-audit --no-fund >/tmp/npm.log 2>&1\n/storage/install/node_modules/.bin/claude --version >/storage/observed-version\n"
                            _probe(account, prepared, script, cache=cache)
                            observed = (prepared / 'observed-version').read_text().strip().split()[0]
                            program = (install / 'node_modules/.bin/claude').resolve(strict=True)
                            restored = tree_inventory(install)
                            if (observed != recipe['version'] or not program.is_relative_to(install)
                                    or restored[str(program.relative_to(install))]['sha256'] != recipe['executable_sha256']):
                                continue
                            verified_programs[key] = 'offline-npm-rebuild'
                    if verified_programs.get(key):
                        recipe['source_verification'] = verified_programs[key]
                        excluded[str(version.relative_to(root))] = recipe
                except (OSError, ValueError, KeyError, subprocess.SubprocessError):
                    # 部分旧 CLI/浏览器缺少可离线证明的恢复来源，必须保留而非扩大排除。
                    continue
    store = _directory(root, 'bench/cli-artifacts')
    if store is not None:
        expected = {item['sha256'] for recipe in excluded.values() if recipe.get('kind') == 'npm-cli'
            for item in recipe['files'].values() if item['kind'] == 'file'}
        inventory = tree_inventory(store)
        if all(relative == '.' or (item['kind'] == 'file' and item['sha256'] in expected
                and re.fullmatch(r'[0-9a-f]{64}\.[0-7]+\.0\.\d+', relative))
                for relative, item in inventory.items()):
            excluded['bench/cli-artifacts'] = {'kind': 'shared-cli-artifacts', 'recovery': '按CLI依赖锁和程序摘要重建'}
    releases = _directory(root, 'bench/project-library/releases')
    if releases is not None and control:
        try:
            with tempfile.TemporaryDirectory(prefix='.v3-content-recovery-', dir=temporary_parent) as scratch:
                prepared = Path(scratch)
                script = "from pathlib import Path\nfrom project_library import ProjectLibrary\nvalue=ProjectLibrary(Path('/repo/project_library')).install(Path('/storage'))\nprint(value.digest)\n"
                digest = _probe(control, prepared, script).strip()
                if re.fullmatch(r'[0-9a-f]{64}', digest):
                    candidate = _directory(releases, digest)
                    rebuilt = prepared / 'project-library/releases' / digest
                    if candidate is not None and tree_inventory(candidate) == tree_inventory(rebuilt):
                        excluded[str(candidate.relative_to(root))] = {'kind': 'project-catalog', 'digest': digest,
                            'image': manifest['images']['control'], 'isolated_rebuild': True}
        except (OSError, ValueError, subprocess.SubprocessError):
            pass
    return excluded
