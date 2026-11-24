"""工程账号删除的持久范围与退役登记，保留环境 ID 供历史记录查询。"""
import json


def remember_deletion(connection, account, row, assignment, expected=None):
    """冻结原所有者和节点，重复删除沿同一代次。@param connection 写事务。@param account 工程账号。@param row 专属环境。@param assignment 当前节点。@param expected 后台恢复的原范围。@return 删除范围。"""
    scope = {'account_id': account['id'], 'name': account['name'], 'environment_id': row['environment_id'],
        'generation': row['generation'], 'node_key': assignment['node_key'], 'revision': assignment['revision']}
    previous = json.loads(row['fingerprint_json']).get('account_deletion')
    binding = account.get('cc2api_account_id')
    scope['previous_binding'] = previous['previous_binding'] if previous is not None else binding
    if (assignment.get('phase','ready') != 'ready'
            or previous is not None and (scope != previous or binding not in (None, previous['previous_binding']))
            or expected is not None and scope != expected):
        raise ValueError('原删除操作的账号、绑定、节点或环境代次已变化')
    record = json.dumps(scope, separators=(',', ':'), ensure_ascii=False)
    result = connection.execute("UPDATE account_environments SET fingerprint_json=json_set(fingerprint_json,"
        "'$.account_deletion',json(?)) WHERE environment_id=? AND account_id=? AND name=? AND generation=? "
        "AND (json_extract(fingerprint_json,'$.account_deletion') IS NULL OR json_extract(fingerprint_json,'$.account_deletion')=?)",
        (record, row['environment_id'], account['id'], account['name'], row['generation'], record))
    if result.rowcount != 1:
        raise ValueError('原删除操作的环境范围已变化')
    return scope


def archive_environment(connection, scope):
    """提交已清理的环境并释放名称和所有者槽位。@param connection 账号删除事务。@param scope 冻结的原环境。@return 无。"""
    # 使用工程合法名称以外的保留前缀，旧目录仍由原环境 ID 定位。
    result = connection.execute("UPDATE account_environments SET state='retired',name='retired:' || environment_id,"
        "account_id=NULL WHERE environment_id=:environment_id AND name=:name AND account_id=:account_id "
        "AND generation=:generation AND state='stopped' AND container_id IS NULL "
        "AND network_container_id IS NULL AND sender_container_id IS NULL", scope)
    if result.rowcount != 1:
        raise ValueError('原环境的角色移除结果尚未确认')
