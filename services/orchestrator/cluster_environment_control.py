"""中央环境管理按人工归属调用具体 Node 操作并镜像实际状态。"""
from __future__ import annotations

import hashlib
import json
import time
from uuid import uuid4

from account_runtime import RuntimeBusy
from cluster_deployment import node_container_name
from cluster_environment_management import (
    EnvironmentCapture, EnvironmentChoice, EnvironmentCpu, EnvironmentMaintenance,
    EnvironmentReference, EnvironmentState,
)
from cluster_execution_grants import ExecutionLeaseProof
from cluster_execution_store import NodeExecutions
from system_update_contract import strict_json


def _lease_proof(value):
    # 原Gateway还返回phase；有限证明只传既有ExecutionLeaseProof定义的字段。
    return ExecutionLeaseProof.model_validate({key: value[key] for key in ExecutionLeaseProof.model_fields if key in value})


class RemoteEnvironmentControl:
    """资源及维护沿原中央准入执行，实际 Docker 和文件由所属 Node 承接。

    :param service: 原节点服务。
    :param runtime: 原中央环境登记。
    :param gateway: 原唯一 Gateway。
    :param quota_identity: 当前账号的原额度身份读取器。
    """

    def __init__(self, service, runtime, gateway, quota_identity) -> None:
        """保存原依赖。:param service: 节点。:param runtime: 环境。:param gateway: 网关。:param quota_identity: 额度。:return: None。"""
        self.service, self.runtime, self.gateway, self.quota_identity = service, runtime, gateway, quota_identity

    def _context(self, account_id, environment_id):
        assignment = self.service.store.assignment(account_id)
        if assignment['kind'] != 'ssh' or assignment['phase'] != 'ready':
            raise RuntimeBusy('环境节点归属正在维护，请先核对原操作')
        node = self.service.store.get(assignment['node_id'])
        preparation = strict_json((node['preparation_json'] or '{}').encode(), 65536)
        if preparation.get('state') != 'prepared' or preparation.get('release') != self.runtime.release_id:
            raise ValueError('请先准备所属节点的同批组件')
        connection = self.service.store.database()
        try:
            account = connection.execute('SELECT * FROM accounts WHERE id=? AND deleted_at IS NULL', (account_id,)).fetchone()
            row = connection.execute('SELECT * FROM account_environments WHERE account_id=? AND environment_id=?',
                (account_id, environment_id)).fetchone()
        finally:
            connection.close()
        if account is None or row is None or account['name'] != row['name']:
            raise ValueError('原账号环境已变化，请重新读取')
        scope = EnvironmentState(node_key=assignment['node_key'], account_id=account_id,
            environment_id=environment_id, assignment_revision=assignment['revision'], gateway_account_id=account['cc2api_account_id'])
        return scope, dict(account), dict(row), assignment['node_id'], hashlib.sha256(node['config_json'].encode()).hexdigest()

    def _rpc(self, context, request, operation):
        scope, account, row, node_id, digest = context
        value = self.service.connection(node_id).execution_environment(
            node_container_name(self.runtime.deployment, scope.node_key), request.model_dump(), operation)
        fresh = self._context(account['id'], row['environment_id'])
        location = scope.model_dump(exclude={'gateway_account_id'})
        if (type(value.get('protocol')) is not int or value['protocol'] != 1 or value.get('node_key') != scope.node_key
                or value.get('location') != location or fresh[0] != scope or fresh[3:] != context[3:]):
            raise ValueError('环境管理期间原 Node 归属或 SSH 配置已变化')
        actual = value.get('environment')
        fields = ('fingerprint_json', 'generation', 'container_id', 'network_container_id', 'sender_container_id', 'state', 'isolation_version')
        if (not isinstance(actual, dict) or any(key not in actual for key in fields)
                or (actual.get('environment_id'), actual.get('account_id'), actual.get('name'))
                != (row['environment_id'], account['id'], account['name'])
                or type(actual.get('generation')) is not int or actual['generation'] < row['generation']
                or actual.get('isolation_version') != 2 or actual.get('state') not in
                ('ready', 'stopped', 'cli_reconcile', 'reconcile', 'retired', 'starting', 'profile_reauth', 'profile_reauth_reconcile')):
            raise ValueError('原 Node 实际环境回执需要核对')
        if not isinstance(value.get('result'), dict) or any(
                actual[key] is not None and not isinstance(actual[key], str)
                for key in ('container_id', 'network_container_id', 'sender_container_id')):
            raise ValueError('原 Node 环境结果需要核对')
        before, after = json.loads(row['fingerprint_json']), json.loads(actual['fingerprint_json'])
        if not isinstance(before,dict) or not isinstance(after,dict):
            raise ValueError('原Node环境画像回执需要核对')
        if any(before.get(key) != after.get(key) for key in ('hostname', 'machine_id', 'mac', 'tz', 'lang')):
            raise ValueError('原 Node 环境稳定身份已变化')
        with self.service.store.lock:
            connection = self.service.store.database()
            try:
                with connection:
                    updated = connection.execute('UPDATE account_environments SET ' + ','.join(key + '=?' for key in fields)
                        + ' WHERE environment_id=? AND account_id=? AND generation=?',
                        (*(actual[key] for key in fields), row['environment_id'], account['id'], row['generation']))
                    if updated.rowcount != 1:
                        raise ValueError('环境镜像代次已变化，请重新读取实际状态')
            finally:
                connection.close()
        return value['result'], actual

    def call(self, row: dict, operation: str, body: dict | None = None) -> dict:
        """核对实际代次后执行一次具体 Node 管理动作。

        :param row: 中央已解析的原环境。
        :param operation: 固定私有操作名。
        :param body: 原公共接口已校验的设置或读取参数。
        :return: 原业务有限结果，环境行只镜像回中央私有库。
        """
        body = body or {}
        with self.runtime.environment_lock(row['environment_id']):
            context = self._context(row['account_id'], row['environment_id'])
            self._rpc(context, context[0], 'environment-state')
            context = self._context(row['account_id'], row['environment_id'])
            scope, account, current, _, _ = context
            reference = {**scope.model_dump(), 'generation': current['generation'], 'observation': body.get('observation')}
            proof, path, owner = None, None, None
            recovering, stopped = False, False
            submitted, completed = False, False
            try:
                if operation == 'environment-cpu-set':
                    if body['expected_generation'] != current['generation']:
                        raise ValueError('环境代次已变化，请重新读取')
                    request = EnvironmentCpu(**reference, expected_revision=body['expected_revision'], cpus=body['cpus'])
                elif operation == 'environment-capture-read':
                    request = EnvironmentCapture(**reference, attempt_id=body['attempt_id'])
                elif operation in ('environment-capture-set', 'environment-criu-set', 'environment-maintenance'):
                    if NodeExecutions(self.service.store, self.runtime.release_id).active(account['id']):
                        raise RuntimeBusy('原 Node 工作尚未收口，请先停止并核对原操作')
                    binding = account['cc2api_account_id']
                    if operation=='environment-maintenance' and body.get('operation')=='stop' and binding is not None:
                        self.gateway._request('POST',f'/admin/accounts/{binding}/native-preparation?cancel=true',{})
                    recovering = False
                    if binding is not None:
                        path = f'/admin/runtime/accounts/{binding}/lease'
                        snapshot = self.gateway._request('GET', path)
                        holder = snapshot.get('lease')
                        if (operation == 'environment-maintenance' and body.get('operation') == 'reconcile'
                                and holder and holder.get('expires_at', 0) <= time.time()
                                and not snapshot.get('active') and not snapshot.get('waiting')):
                            proof, recovering = _lease_proof(holder), True
                        else:
                            if any(snapshot.get(key) for key in ('active', 'waiting', 'lease', 'holders')):
                                raise RuntimeBusy('原绑定仍有活动或维护门禁，请先等待原操作收口')
                            prefix = {'environment-capture-set': 'capture', 'environment-criu-set': 'criu'}.get(operation, 'maintenance')
                            owner = prefix + ':' + uuid4().hex
                            prepared = self.gateway._request('POST', path, {'operation': 'prepare', 'owner': owner})
                            lease = self.runtime._owned_lease(prepared, owner)
                            if not lease or prepared.get('active') or prepared.get('waiting'):
                                raise RuntimeBusy('原环境管理门禁尚未排空')
                            proof = _lease_proof(lease)
                            claimed = self.gateway._request('POST', path, {'operation': 'claim', 'owner': owner, 'generation': proof.generation})
                            actual = self.runtime._owned_lease(claimed, owner)
                            if (actual is None or actual.get('phase') != 'claimed'
                                    or _lease_proof(actual).model_dump(exclude={'expires_at'}) != proof.model_dump(exclude={'expires_at'})):
                                raise RuntimeBusy('原环境管理门禁认领尚待核对')
                            proof = _lease_proof(actual)
                    if operation == 'environment-maintenance':
                        request = EnvironmentMaintenance(**reference, operation=body['operation'], lease=proof, recovering=recovering)
                    else:
                        if proof is None or body['expected_generation'] != current['generation']:
                            raise ValueError('配置切换需要原绑定及实际环境代次')
                        request = EnvironmentChoice(**reference, expected_revision=body['expected_revision'], enabled=body['enabled'],
                            configuration=self.gateway._request('GET', f'/admin/runtime/accounts/{binding}/config'),
                            quota_identity=self.quota_identity(account), lease=proof)
                else:
                    request = EnvironmentReference(**reference)
                submitted = True
                result, actual = self._rpc(context, request, operation)
                if operation=='environment-maintenance' and (result.get('stopped') is not True or actual['state']!='stopped'):
                    raise ValueError('原Node实际停止回执仍需核对')
                stopped = operation == 'environment-maintenance' and result.get('ok') is True
                completed = True
                return result
            finally:
                if proof is None and owner is not None:
                    try:
                        snapshot=self.gateway._request('GET',path)
                        actual=self.runtime._owned_lease(snapshot,owner)
                        if actual:
                            proof=_lease_proof(actual)
                    except Exception:
                        self.runtime._update(current,state='reconcile')
                        raise RuntimeError('原环境门禁准备结果待核对，请继续原环境对账') from None
                if proof is not None and submitted and not completed:
                    # SSH结果未知时Node线程可能仍在重建；到期门禁继续关闭，显式对账确认停止后再释放。
                    self.runtime._update(current, state='reconcile')
                if proof is not None and (not submitted or completed) and (not recovering or stopped):
                    try:
                        self.gateway._request('POST', path, {'operation': 'release', 'owner': proof.owner, 'generation': proof.generation})
                    except Exception:
                        self.runtime._update(current, state='reconcile')
                        raise RuntimeError('原环境管理门禁释放结果待核对，请继续原环境对账') from None
