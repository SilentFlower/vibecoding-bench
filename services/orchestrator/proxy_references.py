"""代理目录的只读引用投影，凭据仅参与内部摘要匹配。"""
import hashlib
import ipaddress
import json


def connection_fingerprint(account: dict) -> str | None:
    """规范化分列连接并生成与网关相同的摘要。

    :param account: 任务账号或草稿私有连接字段
    :return: SHA256；直连返回 None
    """
    host = str(account.get('upstream_socks5_host') or '').strip().strip('[]')
    if not host:
        return None
    try:
        host = str(ipaddress.ip_address(host))
    except ValueError:
        host = host.encode('idna').decode('ascii').lower()
    protocol = account.get('upstream_proxy_scheme') or 'socks5'
    if protocol not in ('http', 'socks5', 'socks5h'):
        raise ValueError('代理类型无效')
    port = int(account.get('upstream_socks5_port') or (80 if protocol == 'http' else 1080))
    if not 1 <= port <= 65535:
        raise ValueError('代理端口无效')
    fields = [protocol, host, port, account.get('upstream_socks5_user') or '', account.get('upstream_socks5_pass') or '']
    return hashlib.sha256(json.dumps(fields, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()


def collect_references(database, drafts) -> dict:
    """一次读取账号并恢复草稿私有连接，任何未知状态保留保护。

    :param database: 数据库连接工厂
    :param drafts: 草稿存储；独立旧部署可为空
    :return: 内部引用及完整性标志，禁止向浏览器转发摘要
    """
    connection = database()
    try:
        # 已绑定任务由网关权威配置计数，避免同一个账号重复显示。
        rows = connection.execute('SELECT id,name,enabled,upstream_proxy_scheme,upstream_socks5_host,'
            'upstream_socks5_port,upstream_socks5_user,upstream_socks5_pass FROM accounts '
            'WHERE deleted_at IS NULL AND cc2api_account_id IS NULL').fetchall()
    finally:
        connection.close()
    result, complete = [], True
    for raw in rows:
        account = dict(raw)
        try:
            fingerprint = connection_fingerprint(account)
            if fingerprint:
                result.append({'kind': 'task', 'id': str(account['id']), 'name': account['name'],
                    'fingerprint': fingerprint, 'status': 'active' if account['enabled'] else 'disabled', 'in_flight': None})
        except (ValueError, TypeError, UnicodeError):
            complete = False
    if drafts:
        for row in drafts.rows():
            try:
                drafts.record(row)
                fingerprint = connection_fingerprint(drafts.account(row))
                if fingerprint:
                    result.append({'kind': 'draft', 'id': row['environment_id'], 'name': row['name'],
                        'fingerprint': fingerprint, 'status': 'draft', 'in_flight': None})
            except (ValueError, KeyError, TypeError, OSError):
                complete = False
    return {'references': result, 'complete': complete}
