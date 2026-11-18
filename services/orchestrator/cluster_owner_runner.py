"""中央原所有权事务在所属SSH节点执行停止和凭据发布。"""
from __future__ import annotations

import json
import time
from contextlib import contextmanager
from uuid import uuid4
from urllib.error import HTTPError

from account_runtime import RuntimeBusy
from cluster_deployment import node_container_name
from cluster_execution import NodeLocation, NodePreparation
from cluster_owner_contract import OwnerLease, OwnerPrepare, OwnerPublish, OwnerReceipt, OwnerScope
from system_update_contract import safe_read, strict_json


class RemoteOwnerTransitions:
    """沿中央owner/profile锁与原长期回执完成具体Node交接。

    :param sessions: 原中央执行协调器。
    :param ownership: 原长期所有权管理器。
    :param read_profile: 原完整管理镜像读取器。
    """

    def __init__(self, sessions, ownership, read_profile):
        """保存原依赖。:param sessions: 执行协调。:param ownership: 原所有权。:param read_profile: 原镜像读取。:return: None。"""
        self.sessions,self.ownership,self.read_profile=sessions,ownership,read_profile
        self.runtime,self.service,self.gateway=sessions.runtime,sessions.service,sessions.gateway

    def _location(self, account):
        assignment=self.service.store.assignment(account['id'])
        if assignment['kind']!='ssh' or assignment['phase']!='ready':
            raise RuntimeBusy('原账号节点归属正在变化，请完成原迁移')
        row=self.runtime._row(account['name'],account['id'])
        node=self.service.store.get(assignment['node_id'])
        preparation=json.loads(node['preparation_json'] or '{}')
        if preparation.get('state')!='prepared' or preparation.get('release')!=self.sessions.ledger.release:
            raise RuntimeBusy('所属节点凭据交接需要同批控制组件')
        location=NodeLocation(node_key=assignment['node_key'],account_id=account['id'],
            environment_id=row['environment_id'],assignment_revision=assignment['revision'])
        return location,row,assignment,node

    def _rpc(self, account, action, payload, original):
        location,row,assignment,node=original
        value=self.service.connection(assignment['node_id']).execution_environment(
            node_container_name(self.runtime.deployment,location.node_key),payload,'credential-owner-'+action)
        latest=self._location(account)
        if (type(value.get('protocol')) is not int or value['protocol']!=1 or value.get('node_key')!=location.node_key
                or latest[0]!=location or latest[1]['generation']!=row['generation']
                or latest[3]['config_json']!=node['config_json']):
            raise ValueError('原节点凭据交接的范围或SSH配置已经变化')
        receipt=value.get('ownership')
        return OwnerReceipt.model_validate(receipt) if receipt is not None else None

    @contextmanager
    def transition(self, account: dict, target_id: int | None, *, handoff_credentials: bool=True, record=None):
        """原中央绑定事务之前实际停止，提交后按原来源发布Node凭据。

        :param account: 原owner/profile锁内重读的中央账号。
        :param target_id: 原操作目标绑定。
        :param handoff_credentials: 显式删除时关闭凭据发布。
        :param record: 原长期交接回执；缺省从原管理器读取。
        :return: 供原绑定事务使用的上下文。
        """
        original=self._location(account)
        location,row,assignment,node=original
        with self.runtime.environment_lock(row['environment_id']):
            if self.sessions.ledger.active(account['id']):
                raise RuntimeBusy('原节点仍有执行待收口，凭据交接继续等待')
            record=record if record is not None else self.ownership.state(account['id'])
            managed=record is not None and (record['phase']!='ready' or record.get('retired') and not handoff_credentials)
            current=None
            if managed:
                scope=OwnerScope(**location.model_dump(),operation_id=record['input']['operation_id'],generation=row['generation'],
                    previous_binding=record['original_binding'],target_binding=target_id,
                    handoff_credentials=handoff_credentials,retire=not handoff_credentials)
            else:
                if row['generation']!=0 or account.get('cc2api_account_id') is not None or handoff_credentials:
                    current=self._rpc(account,'get',location.model_dump(),original)
                if current is not None and current.phase=='preparing':
                    scope=current.scope
                    if (scope.target_binding!=target_id or scope.handoff_credentials!=handoff_credentials
                            or account.get('cc2api_account_id') not in (scope.previous_binding,scope.target_binding)):
                        raise ValueError('原节点已有另一交接待完成')
                else:
                    scope=OwnerScope(**location.model_dump(),operation_id=uuid4().hex,generation=row['generation'],
                        previous_binding=account.get('cc2api_account_id'),target_binding=target_id,
                        handoff_credentials=handoff_credentials,retire=not handoff_credentials)
            leases=[]
            missing=[]
            try:
                for binding in sorted({value for value in (scope.previous_binding,scope.target_binding) if value is not None}):
                    path=f'/admin/runtime/accounts/{binding}/lease'
                    try:
                        snapshot=self.gateway._request('GET',path)
                    except ValueError as error:
                        if (target_id is not None or binding!=scope.previous_binding or not isinstance(error.__cause__,HTTPError)
                                or error.__cause__.code!=404
                                or any(item['id']==binding for item in self.gateway.list_accounts(require_complete=True))):
                            raise
                        missing.append(binding)
                        continue
                    holder=snapshot['lease']
                    owner='binding:'+scope.operation_id
                    if (holder and holder.get('owner')!=owner and current is not None and current.phase=='published'
                            and holder.get('owner')=='binding:'+current.scope.operation_id and holder.get('exclusive') is True
                            and account.get('cc2api_account_id')==current.scope.target_binding and not snapshot['active']):
                        # 上个非长期事务已发布，释放其同源旧lease后再为新操作取得许可。
                        self.gateway._request('POST',path,{'operation':'release','owner':holder['owner'],'generation':holder['generation']})
                        snapshot=self.gateway._request('GET',path)
                        holder=snapshot['lease']
                    if snapshot['active'] or snapshot.get('waiting') or holder and holder.get('owner')!=owner:
                        raise RuntimeBusy('原绑定仍有活动或等待请求，凭据交接等待排空')
                    if holder and (holder.get('phase')=='reconcile' or holder.get('expires_at',0)<=time.time()):
                        self.gateway._request('POST',path,{'operation':'release','owner':holder['owner'],'generation':holder['generation']})
                        holder=None
                    if holder is None:
                        snapshot=self.gateway._request('POST',path,{'operation':'prepare','owner':owner})
                    proof=OwnerLease(account_id=binding,lease={key:snapshot['lease'].get(key,False) if key=='shared_cli'
                        else snapshot['lease'][key] for key in ('owner','generation','expires_at','exclusive','shared_cli')})
                    leases.append(proof)
                    if snapshot['active'] or snapshot.get('waiting'):
                        raise RuntimeBusy('原绑定活动尚未排空')
                expires=min([int(time.time())+30]+[item.lease.expires_at for item in leases])
                initial=None
                if scope.retire and scope.generation==0 and scope.previous_binding is None:
                    initial=NodePreparation(node_key=scope.node_key,assignment_revision=scope.assignment_revision,
                        account=account,environment=row,gateway_config={},quota_identity='owner-retire',cli_only=True)
                prepare=OwnerPrepare(scope=scope,initial_projection=initial,leases=leases,missing_bindings=missing,not_after=expires)
                receipt=self._rpc(account,'prepare',prepare.model_dump(),original)
                if receipt is None or receipt.scope!=scope or not receipt.stopped:
                    raise ValueError('原节点凭据交接的实际停止待核对')
                if not handoff_credentials:
                    # 删除会级联移除中央分配；先确认Node已退休，避免成功删库后才追认旧归属。
                    receipt=self._rpc(account,'publish',OwnerPublish(**prepare.model_dump()).model_dump(),original)
                    if receipt is None or receipt.scope!=scope or receipt.phase!='published' or not receipt.stopped:
                        raise ValueError('原节点退休停止仍需核对')
                    self.runtime._update(row,state='stopped')
                yield
                if not handoff_credentials:
                    return
                material=None
                if handoff_credentials:
                    profile=self.read_profile(account['name'])
                    top=strict_json(safe_read(self.runtime.data/'profiles'/account['name']/'.claude.json',1024*1024),1024*1024)
                    material={'access_token':profile['access_token'],'expires_at':profile['expires_at'],
                        'refresh_token':profile['refresh_token'] if target_id is None else None,
                        'device_id':top.get('userID'),'account_uuid':profile['account_uuid'],
                        'organization_uuid':profile.get('organization_uuid')}
                publication=OwnerPublish(**prepare.model_dump(),material=material)
                receipt=self._rpc(account,'publish',publication.model_dump(),original)
                if receipt is None or receipt.scope!=scope or receipt.phase!='published' or not receipt.stopped:
                    raise ValueError('原节点凭据发布仍需核对')
                self.runtime._update(row,state='stopped')
            finally:
                for item in reversed(leases):
                    self.gateway._request('POST',f'/admin/runtime/accounts/{item.account_id}/lease',
                        {'operation':'release','owner':item.lease.owner,'generation':item.lease.generation})
