"""中央迁移专用网关排他租约，过期和失联继续保留维护。"""
from __future__ import annotations

import threading
import time

from cluster_migrations import NodeMigrations


class IndependentMigrationPermit:
    """独立账号沿中央原owner锁和持久maintenance迁移，保持无Gateway租约。

    :param ledger: 原中央迁移账本。
    :param operation_id: 原持久迁移操作。
    :param transports: 原实际流登记。
    :param account_id: 原正式独立账号。
    :param abort: 原协调关闭信号。
    """

    def __init__(self, ledger, operation_id, transports, account_id, *, abort=None):
        """冻结原依赖。:param ledger: 原账本。:param operation_id: 原操作。:param transports: 实际流。:param account_id: 原账号。:param abort: 关闭信号。:return: None。"""
        self.ledger,self.operation_id,self.transports,self.account_id,self.abort=ledger,operation_id,transports,account_id,abort

    def __enter__(self):
        """复核原持久维护后进入。:return: 本次中央许可。"""
        self.check()
        return self

    def check(self) -> None:
        """每一步复核原独立身份和持久操作，实际Node停止另由原fence确认。:return: None。"""
        if self.abort is not None and self.abort.is_set():
            raise ValueError('迁移服务正在关闭，原操作保留维护')
        operation=self.ledger.get(self.operation_id)
        assignment=self.ledger.store.assignment(self.account_id)
        connection=self.ledger.store.database()
        try:
            account=connection.execute('SELECT cc2api_account_id FROM accounts WHERE id=? AND deleted_at IS NULL',
                (self.account_id,)).fetchone()
        finally:
            connection.close()
        if (operation['account_id']!=self.account_id or operation['phase'] in ('completed','cancelled')
                or assignment['phase'] not in ('maintenance','reconcile') or account is None or account['cc2api_account_id'] is not None):
            raise ValueError('原独立账号迁移许可或持久维护已经变化')

    def drain(self, timeout: float=120) -> None:
        """等待原实际流收口，CLI停止继续使用原Node源隔离。

        :param timeout: 本次排空期限，秒。
        :return: None。
        """
        deadline=time.monotonic()+timeout
        while True:
            self.check()
            if self.transports.account_streams(self.account_id)==0:
                return
            if time.monotonic()>=deadline:
                raise ValueError('独立账号仍有原节点连接待收口')
            if self.abort is not None:
                self.abort.wait(.2)
            else:
                threading.Event().wait(.2)

    def release(self) -> None:
        """核对中央原许可，最终激活事务负责恢复ready。:return: None。"""
        self.check()

    def __exit__(self, error_type, error, traceback) -> None:
        """保留原持久维护供协调器完成或恢复。:param error_type: 异常类型。:param error: 原异常。:param traceback: 原调用栈。:return: None。"""


class MigrationLease:
    """只认领原迁移操作的排他租约，并在长IO期间持续续约。

    :param gateway: 原中央网关受信客户端。
    :param ledger: 原迁移账本。
    :param operation_id: 原操作。
    :param gateway_account_id: 冻结的网关账号。
    :param transports: 中央实际节点流登记。
    :param account_id: 中央账号。
    :param abort: 服务关闭时阻止下一跨节点步骤的事件。
    """

    def __init__(self, gateway, ledger: NodeMigrations, operation_id: str, gateway_account_id: int,
                 transports, account_id: int, *, abort: threading.Event | None = None) -> None:
        """准备单次协调依赖，初始化保持原门禁。

        :param gateway: 中央网关。
        :param ledger: 迁移账本。
        :param operation_id: 原操作。
        :param gateway_account_id: 网关账号。
        :param transports: 实际流计数。
        :param account_id: 中央账号。
        :param abort: 关闭信号。
        :return: None。
        """
        self.gateway, self.ledger, self.operation_id = gateway, ledger, operation_id
        self.transports, self.account_id = transports, account_id
        self.owner = 'node-migration:' + operation_id
        self.path = f'/admin/runtime/accounts/{gateway_account_id}/lease'
        self.proof = None
        self.stopping, self.failed = threading.Event(), threading.Event()
        self.thread = None
        self.mutex = threading.Lock()
        self.abort = abort

    def __enter__(self):
        """核对原排他占用并启动续约，恢复只定向释放同操作旧代次。:return: 本次原租约协调器。"""
        self.check()
        record = self.ledger.get(self.operation_id)
        if record['phase'] in ('completed', 'cancelled'):
            raise ValueError('迁移已经结束')
        assignment = self.ledger.store.assignment(self.account_id)
        if assignment['phase'] not in ('maintenance', 'reconcile'):
            raise ValueError('迁移账号尚未关闭新准入')
        previous = record['record'].get('checkpoints', {}).get('gateway_lease')
        snapshot = self.gateway._request('GET', self.path)
        holders = snapshot.get('holders')
        if not isinstance(holders, list) or snapshot.get('importing') != 0:
            raise ValueError('迁移网关占用或凭据导入状态需要核对')
        if holders:
            current = self._owned(snapshot)
            if previous is not None and current != previous:
                raise ValueError('迁移原网关租约代次已变化')
            holder = holders[0]
            if holder.get('phase') == 'reconcile' or holder.get('expires_at', 0) <= time.time():
                if snapshot.get('active') != 0:
                    raise ValueError('原迁移租约仍有实际API活动，拒绝撤销')
                # 账号分配持续关闭；源实际停止由后续同操作fence核对，TTL不表示进程停止。
                self.gateway._request('POST', self.path, {'operation': 'release', **current})
        snapshot = self.gateway._request('POST', self.path, {'operation': 'prepare', 'owner': self.owner})
        self.proof = self._owned(snapshot)
        self.ledger.checkpoint(self.operation_id, 'gateway_lease', self.proof, previous=previous)
        self.thread = threading.Thread(target=self._heartbeat, name='cluster-migration-lease', daemon=True)
        self.thread.start()
        return self

    def _owned(self, snapshot: dict) -> dict:
        holders = snapshot.get('holders')
        if (not isinstance(holders, list) or len(holders) != 1 or not isinstance(holders[0], dict)
                or holders[0].get('owner') != self.owner or holders[0].get('exclusive') is not True
                or not isinstance(holders[0].get('generation'), str) or not holders[0]['generation']):
            raise ValueError('迁移网关租约属于其他作业或未提供排他证明')
        return {key: holders[0][key] for key in ('owner', 'generation')}

    def _update(self, operation: str) -> dict:
        with self.mutex:
            result = self.gateway._request('POST', self.path, {'operation': operation, **self.proof})
            if operation != 'release' and self._owned(result) != self.proof:
                raise ValueError('迁移续约回执与原代次不一致')
            return result

    def _heartbeat(self) -> None:
        while not self.stopping.wait(5):
            try:
                self._update('heartbeat')
            except Exception:
                self.failed.set()
                return

    def check(self) -> None:
        """新跨节点步骤开始前确认续约仍有效。:return: None；失败保持原排他门禁。"""
        if self.abort is not None and self.abort.is_set():
            raise ValueError('迁移服务正在关闭，原操作保留维护')
        if self.failed.is_set():
            raise ValueError('迁移网关续约失效，请核对原操作')

    def drain(self, timeout: float = 120) -> None:
        """等待实际API与节点流收口后认领排他操作。

        :param timeout: 本次有限排空期限，秒。
        :return: None；到期保留原维护状态。
        """
        deadline = time.monotonic() + timeout
        while True:
            self.check()
            snapshot = self.gateway._request('GET', self.path)
            if self._owned(snapshot) != self.proof or snapshot.get('importing') != 0:
                raise ValueError('迁移排空期间原网关门禁发生变化')
            active = snapshot.get('active')
            if type(active) is not int or active < 0:
                raise ValueError('迁移实际API活动计数无效')
            if active == 0 and self.transports.account_streams(self.account_id) == 0:
                self._update('claim')
                return
            if time.monotonic() >= deadline:
                raise ValueError('迁移原有工作尚未完成，请等待并继续原操作')
            self.stopping.wait(0.2)

    def release(self) -> None:
        """双端收据完成后定向释放原租约，中央分配继续维护到最终事务。

        :return: None；未知释放保留中央维护并由原操作恢复。
        """
        self.check()
        self.stopping.set()
        if self.thread is not None:
            self.thread.join(timeout=10)
            if self.thread.is_alive():
                raise ValueError('迁移续约尚未收口，原租约保持核对状态')
        result = self._update('release')
        if result.get('holders') != [] or result.get('importing') != 0:
            raise ValueError('迁移租约释放后的占用状态需要核对')

    def __exit__(self, error_type, error, traceback) -> None:
        """停止本次续约，异常时保留原排他占用。

        :param error_type: 原异常类型。
        :param error: 原异常。
        :param traceback: 原调用栈。
        :return: None。
        """
        self.stopping.set()
        if self.thread is not None:
            self.thread.join(timeout=10)
