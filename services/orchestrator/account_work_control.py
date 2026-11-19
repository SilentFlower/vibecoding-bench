"""协调账号整体启停，持久保留停止意图并等待实际工作收尾。"""
from __future__ import annotations

import json
import threading
import uuid


class AccountWorkCoordinator:
    """在原账号身份锁下协调网关准入与任务停止。

    :param database: 数据库连接工厂。
    :param db_lock: 数据库写锁。
    :param owner_lock: 账号身份锁工厂。
    :param gateway: 网关管理客户端。
    :param stop: 停止任务的回调。
    :param activity: 读取实际任务占用的回调。
    """

    def __init__(self, database, db_lock, owner_lock, gateway, stop, activity):
        """保存原服务依赖并建立控制锁。

        :param database: 数据库连接工厂。
        :param db_lock: 原写锁。
        :param owner_lock: 身份锁工厂。
        :param gateway: 管理客户端。
        :param stop: 实际停止回调。
        :param activity: 实际占用回调。
        :return: None。
        """
        self.database, self.db_lock, self.owner_lock = database, db_lock, owner_lock
        self.gateway, self.stop, self.activity = gateway, stop, activity
        self._locks = {}
        self._locks_guard = threading.Lock()

    def _read(self, account_id):
        connection = self.database()
        try:
            account = connection.execute('SELECT * FROM accounts WHERE id=? AND deleted_at IS NULL', (account_id,)).fetchone()
            saved = connection.execute('SELECT value FROM app_settings WHERE key=?', (f'account_work_control:{account_id}',)).fetchone()
            if account is None:
                raise ValueError('账号不存在')
            return dict(account), json.loads(saved['value']) if saved else None
        finally:
            connection.close()

    def _save(self, account_id, operation, *, enabled=None):
        with self.db_lock:
            connection = self.database()
            try:
                with connection:
                    if enabled is not None:
                        connection.execute('UPDATE accounts SET enabled=? WHERE id=? AND deleted_at IS NULL', (int(enabled), account_id))
                    connection.execute("INSERT INTO app_settings(key,value,updated_at) VALUES(?,?,julianday('now')) "
                        "ON CONFLICT(key) DO UPDATE SET value=excluded.value,updated_at=excluded.updated_at",
                        (f'account_work_control:{account_id}', json.dumps(operation)))
            finally:
                connection.close()

    def snapshot(self, account_id: int) -> dict:
        """只读观察控制与真实进度。:param account_id: 任务账号。:return: 整体状态和占用摘要。"""
        account, operation = self._read(account_id)
        active, gateway, message = None, None, None
        try:
            active = self.activity(account_id)
        except Exception:
            message = '账号执行占用待核对'
        if account.get('cc2api_account_id'):
            try:
                gateway = self.gateway._request('GET', f"/admin/accounts/{account['cc2api_account_id']}/work-control")
            except (ConnectionError, ValueError):
                message = '账号执行占用及网关状态待核对' if message else '网关工作状态待核对'
        enabled = bool(account['enabled'])
        phase = 'enabled' if enabled else 'draining' if active or gateway and gateway['admitted_requests'] else 'disabled'
        if message or operation and operation['phase'] in ('pending', 'reconcile'):
            phase = 'reconcile'
        if gateway and enabled != gateway['work_enabled']:
            phase, message = 'reconcile', '整体工作状态尚待两端确认，请继续核对'
        return {'enabled': enabled, 'phase': phase, 'active_work': active, 'api': gateway,
            'operation_id': operation['id'] if operation else None,
            'message': message or ('原工作正在正常收尾' if phase == 'draining' else
                '整体启停需要继续核对' if phase == 'reconcile' else None)}

    def change(self, account_id: int, enabled: bool) -> dict:
        """幂等整体启停，部分成功保留关闭意图。:param account_id: 账号。:param enabled: 目标。:return: 实际进度。"""
        if type(enabled) is not bool:
            raise ValueError('整体启停必须为布尔值')
        with self._locks_guard:
            lock = self._locks.setdefault(account_id, threading.Lock())
        with lock:
            account, _ = self._read(account_id)
            with self.owner_lock(account['name']):
                account, previous = self._read(account_id)
                already_enabled = False
                if enabled and account['enabled'] and (previous is None or previous['phase'] == 'enabled'):
                    already_enabled = not account.get('cc2api_account_id') or self.gateway._request(
                        'GET', f"/admin/accounts/{account['cc2api_account_id']}/work-control")['work_enabled']
                if not already_enabled:
                    operation = previous if previous and previous['enabled'] == enabled else {'id': uuid.uuid4().hex, 'enabled': enabled}
                    operation = {**operation, 'phase': 'pending'}
                    # 停止意图与任务门禁同事务提交，重启后调度器仍保持关闭。
                    self._save(account_id, operation, enabled=False)
            if already_enabled:
                # 占用读取会获取项目锁，保持在身份锁外；重复启用不扰动运行中的任务。
                return self.snapshot(account_id)
            try:
                gateway_error = None
                if account.get('cc2api_account_id'):
                    try:
                        self.gateway._request('PUT', f"/admin/accounts/{account['cc2api_account_id']}/work-control", {'work_enabled': enabled})
                    except (ConnectionError, ValueError) as error:
                        gateway_error = error
                if not enabled:
                    # 工作停止会获取项目锁；释放身份锁后调用，避免与项目启动锁序反转。
                    self.stop(account_id)
                if gateway_error:
                    raise gateway_error
                current, _ = self._read(account_id)
                if current.get('cc2api_account_id') != account.get('cc2api_account_id'):
                    raise ValueError('账号关联已变化，请核对原整体控制操作')
                operation['phase'] = 'enabled' if enabled else 'disabled'
                self._save(account_id, operation, enabled=enabled)
            except Exception:
                operation['phase'] = 'reconcile'
                self._save(account_id, operation, enabled=False)
                raise
            return self.snapshot(account_id)

    def recover(self) -> None:
        """按原意图恢复重启前未完成的整体控制。:return: None。"""
        connection = self.database()
        try:
            rows = connection.execute("SELECT key,value FROM app_settings WHERE key LIKE 'account_work_control:%'").fetchall()
        finally:
            connection.close()
        for row in rows:
            operation = json.loads(row['value'])
            if operation['phase'] in ('pending', 'draining', 'reconcile'):
                try:
                    self.change(int(row['key'].split(':')[1]), operation['enabled'])
                except Exception:
                    # 原操作已保存待核对，单账号失败不阻止其余账号恢复。
                    continue
