"""节点草稿完整删除与环境外的持久清理回执。"""
from __future__ import annotations

import shutil

from cluster_draft_login_contract import DraftLoginDeleted, DraftLoginPreparation, DraftLoginPreparationDelete, DraftLoginPreparationScope, DraftLoginScope, DraftLoginStart
from database_migrations import apply_migrations
from login_drafts import LoginDraftStore
from native_kernel_upgrade import pending_upgrade
from runtime_files import atomic_json, private_directory
from system_update_contract import safe_read, strict_json


def _preparation_scope(actor, preparation, intent):
    work=preparation.work
    expected={'operation_id':work.id,'node_key':preparation.node_key,'environment_id':work.environment_id,
        'name':work.name,'draft_generation':work.draft_generation,'source':work.source,
        'preparation_sha256':work.preparation_sha256}
    if intent is not None:
        scope=DraftLoginPreparationScope.model_validate(intent.get('scope'))
        if any(getattr(scope,key)!=value for key,value in expected.items()):
            raise ValueError('原尚未启动准备的清理意图已经变化')
        return scope
    actor.grants._installation()
    directory=actor._operation_directory(work.environment_id,work.id)
    private=directory/'preparation.json'
    try:
        frozen=DraftLoginPreparation.model_validate(strict_json(safe_read(private,2*1024*1024,private=True),2*1024*1024))
    except FileNotFoundError:
        frozen=None
    if frozen is not None and (frozen.work!=work or frozen.node_key!=preparation.node_key or frozen.previous!=preparation.previous):
        raise ValueError('原准备清理的私有配置已经变化')
    grant=actor.grants.directory/work.environment_id/(work.id+'.json')
    if any(path.exists() or path.is_symlink() for path in (grant,directory/'execution.json')):
        raise ValueError('原准备已有输入许可或实际登录登记，请按实际Scope收口')
    connection=actor.executor.database()
    try:
        apply_migrations(connection)
        rows=connection.execute('SELECT * FROM account_environments WHERE environment_id=? OR name=?',
            (work.environment_id,work.name)).fetchall()
    finally:
        connection.close()
    if rows and (len(rows)!=1 or rows[0]['environment_id']!=work.environment_id or rows[0]['name']!=work.name
            or rows[0]['account_id'] is not None):
        raise ValueError('原准备清理的NULL环境归属已经变化')
    root=actor.executor.data/'environments'/work.environment_id
    profile=actor.executor.data/'profiles'/work.name
    if frozen is None and (rows or any(path.exists() or path.is_symlink() for path in (root,profile))):
        if preparation.previous is None:
            raise ValueError('尚未登记的准备不能接管遗留环境或profile')
        prior=actor._preparation(preparation.previous)
        if prior.work.preparation_sha256!=work.preparation_sha256 or prior.work.version!=work.version:
            raise ValueError('原已停止前代的配置或版本与本次准备不一致')
        actor._account(actor._request(preparation.previous,prior.work),stopping=True)
    generation=rows[0]['generation'] if rows else 0
    marker=root/'runtime/node-draft-login.json'
    if marker.exists() or marker.is_symlink():
        value=strict_json(safe_read(marker,8192,private=True),8192)
        observed=DraftLoginScope.model_validate(value.get('scope'))
        if value!={'protocol':1,'scope':observed.model_dump(),'phase':'ready'}:
            raise ValueError('原准备的Node范围标记需要核对')
        if observed==preparation.previous:
            old=actor.get(observed)
            if old['phase']!='closed' or old.get('commit') is not None or actor.grants.get(observed)['phase']!='closed':
                raise ValueError('原准备前代仍需实际停止或继续提交')
            if generation<observed.generation:
                raise ValueError('原准备资源代次不能回退')
        else:
            DraftLoginStart(scope=observed,work=work)
            if observed.generation!=generation:
                raise ValueError('原准备实际代次已经变化')
    return DraftLoginPreparationScope(**expected,generation=generation)


def delete_node_draft(actor, request: DraftLoginScope | DraftLoginPreparationDelete) -> dict:
    """核对原停止事实后清理专属角色、资料和NULL投影，回执保存在环境外。

    :param actor: 原节点草稿消费者。
    :param request: 原已停止Scope，或尚未授予输入许可的冻结工作及原摘要。
    :return: 可按同一范围重复读取的完整删除回执。
    """
    preparing=isinstance(request,DraftLoginPreparationDelete)
    request=(DraftLoginPreparationDelete if preparing else DraftLoginScope).model_validate(request.model_dump())
    environment_id=request.work.environment_id if preparing else request.environment_id
    operation_id=request.work.id if preparing else request.operation_id
    executor=actor.executor
    if request.node_key!=executor.node_key:
        raise ValueError('草稿删除属于其他节点')
    directory=executor.data/'node-draft-deletions'/environment_id
    path=directory/(operation_id+'.json')
    with executor._locked(environment_id=environment_id),executor._locked():
        try:
            intent=strict_json(safe_read(path,16384,private=True),16384)
        except FileNotFoundError:
            intent=None
        scope=_preparation_scope(actor,request,intent) if preparing else request
        if intent is not None:
            if (not isinstance(intent,dict) or set(intent)!={'protocol','scope','phase'}
                    or type(intent.get('protocol')) is not int or intent['protocol']!=1
                    or intent.get('scope')!=scope.model_dump() or intent.get('phase') not in ('deleting','deleted')):
                raise ValueError('原草稿删除意图范围已经变化')
            if intent['phase']=='deleted':
                return DraftLoginDeleted.model_validate(intent).model_dump()
        elif not preparing:
            value=actor.get(scope)
            try:
                proof=actor.grants.get(scope)
            except FileNotFoundError:
                proof=None
            if value['phase']!='closed' or value.get('commit') is not None or proof is not None and proof['phase']=='active':
                raise ValueError('完整删除必须先确认原登录实际停止且尚未提交')
            preparation=actor._preparation(scope)
            actor._account(actor._request(scope,preparation.work),stopping=True)
            if proof is not None and proof['phase']=='prepared':
                actor.grants.close(scope,'node_not_started')
        runtime=actor._recovery_runtime(scope)
        drafts=LoginDraftStore(runtime,executor.database,actor.lock)
        root=executor.data/'environments'/scope.environment_id
        profile=executor.data/'profiles'/scope.name
        operations=executor.data/'node-draft-logins'/scope.environment_id
        with runtime.environment_lock(scope.environment_id):
            connection=executor.database()
            try:
                row=connection.execute('SELECT * FROM account_environments WHERE environment_id=?',(scope.environment_id,)).fetchone()
                if row is not None and (row['account_id'] is not None or row['name']!=scope.name or row['generation']!=scope.generation):
                    raise ValueError('原NULL草稿环境已经变化')
                if connection.execute('SELECT 1 FROM accounts WHERE name=? OR profile_path=? LIMIT 1',
                        (scope.name,'profiles/'+scope.name)).fetchone():
                    raise ValueError('正式或软删除账号仍引用原草稿资料')
                if connection.execute('SELECT 1 FROM account_environments WHERE name=? AND environment_id<>?',
                        (scope.name,scope.environment_id)).fetchone():
                    raise ValueError('其他Node环境仍引用原名称，资料清理需要核对')
                prefix=str(executor.data/'flows'/scope.name)+'/'
                if connection.execute('SELECT 1 FROM runs WHERE environment_id=? OR substr(flows_dir,1,?)=? LIMIT 1',
                        (scope.environment_id,len(prefix),prefix)).fetchone():
                    raise ValueError('历史执行仍引用原节点草稿')
            finally:
                connection.close()
            for target,parent in ((root,executor.data/'environments'),(profile,executor.data/'profiles'),
                    (operations,executor.data/'node-draft-logins')):
                drafts._safe_tree(target,parent)
            if row is None and intent is None and not preparing:
                raise ValueError('原草稿环境缺失且没有完整删除意图')
            if row is not None:
                row=dict(row)
                if (runtime.environment_jobs(scope.environment_id) or runtime._execution_records(row)
                        or any((root/'runtime'/name).exists() or (root/'runtime'/name).is_symlink() for name in
                            ('execution.json','login-commit.json','credential-handoff.json','node-fence.json','node-assignment.json'))
                        or runtime.reviews.serial_state(row) or pending_upgrade(root) or runtime._running_sender_active(row)):
                    raise ValueError('原草稿仍有实际工作或维护，完整清理需要先核对')
                runtime.reviews.check_orphans(row)
                if intent is None:
                    for folder in (directory.parent,directory):
                        private_directory(folder)
                    atomic_json(path,{'protocol':1,'scope':scope.model_dump(),'phase':'deleting'})
                runtime._stop_environment(row,remove=True)
                expected=runtime._labels(row)
                expected.pop('vibebench.role')
                remaining=[container for container in runtime.client.containers.list(all=True,filters={
                    'label':[key+'='+value for key,value in expected.items()]})
                    if container.labels.get('vibebench.cluster-node')==executor.node_key]
                if remaining:
                    raise ValueError('原草稿专属角色仍待确认移除')
            elif intent is None:
                for folder in (directory.parent,directory):
                    private_directory(folder)
                atomic_json(path,{'protocol':1,'scope':scope.model_dump(),'phase':'deleting'})
            # Node准备入口先检查环境外意图；半清理期间不会重新认领同一环境。
            for target in (root,profile,operations):
                if target.exists():
                    shutil.rmtree(target)
            connection=executor.database()
            try:
                with connection:
                    cursor=connection.execute('DELETE FROM account_environments WHERE environment_id=? AND name=? '
                        'AND account_id IS NULL AND generation=?',(scope.environment_id,scope.name,scope.generation))
                    if cursor.rowcount==0 and connection.execute('SELECT 1 FROM account_environments WHERE environment_id=?',
                            (scope.environment_id,)).fetchone():
                        raise ValueError('原草稿已被认领，保留删除意图等待核对')
            finally:
                connection.close()
            receipt=DraftLoginDeleted(scope=scope)
            atomic_json(path,receipt.model_dump())
            return receipt.model_dump()
