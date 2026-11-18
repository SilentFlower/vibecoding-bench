"""所属Node按原凭据交接执行实际停止和原运行凭据发布。"""
from __future__ import annotations

import re
import time
from urllib.error import HTTPError

from account_runtime import RuntimeBusy
from cluster_execution import NodeLocation, _GatewaySnapshot
from database_migrations import apply_migrations
from cluster_owner_contract import OwnerPrepare, OwnerPublish, OwnerReceipt
from cluster_verification import pending_run_programs
from native_kernel_upgrade import pending_upgrade
from runtime_files import atomic_json
from system_update_contract import safe_read, strict_json


class _PreparedGateway:
    """将中央已持有的真实lease作为原Node停止事务的只读许可。"""

    def __init__(self, request):
        """保存已校验的中央许可。:param request: 原发布请求。:return: None。"""
        self.request=request
        self.leases={item.account_id:item.lease.model_dump() for item in request.leases}

    def _request(self, method, path, payload=None):
        matched=re.fullmatch(r'/admin/runtime/accounts/([1-9][0-9]*)/lease',path)
        if matched is not None and int(matched[1]) in self.request.missing_bindings:
            raise ValueError('原Gateway绑定已由中央完整缺失核验') from HTTPError(path,404,'原绑定不存在',{},None)
        if matched is None or int(matched[1]) not in self.leases:
            raise ValueError('节点交接超出原中央排他许可')
        lease=self.leases[int(matched[1])]
        if method=='GET':
            # 原owner_transition会自行prepare；这里借用已认领许可，避免Node另建刷新所有者。
            return {'active':0,'waiting':0,'lease':None}
        if method=='POST' and payload.get('operation')=='prepare':
            _deadline(self.request)
            return {'active':0,'lease':lease}
        if (method=='POST' and payload=={'operation':'release','owner':lease['owner'],'generation':lease['generation']}):
            return {'ok':True}
        raise ValueError('节点交接许可仅允许原准备和归还')

    def list_accounts(self, *, require_complete=False):
        """消费中央已验证的旧绑定完整缺失结论。

        :param require_complete: 原运行时要求完整缺失证明。
        :return: 仅原缺失绑定收口使用的空集合。
        """
        if not require_complete or not self.request.missing_bindings:
            raise ValueError('节点交接没有原绑定完整缺失结论')
        return []


def _deadline(request):
    if not time.time()<request.not_after<=time.time()+35:
        raise ValueError('原节点凭据交接许可已到期')


def _path(executor, environment_id):
    return executor.data/'environments'/environment_id/'runtime/owner-transition.json'


def owner_receipt(executor, request: NodeLocation) -> dict | None:
    """查询当前环境的原交接，不构造运行时或续期。

    :param executor: 原安装Node。
    :param request: 原账号及人工分配范围。
    :return: 无令牌持久回执；尚无操作时为None。
    """
    with executor._locked(read_only=True,environment_id=request.environment_id):
        executor._inspection_row(request)
        return _read(executor,request)


def _read(executor, location):
    try:
        receipt=OwnerReceipt.model_validate(strict_json(safe_read(_path(executor,location.environment_id),16384,private=True),16384))
    except FileNotFoundError:
        return None
    if any(getattr(receipt.scope,key)!=value for key,value in location.model_dump().items()):
        raise ValueError('原节点交接的账号或分配范围已经变化')
    return receipt.model_dump()


def _account(executor, scope):
    row=executor._inspection_row(NodeLocation.model_validate(scope.model_dump(include=set(NodeLocation.model_fields))))
    connection=executor.database()
    try:
        stored=connection.execute('SELECT * FROM accounts WHERE id=?',(scope.account_id,)).fetchone()
    finally:
        connection.close()
    if (stored is None or stored['name']!=row['name'] or stored['deleted_at'] is not None or row['generation']!=scope.generation):
        raise ValueError('原节点交接的账号或环境代次已经变化')
    return dict(stored),row


def _idle(executor, runtime, row, resuming=False):
    root=runtime._root(row)
    fence=root/'runtime/node-fence.json'
    if fence.exists() or fence.is_symlink():
        if strict_json(safe_read(fence,8192,private=True),8192).get('phase')!='cancelled':
            raise RuntimeBusy('原环境正在迁移，凭据交接等待完成')
    executor._check_execution_records(runtime,row)
    pending=[root/'runtime/login-commit.json']
    if not resuming:
        pending.append(root/'runtime/credential-handoff.json')
    pending.append(executor.data/'login-drafts'/(row['environment_id']+'.json'))
    if (runtime.environment_jobs(row['environment_id']) or runtime.reviews.serial_state(row)
            or pending_run_programs(executor.data,row['environment_id']) or pending_upgrade(root)
            or any(path.exists() or path.is_symlink() for path in pending) or runtime._running_sender_active(row)):
        raise RuntimeBusy('凭据交接等待原节点实际工作与发送连接结束')
    runtime.reviews.check_orphans(row)


def _stopped(runtime, row):
    labels=dict(runtime._labels(row))
    labels.pop('vibebench.role')
    for container in runtime.client.containers.list(all=True,filters={'label':[key+'='+value for key,value in labels.items()]}):
        if container.labels.get('vibebench.cluster-node')!=runtime.node_key:
            continue
        container.reload()
        state=container.attrs.get('State',{})
        if any(container.labels.get(key)!=value for key,value in labels.items()) or state.get('Running') is not False or state.get('Pid')!=0:
            raise ValueError('原节点角色实际停止仍需核对')



def _initial_retirement(executor, request):
    initial=request.initial_projection
    if initial is None:
        return
    account_id,name,environment_id,_=executor._validate_preparation(initial)
    root=executor.data/'environments'/environment_id
    connection=executor.database()
    try:
        apply_migrations(connection)
        environment=connection.execute('SELECT * FROM account_environments WHERE environment_id=? OR account_id=?',
            (environment_id,account_id)).fetchone()
        account=connection.execute('SELECT * FROM accounts WHERE id=? OR name=?',(account_id,name)).fetchone()
        if environment is not None or account is not None:
            # 同操作重复准备由原正式行继续；部分身份存在时交给原完整Scope检查拒绝。
            return
        _deadline(request)
        marker={'protocol':1,'node_key':executor.node_key,'account_id':account_id,
            'environment_id':environment_id,'revision':initial.assignment_revision,'phase':'ready'}
        profile=executor.data/'profiles'/name
        runtime=root/'runtime'
        if (root.is_symlink() or profile.is_symlink()
                or profile.exists() and (not profile.is_dir() or any(profile.iterdir()))):
            raise ValueError('首次退休发现原Node资料，请先核对实际环境')
        if root.exists():
            entries=set(root.iterdir())
            if entries:
                if entries!={runtime} or runtime.is_symlink() or not runtime.is_dir():
                    raise ValueError('首次退休发现原Node资料，请先核对实际环境')
                children=set(runtime.iterdir())
                if children and (children!={runtime/'node-assignment.json'}
                        or strict_json(safe_read(runtime/'node-assignment.json',8192,private=True),8192)!=marker):
                    raise ValueError('首次退休发现原Node资料，请先核对实际环境')
        labels={'vibebench.product':'v3','vibebench.deployment':executor.deployment,
            'vibebench.cluster-node':executor.node_key,'vibebench.environment':environment_id}
        if executor.client.containers.list(all=True,filters={'label':[key+'='+value for key,value in labels.items()]}):
            raise ValueError('首次退休仍存在实际Node角色')
        if executor.client.containers.list(all=True,filters={'label':['vibebench.project-verifier=native',
                'vibebench.node-key='+executor.node_key,'vibebench.environment-id='+environment_id]}):
            raise ValueError('首次退休仍存在实际Node独立程序')
        # 与原准备入口一致，先保存归属再原子投影；投影失败只留下可核对的原标记。
        atomic_json(root/'runtime/node-assignment.json',marker)
        with connection:
            executor._project_row(connection,'accounts',{**initial.account,'enabled':0},update=False)
            executor._project_row(connection,'account_environments',{**initial.environment,'state':'stopped','isolation_version':2},update=False)
    finally:
        connection.close()


def prepare_owner(executor, request: OwnerPrepare) -> dict:
    """持久关闭原环境新工作后核对实际停止，同操作可恢复。

    :param executor: 原节点执行器。
    :param request: 原Scope与中央真实排他许可。
    :return: 不含凭据的原停止回执。
    """
    request=OwnerPrepare.model_validate(request.model_dump())
    scope=request.scope
    with executor._locked(environment_id=scope.environment_id):
        _initial_retirement(executor,request)
        account,row=_account(executor,scope)
        location=NodeLocation.model_validate(scope.model_dump(include=set(NodeLocation.model_fields)))
        previous=_read(executor,location)
        if previous is not None and previous['scope']==scope.model_dump():
            if previous['phase']=='published':
                return previous
        elif previous is not None and previous['phase']!='published':
            raise RuntimeBusy('原节点已有另一凭据交接待完成')
        elif account['cc2api_account_id']!=scope.previous_binding:
            raise ValueError('原节点交接的绑定已经变化')
        _deadline(request)
        runtime=executor._runtime(_GatewaySnapshot(0,{}))
        try:
            _idle(executor,runtime,row,resuming=previous is not None and previous['scope']==scope.model_dump() and previous['stopped'])
            receipt=OwnerReceipt(scope=scope)
            atomic_json(_path(executor,scope.environment_id),receipt.model_dump())
            runtime._stop_environment(row)
            _stopped(runtime,row)
            runtime._update(row,state='stopped')
            receipt.stopped=True
            atomic_json(_path(executor,scope.environment_id),receipt.model_dump())
            return receipt.model_dump()
        finally:
            executor._release_runtime(runtime)


def publish_owner(executor, request: OwnerPublish) -> dict:
    """原中央事务完成后使用原发布器切换Node绑定和刷新权。

    :param executor: 原Node执行器。
    :param request: 原已停止Scope和受信所有者快照。
    :return: 同操作发布回执；部分失败保持原意图。
    """
    request=OwnerPublish.model_validate(request.model_dump())
    scope=request.scope
    with executor._locked(environment_id=scope.environment_id):
        account,row=_account(executor,scope)
        location=NodeLocation.model_validate(scope.model_dump(include=set(NodeLocation.model_fields)))
        record=_read(executor,location)
        if record is None or record['scope']!=scope.model_dump() or not record['stopped']:
            raise ValueError('原节点交接实际停止尚未确认')
        if record['phase']=='published':
            return record
        _deadline(request)
        if account['cc2api_account_id'] not in (scope.previous_binding,scope.target_binding):
            raise ValueError('原节点交接发布绑定已经变化')
        runtime=executor._runtime(_GatewaySnapshot(0,{}))
        try:
            profile=executor.data/'profiles'/account['name']
            if request.material is not None:
                material=request.material
                for path in (profile/'.claude.json',runtime._root(row)/'home/.claude.json'):
                    top=strict_json(safe_read(path,1024*1024),1024*1024)
                    oauth=top.get('oauthAccount',{})
                    if (top.get('userID')!=material.device_id or not isinstance(oauth,dict)
                            or str(oauth.get('accountUuid') or '').strip().lower()!=material.account_uuid.strip().lower()
                            or str(oauth.get('organizationUuid') or '').strip().lower()!=str(material.organization_uuid or '').strip().lower()):
                        raise ValueError('原Node HOME与交接快照身份不一致')
                path=profile/'.credentials.json'
                credentials=strict_json(safe_read(path,1024*1024),1024*1024)
                oauth=credentials.get('claudeAiOauth')
                if not isinstance(oauth,dict):
                    raise ValueError('原Node管理凭据结构需要核对')
                oauth.update(accessToken=material.access_token,expiresAt=material.expires_at)
                if material.refresh_token is not None:
                    oauth['refreshToken']=material.refresh_token
                else:
                    oauth.pop('refreshToken',None)
                atomic_json(path,credentials)
            with runtime.owner_transition(account,scope.target_binding,handoff_credentials=scope.handoff_credentials,
                    lease_gateway=_PreparedGateway(request)):
                with runtime.lock:
                    connection=executor.database()
                    try:
                        with connection:
                            connection.execute('UPDATE accounts SET cc2api_account_id=?,enabled=CASE WHEN ? THEN 0 ELSE enabled END WHERE id=?',
                                (scope.target_binding,int(scope.retire),scope.account_id))
                    finally:
                        connection.close()
            record['phase']='published'
            atomic_json(_path(executor,scope.environment_id),record)
            return record
        finally:
            executor._release_runtime(runtime)
