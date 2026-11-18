"""独立节点凭据维护共用的实际账号、代次与HOME身份核对。"""
from __future__ import annotations

import json

from cluster_credentials_contract import CredentialStatusRead
from cluster_execution import NodeExecution, NodeInspection
from system_update_contract import safe_read, strict_json


def read_node_credential_account(executor: NodeExecution, request: CredentialStatusRead, *,
                                 stopping: bool = False, require_home: bool = False,
                                 allow_inactive: bool = False) -> tuple[dict,dict]:
    """读取原独立账号；新输入复核当前HOME，原停止保留同代收口能力。

    :param executor: 原节点实际执行器。
    :param request: 原环境、分配版本、代次及稳定身份。
    :param stopping: 原工作停止时允许已停用或身份产物变化。
    :param require_home: 实际输入前要求当前HOME身份存在。
    :param allow_inactive: 仅受信材料/身份纯读与明确登录允许原停用状态。
    :return: 已核对的账号和原环境行。
    """
    row=executor._inspection_row(NodeInspection(node_key=request.node_key,account_id=request.account_id,
        environment_id=request.environment_id,assignment_revision=request.assignment_revision,version=request.version))
    connection=executor.database()
    try:
        stored=connection.execute('SELECT * FROM accounts WHERE id=?',
            (request.account_id,)).fetchone()
    finally:
        connection.close()
    if (stored is None or stored['cc2api_account_id'] is not None or row['generation']!=request.generation
            or stored['name']!=row['name']):
        raise ValueError('独立凭据所有者的账号或环境代次已变化')
    account=dict(stored)
    if stopping:
        return account,row
    if (not account['enabled'] and not allow_inactive) or account['deleted_at'] is not None:
        raise ValueError('原节点凭据账号已停用或删除')
    top=strict_json(safe_read(executor.data/'profiles'/account['name']/'.claude.json',1024*1024),1024*1024)
    identities=[top]
    try:
        identities.append(strict_json(safe_read(executor.data/'environments'/request.environment_id/'home/.claude.json',
            1024*1024),1024*1024))
    except FileNotFoundError:
        # 首次受控准备可补齐HOME；实际启动前再次校验准备后的当前HOME。
        if require_home:
            raise ValueError('节点当前HOME身份缺失，执行启动等待核对') from None
    for value in identities:
        oauth=value.get('oauthAccount')
        if not isinstance(oauth,dict) or not oauth.get('accountUuid'):
            raise ValueError('节点当前凭据所有者身份暂不可读')
        identity={'account_id':request.account_id,'binding':None,'uuid':oauth['accountUuid'],'org':oauth.get('organizationUuid')}
        if json.dumps(identity,sort_keys=True)!=request.account_identity:
            raise ValueError('原节点凭据身份已经变化')
    return account,row
