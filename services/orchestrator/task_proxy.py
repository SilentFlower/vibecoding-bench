"""任务代理选择快照与交互保存，私有连接只在受信任服务之间传递。"""
import hashlib
import hmac
import json
import re
import threading
from contextlib import ExitStack, contextmanager
from urllib.parse import quote, unquote, urlsplit


class ProxySelectionConflict(ValueError):
    """选择时的账号、关联或连接已变化，需要重新读取。"""

    def __init__(self, message, code='changed'):
        """保存固定错误类型。@param message 公开说明。@param code 受控分类。@return None。"""
        super().__init__(message)
        self.code = code


class TaskProxyActivity:
    """登记同一编排进程内的未决切线，沿既有单进程维护锁边界保护目录。"""

    def __init__(self):
        """建立有锁的活动集合。@return None。"""
        self._lock = threading.Lock()
        self._operations = set()
        self._generation = 0

    @contextmanager
    def track(self, operation_id):
        """领取前登记，所有退出路径释放。@param operation_id 一次性票据。@return 活动上下文。"""
        if not isinstance(operation_id, str) or not re.fullmatch(r'[a-f0-9]{32}', operation_id):
            raise ValueError('代理切换授权无效')
        with self._lock:
            if operation_id in self._operations:
                raise ProxySelectionConflict('代理切换仍在进行中', 'busy')
            self._operations.add(operation_id)
            self._generation += 1
        try:
            yield
        finally:
            with self._lock:
                self._operations.discard(operation_id)
                self._generation += 1

    def active(self):
        """读取是否仍有已登记的切线。@return 活动标志。"""
        with self._lock:
            return bool(self._operations)

    def references(self, read):
        """核对引用读取跨越的活动代次，避免返回提交前的旧快照。@param read 引用读取回调。@return 完整性已核对的引用。"""
        with self._lock:
            before, generation = bool(self._operations), self._generation
        result = read()
        with self._lock:
            if before or self._operations or generation != self._generation:
                result['complete'] = False
        return result


def connection_url(account):
    """恢复独立任务的私有连接。@param account 数据库行。@return 规范连接或直连空串。"""
    host = str(account.get('upstream_socks5_host') or '').strip().strip('[]')
    if not host:
        return ''
    scheme = account.get('upstream_proxy_scheme') or 'socks5'
    port = int(account.get('upstream_socks5_port') or (80 if scheme == 'http' else 1080))
    authority = '[' + host + ']' if ':' in host else host.encode('idna').decode().lower()
    user, password = account.get('upstream_socks5_user') or '', account.get('upstream_socks5_pass') or ''
    auth = (quote(user, safe='') + (':' + quote(password, safe='') if password else '') + '@') if user or password else ''
    return f'{scheme}://{auth}{authority}:{port}'


def selection_revision(account, connection, secret):
    """用服务密钥绑定身份与原配置，防止公开原始连接摘要。@param account 当前身份。@param connection 私有连接。@param secret 服务密钥。@return 不透明版本。"""
    if len(secret) < 32:
        raise ValueError('代理选择服务尚未配置')
    data = json.dumps(['task-proxy-v1', account['id'], account.get('cc2api_account_id'), connection], separators=(',', ':'), ensure_ascii=False).encode()
    return hmac.new(secret.encode(), data, hashlib.sha256).hexdigest()


def read_account(database, identity):
    """读取唯一可见任务账号。@param database 连接工厂。@param identity 账号ID。@return 数据库行。"""
    connection = database()
    try:
        row = connection.execute('SELECT * FROM accounts WHERE id=? AND deleted_at IS NULL', (identity,)).fetchone()
        if row is None:
            raise LookupError('任务账号已不可用')
        return dict(row)
    finally:
        connection.close()


def snapshot(account, gateway, secret):
    """读取权威连接形成内部快照。@param account 任务。@param gateway 内部管理调用。@param secret 版本密钥。@return 仅供网关桥脱敏的快照。"""
    binding = account.get('cc2api_account_id')
    connection = gateway('GET', f'/admin/runtime/accounts/{binding}/config')['proxy_url'] if binding is not None else connection_url(account)
    return {'account_id': account['id'], 'name': account.get('display_name') or account['name'],
        'gateway_account_id': binding, 'connection': connection,
        'selection_revision': selection_revision(account, connection, secret)}


def save_selection(identity, body, database, db_lock, runtime, owner_lock, profile_lock, active_login, gateway, secret, ownership_guard=None, authorize=None):
    """在原维护顺序下比较并保存用户选线，状态冲突明确失败。

    @param identity 任务账号ID。@param body 桥解析后的原版本与私有目标。
    @param database 数据库连接工厂。@param db_lock 写入锁。@param runtime 运行环境。
    @param owner_lock 凭据所有者锁。@param profile_lock 账号配置锁。
    @param active_login 活跃登录判断。@param gateway 内部管理接口。@param secret 版本密钥。
    @param ownership_guard 既有凭据归属门禁。
    @param authorize 活动登记后的内部票据领取，返回操作ID；纯存储测试可省略。
    @return 仅供网关桥脱敏的已保存快照。
    """
    if set(body) != {'selection_revision', 'connection'} or not isinstance(body['selection_revision'], str) or not isinstance(body['connection'], str):
        raise ValueError('代理选择格式无效')
    destination = body['connection']
    if destination:
        parsed = urlsplit(destination)
        if parsed.scheme not in ('http', 'socks5', 'socks5h') or not parsed.hostname or parsed.path not in ('', '/') or parsed.query or parsed.fragment:
            raise ValueError('代理连接无效')
        fields = (parsed.scheme, parsed.hostname, parsed.port or (80 if parsed.scheme == 'http' else 1080), unquote(parsed.username or ''), unquote(parsed.password or ''))
    else:
        fields = ('socks5', '', None, '', '')
    original = read_account(database, identity)
    with ExitStack() as locks:
        for guard in (owner_lock(original['name']), profile_lock(original['name'])):
            if not guard.acquire(blocking=False):
                raise ProxySelectionConflict('账号正在配置或授权，请稍后重试', 'busy')
            locks.callback(guard.release)
        account = read_account(database, identity)
        if ownership_guard:
            ownership_guard(account)
        current = snapshot(account, gateway, secret)
        if not hmac.compare_digest(current['selection_revision'], body['selection_revision']):
            raise ProxySelectionConflict('账号关联或代理已变化，请重新读取后选择')
        if not account.get('enabled'):
            raise ProxySelectionConflict('任务账号已停用，请先核对账号状态', 'disabled')
        if current['connection'] == destination:
            return current
        if active_login(account['name']):
            raise ProxySelectionConflict('账号正在授权，请完成后再切换代理', 'busy')
        binding = account.get('cc2api_account_id')
        # 登记活动早于领取；超时后尚未领取的请求不能开始副作用。
        operation_id = authorize(account) if authorize else None
        if binding is not None:
            # 此处只持有owner/profile锁。网关许可会调用quiesce取得环境锁，不能反向嵌套。
            gateway('POST', f'/admin/runtime/accounts/{binding}/proxy-selection',
                {'expected_connection': current['connection'], 'connection': destination,
                 **({'operation_id': operation_id} if operation_id else {})})
        else:
            connection = database()
            try:
                row = connection.execute('SELECT * FROM account_environments WHERE account_id=?', (identity,)).fetchone()
                row = dict(row) if row else None
            finally:
                connection.close()
            if row:
                guard = runtime.environment_lock(row['environment_id'])
                if not guard.acquire(blocking=False):
                    raise ProxySelectionConflict('运行环境正在维护，请稍后重试', 'busy')
                locks.callback(guard.release)
                with runtime.lock:
                    busy = bool(runtime.environment_jobs(row['environment_id']))
                if busy or runtime._running_sender_active(row):
                    raise ProxySelectionConflict('账号仍有任务或请求运行，请等待结束后切换', 'busy')
                runtime._stop_environment(row, remove=True)
                runtime._update(row, state='stopped')
        with db_lock:
            connection = database()
            try:
                with connection:
                    # owner/profile锁保护关联；SQL再核对原字段，防止其它写入绕过维护顺序。
                    changed = connection.execute('UPDATE accounts SET upstream_proxy_scheme=?,upstream_socks5_host=?,'
                        'upstream_socks5_port=?,upstream_socks5_user=?,upstream_socks5_pass=? '
                        'WHERE id=? AND cc2api_account_id IS ? AND deleted_at IS NULL '
                        'AND upstream_proxy_scheme IS ? AND upstream_socks5_host IS ? AND upstream_socks5_port IS ? '
                        'AND upstream_socks5_user IS ? AND upstream_socks5_pass IS ?',
                        (*fields, identity, binding, *(account.get(key) for key in
                            ('upstream_proxy_scheme','upstream_socks5_host','upstream_socks5_port','upstream_socks5_user','upstream_socks5_pass'))))
                    if changed.rowcount != 1:
                        raise ProxySelectionConflict('账号配置已变化，请重新读取')
            finally:
                connection.close()
        return snapshot(read_account(database, identity), gateway, secret)
