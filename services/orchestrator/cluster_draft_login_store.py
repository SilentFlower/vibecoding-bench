"""中央NULL登录草稿的冻结操作、有限证明与首次账号提交事务。"""
from __future__ import annotations

import hashlib
import re
import time
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, StrictStr, model_validator

from cluster_draft_login_contract import DraftLoginActivated, DraftLoginDeleted, DraftLoginFiles, DraftLoginGrant, DraftLoginPreparation, DraftLoginPreparationScope, DraftLoginReceipt, DraftLoginScope, DraftLoginStart, DraftLoginWork
from system_update_contract import safe_read, strict_json


class CentralDraftLoginRecord(BaseModel):
    """仅保存原范围和无令牌事实的中央草稿记录。

    :param work: 原冻结工作。
    :param node_key: 首次选择的节点。
    :param node_config_sha256: 原SSH配置摘要。
    :param runtime_release: 原控制组件发布。
    :param previous: 显式恢复或重登的原已停止范围。
    :param scope: 准备后观察到的真实Node范围。
    :param grant: 当前有限证明。
    :param start_intent: 原启动意图，先于实际启动落盘。
    :param node_receipt: 原Node受控回执。
    :param saved_account_id: 首次事务提交产生的真实账号。
    :param activation: 原Node实际停止并发布真实ID的回执。
    :param files: 原完整授权文件索引，供接受响应未知后恢复已验证的私有副本。
    :param failure: 固定脱敏恢复原因。
    """

    model_config=ConfigDict(extra='forbid')
    work:DraftLoginWork
    node_key:StrictStr=Field(pattern=r'^[a-f0-9]{32}$')
    node_config_sha256:StrictStr=Field(pattern=r'^[a-f0-9]{64}$')
    runtime_release:StrictStr=Field(min_length=1,max_length=128)
    previous:DraftLoginScope | None=None
    scope:DraftLoginScope | None=None
    grant:DraftLoginGrant | None=None
    start_intent:StrictBool=False
    node_receipt:DraftLoginReceipt | None=None
    saved_account_id:StrictInt | None=Field(default=None,ge=1)
    activation:DraftLoginActivated | None=None
    files:DraftLoginFiles | None=None
    failure:StrictStr | None=Field(default=None,pattern=r'^[a-z][a-z0-9_]{0,79}$')

    @model_validator(mode='after')
    def validate_evidence(self):
        """冻结同一草稿来源，正式ID只在实际授权已收口后出现。:return: 已核对记录。"""
        if self.scope is not None:
            DraftLoginStart(scope=self.scope,work=self.work)
            if self.scope.node_key!=self.node_key:
                raise ValueError('原草稿节点身份已经变化')
        if self.grant is not None and (self.grant.scope()!=self.scope or self.grant.not_after>self.work.expires_at):
            raise ValueError('草稿有限证明超出原范围或授权截止')
        if self.start_intent and self.grant is None:
            raise ValueError('草稿启动意图必须先保存原有限证明')
        if self.node_receipt is not None and (self.node_receipt.scope!=self.scope
                or self.node_receipt.result is not None and not self.start_intent):
            raise ValueError('原草稿Node回执缺少同一范围或启动意图')
        if self.saved_account_id is not None and not self.accepted:
            raise ValueError('首次正式保存前必须确认原Node授权、实际停止和暂存清理')
        if self.files is not None and (self.files.scope!=self.scope or self.node_receipt is None or self.node_receipt.commit is None
                or self.files.authorization_sha256!=self.node_receipt.commit.authorization_sha256
                or set(self.files.files)!=set(self.node_receipt.commit.files)):
            raise ValueError('原草稿完整授权文件索引与冻结范围不一致')
        if self.activation is not None:
            request=self.activation.request
            if (self.saved_account_id is None or not self.accepted or request.account_id!=self.saved_account_id
                    or request.scope!=self.scope or request.authorization_sha256!=self.node_receipt.commit.authorization_sha256
                    or self.activation.refresh_sha256!=self.node_receipt.commit.refresh_sha256):
                raise ValueError('原草稿真实ID激活与中央首次保存范围不一致')
        return self

    @property
    def accepted(self) -> bool:
        """读取完整Node授权收口事实。:return: 原授权接受及清理均已确认。"""
        receipt=self.node_receipt
        return bool(receipt is not None and receipt.phase=='closed' and receipt.commit is not None
            and receipt.commit.stage=='accepted' and not receipt.commit.cleanup_pending and self.start_intent)


class NodeLoginDrafts:
    """与正ID执行账本分离的中央草稿存储，写锁仅覆盖短SQLite事务。

    :param store: 原中央ClusterStore。
    :param release: 同批控制发布。
    :param data: 中央原数据根，用于核对历史flow引用。
    """

    def __init__(self, store, release: str, data: Path) -> None:
        """登记原存储依赖。:param store: 原存储。:param release: 发布。:param data: 原数据根。:return: None。"""
        if not isinstance(release,str) or not 1<=len(release)<=128:
            raise ValueError('草稿登记缺少原控制发布')
        self.store,self.release,self.data=store,release,Path(data)

    def _decode(self, row) -> dict:
        if row is None:
            raise ValueError('原节点登录草稿不存在')
        value=dict(row)
        record=CentralDraftLoginRecord.model_validate(strict_json(value.pop('record_json').encode(),65536))
        expected={'operation_id':record.work.id,'environment_id':record.work.environment_id,'sid':record.work.sid,
            'generation':record.work.draft_generation,'saved_account_id':record.saved_account_id}
        if any(value.get(key)!=item for key,item in expected.items()):
            raise ValueError('中央草稿行与原冻结记录不一致')
        self._validate_phase(value['phase'],record)
        return {**value,'record':record.model_dump()}

    @staticmethod
    def _validate_phase(phase: str, record: CentralDraftLoginRecord) -> None:
        if (record.node_receipt is not None and record.node_receipt.commit is not None and phase not in ('submitting','reconcile')
                and not (phase=='closed' and record.activation is not None)):
            raise ValueError('原草稿冻结授权必须继续保留提交隔离')
        if phase=='active' and (not record.start_intent or record.node_receipt is None or record.node_receipt.phase!='ready'):
            raise ValueError('草稿活动阶段缺少原Node启动确认')
        if phase=='submitting' and (not record.start_intent or record.node_receipt is None or record.node_receipt.commit is None):
            raise ValueError('草稿提交阶段缺少原冻结授权')
        if record.saved_account_id is not None and phase not in ('submitting','reconcile','closed'):
            raise ValueError('已保存草稿继续保留首次提交隔离，等待正式激活收口')
        if phase=='closed' and record.saved_account_id is not None and record.activation is None:
            raise ValueError('原草稿正式账号尚未完成Node真实ID激活')
        if phase=='closed' and (record.scope is not None or record.start_intent or record.grant is not None):
            if record.node_receipt is None or record.node_receipt.phase!='closed':
                raise ValueError('关闭草稿前必须确认原Node实际停止')

    def find(self, environment_id: str) -> dict | None:
        """读取当前环境草稿。:param environment_id: 原环境ID。:return: 原记录，缺失为None。"""
        if not isinstance(environment_id,str) or not re.fullmatch('[a-f0-9]{32}',environment_id):
            raise ValueError('草稿环境身份无效')
        connection=self.store.database()
        try:
            row=connection.execute('SELECT * FROM node_login_drafts WHERE environment_id=?',(environment_id,)).fetchone()
            return self._decode(row) if row is not None else None
        finally:
            connection.close()

    def get(self, operation_id: str) -> dict:
        """按原操作读取恢复记录。:param operation_id: 原操作。:return: 冻结记录。"""
        if not isinstance(operation_id,str) or not re.fullmatch('[a-f0-9]{32}',operation_id):
            raise ValueError('草稿操作身份无效')
        connection=self.store.database()
        try:
            return self._decode(connection.execute('SELECT * FROM node_login_drafts WHERE operation_id=?',(operation_id,)).fetchone())
        finally:
            connection.close()

    def by_sid(self, sid: str) -> dict | None:
        """恢复原管理会话。:param sid: 原SID。:return: 当前草稿操作，缺失为None。"""
        if not isinstance(sid,str) or not re.fullmatch('[a-f0-9]{12}',sid):
            raise ValueError('草稿登录会话身份无效')
        connection=self.store.database()
        try:
            row=connection.execute('SELECT * FROM node_login_drafts WHERE sid=?',(sid,)).fetchone()
            return self._decode(row) if row is not None else None
        finally:
            connection.close()

    def pending(self) -> list[dict]:
        """读取需要后台恢复的当前操作。:return: 未收口私有记录。"""
        connection=self.store.database()
        try:
            return [self._decode(row) for row in connection.execute("SELECT * FROM node_login_drafts WHERE phase<>'closed' ORDER BY created_at")]
        finally:
            connection.close()

    def _current(self, connection, node_id: int, record: CentralDraftLoginRecord, *, allow_disabled: bool=False) -> dict:
        node=connection.execute("SELECT * FROM cluster_nodes WHERE id=? AND kind='ssh' AND (enabled=1 OR ?=1) AND deleted_at IS NULL",(node_id,int(allow_disabled))).fetchone()
        if (node is None or node['node_key']!=record.node_key
                or hashlib.sha256(node['config_json'].encode()).hexdigest()!=record.node_config_sha256):
            raise ValueError('原草稿节点或SSH配置已经变化')
        preparation=strict_json((node['preparation_json'] or '{}').encode(),65536)
        if preparation.get('state')!='prepared' or preparation.get('release')!=record.runtime_release:
            raise ValueError('原草稿节点需要先准备同批控制组件')
        environment=connection.execute('SELECT * FROM account_environments WHERE environment_id=?',(record.work.environment_id,)).fetchone()
        if (environment is None or environment['name']!=record.work.name
                or environment['account_id']!=record.saved_account_id
                or environment['state'] not in ('ready','stopped')
                or record.scope is not None and environment['generation']!=record.scope.generation):
            raise ValueError('原NULL草稿环境或实际代次已经变化')
        if any(environment[key] for key in ('container_id','network_container_id','sender_container_id')):
            raise ValueError('远程草稿不能接管已有本机容器')
        formal=connection.execute('SELECT * FROM accounts WHERE name=? OR profile_path=?',
            (record.work.name,'profiles/'+record.work.name)).fetchall()
        if record.saved_account_id is None:
            if formal:
                raise ValueError('正式或软删除账号仍引用原草稿名称或profile')
        elif (len(formal)!=1 or formal[0]['id']!=record.saved_account_id or formal[0]['name']!=record.work.name
                or formal[0]['profile_path']!='profiles/'+record.work.name or formal[0]['cc2api_account_id'] is not None
                or formal[0]['deleted_at'] is not None or formal[0]['enabled']!=0):
            raise ValueError('首次保存账号的原范围或隔离状态已经变化')
        prefix=str(self.data/'flows'/record.work.name)+'/'
        if connection.execute('SELECT 1 FROM runs WHERE environment_id=? OR substr(flows_dir,1,?)=? LIMIT 1',
                (record.work.environment_id,len(prefix),prefix)).fetchone():
            raise ValueError('历史执行仍引用原草稿环境或名称')
        if record.saved_account_id is not None:
            assignment=connection.execute('SELECT * FROM account_node_assignments WHERE account_id=?',(record.saved_account_id,)).fetchone()
            if (assignment is None or assignment['node_id']!=node_id or assignment['revision']!=1 or assignment['phase']!='ready'):
                raise ValueError('首次保存账号的节点归属已经变化')
        return dict(environment)

    def begin(self, node_id: int, preparation: DraftLoginPreparation, *, previous_revision: int | None=None) -> dict:
        """冻结首次或明确恢复的草稿操作，活动旧操作必须先实际收口。

        :param node_id: 管理员选择的已准备SSH节点。
        :param preparation: 已校验原配置；秘密只用于摘要核验。
        :param previous_revision: 替换原已停止操作时的CAS版本。
        :return: 新操作的持久记录。
        """
        preparation=DraftLoginPreparation.model_validate(preparation.model_dump())
        if type(node_id) is not int or node_id<=0 or preparation.work.expires_at<=time.time():
            raise ValueError('草稿节点身份或本次授权截止无效')
        with self.store.lock:
            connection=self.store.database()
            try:
                with connection:
                    connection.execute('BEGIN IMMEDIATE')
                    node=connection.execute('SELECT config_json FROM cluster_nodes WHERE id=?',(node_id,)).fetchone()
                    if node is None:
                        raise ValueError('草稿节点不存在')
                    old_row=connection.execute('SELECT * FROM node_login_drafts WHERE environment_id=?',(preparation.work.environment_id,)).fetchone()
                    record=CentralDraftLoginRecord(work=preparation.work,node_key=preparation.node_key,
                        node_config_sha256=hashlib.sha256(node['config_json'].encode()).hexdigest(),
                        runtime_release=self.release,previous=preparation.previous)
                    if old_row is not None:
                        old=self._decode(old_row)
                        frozen=CentralDraftLoginRecord.model_validate(old['record'])
                        if frozen.work.id==record.work.id:
                            if (old['node_id']!=node_id or frozen.work!=record.work or frozen.node_key!=record.node_key
                                    or frozen.previous!=record.previous or frozen.runtime_release!=self.release
                                    or frozen.node_config_sha256!=record.node_config_sha256):
                                raise ValueError('原草稿操作冻结内容已经变化')
                            return old
                        if (old['phase']!='closed' or frozen.saved_account_id is not None
                                or type(previous_revision) is not int or old['revision']!=previous_revision
                                or old['node_id']!=node_id or frozen.work.sid==record.work.sid
                                or frozen.work.draft_generation==record.work.draft_generation or frozen.scope!=record.previous
                                or frozen.work.preparation_sha256!=record.work.preparation_sha256 or frozen.work.version!=record.work.version):
                            raise ValueError('新草稿会话必须先核对原停止回执、节点与CAS版本')
                        if frozen.node_receipt is not None and frozen.node_receipt.commit is not None:
                            raise ValueError('原草稿授权已进入提交，请继续原操作')
                    elif preparation.previous is not None or previous_revision is not None:
                        raise ValueError('首次草稿不能引用不存在的前代操作')
                    environment=self._current(connection,node_id,record)
                    if strict_json(environment['fingerprint_json'].encode(),65536)!=strict_json(preparation.fingerprint_json.encode(),65536):
                        raise ValueError('原中央草稿画像已经变化')
                    now=time.time()
                    if old_row is None:
                        connection.execute('INSERT INTO node_login_drafts(environment_id,node_id,operation_id,sid,generation,phase,record_json,created_at,updated_at) '
                            "VALUES(?,?,?,?,?,'preparing',?,?,?)",(record.work.environment_id,node_id,record.work.id,record.work.sid,
                            record.work.draft_generation,record.model_dump_json(),now,now))
                    else:
                        connection.execute("UPDATE node_login_drafts SET operation_id=?,sid=?,generation=?,phase='preparing',"
                            'record_json=?,revision=revision+1,updated_at=? WHERE environment_id=? AND revision=?',
                            (record.work.id,record.work.sid,record.work.draft_generation,record.model_dump_json(),now,
                            record.work.environment_id,previous_revision))
            finally:
                connection.close()
        return self.get(record.work.id)

    def admit(self, operation_id: str) -> dict:
        """新操作前核对冻结节点与真实代次。:param operation_id: 原操作。:return: 当前仍可准入的记录。"""
        value=self.get(operation_id)
        if value['phase'] not in ('preparing','active','submitting'):
            raise ValueError('原草稿正在收口或需要先对账')
        connection=self.store.database()
        try:
            self._current(connection,value['node_id'],CentralDraftLoginRecord.model_validate(value['record']))
            return value
        finally:
            connection.close()

    def preparation(self, row: dict) -> DraftLoginPreparation:
        """只读原私有准备，中央消费者共同核对冻结工作、节点及前代。

        :param row: 本账本解码后的原记录。
        :return: 完整原配置；不构造运行时或读取中央HOME。
        """
        record=CentralDraftLoginRecord.model_validate(row['record'])
        path=self.data/'node-draft-logins'/record.work.environment_id/record.work.id/'preparation.json'
        value=DraftLoginPreparation.model_validate(strict_json(safe_read(path,2*1024*1024,private=True),2*1024*1024))
        if value.work!=record.work or value.node_key!=record.node_key or value.previous!=record.previous:
            raise ValueError('原中央草稿私有配置与冻结记录不一致')
        return value

    def guard_delete(self, operation_id: str) -> dict:
        """在节点实际清理前核对中央NULL、历史和首次配置归属。

        :param operation_id: 原草稿操作。
        :return: 可继续清理的原记录，暂停节点仍可收口旧资源。
        """
        row=self.get(operation_id)
        record=CentralDraftLoginRecord.model_validate(row['record'])
        if record.saved_account_id is not None or record.node_receipt is not None and record.node_receipt.commit is not None:
            raise ValueError('已进入保存的草稿必须继续原提交')
        if record.scope is None and (record.start_intent or record.grant is not None):
            raise ValueError('原草稿输入许可仍需核对')
        connection=self.store.database()
        try:
            self._current(connection,row['node_id'],record,allow_disabled=True)
        finally:
            connection.close()
        return row

    def check_delete(self, receipt: DraftLoginDeleted, *, finish: bool=False) -> None:
        """核对中央引用后，按原Node清理事实条件删除NULL环境及草稿记录。

        :param receipt: 原Node环境外的完整删除回执。
        :param finish: 本地资料已清理时，在短事务内收口数据库。
        :return: None；正式账号、历史、代次及本机角色冲突保持保护。
        """
        receipt=DraftLoginDeleted.model_validate(receipt.model_dump())
        scope=receipt.scope
        with self.store.lock:
            connection=self.store.database()
            try:
                with connection:
                    connection.execute('BEGIN IMMEDIATE')
                    stored=connection.execute('SELECT * FROM node_login_drafts WHERE environment_id=?',(scope.environment_id,)).fetchone()
                    environment=connection.execute('SELECT * FROM account_environments WHERE environment_id=?',(scope.environment_id,)).fetchone()
                    if stored is None:
                        if environment is not None:
                            raise ValueError('原中央草稿清理记录缺失，环境仍需核对')
                        # 两行在同一事务删除；重复尾段只清原标记，不能再次清理后来复用名称的资料。
                        return
                    if stored is not None:
                        row=self._decode(stored)
                        if (row['phase']!='deleting' or row['saved_account_id'] is not None
                                or (row['record']['node_receipt'] or {}).get('commit') is not None):
                            raise ValueError('原草稿删除阶段或范围已经变化')
                        if isinstance(scope,DraftLoginPreparationScope):
                            record=CentralDraftLoginRecord.model_validate(row['record'])
                            work=record.work
                            expected={'operation_id':work.id,'node_key':record.node_key,'environment_id':work.environment_id,
                                'name':work.name,'draft_generation':work.draft_generation,'source':work.source,
                                'preparation_sha256':work.preparation_sha256}
                            if (record.scope is not None or record.start_intent or record.grant is not None
                                    or any(getattr(scope,key)!=value for key,value in expected.items())):
                                raise ValueError('原尚未启动准备的清理范围已经变化')
                            generation=record.previous.generation if record.previous is not None else 0
                            if scope.generation<generation:
                                raise ValueError('原Node准备清理代次不能回退')
                        else:
                            if row['record']['scope']!=scope.model_dump():
                                raise ValueError('原草稿实际删除范围已经变化')
                            generation=scope.generation
                    if environment is not None and (environment['account_id'] is not None or environment['name']!=scope.name
                            or environment['generation']!=generation
                            or any(environment[key] for key in ('container_id','network_container_id','sender_container_id'))):
                        raise ValueError('原中央NULL草稿环境已经变化')
                    if connection.execute('SELECT 1 FROM account_environments WHERE name=? AND environment_id<>?',
                            (scope.name,scope.environment_id)).fetchone():
                        raise ValueError('其他NULL环境仍引用原名称，资料清理需要核对')
                    if connection.execute('SELECT 1 FROM accounts WHERE name=? OR profile_path=? LIMIT 1',
                            (scope.name,'profiles/'+scope.name)).fetchone():
                        raise ValueError('正式或软删除账号仍引用原中央草稿')
                    prefix=str(self.data/'flows'/scope.name)+'/'
                    if connection.execute('SELECT 1 FROM runs WHERE environment_id=? OR substr(flows_dir,1,?)=? LIMIT 1',
                            (scope.environment_id,len(prefix),prefix)).fetchone():
                        raise ValueError('历史执行仍引用原中央草稿')
                    if finish:
                        if stored is not None:
                            connection.execute("DELETE FROM node_login_drafts WHERE environment_id=? AND operation_id=? AND revision=? AND phase='deleting'",
                                (scope.environment_id,scope.operation_id,row['revision']))
                        connection.execute('DELETE FROM account_environments WHERE environment_id=? AND name=? AND account_id IS NULL AND generation=?',
                            (scope.environment_id,scope.name,generation))
            finally:
                connection.close()

    def checkpoint(self, operation_id: str, revision: int, phase: str, **changes) -> dict:
        """按CAS保存实际范围、有限证明或原Node回执。

        :param operation_id: 原操作。
        :param revision: 本次已读版本。
        :param phase: 新阶段。
        :param changes: 原范围首次观察或单调证据。
        :return: 新版本私有记录。
        """
        if set(changes)-{'scope','grant','start_intent','node_receipt','files','failure'}:
            raise ValueError('草稿检查点超出允许证据范围')
        # 启动意图已落盘后，Node可能先于轮询完成授权；按实际提交回执推进，避免依赖轮询时序。
        transitions={'preparing':{'preparing','active','stopping','submitting','reconcile','deleting','closed'},
            'active':{'active','stopping','submitting','reconcile'},'stopping':{'stopping','closed','reconcile','deleting'},
            'submitting':{'submitting','reconcile'},'reconcile':{'reconcile','preparing','active','stopping','submitting','deleting','closed'},
            'deleting':{'deleting'},'closed':{'closed','deleting'}}
        with self.store.lock:
            connection=self.store.database()
            try:
                with connection:
                    connection.execute('BEGIN IMMEDIATE')
                    value=self._decode(connection.execute('SELECT * FROM node_login_drafts WHERE operation_id=?',(operation_id,)).fetchone())
                    if type(revision) is not int or value['revision']!=revision:
                        raise ValueError('草稿版本已变化，请先读取原操作')
                    old=CentralDraftLoginRecord.model_validate(value['record'])
                    record=CentralDraftLoginRecord.model_validate({**value['record'],**changes})
                    if phase not in transitions.get(value['phase'],set()) or old.node_receipt is not None and old.node_receipt.commit is not None and phase not in ('submitting','reconcile'):
                        raise ValueError('草稿阶段不能跳过原提交或恢复边界')
                    if value['phase']=='closed' and record!=old:
                        raise ValueError('原草稿停止历史已经固定')
                    if old.scope is not None and record.scope!=old.scope or old.start_intent and not record.start_intent:
                        raise ValueError('原草稿实际范围与启动意图必须保留')
                    if old.files is not None and record.files!=old.files:
                        raise ValueError('原草稿完整授权文件索引必须保留')
                    if old.grant is not None and record.grant!=old.grant:
                        if record.grant is None or record.grant.sequence!=old.grant.sequence+1 or record.grant.not_after<old.grant.not_after:
                            raise ValueError('草稿证明续接序号或截止不能回退')
                    if old.grant is None and record.grant is not None and record.grant.sequence!=1:
                        raise ValueError('草稿首个证明序号必须为1')
                    self._check_receipt(old,record)
                    if old.scope is None and record.scope is not None:
                        environment=self._current(connection,value['node_id'],old)
                        if record.scope.generation<environment['generation']:
                            raise ValueError('原Node实际环境代次不能回退')
                        connection.execute('UPDATE account_environments SET generation=? WHERE environment_id=? AND account_id IS NULL',
                            (record.scope.generation,record.work.environment_id))
                    if not old.start_intent and record.start_intent or record.grant!=old.grant:
                        self._current(connection,value['node_id'],record)
                    self._validate_phase(phase,record)
                    self._write(connection,value,phase,record)
            finally:
                connection.close()
        return self.get(operation_id)

    def finish(self, operation_id: str, revision: int, activation: DraftLoginActivated, deployment_id: str) -> dict:
        """原Node真实ID激活及原来源收口后，同事务启用账号并关闭草稿。

        :param operation_id: 原首次提交操作。
        :param revision: 原CAS版本。
        :param activation: 原Node受信激活回执。
        :param deployment_id: 本次原运行时部署身份。
        :return: 原关闭记录，重复完成保留当前账号后续状态。
        """
        activation=DraftLoginActivated.model_validate(activation.model_dump())
        if not isinstance(deployment_id,str) or re.fullmatch('[a-z0-9][a-z0-9-]{0,35}',deployment_id) is None:
            raise ValueError('原草稿部署身份无效')
        with self.store.lock:
            connection=self.store.database()
            try:
                with connection:
                    connection.execute('BEGIN IMMEDIATE')
                    value=self._decode(connection.execute('SELECT * FROM node_login_drafts WHERE operation_id=?',(operation_id,)).fetchone())
                    record=CentralDraftLoginRecord.model_validate({**value['record'],'activation':activation})
                    if value['phase']=='closed':
                        if record.model_dump()!=value['record']:
                            raise ValueError('原草稿关闭后的激活回执已经固定')
                        return value
                    if type(revision) is not int or value['revision']!=revision or value['phase']!='submitting':
                        raise ValueError('原草稿提交阶段或版本已变化')
                    self._current(connection,value['node_id'],record)
                    source=connection.execute('SELECT record_json FROM local_credential_authorizations WHERE account_id=?',
                        (record.saved_account_id,)).fetchone()
                    if source is not None:
                        proof=strict_json(source['record_json'].encode(),65536)
                        expected={'schema':1,'account_id':record.saved_account_id,'deployment_id':deployment_id,
                            'cli_version':record.work.version,'environment_id':record.work.environment_id,
                            'refresh_sha256':record.node_receipt.commit.refresh_sha256}
                        if (not isinstance(proof,dict) or type(proof.get('schema')) is not int
                                or type(proof.get('account_id')) is not int or any(proof.get(key)!=item for key,item in expected.items())
                                or any(not isinstance(proof.get(key),str) or not proof[key] for key in ('device_id','email','account_uuid'))):
                            raise ValueError('原草稿授权来源证明与冻结范围不一致')
                    self._validate_phase('closed',record)
                    enabled=connection.execute('UPDATE accounts SET enabled=1 WHERE id=? AND name=? AND enabled=0 '
                        'AND cc2api_account_id IS NULL AND deleted_at IS NULL',(record.saved_account_id,record.work.name))
                    if enabled.rowcount!=1:
                        raise ValueError('原草稿正式账号启用状态已经变化')
                    self._write(connection,value,'closed',record)
            finally:
                connection.close()
        return self.get(operation_id)

    @staticmethod
    def _check_receipt(old: CentralDraftLoginRecord, record: CentralDraftLoginRecord) -> None:
        previous,current=old.node_receipt,record.node_receipt
        if previous is None:
            return
        if current is None or previous.phase=='closed' and current.phase!='closed':
            raise ValueError('原Node草稿停止事实不能回退')
        if previous.result is not None and current.result!=previous.result:
            raise ValueError('原Node草稿执行定位必须保留')
        if previous.discarded is True and current.discarded is not True:
            raise ValueError('原草稿完整删除事实必须保留')
        if previous.commit is not None:
            commit=current.commit
            stages=('frozen','home_saved','saved','accepted')
            if (commit is None or stages.index(commit.stage)<stages.index(previous.commit.stage)
                    or commit.model_dump(exclude={'stage','cleanup_pending'})!=previous.commit.model_dump(exclude={'stage','cleanup_pending'})
                    or not previous.commit.cleanup_pending and commit.cleanup_pending):
                raise ValueError('原草稿冻结授权与保存事实必须保留')

    @staticmethod
    def _write(connection, value: dict, phase: str, record: CentralDraftLoginRecord) -> None:
        result=connection.execute('UPDATE node_login_drafts SET phase=?,saved_account_id=?,record_json=?,revision=revision+1,updated_at=? '
            'WHERE operation_id=? AND revision=?',(phase,record.saved_account_id,record.model_dump_json(),time.time(),value['operation_id'],value['revision']))
        if result.rowcount!=1:
            raise ValueError('草稿版本已变化')

    def save_account(self, operation_id: str, revision: int, preparation: DraftLoginPreparation,
            five_hour_limit: int, seven_day_limit: int) -> dict:
        """同一事务首次创建停用账号、发布原节点归属并认领原NULL环境。

        :param operation_id: 原已完成Node授权收口的操作。
        :param revision: 原CAS版本。
        :param preparation: 原私有配置，重新核对完整摘要后写入正式字段。
        :param five_hour_limit: 原产品五小时额度默认值。
        :param seven_day_limit: 原产品七天额度默认值。
        :return: 仍处于submitting的原记录，重复调用返回原真实账号。
        """
        preparation=DraftLoginPreparation.model_validate(preparation.model_dump())
        if any(type(item) is not int or not 1<=item<=100 for item in (five_hour_limit,seven_day_limit)):
            raise ValueError('首次账号额度默认值无效')
        with self.store.lock:
            connection=self.store.database()
            try:
                with connection:
                    connection.execute('BEGIN IMMEDIATE')
                    value=self._decode(connection.execute('SELECT * FROM node_login_drafts WHERE operation_id=?',(operation_id,)).fetchone())
                    record=CentralDraftLoginRecord.model_validate(value['record'])
                    if record.work!=preparation.work or record.node_key!=preparation.node_key or record.previous!=preparation.previous:
                        raise ValueError('首次保存配置与原冻结草稿不一致')
                    if value['phase']!='submitting' or not record.accepted:
                        raise ValueError('首次保存必须先完成原Node授权、实际停止和暂存清理')
                    self._current(connection,value['node_id'],record)
                    if record.saved_account_id is not None:
                        return value
                    if type(revision) is not int or value['revision']!=revision:
                        raise ValueError('草稿版本已变化，请先读取原操作')
                    settings=preparation.settings
                    cursor=connection.execute('INSERT INTO accounts(name,profile_path,upstream_proxy_scheme,upstream_socks5_host,'
                        'upstream_socks5_port,upstream_socks5_user,upstream_socks5_pass,timezone,enabled,'
                        'warmup_quota_5h_limit_percent,warmup_quota_7d_limit_percent) VALUES(?,?,?,?,?,?,?,?,0,?,?)',
                        (settings.name,'profiles/'+settings.name,settings.upstream_proxy_scheme,settings.upstream_socks5_host,
                        settings.upstream_socks5_port,settings.upstream_socks5_user,settings.upstream_socks5_pass,settings.timezone,
                        five_hour_limit,seven_day_limit))
                    account_id=cursor.lastrowid
                    # 新账号触发器先建立默认归属；同一事务内改为原节点，首次发布不产生本机执行窗口。
                    assignment=connection.execute('UPDATE account_node_assignments SET node_id=? WHERE account_id=? AND revision=1 AND phase=\'ready\' '
                        "AND node_id=(SELECT id FROM cluster_nodes WHERE node_key='local')",(value['node_id'],account_id))
                    if assignment.rowcount!=1:
                        raise ValueError('首次节点归属初始化需要核对')
                    claimed=connection.execute('UPDATE account_environments SET account_id=? WHERE environment_id=? AND name=? AND account_id IS NULL',
                        (account_id,record.work.environment_id,record.work.name))
                    if claimed.rowcount!=1:
                        raise ValueError('原NULL草稿环境已经被认领')
                    saved=CentralDraftLoginRecord.model_validate({**record.model_dump(),'saved_account_id':account_id})
                    self._write(connection,value,'submitting',saved)
            finally:
                connection.close()
        return self.get(operation_id)
