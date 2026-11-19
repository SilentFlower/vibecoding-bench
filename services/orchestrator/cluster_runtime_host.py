"""持久节点运行时及受限账号配置，实际中央租约仍由控制端持有。"""
from __future__ import annotations

import copy
import re
import threading

from account_runtime import AccountRuntime
from cluster_execution import _GatewaySnapshot
from cluster_execution_grants import ExecutionScope
from cluster_input import NodeInputs
from cluster_lease_mirror import NodeLeaseMirror


class _NodeGatewayConfigurations:
    """只提供中央已投影的账号配置和原生准备通知。"""

    def __init__(self, executor) -> None:
        self.executor = executor
        self.lock = threading.RLock()
        self.snapshots = {}
        self.quotas = {}
        self.lease_mirror = None

    def adopt(self, snapshot, quota_identity) -> None:
        if not snapshot.account_id:
            if snapshot.bench_account_id is not None and quota_identity is not None:
                if type(snapshot.bench_account_id) is not int or snapshot.bench_account_id <= 0:
                    raise ValueError('节点独立账号缺少中央身份范围')
                with self.lock:
                    self.quotas[snapshot.bench_account_id] = quota_identity
            return
        if type(snapshot.account_id) is not int or snapshot.account_id <= 0 or type(snapshot.bench_account_id) is not int:
            raise ValueError('节点账号配置缺少中央身份范围')
        with self.lock:
            previous = self.snapshots.get(snapshot.account_id)
            if (previous is not None and previous.bench_account_id != snapshot.bench_account_id
                    and not self._released_owner(previous,snapshot)):
                raise ValueError('节点网关配置属于另一任务账号，请先核对原绑定')
            self.snapshots[snapshot.account_id] = snapshot
            if quota_identity is not None:
                self.quotas[snapshot.bench_account_id] = quota_identity

    def _released_owner(self, previous, snapshot):
        connection=self.executor.database()
        try:
            current=connection.execute('SELECT cc2api_account_id FROM accounts WHERE id=?',(snapshot.bench_account_id,)).fetchone()
            old=connection.execute('SELECT cc2api_account_id FROM accounts WHERE id=?',(previous.bench_account_id,)).fetchone()
        finally:
            connection.close()
        # 当前Node投影确认原账号已解绑后，内存缓存不再永久占用该Gateway身份。
        return (current is not None and current['cc2api_account_id']==snapshot.account_id
            and (old is None or old['cc2api_account_id']!=snapshot.account_id))

    def quota_identity(self, account: dict) -> str:
        """按中央账号取得当前只读额度身份。:param account: 原投影账号。:return: 原冻结额度身份。"""
        with self.lock:
            callback = self.quotas.get(account.get('id'))
        if callback is None:
            raise ValueError('节点尚未收到该账号的中央额度身份')
        return callback(account)

    def _request(self, method: str, path: str, payload=None, **kwargs):
        if method == 'GET' and path == '/admin/native-preparations':
            return []
        lease = re.fullmatch(r'/admin/runtime/accounts/([1-9][0-9]*)/lease', path)
        if lease is not None:
            with self.lock:
                if int(lease[1]) not in self.snapshots or self.lease_mirror is None:
                    raise ValueError('节点尚未收到该账号的原执行许可')
                mirror = self.lease_mirror
            return mirror.request(method, path, payload)
        matched = re.fullmatch(r'/admin/(runtime/accounts/([1-9][0-9]*)/config|accounts/([1-9][0-9]*)/native-preparation)', path)
        if matched is None:
            raise ValueError('节点操作超出受限账号配置范围')
        account_id = int(matched[2] or matched[3])
        with self.lock:
            snapshot = self.snapshots.get(account_id)
            if snapshot is None:
                raise ValueError('节点尚未收到该网关账号的只读配置')
            if method == 'GET' and matched[2]:
                return copy.deepcopy(snapshot.configuration)
            if method == 'POST' and matched[3]:
                snapshot.notifications.add(account_id)
                return {'ok': True}
        raise ValueError('节点账号配置操作方法无效')


class NodeRuntimeHost:
    """同一节点进程借用一个真实运行时，实际jobs与锁持续保留。

    :param executor: 已核对安装归属的节点执行入口。
    :param runtime_factory: 原运行时构造器。
    """

    def __init__(self, executor, runtime_factory=AccountRuntime) -> None:
        """登记安装边界，初始化尚未启动账号环境。

        :param executor: 原固定节点入口。
        :param runtime_factory: 原运行时或测试执行替身。
        :return: None。
        """
        if executor.local_runtime is not None or executor.node_key == 'local' or executor.shared_runtime or executor.runtime_release is not None:
            raise ValueError('持久节点运行时需要独立且尚未借用的远程执行入口')
        self.executor, self.runtime_factory = executor, runtime_factory
        self.gateway, self.runtime = _NodeGatewayConfigurations(executor), None
        self.lock, self.closed = threading.RLock(), False
        self.inputs = None
        executor.runtime_factory, executor.runtime_release, executor.shared_runtime = self.acquire, self.release, True

    def attach_grants(self, grants) -> NodeLeaseMirror:
        """启动前安装本节点有限证明和原租约镜像。

        :param grants: 原安装范围的有限证明存储。
        :return: 后续具体执行操作绑定原scope使用的镜像。
        """
        with self.lock:
            if (self.runtime is not None or self.closed or self.gateway.lease_mirror is not None
                    or grants.data != self.executor.data or grants.node_key != self.executor.node_key
                    or grants.deployment != self.executor.deployment or grants.database != self.executor.database):
                raise ValueError('有限证明需要在原节点运行时启动前绑定')
            mirror = NodeLeaseMirror(grants)
            self.gateway.lease_mirror = mirror
            self.inputs = NodeInputs(self.executor, mirror)
            return mirror

    def acquire(self, client, data, host_data, database, fingerprint, gateway, quota_identity):
        """按原AccountRuntime构造签名借用同一节点运行时。

        :param client: 本节点Docker。
        :param data: 原数据根。
        :param host_data: 原宿主根。
        :param database: 原节点投影库。
        :param fingerprint: 原画像函数。
        :param gateway: 当前有限账号快照。
        :param quota_identity: 当前账号额度身份函数。
        :return: 本进程唯一节点运行时。
        """
        with self.lock:
            if (self.closed or client is not self.executor.client or data != self.executor.data
                    or host_data != self.executor.host_data or database != self.executor.database):
                raise ValueError('节点运行时借用已关闭或安装范围不一致')
            self.gateway.adopt(gateway, quota_identity)
            if self.runtime is None:
                runtime = self.runtime_factory(client, data, host_data, database, fingerprint,
                    self.gateway, self.gateway.quota_identity)
                # 节点只承接中央明确动作，启动进程不自主发起账号预热。
                runtime.native_prewarm_account_id = None
                if self.gateway.lease_mirror is not None:
                    runtime.execution_admission = self.gateway.lease_mirror.authorize_job
                    runtime.execution_input = self.inputs.prepare
                    runtime.execution_input_release = self.inputs.release
                try:
                    runtime.start()
                except BaseException as error:
                    try:
                        runtime.stop()
                    except Exception as cleanup_error:
                        # 启动故障保持主异常，收尾失败通过因果链留给原节点诊断。
                        raise error from cleanup_error
                    raise
                self.runtime = runtime
            return self.runtime

    def recovery_runtime(self, scope: ExecutionScope):
        """为原私有执行收口借用运行时，保持新账号配置和启动许可关闭。

        :param scope: 已由原私有执行和证明核对的账号范围。
        :return: 本节点唯一原运行时；不准备任何账号或模型执行。
        """
        with self.gateway.lock:
            previous = self.gateway.snapshots.get(scope.gateway_account_id)
        if previous is not None and previous.bench_account_id != scope.account_id:
            raise ValueError('原执行恢复的网关账号属于其他本地账号')
        snapshot = previous or _GatewaySnapshot(scope.gateway_account_id or 0, {}, bench_account_id=scope.account_id)
        return self.executor._runtime(snapshot)

    def release(self, runtime) -> None:
        """归还本次借用，持久线程池和作业由节点生命周期收口。

        :param runtime: 本进程取得的原运行时。
        :return: None。
        """
        with self.lock:
            if runtime is not self.runtime:
                raise ValueError('归还的节点运行时不属于当前进程')

    def close(self) -> None:
        """关闭新借用，按原运行时合同收口CLI和后台线程。:return: None。"""
        with self.lock:
            if self.closed:
                return
            self.closed = True
            runtime = self.runtime
        if runtime is not None:
            runtime.stop()
        if self.inputs is not None:
            self.inputs.close()
