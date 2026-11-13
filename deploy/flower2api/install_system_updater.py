#!/usr/bin/env python3
"""首次更新底座的两阶段接入，默认只预览，生产部署沿原操作流程执行。"""
from __future__ import annotations

import argparse
import copy
import fcntl
import hashlib
import json
import os
import secrets
import shlex
import shutil
import sys
import uuid
from contextlib import ExitStack
from pathlib import Path
from source_layout import source_path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(source_path(REPO, 'orchestrator')))
from manage import load_environment
from runtime_files import atomic_json, atomic_text
from storage_maintenance import acquire_storage_lock
from system_update_contract import safe_read, strict_json, utc_now, validate_release, verify_signed
from system_update_host import HostDeployment
from system_update_gate import read_gate
from system_updater import SystemUpdater, validate_policy

SOURCE_FILES = ('deploy/v3/manage.py', 'deploy/v3/system_release.py', 'deploy/v3/system_updater.py',
    'deploy/v3/system_update_host.py', 'deploy/v3/install_system_updater.py', 'deploy/v3/compose.yml',
    'deploy/v3/compose-updates.yml', 'orchestrator/system_update_contract.py', 'orchestrator/system_update_gate.py',
    'orchestrator/runtime_files.py', 'orchestrator/resource_budget.py', 'orchestrator/native_sender.py', 'orchestrator/cpu_resources.py',
    'orchestrator/storage_assets.py', 'orchestrator/storage_backup.py', 'orchestrator/storage_cleanup.py',
    'orchestrator/storage_maintenance.py')

SOURCE_FILES += ('deploy/v3/system_update_database.py', 'deploy/v3/upgrade_system_updater.py',
    'orchestrator/database_migrations.py', 'orchestrator/database_migration_contract.py',
    'orchestrator/database_schema.py', 'orchestrator/database-migration-registry.json', 'orchestrator/projects_store.py')
SOURCE_FILES += ('orchestrator/system_update_connection.py',)
SOURCE_FILES += ('deploy/v3/platform_version.py', 'deploy/v3/release_ci.py', 'deploy/v3/source_layout.py')
SOURCE_FILES += ('orchestrator/runtime_names.py',)


def prepare_installation(env: Path, release_dir: Path, root: Path, public_key: str, *, apply: bool = False,
        backend_type=HostDeployment) -> dict:
    """核对来源后生成独立执行器及首次底座候选，当前服务由原部署流程收口。

    :param env: 当前私有部署配置。
    :param release_dir: 完整签名发行目录。
    :param root: 全新独立更新目录。
    :param public_key: 原始 Ed25519 公钥 hex。
    :param apply: 显式写入接入文件。
    :param backend_type: 测试注入宿主边界。
    :return: 脱敏接入计划。
    """
    if root.exists() or not root.is_absolute() or root != root.resolve():
        raise ValueError('首次接入需要全新真实绝对目录')
    if len(str(root / 'socket/updater.sock').encode()) >= 104:
        raise ValueError('更新目录过长，超出 Unix socket 路径限制')
    values = load_environment(env)
    raw = safe_read(release_dir / 'system-release.json')
    signature = safe_read(release_dir / 'system-release.sig', 64)
    release = validate_release(verify_signed(raw, signature, public_key))
    migration_assets = [] if release['schema_version'] == 1 else [release['migrations'][field] for field in ('plan', 'evidence')]
    for asset in migration_assets:
        content = safe_read(release_dir / asset['name'])
        if len(content) != asset['size'] or hashlib.sha256(content).hexdigest() != asset['sha256']:
            raise ValueError('首次接入迁移附件摘要不符')
    data = Path(values['V3_DATA_ROOT'])
    policy = {'schema_version': release['schema_version'], 'deployment': values['V3_DEPLOYMENT_ID'], 'data_root': str(data),
        'env_file': str(env), 'state_root': str(root), 'public_key': public_key,
        'compose_file': str(root / 'source/deploy/v3/compose.yml'),
        'compose_file_sha256': hashlib.sha256(source_path(REPO, 'deploy/v3/compose.yml').read_bytes()).hexdigest(),
        'override_file': str(root / 'source/deploy/v3/compose-updates.yml'),
        'override_file_sha256': hashlib.sha256(source_path(REPO, 'deploy/v3/compose-updates.yml').read_bytes()).hexdigest()}
    validate_policy(policy)
    backend = backend_type(policy)
    backend.values()
    backend.verify_images({role: release[role] for role in ('control', 'account')})
    metadata = backend.metadata()
    controls = backend.controls()
    plan = {'status': 'planned', 'deployment': policy['deployment'], 'release': release['release'],
        'state_root': str(root), 'source_files': list(SOURCE_FILES),
        'current_controls': {role: item['Id'] for role, item in controls.items()},
        'next': '按原部署流程排空、重建需要变化的账号环境，并使用生成的 bootstrap.env 与双模板接入；最后执行 finalize'}
    if not apply:
        return plan
    root.mkdir(mode=0o700)
    for name in ('releases', 'operations', 'socket', 'gate', 'source'):
        (root / name).mkdir(mode=0o700)
    for relative in SOURCE_FILES:
        target = root / 'source' / relative
        target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        atomic_text(target, source_path(REPO, relative).read_text())
    folder = root / 'releases' / release['release']
    folder.mkdir(mode=0o700)
    atomic_text(folder / 'system-release.json', raw.decode())
    with (folder / 'system-release.sig').open('xb') as output:
        os.fchmod(output.fileno(), 0o600)
        output.write(signature)
        output.flush()
        os.fsync(output.fileno())
    for asset in release['build_manifests'].values():
        content = safe_read(release_dir / asset['name'])
        if len(content) != asset['size'] or hashlib.sha256(content).hexdigest() != asset['sha256']:
            raise ValueError('首次接入原始构建清单摘要不符')
        atomic_text(folder / asset['name'], content.decode())
    for asset in migration_assets:
        atomic_text(folder / asset['name'], safe_read(release_dir / asset['name']).decode())
    atomic_text(root / 'socket/token', secrets.token_hex(32))
    atomic_json(root / 'policy.json', policy)
    revision, epoch, operation_id = str(uuid.uuid4()), str(uuid.uuid4()), str(uuid.uuid4())
    bootstrap = {'schema_version': 1, 'operation_id': operation_id, 'epoch': epoch, 'revision': revision,
        'target': release, 'created_at': utc_now(), 'before_metadata': metadata,
        'before_env_sha256': hashlib.sha256(safe_read(env, private=True)).hexdigest()}
    atomic_json(root / 'bootstrap.json', bootstrap)
    atomic_json(root / 'gate/admission.json', {'schema_version': 1, 'deployment': policy['deployment'],
        'operation_id': operation_id, 'epoch': epoch, 'phase': 'blocked', 'target_release': release['release'],
        'revision': revision, 'created_at': bootstrap['created_at']})
    updates = {'V3_RELEASE': release['control']['release'], 'V3_CONTROL_IMAGE': release['control']['reference'],
        'V3_ACCOUNT_IMAGE': release['account']['reference'], 'V3_ACCOUNT_RELEASE': release['account']['release'],
        'V3_SYSTEM_RELEASE': release['release'], 'V3_UPDATE_ROOT': str(root),
        'V3_RELEASE_MANIFEST': str(folder / release['build_manifests']['control']['name'])}
    lines = []
    for line in safe_read(env, private=True).decode().splitlines():
        key = line.partition('=')[0].strip()
        lines.append(key + '=' + shlex.quote(updates.pop(key)) if key in updates else line)
    lines.extend(key + '=' + shlex.quote(value) for key, value in updates.items())
    atomic_text(root / 'bootstrap.env', '\n'.join(lines) + '\n')
    installed = {'release': release, 'selection': {role: copy.deepcopy(release[role]) for role in ('control', 'account')}, 'installed_at': None}
    atomic_json(root / 'state.json', {'schema_version': 1, 'deployment': policy['deployment'], 'revision': revision,
        'current': installed, 'history': [], 'active_operation': None, 'bootstrap_pending': True})
    def unit_quote(value):
        return '"' + str(value).replace('\\', '\\\\').replace('"', '\\"').replace('%', '%%') + '"'
    unit = '\n'.join(['[Unit]', 'Description=V3 独立平台更新服务', 'After=docker.service network-online.target',
        'Requires=docker.service', 'StartLimitIntervalSec=60', 'StartLimitBurst=5', '', '[Service]', 'Type=simple',
        'UMask=0077', 'NoNewPrivileges=true', 'PrivateTmp=true',
        'ExecStart=/usr/bin/python3 ' + unit_quote(root / 'source/deploy/v3/system_updater.py') + ' --policy ' + unit_quote(root / 'policy.json'),
        'Restart=on-failure', 'RestartSec=3', '', '[Install]', 'WantedBy=multi-user.target', ''])
    atomic_text(root / 'vibebench-updater.service', unit)
    return {**plan, 'status': 'prepared'}


def finalize_installation(policy_path: Path, *, apply: bool = False, backend_type=HostDeployment) -> dict:
    """原部署完成后核对实际底座并提交首次安装，再开放业务准入。

    :param policy_path: 已生成的 root 私有策略。
    :param apply: 显式提交。
    :param backend_type: 测试注入宿主边界。
    :return: 已核对的接入结果。
    """
    policy = validate_policy(strict_json(safe_read(policy_path, private=True)))
    root = Path(policy['state_root'])
    with ExitStack() as resources:
        if apply:
            # 与执行器使用同一进程锁，避免补交首次接入时覆盖另一在线操作。
            descriptor = os.open(root / 'service.lock', os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
            resources.callback(os.close, descriptor)
            try:
                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as error:
                raise ValueError('首次接入收口前请先停止独立更新服务') from error
            storage = acquire_storage_lock(Path(policy['data_root']))
            resources.callback(os.close, storage)
        engine = SystemUpdater(policy, backend_type(policy))
        bootstrap = strict_json(safe_read(root / 'bootstrap.json', 1024 * 1024, private=True), 1024 * 1024)
        backend = engine.backend
        selected = engine.state['current']
        if (selected['release'] != bootstrap['target'] or engine.state['revision'] != bootstrap['revision']
                or engine.state.get('active_operation') or engine.state['history']):
            raise ValueError('首次接入之后已有其他操作，拒绝覆盖当前安装')
        pending = engine.state.get('bootstrap_pending')
        gate = read_gate(root / 'gate', policy['deployment'])
        if (type(pending) is not bool or gate['epoch'] != bootstrap['epoch'] or gate['revision'] != bootstrap['revision']
                or (gate['phase'] == 'blocked' and (gate['operation_id'] != bootstrap['operation_id']
                    or gate['target_release'] != selected['release']['release']))
                or (gate['phase'] == 'idle' and pending)):
            raise ValueError('首次接入门禁归属或提交状态需要对账')
        env = Path(policy['env_file'])
        current = safe_read(env, private=True)
        candidate = safe_read(root / 'bootstrap.env', private=True)
        if (not pending and current != candidate) or (pending and
                hashlib.sha256(current).hexdigest() != bootstrap['before_env_sha256'] and current != candidate):
            raise ValueError('首次接入期间部署配置已经变化')
        images = backend.verify_images(selected['selection'])
        for control in backend.controls().values():
            if control['Image'] != images['control']['Id'] or control['State']['Status'] != 'running':
                raise ValueError('控制服务尚未接入目标底座，请先完成原部署流程')
        metadata = backend.metadata()
        if metadata['identity_sha256'] != bootstrap['before_metadata']['identity_sha256']:
            raise ValueError('首次底座改变了受保护身份或资源，需要对账')
        plan = {'status': 'verified', 'deployment': policy['deployment'], 'release': selected['release']['release'],
            'systemd_unit': str(root / 'vibebench-updater.service')}
        if gate['phase'] == 'idle':
            return {**plan, 'status': 'installed' if apply else 'verified'}
        if not backend.drained(bootstrap)['ready']:
            raise ValueError('首次接入仍有活动或未知环境，请按原部署流程完成账号重建与排空')
        if not apply:
            return plan
        # 软件画像变化只有精确前后值证据时补偿，设备、资源及凭据字段保持原规则。
        if metadata['software'] != bootstrap['before_metadata']['software']:
            backend.restore_software(bootstrap['before_metadata']['software'], metadata['software'])
        atomic_text(env, candidate.decode())
        engine.state['bootstrap_pending'] = False
        engine.state['current']['installed_at'] = engine.state['current']['installed_at'] or utc_now()
        atomic_json(root / 'state.json', engine.state)
        backend.release(bootstrap)
    return {**plan, 'status': 'installed'}


def main() -> None:
    """提供默认 dry-run 的首次接入与最终核验入口。

    :return: None。
    """
    parser = argparse.ArgumentParser(description='首次接入 V3 系统更新底座，默认只预览')
    sub = parser.add_subparsers(dest='action', required=True)
    prepare = sub.add_parser('prepare')
    prepare.add_argument('--env', type=Path, required=True)
    prepare.add_argument('--release-dir', type=Path, required=True)
    prepare.add_argument('--state-root', type=Path, required=True)
    prepare.add_argument('--public-key', required=True)
    prepare.add_argument('--apply', action='store_true')
    final = sub.add_parser('finalize')
    final.add_argument('--policy', type=Path, required=True)
    final.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    if args.action == 'prepare':
        result = prepare_installation(args.env, args.release_dir, args.state_root, args.public_key, apply=args.apply)
    else:
        result = finalize_installation(args.policy, apply=args.apply)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    main()
