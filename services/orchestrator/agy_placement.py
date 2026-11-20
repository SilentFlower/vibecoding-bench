"""中央 AGY 归属的传输、节点回执与容量路由。"""
from contextlib import contextmanager
import hashlib
import ipaddress
import json
import os
import uuid
from urllib.error import HTTPError

from docker.errors import DockerException

from account_isolation import ISOLATION_VERSION, ROLE_COLUMNS
from account_update_identity import configured_release
from agy_capacity import CapacityError, _receipt as capacity_receipt, change_capacity
from agy_environment import lookup, register, summary, transport
from agy_node import AgyNode
from agy_node_contract import AgyLocation, AgyPreparation
from cluster_deployment import node_container_name
from cluster_execution import NodeExecution
from cluster_transport import NodeTransport


class AgyPlacement:
    """按唯一 AGY 归属路由中央操作。@param service 中央集群服务。@param runtime 中央运行时。"""

    def __init__(self, service, runtime):
        """保存中央权威和本机目标投影。@param service 集群服务。@param runtime 中央运行时。@return 无。"""
        self.service, self.runtime = service, runtime
        self.store = service.store
        self.local = AgyNode(NodeExecution(runtime.data, runtime.host_data, 'local',
            runtime.deployment, service.local_client, local_runtime=runtime))

    def command(self, node_id: int, operation: str, payload: dict) -> dict:
        """经固定节点控制执行原动作。@param node_id 节点。@param operation 固定 AGY 动作。@param payload 原范围。@return 私有回执。"""
        node = self.store.get(node_id)
        if node['kind'] == 'local':
            return self.local.call(operation, payload)
        return self.service.connection(node_id).agy_environment(
            node_container_name(self.runtime.deployment, node['node_key']), payload, operation)

    def configuration(self, account_id: int, operation_id: str | None = None) -> dict:
        """读取原 AGY 网关的最新配置及指定操作证明。@param account_id 网关账号。@param operation_id 容量操作。@return 当前配置。"""
        query = '' if operation_id is None else '?capacity_operation=' + operation_id
        config = self.runtime.gateway._request('GET', f'/admin/runtime/accounts/{account_id}/config' + query)
        if (config.get('account_id') != account_id or config.get('platform') != 'antigravity'
                or config.get('auth_type') != 'oauth'):
            raise ValueError('AGY 网关账号身份已变化')
        return config

    def scope(self, row: dict, assignment: dict) -> dict:
        """冻结权威环境及执行来源。@param row 当前环境。@param assignment 当前分配。@return 节点精确定位。"""
        return AgyLocation(node_key=assignment['node_key'], account_id=row['gateway_account_id'],
            environment_id=row['environment_id'], assignment_revision=assignment['revision'],
            generation=row['generation']).model_dump()

    @contextmanager
    def current(self, account_id: int):
        """同一锁内重读 AGY 环境和归属。@param account_id 网关账号。@return 当前环境及归属。"""
        row = lookup(self.runtime, account_id)
        if row is None:
            raise ValueError('AGY 账号运行环境尚未登记')
        with self.runtime.environment_lock(row['environment_id']):
            updated = lookup(self.runtime, account_id)
            if updated is None or updated['environment_id'] != row['environment_id']:
                raise ValueError('AGY 网关环境已变化')
            yield updated, self.store.agy_assignment(account_id)

    def transport(self, account_id: int, *, wake: bool) -> dict | None:
        """解析当前执行节点并核对真实发送绑定。@param account_id 网关账号。@param wake 是否唤醒。@return 受限绑定。"""
        if lookup(self.runtime, account_id) is None:
            if not wake:
                return None
            config = self.configuration(account_id)
            if config.get('status') != 'active' or config.get('credential_state', {}).get('phase') != 'ready':
                raise ValueError('AGY 网关凭据或账号尚未就绪')
            register(self.runtime, account_id)
        with self.current(account_id) as (row, assignment):
            if not self._accepts(assignment):
                raise ValueError('AGY 所属节点正在维护或已暂停接单')
            if assignment['kind'] == 'local':
                return transport(self.runtime, account_id, wake=wake)
            node = self.store.get(assignment['node_id'])
            prepared = json.loads(node['preparation_json'] or '{}')
            if prepared.get('state') != 'prepared' or prepared.get('release') != self.runtime.release_id:
                raise ValueError('AGY 所属节点需要准备同批运行组件')
            scope = self.scope(row, assignment)
            peer = self.command(assignment['node_id'], 'agy-prepare', AgyPreparation(
                **scope, environment=row, configuration=self.configuration(account_id), wake=wake).model_dump())
            actual, binding = self.prepared(peer, scope, wake=wake)
            self._mirror(row, assignment, actual)
            if binding is None:
                return None
            address = str(ipaddress.ip_address(peer['sender_address']))
            path = self.service.connection(assignment['node_id']).sender_socket(row['environment_id'], address)
            self.service.transports.register(NodeTransport(node['id'], node['node_key'], account_id,
                row['environment_id'], assignment['revision'], actual['generation'], path, binding['secret'], agy=True))
            deployment = hashlib.sha256(self.runtime.deployment.encode()).hexdigest()[:12]
            base = os.environ.get('V3_RUNTIME_URL', 'http://orchestrator:8000').rstrip('/')
            endpoint = f"{base}/cluster-transports/v2/{deployment}/{node['node_key']}/{row['environment_id']}/{assignment['revision']}"
            return {**binding, 'endpoint': endpoint}

    def _accepts(self, assignment):
        if assignment['phase'] == 'ready':
            return assignment['enabled']
        # 排空时网关门禁拦截新请求，已取得原许可的请求及其工具仍可使用出处绑定。
        return self.store.agy_draining(assignment['account_id'], assignment['revision'])

    def prepared(self, peer: dict, scope: dict, *, wake: bool) -> tuple[dict, dict | None]:
        """核对节点的精确运行回执。@param peer 节点原回执。@param scope 原节点范围。@param wake 是否已准备。@return 实际环境和绑定。"""
        actual, binding = peer.get('environment'), peer.get('binding')
        if (peer.get('protocol') != 1 or peer.get('node_key') != scope['node_key']
                or peer.get('assignment_revision') != scope['assignment_revision']
                or not isinstance(actual, dict) or actual.get('gateway_account_id') != scope['account_id']
                or actual.get('platform') != 'antigravity' or actual.get('account_id') is not None
                or actual.get('environment_id') != scope['environment_id']
                or actual.get('name') != f"agy:{scope['account_id']}"
                or type(actual.get('generation')) is not int or actual['generation'] < scope['generation']
                or actual.get('state') not in ('ready', 'stopped')
                or actual.get('isolation_version') != ISOLATION_VERSION):
            raise ValueError('AGY 实际环境回执归属已变化')
        if binding is not None:
            if (not isinstance(binding, dict) or binding.get('account_id') != scope['account_id']
                    or binding.get('environment_id') != scope['environment_id']
                    or binding.get('generation') != actual['generation']
                    or binding.get('release_id') != configured_release(self.runtime)
                    or not isinstance(binding.get('secret'), str) or not 32 <= len(binding['secret']) <= 256
                    or not all(isinstance(actual.get(field), str) for field in ROLE_COLUMNS.values())):
                raise ValueError('AGY 实际发送绑定或角色回执无效')
            ipaddress.ip_address(peer['sender_address'])
        elif wake:
            raise ValueError('AGY 实际发送器尚未准备')
        return actual, binding

    def _mirror(self, row, assignment, actual):
        before, after = json.loads(row['fingerprint_json']), json.loads(actual['fingerprint_json'])
        if any(before.get(key) != after.get(key) for key in ('hostname', 'machine_id', 'mac', 'tz', 'lang')):
            raise ValueError('AGY 逻辑环境身份已变化')
        current = self.store.agy_assignment(row['gateway_account_id'])
        if any(current[key] != assignment[key] for key in ('node_id', 'revision', 'phase')):
            raise ValueError('AGY 环境准备期间节点归属已变化')
        self.runtime._update(row, **{key: actual[key] for key in (
            'fingerprint_json', 'generation', 'state', 'isolation_version', *ROLE_COLUMNS.values())})

    def exact(self, row: dict, assignment: dict, operation: str, **body) -> dict:
        """调用指定代次并核对完整回执。@param row 原环境。@param assignment 原分配。@param operation 固定动作。@return 实际节点回执。"""
        scope = self.scope(row, assignment)
        result = self.command(assignment['node_id'], operation, {**scope, **body})
        if any(result.get(key) != value for key, value in {'protocol': 1, **scope}.items()):
            raise ValueError('AGY 节点返回了过期或其他环境回执')
        return result

    def control(self, row: dict, action: str, body: dict | None = None) -> tuple[bool, object]:
        """管理操作只找当前所属节点。@param row AGY 环境。@param action 固定动作。@param body 原管理入参。@return 是否远程处理及实际结果。"""
        account_id = row['gateway_account_id']
        with self.current(account_id) as (current, assignment):
            if current['generation'] != row['generation'] or assignment['phase'] != 'ready':
                raise ValueError('AGY 环境归属或维护状态已变化')
            if assignment['kind'] == 'local':
                return False, None
            if action in ('stop', 'rebuild', 'reconcile', 'quiesce'):
                with self._maintenance(account_id, body if action == 'quiesce' else None):
                    result = self.exact(current, assignment, 'agy-control', action=action, body=body or {})
            else:
                result = self.exact(current, assignment, 'agy-control', action=action, body=body or {})
            actual = result['environment']
            if (actual.get('platform'), actual.get('gateway_account_id'), actual.get('account_id'),
                    actual.get('environment_id'), actual.get('generation')) != (
                    'antigravity', account_id, None, current['environment_id'], current['generation']):
                raise ValueError('AGY 管理结果与当前环境不一致')
            self._mirror(current, assignment, actual)
            return True, result['value']

    @contextmanager
    def _maintenance(self, account_id, proof):
        gateway = self.runtime.gateway
        path = f'/admin/runtime/accounts/{account_id}/lease'
        if proof is not None:
            snapshot = gateway._request('GET', path)
            lease = snapshot.get('lease')
            # 网关配置事务持有排他门禁，在活动已经为零时直接调用静默接口。
            if (not lease or lease.get('exclusive') is not True or lease.get('phase') not in ('draining', 'claimed')
                    or lease['owner'] != proof.get('owner') or lease['generation'] != proof.get('generation')
                    or snapshot.get('active') != 0):
                raise ValueError('AGY 配置许可已变化')
            yield
            return
        owner = 'maintenance:' + uuid.uuid4().hex
        snapshot = gateway._request('POST', path, {'operation': 'prepare', 'owner': owner})
        lease = snapshot.get('lease')
        if not lease or lease.get('owner') != owner or lease.get('exclusive') is not True:
            raise ValueError('AGY 维护许可未确认')
        proof = {'owner': owner, 'generation': lease['generation']}
        try:
            if snapshot.get('active') != 0 or snapshot.get('waiting'):
                raise ValueError('AGY 账号仍有原请求或工具工作')
            claimed = gateway._request('POST', path, {'operation': 'claim', **proof})
            if (claimed.get('lease') or {}).get('phase') != 'claimed':
                raise ValueError('AGY 维护许可尚未认领')
            yield
        finally:
            gateway._request('POST', path, {'operation': 'release', **proof})

    def summary(self, row: dict) -> dict:
        """按归属读取环境的实际公开状态。@param row 中央环境。@return 环境卡片投影。"""
        assignment = self.store.agy_assignment(row['gateway_account_id'])
        if assignment['kind'] == 'local':
            return {**summary(self.runtime, row), 'node': assignment}
        observed = {'fingerprint': json.loads(row['fingerprint_json']), 'state': 'node_unreachable',
            'role_status': {role: 'unknown' for role in ROLE_COLUMNS}, 'busy': True, 'request_backend': 'agy159',
            'node_observed': False, 'node_message': 'AGY 所属节点状态待核对', 'platform_release': self.runtime.release_id}
        try:
            value = self.exact(row, assignment, 'agy-inspect')['environment']
            observed.update(value, node_observed=True, node_message='已读取 AGY 所属节点的实际环境')
        except (ValueError, RuntimeError, OSError, DockerException, KeyError, TypeError):
            pass
        return {**{key: value for key, value in row.items() if key != 'fingerprint_json'},
            **observed, 'node': assignment}

    def capacity(self, account_id: int, operation_id: str, before: int, target: int, phase: str) -> None:
        """在原代次完成网关容量协议。@param account_id 网关账号。@param operation_id 容量操作。@param before 原容量。@param target 新容量。@param phase 原阶段。@return 无。"""
        if lookup(self.runtime, account_id) is None:
            change_capacity(self.runtime, account_id, operation_id, before, target, phase)
            return
        with self.current(account_id) as (row, assignment):
            if assignment['phase'] != 'ready':
                if phase == 'prepare':
                    raise CapacityError('capacity_changed')
                if phase == 'settle' and not self.store.agy_draining(account_id, assignment['revision']):
                    return
            self._change_capacity(row, assignment, operation_id, before, target, phase)

    def _change_capacity(self, row, assignment, operation_id, before, target, phase):
        account_id = row['gateway_account_id']
        receipt = self._capacity_receipt(row, assignment)
        # 新归属只接受自己已有的操作回执，原归属的迟到 settle 不能改写新代次。
        if phase == 'settle' and not (receipt and receipt['operation_id'] == operation_id):
            return
        if assignment['kind'] == 'local':
            change_capacity(self.runtime, account_id, operation_id, before, target, phase)
            return
        authorities = {operation_id: self.configuration(account_id, operation_id)}
        if receipt and receipt['operation_id'] not in authorities:
            previous = receipt['operation_id']
            authorities[previous] = self.configuration(account_id, previous)
        value = self.exact(row, assignment, 'agy-capacity', operation_id=operation_id,
            before=before, target=target, phase=phase, authorities=authorities)
        if value.get('error') in ('capacity_changed', 'capacity_memory', 'capacity_pending'):
            raise CapacityError(value['error'])
        if value.get('operation_id') != operation_id:
            raise ValueError('AGY 容量回执不属于原操作')

    def _capacity_receipt(self, row, assignment):
        if assignment['kind'] == 'local':
            return capacity_receipt(self.runtime, row)
        return self.exact(row, assignment, 'agy-capacity-state')['receipt']

    def settle_capacity(self, row: dict, assignment: dict) -> None:
        """迁移前核对并收口原归属容量。@param row 源环境。@param assignment 源分配。@return 无。"""
        receipt = self._capacity_receipt(row, assignment)
        if receipt:
            self._change_capacity(row, assignment, receipt['operation_id'], receipt['before'], receipt['target'], 'reconcile')
        if self._capacity_receipt(row, assignment) is not None:
            raise CapacityError('capacity_pending')

    def reconcile_capacities(self) -> None:
        """按当前 SSH 归属收口已丢失响应的容量调整。@return 无。"""
        for assignment in self.store.agy_assignments():
            if assignment['kind'] != 'ssh' or assignment['phase'] != 'ready':
                continue
            try:
                with self.current(assignment['account_id']) as (row, current):
                    if current == assignment:
                        self.settle_capacity(row, current)
            except (ValueError, RuntimeError, OSError, DockerException):
                # 活动缩容或暂时失联保留原回执，后续周期继续核对。
                continue

    def reconcile_retired(self) -> None:
        """收口已删除账号留下的 SSH 归属。@return 无。"""
        candidates = self.store.agy_retirement_candidates()
        if not candidates:
            return
        present = {row['id'] for row in self.runtime.gateway.list_accounts(require_complete=True, platform='antigravity')}
        for candidate in candidates:
            account_id = candidate['account_id']
            if account_id in present:
                continue
            try:
                self.configuration(account_id)
            except ValueError as error:
                # 完整列表用于筛选，单账号 404 确认删除，避免分页移动掩盖有效账号。
                cause = error.__cause__
                if isinstance(cause, HTTPError) and cause.code == 404:
                    self.store.retire_agy_assignment(candidate)
            except (RuntimeError, OSError):
                # 原网关失联时保留归属，由后续清理周期重新核对。
                continue
