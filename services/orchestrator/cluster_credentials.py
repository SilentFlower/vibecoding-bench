"""独立节点当前HOME的具体凭据维护，未知提交只读取原操作。"""
from __future__ import annotations

import hashlib
import json
import os
import shlex
import threading
import time
from contextlib import contextmanager
from pathlib import Path

from docker.errors import NotFound

from account_runtime import AccountRuntime, read_cli_identity_at
from cli_telemetry_policy import cli_telemetry_environment
from cluster_credential_account import read_node_credential_account
from cluster_credentials_contract import CredentialIdentityImport, CredentialMaterial, CredentialRefreshStart, CredentialStatusRead, CredentialUsageStart, credential_start
from cluster_execution import NodeInspection, _GatewaySnapshot
from cluster_execution_grants import ExecutionScope
from cluster_runs import RunWork
from oauth_refresh_probe import OAUTH_REFRESH_SCRIPT, execute_oauth_refresh_probe
from oauth_status import oauth_document_status, oauth_expiry_status
from quota_probe import QUOTA_PROBE_SCRIPT, node_usage_result
from runtime_files import atomic_json, private_directory
from system_update_contract import safe_read, strict_json


class NodeCredentials:
    """原节点唯一运行时中的具体无模型凭据维护与额度操作。

    :param executor: 原节点执行器。
    :param host: 原节点唯一AccountRuntime。
    :param grants: 原有限证明存储。
    :param runs: 原具体Run记录，用于核对已释放私有评审。
    """

    def __init__(self, executor, host, grants, runs) -> None:
        """登记原执行边界并限制同时等待响应的线程。

        :param executor: 原节点执行器。
        :param host: 原唯一运行时。
        :param grants: 原节点证明。
        :param runs: 原具体Run执行器。
        :return: None。
        """
        self.executor,self.host,self.grants,self.runs=executor,host,grants,runs
        self.lock,self.slots=threading.RLock(),threading.BoundedSemaphore(4)
        self.workers,self.closing={},False

    def material(self, request: CredentialStatusRead) -> dict:
        """仅供受信所有权流程读取当前Node完整材料。

        :param request: 原完整归属、稳定身份和当前环境代次。
        :return: 受信私有响应；令牌不写入状态缓存或执行回执。
        """
        with self.executor._locked(environment_id=request.environment_id):
            read_node_credential_account(self.executor,request,require_home=True,allow_inactive=True)
            path=self.executor.data/'environments'/request.environment_id/'home/.claude/.credentials.json'
            document=strict_json(safe_read(path,1024*1024),1024*1024)
            oauth=AccountRuntime._local_oauth(document)
            material=CredentialMaterial(access_token=oauth['accessToken'],refresh_token=oauth['refreshToken'],
                expires_at=int(oauth['expiresAt']))
            return {'protocol':1,**request.model_dump(),'material':material.model_dump()}

    def identity(self, request: CredentialStatusRead) -> dict:
        """只读原Node官方配置/实际请求观察中的CLI身份。

        :param request: 原归属、代次、稳定身份及冻结CLI版本。
        :return: 无凭据的设备、来源和环境身份；读取不会创建运行时。
        """
        with self.executor._locked(environment_id=request.environment_id):
            account,_=read_node_credential_account(self.executor,request,require_home=True,allow_inactive=True)
            root=self.executor.data/'environments'/request.environment_id
            identity=read_cli_identity_at(root,self.executor.data/'profiles'/account['name'],request.version)
            return {'protocol':1,**request.model_dump(),'identity':{**identity,'environment_id':request.environment_id}}

    def status(self, request: CredentialStatusRead) -> dict:
        """只读原归属当前HOME的到期元数据。

        :param request: 原环境、代次及稳定身份。
        :return: 受限观察回执；不创建环境或发起上游请求。
        """
        with self.executor._locked(environment_id=request.environment_id):
            row=self.executor._inspection_row(NodeInspection.model_validate(request.model_dump(
                exclude={'generation','account_identity'})))
            connection=self.executor.database()
            try:
                account=connection.execute('SELECT * FROM accounts WHERE id=?',(request.account_id,)).fetchone()
            finally:
                connection.close()
            if row['generation']!=request.generation or account is None or account['cc2api_account_id'] is not None:
                raise ValueError('原独立凭据观察的账号或代次已变化')
            home=self.executor.data/'environments'/request.environment_id/'home'
            observed=time.time()
            try:
                top=strict_json(safe_read(home/'.claude.json',1024*1024),1024*1024)
            except FileNotFoundError:
                status=oauth_expiry_status(None,token_state='unknown')
            else:
                oauth=top.get('oauthAccount')
                if not isinstance(oauth,dict) or not isinstance(oauth.get('accountUuid'),str) or not oauth['accountUuid']:
                    raise ValueError('节点当前HOME的账号身份需要核对')
                identity=json.dumps({'account_id':request.account_id,'binding':None,
                    'uuid':oauth['accountUuid'],'org':oauth.get('organizationUuid')},sort_keys=True)
                if identity!=request.account_identity:
                    raise ValueError('节点当前HOME的稳定账号身份已变化')
                try:
                    document=strict_json(safe_read(home/'.claude/.credentials.json',1024*1024),1024*1024)
                except FileNotFoundError:
                    status=oauth_expiry_status(None,token_state='missing')
                except (OSError,ValueError):
                    status=oauth_expiry_status(None,token_state='invalid')
                else:
                    status=oauth_document_status(document,now=observed)
            return {'protocol':1,**request.model_dump(),'observed_at':observed,'status':status}

    def identity_import(self, request: CredentialStatusRead) -> dict:
        """在原已准备CLI上读取Gateway创建所需的实测环境。

        :param request: 原正式独立账号、实际代次和版本。
        :return: 完整非秘密导入载荷；执行不发起上游认证或模型请求。
        """
        with self.executor._locked(environment_id=request.environment_id):
            account,row=read_node_credential_account(self.executor,request,require_home=True)
            runtime=self.executor._runtime(_GatewaySnapshot(0,{},bench_account_id=account['id']))
            try:
                runtime._check_node_fence(row)
                self.executor._check_execution_records(runtime,row)
                if runtime.environment_jobs(request.environment_id) or runtime.reviews.serial_state(row):
                    raise ValueError('原Node仍有活动工作，设备导入等待空闲')
                container=runtime._container(row)
                container.reload()
                if container.status!='running':
                    raise ValueError('原Node CLI需要先完成准备')
                identity=CredentialIdentityImport.model_validate(runtime.identity_import_current(row,container,request.version))
                return {'protocol':1,**request.model_dump(),'imported_identity':identity.model_dump()}
            finally:
                self.executor._release_runtime(runtime)

    def _directory(self, scope: ExecutionScope, *, create: bool = False) -> Path:
        if (scope.node_key!=self.executor.node_key or scope.role!='login' or scope.gateway_account_id is not None
                or scope.source not in ('oauth-refresh:'+scope.operation_id,'quota:'+scope.operation_id)):
            raise ValueError('节点凭据操作范围无效')
        root=self.executor.data/'node-credentials'
        environment=root/scope.environment_id
        directory=environment/scope.operation_id
        if create:
            for path in (root,environment,directory):
                private_directory(path)
        return directory

    def _record(self, scope: ExecutionScope) -> dict:
        with self.lock:
            value=strict_json(safe_read(self._directory(scope)/'execution.json',32768,private=True),32768)
        request=credential_start({'scope':value.get('scope'),'work':value.get('work')})
        if (value.get('protocol')!=1 or request.scope!=scope
                or value.get('phase') not in ('starting','ready','reconcile','closed')
                or type(value.get('start_intent')) is not bool):
            raise ValueError('节点原凭据操作记录需要核对')
        result,outcome=value.get('result'),value.get('outcome')
        if (result is not None and (not isinstance(result,dict) or result.get('source')!=scope.source
                    or not isinstance(result.get('token'),str) or not 1<=len(result['token'])<=512)
                or outcome is not None and (not isinstance(outcome,dict)
                    or outcome.get('status') not in ('complete','failed','unsubmitted','uncertain'))):
            raise ValueError('节点原凭据结论或执行定位需要核对')
        return value

    def _save(self, scope: ExecutionScope, value: dict) -> None:
        # 私有读取要求单链接；同进程原子替换与读取串行，避免旧fd在fstat前变为零链接。
        with self.lock:
            atomic_json(self._directory(scope)/'execution.json',value)

    def _unsubmitted(self, scope: ExecutionScope) -> dict | None:
        try:
            with self.lock:
                value=strict_json(safe_read(self._directory(scope)/'unsubmitted.json',8192,private=True),8192)
        except FileNotFoundError:
            return None
        expected={'protocol':1,'scope':scope.model_dump(),'phase':'closed','result':None,'outcome':{'status':'unsubmitted'}}
        proof=self.grants.get(scope)
        if value!=expected or proof['phase']!='closed' or proof.get('closed_reason')!='node_not_started':
            raise ValueError('原节点凭据未启动回执需要核对')
        return value

    @staticmethod
    def _receipt(record: dict) -> dict:
        return {key:record[key] for key in ('protocol','scope','phase','result','outcome','error_type') if key in record}

    def _account(self, request: CredentialRefreshStart | CredentialUsageStart, *, stopping: bool = False,
                 require_home: bool = False) -> tuple[dict,dict]:
        scope,work=request.scope,request.work
        observed=CredentialStatusRead(node_key=scope.node_key,account_id=scope.account_id,
            environment_id=scope.environment_id,assignment_revision=scope.assignment_revision,
            generation=scope.generation,version=work.version,account_identity=work.account_identity)
        return read_node_credential_account(self.executor,observed,stopping=stopping,require_home=require_home)

    def _review(self, request: CredentialRefreshStart | CredentialUsageStart, account: dict) -> bool:
        work=request.work
        if isinstance(request,CredentialUsageStart) or work.review_scope is None:
            return True
        parent=self.runs._record(work.review_scope)
        original=RunWork.model_validate(parent['work'])
        if (parent['phase']!='closed' or self.grants.get(work.review_scope)['phase']!='closed'
                or original.project is None or original.project.scenario is None or original.project.scenario.review is None
                or work.review_request_id!=hashlib.sha256(work.review_scope.source.encode()).hexdigest()):
            raise ValueError('原私有评审需要先完成实际停止及许可释放')
        runtime=self.host.runtime
        path=runtime.data/'project-review-owner-refresh'/(str(account['id'])+'.json')
        state=strict_json(safe_read(path,16384),16384)
        if (state.get('request_id')!=work.review_request_id or state.get('source')!=work.review_scope.source
                or state.get('identity')!=work.account_identity or state.get('environment_id')!=request.scope.environment_id
                or state.get('environment_generation')!=request.scope.generation):
            raise ValueError('原Node评审刷新待办已变化')
        pending=runtime.reviews.owner_refresh_state(account,identity=work.account_identity)
        if pending is not None and pending['status'] not in ('waiting','refreshing'):
            raise ValueError('原Node评审刷新待办需要明确恢复')
        return pending is not None

    def start(self, request: CredentialRefreshStart | CredentialUsageStart) -> dict:
        """一次登记具体维护意图，重复启动只返回原回执。

        :param request: 原独立凭据工作与有限Scope。
        :return: 原starting、ready或已确定收口回执。
        """
        scope=request.scope
        with self.executor._locked(environment_id=scope.environment_id),self.lock:
            cancelled=self._unsubmitted(scope)
            if cancelled is not None:
                return cancelled
            path=self._directory(scope,create=True)/'execution.json'
            if path.exists() or path.is_symlink():
                previous=self._record(scope)
                if previous['work']!=request.work.model_dump():
                    raise ValueError('原节点凭据冻结工作已变化')
                return self._receipt(previous)
            if self.closing or self.host.closed or self.host.runtime is None:
                raise ValueError('节点原凭据运行时尚未准备或正在关闭')
            account,_=self._account(request)
            required=self._review(request,account)
            if not self.slots.acquire(blocking=False):
                raise ValueError('节点凭据维护响应仍在核对')
            try:
                # active证明先于线程和实际exec；任一崩溃窗口都保留唯一旧操作。
                self.grants.activate(scope)
                record={'protocol':1,'scope':scope.model_dump(),'work':request.work.model_dump(),'phase':'starting',
                    'result':None,'start_intent':False,'outcome':None}
                atomic_json(path,record)
                if not required:
                    record['outcome']={'status':'complete','skipped':True}
                    self._finish_review(request,record['outcome'])
                    self.grants.close(scope,'node_execution_closed')
                    record['phase']='closed'
                    atomic_json(path,record)
                    self.slots.release()
                else:
                    worker=threading.Thread(target=self._run,args=(request,),name='node-credential-refresh',daemon=True)
                    self.workers[scope.operation_id]=worker
                    worker.start()
            except BaseException:
                self.workers.pop(scope.operation_id,None)
                self.slots.release()
                raise
            return self._receipt(record)

    @contextmanager
    def _setup(self, request, account):
        runtime=self.host.runtime
        if isinstance(request,CredentialUsageStart):
            row,container=runtime.ensure(account,prepare_sender=False)
            job=runtime.claim(row,account,request.scope.source)
            try:
                runtime.authorize_input(job)
                yield row,container,job
            except Exception:
                runtime.cleanup(job['token'])
                raise
        else:
            with runtime._cli_setup(account,request.scope.source,request.work.version,exclusive=True) as value:
                yield value

    def _run(self, request: CredentialRefreshStart | CredentialUsageStart) -> None:
        scope,work=request.scope,request.work
        runtime=self.host.runtime
        try:
            with self.executor._locked(environment_id=scope.environment_id):
                if self._record(scope)['phase']=='closed':
                    return
                account,_=self._account(request)
                mirror=self.host.gateway.lease_mirror
                mirror.attach(scope)
                with mirror.preparing(scope),self._setup(request,account) as (row,container,job):
                    # 首次维护也沿原选择器补齐HOME；已有完整HOME保持轮换后的权威凭据。
                    runtime.sync_credentials(row,account)
                    context={'NETWORK_INSPECTION_MODE':'passthrough','QUOTA_SOURCE':scope.source}
                    atomic_json(runtime._network_runtime(row)/'context.json',context)
                    runtime._configure_network_context(container,context)
                    handle=hashlib.sha256(scope.source.encode()).hexdigest()[:20]
                    directory=runtime._root(row)/'runtime/jobs'/handle
                    directory.mkdir(parents=True,exist_ok=True,mode=0o700)
                    os.chown(directory,1000,1000,follow_symlinks=False)
                    usage=isinstance(request,CredentialUsageStart)
                    job.update(handle=handle,execution_role='credential-usage' if usage else 'credential-refresh',version=work.version)
                    runtime._save_execution(job)
                    record=self._record(scope)
                    record.update(phase='ready',result={'token':job['token'],'source':scope.source})
                    self._save(scope,record)
                    deadline=str(self.grants.authorize(scope).not_after)
                    options={'V3_NATIVE_USAGE':'1','V3_USAGE_NOT_AFTER':deadline} if usage else {
                        'OAUTH_FORCE_REFRESH':'1' if work.force_refresh else '0','OAUTH_REFRESH_BUFFER_SEC':str(work.refresh_buffer_sec),
                        'V3_OAUTH_REFRESH_NOT_AFTER':deadline}
                    environment=cli_telemetry_environment({'HOME':'/home/node','CLAUDE_CODE_VERSION':work.version,
                        **options,**runtime.execution_environment(row)})
                    script='set -eu; echo $$ > '+shlex.quote('/run/v3/jobs/'+handle+'/group.pid')+'; exec bash -lc '+shlex.quote(
                        QUOTA_PROBE_SCRIPT if usage else OAUTH_REFRESH_SCRIPT)
                    command=['setsid','--wait','bash','-c',script]

            @contextmanager
            def launch(exec_id: str):
                # 仅启动HTTP握手持锁；读取正文时允许原stop取得锁并定向收口。
                with self.executor._locked(environment_id=scope.environment_id):
                    record=self._record(scope)
                    if self.closing or self.host.closed or record['phase']!='ready' or record['start_intent']:
                        raise ValueError('原凭据操作已经停止或进入过启动意图')
                    self._account(request,require_home=True)
                    self.grants.authorize(scope)
                    runtime.authorize_input(job)
                    runtime.register_exec(job['token'],exec_id)
                    record['start_intent']=True
                    self._save(scope,record)
                    yield

            value=execute_oauth_refresh_probe(runtime.client.api,container.id,command,environment,
                user='1000',workdir='/home/node',launch_guard=launch)
            # 原探针异常正文可能来自网络；节点只发布固定结论和已核对的到期值。
            if usage:
                credentials=strict_json(safe_read(runtime._root(row)/'home/.claude/.credentials.json',1024*1024),1024*1024)
                outcome={'status':'complete','usage':node_usage_result(value,credentials)}
            elif value.get('error'):
                status='unsubmitted' if value.get('submitted') is False else 'failed' if type(value.get('status')) is int else 'uncertain'
                outcome={'status':status}
                if type(value.get('status')) is int and 100<=value['status']<=599:
                    outcome['http_status']=value['status']
            elif value.get('refreshed') is True or value.get('skipped') is True:
                outcome={'status':'complete','refreshed':value.get('refreshed') is True,'skipped':value.get('skipped') is True}
                if type(value.get('expiresAt')) in (int,float) and 0<value['expiresAt']<10**16:
                    outcome['expires_at']=value['expiresAt']
            else:
                outcome={'status':'uncertain'}
            with self.executor._locked(environment_id=scope.environment_id):
                record=self._record(scope)
                if record['outcome'] is None or record['outcome'].get('status')=='uncertain':
                    record['outcome']=outcome
                    self._save(scope,record)
            self.stop(scope)
        except Exception as error:
            with self.executor._locked(environment_id=scope.environment_id):
                record=self._record(scope)
                if record['phase']!='closed':
                    record.update(phase='reconcile',error_type=type(error).__name__)
                    self._save(scope,record)
        finally:
            with self.lock:
                self.workers.pop(scope.operation_id,None)
            self.slots.release()

    def get(self, scope: ExecutionScope) -> dict:
        """只读原记录，重启后的未决刷新保持核对状态。

        :param scope: 原冻结Scope。
        :return: 无AT/RT的原回执。
        """
        cancelled=self._unsubmitted(scope)
        if cancelled is not None:
            return cancelled
        record=self._record(scope)
        with self.lock:
            active=scope.operation_id in self.workers
        if record['phase'] in ('ready','starting') and not active:
            record={**record,'phase':'reconcile','error_type':'NodeRestart'}
        return self._receipt(record)

    def _finish_review(self, request: CredentialRefreshStart | CredentialUsageStart, outcome: dict) -> None:
        work=request.work
        if isinstance(request,CredentialUsageStart) or work.review_scope is None or outcome['status']=='uncertain':
            return
        known=(outcome['status'] in ('complete','unsubmitted') or outcome['status']=='failed'
            and type(outcome.get('http_status')) is int and 400<=outcome['http_status']<500)
        if not known:
            return
        runtime=self.host.runtime
        path=runtime.data/'project-review-owner-refresh'/(str(work.account_id)+'.json')
        with runtime.reviews._refresh_lock:
            state=strict_json(safe_read(path,16384),16384)
            if (state.get('request_id')!=work.review_request_id or state.get('identity')!=work.account_identity
                    or state.get('source')!=work.review_scope.source or state.get('environment_id')!=request.scope.environment_id
                    or state.get('environment_generation')!=request.scope.generation):
                raise ValueError('原评审待办在凭据维护期间已变化')
            if state.get('maintenance_operation')==request.scope.operation_id:
                return
            if outcome['status']=='complete':
                state.update(status='complete',completed_at=time.time())
            else:
                count=min(2,state['attempts']+1)
                state.update(status='waiting' if outcome['status']=='unsubmitted' and count<2 else 'error',
                    attempts=count,not_before=time.time()+5,error='CredentialRefreshUnsubmitted' if outcome['status']=='unsubmitted' else 'CredentialRefreshRejected')
            state['maintenance_operation']=request.scope.operation_id
            atomic_json(path,state)

    def stop(self, scope: ExecutionScope) -> dict:
        """沿原exec及进程组停止，结果未知仍保留原结论供所有者隔离。

        :param scope: 原Scope；过期后仍具停止能力。
        :return: 实际停止确认后的原回执。
        """
        with self.executor._locked(environment_id=scope.environment_id):
            cancelled=self._unsubmitted(scope)
            if cancelled is not None:
                return cancelled
            try:
                record=self._record(scope)
            except FileNotFoundError:
                if self.grants.get(scope)['phase']!='prepared':
                    raise ValueError('原凭据操作已认领，请核对原启动记录') from None
                self.grants.close(scope,'node_not_started')
                receipt={'protocol':1,'scope':scope.model_dump(),'phase':'closed','result':None,'outcome':{'status':'unsubmitted'}}
                with self.lock:
                    atomic_json(self._directory(scope,create=True)/'unsubmitted.json',receipt)
                return receipt
            if record['phase']=='closed':
                return self._receipt(record)
            self.grants.get(scope)
            runtime=self.host.recovery_runtime(scope)
            request=credential_start({'scope':scope.model_dump(),'work':record['work']})
            account,row=self._account(request,stopping=True)
            usage=isinstance(request,CredentialUsageStart)
            job=runtime.restore_execution(row,account,scope.source,None,shared_cli=False,
                credential_refresh=not usage,credential_usage=usage)
            if job is not None:
                if record['result'] is not None and record['result']['token']!=job['token']:
                    raise ValueError('原节点凭据执行定位与实际作业不一致')
                runtime.cleanup(job['token'])
                if runtime._execution_path(job).exists() or any(value['source']==scope.source
                        for value in runtime.environment_jobs(scope.environment_id)):
                    raise ValueError('原节点凭据执行记录或实际作业仍未收口')
            elif record['start_intent'] or not usage:
                try:
                    container=runtime._container(row)
                except NotFound:
                    container=None
                if container is not None:
                    container.reload()
                    if container.status=='running':
                        observed=container.exec_run(['python3','-I','/usr/local/bin/v3-cli-control','status'])
                        if observed.exit_code!=1:
                            raise ValueError('原账号仍有实际CLI进程，凭据维护继续核对')
                    elif container.status not in ('exited','dead','created'):
                        raise ValueError('原CLI角色实际停止状态尚未确认')
            self.grants.close(scope,'node_execution_closed')
            self.host.gateway.lease_mirror.release_independent(scope)
            record['phase']='closed'
            if record['outcome'] is None:
                record['outcome']={'status':'uncertain' if record['start_intent'] else 'unsubmitted'}
            self._finish_review(request,record['outcome'])
            self._save(scope,record)
            return self._receipt(record)

    def close(self) -> None:
        """关闭新维护线程，保留未决记录供原节点重启收口。:return: None。"""
        with self.lock:
            self.closing=True
            workers=list(self.workers.values())
        deadline=time.monotonic()+5
        for worker in workers:
            worker.join(max(0,deadline-time.monotonic()))
