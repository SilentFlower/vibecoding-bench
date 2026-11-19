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
from source_layout import source_path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(source_path(REPO, 'orchestrator')))
from database_migrations import schema_checksum
from agy_auth import auth_asset_identity
from database_migration_contract import load_registry, registry_contract
from system_update_contract import INDEX_LIMIT, MANIFEST_LIMIT, ROLES, strict_json, utc_now, validate_index, validate_release, validate_migration_evidence, validate_migration_plan


# 与实际迁移执行器的步骤ID绑定，定义扫描与签发校验共用精确来源。
BENCH_SCHEMA_SOURCES = {
    'bench.baseline.1': 'orchestrator/database_schema.py',
    'bench.cluster.2': 'orchestrator/cluster_schema.py',
    'bench.node-executions.3': 'orchestrator/node_execution_schema.py',
    'bench.node-login-drafts.4': 'orchestrator/node_login_draft_schema.py',
    'bench.agy-environments.5': 'orchestrator/agy_environment_schema.py',
}
GATEWAY_SCHEMA_SOURCES = {
    'gateway.request-records.6': 'cc2api/src/store/request_records_schema.rs',
    'gateway.account-platforms.5': 'cc2api/src/store/account_platform_schema.rs',
    'gateway.baseline.1': 'cc2api/src/store/database_schema.rs',
    'gateway.proxies.2': 'cc2api/src/store/proxy_schema.rs',
    'gateway.proxy-sync.3': 'cc2api/src/store/proxy_sync_schema.rs',
    'gateway.session-policy-blocks.4': 'cc2api/src/store/session_policy_block_schema.rs',
}


def data_contracts(root: Path) -> dict:
    """从实际迁移源码生成保守数据合同，变更后需显式兼容证明。

    :param root: 冻结源码根。
    :return: 两库合同 SHA256。
    """
    registries = migration_registries(root)
    return {name: registry_contract(value) for name, value in registries.items()}


def migration_registries(root: Path) -> dict:
    """读取源码登记并核对每项已知迁移定义。:param root: 冻结源码根。:return: 两库登记。"""
    values = {'bench': load_registry(source_path(root, 'orchestrator/database-migration-registry.json'), 'bench'),
        'gateway': load_registry(source_path(root, 'cc2api/src/store/database-migration-registry.json'), 'gateway')}
    for step in values['bench']['steps']:
        logical = BENCH_SCHEMA_SOURCES.get(step['id'])
        if logical is None:
            raise ValueError('编排迁移缺少已登记定义来源：' + step['id'])
        path = source_path(root, logical)
        if path.is_symlink() or not path.is_file() or step['checksum'] != schema_checksum(path):
            raise ValueError('迁移定义与版本登记不符：' + step['id'])
    for step in values['gateway']['steps']:
        logical = GATEWAY_SCHEMA_SOURCES.get(step['id'])
        if logical is None:
            raise ValueError('网关迁移缺少已登记定义来源：' + step['id'])
        path = source_path(root, logical)
        if path.is_symlink() or not path.is_file():
            raise ValueError('迁移定义来源缺失或无效：' + step['id'])
        actual = hashlib.sha256(path.read_bytes().split(b'#[cfg(test)]', 1)[0]).hexdigest()
        if step['checksum'] != actual:
            raise ValueError('迁移定义与版本登记不符：' + step['id'])
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
    names = (common + ['orchestrator', 'webui', 'cc2api/web/src', 'cc2api/web/package-lock.json',
        'images/worker/entrypoint.sh', 'images/worker/task_followups.py', 'images/account/projects_cli.py'] if role == 'control'
        else common + ['images/account', 'images/sidecar', 'images/worker/task_followups.py',
            'images/v3/criu', 'images/v3/tls-observer',
            'orchestrator/runtime_files.py', 'orchestrator/runtime_diagnostics.py',
            'orchestrator/cli_quota.py', 'orchestrator/process_metrics.py', 'orchestrator/native_sender.py', 'orchestrator/agy_auth.py', 'orchestrator/agy_runtime'])
    digest = hashlib.sha256()
    for name in names:
        source = source_path(root, name)
        if not source.exists():
            raise ValueError('组件源码依赖缺失')
        paths = sorted(source.rglob('*')) if source.is_dir() else [source]
        for path in paths:
            if 'agy_runtime/resources' in path.as_posix() and path.name in ('observer-c', 'relocation_reclaim.so', 'admission.json'):
                continue
            if path.is_file() and not any(part in ('__pycache__', 'target', 'node_modules', '.git') for part in path.relative_to(root).parts):
                if path.is_symlink():
                    raise ValueError('组件源码不能是符号链接')
                digest.update(str(Path(name) / path.relative_to(source) if source.is_dir() else Path(name)).encode() + b'\0')
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
    agy_asset = auth_asset_identity(build.get('agy_auth'))
    version = 2 if migration_evidence is not None else 1
    value = {'schema_version': version, 'release': 'system-' + build['release'], 'sequence': sequence,
        'published_at': utc_now(), 'platform': 'linux/amd64', 'changes': changes,
        'build_manifests': {role: {'name': 'v3.json', 'size': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()} for role in ROLES},
        'compatibility': {'updater': version, 'gate': 1, 'bridge': 1, 'layout': 2, 'cli_install': 2,
            'credential_ownership': 1, 'account_protocols': [1]},
        'data_compatibility': {}, 'bundle': build['bundle']}
    recovery = build['images']['control'].get('cli_scratchpad_storage', 0)
    activation = build['images']['account'].get('cli_scratchpad_protocol', 0)
    if (type(recovery) is not int or recovery not in (0, 1)
            or type(activation) is not int or activation not in (0, 1)):
        raise ValueError('CLI临时文件镜像能力声明无效')
    if activation and not recovery:
        raise ValueError('CLI临时文件启用镜像缺少管理端恢复能力')
    if recovery:
        value['compatibility']['scratchpad_storage'] = 1
    if activation:
        value['compatibility']['scratchpad_activation'] = 1
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
        if role == 'account' and agy_asset is not None:
            # 外部制品输入变化也必须切换账号镜像，不能只按源码相同复用旧能力。
            identity = {'source': value[role]['content_sha256'], 'agy_auth': agy_asset}
            value[role]['content_sha256'] = hashlib.sha256(json.dumps(identity, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
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
