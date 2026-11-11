"""只运行本地 SQLite 迁移，独立于业务服务和模型调用。"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import sqlite3
import uuid
from contextlib import closing
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path

from database_schema import initialize_bench_schema
from database_migration_contract import load_registry, registry_contract


def _affinity(declaration: str) -> str:
    value = declaration.upper()
    if 'INT' in value:
        return 'INTEGER'
    if any(token in value for token in ('CHAR', 'CLOB', 'TEXT')):
        return 'TEXT'
    if not value or 'BLOB' in value:
        return 'BLOB'
    if any(token in value for token in ('REAL', 'FLOA', 'DOUB')):
        return 'REAL'
    return 'NUMERIC'


def _structure(connection: sqlite3.Connection) -> dict:
    tables = connection.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' AND name<>'system_schema_migrations'").fetchall()
    return {table[0]: {row[0]: (_affinity(row[1]), row[2])
        for row in connection.execute('SELECT name,type,pk FROM pragma_table_info(?)', (table[0],))} for table in tables}


@lru_cache(maxsize=1)
def _baseline_structure() -> dict:
    # 只在独立内存库读取冻结定义，保持业务连接中的记录和事务归属。
    with closing(sqlite3.connect(':memory:')) as connection:
        connection.row_factory = sqlite3.Row
        initialize_bench_schema(connection)
        return _structure(connection)


def validate_structure(connection: sqlite3.Connection, *, completed: bool) -> None:
    """核对旧库稳定核心及完成后的最低结构，保留兼容新增字段。

    :param connection: 当前 SQLite 连接。
    :param completed: 已登记或迁移完成时检查全部基线结构。
    :return: None；缺列、类型及主键异常时拒绝登记成功。
    """
    expected, actual = _baseline_structure(), _structure(connection)
    core = {'accounts': {'id', 'name', 'profile_path', 'enabled', 'upstream_socks5_host', 'upstream_socks5_port'}}
    if connection.execute("SELECT 1 FROM sqlite_master WHERE name='accounts' AND type<>'table'").fetchone():
        raise ValueError('旧库账号基础结构无效')
    if not completed and actual and 'accounts' not in actual:
        raise ValueError('旧库缺少账号基础表')
    for table, columns in (expected.items() if completed else core.items()):
        if not completed and table not in actual:
            continue
        for column in columns:
            required = expected[table][column]
            observed = actual.get(table, {}).get(column)
            numeric = {'INTEGER', 'REAL', 'NUMERIC'}
            if (observed is None or observed[1] != required[1]
                    or (observed[0] != required[0] and (required[1] or not {observed[0], required[0]} <= numeric))):
                raise ValueError('数据库结构不符合迁移基线：' + table + '.' + column)
    if completed and connection.execute('PRAGMA integrity_check').fetchall()[0][0] != 'ok':
        raise ValueError('数据库完整性校验失败')


def schema_checksum(path: Path | None = None) -> str:
    """生成纯迁移定义摘要，忽略注释、格式与说明文字。

    :param path: 可选的冻结源码路径。
    :return: 迁移语义的 SHA256。
    """
    tree = ast.parse((path or Path(__file__).with_name('database_schema.py')).read_text())
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            if node.body and isinstance(node.body[0], ast.Expr) and isinstance(node.body[0].value, ast.Constant) and isinstance(node.body[0].value.value, str):
                node.body.pop(0)
    return hashlib.sha256(ast.dump(tree, include_attributes=False).encode()).hexdigest()


def migration_plan(connection: sqlite3.Connection, target: int | None = None, *, registry: dict | None = None) -> dict:
    """只读校验登记和台账，兼容后来已验证的增量结构。

    :param connection: 当前 SQLite 连接。
    :param target: 目标版本，省略时使用当前程序最大版本。
    :param registry: 内部已校验登记，默认来自固定源码。
    :return: 当前计划；已知摘要被改写或版本不连续时拒绝。
    """
    registry = registry or load_registry(Path(__file__).with_name('database-migration-registry.json'), 'bench')
    steps = registry['steps']
    target = len(steps) if target is None else target
    if type(target) is not int or not 1 <= target <= len(steps):
        raise ValueError('数据库迁移目标版本不受支持')
    exists = connection.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='system_schema_migrations'").fetchone()
    rows = connection.execute('SELECT migration_id,version,checksum FROM system_schema_migrations ORDER BY version').fetchall() if exists else []
    for version, row in enumerate(rows, 1):
        identity, actual_version, checksum = tuple(row)
        if type(actual_version) is not int or actual_version != version or not isinstance(checksum, str) or (len(checksum) != 64 or any(value not in '0123456789abcdef' for value in checksum)) or not isinstance(identity, str) or not identity.startswith('bench.'):
            raise ValueError('数据库迁移台账版本链无效')
        if version <= len(steps) and (identity, actual_version, checksum) != (steps[version-1]['id'], version, steps[version-1]['checksum']):
            raise ValueError('数据库迁移台账版本或摘要与当前程序不符')
    current = len(rows)
    validate_structure(connection, completed=current > 0)
    return {'database': 'bench', 'contract': registry_contract(registry), 'current_version': current, 'target_version': target,
        'steps': [{**step, 'state': 'completed' if step['version'] <= current else 'pending'} for step in steps[:target]],
        'state': 'compatible_newer' if current > target else 'ready', 'reason': None}


def apply_migrations(connection: sqlite3.Connection, operation_id: str | None = None, target: int | None = None,
                     *, registry: dict | None = None, runners: dict | None = None) -> dict:
    """执行按版本登记的幂等迁移，后来兼容结构保持当前数据。

    :param connection: 本库连接，调用方负责关闭。
    :param operation_id: 宿主冻结 UUID，普通初始化时生成。
    :param target: 目标版本，省略时为本程序最新版本。
    :param registry: 内部可注入的已校验登记。
    :param runners: 内部迁移实现与摘要计算函数，CLI 不接受该字段。
    :return: 完成后的计划。
    """
    operation_id = operation_id or str(uuid.uuid4())
    if str(uuid.UUID(operation_id)) != operation_id:
        raise ValueError('数据库迁移操作身份无效')
    registry = registry or load_registry(Path(__file__).with_name('database-migration-registry.json'), 'bench')
    runners = runners or {'bench.baseline.1': (initialize_bench_schema, schema_checksum)}
    plan = migration_plan(connection, target, registry=registry)
    for step in registry['steps'][:plan['target_version']]:
        runner = runners.get(step['id'])
        if not runner or runner[1]() != step['checksum']:
            raise ValueError('数据库迁移定义未登记或摘要被改写')
    if plan['current_version'] >= plan['target_version']:
        return plan
    for step in plan['steps']:
        if step['state'] == 'completed':
            continue
        runner = runners.get(step['id'])
        if not runner or runner[1]() != step['checksum']:
            raise ValueError('数据库迁移定义未登记或摘要被改写')
        if step['id'] == 'bench.baseline.1':
            # 旧计划迁移自带事务和表重建；完整成功后登记，保留原幂等恢复行为。
            runner[0](connection)
        else:
            # sqlite3 的上下文管理器不会为 DDL 自动 BEGIN，显式事务才能回滚补列和索引。
            connection.execute('BEGIN IMMEDIATE')
        with connection:
            connection.execute("""CREATE TABLE IF NOT EXISTS system_schema_migrations (
                migration_id TEXT PRIMARY KEY, version INTEGER NOT NULL UNIQUE,
                checksum TEXT NOT NULL, applied_at TEXT NOT NULL, operation_id TEXT NOT NULL)""")
            if step['id'] != 'bench.baseline.1':
                runner[0](connection)
            validate_structure(connection, completed=True)
            connection.execute('INSERT INTO system_schema_migrations VALUES(?,?,?,?,?)',
                (step['id'], step['version'], step['checksum'], datetime.now(timezone.utc).isoformat(), operation_id))
    return migration_plan(connection, target, registry=registry)


def main() -> None:
    """执行固定的离线数据库维护入口。@return None。"""
    parser = argparse.ArgumentParser(description='本地数据库迁移维护')
    parser.add_argument('action', choices=('plan', 'apply', 'verify'))
    parser.add_argument('--operation-id', required=True)
    parser.add_argument('--target-version', type=int)
    parser.add_argument('--database', type=Path, default=Path('/data/db.sqlite'))
    args = parser.parse_args()
    if str(uuid.UUID(args.operation_id)) != args.operation_id:
        raise ValueError('数据库迁移操作身份无效')
    if args.database.is_symlink() or args.database.parent != args.database.parent.resolve():
        raise ValueError('数据库迁移路径必须为真实文件')
    mode = 'rwc' if args.action == 'apply' else 'ro'
    with closing(sqlite3.connect(args.database.absolute().as_uri() + '?mode=' + mode, uri=True)) as connection:
        connection.row_factory = sqlite3.Row
        result = apply_migrations(connection, args.operation_id, args.target_version) if args.action == 'apply' else migration_plan(connection, args.target_version)
        if args.action == 'verify' and result['current_version'] < result['target_version']:
            raise ValueError('数据库迁移尚未完成')
        print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    main()
