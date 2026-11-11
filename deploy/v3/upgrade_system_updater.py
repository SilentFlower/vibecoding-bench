#!/usr/bin/env python3
"""一次性升级固定宿主执行器，默认预览并保护原安装与恢复状态。"""
from __future__ import annotations

import argparse
import copy
import fcntl
import hashlib
import json
import os
import re
import subprocess
import time
import uuid
from contextlib import contextmanager
from pathlib import Path

from install_system_updater import REPO, SOURCE_FILES
from runtime_files import atomic_json, atomic_text, directory_fd
from storage_maintenance import acquire_storage_lock
from system_update_contract import safe_read, strict_json
from system_update_gate import read_gate
from system_update_connection import UnixUpdateConnection
from system_updater import STATE_LIMIT, SystemUpdater, validate_policy


def _systemctl(*arguments: str) -> str:
    result = subprocess.run(['systemctl', *arguments], capture_output=True, text=True, timeout=60)
    if result.returncode:
        raise RuntimeError('更新底座服务操作失败，请核对服务状态')
    return result.stdout.strip()


def _probe(root: Path) -> dict:
    connection = UnixUpdateConnection(root / 'socket/updater.sock')
    try:
        token = safe_read(root / 'socket/token', 128, private=True).decode().strip()
        connection.request('GET', '/status', headers={'Authorization': 'Bearer ' + token})
        response = connection.getresponse()
        value = strict_json(response.read(128 * 1024 + 1))
        if response.status != 200:
            raise RuntimeError('更新底座状态接口尚未就绪')
        return value
    finally:
        connection.close()



@contextmanager
def _upgrade_lock(root: Path):
    descriptor = os.open(root / 'updater-upgrade.lock', os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield
    finally:
        os.close(descriptor)


def _journals(root: Path) -> dict:
    folder = root / 'updater-upgrades'
    if not folder.exists():
        return {}
    if folder != folder.resolve():
        raise ValueError('底座接入日志目录归属无效')
    values = {}
    for item in folder.iterdir():
        if str(uuid.UUID(item.name)) != item.name or not item.is_dir() or item != item.resolve():
            raise ValueError('底座接入日志目录无效')
        values[item.name] = strict_json(safe_read(item / 'upgrade.json', STATE_LIMIT, private=True), STATE_LIMIT)
    return values


def _service_owner(root: Path, service: str, control) -> None:
    if not re.fullmatch(r'[a-zA-Z0-9_-]+\.service', service):
        raise ValueError('底座服务名称无效')
    fragment = Path(control('show', '--property=FragmentPath', '--value', service))
    expected = [line for line in safe_read(root / 'vibebench-updater.service').decode().splitlines() if line.startswith('ExecStart=')]
    actual = [line for line in safe_read(fragment).decode().splitlines() if line.startswith('ExecStart=')]
    if len(expected) != 1 or actual != expected or str(root / 'source/deploy/v3/system_updater.py') not in expected[0]:
        raise ValueError('systemd 服务与本部署固定执行器归属不符')


def _target_state(state: dict) -> dict:
    target = copy.deepcopy(state)
    target['legacy_catalog'] = target.get('catalog', {})
    target.update(catalog={}, checked_at=None, check_error='底座已接入自动迁移，请检查更新')
    return target


def upgrade(policy_path: Path, source_root: Path, service: str, *, apply: bool = False, control=_systemctl, probe=_probe) -> dict:
    """升级单个已安装底座的精确文件，失败时按原副本恢复。

    :param policy_path: 当前 root 私有策略。
    :param source_root: 经操作者核验版本的源码根。
    :param service: 当前部署的 systemd 服务名称。
    :param apply: 默认预览；显式开启才修改底座。
    :param control: 可注入的固定 systemctl 边界。
    :param probe: 私有 socket 的真实状态核验入口。
    :return: 脱敏计划或升级结果。
    """
    root = policy_path.parent
    if root != root.resolve() or policy_path.name != 'policy.json':
        raise ValueError('底座升级策略路径需要真实绝对目录')
    with _upgrade_lock(root):
        return _upgrade(policy_path, source_root, service, apply=apply, control=control, probe=probe)


def _upgrade(policy_path: Path, source_root: Path, service: str, *, apply: bool, control, probe) -> dict:
    original_policy = safe_read(policy_path, private=True)
    policy = validate_policy(strict_json(original_policy))
    root = Path(policy['state_root'])
    if policy_path != root / 'policy.json' or not re.fullmatch(r'[a-zA-Z0-9_-]+\.service', service):
        raise ValueError('底座升级策略或服务名称无效')
    if source_root != source_root.resolve():
        raise ValueError('底座升级源码需要真实绝对目录')
    state_path = root / 'state.json'
    original_state = safe_read(state_path, STATE_LIMIT, private=True)
    state = strict_json(original_state, STATE_LIMIT)
    if state.get('active_operation') or read_gate(root / 'gate', policy['deployment'])['phase'] != 'idle':
        raise ValueError('底座升级前需完成原更新并释放维护门禁')
    journals = _journals(root)
    pending = [key for key, value in journals.items() if value.get('state') not in ('succeeded', 'restored')]
    if pending:
        raise ValueError('底座存在未完成接入，请按原 UUID 执行 --recover：' + ','.join(sorted(pending)))
    SystemUpdater(policy)
    if policy['schema_version'] == 2:
        return {'status': 'already-current', 'deployment': policy['deployment']}
    _service_owner(root, service, control)
    before, after = {}, {}
    for name in SOURCE_FILES:
        target = root / 'source' / name
        before[name] = safe_read(target) if target.exists() or target.is_symlink() else None
        after[name] = safe_read(source_root / name)
    plan = {'status': 'planned', 'deployment': policy['deployment'], 'service': service,
        'from_protocol': 1, 'to_protocol': 2, 'previous_upgrades': sorted(journals),
        'before_policy_sha256': hashlib.sha256(original_policy).hexdigest(),
        'before_state_sha256': hashlib.sha256(original_state).hexdigest(), 'files': [{'path': name,
            'before_sha256': hashlib.sha256(before[name]).hexdigest() if before[name] is not None else None,
            'after_sha256': hashlib.sha256(after[name]).hexdigest()} for name in SOURCE_FILES]}
    if not apply:
        return plan
    if control('is-active', service) != 'active':
        raise ValueError('底座升级前服务需要处于可核验运行状态')
    identifier = str(uuid.uuid4())
    plan['operation_id'] = identifier
    folder = root / 'updater-upgrades' / identifier
    # 恢复副本全部落盘后才发布日志目录；准备中断时服务仍由原安装运行。
    staging = root / ('updater-prepare-' + identifier)
    staging.mkdir(mode=0o700)
    for name, raw in before.items():
        if raw is not None:
            atomic_text(staging / 'before' / name, raw.decode())
    atomic_text(staging / 'before-policy.json', original_policy.decode())
    atomic_text(staging / 'before-state.json', original_state.decode())
    atomic_json(staging / 'upgrade.json', {**plan, 'state': 'prepared', 'changed': []})
    directory = directory_fd(folder.parent, create=True)
    try:
        os.rename(staging, folder)
        os.fsync(directory)
    finally:
        os.close(directory)
    service_lock = None
    storage_lock = None
    changed = []
    stopped = False
    try:
        control('stop', service)
        stopped = True
        service_lock = os.open(root / 'service.lock', os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
        fcntl.flock(service_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        storage_lock = acquire_storage_lock(Path(policy['data_root']))
        if (safe_read(policy_path, private=True) != original_policy or safe_read(state_path, STATE_LIMIT, private=True) != original_state
                or read_gate(root / 'gate', policy['deployment'])['phase'] != 'idle'):
            raise ValueError('停止服务后现场发生变化，保留原操作恢复权')
        for name in SOURCE_FILES:
            target = root / 'source' / name
            actual = safe_read(target) if target.exists() or target.is_symlink() else None
            if actual != before[name]:
                raise ValueError('底座源码在预览后发生变化')
            # 意图先记录；文件替换中断时保留精确的原、新 SHA 和恢复副本。
            changed.append(name)
            atomic_json(folder / 'upgrade.json', {**plan, 'state': 'replacing', 'changed': changed})
            atomic_text(target, after[name].decode())
        target_policy = {**policy, 'schema_version': 2}
        target_state = _target_state(state)
        atomic_json(policy_path, target_policy)
        atomic_json(state_path, target_state)
        SystemUpdater(target_policy)
        os.close(service_lock)
        service_lock = None
        control('start', service)
        if control('is-active', service) != 'active':
            raise RuntimeError('新更新底座启动未通过验收')
        deadline = time.monotonic() + 15
        while True:
            try:
                observed = probe(root)
                if (observed.get('migration_capability') is not True or observed.get('deployment') != policy['deployment']
                        or observed.get('current_release') != state['current']['release']['release'] or observed.get('revision') != state['revision']):
                    raise ValueError('新底座能力或安装状态与接入计划不符')
                break
            except (OSError, RuntimeError):
                if time.monotonic() >= deadline:
                    raise RuntimeError('新底座私有接口健康验收超时')
                time.sleep(0.2)
        current = strict_json(safe_read(state_path, STATE_LIMIT, private=True), STATE_LIMIT)
        if current.get('active_operation') or current['current'] != state['current'] or current['history'] != state['history'] or current['revision'] != state['revision']:
            raise ValueError('底座接入改变了原安装、历史或操作现场')
        atomic_json(folder / 'upgrade.json', {**plan, 'state': 'succeeded', 'changed': changed})
        return {**plan, 'status': 'upgraded', 'next': '进入系统更新页面检查新通道并安装新发行'}
    except Exception:
        if stopped:
            current = strict_json(safe_read(state_path, STATE_LIMIT, private=True), STATE_LIMIT)
            if current.get('active_operation') or current['current'] != state['current'] or current['revision'] != state['revision']:
                if service_lock is not None:
                    os.close(service_lock)
                    service_lock = None
                control('start', service)
                atomic_json(folder / 'upgrade.json', {**plan, 'state': 'needs-verification', 'changed': changed})
                raise ValueError('底座接入期间已有后来操作，保留当前源码与安装状态')
            control('stop', service)
            if service_lock is None:
                service_lock = os.open(root / 'service.lock', os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
                fcntl.flock(service_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            current = strict_json(safe_read(state_path, STATE_LIMIT, private=True), STATE_LIMIT)
            if current.get('active_operation') or current['current'] != state['current'] or current['revision'] != state['revision']:
                os.close(service_lock)
                service_lock = None
                control('start', service)
                raise ValueError('停止服务后发现后来操作，保留当前源码与安装状态')
            for name in reversed(changed):
                target = root / 'source' / name
                actual = safe_read(target) if target.exists() or target.is_symlink() else None
                if actual not in (before[name], after[name]):
                    raise ValueError('底座恢复遇到外来源码变更，保留恢复材料')
                if before[name] is None:
                    target.unlink(missing_ok=True)
                else:
                    atomic_text(target, before[name].decode())
            # 启动新服务后若有后来操作进入，不能覆盖其状态；保留现场供原操作恢复。
            current = strict_json(safe_read(state_path, STATE_LIMIT, private=True), STATE_LIMIT)
            if current.get('active_operation') or current['current'] != state['current'] or current['revision'] != state['revision']:
                raise ValueError('底座恢复发现后来操作，保留当前安装状态')
            atomic_text(policy_path, original_policy.decode())
            atomic_text(state_path, original_state.decode())
            if service_lock is not None:
                os.close(service_lock)
                service_lock = None
            control('start', service)
            atomic_json(folder / 'upgrade.json', {**plan, 'state': 'restored', 'changed': changed})
        raise
    finally:
        if service_lock is not None:
            os.close(service_lock)
        if storage_lock is not None:
            os.close(storage_lock)



def recover_upgrade(policy_path: Path, service: str, identifier: str, *, apply: bool = False,
                    control=_systemctl, probe=_probe) -> dict:
    """按原接入 UUID 恢复精确副本，允许服务停机及恢复过程再次中断。

    :param policy_path: 本部署真实绝对策略路径。
    :param service: 已核验归属的原服务名称。
    :param identifier: 未完成底座接入的原 UUID。
    :param apply: 默认仅预览，显式应用后恢复及启动原服务。
    :param control: 固定服务操作边界。
    :param probe: 原服务私有接口验收入口。
    :return: 脱敏恢复计划或完成回执；外来变化保留现场并报错。
    """
    root = policy_path.parent
    if root != root.resolve() or policy_path.name != 'policy.json' or str(uuid.UUID(identifier)) != identifier:
        raise ValueError('底座恢复路径或 UUID 无效')
    with _upgrade_lock(root):
        journals = _journals(root)
        journal = journals[identifier]
        if (journal.get('operation_id') != identifier or journal.get('service') != service
                or journal.get('state') not in ('prepared', 'replacing', 'needs-verification', 'recovering', 'restored')
                or journal.get('from_protocol') != 1 or journal.get('to_protocol') != 2
                or set(journals) != set(journal['previous_upgrades']) | {identifier}):
            raise ValueError('底座恢复归属或后续接入记录发生变化')
        files = journal['files']
        if [entry['path'] for entry in files] != list(SOURCE_FILES):
            raise ValueError('底座恢复源码清单无效')
        folder = root / 'updater-upgrades' / identifier
        original_policy = safe_read(folder / 'before-policy.json', private=True)
        original_state = safe_read(folder / 'before-state.json', STATE_LIMIT, private=True)
        if (hashlib.sha256(original_policy).hexdigest() != journal['before_policy_sha256']
                or hashlib.sha256(original_state).hexdigest() != journal['before_state_sha256']):
            raise ValueError('底座恢复副本摘要不符')
        policy = validate_policy(strict_json(original_policy))
        state = strict_json(original_state, STATE_LIMIT)
        if (policy['state_root'] != str(root) or policy['schema_version'] != 1
                or policy['deployment'] != journal['deployment'] or state['deployment'] != policy['deployment']
                or state.get('active_operation')):
            raise ValueError('底座恢复副本部署或操作归属无效')
        target_policy, target_state = {**policy, 'schema_version': 2}, _target_state(state)
        before = {}
        for entry in files:
            raw = None if entry['before_sha256'] is None else safe_read(folder / 'before' / entry['path'], private=True)
            if (raw is not None and hashlib.sha256(raw).hexdigest() != entry['before_sha256']
                    or not re.fullmatch(r'[0-9a-f]{64}', entry['after_sha256'])):
                raise ValueError('底座恢复源码副本摘要无效')
            before[entry['path']] = raw
        _service_owner(root, service, control)

        def inspect() -> None:
            # 只接受这次接入能产生的原值或目标值，避免旧日志覆盖后来业务或运维写入。
            current_policy = strict_json(safe_read(policy_path, private=True))
            current_state = strict_json(safe_read(root / 'state.json', STATE_LIMIT, private=True), STATE_LIMIT)
            if (current_policy not in (policy, target_policy) or current_state not in (state, target_state)
                    or read_gate(root / 'gate', policy['deployment'])['phase'] != 'idle'):
                raise ValueError('底座恢复发现后来操作或外来状态，保留现场')
            for entry in files:
                target = root / 'source' / entry['path']
                actual = safe_read(target) if target.exists() or target.is_symlink() else None
                digest = hashlib.sha256(actual).hexdigest() if actual is not None else None
                if digest not in (entry['before_sha256'], entry['after_sha256']):
                    raise ValueError('底座恢复遇到外来源码变更，保留恢复材料')

        inspect()
        plan = {'status': 'recovery-planned', 'operation_id': identifier, 'deployment': policy['deployment'],
            'service': service, 'action': 'restore-original', 'files': files}
        if not apply:
            return plan
        service_lock = None
        storage_lock = None
        try:
            control('stop', service)
            service_lock = os.open(root / 'service.lock', os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
            fcntl.flock(service_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            storage_lock = acquire_storage_lock(Path(policy['data_root']))
            inspect()
            # 整组恢复意图先落盘；任何文件替换中断后都能沿同一 UUID 再次核对及恢复。
            atomic_json(folder / 'upgrade.json', {**journal, 'state': 'recovering'})
            for name, raw in reversed(list(before.items())):
                target = root / 'source' / name
                if raw is None:
                    if target.exists():
                        target.unlink()
                        directory = os.open(target.parent, os.O_DIRECTORY | os.O_NOFOLLOW)
                        try:
                            os.fsync(directory)
                        finally:
                            os.close(directory)
                else:
                    atomic_text(target, raw.decode())
            atomic_text(policy_path, original_policy.decode())
            atomic_text(root / 'state.json', original_state.decode())
            SystemUpdater(policy)
            os.close(service_lock)
            service_lock = None
            control('start', service)
            if control('is-active', service) != 'active':
                raise RuntimeError('原更新底座启动未通过验收')
            deadline = time.monotonic() + 15
            while True:
                try:
                    observed = probe(root)
                    if (observed.get('migration_capability', False) is not False
                            or observed.get('deployment') != policy['deployment']
                            or observed.get('revision') != state['revision']
                            or observed.get('current_release') != state['current']['release']['release']):
                        raise ValueError('原底座能力或安装状态与恢复副本不符')
                    break
                except (OSError, RuntimeError):
                    if time.monotonic() >= deadline:
                        raise RuntimeError('原底座私有接口恢复验收超时')
                    time.sleep(0.2)
            # 恢复完成后记录终态；后来操作仍须按精确原值保护。
            inspect()
            atomic_json(folder / 'upgrade.json', {**journal, 'state': 'restored'})
            return {**plan, 'status': 'recovered'}
        finally:
            if service_lock is not None:
                os.close(service_lock)
            if storage_lock is not None:
                os.close(storage_lock)


def main() -> None:
    """预览或显式应用一次底座升级。@return None。"""
    parser = argparse.ArgumentParser(description='固定更新底座迁移能力接入')
    parser.add_argument('--policy', type=Path, required=True)
    parser.add_argument('--source-root', type=Path, default=REPO)
    parser.add_argument('--service', required=True)
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--recover', metavar='UUID', help='按未完成接入的原 UUID 预览恢复；与 --apply 合用时执行')
    args = parser.parse_args()
    value = (recover_upgrade(args.policy, args.service, args.recover, apply=args.apply) if args.recover
        else upgrade(args.policy, args.source_root, args.service, apply=args.apply))
    print(json.dumps(value, ensure_ascii=False))


if __name__ == '__main__':
    main()
