"""原NULL草稿实际停止后投影真实账号，保留HOME并移除草稿角色。"""
from __future__ import annotations

import hashlib

from cluster_draft_login_contract import DraftLoginActivated, DraftLoginActivation
from cluster_login_contract import login_authorization_sha256
from native_kernel_upgrade import pending_upgrade
from runtime_files import atomic_json
from system_update_contract import safe_read, strict_json


def activate_draft_login(actor, request: DraftLoginActivation) -> dict:
    """在原授权收口后发布真实账号，响应未知时接续同一持久激活意图。

    :param actor: 原NULL草稿具体消费者。
    :param request: 中央同一草稿首次事务产生的真实ID及原授权摘要。
    :return: 无令牌激活回执，原HOME、设备和CLI缓存保留。
    """
    request=DraftLoginActivation.model_validate(request.model_dump())
    scope=request.scope
    executor=actor.executor
    with executor._locked(environment_id=scope.environment_id):
        value=actor._record(scope)
        commit=value.get('commit')
        if (value['phase']!='closed' or commit is None or commit['stage']!='accepted' or commit['cleanup_pending']
                or commit['authorization_sha256']!=request.authorization_sha256 or actor.grants.get(scope)['phase']!='closed'):
            raise ValueError('真实账号激活必须先确认原Node授权、实际停止和暂存清理')
        preparation=actor._preparation(scope)
        path=actor._directory(scope)/'activation.json'
        try:
            intent=strict_json(safe_read(path,16384,private=True),16384)
        except FileNotFoundError:
            intent=None
        if intent is not None:
            if (not isinstance(intent,dict) or set(intent)-{'request','phase','receipt'}
                    or DraftLoginActivation.model_validate(intent.get('request'))!=request
                    or intent.get('phase') not in ('preparing','activated')):
                raise ValueError('原草稿真实ID激活意图已经变化')
            if intent['phase']=='activated':
                receipt=DraftLoginActivated.model_validate(intent.get('receipt'))
                if receipt.request!=request or receipt.refresh_sha256!=commit['refresh_sha256']:
                    raise ValueError('原草稿真实ID激活回执需要核对')
                return receipt.model_dump()
        if intent is None:
            actor._account(actor._request(scope,value['work']),stopping=True)
        root=executor.data/'environments'/scope.environment_id
        assignment={'protocol':1,'node_key':scope.node_key,'account_id':request.account_id,
            'environment_id':scope.environment_id,'revision':request.assignment_revision,'phase':'ready'}
        assignment_path=root/'runtime/node-assignment.json'
        if assignment_path.exists() or assignment_path.is_symlink():
            if strict_json(safe_read(assignment_path,8192,private=True),8192)!=assignment:
                raise ValueError('原草稿正式分配投影已经变化')
        connection=executor.database()
        try:
            stored=connection.execute('SELECT * FROM account_environments WHERE environment_id=?',(scope.environment_id,)).fetchone()
            if (stored is None or stored['name']!=scope.name or stored['generation']!=scope.generation
                    or stored['account_id'] not in (None,request.account_id) or stored['account_id'] is not None and intent is None):
                raise ValueError('原草稿真实ID投影的环境范围已经变化')
            row=dict(stored)
            accounts=connection.execute('SELECT * FROM accounts WHERE id=? OR name=? OR profile_path=?',
                (request.account_id,scope.name,'profiles/'+scope.name)).fetchall()
            if accounts and (intent is None or len(accounts)!=1 or accounts[0]['id']!=request.account_id
                    or accounts[0]['name']!=scope.name or accounts[0]['profile_path']!='profiles/'+scope.name
                    or accounts[0]['enabled']!=0 or accounts[0]['cc2api_account_id'] is not None or accounts[0]['deleted_at'] is not None):
                raise ValueError('原草稿真实ID与Node已有账号冲突')
        finally:
            connection.close()
        documents={name:strict_json(safe_read(root/'home'/name,1024*1024),1024*1024) for name in commit['files']}
        if (login_authorization_sha256(documents)!=request.authorization_sha256
                or hashlib.sha256(documents['.claude/.credentials.json']['claudeAiOauth']['refreshToken'].encode()).hexdigest()!=commit['refresh_sha256']):
            raise ValueError('原草稿激活前的当前HOME授权已经变化')
        runtime=actor._recovery_runtime(scope)
        with runtime.environment_lock(scope.environment_id):
            if (runtime.environment_jobs(scope.environment_id) or runtime._execution_records(row)
                    or any((root/'runtime'/name).exists() or (root/'runtime'/name).is_symlink()
                        for name in ('execution.json','login-commit.json','credential-handoff.json','node-fence.json'))
                    or runtime.reviews.serial_state(row) or pending_upgrade(root) or runtime._running_sender_active(row)):
                raise ValueError('原草稿仍有实际工作或维护，真实ID激活需要先核对')
            runtime.reviews.check_orphans(row)
            if intent is None:
                intent={'request':request.model_dump(),'phase':'preparing'}
                atomic_json(path,intent)
            # NULL草稿角色缺正式额度挂载。先按原实际归属移除角色，后续正式准备重新创建正确挂载。
            runtime._stop_environment(row,remove=True)
            expected=runtime._labels(row)
            expected.pop('vibebench.role')
            remaining=[container for container in runtime.client.containers.list(all=True,filters={
                'label':[key+'='+value for key,value in expected.items()]})
                if container.labels.get('vibebench.cluster-node')==executor.node_key]
            if remaining:
                raise ValueError('原草稿角色实际移除结果仍需核对')
            connection=executor.database()
            try:
                with connection:
                    connection.execute('BEGIN IMMEDIATE')
                    current=connection.execute('SELECT * FROM account_environments WHERE environment_id=?',(scope.environment_id,)).fetchone()
                    if (current is None or current['account_id'] not in (None,request.account_id) or current['generation']!=scope.generation
                            or any(current[key] for key in ('container_id','network_container_id','sender_container_id'))):
                        raise ValueError('原草稿角色或真实ID投影已经变化')
                    account={**preparation.settings.model_dump(),'id':request.account_id,'profile_path':'profiles/'+scope.name,
                        'cc2api_account_id':None,'enabled':0}
                    if not accounts:
                        executor._project_row(connection,'accounts',account,update=False)
                    connection.execute("UPDATE account_environments SET account_id=?,state='stopped' WHERE environment_id=?",
                        (request.account_id,scope.environment_id))
            finally:
                connection.close()
            if assignment_path.exists() or assignment_path.is_symlink():
                if strict_json(safe_read(assignment_path,8192,private=True),8192)!=assignment:
                    raise ValueError('原草稿正式分配投影已经变化')
            atomic_json(assignment_path,assignment)
            atomic_json(root/'runtime/node-draft-login.json',{'protocol':1,'scope':scope.model_dump(),'phase':'activated'})
            receipt=DraftLoginActivated(request=request,refresh_sha256=commit['refresh_sha256'])
            atomic_json(path,{'request':request.model_dump(),'phase':'activated','receipt':receipt.model_dump()})
            return receipt.model_dump()
