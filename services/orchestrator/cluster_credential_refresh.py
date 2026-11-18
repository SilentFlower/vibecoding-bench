"""中央独立凭据维护协调，只查询和收口已提交的原刷新操作。"""
from __future__ import annotations

import threading
import time
import hashlib
import math
import json
from contextlib import nullcontext
from uuid import uuid4

from account_runtime import CLI_CONFIG_IDENTITY_SOURCES, CLI_REQUEST_IDENTITY_SOURCE, RuntimeBusy
from cluster_credentials_contract import CredentialIdentityImport, CredentialMaterial, CredentialRefreshStart, CredentialRefreshWork, CredentialStatusRead, CredentialUsageStart, CredentialUsageWork, credential_start
from cluster_deployment import node_container_name
from cluster_execution_grants import ExecutionGrant, ExecutionScope
from cluster_runs import RunWork
from oauth_status import oauth_expiry_status


class RemoteCredentialRefresh:
    """复用原中央账本、所有权和SSH通道的具体维护协调器。

    :param sessions: 原中央执行账本及私有节点通道。
    :param ownership: 原CredentialOwnership，旧独立账号可为None。
    :param owner_lock: 原账号OAuth所有者锁工厂。
    :param identity: 原稳定账号身份读取。
    :param version: 原实际CLI版本解析。
    """

    def __init__(self, sessions, ownership, owner_lock, identity, version) -> None:
        """登记原依赖并标记本进程正在观察的操作。

        :param sessions: 原中央执行协调。
        :param ownership: 原凭据所有者。
        :param owner_lock: 原所有者锁。
        :param identity: 原稳定身份。
        :param version: 原版本解析。
        :return: None。
        """
        self.sessions,self.ownership,self.owner_lock,self.identity,self.version=sessions,ownership,owner_lock,identity,version
        self.lock,self.inflight=threading.RLock(),set()
        self.closing=False
        self.reviewing=set()
        self.observations={}

    def _status_request(self, account: dict) -> tuple[CredentialStatusRead,dict,str]:
        assignment=self.sessions.service.store.assignment(account['id'])
        if assignment['kind']!='ssh' or assignment['phase']!='ready' or account.get('cc2api_account_id') is not None:
            raise ValueError('原独立账号节点归属正在变化')
        actual=self.sessions.runtime._row(account['name'],account['id'])
        request=CredentialStatusRead(node_key=assignment['node_key'],account_id=account['id'],
            environment_id=actual['environment_id'],assignment_revision=assignment['revision'],generation=actual['generation'],
            account_identity=self.identity(account),version=self.version(account))
        node=self.sessions.service.store.get(assignment['node_id'])
        key=request.model_dump_json()+hashlib.sha256(node['config_json'].encode()).hexdigest()
        return request,assignment,key

    def _owner_read(self, account: dict, operation: str, *, version: str | None = None) -> tuple[dict,CredentialStatusRead]:
        if operation not in ('credential-material','credential-identity','credential-identity-import'):
            raise ValueError('原所有者只读操作无效')
        request,assignment,key=self._status_request(account)
        if version is not None:
            request=CredentialStatusRead.model_validate({**request.model_dump(),'version':version})
        response=self.sessions.service.connection(assignment['node_id']).execution_environment(
            node_container_name(self.sessions.runtime.deployment,request.node_key),request.model_dump(),operation)
        value=response.get('credentials')
        field={'credential-material':'material','credential-identity':'identity','credential-identity-import':'imported_identity'}[operation]
        try:
            returned=CredentialStatusRead.model_validate({name:value[name] for name in type(request).model_fields})
        except (ValueError,TypeError,KeyError):
            raise ValueError('原Node所有者资料范围需要核对') from None
        if (type(response.get('protocol')) is not int or response['protocol']!=1 or response.get('node_key')!=request.node_key
                or not isinstance(value,dict) or set(value)!={'protocol',*type(request).model_fields,field}
                or type(value.get('protocol')) is not int or value['protocol']!=1
                or returned!=request
                or self._status_request(account)[2]!=key):
            raise ValueError('原Node所有者资料的归属或代次需要核对')
        return value[field],request

    def read_material(self, account: dict) -> dict:
        """只供原owner锁内的受信凭据流程读取当前Node材料。

        :param account: 当前独立账号。
        :return: 已校验的当前AT/RT/到期值；不写入缓存或回执。
        """
        value,_=self._owner_read(account,'credential-material')
        try:
            return CredentialMaterial.model_validate(value).model_dump()
        except (ValueError,TypeError):
            raise ValueError('原Node当前凭据材料需要核对') from None

    def read_identity(self, account: dict, version: str | None = None) -> dict:
        """读取原Node实际CLI身份来源，冻结版本不随之后的默认设置变化。

        :param account: 当前独立账号。
        :param version: 原登录的实际版本；空时取账号当前版本。
        :return: 无凭据设备/账号/环境与已验证来源。
        """
        value,request=self._owner_read(account,'credential-identity',version=version)
        identity=json.loads(request.account_identity)
        if (not isinstance(identity,dict) or identity.get('account_id')!=request.account_id or identity.get('binding') is not None
                or not isinstance(identity.get('uuid'),str) or not identity['uuid']):
            raise ValueError('原独立账号稳定身份需要核对')
        sources={CLI_REQUEST_IDENTITY_SOURCE}
        configured=CLI_CONFIG_IDENTITY_SOURCES.get(request.version)
        if configured:
            sources.add(configured)
        if (not isinstance(value,dict) or set(value)!={'device_id','account_uuid','source','environment_id'}
                or not isinstance(value.get('device_id'),str) or len(value['device_id'])!=64
                or any(character not in 'abcdef0123456789' for character in value['device_id'])
                or value.get('account_uuid')!=identity.get('uuid') or not isinstance(value.get('source'),str) or value['source'] not in sources
                or value.get('environment_id')!=request.environment_id):
            raise ValueError('原Node当前CLI身份或已验证版本来源需要核对')
        return value

    def identity_import(self, account: dict) -> dict:
        """原owner锁内准备所属CLI并读取完整Gateway创建身份。

        :param account: 当前独立账号。
        :return: 原Node实测环境及设备载荷。
        """
        sessions=self.sessions
        sessions.service.prepare_remote_cli(account,sessions.runtime,sessions.gateway,self.identity(account))
        value,request=self._owner_read(account,'credential-identity-import')
        imported=CredentialIdentityImport.model_validate(value)
        if imported.environment_id!=request.environment_id:
            raise ValueError('原Node完整身份的环境范围已经变化')
        return imported.model_dump()

    def status(self, account: dict, *, observe: bool = False) -> dict:
        """按完整归属读取有界缓存，明确观察时才调用Node只读操作。

        :param account: 原独立账号行。
        :param observe: 原调度器或手动入口是否核对当前Node。
        :return: 公开状态、真实观察时间及固定来源；失效或失败显示unknown。
        """
        unknown={**oauth_expiry_status(None,token_state='unknown'),
            'oauth_status_source':'node-home','oauth_observed_at':None}
        try:
            request,assignment,key=self._status_request(account)
        except Exception:
            return unknown
        if observe:
            try:
                response=self.sessions.service.connection(assignment['node_id']).execution_environment(
                    node_container_name(self.sessions.runtime.deployment,request.node_key),request.model_dump(),'credential-status')
                value=response.get('credentials')
                now=time.time()
                observed=value.get('observed_at') if isinstance(value,dict) else None
                if (type(response.get('protocol')) is not int or response['protocol']!=1
                        or response.get('node_key')!=request.node_key or not isinstance(value,dict)
                        or set(value)!={'protocol',*type(request).model_fields,'observed_at','status'} or value.get('protocol')!=1
                        or any(value.get(field)!=expected for field,expected in request.model_dump().items())
                        or type(observed) not in (int,float) or not math.isfinite(observed) or not now-120<=observed<=now+60):
                    raise ValueError('原Node凭据观察范围或时间需要核对')
                if CredentialStatusRead.model_validate({field:value[field] for field in type(request).model_fields})!=request:
                    raise ValueError('原Node观察定位字段需要核对')
                state=value['status']
                if not isinstance(state,dict) or state.get('oauth_token_state') not in ('valid','expiring','expired','missing','invalid','unknown'):
                    raise ValueError('原Node凭据状态需要核对')
                expected=oauth_expiry_status(state.get('oauth_expires_at_ms'),token_state=state['oauth_token_state'],now=observed)
                # 由Node生成四字段并在中央重算，防止异常字段夹带凭据或伪造剩余时间。
                if state!=expected or self._status_request(account)[2]!=key:
                    raise ValueError('原Node观察内容或当前账号归属已经变化')
                cached={'expires_at':state['oauth_expires_at_ms'],'state':state['oauth_token_state'],
                    'observed_at':observed,'received_at':time.monotonic()}
            except Exception:
                with self.lock:
                    self.observations.pop(account['id'],None)
                return unknown
            with self.lock:
                self.observations[account['id']]=(key,cached)
                if len(self.observations)>4096:
                    self.observations.pop(next(iter(self.observations)))
        with self.lock:
            cached_key,cached=self.observations.get(account['id'],(None,None))
        if (cached is None or cached_key!=key or not 0<=time.monotonic()-cached['received_at']<=120
                or not -60<=time.time()-cached['observed_at']<=120):
            return unknown
        return {**oauth_expiry_status(cached['expires_at'],token_state=cached['state']),
            'oauth_status_source':'node-home','oauth_observed_at':cached['observed_at']}

    def refresh(self, account: dict, *, force_refresh: bool = False, refresh_buffer_sec: int = 600,
                owner_locked: bool = False) -> bool:
        """在原Node当前HOME发起一次具体独立刷新。

        :param account: 原独立账号，仅用于重新读取当前中央行。
        :param force_refresh: 原401是否要求忽略有效期缓冲。
        :param refresh_buffer_sec: 原调用方缓冲。
        :param owner_locked: 原Runner入口的调用方已持有不可重入owner锁。
        :return: 实际发生刷新时True，有效凭据跳过时False。
        """
        sessions=self.sessions
        with nullcontext() if owner_locked else self.owner_lock(account['name']):
            connection=sessions.service.store.database()
            try:
                stored=connection.execute('SELECT * FROM accounts WHERE id=?',(account['id'],)).fetchone()
            finally:
                connection.close()
            if (stored is None or stored['name']!=account['name'] or stored['cc2api_account_id'] is not None
                    or not stored['enabled'] or stored['deleted_at'] is not None):
                raise ValueError('原独立刷新账号或绑定已经变化')
            account=dict(stored)
            with self.lock:
                if self.closing:
                    raise RuntimeBusy('节点凭据维护服务正在关闭')
            if self.ownership:
                self.ownership.guard(account)
            if sessions.ledger.active(account['id']):
                raise RuntimeBusy('等待原节点工作实际释放后刷新凭据')
            identity=self.identity(account)
            sessions.service.prepare_remote_cli(account,sessions.runtime,sessions.gateway,identity)
            assignment=sessions.service.store.assignment(account['id'])
            if assignment['kind']!='ssh' or assignment['phase']!='ready':
                raise ValueError('原独立账号的节点归属已经变化')
            actual=sessions.runtime._row(account['name'],account['id'])
            work=CredentialRefreshWork(id=uuid4().hex,account_id=account['id'],account_identity=identity,
                version=self.version(account),force_refresh=force_refresh,refresh_buffer_sec=refresh_buffer_sec)
            scope=ExecutionScope(operation_id=work.id,node_key=assignment['node_key'],account_id=account['id'],
                environment_id=actual['environment_id'],assignment_revision=assignment['revision'],generation=actual['generation'],
                source=work.source,role='login')
            request=CredentialRefreshStart(scope=scope,work=work)
            row=sessions.ledger.begin(scope,work,require_new=True)
            refreshed=self._execute(request,row,account)
            self.status(account,observe=True)
            return refreshed

    def query_usage(self, account: dict, *, owner_locked: bool = False) -> dict:
        """在原Node查询一次当前HOME的usage，沿原owner锁串行凭据准备。

        :param account: 原账号行，执行前重新读取。
        :param owner_locked: 原HTTP额度入口已经持有不可重入owner锁。
        :return: 实际一次usage结果，错误保留原结构化门禁语义。
        """
        sessions=self.sessions
        with nullcontext() if owner_locked else self.owner_lock(account['name']):
            connection=sessions.service.store.database()
            try:
                stored=connection.execute('SELECT * FROM accounts WHERE id=?',(account['id'],)).fetchone()
            finally:
                connection.close()
            if (stored is None or stored['name']!=account['name'] or stored['cc2api_account_id'] is not None
                    or not stored['enabled'] or stored['deleted_at'] is not None):
                raise ValueError('原独立额度查询账号或绑定已经变化')
            account=dict(stored)
            with self.lock:
                if self.closing:
                    raise RuntimeBusy('节点额度查询正在关闭')
            if self.ownership:
                self.ownership.guard(account)
            if sessions.ledger.active(account['id']):
                raise RuntimeBusy('等待原节点CLI工作释放后查询额度')
            identity=self.identity(account)
            sessions.service.prepare_remote_cli(account,sessions.runtime,sessions.gateway,identity)
            state=self.status(account,observe=True)['oauth_token_state']
            if state in ('expired','expiring'):
                self.refresh(account,owner_locked=True)
            elif state in ('unknown','invalid','missing'):
                raise ValueError('所属节点当前HOME凭据需要核对后查询额度')
            assignment=sessions.service.store.assignment(account['id'])
            if assignment['kind']!='ssh' or assignment['phase']!='ready':
                raise ValueError('原独立账号的节点归属已经变化')
            actual=sessions.runtime._row(account['name'],account['id'])
            work=CredentialUsageWork(id=uuid4().hex,account_id=account['id'],account_identity=identity,version=self.version(account))
            scope=ExecutionScope(operation_id=work.id,node_key=assignment['node_key'],account_id=account['id'],
                environment_id=actual['environment_id'],assignment_revision=assignment['revision'],generation=actual['generation'],
                source=work.source,role='login')
            request=CredentialUsageStart(scope=scope,work=work)
            row=sessions.ledger.begin(scope,work,require_new=True)
            return self._execute(request,row,account)

    def _register_review(self, parent: dict, account: dict, attempt: int) -> dict:
        original=RunWork.model_validate(parent['record']['work'])
        scope=ExecutionScope.model_validate(parent['record']['scope'])
        identity=self.identity(account)
        if (scope.account_id!=account['id'] or scope.gateway_account_id is not None
                or original.project is None or original.project.scenario is None or original.project.scenario.review is None
                or identity!=parent['record']['quota_identity'] or not 0<=attempt<2):
            raise ValueError('原私有评审刷新来源或身份已变化')
        operation=hashlib.sha256(f'node-owner-refresh:{scope.operation_id}:{attempt}'.encode()).hexdigest()[:32]
        work=CredentialRefreshWork(id=operation,account_id=account['id'],account_identity=identity,
            version=original.worker_env['CLAUDE_CODE_VERSION'],force_refresh=True,review_scope=scope,
            review_request_id=hashlib.sha256(scope.source.encode()).hexdigest())
        current=scope.model_copy(update={'operation_id':operation,'role':'login','source':work.source})
        row=self.sessions.ledger.begin(current,work)
        if row['phase']!='closed':
            with self.sessions.lock:
                activity=self.sessions.activities.get(current.operation_id)
            if activity is None:
                activity=self.sessions.activity_gate.reserve('remote-credentials:'+current.source)
                with self.sessions.lock:
                    self.sessions.activities[current.operation_id]=activity
        return row

    def defer_review(self, parent: dict, request_sha256: str) -> None:
        """先确认原Node401待办，再登记中央维护并调度原评审释放。

        :param parent: 原实际私有评审行。
        :param request_sha256: 原worker单次401请求摘要。
        :return: None；任何未知步骤保留原Node待办和中央活动。
        """
        scope=ExecutionScope.model_validate(parent['record']['scope'])
        value=self.sessions._call(parent,'run-owner-refresh-defer',{'scope':scope.model_dump(),'request_sha256':request_sha256})
        expected={'protocol':1,'scope':scope.model_dump(),'request_sha256':request_sha256,'phase':'deferred',
            'request_id':hashlib.sha256(scope.source.encode()).hexdigest()}
        if value!=expected:
            raise ValueError('原Node401待办确认需要核对')
        account=self.sessions._account(scope)
        with self.owner_lock(account['name']):
            self._register_review(parent,account,0)
        self.retry_review(account)

    def retry_review(self, account: dict) -> bool:
        """读取所属Node原待办，原评审严格释放后异步执行同一维护。

        :param account: 当前原账号。
        :return: 是否仍在等待原Node所有者处理。
        """
        with self.lock:
            if self.closing:
                return False
            if account['id'] in self.reviewing:
                return True
        connection=self.sessions.service.store.database()
        try:
            saved=connection.execute('SELECT * FROM account_environments WHERE account_id=?',(account['id'],)).fetchone()
        finally:
            connection.close()
        if saved is None:
            return False
        response=self.sessions.service.review_admission(dict(saved),self.sessions.runtime,self.version(account),
            self.identity(account),include_refresh=True)
        pending=response.get('owner_refresh')
        if pending is None or pending['status']=='error':
            return False
        if pending['not_before']>time.time():
            return True
        parent=self.sessions.ledger.by_source(account['id'],pending['source'],active_only=False)
        if parent is None or pending['request_id']!=hashlib.sha256(parent['source'].encode()).hexdigest():
            raise ValueError('原Node401待办缺少对应的中央评审来源')
        with self.owner_lock(account['name']):
            row=self._register_review(parent,account,pending['attempts'])
        if row['phase']=='closed':
            return False
        with self.lock:
            if self.closing or account['id'] in self.reviewing:
                return True
            self.reviewing.add(account['id'])
        def process() -> None:
            try:
                if self.sessions.ledger.get(parent['operation_id'])['phase']!='closed':
                    self.sessions.stop(parent['operation_id'])
                with self.owner_lock(account['name']):
                    current=self.sessions.ledger.get(row['operation_id'])
                    if current['phase']=='closed' or current['record']['grant'] is not None:
                        return
                    scope=ExecutionScope.model_validate(current['record']['scope'])
                    actual=self.sessions._account(scope)
                    if self.identity(actual)!=current['record']['work']['account_identity']:
                        raise ValueError('原评审凭据维护身份已变化')
                    request=CredentialRefreshStart(scope=scope,work=CredentialRefreshWork.model_validate(current['record']['work']))
                    self._execute(request,current,actual)
            except Exception:
                # 原具体账本及Node待办承担恢复；线程异常不重建另一刷新来源。
                pass
            finally:
                with self.lock:
                    self.reviewing.discard(account['id'])
        threading.Thread(target=process,name='remote-review-owner-refresh',daemon=True).start()
        return True

    def _execute(self, request: CredentialRefreshStart | CredentialUsageStart, row: dict, account: dict) -> bool | dict:
        """沿已冻结原工作登记许可并观察一次提交。

        :param request: 原具体凭据工作。
        :param row: 原中央preparing记录。
        :param account: 已在原owner锁内重读的账号。
        :return: 实际刷新结论或本次usage对象。
        """
        sessions,scope=self.sessions,request.scope
        usage=isinstance(request,CredentialUsageStart)
        operation='credential-usage-' if usage else 'credential-refresh-'
        with self.lock:
            self.inflight.add(scope.operation_id)
            if not usage:
                self.observations.pop(scope.account_id,None)
        try:
            with self.lock:
                if self.closing:
                    raise RuntimeBusy('节点凭据维护服务正在关闭新操作')
            with sessions.lock:
                activity=sessions.activities.get(scope.operation_id)
            if activity is None:
                activity=sessions.activity_gate.reserve('remote-credentials:'+scope.source)
                with sessions.lock:
                    sessions.activities[scope.operation_id]=activity
            if any(item['operation_id']!=scope.operation_id for item in sessions.ledger.active(account['id'])):
                raise RuntimeBusy('账号在刷新准备期间取得了其他执行，等待原工作释放')
            if self.ownership and not usage:
                state=self.ownership.state(account['id'])
                if state and state.get('refresh_pending') and state.get('refresh_source')==scope.source:
                    if state['owner']!='local' or state['phase']!='reconcile':
                        raise ValueError('原独立凭据维护所有者已变化')
                else:
                    self.ownership.begin_local_refresh(account['id'],scope.source)
            grant=ExecutionGrant(**scope.model_dump(),not_after=int(time.time())+30)
            row=sessions._save(scope.operation_id,'claimed',local_admission_intent=True,grant=grant.model_dump())
            prepared=sessions._call(row,'grant-create',grant.model_dump())
            if prepared.get('phase')!='prepared' or prepared.get('grant')!=grant.model_dump():
                raise ValueError('节点原凭据维护证明需要核对')
            row=sessions._save(scope.operation_id,'starting')
            with self.lock:
                if self.closing:
                    raise RuntimeBusy('原凭据操作保留准备证明，等待重启核对')
            receipt=sessions._call(row,operation+'start',request.model_dump())
            self._check(scope,receipt)
            sessions._save(scope.operation_id,node_receipt=receipt)
            deadline,renew_at=time.monotonic()+90,time.monotonic()+5
            while receipt['phase']!='closed':
                with self.lock:
                    closing=self.closing
                if closing or time.monotonic()>=deadline:
                    receipt=sessions._call(row,operation+'stop',scope.model_dump())
                    break
                time.sleep(.2)
                receipt=sessions._call(row,operation+'get',scope.model_dump())
                self._check(scope,receipt)
                if receipt['phase']=='reconcile':
                    receipt=sessions._call(row,operation+'stop',scope.model_dump())
                    break
                if receipt['phase']!='closed' and time.monotonic()>=renew_at:
                    try:
                        row=self._renew(row)
                    except Exception:
                        # Node可在查询与续接之间完成；只补读该原结论，保持提交次数不变。
                        receipt=sessions._call(row,operation+'get',scope.model_dump())
                        self._check(scope,receipt)
                        if receipt['phase']!='closed':
                            raise
                    renew_at=time.monotonic()+5
            result=self._finish(scope,receipt)
            if usage:
                return result['usage'] if result.get('status')=='complete' and isinstance(result.get('usage'),dict) else {
                    'error':'所属节点额度查询未完成，请核对本次操作'}
            if result['status']=='complete':
                return result.get('refreshed') is True
            raise ValueError('原节点凭据刷新失败，请查看账号的凭据维护状态')
        except Exception:
            row=sessions.ledger.get(scope.operation_id)
            if row['record']['grant'] is None:
                # 证明检查点先于任何Node请求，故此分支明确尚未使用RT。
                self._finish_owner(scope)
                if usage or request.work.review_scope is None:
                    sessions._save(scope.operation_id,'closed',failure='central_not_started')
                    sessions._release_activity(scope.operation_id)
            elif row['phase']!='closed':
                sessions._isolate(scope.operation_id,'credential_refresh_unconfirmed')
            raise
        finally:
            with self.lock:
                self.inflight.discard(scope.operation_id)

    def _renew(self, row: dict) -> dict:
        scope=ExecutionScope.model_validate(row['record']['scope'])
        with self.sessions._operation_lock(scope.operation_id):
            current=self.sessions.ledger.admit(scope.operation_id)
            old=ExecutionGrant.model_validate(current['record']['grant'])
            if old.not_after<=time.time():
                raise ValueError('原独立凭据维护证明已经过期')
            grant=old.model_copy(update={'sequence':old.sequence+1,'not_after':int(time.time())+30})
            current=self.sessions._save(scope.operation_id,grant=grant.model_dump())
            result=self.sessions._call(current,'grant-renew',grant.model_dump())
            if result.get('grant')!=grant.model_dump() or result.get('phase') not in ('active','prepared'):
                raise ValueError('原节点凭据证明续接结果需要核对')
            return current

    @staticmethod
    def _check(scope: ExecutionScope, receipt: dict) -> None:
        if (receipt.get('protocol')!=1 or receipt.get('scope')!=scope.model_dump()
                or receipt.get('phase') not in ('starting','ready','reconcile','closed')):
            raise ValueError('原节点凭据维护回执身份不一致')

    def _finish_owner(self, scope: ExecutionScope) -> None:
        if self.ownership is None or scope.source=='quota:'+scope.operation_id:
            return
        state=self.ownership.state(scope.account_id)
        if state is None:
            return
        if state.get('refresh_pending') and state.get('refresh_source')==scope.source:
            self.ownership.finish_local_refresh(scope.account_id,scope.source)
        elif state.get('phase')!='ready' or state.get('owner')!='local':
            raise ValueError('原节点凭据维护所有权需要核对')

    def _finish(self, scope: ExecutionScope, receipt: dict) -> dict:
        self._check(scope,receipt)
        outcome=receipt.get('outcome')
        if receipt['phase']!='closed' or not isinstance(outcome,dict):
            raise ValueError('原节点凭据实际停止或结果仍需核对')
        known=(scope.source=='quota:'+scope.operation_id or outcome.get('status') in ('complete','unsubmitted') or outcome.get('status')=='failed'
            and type(outcome.get('http_status')) is int and 400<=outcome['http_status']<500)
        # 实际进程停止仅证明收口；RT提交结果未知时原所有权仍保持隔离。
        self.sessions._save(scope.operation_id,'stopping',node_receipt=receipt)
        if not known:
            raise ValueError('原节点RT刷新结果未知，等待原操作核对或明确重授权')
        self._finish_owner(scope)
        self.sessions._save(scope.operation_id,'closed',local_admission_released=True)
        self.sessions._release_activity(scope.operation_id)
        return outcome

    def recover_pending(self) -> None:
        """复用原后台循环，只查询及实际停止旧凭据工作。

        :return: None；逐账号未知记录继续持有原维护占用。
        """
        sessions=self.sessions
        for operation_id in sessions.ledger.pending():
            row=sessions.ledger.get(operation_id)
            if row['record']['work'].get('kind') not in ('credential-refresh','credential-usage'):
                continue
            with self.lock:
                if self.closing or operation_id in self.inflight:
                    continue
                self.inflight.add(operation_id)
            try:
                scope=ExecutionScope.model_validate(row['record']['scope'])
                account=sessions._account(scope,available=False)
                with self.lock:
                    if account['id'] in self.reviewing:
                        continue
                request=credential_start({'scope':scope.model_dump(),'work':row['record']['work']})
                work=request.work
                usage=isinstance(request,CredentialUsageStart)
                operation='credential-usage-' if usage else 'credential-refresh-'
                if not usage and work.review_scope is not None and sessions.ledger.get(work.review_scope.operation_id)['phase']!='closed':
                    sessions.stop(work.review_scope.operation_id)
                owner_guard=self.owner_lock(account['name'])
                if not owner_guard.acquire(blocking=False):
                    # 一个账号仍在原owner操作中时，其他账号继续使用同一恢复循环。
                    continue
                try:
                    row=sessions.ledger.get(operation_id)
                    if row['phase']=='closed':
                        continue
                    if row['record']['grant'] is None:
                        if not usage and work.review_scope is not None:
                            actual=sessions._account(scope)
                            if self.identity(actual)!=work.account_identity:
                                raise ValueError('原私有评审凭据身份已变化')
                            self._execute(CredentialRefreshStart(scope=scope,work=work),row,actual)
                            continue
                        self._finish_owner(scope)
                        sessions._save(operation_id,'closed',failure='central_not_started')
                        sessions._release_activity(operation_id)
                        continue
                    try:
                        receipt=sessions._call(row,operation+'get',scope.model_dump())
                    except Exception:
                        # prepared取消可阻止迟到启动；已提交记录由Node具体停止处理。
                        receipt=sessions._call(row,operation+'stop',scope.model_dump())
                    self._check(scope,receipt)
                    if receipt['phase']!='closed':
                        receipt=sessions._call(row,operation+'stop',scope.model_dump())
                    self._finish(scope,receipt)
                finally:
                    owner_guard.release()
            except Exception:
                sessions._isolate(operation_id,'credential_refresh_unconfirmed')
            finally:
                with self.lock:
                    self.inflight.discard(operation_id)

    def close(self) -> None:
        """关闭本进程新维护，原未决记录继续由原账本恢复。:return: None。"""
        with self.lock:
            self.closing=True
