"""三个固定角色的在线CPU额度与重建持久化，不改变内存、PID及运行生命周期。"""
import hashlib
import json
import os
import uuid
from decimal import Decimal, InvalidOperation

from runtime_files import atomic_json, directory_fd
from system_update_contract import safe_read, strict_json


ROLES = ('cli', 'sender', 'network')
NANO = 1_000_000_000


def default_cpu_limits(values: dict | None = None) -> dict[str, int]:
    """统一解析新隔离角色的独立默认CPU。@param values 部署配置，省略时读取环境。@return CLI/sender/network的NanoCpus；非法配置拒绝。"""
    configuration = os.environ if values is None else values
    result = {}
    for role, default in (('cli', '1.5'), ('sender', '1.5'), ('network', '0.5')):
        raw = configuration.get(f'V3_ACCOUNT_{role.upper()}_CPUS', default)
        if raw == '':
            raw = default
        try:
            if type(raw) not in (str, int, float):
                raise ValueError('CPU默认值必须为数字')
            amount = Decimal(str(raw))
            if not amount.is_finite() or amount < Decimal('0.01'):
                raise ValueError('CPU默认额度至少0.01核，且最多九位有效小数')
            # 先转精确整数比，避免Decimal上下文在乘法时抹掉超出纳核精度的小数。
            numerator, denominator = amount.as_integer_ratio()
            nano_cpus, remainder = divmod(numerator * NANO, denominator)
            if remainder:
                raise ValueError('CPU默认额度至少0.01核，且最多九位有效小数')
            result[role] = nano_cpus
        except InvalidOperation:
            raise ValueError('CPU默认额度格式无效') from None
    return result


def read_policy(runtime, row: dict) -> dict | None:
    """读取本环境的私有CPU策略，历史缺失采用原默认额度。

    :param runtime: 权威运行时。
    :param row: 当前环境行。
    :return: 已验证策略或None；损坏与错误归属拒绝使用。
    """
    try:
        value = strict_json(safe_read(runtime._root(row) / 'runtime/cpu-resources.json', 8192, private=True), 8192)
    except FileNotFoundError:
        return None
    if (set(value) != {'schema_version', 'environment_id', 'account_id', 'revision', 'nano_cpus'}
            or type(value['schema_version']) is not int or value['schema_version'] != 1
            or value['environment_id'] != row['environment_id'] or value['account_id'] != row.get('account_id')
            or type(value['account_id']) is not type(row.get('account_id'))
            or not isinstance(value['revision'], str) or str(uuid.UUID(value['revision'])) != value['revision']
            or not isinstance(value['nano_cpus'], dict) or set(value['nano_cpus']) != set(ROLES)
            or any(type(v) is not int or v < 10_000_000 for v in value['nano_cpus'].values())):
        raise ValueError('CPU持久策略损坏或环境归属不符')
    return value


def _collect(runtime, row):
    # 创建角色时会读取策略；延后导入角色所有者，避免模块初始化形成循环。
    from account_isolation import ISOLATION_VERSION, role_container
    if row.get('isolation_version') != ISOLATION_VERSION:
        raise ValueError('当前环境需先升级为三个独立角色')
    containers, observations = {}, {}
    for role in ROLES:
        container = role_container(runtime, row, role)
        container.reload()
        info = container.attrs
        limits = {key: info['HostConfig'].get(key) for key in ('NanoCpus', 'Memory', 'MemorySwap', 'PidsLimit')}
        if type(limits['NanoCpus']) is not int or limits['NanoCpus'] < 10_000_000:
            raise ValueError('实际CPU额度尚未核对')
        containers[role] = container
        observations[role] = {'id': container.id, 'image': info['Image'], 'limits': limits,
            'started_at': info['State']['StartedAt'], 'restarts': info['RestartCount'],
            'state': {key: info['State'].get(key) for key in ('Status', 'Running', 'Pid')}}
    return containers, observations


def _revision(row, policy, observations):
    value = {'environment_id': row['environment_id'], 'generation': row['generation'],
        'policy': policy, 'actual': observations}
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def _update_cpu(runtime, container, nano_cpus):
    # 当前Docker SDK的update_container未暴露NanoCpus；沿其相同JSON/状态校验入口调用真实API。
    api = runtime.client.api
    url = api._url('/containers/{0}/update', container.id)
    api._result(api._post_json(url, data={'NanoCpus': nano_cpus}), True)


def _public(row, policy, observations, host_cpus):
    return {'generation': row['generation'], 'revision': _revision(row, policy, observations),
        'host_cpus': host_cpus, 'cpus': {role: value['limits']['NanoCpus'] / NANO for role, value in observations.items()},
        'persisted_cpus': {role: value / NANO for role, value in policy['nano_cpus'].items()} if policy else None}


def read_resources(runtime, row: dict) -> dict:
    """只读取得实际额度及乐观并发摘要。

    :param runtime: 权威运行时。
    :param row: 当前环境行。
    :return: 页面可用的有限资源字段。
    """
    _, observations = _collect(runtime, row)
    host_cpus = runtime.client.info().get('NCPU')
    if type(host_cpus) is not int or host_cpus <= 0:
        raise ValueError('Docker宿主CPU数量尚未核对')
    return _public(row, read_policy(runtime, row), observations, host_cpus)


def set_resources(runtime, row: dict, expected_generation: int, expected_revision: str, cpus: dict) -> dict:
    """在部署活动与环境锁内原地调整CPU，验证后发布重建策略。

    :param runtime: 已登记部署维护活动的运行时。
    :param row: 调用方在环境锁内重读的当前行。
    :param expected_generation: 页面冻结的环境代次。
    :param expected_revision: 页面冻结的实际额度摘要。
    :param cpus: 三角色分别设置的正数核数。
    :return: 最新实际值；失败恢复原额度，未知恢复结果保留在操作记录。
    """
    from native_kernel_upgrade import status as kernel_status
    if row.get('state') not in ('ready', 'stopped'):
        raise ValueError('环境正在维护或需要先对账')
    if runtime.reviews.serial_state(row) is not None:
        raise ValueError('评审资源正在交接，请完成后再调整CPU')
    kernel = kernel_status(runtime, row)
    if kernel and kernel.get('state') in ('preparing', 'draining', 'switching', 'restoring', 'finishing', 'reconcile'):
        raise ValueError('内核操作正在进行，请完成后再调整CPU')
    containers, before = _collect(runtime, row)
    original = read_policy(runtime, row)
    host_cpus = runtime.client.info().get('NCPU')
    if type(host_cpus) is not int or host_cpus <= 0:
        raise ValueError('Docker宿主CPU数量尚未核对')
    if expected_generation != row['generation'] or expected_revision != _revision(row, original, before):
        raise ValueError('环境或CPU额度已变化，请重新读取后调整')
    if not isinstance(cpus, dict) or set(cpus) != set(ROLES):
        raise ValueError('必须分别指定CLI、API发送器和网络的CPU额度')
    desired = {}
    for role, value in cpus.items():
        try:
            if type(value) not in (int, float):
                raise ValueError('CPU额度必须为数字')
            amount = Decimal(str(value)) * NANO
            if not amount.is_finite() or amount != amount.to_integral_value():
                raise ValueError('CPU额度需为有限数字且最多九位小数')
            desired[role] = int(amount)
        except InvalidOperation:
            raise ValueError('CPU额度格式无效') from None
        if desired[role] < 10_000_000 or desired[role] > host_cpus * NANO:
            raise ValueError('每项CPU额度应为0.01到宿主可用核数之间')
    policy_path = runtime._root(row) / 'runtime/cpu-resources.json'
    audit_path = runtime._root(row) / 'runtime/cpu-resources-operation.json'
    policy = {'schema_version': 1, 'environment_id': row['environment_id'], 'account_id': row.get('account_id'),
        'revision': str(uuid.uuid4()), 'nano_cpus': desired}
    audit = {'operation_id': str(uuid.uuid4()), 'generation': row['generation'], 'state': 'applying',
        'before': before, 'original_policy': original, 'target': desired}
    atomic_json(audit_path, audit)
    attempted, policy_attempted = [], False
    try:
        for role in ROLES:
            if desired[role] != before[role]['limits']['NanoCpus']:
                # Docker返回异常时也可能已经生效，恢复集合必须先于调用登记。
                attempted.append(role)
                _update_cpu(runtime, containers[role], desired[role])
        _, after = _collect(runtime, row)
        for role in ROLES:
            expected = {**before[role], 'limits': {**before[role]['limits'], 'NanoCpus': desired[role]}}
            if after[role] != expected:
                raise ValueError('CPU更新后的实际资源或容器生命周期发生变化')
        policy_attempted = True
        atomic_json(policy_path, policy)
        if read_policy(runtime, row) != policy:
            raise ValueError('CPU持久策略发布后校验失败')
        atomic_json(audit_path, {**audit, 'state': 'applied'})
        return _public(row, policy, after, host_cpus)
    except Exception:
        restored = True
        for role in reversed(attempted):
            try:
                _update_cpu(runtime, containers[role], before[role]['limits']['NanoCpus'])
            except Exception:
                restored = False
        try:
            _, recovered = _collect(runtime, row)
            restored = restored and recovered == before
            if policy_attempted:
                if original is not None:
                    atomic_json(policy_path, original)
                else:
                    directory = directory_fd(policy_path.parent)
                    try:
                        try:
                            os.unlink(policy_path.name, dir_fd=directory)
                        except FileNotFoundError:
                            pass
                        os.fsync(directory)
                    finally:
                        os.close(directory)
        except Exception:
            restored = False
        atomic_json(audit_path, {**audit, 'state': 'restored' if restored else 'reconcile'})
        raise RuntimeError('CPU调整失败，原额度已恢复' if restored else 'CPU调整结果需要对账，请重新读取实际额度') from None
