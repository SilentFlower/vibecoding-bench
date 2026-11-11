#!/usr/bin/env python3
"""生成并签署唯一平台发行及原子版本目录，生产服务器只需要公钥。"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / 'orchestrator'))
from database_migrations import schema_checksum
from database_migration_contract import load_registry, registry_contract
from system_update_contract import INDEX_LIMIT, MANIFEST_LIMIT, ROLES, strict_json, utc_now, validate_index, validate_release, validate_migration_evidence, validate_migration_plan


def data_contracts(root: Path) -> dict:
    """从实际迁移源码生成保守数据合同，变更后需显式兼容证明。

    :param root: 冻结源码根。
    :return: 两库合同 SHA256。
    """
    registries = migration_registries(root)
    return {name: registry_contract(value) for name, value in registries.items()}


def migration_registries(root: Path) -> dict:
    """读取源码登记并核对首版纯迁移定义。:param root: 冻结源码根。:return: 两库登记。"""
    values = {'bench': load_registry(root / 'orchestrator/database-migration-registry.json', 'bench'),
        'gateway': load_registry(root / 'cc2api/src/store/database-migration-registry.json', 'gateway')}
    actual = {'bench': schema_checksum(root / 'orchestrator/database_schema.py'),
        'gateway': hashlib.sha256((root / 'cc2api/src/store/database_schema.rs').read_bytes().split(b'#[cfg(test)]', 1)[0]).hexdigest()}
    if any(value['steps'][0]['checksum'] != actual[name] for name, value in values.items()):
        raise ValueError('迁移定义与版本登记不符')
    return values



def sign_file(path: Path, key: Path) -> Path:
    """通过 OpenSSL 签署完整原字节，并核对签名长度。

    :param path: 独占发布的 JSON 文件。
    :param key: 私有 Ed25519 PEM 路径。
    :return: 同目录签名路径。
    """
    destination = path.with_suffix('.sig')
    with destination.open('xb') as output:
        result = subprocess.run(['openssl', 'pkeyutl', '-sign', '-rawin', '-inkey', str(key),
            '-in', str(path)], stdout=output, stderr=subprocess.PIPE, check=False, timeout=10)
    if result.returncode or destination.stat().st_size != 64:
        raise ValueError('平台发行签名生成失败')
    return destination


def component_content(root: Path, role: str) -> str:
    """计算排除发布标签的组件源码身份，用于确定账号是否确需重建。

    :param root: 冻结源码根。
    :param role: control 或 account。
    :return: 源码集合 SHA256；未知依赖采用保守失配。
    """
    common = ['images/v3/Dockerfile', 'cc2api/src', 'cc2api/Cargo.toml', 'cc2api/Cargo.lock',
        'cc2api/vendor', 'cc2api/craftls']
    names = (common + ['orchestrator', 'webui', 'cc2api/web/src', 'cc2api/web/package-lock.json'] if role == 'control'
        else common + ['images/account', 'images/sidecar', 'images/worker/task_followups.py',
            'orchestrator/runtime_files.py', 'orchestrator/runtime_diagnostics.py',
            'orchestrator/cli_quota.py', 'orchestrator/process_metrics.py', 'orchestrator/native_sender.py'])
    digest = hashlib.sha256()
    for name in names:
        source = root / name
        if not source.exists():
            raise ValueError('组件源码依赖缺失')
        paths = sorted(source.rglob('*')) if source.is_dir() else [source]
        for path in paths:
            if path.is_file() and not any(part in ('__pycache__', 'target', 'node_modules', '.git') for part in path.relative_to(root).parts):
                if path.is_symlink():
                    raise ValueError('组件源码不能是符号链接')
                digest.update(str(path.relative_to(root)).encode() + b'\0')
                digest.update(hashlib.sha256(path.read_bytes()).digest())
    return digest.hexdigest()


def create_release(manifest_path: Path, policy_path: Path, output: Path, key: Path,
        sequence: list[int], changes: str, *, root: Path = REPO, migration_evidence: Path | None = None) -> dict:
    """将已发布同批制品转换为严格平台发行，禁止覆盖身份。

    :param manifest_path: 现有 schema3 发布清单。
    :param policy_path: 代码审查过的回退兼容证明。
    :param output: 全新目录。
    :param key: CI 私有签名文件。
    :param sequence: 工作流顺序及 attempt。
    :param changes: 普通文本版本说明。
    :param root: 冻结来源根。
    :param migration_evidence: 可选的真实镜像迁移演练证据，提供时生成 v2。
    :return: 已签署平台合同。
    """
    raw = manifest_path.read_bytes()
    build = strict_json(raw)
    if (build.get('schema') != 3 or build.get('dirty_worktree') is not False
            or build.get('layout_version') != 2 or build.get('credential_ownership_protocol') != 1
            or build.get('system_update_protocol') != 1):
        raise ValueError('联合清单缺少可在线更新底座能力')
    policy = strict_json(policy_path.read_bytes())
    if set(policy) != {'schema_version', 'rollback_compatible'} or policy['schema_version'] != 1 or set(policy['rollback_compatible']) != {'bench', 'gateway'}:
        raise ValueError('数据兼容证明格式无效')
    contracts = data_contracts(root)
    version = 2 if migration_evidence is not None else 1
    value = {'schema_version': version, 'release': 'system-' + build['release'], 'sequence': sequence,
        'published_at': utc_now(), 'platform': 'linux/amd64', 'changes': changes,
        'build_manifests': {role: {'name': 'v3.json', 'size': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()} for role in ROLES},
        'compatibility': {'updater': version, 'gate': 1, 'bridge': 1, 'layout': 2, 'cli_install': 2,
            'credential_ownership': 1, 'account_protocols': [1]},
        'data_compatibility': {}, 'bundle': build['bundle']}
    for name, digest in contracts.items():
        allowed = policy['rollback_compatible'][name]
        if not isinstance(allowed, list):
            raise ValueError('数据兼容证明必须为列表')
        value['data_compatibility'][name] = {'contract': digest, 'rollback_compatible': list(dict.fromkeys([digest, *allowed]))}
    for role in ROLES:
        entry = build['images'][role]
        if entry.get('platform') != 'linux/amd64' or type(entry.get('unpacked_bytes')) is not int:
            raise ValueError('镜像缺少平台或空间证据')
        value[role] = {field: entry[field] for field in ('reference', 'registry_digest', 'config_digest', 'unpacked_bytes')}
        value[role].update(release=build['release'], revision=build['parent_revision'])
        value[role]['content_sha256'] = component_content(root, role)
    evidence = None
    if migration_evidence is not None:
        evidence = strict_json(migration_evidence.read_bytes())
        validate_migration_evidence(evidence, value)
        for name in contracts:
            allowed = [source['contracts'][name] for source in evidence['sources']]
            value['data_compatibility'][name]['rollback_compatible'] = list(dict.fromkeys([contracts[name], *allowed]))
    output.mkdir(mode=0o700)
    if evidence is not None:
        registries = migration_registries(root)
        plan = {'schema_version': 1, 'databases': {name: {'version': len(registries[name]['steps']),
            'contract': digest, 'steps': registries[name]['steps']} for name, digest in contracts.items()}}
        value['migrations'] = {'protocol': 1}
        for field, filename, content in (('plan', 'database-migrations.json', plan), ('evidence', 'database-compatibility.json', evidence)):
            raw_asset = json.dumps(content, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()
            (output / filename).write_bytes(raw_asset)
            value['migrations'][field] = {'name': filename, 'size': len(raw_asset), 'sha256': hashlib.sha256(raw_asset).hexdigest()}
        validate_migration_plan(plan, value)
    validate_release(value)
    (output / 'v3.json').write_bytes(raw)
    path = output / 'system-release.json'
    path.write_text(json.dumps(value, ensure_ascii=False, separators=(',', ':')))
    sign_file(path, key)
    return value


def create_index(release_path: Path, previous_path: Path | None, output: Path, key: Path) -> dict:
    """将完整发行追加到有界通道，拒绝顺序倒退。

    :param release_path: 当前已校验发行。
    :param previous_path: 原目录；首次为空。
    :param output: 全新目录文件。
    :param key: CI 签名密钥路径。
    :return: 新目录。
    """
    raw = release_path.read_bytes()
    release = validate_release(strict_json(raw))
    old = strict_json(previous_path.read_bytes(), INDEX_LIMIT) if previous_path else None
    if old and (old.get('schema_version') != 1 or old.get('sequence', []) >= release['sequence']):
        raise ValueError('通道顺序禁止回退或重复推进')
    entry = {'release': release['release'], 'sequence': release['sequence'],
        'manifest': {'name': 'system-release.json', 'size': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}}
    entries = [entry, *([] if old is None else old['releases'])][:64]
    now = datetime.now(timezone.utc)
    value = {'schema_version': 1, 'sequence': release['sequence'], 'issued_at': utc_now(),
        'expires_at': (now + timedelta(days=30)).isoformat(timespec='seconds').replace('+00:00', 'Z'), 'releases': entries}
    validate_index(value)
    with output.open('x') as stream:
        json.dump(value, stream, ensure_ascii=False, separators=(',', ':'))
    sign_file(output, key)
    return value


def main() -> None:
    """执行 CI 的制品签名与目录生成，私钥由受限文件传入。

    :return: None。
    """
    parser = argparse.ArgumentParser(description='v3 受信系统发行')
    sub = parser.add_subparsers(dest='action', required=True)
    release = sub.add_parser('release')
    release.add_argument('--manifest', type=Path, required=True)
    release.add_argument('--policy', type=Path, default=Path(__file__).with_name('system-update-policy.json'))
    release.add_argument('--output', type=Path, required=True)
    release.add_argument('--key', type=Path, required=True)
    release.add_argument('--run-number', type=int, required=True)
    release.add_argument('--attempt', type=int, required=True)
    release.add_argument('--migration-evidence', type=Path)
    release.add_argument('--changes', default='平台联合构建，组件变化及兼容条件见版本清单。')
    index = sub.add_parser('index')
    index.add_argument('--release', type=Path, required=True)
    index.add_argument('--previous', type=Path)
    index.add_argument('--output', type=Path, required=True)
    index.add_argument('--key', type=Path, required=True)
    args = parser.parse_args()
    if args.action == 'release':
        value = create_release(args.manifest, args.policy, args.output, args.key,
            [args.run_number, args.attempt], args.changes, migration_evidence=args.migration_evidence)
    else:
        value = create_index(args.release, args.previous, args.output, args.key)
    print(json.dumps({'status': 'signed', 'identity': value.get('release', value['sequence'])}))


if __name__ == '__main__':
    main()
