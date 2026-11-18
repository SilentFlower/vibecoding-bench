"""兼容原运行时的中央租约有限镜像，节点没有真实租约的续长或释放权。"""
from __future__ import annotations

import re
import threading
from contextlib import contextmanager
from contextvars import ContextVar

from cluster_execution_grants import ExecutionGrants, ExecutionScope


class NodeLeaseMirror:
    """仅为已明确认领的执行范围提供原网关调用合同。

    :param grants: 本节点有限证明存储。
    """

    def __init__(self, grants: ExecutionGrants) -> None:
        """建立进程内绑定，重启后的旧作业由恢复入口单独对账。

        :param grants: 原节点有限证明。
        :return: None。
        """
        self.grants, self.lock = grants, threading.RLock()
        self.scopes, self.claimed = {}, set()
        self.draft_authorizer=None
        self.context = ContextVar('node_execution_preparing', default=None)

    def attach(self, scope: ExecutionScope) -> None:
        """绑定已经认领的单次执行许可，禁止同来源换操作。

        :param scope: 原不可变执行范围。
        :return: None。
        """
        with self.lock:
            self.grants.authorize(scope)
            key = (scope.gateway_account_id, scope.source)
            previous = self.scopes.get(key)
            if previous is not None and previous != scope:
                raise ValueError('原节点执行来源已经绑定其他操作')
            self.scopes[key] = scope

    @contextmanager
    def preparing(self, scope: ExecutionScope):
        """限定本次启动的原owner，支持原低优先级空闲检查。

        :param scope: 已绑定的原执行。
        :return: 不授予新中央租约的兼容上下文。
        """
        with self.lock:
            if self.scopes.get((scope.gateway_account_id, scope.source)) != scope:
                raise ValueError('节点尚未绑定本次执行许可')
            self.grants.authorize(scope)
        token = self.context.set({'scope': scope, 'prepared': False})
        try:
            yield
        finally:
            self.context.reset(token)

    def recover(self, scope: ExecutionScope) -> None:
        """恢复原租约的停止能力，过期证明继续拒绝启动和输入。

        :param scope: 原持久执行范围。
        :return: None；不续长原截止，不授予新的prepare或claim。
        """
        with self.lock:
            self.grants.get(scope)
            key = (scope.gateway_account_id, scope.source)
            previous = self.scopes.get(key)
            if previous is not None and previous != scope:
                raise ValueError('恢复原租约的执行来源已绑定其他操作')
            self.scopes[key] = scope
            self.claimed.add(scope.operation_id)

    def scope_for_job(self, job: dict) -> ExecutionScope:
        """核对原账号、source、代次和截止，取得实际job的冻结范围。

        :param job: 本进程原AccountRuntime作业。
        :return: 原有效执行scope。
        """
        with self.lock:
            scope = self.scopes.get((job['account'].get('cc2api_account_id'), job['source']))
            row = job['row']
            if (scope is None or scope.account_id != job['account'].get('id')
                    or scope.account_id != row.get('account_id') or scope.environment_id != row.get('environment_id')
                    or scope.generation != row.get('generation')):
                raise ValueError('节点输入与原执行许可的账号、环境或代次不一致')
            self.grants.authorize(scope)
            return scope

    def authorize_job(self, job: dict) -> None:
        """在实际新输入前核对原有限证明。:param job: 原实际作业。:return: None。"""
        if job['account'].get('id') is None:
            if (job['row'].get('account_id') is not None or job['account'].get('cc2api_account_id') is not None
                    or self.draft_authorizer is None or re.fullmatch('login:[a-f0-9]{12}',job['source']) is None):
                raise ValueError('NULL账号输入缺少原草稿专属许可')
            self.draft_authorizer(job)
            return
        self.scope_for_job(job)

    def release_independent(self, scope: ExecutionScope) -> None:
        """实际停止后解除独立账号的进程内来源绑定。:param scope: 原已关闭执行。:return: None；持久墓碑保留。"""
        with self.lock:
            if scope.gateway_account_id is not None or self.grants.get(scope)['phase'] != 'closed':
                raise ValueError('独立执行仍需原停止和关闭回执')
            key = (None, scope.source)
            previous = self.scopes.get(key)
            if previous is not None and previous != scope:
                raise ValueError('独立执行来源已绑定其他操作')
            self.scopes.pop(key, None)
            self.claimed.discard(scope.operation_id)

    def release_bound_login(self, scope: ExecutionScope) -> None:
        """实际停止后解除原绑定登录镜像，真实Gateway租约仍由中央释放。

        :param scope: 原已关闭的绑定登录范围。
        :return: None；不调用真实网关，不为其它来源解除镜像。
        """
        with self.lock:
            if (scope.gateway_account_id is None or scope.role!='login'
                    or re.fullmatch('login:[a-f0-9]{12}',scope.source) is None
                    or self.grants.get(scope)['phase']!='closed'):
                raise ValueError('绑定登录仍需原实际停止及关闭回执')
            key=(scope.gateway_account_id,scope.source)
            previous=self.scopes.get(key)
            if previous is not None and previous!=scope:
                raise ValueError('原绑定登录来源已经变化')
            self.scopes.pop(key,None)
            self.claimed.discard(scope.operation_id)

    def _snapshot(self, account_id: int, *, hide=None) -> dict:
        holders = []
        for (identity, _), scope in self.scopes.items():
            if identity != account_id or scope == hide:
                continue
            grant = self.grants.get(scope)['grant']
            # 心跳只镜像中央原截止。过期关闭新输入，已经接受的进程继续保留原现场。
            holders.append({**grant['lease'], 'phase': 'claimed'})
        return {'lease': holders[0] if holders else None, 'holders': holders,
            'cli_capacity': 2, 'active': 0, 'importing': 0}

    def request(self, method: str, path: str, payload=None) -> dict:
        """解释固定租约调用，所有操作只改变本地兼容状态。

        :param method: GET或POST。
        :param path: 已投影账号的固定lease路径。
        :param payload: 原运行时的prepare、claim、heartbeat或release输入。
        :return: 包含原租约身份和原截止的快照。
        """
        matched = re.fullmatch(r'/admin/runtime/accounts/([1-9][0-9]*)/lease', path)
        if matched is None:
            raise ValueError('节点租约调用超出固定范围')
        account_id = int(matched[1])
        with self.lock:
            context = self.context.get()
            if method == 'GET' and payload is None:
                hide = context['scope'] if context and not context['prepared'] else None
                return self._snapshot(account_id, hide=hide)
            if method != 'POST' or not isinstance(payload, dict):
                raise ValueError('节点租约调用方法无效')
            operation, owner = payload.get('operation'), payload.get('owner')
            scope = self.scopes.get((account_id, owner))
            if scope is None:
                raise ValueError('节点未收到本次原租约许可')
            record = self.grants.get(scope)
            lease = record['grant']['lease']
            if operation in ('prepare', 'prepare-cli', 'prepare-cli-shared'):
                if (set(payload) != {'operation', 'owner'} or not context or context['scope'] != scope
                        or scope.operation_id in self.claimed):
                    raise ValueError('节点租约准备属于另一启动或已有实际作业')
                grant = self.grants.authorize(scope)
                mode = 'prepare' if grant.lease.exclusive else ('prepare-cli-shared' if grant.lease.shared_cli else 'prepare-cli')
                if operation != mode:
                    raise ValueError('节点租约模式与中央原许可不一致')
                context['prepared'] = True
            else:
                if set(payload) != {'operation', 'owner', 'generation'} or payload['generation'] != lease['generation']:
                    raise ValueError('节点租约原代次不一致')
                if operation == 'claim':
                    if not context or context['scope'] != scope or not context['prepared'] or scope.operation_id in self.claimed:
                        raise ValueError('节点租约启动已经认领或缺少原准备')
                    self.grants.authorize(scope)
                    self.claimed.add(scope.operation_id)
                elif operation == 'heartbeat':
                    if scope.operation_id not in self.claimed:
                        raise ValueError('节点作业尚未实际认领')
                elif operation == 'release':
                    self.grants.close(scope, 'node_execution_closed')
                    self.scopes.pop((account_id, owner))
                    self.claimed.discard(scope.operation_id)
                else:
                    raise ValueError('节点租约操作无效')
            return self._snapshot(account_id)
