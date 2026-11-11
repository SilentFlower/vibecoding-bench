#!/usr/bin/env python3
"""CI 检查纯迁移所有权，业务代码新增 DDL 必须先进入版本登记。"""
from __future__ import annotations

import ast
import re
from pathlib import Path

from system_release import REPO, migration_registries


DDL = re.compile(r'(?:^|;)\s*(?:CREATE\s+(?:(?:TEMP|TEMPORARY)\s+)?(?:TABLE|INDEX|UNIQUE\s+INDEX|TRIGGER|VIEW)|ALTER\s+TABLE|DROP\s+(?:TABLE|INDEX|TRIGGER|VIEW))\b', re.I | re.M)
RUST_LITERAL = re.compile(r'''(?P<comment>//[^\n]*|/\*[\s\S]*?\*/)|(?P<char>'(?:\\.|[^'\\])')|r(?P<hashes>\#{0,16})"(?P<raw>[\s\S]*?)"(?P=hashes)|"(?P<string>(?:\\.|[^"\\])*)"''')


def source_ownership(root: Path) -> list[str]:
    """定位迁移所有者以外的结构变更定义。

    :param root: 冻结源码根。
    :return: 需要迁移登记的位置，不包含 SQL 或业务数据。
    """
    findings = []
    schema = root / 'orchestrator/database_schema.py'
    for node in ast.walk(ast.parse(schema.read_text())):
        if ((isinstance(node, ast.ImportFrom) and node.module != '__future__')
                or (isinstance(node, ast.Import) and any(item.name not in ('re', 'sqlite3') for item in node.names))):
            findings.append(str(schema.relative_to(root)) + ':' + str(node.lineno))
    rust_schema = root / 'cc2api/src/store/database_schema.rs'
    definitions = rust_schema.read_text().split('#[cfg(test)]', 1)[0]
    if re.search(r'\b(?:crate|super)::', RUST_LITERAL.sub(' ', definitions)):
        findings.append(str(rust_schema.relative_to(root)) + ':1')
    for path in (root / 'orchestrator').glob('*.py'):
        if path.name.startswith('test_') or path.name == 'database_schema.py':
            continue
        tree = ast.parse(path.read_text())
        docstrings = set()
        for node in ast.walk(tree):
            if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)) and node.body:
                first = node.body[0]
                if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant):
                    docstrings.add(id(first.value))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Constant) or not isinstance(node.value, str) or id(node) in docstrings or not DDL.search(node.value):
                continue
            if path.name == 'database_migrations.py' and re.match(r'\s*CREATE TABLE IF NOT EXISTS system_schema_migrations\b', node.value):
                continue
            findings.append(str(path.relative_to(root)) + ':' + str(node.lineno))
    for path in (root / 'cc2api/src').rglob('*.rs'):
        if path.name == 'database_schema.rs':
            continue
        source = path.read_text().split('#[cfg(test)]', 1)[0]
        for match in RUST_LITERAL.finditer(source):
            value = match.group('raw') if match.group('raw') is not None else match.group('string')
            if value is None:
                continue
            value = value.replace('\\n', '\n').replace('\\t', '\t').replace('\\r', '\r')
            if not DDL.search(value):
                continue
            if path.name == 'database_migrations.rs' and re.match(r'\s*CREATE TABLE IF NOT EXISTS system_schema_migrations\b', value):
                continue
            findings.append(str(path.relative_to(root)) + ':' + str(source.count('\n', 0, match.start()) + 1))
    return findings


def verify(root: Path = REPO) -> dict:
    """验证迁移所有权与实际定义摘要。

    :param root: 冻结源码根。
    :return: 校验摘要；任一未登记变更阻断构建。
    """
    findings = source_ownership(root)
    if findings:
        raise ValueError('发现未登记数据库结构变更：' + ', '.join(findings))
    registries = migration_registries(root)
    return {'status': 'passed', 'databases': {name: len(value['steps']) for name, value in registries.items()}}


if __name__ == '__main__':
    import json
    print(json.dumps(verify(), ensure_ascii=False))
