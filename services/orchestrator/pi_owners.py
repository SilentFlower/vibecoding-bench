"""账号级 Pi 控制权认领，覆盖模型选题期间尚未启动原生终端的空隙。"""
from __future__ import annotations

import threading
import uuid


class AccountPiOwners:
    """在当前管理进程内为每个账号保留唯一 Pi 控制者。"""

    def __init__(self) -> None:
        """建立独立认领锁与内存登记，不启动任何工作。:return: None。"""
        self._lock = threading.Lock()
        self._owners = {}

    def claim(self, account_id: int, kind: str, generation: int) -> str | None:
        """非阻塞认领账号，已有所有者时不抢占或复用其令牌。

        :param account_id: 可信账号 ID。
        :param kind: 服务端固定的 projects 或 warmup。
        :param generation: 当前服务的控制代次。
        :return: 本次独有令牌；账号繁忙时为 None。
        """
        if (type(account_id) is not int or account_id < 1 or kind not in ('projects', 'warmup')
                or type(generation) is not int or generation < 1):
            raise ValueError('Pi 账号控制者标识不合法')
        with self._lock:
            if account_id in self._owners:
                return None
            token = uuid.uuid4().hex
            self._owners[account_id] = {'kind': kind, 'generation': generation, 'token': token}
            return token

    def release(self, account_id: int, token: str) -> bool:
        """仅释放精确认领令牌，迟到的旧控制者不能释放新工作。

        :param account_id: 原账号 ID。
        :param token: claim 返回的独有令牌。
        :return: 是否实际释放了当前所有者。
        """
        with self._lock:
            current = self._owners.get(account_id)
            if not current or current['token'] != token:
                return False
            del self._owners[account_id]
            return True

    def owner(self, account_id: int) -> dict | None:
        """读取不可用于释放的所有者摘要。

        :param account_id: 待读账号 ID。
        :return: 服务类型与代次；空闲时为 None。
        """
        with self._lock:
            current = self._owners.get(account_id)
            return {key: current[key] for key in ('kind', 'generation')} if current else None
