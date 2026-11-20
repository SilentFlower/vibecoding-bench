"""同一 AGY 环境代次的并发容量更新与故障收口。"""
import json
import re
from urllib.error import HTTPError
from urllib.request import ProxyHandler, Request, build_opener

from docker.errors import DockerException

from account_isolation import ROLE_COLUMNS, role_container
from agy_environment import lookup
from native_criu_policy import restore_policy
from resource_budget import agy_worker_limits, default_account_memory, sender_pid_limit
from runtime_files import atomic_json
from system_update_contract import safe_read, strict_json

MIB = 1024 ** 2
_LIMIT_KEYS = ('Memory', 'MemorySwap', 'PidsLimit')


class CapacityError(ValueError):
    """用于管理入口的脱敏容量故障。"""


def _receipt_path(runtime, row):
    return runtime._root(row) / 'runtime/agy-capacity.json'


def _receipt(runtime, row):
    try:
        receipt = strict_json(safe_read(_receipt_path(runtime, row), 4096, private=True), 4096)
    except FileNotFoundError:
        return None
    if (receipt.get('schema_version') != 1 or receipt.get('account_id') != row['gateway_account_id']
            or receipt.get('environment_id') != row['environment_id']
            or not isinstance(receipt.get('operation_id'), str)
            or not re.fullmatch(r'[a-f0-9]{32}', receipt['operation_id'])
            or any(type(receipt.get(key)) is not int or not 1 <= receipt[key] <= 64 for key in ('before', 'target'))):
        raise CapacityError('capacity_changed')
    return receipt if receipt.get('generation') == row['generation'] else None


def pending_layout(runtime, row: dict, applied: dict, desired: dict) -> bool:
    """识别同一操作的容量过渡，继续使用原绑定。@param runtime 运行时。@param row 原环境。@param applied 当前配置。@param desired 网关目标。@return 是否为同一操作内的资源差异。"""
    if not isinstance(applied, dict):
        return False
    layout_keys = set(desired) - {'max_workers', 'memory_mib'}
    if set(applied) != set(desired) or any(applied[key] != desired[key] for key in layout_keys):
        return False
    receipt = _receipt(runtime, row)
    if receipt is None:
        return False
    workers = (receipt['before'], receipt['target'])
    return (type(applied['max_workers']) is int and applied['max_workers'] in workers and desired['max_workers'] in workers
            and type(applied['memory_mib']) is int and applied['memory_mib'] >= 0)


def _gateway(runtime, account_id, operation_id):
    config = runtime.gateway._request('GET', f'/admin/runtime/accounts/{account_id}/config?capacity_operation={operation_id}')
    if (not isinstance(config, dict) or config.get('account_id') != account_id
            or config.get('platform') != 'antigravity' or config.get('auth_type') != 'oauth'
            or type(config.get('capacity_edit_active')) is not bool
            or type(config.get('concurrency')) is not int or not 1 <= config['concurrency'] <= 64):
        raise CapacityError('capacity_changed')
    return config


def _sender(row, binding, workers=None):
    identity = {'account_id': row['gateway_account_id'], 'environment_id': row['environment_id'],
        'generation': row['generation']}
    if any(binding.get(key) != value for key, value in identity.items()):
        raise CapacityError('capacity_changed')
    body = json.dumps({**identity, 'max_workers': workers}).encode() if workers is not None else None
    suffix = '/internal/agy/capacity' if body is not None else '/internal/status'
    request = Request(binding['endpoint'] + suffix, data=body,
        headers={'Authorization': 'Bearer ' + binding['secret'], 'Content-Type': 'application/json'})
    try:
        # 状态的进程指标沿环境摘要的 1MiB 预算，容量回执只包含归属和上限。
        limit = 1048576 if body is None else 4096
        with build_opener(ProxyHandler({})).open(request, timeout=15 if body is not None else 5) as response:
            result = strict_json(response.read(limit + 1), limit)
    except HTTPError as error:
        if error.code == 404:
            raise CapacityError('capacity_unsupported') from None
        raise CapacityError('capacity_pending') from None
    if result.get('environment_id') != identity['environment_id'] or result.get('generation') != identity['generation']:
        raise CapacityError('capacity_changed')
    if workers is not None:
        if result.get('account_id') != identity['account_id'] or result.get('max_workers') != workers:
            raise CapacityError('capacity_pending')
        return result
    status = result.get('agy')
    if not isinstance(status, dict) or status.get('state') in ('unknown', 'reconcile'):
        raise CapacityError('capacity_pending')
    if status.get('capacity_protocol') != 1:
        raise CapacityError('capacity_unsupported')
    if type(status.get('allocated_workers')) is not int:
        raise CapacityError('capacity_pending')
    return status


def _observed(container):
    container.reload()
    return {key: container.attrs['HostConfig'][key] for key in _LIMIT_KEYS}


def _lifecycle(container):
    state = container.attrs['State']
    return (state['Running'], state.get('Pid'), state.get('StartedAt'), container.attrs.get('RestartCount'))


def _can_reduce(container, before, after):
    memory_down = after['Memory'] > 0 and (before['Memory'] == 0 or after['Memory'] < before['Memory'])
    pids_down = 0 < after['PidsLimit'] < before['PidsLimit']
    if not (memory_down or pids_down) or not container.attrs['State']['Running']:
        return True
    stats = container.stats(stream=False, one_shot=True)
    memory = stats.get('memory_stats', {}).get('usage')
    pids = stats.get('pids_stats', {}).get('current')
    return ((not memory_down or (type(memory) is int and memory < after['Memory']))
            and (not pids_down or (type(pids) is int and pids < after['PidsLimit'])))


def _apply(runtime, row, target):
    config = runtime.read_sender_configuration(row)
    original = config['agy']
    fingerprint = json.loads(row['fingerprint_json'])
    memory_mib, limits = agy_worker_limits(target, fingerprint)
    containers = {role: role_container(runtime, row, role) for role in ROLE_COLUMNS}
    before = {role: _observed(container) for role, container in containers.items()}
    running = {container.attrs['State']['Running'] for container in containers.values()}
    if len(running) != 1 or (row['state'] == 'ready') != next(iter(running)):
        raise CapacityError('capacity_changed')
    live = next(iter(running))
    desired = {role: {**before[role], 'Memory': ram, 'MemorySwap': total} for role, (ram, total) in limits.items()}
    desired['sender']['PidsLimit'] = sender_pid_limit(target, agy=True)
    if before['network'] != desired['network']:
        raise CapacityError('capacity_changed')
    status = _sender(row, config['binding']) if live else None
    memory_before = before['sender']['Memory'] // MIB

    def publish(workers, memory):
        previous = (config['agy'], config.get('native_criu_enabled'), config.get('native_criu_reason'))
        config['agy'] = {**original, 'max_workers': workers, 'memory_mib': memory}
        policy = restore_policy(config['agy'], fingerprint, containers['sender'].labels.get('vibebench.agy-criu') == '1')
        config.update(native_criu_enabled=policy['eligible'], native_criu_reason=policy['reason'])
        if (config['agy'], policy['eligible'], policy['reason']) != previous:
            runtime._write_sender_config(row, config)
        if live:
            _sender(row, config['binding'], workers)

    reducing = (desired['sender']['Memory'] < before['sender']['Memory']
        or desired['sender']['PidsLimit'] < before['sender']['PidsLimit'])
    if target < original['max_workers'] or reducing:
        if (before['sender']['Memory'] < desired['sender']['Memory']
                or before['sender']['PidsLimit'] < desired['sender']['PidsLimit']):
            raise CapacityError('capacity_pending')
        # 先约束分配，再等待超出的实例自然归还。保留正在使用的角色额度。
        publish(target, memory_before)
        if status and status['allocated_workers'] > target:
            return False
    if not all(_can_reduce(containers[role], before[role], desired[role]) for role in ('cli', 'sender')):
        if reducing:
            return False
        raise CapacityError('capacity_busy')
    if live and status['state'] == 'unprepared' and before['sender'] != desired['sender'] and not reducing:
        # 活角色先建立监督器，避免角色额度更新期间用旧配置启动。
        _sender(row, config['binding'], original['max_workers'])
    order = ('cli', 'sender') if desired['sender']['Memory'] > before['sender']['Memory'] else ('sender', 'cli')
    api = runtime.client.api
    for role in order:
        container = containers[role]
        if before[role] != desired[role]:
            # Docker Python SDK 未暴露在线 PidsLimit，沿实际 update 接口更新。
            lifecycle = _lifecycle(container)
            api._result(api._post_json(api._url('/containers/{0}/update', container.id), data=desired[role]), True)
            if _observed(container) != desired[role] or _lifecycle(container) != lifecycle:
                raise CapacityError('capacity_pending')
    publish(target, memory_mib)
    return True


def _ready_row(row):
    present = [bool(row.get(column)) for column in ROLE_COLUMNS.values()]
    if row['state'] not in ('ready', 'stopped') or (any(present) and not all(present)):
        raise CapacityError('capacity_changed')
    return all(present)


def _settle(runtime, row, receipt, workers):
    if workers not in (receipt['before'], receipt['target']):
        raise CapacityError('capacity_changed')
    if not _ready_row(row) or _apply(runtime, row, workers):
        _receipt_path(runtime, row).unlink(missing_ok=True)


def change_capacity(runtime, account_id: int, operation_id: str, before: int, target: int, phase: str) -> None:
    """准备或收口同一账号的容量变更。@param runtime 运行时。@param account_id 网关账号。@param operation_id 原操作。@param before 原上限。@param target 目标。@param phase 准备或收口。@return 回执成功时无返回值。"""
    row = lookup(runtime, account_id)
    if row is None:
        if phase == 'prepare':
            _budget(target, {'mem': default_account_memory()})
        return
    with runtime.environment_lock(row['environment_id']):
        environment_id = row['environment_id']
        row = lookup(runtime, account_id)
        if row is None or row['environment_id'] != environment_id:
            raise CapacityError('capacity_changed')
        receipt = _receipt(runtime, row)
        if phase == 'reconcile':
            if receipt is not None:
                authority = _gateway(runtime, account_id, receipt['operation_id'])
                if authority['capacity_edit_active']:
                    raise CapacityError('capacity_changed')
                _settle(runtime, row, receipt, authority['concurrency'])
            return
        authority = _gateway(runtime, account_id, operation_id)
        if phase == 'settle' and receipt and receipt['operation_id'] != operation_id:
            return
        if phase == 'prepare' and (not authority['capacity_edit_active'] or authority['concurrency'] != before
                or authority.get('credential_state', {}).get('phase') != 'ready'):
            raise CapacityError('capacity_changed')
        if phase == 'prepare':
            _budget(target, json.loads(row['fingerprint_json']))
        if not _ready_row(row):
            return
        if receipt and receipt['operation_id'] != operation_id:
            previous = _gateway(runtime, account_id, receipt['operation_id'])
            if previous['capacity_edit_active']:
                raise CapacityError('capacity_changed')
            _settle(runtime, row, receipt, previous['concurrency'])
            receipt = None
        if receipt is None:
            if phase == 'settle' and authority['concurrency'] != target:
                return
            config = runtime.read_sender_configuration(row)
            if row['state'] == 'ready':
                status = _sender(row, config['binding'])
                if status['max_workers'] != before and phase == 'prepare':
                    raise CapacityError('capacity_changed')
                if status['state'] == 'unprepared' and phase == 'prepare':
                    _sender(row, config['binding'], before)
            receipt = {'schema_version': 1, 'account_id': account_id, 'environment_id': row['environment_id'],
                'generation': row['generation'], 'operation_id': operation_id, 'before': before, 'target': target}
            atomic_json(_receipt_path(runtime, row), receipt)
        if (receipt['before'], receipt['target']) != (before, target):
            raise CapacityError('capacity_changed')
        if phase == 'prepare' and target > before:
            # 连续编辑可直接使用尚未回收的较高额度，后台继续回收多出的部分。
            _apply(runtime, row, target)
        elif phase == 'settle':
            _settle(runtime, row, receipt, authority['concurrency'])


def _budget(target, fingerprint):
    try:
        agy_worker_limits(target, fingerprint)
    except ValueError:
        raise CapacityError('capacity_memory') from None


def reconcile_pending(runtime) -> None:
    """在原环境锁内继续无人持有的容量操作。@param runtime 运行时。@return 无。"""
    connection = runtime.database()
    try:
        ids = [row[0] for row in connection.execute("SELECT gateway_account_id FROM platform_api_environments WHERE platform='antigravity'")]
    finally:
        connection.close()
    for account_id in ids:
        try:
            row = lookup(runtime, account_id)
            if row is None or not _receipt_path(runtime, row).is_file():
                continue
            with runtime.environment_lock(row['environment_id']):
                environment_id = row['environment_id']
                row = lookup(runtime, account_id)
                receipt = _receipt(runtime, row) if row and row['environment_id'] == environment_id else None
                if receipt is None:
                    continue
                authority = _gateway(runtime, account_id, receipt['operation_id'])
                if not authority['capacity_edit_active']:
                    _settle(runtime, row, receipt, authority['concurrency'])
        except (DockerException, KeyError, OSError, RuntimeError, ValueError):
            # 未知结果保留同代收据。下次按真实网关配置和角色额度重读。
            continue
