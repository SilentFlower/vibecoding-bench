"""NULL账号草稿的Node资源准备、原登录交互与实际停止。"""
from __future__ import annotations

import os
import hashlib
import time
from pathlib import Path
from types import SimpleNamespace

from cluster_draft_login_contract import DraftLoginCodeRead, DraftLoginFiles, DraftLoginGrant, DraftLoginInputQuery, DraftLoginPreparation, DraftLoginPreparationDelete, DraftLoginScope, DraftLoginStart, DraftLoginSummary
from cluster_execution import _GatewaySnapshot
from cluster_draft_login_activation import activate_draft_login
from cluster_draft_login_deletion import delete_node_draft
from cluster_login import NodeAccountLogins
from database_migrations import apply_migrations
from runtime_files import atomic_json, private_directory
from system_update_contract import safe_read, strict_json


class NodeDraftLogins(NodeAccountLogins):
    """复用原登录与单次输入核心，NULL身份使用独立文件、范围与有限证明。

    :param executor: 原受信Node执行器。
    :param host: 原持久运行时。
    :param grants: 本节点草稿专用证明。
    """

    def __init__(self, executor, host, grants) -> None:
        """安装唯一草稿作业授权回调。

        :param executor: 原节点。
        :param host: 原持久Host。
        :param grants: 本节点草稿证明。
        :return: None。
        """
        super().__init__(executor,host,grants)
        mirror=host.gateway.lease_mirror
        if (mirror is None or grants.data!=executor.data or grants.node_key!=executor.node_key
                or grants.database!=executor.database or grants.deployment!=executor.deployment):
            raise ValueError('原节点草稿证明或运行时安装范围不一致')
        with mirror.lock:
            if mirror.draft_authorizer is not None:
                raise ValueError('原节点草稿授权消费者已经安装')
            mirror.draft_authorizer=self.authorize_job

    def _request(self, scope, work):
        return DraftLoginStart.model_validate({'scope':scope,'work':work})

    def _code_read(self, scope, request_id):
        return DraftLoginCodeRead(scope=scope,request_id=request_id)

    def _input_query(self, scope, operation_id):
        return DraftLoginInputQuery(scope=scope,operation_id=operation_id)

    def _recovery_runtime(self, scope):
        return self.executor._runtime(_GatewaySnapshot(0,{}))

    def _session_profile(self, request):
        return self.executor.data/'environments'/request.scope.environment_id/'home'/Path(request.work.home).relative_to('/home/node')/'.claude'

    def _operation_directory(self, environment_id: str, operation_id: str, *, create: bool=False) -> Path:
        root=self.executor.data/'node-draft-logins'
        environment,directory=root/environment_id,root/environment_id/operation_id
        if create:
            for path in (root,environment,directory):
                private_directory(path)
        return directory

    def _directory(self, scope: DraftLoginScope, *, create: bool=False) -> Path:
        scope=DraftLoginScope.model_validate(scope.model_dump())
        if scope.node_key!=self.executor.node_key:
            raise ValueError('原草稿操作属于其他Node')
        return self._operation_directory(scope.environment_id,scope.operation_id,create=create)

    def _preparation(self, scope: DraftLoginScope) -> DraftLoginPreparation:
        value=DraftLoginPreparation.model_validate(strict_json(safe_read(self._directory(scope)/'preparation.json',2*1024*1024,private=True),2*1024*1024))
        DraftLoginStart(scope=scope,work=value.work)
        if value.node_key!=scope.node_key:
            raise ValueError('原草稿准备来源已经变化')
        return value

    def _account(self, request: DraftLoginStart, *, stopping: bool=False) -> tuple[dict,dict]:
        preparation=self._preparation(request.scope)
        if preparation.work!=request.work:
            raise ValueError('原草稿登录工作已经变化')
        if stopping:
            self.grants.check_stopping_scope(request.scope)
        else:
            self.grants.check_scope(request.scope)
        connection=self.executor.database()
        try:
            row=dict(connection.execute('SELECT * FROM account_environments WHERE environment_id=?',(request.scope.environment_id,)).fetchone())
        finally:
            connection.close()
        # 原AccountRuntime已支持NULL草稿；只提供原私有配置，不创建正式账号占位。
        return {**preparation.settings.model_dump(),'id':None},row

    def _authorize(self, request: DraftLoginStart, *, prepared: bool=False) -> None:
        recovery=self._directory(request.scope)/'recovery-only.json'
        if recovery.exists() or recovery.is_symlink():
            raise ValueError('原草稿准备已进入停止恢复，新的授权输入已关闭')
        if prepared:
            value=self.grants.get(request.scope)
            if value['phase']!='prepared':
                raise ValueError('原草稿证明已被认领或关闭')
            grant=DraftLoginGrant.model_validate(value['grant'])
        else:
            grant=self.grants.authorize(request.scope)
        if time.time()>=request.work.expires_at or grant.not_after>request.work.expires_at:
            raise ValueError('原草稿登录截止已经失效')

    def _refresh_parent(self, request: DraftLoginStart) -> None:
        """NULL草稿没有正式账号的旧RT维护父来源。"""

    def _release_mirror(self, scope: DraftLoginScope) -> None:
        if self.grants.get(scope)['phase']!='closed':
            raise ValueError('原草稿输入许可仍需关闭')

    def _restore_login_execution(self, runtime, row, account, request, proof):
        return runtime.restore_execution(row,account,request.scope.source,None,shared_cli=False,account_login=True,
            draft_login_recovery=request.work.mode=='recover')

    def _check_unstarted_scope(self, scope):
        self.grants.check_stopping_scope(scope)
        runtime=self._recovery_runtime(scope)
        row=runtime._row(scope.name)
        root=self.executor.data/'environments'/scope.environment_id
        if (runtime.environment_jobs(scope.environment_id) or runtime._execution_records(row)
                or (root/'runtime/execution.json').exists() or (root/'runtime/execution.json').is_symlink()
                or runtime._running_sender_active(row)):
            raise ValueError('原草稿准备仍有未登记实际工作，停止结果需要核对')

    def authorize_job(self, job: dict) -> None:
        """在原CLI实际输入前核对草稿作业来源、NULL身份和有限许可。

        :param job: 原AccountRuntime认领的真实作业。
        :return: None；任一范围变化保持关闭。
        """
        row=job['row']
        marker=strict_json(safe_read(self.executor.data/'environments'/row['environment_id']/'runtime/node-draft-login.json',8192,private=True),8192)
        scope=DraftLoginScope.model_validate(marker.get('scope'))
        preparation=self._preparation(scope)
        if (job['account'].get('id') is not None or job['account'].get('cc2api_account_id') is not None
                or row.get('account_id') is not None or job['account'].get('name')!=scope.name
                or row.get('generation')!=scope.generation or job['source']!=scope.source
                or job.get('exclusive') is not True or job.get('shared_cli') is True):
            raise ValueError('原NULL草稿实际作业与有限范围不一致')
        self._authorize(DraftLoginStart(scope=scope,work=preparation.work))

    def prepare(self, preparation: DraftLoginPreparation, *, recovering: bool=False) -> dict:
        """先持久冻结私有准备，再创建NULL资源并返回真实代次；此阶段不启动授权。

        :param preparation: 原节点、操作、私有配置和可选停止来源。
        :param recovering: 只允许完成原准备并立即停止，永久关闭本操作的新授权输入。
        :return: 独立草稿范围，供中央随后发放有限证明。
        """
        preparation=DraftLoginPreparation.model_validate(preparation.model_dump())
        work=preparation.work
        if preparation.node_key!=self.executor.node_key or not recovering and time.time()>=work.expires_at:
            raise ValueError('草稿准备的原节点或截止需要核对')
        with self.executor._locked(environment_id=work.environment_id),self.executor._locked():
            deletion=self.executor.data/'node-draft-deletions'/work.environment_id
            if deletion.is_symlink() or any(deletion.glob('*.json')):
                raise ValueError('原草稿已进入完整删除，不能重新准备')
            directory=self._operation_directory(work.environment_id,work.id)
            if recovering:
                directory=self._operation_directory(work.environment_id,work.id,create=True)
                recovery=directory/'recovery-only.json'
                expected={'protocol':1,'work':work.model_dump()}
                if recovery.exists() or recovery.is_symlink():
                    if strict_json(safe_read(recovery,16384,private=True),16384)!=expected:
                        raise ValueError('原草稿停止恢复工作已经变化')
                else:
                    # Scope尚未返回时，先永久关闭该操作的启动/输入，再核对可能已经创建的资源。
                    atomic_json(recovery,expected)
            path=directory/'preparation.json'
            exists=path.exists() or path.is_symlink()
            if exists:
                previous=DraftLoginPreparation.model_validate(strict_json(safe_read(path,2*1024*1024,private=True),2*1024*1024))
                if previous!=preparation:
                    raise ValueError('原草稿准备配置已经冻结')
            root=self.executor.data/'environments'/work.environment_id
            prepared_path=directory/'prepared.json'
            if prepared_path.exists() or prepared_path.is_symlink():
                marker=strict_json(safe_read(prepared_path,8192,private=True),8192)
                scope=DraftLoginScope.model_validate(marker.get('scope'))
                if marker!={'protocol':1,'scope':scope.model_dump(),'phase':'ready'}:
                    raise ValueError('原草稿准备回执需要核对')
                DraftLoginStart(scope=scope,work=work)
                if recovering:
                    self.grants.check_stopping_scope(scope)
                else:
                    self.grants.check_scope(scope)
                self._recovery_runtime(scope)
                return marker
            if any(item.exists() or item.is_symlink() for item in (root/'runtime/node-assignment.json',root/'runtime/node-fence.json')):
                raise ValueError('原草稿环境存在正式归属或迁移隔离')
            previous=preparation.previous
            if previous is not None:
                old=self.get(previous)
                cancelled=self._cancelled(previous)
                try:
                    proof=self.grants.get(previous)
                except FileNotFoundError:
                    proof=None
                if (old['phase']!='closed' or old.get('commit') is not None
                        or (proof is None or proof['phase']!='closed') and cancelled is None):
                    raise ValueError('原草稿登录尚未实际停止或已经进入提交')
                if proof is not None and proof['phase']=='prepared':
                    self.grants.close(previous,'node_not_started')
                old_preparation=self._preparation(previous)
                if old_preparation.work.preparation_sha256!=work.preparation_sha256 or old_preparation.work.version!=work.version:
                    raise ValueError('原草稿设备配置、代理或版本必须继续保留')
            connection=self.executor.database()
            try:
                apply_migrations(connection)
                if connection.execute('SELECT 1 FROM accounts WHERE name=? OR profile_path=? LIMIT 1',(work.name,'profiles/'+work.name)).fetchone():
                    raise ValueError('正式或软删除账号仍引用Node草稿')
                environment=connection.execute('SELECT * FROM account_environments WHERE environment_id=? OR name=?',(work.environment_id,work.name)).fetchall()
                if environment and (len(environment)!=1 or environment[0]['environment_id']!=work.environment_id
                        or environment[0]['name']!=work.name or environment[0]['account_id'] is not None
                        or not exists and previous is None):
                    raise ValueError('原Node草稿环境归属需要核对')
                if not environment and (previous is not None or root.exists() and any(root.iterdir())):
                    raise ValueError('原草稿持久资料尚未核对归属')
                profile=self.executor.data/'profiles'/work.name
                if not exists and previous is None and (profile.exists() or profile.is_symlink()):
                    raise ValueError('首次Node草稿不能接管遗留profile资料')
                if not exists:
                    self._operation_directory(work.environment_id,work.id,create=True)
                    atomic_json(path,preparation.model_dump())
                # 环境及全节点准备锁已持有；私有文件先持久化，短SQL事务只认领原NULL行。
                with connection:
                    connection.execute('BEGIN IMMEDIATE')
                    if not environment:
                        connection.execute('INSERT INTO account_environments(environment_id,name,fingerprint_json) VALUES(?,?,?)',
                            (work.environment_id,work.name,preparation.fingerprint_json))
            finally:
                connection.close()
            runtime=self.executor._runtime(_GatewaySnapshot(0,{}))
            row=runtime._row(work.name)
            if (runtime.environment_jobs(work.environment_id) or runtime._execution_records(row)
                    or (root/'runtime/execution.json').exists() or (root/'runtime/login-commit.json').exists()):
                raise ValueError('原草稿仍有实际工作或未确认提交')
            if previous is None:
                profile=self.executor.data/'profiles'/work.name
                for filename,content in preparation.profile_files.items():
                    target=profile/filename
                    document=strict_json(content.encode(),1024*1024)
                    if target.exists() or target.is_symlink():
                        if strict_json(safe_read(target,1024*1024),1024*1024)!=document:
                            raise ValueError('Node草稿初始profile已经变化')
                    else:
                        atomic_json(target,document)
                for relative,filename in (('.claude.json','.claude.json'),('.claude/settings.json','settings.json')):
                    target=root/'home'/relative
                    if not target.exists() and not target.is_symlink():
                        atomic_json(target,strict_json(preparation.profile_files.get(filename,'{}').encode(),1024*1024))
                        os.chown(target,1000,1000,follow_symlinks=False)
                os.chown(root/'home/.claude',1000,1000,follow_symlinks=False)
            runtime.ensure(preparation.settings.model_dump(),prepare_sender=False,ownership_source=work.source)
            row=runtime._row(work.name)
            scope=DraftLoginScope(operation_id=work.id,node_key=preparation.node_key,environment_id=work.environment_id,
                name=work.name,draft_generation=work.draft_generation,generation=row['generation'],source=work.source)
            marker={'protocol':1,'scope':scope.model_dump(),'phase':'ready'}
            atomic_json(root/'runtime/node-draft-login.json',marker)
            atomic_json(prepared_path,marker)
            return marker

    def recover_preparation(self, preparation: DraftLoginPreparation) -> dict:
        """沿原冻结准备核对实际Scope并立即停止，过期操作只获得收口能力。

        :param preparation: 中央持久冻结的原准备。
        :return: 原实际Scope的严格停止回执。
        """
        prepared=self.prepare(preparation,recovering=True)
        return self.stop(DraftLoginScope.model_validate(prepared['scope']))

    def _run(self, request: DraftLoginStart) -> None:
        scope,work=request.scope,request.work
        try:
            with self.executor._locked(environment_id=scope.environment_id):
                value=self._record(scope)
                if self.closing or value['phase']=='closed':
                    return
                account,_=self._account(request)
                self._authorize(request)
                value['start_intent']=True
                self._save(scope,value)
                runtime=self.host.runtime
                if work.mode=='recover':
                    row,container=runtime.recover_login(work.sid,account,work.version,work.home)
                    home,profile=work.home,self._session_profile(request)
                else:
                    row,container,profile,home=runtime.begin_login(work.sid,account,work.version,True)
                job=runtime.job_for_container(runtime.execution_token(container.id,scope.source))
                job['execution_role']='draft-login-recovery' if work.mode=='recover' else 'account-login'
                runtime._save_execution(job)
                if row['generation']!=scope.generation or home!=work.home:
                    raise ValueError('原草稿登录的实际代次或HOME已经变化')
                phase='ready_to_submit' if work.mode=='recover' else 'authorizing'
                session=SimpleNamespace(sid=work.sid,name=work.name,worker_id=container.id,profile_dir=profile,
                    home=home,version=work.version,force_reauth=True,phase=phase,created_at=time.time())
                with self.lock:
                    self.sessions[scope.operation_id]=session
                value.update(phase='ready',result={'token':job['token'],'source':scope.source})
                self._save(scope,value)
        except Exception as error:
            with self.executor._locked(environment_id=scope.environment_id):
                value=self._record(scope)
                if value['phase']!='closed':
                    value.update(phase='reconcile',error_type=type(error).__name__)
                    self._save(scope,value)
        finally:
            with self.lock:
                self.workers.pop(scope.operation_id,None)
            self.slots.release()

    def _cleanup_materials(self, scope: DraftLoginScope, sid: str) -> None:
        work=self._request(scope,self._record(scope)['work']).work
        # 恢复会话可能沿用旧SID暂存；只在同一冻结授权已接受后清理其原专属HOME。
        original=work.home.rsplit('/',1)[1] if work.home.startswith('/home/node/.v3-login/') else sid
        super()._cleanup_materials(scope,original)

    def files(self, scope: DraftLoginScope) -> dict:
        """读取已冻结原文件的有限索引，完整配置保持在私有数据通道。

        :param scope: 原草稿范围。
        :return: 只包含范围、固定文件及字节摘要的索引。
        """
        with self.executor._locked(environment_id=scope.environment_id):
            value=self._record(scope)
            commit=value.get('commit')
            if commit is None or commit['stage']!='saved':
                raise ValueError('原草稿完整文件尚未冻结或已确认清理')
            self._account(self._request(scope,value['work']),stopping=True)
            self._authorization_files(scope,commit)
            files={}
            for name in commit['files']:
                raw=safe_read(self._directory(scope)/'authorization'/name,1024*1024,private=True)
                files[name]={'sha256':hashlib.sha256(raw).hexdigest(),'bytes':len(raw)}
            return DraftLoginFiles(scope=scope,authorization_sha256=commit['authorization_sha256'],files=files).model_dump()

    def discard(self, scope: DraftLoginScope) -> dict:
        """草稿取消实际停止原登录并保留产物，完整删除另走专属生命周期。

        :param scope: 原草稿范围。
        :return: 原实际停止回执。
        """
        return self.stop(scope)

    def activate(self, request) -> dict:
        """中央首次落库后接续原真实账号激活。:param request: 原激活请求。:return: 原Node激活回执。"""
        return activate_draft_login(self,request)

    def delete(self, scope: DraftLoginScope) -> dict:
        """完整清理原NULL草稿。:param scope: 原已停止范围。:return: 环境外持久删除回执。"""
        return delete_node_draft(self,scope)

    def delete_preparation(self, preparation: DraftLoginPreparationDelete) -> dict:
        """只清理原尚未授予输入许可的准备。:param preparation: 原冻结工作及准备摘要。:return: 独立只清理身份的持久回执。"""
        return delete_node_draft(self,preparation)

    def summary(self, scope: DraftLoginScope) -> dict:
        """只读原草稿文件与既有运行时状态，查询不创建运行时或唤醒角色。

        :param scope: 原草稿范围。
        :return: 无凭据、代理和授权链接的草稿摘要。
        """
        with self.executor._locked(read_only=True,environment_id=scope.environment_id):
            preparation=self._preparation(scope)
            _,row=self._account(DraftLoginStart(scope=scope,work=preparation.work),stopping=True)
            path=self._session_profile(DraftLoginStart(scope=scope,work=preparation.work))/'.credentials.json'
            try:
                safe_read(path,1024*1024)
                present=True
            except FileNotFoundError:
                present=False
            status='missing' if not row.get('container_id') else 'unknown'
            if row.get('container_id') and self.host.runtime is not None:
                observed=self.host.runtime.role_status(row).get('cli')
                if observed in ('running','exited','dead','created','restarting','paused'):
                    status=observed
            return DraftLoginSummary(scope=scope,credentials_present=present,container_status=status,state=row['state']).model_dump()
