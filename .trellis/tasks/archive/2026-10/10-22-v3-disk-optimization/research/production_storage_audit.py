"""只读盘点美国部署的可重建缓存、CLI 制品和数据库版本引用。"""

import collections
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import stat
import subprocess
from urllib.parse import urlsplit


def directory_bytes(path: Path) -> int:
    """查询目录物理占用。@param path 已确认的本部署路径。@return 字节数。"""
    if not path.is_dir() or path.is_symlink():
        return 0
    output = subprocess.check_output(['du', '-x', '-s', '-B1', str(path)], text=True)
    return int(output.split()[0])


def main() -> None:
    """生成不含凭据或账号身份的只读研究报告。@return None。"""
    root = Path('/srv/vibebench-v3-us')
    bench = root / 'bench'
    deployment = json.loads((root / '.v3-deployment.json').read_text())
    if deployment.get('deployment') != 'us':
        raise ValueError('数据根部署归属不匹配')
    caches = collections.Counter()
    browser_packages = collections.Counter()
    cli_versions = collections.Counter()
    cli_groups = collections.defaultdict(list)
    cli_skipped = collections.Counter()
    environment_count = 0
    recipes = []
    browser_links = []
    for environment in (bench / 'environments').iterdir():
        if not environment.is_dir() or environment.is_symlink():
            continue
        environment_count += 1
        for relative in ('home/.npm/_cacache', 'cli/.npm-cache/_cacache', 'home/.cache/ms-playwright'):
            caches[relative] += directory_bytes(environment / relative)
        browser_root = environment / 'home/.cache/ms-playwright'
        if browser_root.is_dir() and not browser_root.is_symlink():
            for path in browser_root.iterdir():
                if path.is_dir() and not path.is_symlink():
                    browser_packages[path.name] += directory_bytes(path)
            link_root = browser_root / '.links'
            if link_root.is_dir() and not link_root.is_symlink():
                for link in link_root.iterdir():
                    if not link.is_file() or link.is_symlink() or link.stat().st_size > 8192:
                        continue
                    value = link.read_text().strip()
                    if value.startswith('/home/node/'):
                        package = environment / 'home' / value.removeprefix('/home/node/')
                        browsers = package / 'browsers.json'
                        metadata = package / 'package.json'
                        if browsers.is_file() and not browsers.is_symlink() and metadata.is_file() and not metadata.is_symlink():
                            document = json.loads(browsers.read_text())
                            definition = json.loads(metadata.read_text())
                            browser_links.append({'package_name': definition.get('name'), 'package_version': definition.get('version'),
                                'browser_document_keys': list(document), 'browsers': document.get('browsers')})
                        else:
                            browser_links.append({'restorable_package_metadata': False})
                    else:
                        browser_links.append({'package_location_in_account_home': False})
        cli_root = environment / 'cli'
        if not cli_root.is_dir() or cli_root.is_symlink():
            continue
        for version in cli_root.iterdir():
            if not version.is_dir() or version.is_symlink() or not re.fullmatch(r'\d+\.\d+\.\d+(?:[-+][A-Za-z0-9._-]+)?', version.name):
                continue
            cli_versions[version.name] += directory_bytes(version)
            lock_path = version / 'package-lock.json'
            definition_path = version / 'node_modules/@anthropic-ai/claude-code/package.json'
            if lock_path.is_file() and definition_path.is_file():
                lock = json.loads(lock_path.read_text())
                definition = json.loads(definition_path.read_text())
                entry = lock.get('packages', {}).get('node_modules/@anthropic-ai/claude-code', {})
                recipes.append({'version_directory': version.name, 'package_name': definition.get('name'),
                    'package_version': definition.get('version'), 'lock_keys': list(lock),
                    'lock_package_keys': list(entry), 'lock_version': entry.get('version'),
                    'registry_host': urlsplit(entry.get('resolved', '')).hostname, 'integrity_present': bool(entry.get('integrity'))})
            else:
                recipes.append({'version_directory': version.name, 'metadata_available': False})
            if not (version / '.ready').is_file() or (version / '.ready').is_symlink():
                cli_skipped['未就绪版本'] += 1
                continue
            for directory, folders, names in os.walk(version, followlinks=False):
                parent = Path(directory)
                folders[:] = [name for name in folders if not (parent / name).is_symlink()]
                for name in names:
                    path = parent / name
                    metadata = path.lstat()
                    if not stat.S_ISREG(metadata.st_mode) or metadata.st_size < 1024**2:
                        continue
                    if metadata.st_uid != 0 or stat.S_IMODE(metadata.st_mode) & 0o022:
                        cli_skipped['非root只读制品'] += metadata.st_size
                        continue
                    digest = hashlib.sha256()
                    with path.open('rb') as source:
                        for chunk in iter(lambda: source.read(1024**2), b''):
                            digest.update(chunk)
                    key = (digest.hexdigest(), metadata.st_size, stat.S_IMODE(metadata.st_mode), metadata.st_uid, metadata.st_gid)
                    cli_groups[key].append((metadata.st_dev, metadata.st_ino))
    cli_duplicate_bytes = sum(key[1] * (len(set(inodes)) - 1) for key, inodes in cli_groups.items())
    references = {}
    database_path = bench / 'db.sqlite'
    with sqlite3.connect(database_path.as_uri() + '?mode=ro', uri=True, timeout=3) as database:
        tables = {row[0] for row in database.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        for name in ('runs', 'accounts', 'account_environments', 'login_drafts', 'project_batches'):
            if name not in tables:
                continue
            columns = [row[1] for row in database.execute('PRAGMA table_info("' + name + '")')]
            entry = {'rows': database.execute('SELECT COUNT(*) FROM "' + name + '"').fetchone()[0]}
            versions = {}
            for column in columns:
                if 'version' not in column:
                    continue
                values = database.execute('SELECT "' + column.replace('"', '""') + '",COUNT(*) FROM "' + name + '" GROUP BY "' + column.replace('"', '""') + '"')
                versions[column] = {str(value): count for value, count in values if value is None or re.fullmatch(r'\d+(?:\.\d+){0,2}(?:[-+][A-Za-z0-9._-]+)?', str(value))}
            entry['version_counts'] = versions
            references[name] = entry
    ids = subprocess.check_output(['docker', 'ps', '-aq'], text=True).split()
    containers = json.loads(subprocess.check_output(['docker', 'inspect', *ids], text=True)) if ids else []
    occupied_roles = collections.Counter()
    for item in containers:
        labels = item['Config'].get('Labels') or {}
        if labels.get('vibebench.product') == 'v3' and labels.get('vibebench.deployment') == 'us' and item['State']['Running']:
            occupied_roles[labels.get('vibebench.role', 'unknown')] += 1
    free = shutil.disk_usage(root).free
    filesystem = subprocess.check_output(['stat', '-f', '-c', '%T', str(root)], text=True).strip()
    print(json.dumps({
        'read_only': True,
        'environment_count': environment_count,
        'known_cache_bytes': dict(caches),
        'browser_package_bytes': dict(browser_packages),
        'cli_version_bytes': dict(cli_versions),
        'cli_large_file_dedup_potential_bytes': cli_duplicate_bytes,
        'cli_large_file_groups': len(cli_groups),
        'cli_skipped': dict(cli_skipped),
        'cli_recovery_metadata': recipes,
        'browser_recovery_metadata': browser_links,
        'database_references': references,
        'running_owned_roles': dict(occupied_roles),
        'filesystem': filesystem,
        'free_bytes': free,
        'production_writes': 0,
    }, ensure_ascii=False))


if __name__ == '__main__':
    main()
