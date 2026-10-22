"""只读核对默认值、数据库快照及受控登录/执行记录中的精确 CLI 版本。"""
import collections
import json
import os
from pathlib import Path
import re
import shlex
import sqlite3
import stat


def versions(value: object, key: str = '') -> set[str]:
    """提取版本字段而不返回其他业务内容。@param value JSON值。@param key 字段。@return 版本集合。"""
    result = set()
    if isinstance(value, dict):
        for name, item in value.items():
            result.update(versions(item, name))
    elif isinstance(value, list):
        for item in value:
            result.update(versions(item, key))
    elif isinstance(value, str) and (key.lower().endswith('version') or key == 'CLAUDE_CODE_VERSION'):
        if re.fullmatch(r'\d+\.\d+\.\d+(?:[-+][A-Za-z0-9._-]+)?', value):
            result.add(value)
    return result


def main() -> None:
    """输出引用计数和不确定项数量，不删除旧版本或输出凭据。@return None。"""
    root = Path('/srv/vibebench-v3-us/bench')
    sources = collections.defaultdict(collections.Counter)
    uncertain = 0
    database = sqlite3.connect((root / 'db.sqlite').as_uri() + '?mode=ro', uri=True)
    try:
        for table in ('runs', 'tasks', 'project_task_executions'):
            columns = {row[1] for row in database.execute('PRAGMA table_info("' + table + '")')}
            if 'claude_code_version' in columns:
                for value, count in database.execute('SELECT claude_code_version,COUNT(*) FROM "' + table + '" GROUP BY claude_code_version'):
                    if value:
                        sources[table][value] += count
        for key, value in database.execute('SELECT key,value FROM app_settings WHERE key=?', ('claude_code_version',)):
            if value:
                sources['app_settings'][value] += 1
    finally:
        database.close()
    settings = {}
    for line in Path('/opt/vibebench-v3-us/v3.env').read_text().splitlines():
        key, separator, raw = line.partition('=')
        if separator and key.strip() in ('V3_CLI_VERSION', 'CLAUDE_CODE_VERSION', 'V3_RELEASE_MANIFEST'):
            parts = shlex.split(raw, comments=False)
            if len(parts) == 1:
                settings[key.strip()] = parts[0]
    for key in ('V3_CLI_VERSION', 'CLAUDE_CODE_VERSION'):
        if settings.get(key):
            sources['configured_default'][settings[key]] += 1
    manifest_path = settings.get('V3_RELEASE_MANIFEST')
    if manifest_path:
        manifest = json.loads(Path(manifest_path).read_text())
        if manifest.get('default_cli_version'):
            sources['release_default'][manifest['default_cli_version']] += 1
    paths = list((root / 'login-drafts').glob('*.json'))
    for directory, folders, names in os.walk(root / 'profiles', followlinks=False):
        parent = Path(directory)
        folders[:] = [name for name in folders if not (parent / name).is_symlink()]
        paths.extend(parent / name for name in names if name.endswith('.json'))
    for environment in (root / 'environments').iterdir():
        if environment.is_symlink() or not environment.is_dir():
            continue
        runtime = environment / 'runtime'
        if runtime.is_symlink():
            uncertain += 1
            continue
        paths.extend(runtime.glob('*.json'))
        executions = runtime / 'executions'
        if not executions.is_symlink():
            paths.extend(executions.glob('*.json'))
    for path in paths:
        try:
            descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
            with os.fdopen(descriptor, 'rb') as source:
                metadata = os.fstat(source.fileno())
                if not stat.S_ISREG(metadata.st_mode) or metadata.st_size > 4 * 1024**2:
                    uncertain += 1
                    continue
                value = json.load(source)
            for version in versions(value):
                sources['controlled_records'][version] += 1
        except (OSError, ValueError):
            uncertain += 1
    print(json.dumps({'read_only': True, 'production_writes': 0, 'references': dict(sources),
        'controlled_records_inspected': len(paths), 'uncertain_records': uncertain,
        'policy': '未知引用和旧安装协议版本保留，不凭安装日期删除'}, ensure_ascii=False))


if __name__ == '__main__':
    main()
