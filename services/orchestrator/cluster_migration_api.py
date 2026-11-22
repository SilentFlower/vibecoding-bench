"""人工迁移后台作业与脱敏状态接口，浏览器沿用中央管理员会话。"""
from __future__ import annotations

import threading
from contextlib import nullcontext

from fastapi import APIRouter, HTTPException, Path

from cluster_api import NodeRoute
from cluster_migration_runner import MigrationCoordinator, MigrationStart
from system_update_gate import UPDATE_GATE
from cluster_migration_errors import public_failure


_STAGES = {'preflight': '检查目标节点并同步运行组件', 'draining': '等待原工作完成', 'fence': '停止并隔离源环境', 'export': '导出源环境资料',
    'transfer': '传输迁移资料', 'verify-import': '核验目标资料', 'prepare-import': '准备目标运行环境',
    'activate-import': '激活目标环境', 'revoke-import': '撤销目标副本', 'restore-source': '恢复原源环境'}

_PHASES = {'requested': '等待迁移', 'draining': '排空原有工作', 'source_fenced': '源环境已停止隔离',
    'exporting': '导出和传输资料', 'importing': '核验并准备目标', 'verified': '目标已核对',
    'committed': '归属已切换，正在激活目标', 'completed': '迁移完成', 'cancelled': '迁移已取消',
    'reconcile': '迁移需要核对'}


class MigrationOperations:
    """为每个账号串行运行已持久迁移，重启后通过原操作继续。

    :param coordinator: 持久阶段与节点IO协调器。
    """

    def __init__(self, coordinator: MigrationCoordinator) -> None:
        """建立只含活动线程的瞬时索引。:param coordinator: 原协调器。:return: None。"""
        self.coordinator, self.lock = coordinator, threading.RLock()
        self.workers: dict[str, threading.Thread] = {}
        self.accounts: dict[int, str] = {}
        self.closing = False

    def start(self, account_id: int, request: MigrationStart) -> dict:
        """持久登记人工迁移并在后台执行。

        :param account_id: 当前账号。
        :param request: 原分配与人工目标。
        :return: 脱敏操作状态。
        """
        activity = UPDATE_GATE.reserve('node-migration:' + request.operation_id)
        try:
            record = self.coordinator.begin(account_id, request)
            return self._launch(record, 'run', activity)
        except BaseException:
            UPDATE_GATE.release_reserved(activity)
            raise

    def continue_operation(self, account_id: int, operation_id: str, *, cancel: bool = False) -> dict:
        """继续原迁移或原取消意图，提交后仅允许目标激活。

        :param account_id: 当前账号。
        :param operation_id: 原操作。
        :param cancel: 管理员明确发起提交前取消。
        :return: 脱敏状态。
        """
        record = self._owned(account_id, operation_id)
        if cancel and (record['phase'] == 'completed' or record['record']['last_confirmed_phase'] == 'committed'):
            raise ValueError('归属已提交，请继续目标激活')
        cancelling = cancel or 'cancellation' in record['record'].get('checkpoints', {})
        if cancel and getattr(self.coordinator.ledger, 'agy', False):
            with self.lock:
                if operation_id in self.workers:
                    self.coordinator.ledger.request_drain_cancel(operation_id)
                    return self.get(account_id, operation_id)
        activity = UPDATE_GATE.reserve('node-migration:' + operation_id)
        try:
            return self._launch(record, 'cancel' if cancelling else 'run', activity)
        except BaseException:
            UPDATE_GATE.release_reserved(activity)
            raise

    def _launch(self, record: dict, action: str, activity: str | None) -> dict:
        operation_id, account_id = record['operation_id'], record['account_id']
        with self.lock:
            if self.closing:
                raise ValueError('迁移服务正在关闭')
            if record['phase'] in ('completed', 'cancelled') or operation_id in self.workers:
                UPDATE_GATE.release_reserved(activity)
                return self.get(account_id, operation_id)
            if account_id in self.accounts:
                raise ValueError('账号已有迁移操作正在执行')
            thread = threading.Thread(target=self._work, args=(record, action, activity),
                name='cluster-migration', daemon=True)
            self.accounts[account_id], self.workers[operation_id] = operation_id, thread
            try:
                thread.start()
            except BaseException:
                self.accounts.pop(account_id, None)
                self.workers.pop(operation_id, None)
                raise
        return self.get(account_id, operation_id)

    def _work(self, record: dict, action: str, activity: str | None) -> None:
        operation_id = record['operation_id']
        try:
            context = UPDATE_GATE.continue_reserved(activity) if activity is not None else nullcontext()
            with context:
                if action == 'cancel':
                    self.coordinator.cancel(operation_id)
                else:
                    self.coordinator.run(operation_id)
        except Exception:
            current = self.coordinator.ledger.get(operation_id)
            if current['phase'] not in ('completed', 'cancelled', 'reconcile'):
                self.coordinator.ledger.isolate(operation_id, 'migration_worker_unconfirmed')
        finally:
            UPDATE_GATE.release_reserved(activity)
            with self.lock:
                self.workers.pop(operation_id, None)
                self.accounts.pop(record['account_id'], None)

    def _owned(self, account_id: int, operation_id: str) -> dict:
        record = self.coordinator.ledger.get(operation_id)
        if record['account_id'] != account_id:
            raise ValueError('迁移操作不属于当前账号')
        return record

    def get(self, account_id: int, operation_id: str) -> dict:
        """读取明确列举的公开状态，移除节点秘密与内部检查点。

        :param account_id: 原账号。
        :param operation_id: 原操作。
        :return: 可轮询的公开投影。
        """
        migration = self._owned(account_id, operation_id)
        record = migration['record']
        with self.lock:
            running = operation_id in self.workers
        terminal = migration['phase'] in ('completed', 'cancelled')
        committed = record['last_confirmed_phase'] in ('committed', 'completed')
        nodes = {}
        for side in ('source', 'target'):
            node = self.coordinator.service.store.history_identity(migration[side + '_node_id'])
            nodes[side] = {'id': node['id'], 'name': node['name']}
        return {'operation_id': operation_id, 'account_id': account_id, **nodes,
            'phase': migration['phase'], 'last_confirmed_phase': record['last_confirmed_phase'],
            'message': (_STAGES.get(record.get('progress', {}).get('stage')) if running else None)
                or _PHASES.get(migration['phase'], '迁移状态需要核对'), 'running': running,
            'failure': public_failure(record.get('failure')) if migration['phase'] == 'reconcile' and not running else None,
            'can_resume': not running and not terminal,
            'can_cancel': (not running or getattr(self.coordinator.ledger, 'agy', False)
                and record['last_confirmed_phase'] == 'requested' and 'cancellation' not in record.get('checkpoints', {}))
                and not terminal and not committed,
            'source_revision': record['source_revision'], 'target_revision': record.get('target_revision'),
            'cancelling': 'cancellation' in record.get('checkpoints', {}),
            'created_at': migration['created_at'], 'updated_at': migration['updated_at']}

    def list(self, account_id: int) -> dict:
        """列出当前账号最近二十项迁移。

        :param account_id: 当前账号。
        :return: 脱敏列表，活动迁移优先。
        """
        rows = self.coordinator.ledger.history(account_id)
        return {'items': [self.get(account_id, row['operation_id']) for row in rows]}

    def close(self) -> None:
        """停止新迁移并阻止下一节点步骤，持久记录继续保护重启恢复。:return: None。"""
        with self.lock:
            self.closing = True
            self.coordinator.stopping.set()
            workers = list(self.workers.values())
        for worker in workers:
            worker.join(timeout=1)


def migration_router(operations, *, agy: bool = False) -> APIRouter:
    """提供已鉴权管理桥中的迁移资源路由。

    :param operations: 当前后台迁移作业服务回调。
    :param agy: 反重力使用独立网关账号路由。
    :return: 按账号限制的公开路由。
    """
    domain = 'agy-accounts' if agy else 'accounts'
    router = APIRouter(prefix=f'/api/{domain}/{{account_id}}/node-migrations', route_class=NodeRoute)

    def current():
        service = operations()
        if service is None:
            raise HTTPException(503, '迁移服务尚未就绪')
        return service

    @router.get('')
    def list_migrations(account_id: int) -> dict:
        """读取账号迁移历史。:param account_id: 原账号。:return: 公开列表。"""
        try:
            return current().list(account_id)
        except ValueError:
            raise HTTPException(404, '账号或迁移记录不存在') from None

    @router.post('', status_code=202)
    def start_migration(account_id: int, body: MigrationStart) -> dict:
        """后台启动人工迁移。:param account_id: 原账号。:param body: 目标和原版本。:return: 操作状态。"""
        try:
            return current().start(account_id, body)
        except ValueError as error:
            raise HTTPException(409, str(error)) from None
        except (RuntimeError, OSError):
            raise HTTPException(409, '迁移尚未启动，请核对账号空闲、原归属版本和目标组件状态') from None

    @router.get('/{operation_id}')
    def get_migration(account_id: int, operation_id: str = Path(pattern=r'^[a-f0-9]{32}$')) -> dict:
        """轮询原操作状态。:param account_id: 账号。:param operation_id: 原操作。:return: 公开状态。"""
        try:
            return current().get(account_id, operation_id)
        except ValueError:
            raise HTTPException(404, '账号或迁移记录不存在') from None

    @router.post('/{operation_id}/{action}', status_code=202)
    def control_migration(account_id: int, operation_id: str = Path(pattern=r'^[a-f0-9]{32}$'),
                          action: str = Path(pattern=r'^(resume|cancel)$')) -> dict:
        """继续或取消原操作。:param account_id: 账号。:param operation_id: 原操作。:param action: 固定动作。:return: 状态。"""
        try:
            return current().continue_operation(account_id, operation_id, cancel=action == 'cancel')
        except (ValueError, RuntimeError, OSError):
            raise HTTPException(409, '迁移操作需要核对，请重新读取原阶段；归属提交后继续目标激活') from None

    return router
