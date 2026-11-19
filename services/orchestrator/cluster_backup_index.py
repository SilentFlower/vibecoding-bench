"""离线备份的中央/Node范围索引与组合恢复对应检查。"""
from __future__ import annotations

import re
import json
import sqlite3
from contextlib import closing
from pathlib import Path

from storage_maintenance import read_storage_json


def cluster_backup_scope(data: Path) -> dict | None:
    """从已复制的离线资料读取安装与节点范围。

    :param data: 备份内已校验的数据根。
    :return: 公开安装身份与所需节点；单机资料为None。
    """
    marker=data/'cluster-node.json'
    if marker.exists() or marker.is_symlink():
        installation=read_storage_json(marker,maximum_bytes=8192,private=False)
        if (not isinstance(installation,dict) or installation.get('protocol')!=1
                or re.fullmatch(r'[a-f0-9]{32}',str(installation.get('node_key',''))) is None
                or re.fullmatch(r'[a-z0-9][a-z0-9-]{0,35}',str(installation.get('deployment_id',''))) is None):
            raise ValueError('Node备份安装身份无效')
        return {'protocol':1,'kind':'node','node_key':installation['node_key'],'deployment_id':installation['deployment_id']}
    database=data/'bench/db.sqlite'
    if not database.exists():
        return None
    with closing(sqlite3.connect(database.as_uri()+'?mode=ro&immutable=1',uri=True)) as connection:
        if not connection.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='cluster_nodes'").fetchone():
            return None
        nodes=[{'node_id':row[0],'node_key':row[1]} for row in connection.execute(
            "SELECT id,node_key FROM cluster_nodes WHERE kind='ssh' AND deleted_at IS NULL ORDER BY id")]
    if not nodes:
        return None
    deployment=read_storage_json(data/'.v3-deployment.json',maximum_bytes=8192,private=False)
    if not isinstance(deployment,dict) or not isinstance(deployment.get('deployment'),str):
        raise ValueError('中央备份缺少部署归属')
    return {'protocol':1,'kind':'central','deployment_id':deployment['deployment'],'nodes':nodes}


def verify_cluster_correspondence(central: Path, nodes: dict[str,Path]) -> dict:
    """只读核对中央冻结归属与所有Node离线资料。

    :param central: 中央备份的数据根。
    :param nodes: 已验证安装身份的Node数据根。
    :return: 环境数量及需要沿原维护状态恢复的环境数量。
    """
    environments,reconcile,pending=0,0,0
    with closing(sqlite3.connect((central/'bench/db.sqlite').as_uri()+'?mode=ro&immutable=1',uri=True)) as connection:
        connection.row_factory=sqlite3.Row
        tables={row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        for table,terminal in (('node_executions',('closed',)),('node_login_drafts',('closed',)),('node_migrations',('completed','cancelled'))):
            if table in tables:
                pending+=connection.execute('SELECT count(*) FROM '+table+' WHERE phase NOT IN ('+','.join('?' for _ in terminal)+')',terminal).fetchone()[0]
        if 'account_credential_ownerships' in tables:
            for row in connection.execute('SELECT record_json FROM account_credential_ownerships'):
                try:
                    record=json.loads(row[0])
                except ValueError:
                    record={}
                if not isinstance(record,dict) or record.get('phase')!='ready':
                    pending+=1
        rows=connection.execute('SELECT e.*,b.revision,b.phase AS assignment_phase,n.node_key FROM account_environments e '
            'JOIN account_node_assignments b ON b.account_id=e.account_id JOIN cluster_nodes n ON n.id=b.node_id '
            "WHERE n.kind='ssh' AND n.deleted_at IS NULL").fetchall()
        for expected in rows:
            data=nodes[expected['node_key']]
            path=data/'node-execution.sqlite'
            observed=None
            if path.exists():
                with closing(sqlite3.connect(path.as_uri()+'?mode=ro&immutable=1',uri=True)) as node:
                    node.row_factory=sqlite3.Row
                    if node.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='account_environments'").fetchone():
                        observed=node.execute('SELECT * FROM account_environments WHERE environment_id=?',
                            (expected['environment_id'],)).fetchone()
            if observed is None:
                if expected['generation']==0:
                    continue
                raise ValueError('Node备份缺少中央仍引用的环境')
            draft=(connection.execute("SELECT saved_account_id FROM node_login_drafts WHERE environment_id=? AND phase<>'closed'",
                (expected['environment_id'],)).fetchone() if 'node_login_drafts' in tables else None)
            if (draft is not None and draft['saved_account_id']==expected['account_id']
                    and observed['account_id'] in (None,expected['account_id']) and observed['name']==expected['name']):
                environments+=1
                reconcile+=1
                continue
            if observed['account_id']!=expected['account_id'] or observed['name']!=expected['name']:
                raise ValueError('Node备份环境属于另一账号')
            root=data/'environments'/expected['environment_id']
            marker=read_storage_json(root/'runtime/node-assignment.json',maximum_bytes=8192)
            if (not isinstance(marker,dict) or marker.get('node_key')!=expected['node_key']
                    or marker.get('account_id')!=expected['account_id'] or marker.get('environment_id')!=expected['environment_id']):
                raise ValueError('Node备份环境的安装归属不一致')
            environments+=1
            if (expected['assignment_phase']!='ready' or marker.get('phase')!='ready'
                    or marker.get('revision')!=expected['revision'] or observed['generation']!=expected['generation']):
                # 原维护/未知提交属于恢复资料；完整备份仍保留该状态，不能据此开放普通工作。
                reconcile+=1
    return {'environments':environments,'reconcile_required':reconcile,'pending_operations':pending}
