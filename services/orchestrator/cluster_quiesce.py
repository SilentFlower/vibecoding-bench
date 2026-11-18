"""原Gateway配置事务在所属SSH节点收口空闲环境。"""
from __future__ import annotations

import re
import time
import json

from pydantic import Field, StrictInt, model_validator

from account_runtime import RuntimeBusy
from cluster_deployment import node_container_name
from cluster_execution import NodeExecution, NodeLocation, _GatewaySnapshot
from cluster_execution_grants import ExecutionLeaseProof
from cluster_execution_store import NodeExecutions
from cluster_verification import pending_run_programs
from native_kernel_upgrade import pending_upgrade


class NodeQuiesce(NodeLocation):
    """冻结原配置排他门禁的有限空闲停止范围。

    :param gateway_account_id: 原绑定账号。
    :param generation: 实际环境代次。
    :param lease: 原gateway-config排他门禁。
    """

    gateway_account_id: StrictInt = Field(ge=1)
    generation: StrictInt = Field(ge=0)
    lease: ExecutionLeaseProof

    @model_validator(mode='after')
    def validate_configuration_lease(self):
        """只接受原配置事务排他来源。:return: 已核对的有限请求。"""
        if (not self.lease.exclusive or self.lease.shared_cli
                or re.fullmatch(r'gateway-config:[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}',self.lease.owner) is None):
            raise ValueError('节点配置收口需要原Gateway排他配置门禁')
        return self


def quiesce_node(executor: NodeExecution, request: NodeQuiesce) -> dict:
    """持有原环境锁，确认实际空闲后停止原角色并返回物理事实。

    :param executor: 原安装节点执行器。
    :param request: 中央核对的原配置门禁与完整环境范围。
    :return: 精确范围及实际停止结果；未决工作保持失败。
    """
    with executor._locked(environment_id=request.environment_id):
        if not time.time()<request.lease.expires_at<=time.time()+35:
            raise ValueError('原节点配置门禁已过期或截止超出允许范围')
        row=executor._inspection_row(request)
        connection=executor.database()
        try:
            account=connection.execute('SELECT * FROM accounts WHERE id=?',(request.account_id,)).fetchone()
        finally:
            connection.close()
        if (account is None or account['cc2api_account_id']!=request.gateway_account_id
                or account['deleted_at'] is not None or row['generation']!=request.generation):
            raise ValueError('原节点配置门禁的账号绑定或环境代次已经变化')
        # 停止操作只借用原运行时；空配置不能覆盖其已投影的账号配置和额度来源。
        runtime=executor._runtime(_GatewaySnapshot(0,{}))
        try:
            root=runtime._root(row)
            runtime._check_node_fence(row)
            executor._check_execution_records(runtime,row)
            pending=[root/'runtime'/name for name in ('login-commit.json','credential-handoff.json')]
            pending.append(executor.data/'login-drafts'/(request.environment_id+'.json'))
            if (runtime.environment_jobs(request.environment_id) or runtime.reviews.serial_state(row)
                    or pending_run_programs(executor.data,request.environment_id) or pending_upgrade(root)
                    or any(path.exists() or path.is_symlink() for path in pending)
                    or runtime._running_sender_active(row)):
                raise RuntimeBusy('原节点配置收口等待实际工作与发送连接结束')
            runtime.reviews.check_orphans(row)
            if not time.time()<request.lease.expires_at<=time.time()+35:
                raise ValueError('原节点配置门禁已过期或截止超出允许范围')
            runtime._stop_environment(row)
            expected=dict(runtime._labels(row))
            expected.pop('vibebench.role')
            for container in runtime.client.containers.list(all=True,filters={'label':[key+'='+value for key,value in expected.items()]}):
                if container.labels.get('vibebench.cluster-node')!=runtime.node_key:
                    continue
                container.reload()
                state=container.attrs.get('State',{})
                if (any(container.labels.get(key)!=value for key,value in expected.items())
                        or state.get('Running') is not False or state.get('Pid')!=0):
                    raise ValueError('原节点角色实际停止结果仍需核对')
            runtime._update(row,state='stopped')
            return {'protocol':1,'node_key':executor.node_key,'request':request.model_dump(),'stopped':True}
        finally:
            executor._release_runtime(runtime)


def quiesce_remote(service, runtime, account: dict, lease: dict) -> None:
    """原中央配置回调按当前归属请求所属Node的实际停止。

    :param service: 原节点服务。
    :param runtime: 中央环境登记器。
    :param account: 当前绑定账号。
    :param lease: 原Gateway已核验的真实配置门禁。
    :return: None；未知保持配置失败，由原Gateway释放自身门禁。
    """
    row=runtime._row(account['name'],account['id'])
    with runtime.environment_lock(row['environment_id']):
        if NodeExecutions(service.store,runtime.release_id).active(account['id']):
            raise RuntimeBusy('原节点仍有未收口执行，配置事务继续等待')
        assignment=service.store.assignment(account['id'])
        if assignment['kind']!='ssh' or not assignment['enabled'] or assignment['phase']!='ready':
            raise RuntimeBusy('原节点配置收口的人工归属尚未就绪')
        node=service.store.get(assignment['node_id'])
        preparation=json.loads(node['preparation_json'] or '{}')
        if preparation.get('state')!='prepared' or preparation.get('release')!=runtime.release_id:
            raise RuntimeBusy('原节点配置收口需要同批控制组件')
        request=NodeQuiesce(node_key=assignment['node_key'],account_id=account['id'],
            gateway_account_id=account['cc2api_account_id'],environment_id=row['environment_id'],
            assignment_revision=assignment['revision'],generation=row['generation'],
            lease=ExecutionLeaseProof.model_validate({key:lease[key] for key in
                ('owner','generation','expires_at','exclusive','shared_cli')}))
        result=service.connection(assignment['node_id']).execution_environment(
            node_container_name(runtime.deployment,assignment['node_key']),request.model_dump(),'account-quiesce')
        if result!={'protocol':1,'node_key':assignment['node_key'],'request':request.model_dump(),'stopped':True}:
            raise ValueError('原节点配置收口的实际停止回执需要核对')
        actual=service.store.assignment(account['id'])
        if (any(actual[key]!=assignment[key] for key in ('node_id','node_key','revision','phase','kind','enabled'))
                or service.store.get(assignment['node_id'])['config_json']!=node['config_json']):
            raise ValueError('原节点配置收口期间人工归属已经变化')
        runtime._update(row,state='stopped')
