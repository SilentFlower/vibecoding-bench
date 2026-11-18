"""中央已有独立SSH账号登录协调，未知输入只查询原操作。"""
from __future__ import annotations

import hashlib
import re
import threading
import time
from contextlib import nullcontext
from uuid import uuid4

from account_runtime import RuntimeBusy
from cluster_credentials_contract import CredentialRefreshWork
from cluster_continue_runner import RemoteContinuePty
from cluster_execution_grants import ExecutionGrant, ExecutionScope
from cluster_login_contract import AccountLoginAccept, AccountLoginCode, AccountLoginCodeRead, AccountLoginSnapshot, AccountLoginStart, AccountLoginWork


class ClusterAccountLogins:
    """原中央账本、owner锁及具体Node登录的唯一协调。

    :param sessions: 原中央持久执行协调。
    :param credentials: 原具体凭据协调与受信只读入口。
    :param owner_lock: 原不可重入账号锁工厂。
    :param save_authorization: 中央镜像和原授权证明保存，调用时持有owner锁。
    :param admission: 可选原业务活动门禁，已停止RT父来源单独传入。
    """

    kind='account-login'
    operation_prefix='account-login-'
    pty_purpose='login'

    def __init__(self, sessions, credentials, owner_lock, save_authorization, admission=None) -> None:
        """登记具体依赖及有限证明维护线程。

        :param sessions: 原执行协调。
        :param credentials: 原凭据协调。
        :param owner_lock: 原账号锁。
        :param save_authorization: 原授权保存回调。
        :param admission: 原产品业务活动检查。
        :return: None。
        """
        self.sessions,self.credentials,self.owner_lock,self.save_authorization=sessions,credentials,owner_lock,save_authorization
        self.admission=admission
        self.lock,self.workers,self.committing=threading.RLock(),{},set()
        self.closing=False

    def _call(self, row: dict, action: str, payload: dict) -> dict:
        return self.sessions._call(row,self.operation_prefix+action,payload)

    def routes(self, account: dict) -> bool:
        """识别已有独立SSH账号。

        :param account: 当前账号行。
        :return: 是否属于本具体登录消费者。
        """
        return (account.get('id') is not None and account.get('cc2api_account_id') is None
            and self.sessions.service.store.assignment(account['id'])['kind']=='ssh')

    def _row(self, operation_id: str) -> tuple[dict,AccountLoginStart]:
        row=self.sessions.ledger.get(operation_id)
        request=AccountLoginStart.model_validate({'scope':row['record']['scope'],'work':row['record']['work']})
        return row,request

    def find(self, sid: str) -> dict | None:
        """按原SID读取持久登录，冲突时关闭自动操作。

        :param sid: 原12位登录标识。
        :return: 原具体记录或None。
        """
        if re.fullmatch('[a-f0-9]{12}',sid) is None:
            raise ValueError('原登录标识无效')
        connection=self.sessions.service.store.database()
        try:
            rows=connection.execute("SELECT operation_id FROM node_executions WHERE role='login' AND source=? LIMIT 2",
                ('login:'+sid,)).fetchall()
        finally:
            connection.close()
        if len(rows)>1:
            raise ValueError('原登录来源存在冲突，需要核对')
        if not rows or self.sessions.ledger.get(rows[0][0])['record']['work'].get('kind')!=self.kind:
            return None
        return self._row(rows[0][0])[0]

    def _account(self, account: dict) -> dict:
        connection=self.sessions.service.store.database()
        try:
            current=connection.execute('SELECT * FROM accounts WHERE id=?',(account['id'],)).fetchone()
        finally:
            connection.close()
        if (current is None or current['name']!=account['name'] or current['cc2api_account_id'] is not None
                or current['deleted_at'] is not None or not self.routes(dict(current))):
            raise ValueError('原独立登录账号或节点归属已经变化')
        return dict(current)

    def _parent(self, account: dict, identity: str) -> ExecutionScope | None:
        active=self.sessions.ledger.active(account['id'])
        if not active:
            return None
        if len(active)!=1 or active[0]['record']['work'].get('kind')!='credential-refresh':
            raise RuntimeBusy('账号还有原节点工作，需要先实际释放')
        row=active[0]
        scope=ExecutionScope.model_validate(row['record']['scope'])
        work=CredentialRefreshWork.model_validate(row['record']['work'])
        if scope.gateway_account_id is not None or work.account_identity!=identity:
            raise ValueError('原RT维护与当前独立账号身份不一致')
        receipt=self.sessions._call(row,'credential-refresh-get',scope.model_dump())
        self.credentials._check(scope,receipt)
        if receipt['phase']!='closed':
            receipt=self.sessions._call(row,'credential-refresh-stop',scope.model_dump())
            self.credentials._check(scope,receipt)
        if receipt['phase']!='closed':
            raise RuntimeBusy('原RT维护尚未实际停止')
        outcome=receipt.get('outcome') or {}
        known=(outcome.get('status') in ('complete','unsubmitted') or outcome.get('status')=='failed'
            and type(outcome.get('http_status')) is int and 400<=outcome['http_status']<500)
        if known:
            self.credentials._finish(scope,receipt)
            return None
        self.sessions._save(scope.operation_id,'reconcile',node_receipt=receipt,failure='credential_refresh_unconfirmed')
        return scope

    def start(self, account: dict, sid: str, version: str, *, ttl: int = 1800, owner_locked: bool = False) -> dict:
        """冻结一次明确登录，仅关联实际已停止的原RT维护。

        :param account: 已存在的独立账号。
        :param sid: 原中央登录SID。
        :param version: 实际选择的冻结CLI版本。
        :param ttl: 原登录授权有效秒数。
        :param owner_locked: 调用方已持有原不可重入owner锁。
        :return: 原中央具体登录记录。
        """
        with nullcontext() if owner_locked else self.owner_lock(account['name']):
            with self.lock:
                if self.closing:
                    raise RuntimeBusy('节点登录服务正在关闭')
            if type(ttl) is not int or not 1<=ttl<=86400:
                raise ValueError('原登录授权时长无效')
            account=self._account(account)
            identity=self.credentials.identity(account)
            parent=self._parent(account,identity)
            if self.admission is not None:
                self.admission(account,sid,parent)
            state=self.credentials.ownership.state(account['id']) if self.credentials.ownership else None
            if parent is not None or state and (state.get('refresh_pending') or state.get('retired')):
                # 先确认选定版本有实际设备来源，避免新HOME保存后才发现无法解除原隔离。
                self.credentials.read_identity(account,version)
            if self.credentials.ownership:
                self.credentials.ownership.guard(account,'login:'+sid)
            self.sessions.service.prepare_remote_login(account,self.sessions.runtime,self.sessions.gateway,identity,sid)
            assignment=self.sessions.service.store.assignment(account['id'])
            actual=self.sessions.runtime._row(account['name'],account['id'])
            work=AccountLoginWork(id=uuid4().hex,sid=sid,account_id=account['id'],account_identity=identity,
                version=version,expires_at=int(time.time())+ttl,refresh_scope=parent)
            scope=ExecutionScope(operation_id=work.id,node_key=assignment['node_key'],account_id=account['id'],
                environment_id=actual['environment_id'],assignment_revision=assignment['revision'],generation=actual['generation'],
                source=work.source,role='login')
            request=AccountLoginStart(scope=scope,work=work)
            row=self.sessions.ledger.begin(scope,work,require_new=True)
            try:
                activity=self.sessions.activity_gate.reserve('remote-login:'+scope.source)
                with self.sessions.lock:
                    self.sessions.activities[scope.operation_id]=activity
                others=[current for current in self.sessions.ledger.active(account['id']) if current['operation_id']!=work.id]
                if any(parent is None or current['record']['scope']!=parent.model_dump()
                        or (current['record'].get('node_receipt') or {}).get('phase')!='closed' for current in others):
                    raise RuntimeBusy('登录准备期间账号取得了其它工作')
                grant=ExecutionGrant(**scope.model_dump(),not_after=min(int(time.time())+30,work.expires_at))
                row=self.sessions._save(work.id,'claimed',local_admission_intent=True,grant=grant.model_dump())
                prepared=self.sessions._call(row,'grant-create',grant.model_dump())
                if prepared.get('phase')!='prepared' or prepared.get('grant')!=grant.model_dump():
                    raise ValueError('原Node登录准备证明需要核对')
                row=self.sessions._save(work.id,'starting')
                receipt=self._call(row,'start',request.model_dump())
                self._check(scope,receipt)
                row=self.sessions._save(work.id,'running' if receipt['phase']=='ready' else None,node_receipt=receipt)
                self._watch(work.id)
                return row
            except Exception:
                current=self.sessions.ledger.get(work.id)
                if current['record']['grant'] is None:
                    self.sessions._save(work.id,'closed',failure='central_not_started')
                    self.sessions._release_activity(work.id)
                else:
                    self.sessions._isolate(work.id,'account_login_unconfirmed')
                raise

    @staticmethod
    def _check(scope: ExecutionScope, receipt: dict) -> None:
        if (not isinstance(receipt,dict) or type(receipt.get('protocol')) is not int or receipt['protocol']!=1
                or receipt.get('scope')!=scope.model_dump() or receipt.get('phase') not in ('starting','ready','reconcile','closed')):
            raise ValueError('原Node登录回执与完整Scope不一致')

    def _renew(self, operation_id: str) -> None:
        with self.sessions._operation_lock(operation_id):
            row=self.sessions.ledger.admit(operation_id)
            request=AccountLoginStart(scope=ExecutionScope.model_validate(row['record']['scope']),work=AccountLoginWork.model_validate(row['record']['work']))
            old=ExecutionGrant.model_validate(row['record']['grant'])
            now=time.time()
            if old.not_after<=now or request.work.expires_at<=now:
                raise RuntimeBusy('原登录执行许可已过期，等待原操作核对')
            grant=old.model_copy(update={'sequence':old.sequence+1,'not_after':min(int(now)+30,request.work.expires_at)})
            row=self.sessions._save(operation_id,grant=grant.model_dump())
            value=self.sessions._call(row,'grant-renew',grant.model_dump())
            if value.get('phase') not in ('prepared','active') or value.get('grant')!=grant.model_dump():
                raise ValueError('原Node登录证明续接需要核对')

    def _watch(self, operation_id: str) -> None:
        event=threading.Event()
        def observe() -> None:
            renew_at=time.monotonic()+5
            try:
                while not event.wait(.5):
                    row,request=self._row(operation_id)
                    if row['phase'] in ('closed','reconcile','stopping'):
                        return
                    receipt=self._call(row,'get',request.scope.model_dump())
                    self._check(request.scope,receipt)
                    if receipt['phase']=='reconcile':
                        raise ValueError('原Node登录等待实际作业核对')
                    if receipt['phase']=='closed':
                        if receipt.get('commit') is None:
                            self.cancel(operation_id)
                        return
                    if row['phase']=='starting' and receipt['phase']=='ready':
                        self.sessions._save(operation_id,'running',node_receipt=receipt)
                    if request.work.expires_at<=time.time():
                        with self.lock:
                            committing=operation_id in self.committing
                        if not committing and receipt.get('commit') is None:
                            self.cancel(operation_id)
                        return
                    if time.monotonic()>=renew_at:
                        self._renew(operation_id)
                        renew_at=time.monotonic()+5
            except Exception:
                with self.lock:
                    finishing=operation_id in self.committing or self.closing
                if not finishing:
                    self.sessions._isolate(operation_id,'account_login_unconfirmed')
            finally:
                with self.lock:
                    self.workers.pop(operation_id,None)
        worker=threading.Thread(target=observe,daemon=True,name='remote-account-login')
        with self.lock:
            self.workers[operation_id]=(event,worker)
        worker.start()

    def _stop_watch(self, operation_id: str) -> None:
        with self.lock:
            value=self.workers.get(operation_id)
        if value:
            event,worker=value
            event.set()
            if worker is not threading.current_thread():
                worker.join(timeout=5)

    def status(self, operation_id: str) -> dict:
        """查询原登录阶段，普通读取不创建CLI或重发输入。

        :param operation_id: 原操作ID。
        :return: 无秘密状态与原授权链接。
        """
        row,request=self._row(operation_id)
        if row['phase']=='closed':
            commit=(row['record'].get('node_receipt') or {}).get('commit') or {}
            complete=commit.get('stage')=='accepted' and commit.get('cleanup_pending') is False
            return {'phase':'committed' if complete else 'ended','credentials_ready':complete,'reconnectable':False,
                'authorization_url':None,'expires_at':request.work.expires_at}
        receipt=self._call(row,'get',request.scope.model_dump())
        self._check(request.scope,receipt)
        commit=receipt.get('commit')
        if commit is not None:
            # Node完成只代表本机产物已收口；中央真实租约与长期所有权仍由原账本确认。
            return {'phase':'ended' if commit.get('aborted',False) else 'submitting',
                'credentials_ready':not commit.get('aborted',False),'reconnectable':False,
                'authorization_url':None,'expires_at':request.work.expires_at}
        if receipt['phase']=='starting':
            return {'phase':'preparing','credentials_ready':False,'reconnectable':True,
                'authorization_url':None,'expires_at':request.work.expires_at}
        return self._call(row,'observe',request.scope.model_dump())

    def code(self, operation_id: str, request_id: str, code: str) -> dict:
        """向同一Scope投递一次授权码，失败后由调用方查询原回执。

        :param operation_id: 原登录操作。
        :param request_id: 原单次输入ID。
        :param code: 原码，只用于本次私有stdin载荷。
        :return: 原固定投递回执。
        """
        row,request=self._row(operation_id)
        self.sessions.ledger.admit(operation_id)
        return self._call(row,'code',AccountLoginCode(scope=request.scope,request_id=request_id,code=code).model_dump())

    def code_receipt(self, operation_id: str, request_id: str) -> dict:
        """只读原输入回执。

        :param operation_id: 原登录操作。
        :param request_id: 原单次输入。
        :return: 原回执；不触发授权码投递。
        """
        row,request=self._row(operation_id)
        return self._call(row,'code-receipt',AccountLoginCodeRead(scope=request.scope,request_id=request_id).model_dump())

    def open(self, operation_id: str) -> RemoteContinuePty:
        """连接原登录tmux，节点逐片核对有限证明与一次输入回执。

        :param operation_id: 原登录操作。
        :return: 保持原输出socket接口的受限PTY桥。
        """
        row,_=self._row(operation_id)
        self.sessions.ledger.admit(operation_id)
        deadline=time.monotonic()+30
        while True:
            row,request=self._row(operation_id)
            self.sessions.ledger.admit(operation_id)
            receipt=self._call(row,'get',request.scope.model_dump())
            self._check(request.scope,receipt)
            if receipt['phase']=='ready':
                break
            if receipt['phase']!='starting' or time.monotonic()>=deadline:
                raise RuntimeBusy('原节点登录仍在准备或需要核对，请刷新状态后重连')
            time.sleep(.2)
        return RemoteContinuePty(self,row,purpose=self.pty_purpose)

    def _snapshot(self, row: dict, request: AccountLoginStart, receipt: dict) -> dict:
        value=self._call(row,'snapshot',request.scope.model_dump())
        try:
            snapshot=AccountLoginSnapshot.model_validate(value)
        except (ValueError,TypeError):
            raise ValueError('原Node新授权快照需要核对') from None
        commit=receipt.get('commit') or {}
        if (snapshot.scope!=request.scope or snapshot.version!=request.work.version
                or snapshot.authorization_sha256!=commit.get('authorization_sha256')):
            raise ValueError('原Node新授权快照来源需要核对')
        material=snapshot.material.model_dump()
        if hashlib.sha256(material['refresh_token'].encode()).hexdigest()!=commit.get('refresh_sha256'):
            raise ValueError('原Node新授权RT摘要不一致')
        return snapshot.model_dump()

    def commit(self, operation_id: str, *, owner_locked: bool = False) -> dict:
        """保存同一授权和原证明后，确认Node实际停止与清理，再释放旧隔离。

        :param operation_id: 原明确登录。
        :param owner_locked: 原产品提交入口已持有owner锁。
        :return: 固定无秘密完成结果；未知保留原工作和材料。
        """
        row,request=self._row(operation_id)
        if row['phase']=='closed':
            return self.result(operation_id)
        account=self.sessions._account(request.scope,available=False)
        with nullcontext() if owner_locked else self.owner_lock(account['name']):
            row,request=self._row(operation_id)
            if row['phase']=='closed':
                return self.result(operation_id)
            with self.lock:
                self.committing.add(operation_id)
            try:
                self.sessions.ledger._check_assignment(row,request.scope)
                if self.admission is not None:
                    self.admission(account,request.work.sid,request.work.refresh_scope)
                receipt=self._call(row,'commit',request.scope.model_dump())
                self._check(request.scope,receipt)
                if (receipt.get('commit') or {}).get('stage') not in ('saved','accepted'):
                    raise ValueError('原Node新授权尚未完成保存')
                row=self.sessions._save(operation_id,node_receipt=receipt)
                snapshot=self._snapshot(row,request,receipt)
                self.save_authorization(account,snapshot,request.work.version)
                self._stop_watch(operation_id)
                accepted=AccountLoginAccept(scope=request.scope,authorization_sha256=snapshot['authorization_sha256'])
                receipt=self._call(row,'accept',accepted.model_dump())
                self._check(request.scope,receipt)
                if receipt['phase']!='closed' or (receipt.get('commit') or {}).get('cleanup_pending') is not False:
                    raise ValueError('原Node登录终端或暂存尚未实际清理')
                self.sessions._save(operation_id,'stopping',node_receipt=receipt)
                parent=request.work.refresh_scope
                if parent is not None:
                    old=self.sessions.ledger.get(parent.operation_id)
                    if old['phase']!='closed':
                        if old['record']['scope']!=parent.model_dump() or (old['record'].get('node_receipt') or {}).get('phase')!='closed':
                            raise ValueError('原RT父维护的实际停止需要核对')
                        self.sessions._save(parent.operation_id,'stopping')
                        self.sessions._save(parent.operation_id,'closed',local_admission_released=True,failure='superseded_by_new_authorization')
                        self.sessions._release_activity(parent.operation_id)
                self.sessions._save(operation_id,'closed',local_admission_released=True)
                self.sessions._release_activity(operation_id)
                return self.result(operation_id)
            except Exception:
                if self.sessions.ledger.get(operation_id)['phase']!='closed':
                    self.sessions._isolate(operation_id,'account_login_commit_unconfirmed')
                raise
            finally:
                with self.lock:
                    self.committing.discard(operation_id)

    def result(self, operation_id: str) -> dict:
        """读取已完成原操作的固定结果。

        :param operation_id: 原登录操作。
        :return: 账号、原认证方式与明确的独立保存状态。
        """
        row,request=self._row(operation_id)
        commit=(row['record'].get('node_receipt') or {}).get('commit') or {}
        if row['phase']!='closed' or commit.get('stage')!='accepted' or commit.get('cleanup_pending') is not False:
            raise ValueError('原登录尚未完整完成')
        connection=self.sessions.service.store.database()
        try:
            account=connection.execute('SELECT name FROM accounts WHERE id=?',(request.scope.account_id,)).fetchone()
        finally:
            connection.close()
        if account is None:
            raise ValueError('原已保存账号需要核对')
        return {'id':request.scope.account_id,'name':account['name'],'auth_method':commit.get('auth_method'),
            'cc2api_account_id':None,'credentials_synced':False}

    def cancel(self, operation_id: str, *, owner_locked: bool = False) -> None:
        """停止并清理无提交意图的原登录，未知RT父来源继续隔离。

        :param operation_id: 原登录操作。
        :param owner_locked: 调用方已持有原owner锁。
        :return: None；提交待确认时保留原材料。
        """
        row,request=self._row(operation_id)
        if row['phase']=='closed':
            return
        account=self.sessions._account(request.scope,available=False)
        with nullcontext() if owner_locked else self.owner_lock(account['name']):
            self._stop_watch(operation_id)
            row,request=self._row(operation_id)
            if row['phase']=='closed':
                return
            try:
                receipt=self._call(row,'stop',request.scope.model_dump())
                self._check(request.scope,receipt)
                receipt=self._call(row,'discard',request.scope.model_dump())
                if receipt.get('phase')!='closed' or receipt.get('discarded') is not True:
                    raise ValueError('原Node登录暂存清理仍需核对')
                self.sessions._save(operation_id,'stopping',node_receipt=receipt)
                self.sessions._save(operation_id,'closed',local_admission_released=True)
                self.sessions._release_activity(operation_id)
            except Exception:
                self.sessions._isolate(operation_id,'account_login_cleanup_unconfirmed')
                raise

    def recover_pending(self) -> None:
        """恢复原明确提交或停止旧交互，原授权码与CLI启动都不重放。

        :return: None；单账号未知继续隔离，其他账号继续核对。
        """
        for operation_id in self.sessions.ledger.pending():
            row=self.sessions.ledger.get(operation_id)
            if row['record']['work'].get('kind')!='account-login':
                continue
            with self.lock:
                if self.closing or operation_id in self.workers or operation_id in self.committing:
                    continue
            row,request=self._row(operation_id)
            account=self.sessions._account(request.scope,available=False)
            guard=self.owner_lock(account['name'])
            if not guard.acquire(blocking=False):
                continue
            try:
                row,request=self._row(operation_id)
                if row['phase']=='closed':
                    continue
                if row['record']['grant'] is None:
                    self.sessions._save(operation_id,'closed',failure='central_not_started')
                    self.sessions._release_activity(operation_id)
                    continue
                try:
                    receipt=self._call(row,'get',request.scope.model_dump())
                except Exception:
                    receipt=self._call(row,'stop',request.scope.model_dump())
                self._check(request.scope,receipt)
                if receipt.get('commit') is not None:
                    self.commit(operation_id,owner_locked=True)
                else:
                    self.cancel(operation_id,owner_locked=True)
            except Exception:
                self.sessions._isolate(operation_id,'account_login_recovery_unconfirmed')
            finally:
                guard.release()

    def close(self) -> None:
        """关闭新操作和本进程续接，原持久来源交给恢复核对。

        :return: None。
        """
        with self.lock:
            self.closing=True
            workers=list(self.workers.values())
        for event,_ in workers:
            event.set()
        for _,worker in workers:
            if worker is not threading.current_thread():
                worker.join(timeout=5)
