"""已有独立Node账号的原暂存登录、单次输入与严格停止。"""
from __future__ import annotations

import json
import hashlib
import base64
import os
import re
import shutil
import threading

import time
from pathlib import Path
from types import SimpleNamespace

from docker.errors import NotFound
from starlette.websockets import WebSocket
from account_runtime import AccountRuntime
from cluster_update_gate import NodeJobThread
from cluster_credential_account import read_node_credential_account
from cluster_credentials_contract import CredentialRefreshStart, CredentialStatusRead
from cluster_execution_grants import ExecutionGrant, ExecutionScope
from cluster_login_contract import AccountLoginAccept, AccountLoginCode, AccountLoginCodeRead, AccountLoginStart, login_authorization_sha256
from cluster_pty import PtyInput, PtyResize, serve_node_pty
from cluster_terminal import TerminalInputQuery
from login_terminal import authorization_url
from runtime_files import atomic_json, directory_fd, private_directory
from system_update_contract import safe_read, strict_json


class NodeAccountLogins:
    """在原唯一节点运行时管理明确登录；新输入持续受有限证明保护。

    :param executor: 原节点执行器。
    :param host: 原唯一运行时。
    :param grants: 原中央有限许可。
    :param credentials: 原具体凭据维护，用于已停止RT父来源核对。
    """

    def __init__(self, executor, host, grants, credentials=None) -> None:
        """保存具体维护依赖和有限安装线程。

        :param executor: 原执行器。
        :param host: 原运行时。
        :param grants: 原证明存储。
        :param credentials: 原具体凭据执行器，用于读取实际已停止的RT父来源。
        :return: None。
        """
        self.executor,self.host,self.grants=executor,host,grants
        self.credentials=credentials
        self.lock,self.slots=threading.RLock(),threading.BoundedSemaphore(4)
        self.sessions,self.workers={},{}
        self.ptys={}
        self.code_inflight=set()
        self.closing=False

    def _request(self, scope, work):
        return AccountLoginStart.model_validate({'scope':scope,'work':work})

    def _code_read(self, scope, request_id):
        return AccountLoginCodeRead(scope=scope,request_id=request_id)

    def _input_query(self, scope, operation_id):
        return TerminalInputQuery(scope=scope,operation_id=operation_id)

    def _recovery_runtime(self, scope):
        return self.host.recovery_runtime(scope)

    def _session_profile(self, request):
        return self.executor.data/'environments'/request.scope.environment_id/'home/.v3-login'/request.work.sid/'.claude'

    def _restore_login_execution(self, runtime, row, account, request, proof):
        return runtime.restore_execution(row,account,request.scope.source,proof['grant'].get('lease'),shared_cli=False,account_login=True)

    def _commit_identity(self, request, top: dict, commit: dict) -> None:
        """独立账号沿原提交规则；具体绑定消费者在冻结前额外核对原身份。"""

    def _can_stop(self, value: dict) -> bool:
        return value.get('commit') is None or value['commit']['stage']=='accepted'

    def _release_mirror(self, scope: ExecutionScope) -> None:
        self.host.gateway.lease_mirror.release_independent(scope)

    def _directory(self, scope: ExecutionScope, *, create: bool = False) -> Path:
        if (scope.node_key!=self.executor.node_key or scope.role!='login' or scope.gateway_account_id is not None
                or re.fullmatch(r'login:[a-f0-9]{12}',scope.source) is None):
            raise ValueError('原独立登录操作范围无效')
        root=self.executor.data/'node-logins'
        environment,directory=root/scope.environment_id,root/scope.environment_id/scope.operation_id
        if create:
            for path in (root,environment,directory):
                private_directory(path)
        return directory

    def _record(self, scope: ExecutionScope) -> dict:
        with self.lock:
            value=strict_json(safe_read(self._directory(scope)/'execution.json',32768,private=True),32768)
        request=self._request(value.get('scope'),value.get('work'))
        if (request.scope!=scope or value.get('protocol')!=1 or type(value.get('start_intent')) is not bool
                or type(value.get('discarded',False)) is not bool
                or value.get('phase') not in ('starting','ready','reconcile','closed')):
            raise ValueError('原Node登录记录需要核对')
        result=value.get('result')
        if result is not None and (not isinstance(result,dict) or result.get('source')!=scope.source
                or not isinstance(result.get('token'),str) or not 1<=len(result['token'])<=512):
            raise ValueError('原登录实际执行定位需要核对')
        commit=value.get('commit')
        if commit is not None and (not isinstance(commit,dict) or commit.get('stage') not in ('frozen','home_saved','saved','accepted')
                or not re.fullmatch('[a-f0-9]{64}',str(commit.get('authorization_sha256','')))
                or not re.fullmatch('[a-f0-9]{64}',str(commit.get('refresh_sha256','')))
                or type(commit.get('cleanup_pending')) is not bool):
            raise ValueError('原登录提交阶段需要核对')
        if commit is not None and (not isinstance(commit.get('files'),list)
                or set(commit['files']) not in ({'.claude.json','.claude/.credentials.json'},
                    {'.claude.json','.claude/.credentials.json','.claude/settings.json'})
                or len(commit['files'])!=len(set(commit['files']))):
            raise ValueError('原登录冻结文件清单需要核对')
        return value

    def _save(self, scope: ExecutionScope, value: dict) -> None:
        with self.lock:
            atomic_json(self._directory(scope)/'execution.json',value)

    def _cancelled(self, scope: ExecutionScope) -> dict | None:
        try:
            with self.lock:
                value=strict_json(safe_read(self._directory(scope)/'unsubmitted.json',8192,private=True),8192)
        except FileNotFoundError:
            return None
        expected={'protocol':1,'scope':scope.model_dump(),'phase':'closed','result':None}
        try:
            proof=self.grants.get(scope)
        except FileNotFoundError:
            proof=None
        if (value!=expected or proof is not None and (proof['phase'] not in ('prepared','closed')
                or proof['phase']=='closed' and proof.get('closed_reason')!='node_not_started')):
            raise ValueError('原登录取消回执需要核对')
        return value

    @staticmethod
    def _receipt(value: dict) -> dict:
        return {key:value[key] for key in ('protocol','scope','phase','result','error_type','commit','discarded') if key in value}

    def _account(self, request: AccountLoginStart, *, stopping: bool = False) -> tuple[dict,dict]:
        scope,work=request.scope,request.work
        observed=CredentialStatusRead(node_key=scope.node_key,account_id=scope.account_id,
            environment_id=scope.environment_id,assignment_revision=scope.assignment_revision,generation=scope.generation,
            version=work.version,account_identity=work.account_identity)
        return read_node_credential_account(self.executor,observed,stopping=stopping,require_home=not stopping,allow_inactive=True)

    def _authorize(self, request: AccountLoginStart, *, prepared: bool = False) -> None:
        if prepared:
            value=self.grants.get(request.scope)
            if value['phase']!='prepared':
                raise ValueError('原登录准备证明已被认领或关闭')
            grant=ExecutionGrant.model_validate(value['grant'])
        else:
            grant=self.grants.authorize(request.scope)
        if time.time()>=request.work.expires_at or grant.not_after>request.work.expires_at:
            raise ValueError('原登录授权已过期或有限证明越过原TTL')

    def _refresh_parent(self, request: AccountLoginStart) -> None:
        parent=request.work.refresh_scope
        if parent is None:
            return
        if self.credentials is None:
            raise ValueError('原RT维护读取器尚未准备')
        value=self.credentials._record(parent)
        original=CredentialRefreshStart.model_validate({'scope':value['scope'],'work':value['work']})
        if (value['phase']!='closed' or self.grants.get(parent)['phase']!='closed'
                or original.work.account_identity!=request.work.account_identity):
            raise ValueError('原RT维护尚未实际停止或账号身份已变化')

    def start(self, request: AccountLoginStart) -> dict:
        """持久登记后一次启动原暂存登录，重复请求只返回原记录。

        :param request: 原明确重授权工作。
        :return: 原异步准备或已有回执。
        """
        scope=request.scope
        with self.executor._locked(environment_id=scope.environment_id),self.lock:
            cancelled=self._cancelled(scope)
            if cancelled is not None:
                return cancelled
            path=self._directory(scope,create=True)/'execution.json'
            if path.exists() or path.is_symlink():
                value=self._record(scope)
                if self._request(scope,value['work']).work!=request.work:
                    raise ValueError('原登录冻结工作已变化')
                return self.get(scope)
            if self.closing or self.host.closed or self.host.runtime is None:
                raise ValueError('原节点登录运行时尚未准备或正在关闭')
            self._account(request)
            self._refresh_parent(request)
            self._authorize(request,prepared=True)
            if not self.slots.acquire(blocking=False):
                raise ValueError('节点登录准备仍在核对')
            try:
                self.grants.activate(scope)
                value={'protocol':1,'scope':scope.model_dump(),'work':request.work.model_dump(),
                    'phase':'starting','result':None,'start_intent':False}
                atomic_json(path,value)
                worker=NodeJobThread(target=self._run,args=(request,),daemon=True,name='node-account-login')
                self.workers[scope.operation_id]=worker
                worker.start()
            except BaseException:
                self.workers.pop(scope.operation_id,None)
                self.slots.release()
                raise
            return self._receipt(value)

    def _run(self, request: AccountLoginStart) -> None:
        scope,work=request.scope,request.work
        try:
            with self.executor._locked(environment_id=scope.environment_id):
                value=self._record(scope)
                if self.closing or value['phase']=='closed':
                    return
                account,_=self._account(request)
                self._refresh_parent(request)
                self._authorize(request)
                value['start_intent']=True
                self._save(scope,value)
                mirror=self.host.gateway.lease_mirror
                mirror.attach(scope)
                with mirror.preparing(scope):
                    row,container,profile,home=self.host.runtime.begin_login(work.sid,account,work.version,True)
                job=self.host.runtime.job_for_container(self.host.runtime.execution_token(container.id,scope.source))
                job['execution_role']='account-login'
                self.host.runtime._save_execution(job)
                session=SimpleNamespace(sid=work.sid,name=account['name'],worker_id=container.id,profile_dir=profile,
                    home=home,version=work.version,force_reauth=True,phase='authorizing',created_at=time.time())
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

    def get(self, scope: ExecutionScope) -> dict:
        """只查询原登录，重启后保持原工作待核对。

        :param scope: 原冻结范围。
        :return: 无凭据或终端正文的原回执。
        """
        cancelled=self._cancelled(scope)
        if cancelled is not None:
            return cancelled
        value=self._record(scope)
        with self.lock:
            active=scope.operation_id in self.sessions or scope.operation_id in self.workers
        if value['phase'] in ('starting','ready') and not active:
            value={**value,'phase':'reconcile','error_type':'NodeRestart'}
        if value['phase']=='ready' and self._pending_pty(scope):
            value={**value,'phase':'reconcile','error_type':'LoginPtyInputUnconfirmed'}
        return self._receipt(value)

    def observe(self, scope: ExecutionScope) -> dict:
        """沿原有限证明执行固定CLI认证检查并提取原授权链接。

        :param scope: 原登录范围。
        :return: 已校验的公开阶段、认证状态和链接，不返回身份或凭据。
        """
        with self.executor._locked(environment_id=scope.environment_id):
            return self._observe_locked(scope)

    def _observe_locked(self, scope: ExecutionScope) -> dict:
        value=self._record(scope)
        request=self._request(scope,value['work'])
        if value.get('commit') is not None:
            phase='committed' if value['phase']=='closed' and not value['commit']['cleanup_pending'] else 'submitting'
            return {'phase':phase,'credentials_ready':True,'expires_at':request.work.expires_at,
                'reconnectable':False,'authorization_url':None}
        self._authorize(request)
        self._account(request)
        with self.lock:
            session=self.sessions.get(scope.operation_id)
        if value['phase']!='ready' or session is None:
            raise ValueError('原登录终端仍需核对')
        try:
            document=strict_json(safe_read(session.profile_dir/'.credentials.json',1024*1024),1024*1024)
            AccountRuntime._local_oauth(document)
            credentials_present=True
        except (OSError,ValueError):
            credentials_present=False
        ready,auth_method=False,None
        if credentials_present:
            result=self.host.runtime.exec_cli(value['result']['token'],['claude','auth','status'],session.home,session.version)
            try:
                status=json.loads(result.output)
            except (ValueError,TypeError):
                status={}
            ready=result.exit_code==0 and isinstance(status,dict) and status.get('loggedIn') is True
            if ready and isinstance(status.get('authMethod'),str) and len(status['authMethod'])<=80:
                auth_method=status['authMethod']
                oauth=document['claudeAiOauth']
                if any(oauth[key] in auth_method for key in ('accessToken','refreshToken')):
                    auth_method=None
        phase=session.phase
        if ready:
            phase='ready_to_submit'
        elif phase=='ready_to_submit' or phase=='authorizing' and not self.host.runtime.login_terminal_alive(session):
            phase='ended'
        url=authorization_url(self.host.runtime.capture_login_pane(session)) if phase=='authorizing' else None
        session.phase=phase
        return {'phase':phase,'credentials_ready':ready,'expires_at':request.work.expires_at,
            'reconnectable':phase=='authorizing','authorization_url':url,'auth_method':auth_method}

    def code(self, request: AccountLoginCode) -> dict:
        """持久登记本次输入回执，授权码只送入原tmux stdin一次。

        :param request: 原Scope与单次授权码输入。
        :return: 原delivered/rejected/uncertain回执；同标识重读。
        """
        scope=request.scope
        with self.executor._locked(environment_id=scope.environment_id):
            value=self._record(scope)
            original=self._request(scope,value['work'])
            directory=self._directory(scope)/'codes'
            private_directory(directory)
            path=directory/(request.request_id+'.json')
            with self.lock:
                if path.exists() or path.is_symlink():
                    return self.code_receipt(self._code_read(scope,request.request_id))
            self._authorize(original)
            self._account(original)
            if self._pending_pty(scope):
                raise ValueError('原登录PTY输入结果需要先核对')
            with self.lock:
                session=self.sessions.get(scope.operation_id)
            if (value['phase']!='ready' or value.get('commit') is not None or session is None or session.phase!='authorizing'
                    or len(list(directory.glob('*.json')))>=32):
                raise ValueError('原登录已结束或本次输入需要核对')
            receipt={'request_id':request.request_id,'status':'sending','message':'正在发送授权码'}
            key=(scope.operation_id,request.request_id)
            with self.lock:
                self.code_inflight.add(key)
            try:
                with self.lock:
                    atomic_json(path,receipt)
                try:
                    self.host.runtime.send_login_code(session,request.request_id,request.code.strip())
                    receipt.update(status='delivered',message='已送到CLI，等待认证检查')
                except ValueError:
                    receipt.update(status='rejected',message='原登录终端不可用，授权码未发送')
                except Exception:
                    receipt.update(status='uncertain',message='发送结果未知，请查询原回执并检查CLI')
                with self.lock:
                    atomic_json(path,receipt)
            finally:
                with self.lock:
                    self.code_inflight.discard(key)
            return receipt

    def code_receipt(self, request: AccountLoginCodeRead) -> dict:
        """只读原授权码回执；重启或超时均不补发输入。

        :param request: 原完整范围与输入标识。
        :return: 已持久保存的固定回执。
        """
        self._record(request.scope)
        with self.lock:
            value=strict_json(safe_read(self._directory(request.scope)/'codes'/(request.request_id+'.json'),4096,private=True),4096)
            inflight=(request.scope.operation_id,request.request_id) in self.code_inflight
        if (set(value)!={'request_id','status','message'} or value['request_id']!=request.request_id
                or value['status'] not in ('sending','delivered','rejected','uncertain')
                or not isinstance(value['message'],str) or len(value['message'])>200):
            raise ValueError('原授权码回执需要核对')
        if value['status']=='sending' and not inflight:
            # 重启或回执落盘失败后只投影未知，保留原发送意图并禁止重新输入。
            return {'request_id':request.request_id,'status':'uncertain','message':'发送结果未知，请查询原回执并检查CLI'}
        return value

    def _pending_pty(self, scope: ExecutionScope) -> bool:
        with self.lock:
            try:
                value=strict_json(safe_read(self._directory(scope)/'pty-input-state.json',8192,private=True),8192)
            except FileNotFoundError:
                return False
            if set(value)!={'scope','operation_id'} or value['scope']!=scope.model_dump():
                raise ValueError('原登录PTY输入定位需要核对')
            request=self._input_query(scope,value['operation_id'])
            try:
                return self.input_receipt(request)['status']=='unknown'
            except FileNotFoundError:
                return True

    def _pty_session(self, scope: ExecutionScope):
        value=self._record(scope)
        request=self._request(scope,value['work'])
        self._authorize(request)
        self._account(request)
        if self._pending_pty(scope):
            raise ValueError('原登录PTY输入结果需要先核对')
        with self.lock:
            session=self.sessions.get(scope.operation_id)
        if value['phase']!='ready' or value.get('commit') is not None or session is None or session.phase!='authorizing':
            raise ValueError('原登录终端已经结束或正在保存')
        runtime=self.host.runtime
        if runtime is None:
            raise ValueError('原登录运行时需要核对')
        job=runtime.job_for_container(value['result']['token'])
        runtime.authorize_input(job)
        return runtime,job,session

    def open_pty(self, scope: ExecutionScope):
        """只连接同一原tmux，浏览器重连不再次执行auth login。

        :param scope: 原登录完整范围。
        :return: 原attach的非阻塞输出socket。
        """
        with self.executor._locked(environment_id=scope.environment_id):
            runtime,job,session=self._pty_session(scope)
            with runtime.environment_lock(scope.environment_id),self.lock:
                if scope.operation_id in self.ptys:
                    raise ValueError('原登录终端已有连接，请关闭原连接后重连')
                execution=runtime.client.api.exec_create(session.worker_id,
                    ['tmux','-S',job['tmux_socket'],'attach-session','-d','-t',session.sid],stdin=True,tty=True,
                    user='1000',environment={'HOME':session.home,'TERM':'xterm-256color','COLUMNS':'120','LINES':'36'},workdir=session.home)
                stream=runtime.client.api.exec_start(execution['Id'],detach=False,tty=True,stream=False,socket=True,demux=False)
                raw=getattr(stream,'_sock',None) or stream
                try:
                    raw.setblocking(False)
                except BaseException:
                    raw.close()
                    raise
                self.ptys[scope.operation_id]={'raw':raw,'exec':execution['Id'],'job':job,'scope':scope}
                return raw

    def send_input(self, scope: ExecutionScope, request: PtyInput) -> dict:
        """原登录PTY每片只投递一次，未知写入关闭本次后续输入。

        :param scope: 原登录范围。
        :param request: 有限字节和单次输入标识。
        :return: sent、not_sent或unknown回执，记录仅含输入摘要。
        """
        data=base64.b64decode(request.data,validate=True)
        if not 1<=len(data)<=16384:
            raise ValueError('原登录PTY输入超过上限')
        digest=hashlib.sha256(data).hexdigest()
        with self.executor._locked(environment_id=scope.environment_id):
            directory=self._directory(scope)/'pty-inputs'
            private_directory(directory)
            path=directory/(request.operation_id+'.json')
            with self.lock:
                if path.exists() or path.is_symlink():
                    old=self.input_receipt(self._input_query(scope,request.operation_id))
                    if old['payload_sha256']!=digest:
                        raise ValueError('原PTY输入标识已经用于其他内容')
                    return old
            runtime,job,_=self._pty_session(scope)
            with runtime.environment_lock(scope.environment_id),self.lock:
                pty=self.ptys.get(scope.operation_id)
                if pty is None or pty['job'] is not job or len(list(directory.glob('*.json')))>=1024:
                    raise ValueError('原登录PTY连接已结束或输入次数达到上限')
                runtime.authorize_input(job)
                receipt={'scope':scope.model_dump(),'operation_id':request.operation_id,'payload_sha256':digest,'status':'unknown'}
                atomic_json(self._directory(scope)/'pty-input-state.json',{'scope':scope.model_dump(),'operation_id':request.operation_id})
                atomic_json(path,receipt)
                try:
                    original=self._request(scope,self._record(scope)['work'])
                    self._authorize(original)
                    runtime.authorize_input(job)
                    if pty['raw'].send(data)==len(data):
                        receipt['status']='sent'
                except Exception:
                    pass
                atomic_json(path,receipt)
                if receipt['status']!='sent':
                    value=self._record(scope)
                    value.update(phase='reconcile',error_type='LoginPtyInputUnconfirmed')
                    self._save(scope,value)
                return receipt

    def input_receipt(self, request: TerminalInputQuery) -> dict:
        """只读本次PTY片段回执，重启后保持未知发送意图。

        :param request: 原完整范围和输入标识。
        :return: 固定摘要与原状态。
        """
        self._record(request.scope)
        with self.lock:
            value=strict_json(safe_read(self._directory(request.scope)/'pty-inputs'/(request.operation_id+'.json'),8192,private=True),8192)
        if (set(value)!={'scope','operation_id','payload_sha256','status'} or value['scope']!=request.scope.model_dump()
                or value['operation_id']!=request.operation_id or value['status'] not in ('sent','not_sent','unknown')
                or re.fullmatch('[a-f0-9]{64}',str(value['payload_sha256'])) is None):
            raise ValueError('原登录PTY输入回执需要核对')
        return value

    def resize(self, scope: ExecutionScope, request: PtyResize) -> None:
        """核对原许可后调整同一登录窗口。

        :param scope: 原范围。
        :param request: 有限行列尺寸。
        :return: None。
        """
        with self.executor._locked(environment_id=scope.environment_id):
            runtime,_,_=self._pty_session(scope)
            with self.lock:
                pty=self.ptys[scope.operation_id]
                runtime.client.api.exec_resize(pty['exec'],height=request.rows,width=request.cols)

    def close_pty(self, scope: ExecutionScope) -> None:
        """关闭本次attach，原tmux继续由实际停止协议管理。

        :param scope: 原完整范围。
        :return: None。
        """
        with self.lock:
            pty=self.ptys.pop(scope.operation_id,None)
        if pty is not None:
            pty['raw'].close()

    async def serve(self, websocket: WebSocket, scope: ExecutionScope) -> None:
        """在原私有认证连接中转发本次登录PTY。

        :param websocket: 已鉴权的Node连接。
        :param scope: 首帧冻结的原登录。
        :return: None。
        """
        await serve_node_pty(self,websocket,scope)

    _authorization_digest=staticmethod(login_authorization_sha256)

    def _authorization_files(self, scope: ExecutionScope, commit: dict) -> dict:
        root=self._directory(scope)/'authorization'
        documents={name:strict_json(safe_read(root/name,1024*1024,private=True),1024*1024) for name in commit['files']}
        if self._authorization_digest(documents)!=commit['authorization_sha256']:
            raise ValueError('原登录冻结授权摘要不一致')
        AccountRuntime._local_oauth(documents['.claude/.credentials.json'])
        return documents

    def _freeze_authorization(self, scope: ExecutionScope, value: dict, request) -> None:
        """在原环境锁内冻结本次真实认证文件；副本供各具体提交路径接续。"""
        if value['phase']!='ready':
            raise ValueError('原登录尚未完成实际准备')
        observed=self._observe_locked(scope)
        if observed['credentials_ready'] is not True:
            raise ValueError('本次CLI认证检查尚未通过')
        account,row=self._account(request)
        with self.lock:
            session=self.sessions.get(scope.operation_id)
        expected=self._session_profile(request)
        if session is None or session.profile_dir!=expected:
            raise ValueError('本次登录暂存HOME归属不一致')
        documents={}
        for name in ('.claude.json','.claude/.credentials.json','.claude/settings.json'):
            try:
                documents[name]=strict_json(safe_read(session.profile_dir.parent/name,1024*1024),1024*1024)
            except FileNotFoundError:
                if name!='.claude/settings.json':
                    raise ValueError('本次登录授权文件尚不完整') from None
        oauth=AccountRuntime._local_oauth(documents['.claude/.credentials.json'])
        top=documents['.claude.json']
        identity=top.get('oauthAccount')
        if (not isinstance(identity,dict) or not isinstance(identity.get('accountUuid'),str) or not identity['accountUuid']
                or not isinstance(identity.get('emailAddress'),str) or not identity['emailAddress'].strip()
                or oauth['expiresAt']<=int(time.time()*1000)+60000):
            raise ValueError('本次新授权身份或有效期需要核对')
        previous=strict_json(safe_read(self.executor.data/'environments'/scope.environment_id/'home/.claude.json',1024*1024),1024*1024)
        if previous.get('userID') is not None and top.get('userID')!=previous['userID']:
            raise ValueError('本次重授权的原设备身份已变化')
        commit={'stage':'frozen','authorization_sha256':self._authorization_digest(documents),
            'refresh_sha256':hashlib.sha256(oauth['refreshToken'].encode()).hexdigest(),
            'files':sorted(documents),'cleanup_pending':True,'auth_method':observed.get('auth_method')}
        self._commit_identity(request,top,commit)
        root=self._directory(scope)/'authorization'
        private_directory(root)
        optional=root/'.claude/settings.json'
        if '.claude/settings.json' not in documents and (optional.exists() or optional.is_symlink()):
            optional.unlink()
        for name,document in documents.items():
            atomic_json(root/name,document)
        value['commit']=commit
        self._save(scope,value)
        session.phase='submitting'

    def commit(self, scope: ExecutionScope) -> dict:
        """冻结已认证的新授权并保存原Node HOME，重复调用接续原阶段。

        :param scope: 原明确重授权Scope。
        :return: 无令牌的提交阶段与摘要，待中央确认后才释放维护。
        """
        with self.executor._locked(environment_id=scope.environment_id):
            value=self._record(scope)
            request=self._request(scope,value['work'])
            if value.get('commit') is None:
                self._freeze_authorization(scope,value,request)
            commit=value['commit']
            if commit['stage'] in ('saved','accepted'):
                return self._receipt(value)
            if self.grants.get(scope)['phase']!='active':
                raise ValueError('原登录提交证明已经关闭，保存状态需要核对')
            # 冻结意图后的恢复仅复制同一私有授权材料，不重新启动CLI或交换授权码。
            account,row=self._account(request,stopping=True)
            documents=self._authorization_files(scope,commit)
            runtime=self._recovery_runtime(scope)
            if commit['stage']=='frozen':
                runtime._publish_login_home(row,self._directory(scope)/'authorization/.claude')
                commit['stage']='home_saved'
                self._save(scope,value)
            if commit['stage']=='home_saved':
                profile=self.executor.data/'profiles'/account['name']
                for source,target in (('.claude.json','.claude.json'),('.claude/.credentials.json','.credentials.json'),
                        ('.claude/settings.json','settings.json')):
                    if source in documents:
                        atomic_json(profile/target,documents[source])
                commit['stage']='saved'
                self._save(scope,value)
            return self._receipt(value)

    def snapshot(self, scope: ExecutionScope) -> dict:
        """仅经原私有操作读取已保存的新授权，供中央镜像和来源登记。

        :param scope: 原完整登录Scope。
        :return: 受信任调用方使用的当前材料和身份；令牌不保存到操作回执。
        """
        with self.executor._locked(environment_id=scope.environment_id):
            value=self._record(scope)
            request=self._request(scope,value['work'])
            commit=value.get('commit')
            if commit is None or commit['stage'] not in ('saved','accepted'):
                raise ValueError('原Node新授权尚未实际保存')
            account,row=self._account(request,stopping=True)
            root=self.executor.data/'environments'/scope.environment_id/'home'
            credentials=strict_json(safe_read(root/'.claude/.credentials.json',1024*1024),1024*1024)
            oauth=AccountRuntime._local_oauth(credentials)
            if hashlib.sha256(oauth['refreshToken'].encode()).hexdigest()!=commit['refresh_sha256']:
                raise ValueError('原新授权已经轮换，当前所有者资料需要另行核对')
            top=strict_json(safe_read(root/'.claude.json',1024*1024),1024*1024)
            identity=top.get('oauthAccount')
            if not isinstance(identity,dict):
                raise ValueError('原新授权当前身份需要核对')
            runtime=self._recovery_runtime(scope)
            try:
                cli_identity=runtime.read_cli_identity(row,request.work.version)
            except ValueError:
                cli_identity=None
            material={'access_token':oauth['accessToken'],'refresh_token':oauth['refreshToken'],'expires_at':int(oauth['expiresAt'])}
            for key,target in (('subscriptionType','subscription_type'),('rateLimitTier','rate_limit_tier')):
                if isinstance(oauth.get(key),str):
                    material[target]=oauth[key]
            result={'protocol':1,'scope':scope.model_dump(),'authorization_sha256':commit['authorization_sha256'],
                'material':material,'identity':{'user_id':top.get('userID'),'email':identity.get('emailAddress'),
                    'account_uuid':identity.get('accountUuid'),'organization_uuid':identity.get('organizationUuid')},
                'cli_identity':cli_identity,'version':request.work.version,'auth_method':commit.get('auth_method')}
            if len(json.dumps(result,ensure_ascii=False,allow_nan=False).encode())>65536:
                raise ValueError('本次授权快照超过受控响应上限')
            return result

    def accept(self, request: AccountLoginAccept) -> dict:
        """中央确认同一授权保存后，严格停止并清理本次暂存副本。

        :param request: 原Scope及中央已保存的授权摘要。
        :return: 实际停止和暂存清理都确认的原回执。
        """
        scope=request.scope
        with self.executor._locked(environment_id=scope.environment_id):
            value=self._record(scope)
            commit=value.get('commit')
            if (commit is None or commit['stage'] not in ('saved','accepted')
                    or commit['authorization_sha256']!=request.authorization_sha256):
                raise ValueError('中央确认与原Node新授权不一致')
            if commit['stage']!='accepted':
                commit['stage']='accepted'
                self._save(scope,value)
        self.stop(scope)
        with self.executor._locked(environment_id=scope.environment_id):
            value=self._record(scope)
            original=self._request(scope,value['work'])
            self._account(original,stopping=True)
            if value['commit']['cleanup_pending']:
                self._cleanup_materials(scope,original.work.sid)
                value['commit']['cleanup_pending']=False
                self._save(scope,value)
            return self._receipt(value)

    def _cleanup_materials(self, scope: ExecutionScope, sid: str) -> None:
        parents=((self.executor.data/'environments'/scope.environment_id/'home/.v3-login',sid),
            (self._directory(scope),'authorization'))
        for parent,name in parents:
            try:
                descriptor=directory_fd(parent)
            except FileNotFoundError:
                continue
            try:
                # 保持原目录fd；确认删除已同步到目录后才发布清理完成。
                try:
                    shutil.rmtree(name,dir_fd=descriptor)
                except FileNotFoundError:
                    pass
                os.fsync(descriptor)
            finally:
                os.close(descriptor)

    def discard(self, scope: ExecutionScope) -> dict:
        """严格停止后清理明确尚无提交意图的原登录暂存。

        :param scope: 原登录范围。
        :return: 实际关闭且本次暂存已清理的回执；已进入提交必须原路确认。
        """
        with self.executor._locked(environment_id=scope.environment_id):
            cancelled=self._cancelled(scope)
            if cancelled is not None:
                return {**cancelled,'discarded':True}
            value=self._record(scope)
            if value.get('commit') is not None:
                raise ValueError('原授权已进入保存，请先完成原提交对账')
        self.stop(scope)
        with self.executor._locked(environment_id=scope.environment_id):
            value=self._record(scope)
            request=self._request(scope,value['work'])
            self._account(request,stopping=True)
            if not value.get('discarded',False):
                self._cleanup_materials(scope,request.work.sid)
                value['discarded']=True
                self._save(scope,value)
            return self._receipt(value)

    def _check_unstarted_scope(self, scope):
        self.grants.check_scope(scope)

    def stop(self, scope: ExecutionScope) -> dict:
        """按原tmux及实际执行记录停止，严格释放原独占维护。

        :param scope: 原范围；有限证明过期后仍具停止能力。
        :return: 原实际closed回执。
        """
        with self.executor._locked(environment_id=scope.environment_id):
            cancelled=self._cancelled(scope)
            if cancelled is not None:
                return cancelled
            try:
                value=self._record(scope)
            except FileNotFoundError:
                self._check_unstarted_scope(scope)
                try:
                    proof=self.grants.get(scope)
                except FileNotFoundError:
                    proof=None
                if proof is not None and proof['phase']!='prepared':
                    raise ValueError('原登录已认领，请核对原操作') from None
                # 先保存本次取消门禁；迟到创建的prepared证明也不能越过原Actor启动检查。
                receipt={'protocol':1,'scope':scope.model_dump(),'phase':'closed','result':None}
                with self.lock:
                    atomic_json(self._directory(scope,create=True)/'unsubmitted.json',receipt)
                if proof is not None:
                    self.grants.close(scope,'node_not_started')
                return receipt
            if value['phase']=='closed':
                return self._receipt(value)
            if not self._can_stop(value):
                raise ValueError('原登录提交仍待中央确认，请先对账后收口')
            request=self._request(scope,value['work'])
            proof=self.grants.get(scope)
            self.close_pty(scope)
            runtime=self._recovery_runtime(scope)
            account,row=self._account(request,stopping=True)
            job=self._restore_login_execution(runtime,row,account,request,proof)
            if job is not None:
                if (value['result'] is not None and value['result']['token']!=job['token']
                        or job.get('version') not in (None,request.work.version)):
                    raise ValueError('原登录实际定位或冻结CLI版本已变化')
                runtime.cleanup(job['token'])
                if runtime._execution_path(job).exists() or any(current['source']==scope.source
                        for current in runtime.environment_jobs(scope.environment_id)):
                    raise ValueError('原登录执行记录仍需收口')
            elif value['start_intent']:
                try:
                    container=runtime._container(row)
                except NotFound:
                    container=None
                if container is not None:
                    container.reload()
                    if container.status=='running':
                        checked=container.exec_run(['pgrep','-f','/tmp/v3-login-'+request.work.sid+'.sock'])
                        if checked.exit_code!=1:
                            raise ValueError('原登录tmux实际停止仍需核对')
                    elif container.status not in ('created','exited','dead'):
                        raise ValueError('原登录CLI实际状态需要核对')
            self.grants.close(scope,'node_execution_closed')
            self._release_mirror(scope)
            value['phase']='closed'
            self._save(scope,value)
            with self.lock:
                self.sessions.pop(scope.operation_id,None)
            return self._receipt(value)

    def close(self) -> None:
        """关闭新登录，原作业由宿主按实际记录收口。

        :return: None；未决记录继续持久保留。
        """
        with self.lock:
            self.closing=True
            workers=list(self.workers.values())
            scopes=[value['scope'] for value in self.ptys.values()]
        for scope in scopes:
            self.close_pty(scope)
        for worker in workers:
            worker.join(timeout=5)
