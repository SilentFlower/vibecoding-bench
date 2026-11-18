"""绑定SSH账号的当前Node设备纯读取，沿原Gateway身份准备长期重授权。"""
from __future__ import annotations

import hashlib
import json
import re

from pydantic import BaseModel, ConfigDict, Field, StrictInt, StrictStr

from cluster_deployment import node_container_name
from cluster_execution import NodeInspection, _GatewaySnapshot
from account_isolation import role_container
from system_update_contract import safe_read, strict_json


class BoundIdentityRead(NodeInspection):
    """原绑定及实际代次冻结的当前设备查询。

    :param gateway_account_id: 原网关绑定。
    :param generation: 原Node实际环境代次。
    :param account_identity: 原Gateway配置中的UUID/组织与本地绑定。
    """

    gateway_account_id:StrictInt=Field(ge=1)
    generation:StrictInt=Field(ge=1)
    account_identity:StrictStr=Field(min_length=1,max_length=4096)


class BoundIdentitySnapshot(BaseModel):
    """当前Node身份白名单，原材料留在原所有者。

    :param protocol: 固定协议。
    :param request: 原查询完整范围。
    :param device_id: 当前HOME原设备。
    """

    model_config=ConfigDict(extra='forbid')
    protocol:StrictInt=Field(default=1,ge=1,le=1)
    request:BoundIdentityRead
    device_id:StrictStr=Field(pattern='^[a-f0-9]{64}$')



class BoundProcessSnapshot(BoundIdentitySnapshot):
    """当前Node原进程指标导入回执。

    :param process: 原Gateway进程导入载荷，全部字段由实际Node采样。
    """

    process:dict


def read_bound_process(executor, request: BoundIdentityRead) -> dict:
    """核对原绑定后采样所属Node，复用原进程导入实现。

    :param executor: 已登记Node执行器。
    :param request: 原绑定及完整实际环境范围。
    :return: 不含OAuth材料的进程导入回执。
    """
    with executor._locked(environment_id=request.environment_id):
        identity=_read_bound_identity_locked(executor,request)
        row=executor._inspection_row(NodeInspection.model_validate(request.model_dump(exclude={
            'gateway_account_id','generation','account_identity'})))
        runtime=executor._runtime(_GatewaySnapshot(0,{}))
        try:
            container=role_container(runtime,row,'cli')
            container.reload()
            if container.status!='running':
                raise ValueError('请先准备原Node CLI，再采样进程指标')
            process=runtime.process_identity_import_current(row,container,request.version)
            return BoundProcessSnapshot(**identity,process=process).model_dump()
        finally:
            executor._release_runtime(runtime)


def read_bound_identity(executor, request: BoundIdentityRead) -> dict:
    """读取原Node投影与当前HOME设备，保持纯文件和数据库核对。

    :param executor: 原Node执行器。
    :param request: 原中央绑定、身份和实际代次。
    :return: 固定无令牌设备回执。
    """
    with executor._locked(read_only=True,environment_id=request.environment_id):
        return _read_bound_identity_locked(executor,request)


def _read_bound_identity_locked(executor, request: BoundIdentityRead) -> dict:
    row=executor._inspection_row(NodeInspection(**request.model_dump(include={
        'node_key','account_id','environment_id','assignment_revision','version'})))
    connection=executor.database()
    try:
        account=connection.execute('SELECT * FROM accounts WHERE id=?',(request.account_id,)).fetchone()
    finally:
        connection.close()
    if (account is None or account['cc2api_account_id']!=request.gateway_account_id
            or account['name']!=row['name'] or account['deleted_at'] is not None or row['generation']!=request.generation):
        raise ValueError('原绑定设备的账号或环境代次已经变化')
    profile=strict_json(safe_read(executor.data/'profiles'/account['name']/'.claude.json',1024*1024),1024*1024)
    home=strict_json(safe_read(executor.data/'environments'/request.environment_id/'home/.claude.json',1024*1024),1024*1024)
    expected=strict_json(request.account_identity.encode(),4096)
    if (set(expected)!={'account_id','binding','uuid','org'} or type(expected['account_id']) is not int
            or expected['account_id']!=request.account_id or type(expected['binding']) is not int
            or expected['binding']!=request.gateway_account_id
            or any(value is not None and not isinstance(value,str) for value in (expected['uuid'],expected['org']))):
        raise ValueError('原网关绑定身份范围无效')
    identities=[]
    for top in (profile,home):
        identity=top.get('oauthAccount')
        if (not isinstance(identity,dict) or not isinstance(identity.get('accountUuid'),str)
                or not identity['accountUuid'].strip() or identity.get('organizationUuid') is not None
                and not isinstance(identity['organizationUuid'],str)):
            raise ValueError('原绑定HOME身份不完整')
        current={'uuid':identity['accountUuid'].strip().lower(),'org':(identity.get('organizationUuid') or '').strip().lower()}
        # 原网关仅约束已登记的UUID/组织；Node自身两份稳定身份仍必须相符。
        if any((expected[key] or '').strip() and current[key]!=(expected[key] or '').strip().lower() for key in ('uuid','org')):
            raise ValueError('当前Node与原网关绑定身份不一致')
        identities.append(current)
    if identities[0]!=identities[1]:
        raise ValueError('当前Node与原网关绑定身份不一致')
    device=home.get('userID')
    if (not isinstance(device,str) or re.fullmatch('[a-f0-9]{64}',device) is None
            or profile.get('userID') is not None and profile['userID']!=device):
        raise ValueError('当前Node设备身份需要核对')
    return BoundIdentitySnapshot(request=request,device_id=device).model_dump()


class RemoteBoundIdentity:
    """从原受信SSH连接核对当前设备，不读取中央HOME副本。

    :param sessions: 原中央执行协调及节点服务。
    :param version: 当前选定CLI版本，仅用于固定查询合同。
    """

    def __init__(self, sessions, version) -> None:
        """保存只读依赖。:param sessions: 原执行协调。:param version: 版本读取器。:return: None。"""
        self.sessions,self.version=sessions,version

    def _request(self, account: dict, configuration: dict) -> tuple[BoundIdentityRead,dict,str]:
        assignment=self.sessions.service.store.assignment(account['id'])
        if (assignment['kind']!='ssh' or assignment['phase']!='ready'
                or type(account.get('cc2api_account_id')) is not int
                or configuration.get('account_id')!=account['cc2api_account_id']):
            raise ValueError('原绑定身份的节点或网关归属需要核对')
        connection=self.sessions.service.store.database()
        try:
            actual=connection.execute('SELECT e.environment_id,e.generation,a.name,a.cc2api_account_id,a.deleted_at '
                'FROM account_environments e JOIN accounts a ON a.id=e.account_id WHERE a.id=?',(account['id'],)).fetchone()
        finally:
            connection.close()
        if (actual is None or actual['name']!=account['name'] or actual['cc2api_account_id']!=account['cc2api_account_id']
                or actual['deleted_at'] is not None):
            raise ValueError('原绑定身份的中央账号已经变化')
        identity=json.dumps({'account_id':account['id'],'binding':account['cc2api_account_id'],
            'uuid':configuration.get('account_uuid'),'org':configuration.get('organization_uuid')},sort_keys=True)
        request=BoundIdentityRead(node_key=assignment['node_key'],account_id=account['id'],gateway_account_id=account['cc2api_account_id'],
            environment_id=actual['environment_id'],assignment_revision=assignment['revision'],generation=actual['generation'],
            version=self.version(account),account_identity=identity)
        node=self.sessions.service.store.get(assignment['node_id'])
        preparation=strict_json((node['preparation_json'] or '{}').encode(),65536)
        if preparation.get('state')!='prepared' or preparation.get('release')!=self.sessions.ledger.release:
            raise ValueError('原绑定身份的Node发布需要核对')
        return request,assignment,hashlib.sha256(node['config_json'].encode()).hexdigest()

    def read(self, account: dict, configuration: dict) -> dict:
        """读取一次原Node当前设备，前后归属或配置变化保持失败。

        :param account: 原账号行。
        :param configuration: 原Gateway当前配置。
        :return: 原CredentialOwnership所需的设备与环境。
        """
        return self._read(account,configuration,'account-bound-identity')

    def process(self, account: dict, configuration: dict) -> dict:
        """读取原Node进程载荷，保持完整范围的前后核对。

        :param account: 原绑定账号。
        :param configuration: 原Gateway当前配置。
        :return: 原进程导入接口载荷。
        """
        return self._read(account,configuration,'account-bound-process')

    def _read(self, account: dict, configuration: dict, operation: str) -> dict:
        request,assignment,digest=self._request(account,configuration)
        result=self.sessions.service.connection(assignment['node_id']).execution_environment(
            node_container_name(self.sessions.runtime.deployment,request.node_key),request.model_dump(),operation)
        if type(result.get('protocol')) is not int or result['protocol']!=1 or result.get('node_key')!=request.node_key:
            raise ValueError('绑定身份读取来自其他Node')
        try:
            snapshot=(BoundProcessSnapshot if operation=='account-bound-process' else BoundIdentitySnapshot).model_validate(result.get('identity'))
        except (ValueError,TypeError):
            raise ValueError('原Node绑定设备回执需要核对') from None
        fresh_request,fresh_assignment,fresh_digest=self._request(account,configuration)
        if snapshot.request!=request or fresh_request!=request or fresh_assignment!=assignment or fresh_digest!=digest:
            raise ValueError('绑定设备读取期间原Node归属已经变化')
        if isinstance(snapshot,BoundProcessSnapshot):
            value=snapshot.process
            if (value.get('device_id')!=snapshot.device_id or value.get('environment_id')!=request.environment_id
                    or value.get('cli_version')!=request.version
                    or set(value)!={'device_id','account_uuid','email','environment_id','cli_version','canonical_process'}
                    or not isinstance(value.get('canonical_process'),dict)):
                raise ValueError('原Node进程载荷的身份或字段范围需要核对')
            return value
        return {'device_id':snapshot.device_id,'environment_id':request.environment_id}
