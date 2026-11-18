"""中央NULL草稿具体协调，提交恢复始终沿原Node操作和冻结文件。"""
from __future__ import annotations

import hashlib
import re
import shutil
import threading
import time
import uuid
from contextlib import nullcontext

from account_runtime import RuntimeBusy
from cluster_continue_runner import RemoteContinuePty
from cluster_deployment import node_container_name
from cluster_draft_login_contract import DraftLoginAccept, DraftLoginActivated, DraftLoginActivation, DraftLoginCode, DraftLoginCodeRead, DraftLoginDeleted, DraftLoginFiles, DraftLoginGrant, DraftLoginPreparation, DraftLoginPreparationDelete, DraftLoginReceipt, DraftLoginScope, DraftLoginStart, DraftLoginSummary
from cluster_draft_login_files import read_draft_login_documents
from cluster_draft_login_operations import DRAFT_LOGIN_OPERATIONS
from cluster_draft_login_store import NodeLoginDrafts
from cluster_transfer import NodeArchiveTransfer
from login_drafts import LoginDraftStore
from runtime_files import atomic_json
from system_update_contract import safe_read, strict_json


class ClusterDraftLogins:
    """复用原账号owner锁、部署活动和具体SSH通道的草稿协调器。

    :param sessions: 原正式执行协调，仅借用其服务、运行时及部署门禁。
    :param owner_lock: 原按名称串行的不可重入锁工厂。
    :param save_profile: 原profile锁内完整镜像固定文件的回调。
    :param record_authorization: 原首次独立授权来源登记回调。
    :param five_hour_limit: 原产品五小时额度默认值。
    :param seven_day_limit: 原产品七天额度默认值。
    """

    def __init__(self, sessions, owner_lock, save_profile, record_authorization,
            five_hour_limit: int, seven_day_limit: int, *, profile_lock=None, prepare_admission=None) -> None:
        """登记原具体依赖，草稿账本保持与正式账号分离。

        :param sessions: 原中央会话服务。
        :param owner_lock: 原名称锁。
        :param save_profile: 原完整文件镜像。
        :param record_authorization: 原来源登记。
        :param five_hour_limit: 原五小时默认额度。
        :param seven_day_limit: 原七天默认额度。
        :param profile_lock: 原中央资料锁，完整删除与镜像使用同一名称锁。
        :param prepare_admission: 管理入口在实际资源准备前持久原节点意图的回调。
        :return: None。
        """
        self.service,self.runtime,self.activity_gate=sessions.service,sessions.runtime,sessions.activity_gate
        self.ledger=NodeLoginDrafts(self.service.store,sessions.ledger.release,self.runtime.data)
        self.owner_lock,self.save_profile,self.record_authorization=owner_lock,save_profile,record_authorization
        self.profile_lock=profile_lock or (lambda name:nullcontext())
        self.prepare_admission=prepare_admission
        self.five_hour_limit,self.seven_day_limit=five_hour_limit,seven_day_limit
        self.lock=threading.RLock()
        self.operations,self.workers,self.activities={},{},{}
        self.committing=set()
        self.closing=False
        self.sessions=self
        connection=self.service.store.database()
        try:
            pending=[row[0] for row in connection.execute("SELECT operation_id FROM node_login_drafts WHERE phase<>'closed'")]
        finally:
            connection.close()
        for operation_id in pending:
            self.activities[operation_id]=self.activity_gate.restore_reserved('remote-draft:'+operation_id)
            try:
                self._isolate(operation_id,'central_restart')
            except Exception:
                # 冷启动坏记录仍占原部署活动，其他草稿继续初始化。
                pass

    def _operation_lock(self, operation_id):
        with self.lock:
            return self.operations.setdefault(operation_id,threading.RLock())

    def _preparation_path(self, row):
        work=row['record']['work']
        return self.runtime.data/'node-draft-logins'/work['environment_id']/work['id']/'preparation.json'

    def preparation(self, row: dict) -> DraftLoginPreparation:
        """读取原私有准备配置，恢复不会从页面重建代理。

        :param row: 原中央草稿记录。
        :return: 与原冻结工作一致的私有准备。
        """
        return self.ledger.preparation(row)

    def _save(self, operation_id, phase=None, **changes):
        row=self.ledger.get(operation_id)
        return self.ledger.checkpoint(operation_id,row['revision'],phase or row['phase'],**changes)

    def _node(self, row):
        node=self.service.store.get(row['node_id'])
        if (node['node_key']!=row['record']['node_key']
                or hashlib.sha256(node['config_json'].encode()).hexdigest()!=row['record']['node_config_sha256']):
            raise ValueError('原草稿SSH配置已经变化')
        preparation=strict_json((node['preparation_json'] or '{}').encode(),65536)
        if preparation.get('state')!='prepared' or preparation.get('release')!=row['record']['runtime_release']:
            raise ValueError('原草稿Node控制发布需要核对')
        return node

    def _call(self, row, operation, payload):
        if operation not in DRAFT_LOGIN_OPERATIONS:
            raise ValueError('原草稿私有操作超出固定范围')
        node=self._node(row)
        response=self.service.connection(node['id']).execution_environment(
            node_container_name(self.runtime.deployment,node['node_key']),payload,operation)
        value=response.get('record' if operation.startswith('draft-login-grant-') else 'login')
        if (type(response.get('protocol')) is not int or response['protocol']!=1 or response.get('node_key')!=node['node_key']
                or not isinstance(value,dict) or self._node(row)['config_json']!=node['config_json']):
            raise ValueError('原草稿Node回执来源需要核对')
        return value

    def _rpc(self, row, action, payload):
        if action in ('prepare','recover-preparation') and self.prepare_admission is not None:
            self.prepare_admission(row)
        return self._call(row,'draft-login-'+action,payload)

    def _receipt(self, row, value):
        receipt=DraftLoginReceipt.model_validate(value)
        if receipt.scope.model_dump()!=row['record']['scope']:
            raise ValueError('原草稿Node回执Scope已经变化')
        return receipt.model_dump()

    def _reserve(self, row):
        with self.lock:
            if row['operation_id'] not in self.activities:
                source='remote-draft:'+row['operation_id']
                self.activities[row['operation_id']]=self.activity_gate.reserve(source)

    def _release(self, operation_id):
        with self.lock:
            activity=self.activities.pop(operation_id,None)
        self.activity_gate.release_reserved(activity)

    def _isolate(self, operation_id, reason):
        with self._operation_lock(operation_id):
            row=self.ledger.get(operation_id)
            if row['phase']!='closed' and (row['phase']!='reconcile' or row['record']['failure']!=reason):
                self._save(operation_id,'reconcile',failure=reason)

    def find(self, sid: str) -> dict | None:
        """恢复当前草稿SID。:param sid: 原管理SID。:return: 原记录，缺失为None。"""
        return self.ledger.by_sid(sid)

    def start(self, node_id: int, preparation: DraftLoginPreparation, *, previous_revision: int | None=None,
            owner_locked: bool=False) -> dict:
        """持久冻结原配置后准备NULL资源，再发有限证明并启动一次原登录。

        :param node_id: 原选定节点。
        :param preparation: 原NULL环境及私有设置。
        :param previous_revision: 明确新SID恢复或重登的原CAS版本。
        :param owner_locked: 原入口已持有owner锁。
        :return: 持久中央草稿记录。
        """
        preparation=DraftLoginPreparation.model_validate(preparation.model_dump())
        with nullcontext() if owner_locked else self.owner_lock(preparation.work.name):
            with self.lock:
                if self.closing:
                    raise RuntimeBusy('节点草稿登录服务正在关闭')
            row=self.ledger.begin(node_id,preparation,previous_revision=previous_revision)
            if row['phase']=='closed':
                return row
            path=self._preparation_path(row)
            if path.exists() or path.is_symlink():
                if self.preparation(row)!=preparation:
                    raise ValueError('原草稿准备配置已经冻结')
            else:
                atomic_json(path,preparation.model_dump())
            self._reserve(row)
            try:
                with self._operation_lock(row['operation_id']):
                    row=self.ledger.admit(row['operation_id'])
                    if row['record']['start_intent']:
                        return row
                    prepared=self._rpc(row,'prepare',preparation.model_dump())
                    scope=DraftLoginScope.model_validate(prepared.get('scope'))
                    if prepared!={'protocol':1,'scope':scope.model_dump(),'phase':'ready'}:
                        raise ValueError('原Node草稿准备回执需要核对')
                    DraftLoginStart(scope=scope,work=preparation.work)
                    row=self._save(row['operation_id'],scope=scope)
                    grant=DraftLoginGrant(**scope.model_dump(),not_after=min(int(time.time())+30,preparation.work.expires_at))
                    row=self._save(row['operation_id'],grant=grant)
                    proof=self._rpc(row,'grant-create',grant.model_dump())
                    if proof.get('phase')!='prepared' or proof.get('grant')!=grant.model_dump():
                        raise ValueError('原Node草稿初次有限证明需要核对')
                    row=self._save(row['operation_id'],start_intent=True)
                    receipt=self._receipt(row,self._rpc(row,'start',DraftLoginStart(scope=scope,work=preparation.work).model_dump()))
                    row=self._save(row['operation_id'],'active' if receipt['phase']=='ready' else 'preparing',node_receipt=receipt)
                self._watch(row['operation_id'])
                return row
            except Exception:
                self._isolate(row['operation_id'],'draft_start_unconfirmed')
                raise

    def _renew(self, operation_id):
        with self._operation_lock(operation_id):
            row=self.ledger.admit(operation_id)
            old=DraftLoginGrant.model_validate(row['record']['grant'])
            expires=row['record']['work']['expires_at']
            if old.not_after<=time.time() or expires<=time.time():
                raise RuntimeBusy('原草稿有限证明已过期')
            grant=old.model_copy(update={'sequence':old.sequence+1,'not_after':min(int(time.time())+30,expires)})
            row=self._save(operation_id,grant=grant)
            proof=self._rpc(row,'grant-renew',grant.model_dump())
            if proof.get('phase') not in ('prepared','active') or proof.get('grant')!=grant.model_dump():
                raise ValueError('原Node草稿续接证明需要核对')

    def _watch(self, operation_id):
        event=threading.Event()
        def observe():
            renew_at=time.monotonic()+5
            try:
                while not event.wait(.5):
                    with self._operation_lock(operation_id):
                        row=self.ledger.get(operation_id)
                        if row['phase'] not in ('preparing','active'):
                            return
                        receipt=self._receipt(row,self._rpc(row,'get',row['record']['scope']))
                        if receipt['phase']=='reconcile':
                            raise ValueError('原Node草稿执行需要核对')
                        if receipt.get('commit') is not None:
                            self._save(operation_id,'submitting',node_receipt=receipt)
                            return
                        expired=row['record']['work']['expires_at']<=time.time() or receipt['phase']=='closed'
                        if not expired and receipt['phase']=='ready' and row['phase']=='preparing':
                            self._save(operation_id,'active',node_receipt=receipt)
                    if expired:
                        guard=self.owner_lock(row['record']['work']['name'])
                        if guard.acquire(blocking=False):
                            try:
                                self.cancel(operation_id,owner_locked=True)
                            finally:
                                guard.release()
                        return
                    if time.monotonic()>=renew_at:
                        self._renew(operation_id)
                        renew_at=time.monotonic()+5
            except Exception:
                self._isolate(operation_id,'draft_observation_unconfirmed')
            finally:
                with self.lock:
                    self.workers.pop(operation_id,None)
        worker=threading.Thread(target=observe,daemon=True,name='remote-draft-login')
        with self.lock:
            self.workers[operation_id]=(event,worker)
        worker.start()

    def _stop_watch(self, operation_id):
        with self.lock:
            value=self.workers.get(operation_id)
        if value:
            event,worker=value
            event.set()
            if worker is not threading.current_thread():
                worker.join(timeout=5)

    def status(self, operation_id: str) -> dict:
        """沿原Node观察登录，中央完成后读取原结果。:param operation_id: 原操作。:return: 无秘密会话状态。"""
        row=self.ledger.get(operation_id)
        common={'expires_at':row['record']['work']['expires_at'],'authorization_url':None,'reconnectable':False}
        if row['phase']=='closed':
            complete=row['saved_account_id'] is not None
            return {**common,'phase':'committed' if complete else 'ended','credentials_ready':complete}
        if row['record']['scope'] is None:
            return {**common,'phase':'preparing' if row['phase']=='preparing' else 'ended','credentials_ready':False}
        receipt=self._receipt(row,self._rpc(row,'get',row['record']['scope']))
        if receipt.get('commit') is not None:
            return {**common,'phase':'submitting','credentials_ready':True}
        if row['phase'] in ('reconcile','stopping','deleting') or receipt['phase'] in ('reconcile','closed'):
            return {**common,'phase':'ended','credentials_ready':False}
        if receipt['phase']=='starting':
            return {**common,'phase':'preparing','credentials_ready':False}
        return self._rpc(row,'observe',row['record']['scope'])

    def summary(self, operation_id: str) -> dict:
        """只读原Node产物与角色状态。:param operation_id: 原操作。:return: 无凭据摘要。"""
        row=self.ledger.get(operation_id)
        if row['record']['scope'] is None:
            raise RuntimeBusy('原草稿资源准备仍需核对')
        value=DraftLoginSummary.model_validate(self._rpc(row,'summary',row['record']['scope']))
        if value.scope.model_dump()!=row['record']['scope']:
            raise ValueError('原草稿摘要范围已经变化')
        return value.model_dump()

    def code(self, operation_id: str, request_id: str, code: str) -> dict:
        """向原草稿投递一次授权码。:param operation_id: 原操作。:param request_id: 单次标识。:param code: 私有码。:return: 原回执。"""
        row=self.ledger.admit(operation_id)
        if row['phase'] not in ('preparing','active'):
            raise RuntimeBusy('原草稿正在保存或收口，授权码输入已关闭')
        return self._rpc(row,'code',DraftLoginCode(scope=row['record']['scope'],request_id=request_id,code=code).model_dump())

    def code_receipt(self, operation_id: str, request_id: str) -> dict:
        """只读取原授权码回执。:param operation_id: 原操作。:param request_id: 单次标识。:return: 原回执。"""
        row=self.ledger.get(operation_id)
        return self._rpc(row,'code-receipt',DraftLoginCodeRead(scope=row['record']['scope'],request_id=request_id).model_dump())

    def open(self, operation_id: str) -> RemoteContinuePty:
        """只连接原草稿tmux。:param operation_id: 原操作。:return: 原私有PTY桥。"""
        row=self.ledger.admit(operation_id)
        if row['phase'] not in ('preparing','active') or row['record']['work']['mode']!='authorize':
            raise RuntimeBusy('原草稿正在保存或检查产物，交互终端已关闭')
        deadline=time.monotonic()+30
        while True:
            row=self.ledger.admit(operation_id)
            receipt=self._receipt(row,self._rpc(row,'get',row['record']['scope']))
            if receipt['phase']=='ready':
                break
            if receipt['phase']!='starting' or time.monotonic()>=deadline:
                raise RuntimeBusy('原草稿终端仍在准备或需要先核对')
            time.sleep(.2)
        return RemoteContinuePty(self,row,purpose='draft-login')

    def _transfer(self, row):
        self._node(row)
        return NodeArchiveTransfer(self.service.connection(row['node_id']).docker_socket(),self.service.docker(row['node_id']).api._version,
            node_container_name(self.runtime.deployment,row['record']['node_key']))

    def commit(self, operation_id: str, *, owner_locked: bool=False) -> dict:
        """完整文件镜像、Node接受、首次落库、真实ID激活及来源收口逐层接续。

        :param operation_id: 原草稿操作。
        :param owner_locked: 调用方已持有原owner锁。
        :return: 完整保存结果；未知继续保留原阶段与材料。
        """
        row=self.ledger.get(operation_id)
        with nullcontext() if owner_locked else self.owner_lock(row['record']['work']['name']):
            self._stop_watch(operation_id)
            with self._operation_lock(operation_id):
                row=self.ledger.get(operation_id)
                if row['phase']=='closed':
                    return self.result(operation_id)
                with self.lock:
                    self.committing.add(operation_id)
                try:
                    scope=DraftLoginScope.model_validate(row['record']['scope'])
                    receipt=self._receipt(row,self._rpc(row,'commit',scope.model_dump()))
                    if (receipt.get('commit') or {}).get('stage') not in ('saved','accepted'):
                        raise ValueError('原草稿Node授权尚未保存')
                    row=self._save(operation_id,'submitting',node_receipt=receipt,failure=None)
                    if row['record']['files'] is None:
                        index=DraftLoginFiles.model_validate(self._rpc(row,'files',scope.model_dump()))
                        row=self._save(operation_id,files=index)
                    index=DraftLoginFiles.model_validate(row['record']['files'])
                    documents=read_draft_login_documents(self._transfer(row),index,
                        self.runtime.data/'draft-authorizations'/operation_id)
                    self.save_profile(row['record']['work']['name'],documents)
                    if receipt['commit']['stage']!='accepted' or receipt['commit']['cleanup_pending']:
                        request=DraftLoginAccept(scope=scope,authorization_sha256=index.authorization_sha256)
                        receipt=self._receipt(row,self._rpc(row,'accept',request.model_dump()))
                        row=self._save(operation_id,node_receipt=receipt)
                    if receipt['phase']!='closed' or receipt['commit']['cleanup_pending']:
                        raise ValueError('原草稿Node实际停止和暂存清理尚未完成')
                    row=self.ledger.save_account(operation_id,row['revision'],self.preparation(row),
                        self.five_hour_limit,self.seven_day_limit)
                    request=DraftLoginActivation(scope=scope,account_id=row['saved_account_id'],authorization_sha256=index.authorization_sha256)
                    activation=DraftLoginActivated.model_validate(self._rpc(row,'activate',request.model_dump()))
                    if activation.request!=request or activation.refresh_sha256!=receipt['commit']['refresh_sha256']:
                        raise ValueError('原草稿Node真实ID激活回执与授权不一致')
                    self.record_authorization(row['saved_account_id'],row['record']['work']['version'])
                    self.ledger.finish(operation_id,row['revision'],activation,self.runtime.deployment)
                    self._release(operation_id)
                    return self.result(operation_id)
                except Exception:
                    self._isolate(operation_id,'draft_commit_unconfirmed')
                    raise
                finally:
                    with self.lock:
                        self.committing.discard(operation_id)

    def result(self, operation_id: str) -> dict:
        """读取完整保存的原结果。:param operation_id: 原操作。:return: 原正式账号与认证方式。"""
        row=self.ledger.get(operation_id)
        if row['phase']!='closed' or row['saved_account_id'] is None:
            raise ValueError('原草稿尚未完整保存')
        commit=row['record']['node_receipt']['commit']
        return {'id':row['saved_account_id'],'name':row['record']['work']['name'],'auth_method':commit.get('auth_method'),
            'cc2api_account_id':None,'credentials_synced':False}

    def cancel(self, operation_id: str, *, owner_locked: bool=False) -> None:
        """严格停止并保留草稿产物，待确认提交继续原保存。

        :param operation_id: 原操作。
        :param owner_locked: 原入口已持有owner锁。
        :return: None；实际停止未知时保留原记录。
        """
        row=self.ledger.get(operation_id)
        with nullcontext() if owner_locked else self.owner_lock(row['record']['work']['name']):
            self._stop_watch(operation_id)
            with self._operation_lock(operation_id):
                row=self.ledger.get(operation_id)
                if row['phase']=='closed':
                    return
                if row['record']['scope'] is None:
                    self._reserve(row)
                    receipt=DraftLoginReceipt.model_validate(self._rpc(row,'recover-preparation',self.preparation(row).model_dump()))
                    DraftLoginStart(scope=receipt.scope,work=row['record']['work'])
                    if receipt.phase!='closed' or receipt.commit is not None or receipt.result is not None:
                        raise ValueError('原草稿准备恢复尚未确认停止')
                    self._save(operation_id,scope=receipt.scope)
                    self._save(operation_id,'closed',node_receipt=receipt,failure=None)
                    self._release(operation_id)
                    return
                if (row['record']['node_receipt'] or {}).get('commit') is not None:
                    raise RuntimeBusy('原草稿已进入保存，请继续原提交')
                try:
                    self._save(operation_id,'stopping')
                    receipt=self._receipt(row,self._rpc(row,'discard',row['record']['scope']))
                    if receipt['phase']!='closed':
                        raise ValueError('原草稿实际停止尚未确认')
                    self._save(operation_id,'closed',node_receipt=receipt)
                    self._release(operation_id)
                except Exception:
                    self._isolate(operation_id,'draft_stop_unconfirmed')
                    raise

    def retry(self, operation_id: str, mode: str, expires_at: int, *, owner_locked: bool=False) -> dict:
        """确认旧操作实际停止后，沿原节点和私有配置创建新登录代次。

        :param operation_id: 页面读取的旧操作。
        :param mode: authorize重新授权，recover仅检查保留产物。
        :param expires_at: 新代次的固定截止时间。
        :param owner_locked: 调用方已持有原名称锁。
        :return: 新操作的持久记录。
        """
        if mode not in ('authorize','recover'):
            raise ValueError('草稿恢复方式无效')
        row=self.ledger.get(operation_id)
        with nullcontext() if owner_locked else self.owner_lock(row['record']['work']['name']):
            self.cancel(operation_id,owner_locked=True)
            row=self.ledger.get(operation_id)
            if row['saved_account_id'] is not None or (row['record']['node_receipt'] or {}).get('commit') is not None:
                raise RuntimeBusy('草稿已进入保存，请继续原提交')
            if mode=='recover' and not self.summary(operation_id)['credentials_present']:
                raise ValueError('原节点草稿没有保留凭据，请选择重新登录')
            previous=self.preparation(row)
            sid=uuid.uuid4().hex[:12]
            work=previous.work.model_copy(update={'id':uuid.uuid4().hex,'sid':sid,'draft_generation':uuid.uuid4().hex,
                'mode':mode,'home':previous.work.home if mode=='recover' else '/home/node/.v3-login/'+sid,
                'expires_at':expires_at})
            preparation=previous.model_copy(update={'work':work,'previous':DraftLoginScope.model_validate(row['record']['scope'])})
            return self.start(row['node_id'],preparation,previous_revision=row['revision'],owner_locked=True)

    def deletion(self, environment_id: str) -> DraftLoginDeleted | None:
        """读取中央环境外的原Node完整删除事实。:param environment_id: 原环境。:return: 原回执或None。"""
        if not isinstance(environment_id,str) or not re.fullmatch('[a-f0-9]{32}',environment_id):
            raise ValueError('原草稿删除环境无效')
        path=self.runtime.data/'node-draft-deletions'/(environment_id+'.json')
        try:
            value=DraftLoginDeleted.model_validate(strict_json(safe_read(path,16384,private=True),16384))
        except FileNotFoundError:
            return None
        if value.scope.environment_id!=environment_id:
            raise ValueError('原草稿删除回执环境已经变化')
        return value

    def delete(self, environment_id: str, generation: str, *, owner_locked: bool=False) -> None:
        """先确认Node完整清理，再删除中央私有副本和NULL记录，部分失败按原回执接续。

        :param environment_id: 原草稿环境。
        :param generation: 页面读取的逻辑代次。
        :param owner_locked: 调用方已持有原名称锁。
        :return: None；任一未知保留原记录或环境外回执。
        """
        row=self.ledger.find(environment_id)
        if row is not None and row['generation']!=generation:
            raise ValueError('原草稿删除代次已经变化')
        receipt=self.deletion(environment_id)
        if row is None and (receipt is None or receipt.scope.draft_generation!=generation):
            raise ValueError('原草稿删除代次或准备结果需要核对')
        name=row['record']['work']['name'] if row else receipt.scope.name
        operation_id=row['operation_id'] if row else receipt.scope.operation_id
        with nullcontext() if owner_locked else self.owner_lock(name):
            self._stop_watch(operation_id)
            with self._operation_lock(operation_id):
                row=self.ledger.find(environment_id)
                if row is None:
                    self.ledger.check_delete(receipt)
                    self._release(operation_id)
                    return
                if row['operation_id']!=operation_id or row['generation']!=generation:
                    raise ValueError('原草稿删除期间已换代，请刷新列表')
                if row is not None:
                    self.ledger.guard_delete(operation_id)
                    self._reserve(row)
                    if row['phase']!='deleting':
                        if row['record']['scope'] is not None:
                            self.cancel(operation_id,owner_locked=True)
                        row=self._save(operation_id,'deleting')
                    if receipt is None:
                        preparing=row['record']['scope'] is None
                        payload=(DraftLoginPreparationDelete(node_key=row['record']['node_key'],work=row['record']['work'],
                            previous=row['record']['previous']).model_dump() if preparing else row['record']['scope'])
                        receipt=DraftLoginDeleted.model_validate(self._rpc(row,'delete-preparation' if preparing else 'delete',payload))
                        self.ledger.check_delete(receipt)
                        atomic_json(self.runtime.data/'node-draft-deletions'/(environment_id+'.json'),receipt.model_dump())
                if receipt is None:
                    raise ValueError('原Node草稿完整清理事实需要核对')
                scope=receipt.scope
                with self.profile_lock(scope.name):
                    self.ledger.check_delete(receipt)
                    drafts=LoginDraftStore(self.runtime,self.service.store.database,self.service.store.lock)
                    targets=((self.runtime.data/'environments'/environment_id,self.runtime.data/'environments'),
                        (self.runtime.data/'profiles'/scope.name,self.runtime.data/'profiles'),
                        (self.runtime.data/'node-draft-logins'/environment_id,self.runtime.data/'node-draft-logins'),
                        (self.runtime.data/'draft-authorizations'/scope.operation_id,self.runtime.data/'draft-authorizations'))
                    for target,parent in targets:
                        drafts._safe_tree(target,parent)
                    for target,_ in targets:
                        if target.exists():
                            shutil.rmtree(target)
                    self.ledger.check_delete(receipt,finish=True)
                self._release(scope.operation_id)

    def reconcile(self, operation_id: str, *, owner_locked: bool=False) -> dict:
        """只收口指定草稿的原提交或原交互，保留未提交产物。

        :param operation_id: 原操作。
        :param owner_locked: 调用方已持有原名称锁。
        :return: 收口后的原记录。
        """
        row=self.ledger.get(operation_id)
        with nullcontext() if owner_locked else self.owner_lock(row['record']['work']['name']):
            if row['phase']=='closed':
                return row
            if row['record']['scope'] is None:
                self.cancel(operation_id,owner_locked=True)
                return self.ledger.get(operation_id)
            receipt=self._receipt(row,self._rpc(row,'get',row['record']['scope']))
            if receipt.get('commit') is not None:
                self.commit(operation_id,owner_locked=True)
            else:
                self.cancel(operation_id,owner_locked=True)
            return self.ledger.get(operation_id)

    def recover_pending(self) -> None:
        """重启后只接续原提交或停止旧交互。:return: None；单条未知继续保留隔离。"""
        connection=self.service.store.database()
        try:
            operations=[row[0] for row in connection.execute("SELECT operation_id FROM node_login_drafts WHERE phase<>'closed'")]
        finally:
            connection.close()
        for operation_id in operations:
            with self.lock:
                if self.closing or operation_id in self.workers or operation_id in self.committing:
                    continue
            try:
                row=self.ledger.get(operation_id)
                guard=self.owner_lock(row['record']['work']['name'])
                if not guard.acquire(blocking=False):
                    continue
                try:
                    # 本进程新登记且尚未准入的工作必须重新走真实门禁，不能被轮询恢复为旧许可。
                    self._reserve(row)
                    if row['phase']=='deleting':
                        self.delete(row['environment_id'],row['generation'],owner_locked=True)
                        continue
                    if row['record']['scope'] is None:
                        self.cancel(operation_id,owner_locked=True)
                        continue
                    try:
                        receipt=self._receipt(row,self._rpc(row,'get',row['record']['scope']))
                    except Exception:
                        receipt=self._receipt(row,self._rpc(row,'stop',row['record']['scope']))
                    if receipt.get('commit') is not None:
                        self.commit(operation_id,owner_locked=True)
                    else:
                        self.cancel(operation_id,owner_locked=True)
                finally:
                    guard.release()
            except Exception:
                try:
                    self._isolate(operation_id,'draft_recovery_unconfirmed')
                except Exception:
                    # 坏记录继续占用原部署活动，单条故障不遮住其他草稿的恢复。
                    with self.lock:
                        if operation_id not in self.activities:
                            self.activities[operation_id]=self.activity_gate.restore_reserved('remote-draft:'+operation_id)

    def close(self) -> None:
        """关闭新操作与本进程续接。:return: None；原持久活动保留供恢复。"""
        with self.lock:
            self.closing=True
            workers=list(self.workers.values())
        for event,_ in workers:
            event.set()
        for _,worker in workers:
            if worker is not threading.current_thread():
                worker.join(timeout=5)
