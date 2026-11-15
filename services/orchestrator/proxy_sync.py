"""空闲任务账号与登录草稿的代理同步；由网关持久队列负责重试。"""
import json
import re
from contextlib import ExitStack
from urllib.parse import unquote, urlsplit

from proxy_references import connection_fingerprint


def synchronize_proxy(body, database, db_lock, runtime, drafts, owner_lock, profile_lock, active_login):
    """在原维护锁下同步固定目标，忙碌或未知状态由调用方稍后重试。

    :param body: 内部目标、原连接摘要、新私有连接
    :param database: 数据库连接工厂
    :param db_lock: 数据库写入锁
    :param runtime: 固定账号运行环境
    :param drafts: 登录草稿存储
    :param owner_lock: OAuth所有者锁工厂
    :param profile_lock: 账号画像锁工厂
    :param active_login: 活跃登录判断函数
    :return: 完成、等待或转换后的账号身份
    """
    kind, identity = body['target']['kind'], body['target']['id']
    source, destination = body['source'], body['destination']
    if kind not in ('task', 'draft') or not re.fullmatch(r'[a-f0-9]{64}', source):
        raise ValueError('同步目标无效')
    if not isinstance(identity, str) or not re.fullmatch(r'[a-f0-9]{32}' if kind == 'draft' else r'[1-9][0-9]*', identity):
        raise ValueError('同步身份无效')
    parsed = urlsplit(destination)
    if parsed.scheme not in ('http', 'socks5', 'socks5h') or not parsed.hostname or not parsed.port or parsed.path not in ('', '/') or parsed.query or parsed.fragment:
        raise ValueError('同步连接无效')
    fields = {'upstream_proxy_scheme': parsed.scheme, 'upstream_socks5_host': parsed.hostname,
        'upstream_socks5_port': parsed.port, 'upstream_socks5_user': unquote(parsed.username or ''),
        'upstream_socks5_pass': unquote(parsed.password or '')}

    def read_target():
        if kind == 'draft':
            return drafts.row(identity)
        connection = database()
        try:
            row = connection.execute('SELECT * FROM accounts WHERE id=? AND deleted_at IS NULL', (int(identity),)).fetchone()
            return dict(row) if row else None
        finally:
            connection.close()

    target = read_target()
    if not target:
        return {'complete': True}
    with ExitStack() as locks:
        # 与授权/提交沿用相同锁序，后台同步不等待长时间的人机交互。
        for guard in (owner_lock(target['name']), profile_lock(target['name'])):
            if not guard.acquire(blocking=False):
                return {'complete': False}
            locks.callback(guard.release)
        target = read_target()
        if not target:
            return {'complete': True}
        if kind == 'draft' and target.get('account_id') is not None:
            return {'complete': False, 'task_account_id': target['account_id']}
        if kind == 'task' and target.get('cc2api_account_id') is not None:
            return {'complete': False, 'gateway_account_id': target['cc2api_account_id']}
        if active_login(target['name']):
            return {'complete': False}
        if kind == 'draft':
            drafts.guard(target)
            row = target
        else:
            connection = database()
            try:
                row = connection.execute('SELECT * FROM account_environments WHERE account_id=?', (int(identity),)).fetchone()
                row = dict(row) if row else None
            finally:
                connection.close()
        if row:
            guard = runtime.environment_lock(row['environment_id'])
            if not guard.acquire(blocking=False):
                return {'complete': False}
            locks.callback(guard.release)
        current = drafts.account(target) if kind == 'draft' else target
        if connection_fingerprint(current) != source:
            # 回执丢失或用户已改为其它线路时尊重实际配置，避免覆盖新的选择。
            return {'complete': True}
        if row:
            with runtime.lock:
                busy = bool(runtime.environment_jobs(row['environment_id']))
            if busy or runtime._running_sender_active(row):
                return {'complete': False}
            # 删除旧实例使下次启动按新代理重新解析DNS和网络配置，持久资料继续保留。
            runtime._stop_environment(row, remove=True)
            runtime._update(row, state='stopped')
        if kind == 'draft':
            configuration = json.loads(runtime._sender_config(row).read_text())
            configuration.update(proxy_source=destination, proxy_url=destination)
            runtime._write_sender_config(row, configuration)
        else:
            with db_lock:
                connection = database()
                try:
                    connection.execute('UPDATE accounts SET upstream_proxy_scheme=?,upstream_socks5_host=?,'
                        'upstream_socks5_port=?,upstream_socks5_user=?,upstream_socks5_pass=? '
                        'WHERE id=? AND cc2api_account_id IS NULL AND deleted_at IS NULL', (*fields.values(), int(identity)))
                    connection.commit()
                finally:
                    connection.close()
        return {'complete': True}
