"""所属 Node 的具体资源、采集与空闲维护，复用原环境实现。"""
from __future__ import annotations

import re
import time
from typing import Literal

from pydantic import Field, StrictBool, StrictFloat, StrictInt, StrictStr

from cluster_execution import NodeLocation, _GatewaySnapshot
from cluster_execution_grants import ExecutionLeaseProof
from cluster_owner_node import _idle, _stopped
from content_capture_settings import read_settings as read_capture_settings, set_settings as set_capture_settings
from cpu_resources import read_resources, set_resources
from native_capture import CaptureExpired, read_capture
from native_criu_settings import read_settings as read_criu_settings, set_settings as set_criu_settings


class EnvironmentState(NodeLocation):
    """仅发现原绑定当前实际环境，保持无容器准备。

    :param gateway_account_id: 当前唯一 Gateway 绑定，独立账号为空。
    """

    gateway_account_id: StrictInt | None = Field(default=None, ge=1)


class EnvironmentReference(EnvironmentState):
    """具体管理动作使用已经发现的实际代次。

    :param generation: 原 Node 当前环境代次。
    :param observation: 原 Gateway 对该账号的只读准备观察。
    """

    generation: StrictInt = Field(ge=0)
    observation: dict | None = None


class EnvironmentCpu(EnvironmentReference):
    """冻结三角色 CPU 修改。

    :param expected_revision: 原实际资源摘要。
    :param cpus: 各角色核数，原资源实现继续核验真实宿主上限。
    """

    expected_revision: StrictStr = Field(pattern='^[a-f0-9]{64}$')
    cpus: dict[Literal['cli', 'sender', 'network'], StrictFloat | StrictInt]


class EnvironmentChoice(EnvironmentReference):
    """中央真实排他门禁内的单个配置选择。

    :param expected_revision: 原策略及角色摘要。
    :param enabled: 管理员明确选择。
    :param configuration: 原 Gateway 当前受限运行配置。
    :param quota_identity: 原账号额度身份。
    :param lease: 本次中央已认领的真实门禁。
    """

    expected_revision: StrictStr = Field(pattern='^[a-f0-9]{64}$')
    enabled: StrictBool
    configuration: dict
    quota_identity: StrictStr = Field(max_length=4096)
    lease: ExecutionLeaseProof


class EnvironmentCapture(EnvironmentReference):
    """只读取原 Gateway 尝试的已脱敏私有快照。

    :param attempt_id: 原尝试标准 UUID。
    """

    attempt_id: StrictStr = Field(pattern='^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$')


class EnvironmentMaintenance(EnvironmentReference):
    """保留身份的实际空闲停止及重建收口。

    :param operation: 原环境停止、重建或对账。
    :param lease: 绑定账号的真实中央排他门禁，独立账号为空。
    """

    operation: Literal['stop', 'rebuild', 'reconcile']
    lease: ExecutionLeaseProof | None = None
    recovering: StrictBool = False


class _ConfigurationLease:
    """将中央已持有的真实门禁提供给原配置生命周期。"""

    def __init__(self, account_id: int, proof: ExecutionLeaseProof) -> None:
        """冻结一次许可。:param account_id: 原绑定。:param proof: 原门禁。:return: None。"""
        self.path, self.proof, self.prepared = f'/admin/runtime/accounts/{account_id}/lease', proof, False

    def _request(self, method, path, payload=None):
        if path != self.path:
            raise ValueError('环境配置操作超出原绑定许可')
        if method == 'GET':
            return {'active': 0, 'waiting': 0, 'lease': self.proof.model_dump() if self.prepared else None}
        if method != 'POST' or payload.get('owner') != self.proof.owner:
            raise ValueError('环境配置门禁来源不一致')
        operation = payload.get('operation')
        if operation in ('prepare', 'claim'):
            _permit(self.proof)
            if operation == 'claim' and payload.get('generation') != self.proof.generation:
                raise ValueError('环境配置门禁代次不一致')
            self.prepared = True
            return {'active': 0, 'lease': self.proof.model_dump()}
        if operation == 'release' and payload.get('generation') == self.proof.generation:
            self.prepared = False
            return {'ok': True}
        raise ValueError('环境配置门禁动作无效')


def _permit(proof, *, recovering=False):
    if recovering:
        if proof.expires_at > time.time():
            raise ValueError('原环境门禁仍有效，请等待原操作收口')
        return
    if (not proof.exclusive or proof.shared_cli or not time.time() < proof.expires_at <= time.time() + 35):
        raise ValueError('原环境管理门禁已到期或范围不一致')


def environment_management(executor, request: EnvironmentState, operation: str) -> dict:
    """在完整归属及实际代次中执行一个固定管理操作。

    :param executor: 原安装 Node 执行器。
    :param request: 具体操作模型。
    :param operation: Actor 固定白名单中的操作名。
    :return: 原请求定位、实际环境行及有限结果。
    """
    with executor._locked(environment_id=request.environment_id):
        location = NodeLocation.model_validate(request.model_dump(include=set(NodeLocation.model_fields)))
        row = executor._inspection_row(location)
        connection = executor.database()
        try:
            stored = connection.execute('SELECT * FROM accounts WHERE id=?', (request.account_id,)).fetchone()
        finally:
            connection.close()
        if (stored is None or stored['name'] != row['name'] or stored['deleted_at'] is not None
                or stored['cc2api_account_id'] != request.gateway_account_id):
            raise ValueError('原 Node 环境管理的账号绑定已变化')
        account = dict(stored)
        if operation == 'environment-state':
            return {'protocol':1,'node_key':executor.node_key,'location':location.model_dump(),
                'environment':row,'result':{}}
        if isinstance(request, EnvironmentReference) and request.generation != row['generation']:
            raise ValueError('原 Node 环境管理代次已变化')
        gateway = (_GatewaySnapshot(request.gateway_account_id, request.configuration, bench_account_id=request.account_id)
            if isinstance(request, EnvironmentChoice) else _GatewaySnapshot(0, {}))
        runtime = executor._runtime(gateway,
            (lambda account: request.quota_identity) if isinstance(request, EnvironmentChoice) else None)
        try:
            result = {}
            current = {**row, 'gateway_account_id': request.gateway_account_id}
            if operation == 'environment-cpu-read':
                result = read_resources(runtime, current)
            elif operation == 'environment-cpu-set':
                runtime._check_node_fence(row)
                result = set_resources(runtime, current, request.generation, request.expected_revision, request.cpus)
            elif operation == 'environment-physical-refresh':
                runtime._check_node_fence(row)
                executor._check_execution_records(runtime, row)
                runtime.refresh_physical_features(row)
                result = {'ok': True}
            elif operation == 'environment-capture-read':
                if request.gateway_account_id is None:
                    raise ValueError('请求快照需要原 Gateway 绑定')
                try:
                    result = {'state': 'available', 'snapshot': read_capture(runtime._root(row), request.gateway_account_id, request.attempt_id)}
                except CaptureExpired:
                    result = {'state': 'expired'}
                except FileNotFoundError:
                    result = {'state': 'missing'}
            elif operation in ('environment-capture-settings', 'environment-criu-settings'):
                if request.gateway_account_id is None:
                    raise ValueError('配置读取需要原 Gateway 绑定')
                reader = read_capture_settings if operation == 'environment-capture-settings' else read_criu_settings
                result = reader(runtime, current, request.observation)
            elif operation in ('environment-capture-set', 'environment-criu-set'):
                prefix = 'capture' if operation == 'environment-capture-set' else 'criu'
                if request.gateway_account_id is None or re.fullmatch(prefix + ':[a-f0-9]{32}', request.lease.owner) is None:
                    raise ValueError('环境配置来源与原门禁不一致')
                if request.configuration.get('account_id')!=request.gateway_account_id:
                    raise ValueError('环境配置快照来自另一Gateway账号')
                _permit(request.lease)
                runtime._check_node_fence(row)
                _idle(executor, runtime, row)
                setter = set_capture_settings if prefix == 'capture' else set_criu_settings
                result = setter(runtime, current, account, request.enabled, request.generation, request.expected_revision,
                    lease_gateway=_ConfigurationLease(request.gateway_account_id, request.lease), lease_owner=request.lease.owner)
            elif operation == 'environment-maintenance':
                if request.gateway_account_id is not None:
                    if request.recovering and request.operation!='reconcile':
                        raise ValueError('过期门禁仅用于原实际停止对账')
                    if request.lease is None or (not request.recovering and re.fullmatch('maintenance:[a-f0-9]{32}', request.lease.owner) is None):
                        raise ValueError('绑定环境维护需要原排他门禁')
                    _permit(request.lease,recovering=request.recovering)
                elif request.lease is not None:
                    raise ValueError('独立环境维护保持无 Gateway 门禁')
                runtime._check_node_fence(row)
                _idle(executor, runtime, row)
                runtime._stop_environment(row, remove=request.operation in ('rebuild', 'reconcile'))
                _stopped(runtime, row)
                runtime._update(row, state='stopped')
                result = {'ok': True,'stopped':True}
            elif operation != 'environment-state':
                raise ValueError('环境管理操作无效')
            connection = executor.database()
            try:
                actual = dict(connection.execute('SELECT * FROM account_environments WHERE environment_id=?', (row['environment_id'],)).fetchone())
            finally:
                connection.close()
            return {'protocol': 1, 'node_key': executor.node_key, 'location': location.model_dump(),
                'environment': actual, 'result': result}
        finally:
            executor._release_runtime(runtime)
