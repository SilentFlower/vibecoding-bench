"""绑定SSH登录的原Gateway租约、同操作导入和长期所有权收口。"""
from __future__ import annotations

import time
import json
from contextlib import nullcontext
from uuid import uuid4

from account_runtime import AccountRuntime, RuntimeBusy
from cluster_bound_identity import RemoteBoundIdentity
from cluster_bound_login_contract import BoundLoginAbort, BoundLoginCommit, BoundLoginIdentity, BoundLoginPublish, BoundLoginStart, BoundLoginWork
from cluster_credentials_contract import CredentialMaterial
from cluster_execution_grants import ExecutionGrant, ExecutionLeaseProof, ExecutionScope
from cluster_login_contract import AccountLoginAccept, AccountLoginSnapshot
from cluster_login_runner import ClusterAccountLogins


class ClusterBoundAccountLogins(ClusterAccountLogins):
    """保持原Gateway唯一刷新权，仅把实际授权CLI交给所属Node。

    :param sessions: 原中央执行账本和受信SSH。
    :param credentials: 原凭据协调及长期所有者依赖。
    :param owner_lock: 原不可重入账号锁。
    :param save_authorization: 中央权威镜像回调；保持绑定账号原策略和额度。
    :param admission: 原业务活动检查。
    """

    kind='account-bound-login'
    operation_prefix='account-bound-login-'
    pty_purpose='bound-login'

    def __init__(self, sessions, credentials, owner_lock, save_authorization, admission=None) -> None:
        """复用原有限会话与一次输入协调，长期所有权继续由原对象维护。

        :param sessions: 原执行协调。
        :param credentials: 原凭据协调。
        :param owner_lock: 原账号锁。
        :param save_authorization: 原中央镜像回调。
        :param admission: 原业务活动门禁。
        :return: None。
        """
        super().__init__(sessions,credentials,owner_lock,save_authorization,admission)
        self.ownership=credentials.ownership
        self.identity_reader=RemoteBoundIdentity(sessions,credentials.version)

    def routes(self, account: dict) -> bool:
        """识别已有绑定SSH账号。:param account: 当前账号。:return: 是否属于本具体消费者。"""
        return (type(account.get('cc2api_account_id')) is int and account['cc2api_account_id']>0
            and self.sessions.service.store.assignment(account['id'])['kind']=='ssh')

    def _row(self, operation_id: str):
        row=self.sessions.ledger.get(operation_id)
        request=BoundLoginStart.model_validate({'scope':row['record']['scope'],'work':row['record']['work']})
        return row,request

    def _account(self, account: dict) -> dict:
        connection=self.sessions.service.store.database()
        try:
            current=connection.execute('SELECT * FROM accounts WHERE id=?',(account['id'],)).fetchone()
        finally:
            connection.close()
        if (current is None or current['name']!=account['name'] or current['cc2api_account_id']!=account.get('cc2api_account_id')
                or current['deleted_at'] is not None or not self.routes(dict(current))):
            raise ValueError('原绑定登录账号或节点归属已经变化')
        return dict(current)

    def _owner_record(self, request: BoundLoginStart) -> dict:
        if self.ownership is None:
            raise ValueError('原Gateway凭据所有权服务尚未就绪')
        record=self.ownership.state(request.scope.account_id)
        identity=((record or {}).get('input') or {}).get('identity') or {}
        expected=request.work.expected_identity
        if (record is None or record.get('owner')!='gateway' or record.get('remote_id')!=request.scope.gateway_account_id
                or record.get('original_binding')!=request.scope.gateway_account_id
                or record.get('input',{}).get('direction')!='reauth'
                or record['input'].get('lease_owner')!=request.scope.source
                or identity.get('environment_id')!=request.scope.environment_id
                or identity.get('bench_account_id')!=request.scope.account_id or identity.get('device_id')!=request.work.device_id
                or str(identity.get('email') or '').strip().lower()!=expected.email.strip().lower()
                or str(identity.get('account_uuid') or '').strip().lower()!=expected.account_uuid.strip().lower()
                or (expected.organization_uuid or '').strip()
                and str(identity.get('organization_uuid') or '').strip().lower()!=expected.organization_uuid.strip().lower()):
            raise ValueError('原Gateway长期重授权来源或身份已经变化')
        return record

    def _metadata(self, request: BoundLoginStart, receipt: dict) -> BoundLoginCommit:
        self._check(request.scope,receipt)
        try:
            metadata=BoundLoginCommit.model_validate(receipt.get('commit'))
        except (ValueError,TypeError):
            raise ValueError('原绑定Node授权回执需要核对') from None
        expected=request.work.expected_identity
        if (metadata.aborted or metadata.identity.email.strip().lower()!=expected.email.strip().lower()
                or metadata.identity.account_uuid.strip().lower()!=expected.account_uuid.strip().lower()
                or (expected.organization_uuid or '').strip()
                and (metadata.identity.organization_uuid or '').strip().lower()!=expected.organization_uuid.strip().lower()):
            raise ValueError('原绑定Node冻结授权与本次工作不一致')
        return metadata

    def start(self, account: dict, sid: str, version: str, *, ttl: int = 1800, owner_locked: bool = False) -> dict:
        """先落账再暂停原Gateway并认领真实排他lease，最后启动一次Node授权。

        :param account: 原绑定账号。
        :param sid: 本次原登录SID。
        :param version: 已选定的实际CLI版本。
        :param ttl: 原授权TTL。
        :param owner_locked: 调用方已持有原账号锁。
        :return: 本次持久登录记录；未知保留原Scope与长期暂停。
        """
        with nullcontext() if owner_locked else self.owner_lock(account['name']):
            if self.closing or self.ownership is None:
                raise RuntimeBusy('绑定节点登录服务尚未就绪或正在关闭')
            if type(ttl) is not int or not 1<=ttl<=86400:
                raise ValueError('原登录授权时长无效')
            account=self._account(account)
            if self.admission is not None:
                self.admission(account,sid,None)
            if self.sessions.ledger.active(account['id']):
                raise RuntimeBusy('原绑定账号还有未收口节点工作')
            state=self.ownership.state(account['id'])
            if state and state['phase']!='ready' and not state.get('gateway_refresh_pending'):
                raise ValueError('原凭据交接或重授权仍需核对')
            if not state or not state.get('gateway_refresh_pending'):
                self.ownership.guard(account,'login:'+sid)
            configuration=self.sessions.gateway._request('GET',f"/admin/runtime/accounts/{account['cc2api_account_id']}/config")
            identity=BoundLoginIdentity.model_validate({key:configuration.get(key) for key in
                ('email','account_uuid','organization_uuid')})
            stable=json.dumps({'account_id':account['id'],'binding':account['cc2api_account_id'],
                'uuid':identity.account_uuid,'org':identity.organization_uuid},sort_keys=True)
            self.sessions.service.prepare_remote_login(account,self.sessions.runtime,self.sessions.gateway,stable,sid)
            observed=self.identity_reader.read(account,configuration)
            assignment=self.sessions.service.store.assignment(account['id'])
            actual=self.sessions.runtime._row(account['name'],account['id'])
            work=BoundLoginWork(id=uuid4().hex,sid=sid,account_id=account['id'],gateway_account_id=account['cc2api_account_id'],
                account_identity=stable,device_id=observed['device_id'],expected_identity=identity,version=version,expires_at=int(time.time())+ttl)
            scope=ExecutionScope(operation_id=work.id,node_key=assignment['node_key'],account_id=account['id'],
                gateway_account_id=work.gateway_account_id,environment_id=actual['environment_id'],assignment_revision=assignment['revision'],
                generation=actual['generation'],source=work.source,role='login')
            request=BoundLoginStart(scope=scope,work=work)
            row=self.sessions.ledger.begin(scope,work,require_new=True)
            try:
                activity=self.sessions.activity_gate.reserve('remote-bound-login:'+scope.source)
                with self.sessions.lock:
                    self.sessions.activities[work.id]=activity
                row=self.sessions._save(work.id,gateway_prepare_intent=True)
                self.ownership.begin_reauth(account,sid)
                owner=self._owner_record(request)
                value=self.ownership._rpc(owner,'status')
                if (value.get('receipt') or {}).get('stage')!='prepared':
                    raise ValueError('原Gateway长期登录暂停尚未确认')
                snapshot=self.sessions.gateway._request('POST',self.sessions._path(scope),{'operation':'prepare','owner':scope.source})
                lease=self.sessions._lease(snapshot,scope,exclusive=True)
                row=self.sessions._save(work.id,lease=lease.model_dump())
                if snapshot.get('active')!=0 or snapshot.get('importing')!=0:
                    raise RuntimeBusy('原Gateway活动尚未排空')
                lease=self.sessions._lease(self.sessions.gateway._request('POST',self.sessions._path(scope),
                    {'operation':'claim','owner':lease.owner,'generation':lease.generation}),scope,claimed=True,exclusive=True)
                grant=ExecutionGrant(**scope.model_dump(),not_after=min(lease.expires_at,work.expires_at),lease=lease)
                row=self.sessions._save(work.id,'claimed',lease=lease.model_dump(),grant=grant.model_dump())
                value=self.sessions._call(row,'grant-create',grant.model_dump())
                if value.get('phase')!='prepared' or value.get('grant')!=grant.model_dump():
                    raise ValueError('原Node绑定登录准备证明尚未确认')
                row=self.sessions._save(work.id,'starting')
                receipt=self._call(row,'start',request.model_dump())
                self._check(scope,receipt)
                row=self.sessions._save(work.id,'running' if receipt['phase']=='ready' else None,node_receipt=receipt)
                self._watch(work.id)
                return row
            except Exception:
                self.sessions._isolate(work.id,'bound_login_start_unconfirmed')
                raise

    def _renew(self, operation_id: str) -> None:
        with self.sessions._operation_lock(operation_id):
            row=self.sessions.ledger.admit(operation_id)
            _,request=self._row(operation_id)
            old=ExecutionGrant.model_validate(row['record']['grant'])
            if old.not_after<=time.time() or request.work.expires_at<=time.time():
                raise RuntimeBusy('原绑定登录证明已过期，需要核对原操作')
            self._owner_record(request)
            snapshot=self.sessions.gateway._request('POST',self.sessions._path(request.scope),
                {'operation':'heartbeat','owner':old.lease.owner,'generation':old.lease.generation})
            lease=self.sessions._lease(snapshot,request.scope,claimed=True,exclusive=True)
            grant=ExecutionGrant(**request.scope.model_dump(),sequence=old.sequence+1,
                not_after=min(lease.expires_at,request.work.expires_at),lease=lease)
            row=self.sessions._save(operation_id,lease=lease.model_dump(),grant=grant.model_dump())
            result=self.sessions._call(row,'grant-renew',grant.model_dump())
            if result.get('phase') not in ('prepared','active') or result.get('grant')!=grant.model_dump():
                raise ValueError('原绑定Node登录续接尚未确认')

    def _current(self, request: BoundLoginStart, value: dict) -> dict:
        if not isinstance(value,dict) or type(value.get('account_id')) is not int or value['account_id']!=request.scope.gateway_account_id:
            raise ValueError('原Gateway导入快照属于其他账号')
        try:
            return CredentialMaterial.model_validate({key:value.get(key) for key in
                ('access_token','refresh_token','expires_at')}).model_dump()
        except (ValueError,TypeError):
            raise ValueError('原Gateway导入快照需要核对') from None

    def _publish(self, row: dict, request: BoundLoginStart, metadata: BoundLoginCommit, current: dict) -> dict:
        snapshot=AccountLoginSnapshot(scope=request.scope,authorization_sha256=metadata.authorization_sha256,
            material=current,identity={'user_id':request.work.device_id,**metadata.identity.model_dump()},
            version=request.work.version,auth_method=metadata.auth_method)
        account=self.sessions._account(request.scope,available=False)
        self.save_authorization(account,snapshot.model_dump(),request.work.version)
        receipt=self._call(row,'publish',BoundLoginPublish(scope=request.scope,authorization_sha256=metadata.authorization_sha256,
            access_token=current['access_token'],expires_at=current['expires_at']).model_dump())
        published=self._metadata(request,receipt)
        if published.stage not in ('saved','accepted'):
            raise ValueError('原Node当前AT发布尚未完成')
        return receipt

    def _lease_snapshot(self, row: dict, request: BoundLoginStart):
        snapshot=self.sessions.gateway._request('GET',self.sessions._path(request.scope))
        if not isinstance(snapshot.get('holders'),list):
            raise ValueError('原Gateway租约快照需要核对')
        current=AccountRuntime._owned_lease(snapshot,request.scope.source)
        if current is not None:
            lease=ExecutionLeaseProof.model_validate({key:current[key] for key in
                ('owner','generation','expires_at','exclusive','shared_cli')})
            if not lease.exclusive or lease.shared_cli:
                raise ValueError('原绑定登录排他模式已经变化')
            old=row['record']['lease']
            if old is not None and any(old[key]!=getattr(lease,key) for key in ('owner','generation','exclusive','shared_cli')):
                raise ValueError('原绑定登录真实lease代次已经变化')
            if old is None:
                row=self.sessions._save(request.work.id,lease=lease.model_dump())
        return row,snapshot,current

    def _fence(self, row: dict, request: BoundLoginStart) -> dict:
        row,snapshot,current=self._lease_snapshot(row,request)
        if current is not None:
            proof={'owner':current['owner'],'generation':current['generation']}
            try:
                snapshot=self.sessions.gateway._request('POST',self.sessions._path(request.scope),{'operation':'fence',**proof})
            except Exception:
                snapshot=self.sessions.gateway._request('GET',self.sessions._path(request.scope))
            current=AccountRuntime._owned_lease(snapshot,request.scope.source)
            if current is not None and (current.get('generation')!=proof['generation'] or current.get('phase')!='reconcile'):
                raise ValueError('原Gateway登录fence尚未确认')
        if not isinstance(snapshot.get('holders'),list) or snapshot.get('importing')!=0:
            raise RuntimeBusy('原Gateway凭据导入仍在途，需要继续对账')
        return row

    def _release_gateway(self, row: dict, request: BoundLoginStart) -> dict:
        if row['record']['lease_released'] is not None:
            return row
        row,snapshot,current=self._lease_snapshot(row,request)
        lease=row['record']['lease']
        if lease is None:
            return row
        proof={'owner':lease['owner'],'generation':lease['generation']}
        if current is not None:
            try:
                snapshot=self.sessions.gateway._request('POST',self.sessions._path(request.scope),{'operation':'release',**proof})
            except Exception:
                snapshot=self.sessions.gateway._request('GET',self.sessions._path(request.scope))
        if not isinstance(snapshot.get('holders'),list) or AccountRuntime._owned_lease(snapshot,request.scope.source) is not None:
            raise ValueError('原Gateway真实登录lease释放尚未确认')
        return self.sessions._save(request.work.id,lease_released={**proof,'released':True})

    def _finish_owner(self, row: dict, request: BoundLoginStart, *, imported: bool) -> None:
        record=self._owner_record(request)
        value=self.ownership._rpc(record,'status')
        receipt=value.get('receipt')
        if receipt is None and not imported:
            # 同一无凭据prepare是幂等暂停；该恢复不启动Node CLI或交换RT。
            value=self.ownership._rpc(record,'prepare')
            receipt=value.get('receipt')
        if imported and (receipt or {}).get('import_operation_id')!=request.work.id:
            raise ValueError('原长期所有权回执尚未关联本次导入')
        self.ownership.close_reauth(request.scope.account_id,request.work.sid)
        if self._owner_record(request).get('stage')!='ready':
            raise ValueError('原长期重授权尚未完整收口')

    def commit(self, operation_id: str, *, owner_locked: bool = False) -> dict:
        """同一Gateway操作先查回执再导入，AT-only及实际RT清理后才结束长期暂停。

        :param operation_id: 原绑定登录操作。
        :param owner_locked: 调用方已持有原账号锁。
        :return: 固定无令牌完成结果；未知保留同Scope、材料及长期门禁。
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
                self._owner_record(request)
                if self.admission is not None:
                    self.admission(account,request.work.sid,None)
                receipt=self._call(row,'commit',request.scope.model_dump())
                metadata=self._metadata(request,receipt)
                row=self.sessions._save(operation_id,node_receipt=receipt)
                current=self.sessions.gateway.import_status(request.scope.gateway_account_id,operation_id)
                if current is None:
                    if metadata.stage!='frozen':
                        raise ValueError('原Node已发布授权，Gateway原导入回执需要继续核对')
                    snapshot=self._snapshot(row,request,receipt)
                    material=snapshot['material']
                    lease=ExecutionLeaseProof.model_validate(row['record']['lease'])
                    payload={**{key:snapshot['identity'][key] for key in ('email','account_uuid','organization_uuid')},
                        **{key:material[key] for key in ('access_token','refresh_token','expires_at')},
                        'operation_id':operation_id,'owner':lease.owner,'generation':lease.generation}
                    payload.update({key:material[key] for key in ('subscription_type','rate_limit_tier') if material.get(key) is not None})
                    current=self.sessions.gateway.import_credentials(request.scope.gateway_account_id,payload)
                current=self._current(request,current)
                receipt=self._publish(row,request,metadata,current)
                row=self.sessions._save(operation_id,node_receipt=receipt)
                self._stop_watch(operation_id)
                receipt=self._call(row,'accept',AccountLoginAccept(scope=request.scope,
                    authorization_sha256=metadata.authorization_sha256).model_dump())
                accepted=self._metadata(request,receipt)
                if receipt['phase']!='closed' or accepted.stage!='accepted' or accepted.cleanup_pending:
                    raise ValueError('原绑定Node终端或RT暂存清理仍需核对')
                row=self.sessions._save(operation_id,'stopping',node_receipt=receipt)
                row=self._release_gateway(row,request)
                self._finish_owner(row,request,imported=True)
                self.sessions._save(operation_id,'closed')
                self.sessions._release_activity(operation_id)
                return self.result(operation_id)
            except Exception:
                if self.sessions.ledger.get(operation_id)['phase']!='closed':
                    self.sessions._isolate(operation_id,'bound_login_commit_unconfirmed')
                raise
            finally:
                with self.lock:
                    self.committing.discard(operation_id)

    def result(self, operation_id: str) -> dict:
        """读取原绑定登录已完成结果。:param operation_id: 原操作。:return: 无令牌同步状态。"""
        result=super().result(operation_id)
        _,request=self._row(operation_id)
        return {**result,'cc2api_account_id':request.scope.gateway_account_id,'credentials_synced':True}

    def cancel(self, operation_id: str, *, owner_locked: bool = False) -> None:
        """先fence并查原导入回执，明确未导入才清理本次RT并取消原长期暂停。

        :param operation_id: 原登录。
        :param owner_locked: 调用方已持有原账号锁。
        :return: None；已导入接完成分支，未知继续保留原材料和门禁。
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
                if not row['record']['gateway_prepare_intent']:
                    self.sessions._save(operation_id,'closed',failure='central_not_started')
                    self.sessions._release_activity(operation_id)
                    return
                row=self._fence(row,request)
                current=self.sessions.gateway.import_status(request.scope.gateway_account_id,operation_id)
                if current is not None:
                    self.commit(operation_id,owner_locked=True)
                    return
                if row['record']['grant'] is not None:
                    try:
                        receipt=self._call(row,'get',request.scope.model_dump())
                    except Exception:
                        receipt=self._call(row,'stop',request.scope.model_dump())
                    self._check(request.scope,receipt)
                    commit=receipt.get('commit')
                    if commit is not None:
                        metadata=BoundLoginCommit.model_validate(commit)
                        if metadata.stage!='frozen':
                            raise ValueError('Node已发布授权，原Gateway回执需要继续核对')
                        receipt=self._call(row,'abort',BoundLoginAbort(scope=request.scope,
                            authorization_sha256=metadata.authorization_sha256,lease_generation=row['record']['lease']['generation'],
                            import_not_submitted=True).model_dump())
                        if (receipt.get('commit') or {}).get('cleanup_pending') is not False:
                            raise ValueError('原绑定RT清理仍需核对')
                    else:
                        self._call(row,'stop',request.scope.model_dump())
                        receipt=self._call(row,'discard',request.scope.model_dump())
                        if receipt.get('discarded') is not True:
                            raise ValueError('原绑定登录暂存清理仍需核对')
                    self._check(request.scope,receipt)
                    if receipt['phase']!='closed':
                        raise ValueError('原绑定Node登录尚未实际停止')
                    row=self.sessions._save(operation_id,'stopping',node_receipt=receipt)
                row=self._release_gateway(row,request)
                state=self.ownership.state(request.scope.account_id)
                if state and (state.get('input') or {}).get('lease_owner')==request.scope.source:
                    self._finish_owner(row,request,imported=False)
                elif row['record']['grant'] is not None or row['record']['lease'] is not None:
                    raise ValueError('原绑定长期暂停来源需要核对')
                if row['record']['grant'] is None:
                    self.sessions._save(operation_id,'closed',node_start_cancelled=True,failure='central_node_not_submitted')
                else:
                    self.sessions._save(operation_id,'closed')
                self.sessions._release_activity(operation_id)
            except Exception:
                self.sessions._isolate(operation_id,'bound_login_cleanup_unconfirmed')
                raise

    def recover_pending(self) -> None:
        """按原Gateway回执恢复提交或fence取消，原CLI启动与授权码都不补发。

        :return: None；单账号未知保留隔离，其他账号继续核对。
        """
        for operation_id in self.sessions.ledger.pending():
            row=self.sessions.ledger.get(operation_id)
            if row['record']['work'].get('kind')!=self.kind:
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
                if row['record']['grant'] is None:
                    self.cancel(operation_id,owner_locked=True)
                    continue
                try:
                    receipt=self._call(row,'get',request.scope.model_dump())
                except Exception:
                    self.cancel(operation_id,owner_locked=True)
                    continue
                self._check(request.scope,receipt)
                if receipt.get('commit') is not None and not (receipt['commit'].get('aborted',False)):
                    if receipt['commit'].get('stage')=='frozen' and self.sessions.gateway.import_status(request.scope.gateway_account_id,operation_id) is None:
                        row,_,lease=self._lease_snapshot(row,request)
                        if lease is None or lease.get('phase')!='claimed' or lease.get('expires_at',0)<=time.time():
                            self.cancel(operation_id,owner_locked=True)
                            continue
                    self.commit(operation_id,owner_locked=True)
                else:
                    self.cancel(operation_id,owner_locked=True)
            except Exception:
                self.sessions._isolate(operation_id,'bound_login_recovery_unconfirmed')
            finally:
                guard.release()

    def owner_idle(self, account: dict, record: dict) -> bool:
        """供原Owner收口核对本次Node实际停止及原Gateway lease释放。

        :param account: 原绑定账号。
        :param record: 原长期重授权记录。
        :return: True；未知或错来源保持失败。
        """
        source=record.get('input',{}).get('lease_owner','')
        row=self.find(source.removeprefix('login:'))
        if row is None or row['account_id']!=account['id']:
            raise ValueError('原绑定登录停止证据暂不可读')
        _,request=self._row(row['operation_id'])
        self._owner_record(request)
        if row['record']['grant'] is not None:
            receipt=row['record'].get('node_receipt') or {}
            commit=receipt.get('commit')
            complete=(commit is not None and commit.get('cleanup_pending') is False
                and (commit.get('stage')=='accepted' or commit.get('aborted') is True)) or receipt.get('discarded') is True
            if receipt.get('phase')!='closed' or not complete:
                raise ValueError('原绑定Node终端或RT暂存仍需实际收口')
        if row['record']['lease'] is not None and row['record']['lease_released'] is None:
            raise ValueError('原绑定Gateway排他lease仍需释放')
        return True

    def owner_publish(self, account: dict, snapshot: dict, record: dict, value: dict) -> bool:
        """原Owner确认同一导入回执后，只同步当前Gateway AT。

        :param account: 原账号。
        :param snapshot: 原Gateway当前权威快照。
        :param record: 原长期重授权来源。
        :param value: 原同操作所有权回执。
        :return: True；不通过中央HOME同步远程材料。
        """
        self.owner_idle(account,record)
        row=self.find(record['input']['lease_owner'].removeprefix('login:'))
        _,request=self._row(row['operation_id'])
        if (value.get('receipt') or {}).get('import_operation_id')!=request.work.id:
            raise ValueError('原长期所有权回执属于其他导入操作')
        metadata=self._metadata(request,row['record']['node_receipt'])
        receipt=self._publish(row,request,metadata,self._current(request,snapshot))
        self.sessions._save(request.work.id,node_receipt=receipt)
        return True
