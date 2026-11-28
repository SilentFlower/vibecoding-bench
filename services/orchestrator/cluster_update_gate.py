"""仅为历史停机取证参与者协调节点本地维护门禁。"""
from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from hashlib import sha256
import fcntl
import os
from pathlib import Path
from threading import Thread
from typing import Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, StrictInt, StrictStr, field_validator

from cluster_deployment import node_container_name
from runtime_files import atomic_json, directory_fd
from system_update_contract import safe_read, strict_json
from system_update_gate import UPDATE_GATE, read_gate, validate_gate


class GatePeer(BaseModel):
    """冻结的节点安装范围。节点改配后，旧操作不得作用到替代节点。"""

    model_config = ConfigDict(extra='forbid', strict=True)
    id: StrictInt = Field(gt=0)
    node_key: StrictStr = Field(pattern='^[a-f0-9]{32}$')
    config_sha256: StrictStr = Field(pattern='^[a-f0-9]{64}$')


class NodeGateCommand(BaseModel):
    """节点实际核对的本次操作、原节点门禁修订及维护归属。"""

    model_config = ConfigDict(extra='forbid', strict=True)
    action: Literal['read', 'freeze', 'release']
    node_key: StrictStr = Field(pattern='^[a-f0-9]{32}$')
    deployment: StrictStr
    operation_id: StrictStr
    epoch: StrictStr
    expected_revision: StrictStr | None = None
    target_release: StrictStr
    created_at: StrictStr

    @field_validator('epoch', 'operation_id', 'expected_revision')
    @classmethod
    def canonical_uuid(cls, value):
        """保持与宿主及节点持久门禁相同的 UUID 格式。@param value 输入。@return 原值。"""
        if value is not None and str(UUID(value)) != value:
            raise ValueError('节点维护操作身份无效')
        return value


class NodeJobThread(Thread):
    """把私有请求交给异步节点工作的占用延续到线程结束。"""

    def start(self):
        """在返回启动回执前登记，线程启动失败时归还占用。@return 无。"""
        self._activity = UPDATE_GATE.reserve('node-background')
        try:
            return super().start()
        except BaseException:
            UPDATE_GATE.release_reserved(self._activity)
            raise

    def run(self):
        """通过原登记执行本份后台工作，结束时定向释放。@return 无。"""
        try:
            if self._activity is None:
                return super().run()
            with UPDATE_GATE.continue_reserved(self._activity):
                return super().run()
        finally:
            UPDATE_GATE.release_reserved(self._activity)


def node_gate(executor, command: NodeGateCommand, gate=UPDATE_GATE):
    """在实际准入锁中读取或切换原节点门禁。@param executor 节点。@param command 已认证命令。@param gate 本地准入。@return 实际状态。"""
    directory = executor.data / 'system-update-gate'
    selected = gate.directory or Path(os.environ.get('V3_UPDATE_GATE_DIR', ''))
    if (command.node_key != executor.node_key or command.deployment != executor.deployment or selected != directory):
        raise ValueError('节点维护归属或门禁挂载变化')
    with gate.lock:
        current = read_gate(directory, executor.deployment)
        owned = (current['phase'] == 'blocked' and current['epoch'] == command.epoch
                 and current['operation_id'] == command.operation_id)
        if owned and current['target_release'] != command.target_release:
            raise ValueError('节点冻结目标与本次操作不一致')
        if command.action != 'read' and command.expected_revision is None:
            raise ValueError('节点维护缺少原空闲门禁修订')
        if command.action == 'freeze' and not owned:
            if (current['phase'] != 'idle' or current['revision'] != command.expected_revision
                    or current['epoch'] == command.epoch):
                raise ValueError('原节点门禁已被另一操作改变')
            if not gate.state()['active']:
                # 先让已认证的操作和驻留作业自行收口；有活动时保留 idle，只返回真实占用。
                current = validate_gate({**current, 'phase': 'blocked', 'operation_id': command.operation_id,
                    'epoch': command.epoch, 'revision': str(uuid4()), 'created_at': command.created_at,
                    'target_release': command.target_release}, executor.deployment)
                atomic_json(directory / 'admission.json', current)
        elif command.action == 'release':
            if owned:
                if not gate.state()['active']:
                    current = {**current, 'phase': 'idle', 'operation_id': None, 'target_release': None, 'revision': str(uuid4())}
                    atomic_json(directory / 'admission.json', current)
            elif current['phase'] == 'idle' and current['revision'] == command.expected_revision:
                # 冻结的 SSH 回复可能丢失，释放也要消费原修订，拒绝随后抵达的迟到冻结。
                current = {**current, 'epoch': command.epoch, 'revision': str(uuid4())}
                atomic_json(directory / 'admission.json', current)
            elif (current['phase'] != 'idle' or (current['epoch'] != command.epoch
                    and current['revision'] != command.expected_revision)):
                raise ValueError('节点门禁不属于本次释放')
        return {'protocol': 1, 'node_key': executor.node_key, 'deployment': executor.deployment,
                **{key: current[key] for key in ('phase', 'operation_id', 'epoch', 'revision')},
                'active': gate.state()['active']}


# 只有通过原宿主维护鉴权的协调线程，或由该维护活动派生的节点安装线程，才携带这个上下文。
PLATFORM_NODE_OPERATION = ContextVar('platform_node_operation', default=None)


@contextmanager
def maintenance_scope(maintenance):
    """沿已核对的宿主操作传递范围。@param maintenance 受信操作及代次。@return 原执行上下文。"""
    token = PLATFORM_NODE_OPERATION.set((maintenance['operation_id'], maintenance['epoch']) if maintenance else None)
    try:
        yield
    finally:
        PLATFORM_NODE_OPERATION.reset(token)


@contextmanager
def node_admission(operation, continuation, gate=UPDATE_GATE):
    """普通操作进入实际节点计数，冻结中仅放行只读核验和原平台维护操作。@param operation 私有动作。@param continuation 原操作代次。@param gate 本地准入。"""
    if operation in ('health', 'platform-gate', 'stopped-environment-observe', 'inspect'):
        yield
    elif continuation:
        if operation not in ('fence', 'restore-source', 'restart-preserved', 'stage-preparation-files', 'prepare-files', 'prepare'):
            raise ValueError('该节点操作不属于平台备份或组件恢复')
        identifier = gate.reserve_maintenance('node:' + operation, *continuation)
        try:
            with gate.continue_reserved(identifier):
                yield
        finally:
            gate.release_reserved(identifier)
    else:
        with gate.admission('node:' + operation):
            yield


def gate_peers(service, nodes):
    """冻结参与取证节点的原 SSH 配置身份。@param service 节点服务。@param nodes 当时登记。@return 有序参与者。"""
    return [dict(id=node['id'], node_key=node['node_key'],
                 config_sha256=sha256(service.store.get(node['id'])['config_json'].encode()).hexdigest())
            for node in sorted(nodes, key=lambda entry: entry['id']) if node['kind'] == 'ssh']


def _call(service, runtime, peer: GatePeer, command: NodeGateCommand):
    """按同一受证安装身份转发门禁操作。@param service 节点服务。@param runtime 中央运行时。@param peer 冻结的节点。@param command 原操作。@return 真实节点回执。"""
    def check():
        node = service.store.get(peer.id)
        if (node['kind'] != 'ssh' or node['node_key'] != peer.node_key or peer.node_key != command.node_key
                or command.deployment != runtime.deployment or sha256(node['config_json'].encode()).hexdigest() != peer.config_sha256):
            raise ValueError('冻结参与节点已改配')
    check()
    connection = service.connection(peer.id)
    receipt = connection.execution_environment(node_container_name(runtime.deployment, peer.node_key),
                                                command.model_dump(), 'platform-gate')
    check()
    if (receipt.get('node_key') != peer.node_key or receipt.get('deployment') != command.deployment
            or type(receipt.get('active')) is not int or receipt['active'] < 0
            or receipt.get('phase') not in ('idle', 'blocked')):
        raise ValueError('原节点维护回执无效')
    return receipt


_MARKER = 'stopped-proof-gate.json'


def forwarding_scope(private: Path):
    """只向本轮已冻结节点转发原平台维护身份。@param private 原 SSH 安装凭据目录。@return 操作及代次。"""
    scope = PLATFORM_NODE_OPERATION.get()
    if scope is None:
        return None
    try:
        record = strict_json(safe_read(private / _MARKER, 4096, private=True))
    except FileNotFoundError:
        return None
    return scope if (record['operation_id'], record['epoch']) == scope and not record['released'] else None


def coordinate_gate(service, runtime, peer: GatePeer, action: str, gate: dict):
    """登记每节点冻结意图，重试依原修订回收。@param service 节点服务。@param runtime 中央运行时。
    @param peer 原安装身份。@param action freeze 或 release。@param gate 宿主持有的中央门禁。@return 节点已完成该动作。"""
    if action not in ('freeze', 'release'):
        raise ValueError('未知节点门禁动作')
    # 以冻结的节点键定位中央意图，即使配置已变，释放也不能误查替代节点的私有目录。
    private = service.private_root / peer.node_key
    lock = directory_fd(private, create=True)
    try:
        fcntl.flock(lock, fcntl.LOCK_EX)
        current = UPDATE_GATE.state()
        if (gate['phase'] != 'blocked' or any(gate[key] != current.get(key) for key in ('phase','operation_id','epoch'))):
            raise ValueError('宿主已释放节点维护操作')
        marker = private / _MARKER
        identity = {'operation_id': gate['operation_id'], 'epoch': gate['epoch'], 'peer': peer.model_dump()}
        try:
            record = strict_json(safe_read(marker, 4096, private=True))
        except FileNotFoundError:
            record = None
        if record and any(record[key] != value for key, value in identity.items()):
            if not record['released']:
                raise ValueError('节点仍有前一操作的冻结意图')
            record = None
        if action == 'release' and record is None:
            # 原 freeze 的 HTTP 也可能晚于取消抵达。此时无需访问 SSH，记录本地取消决定防止迟到的新写入。
            atomic_json(marker, {**identity, 'revision': None, 'released': True})
            return True
        if action == 'release' and record['released']:
            return True
        command = NodeGateCommand(action='read', deployment=runtime.deployment, node_key=peer.node_key,
            operation_id=gate['operation_id'], epoch=gate['epoch'], target_release=gate['target_release'], created_at=gate['created_at'])
        if record is None:
            status = _call(service, runtime, peer, command)
            if status['phase'] != 'idle':
                raise ValueError('节点已有维护门禁')
            if status['active']:
                return False
            record = {**identity, 'revision': status['revision'], 'released': False}
            # 在第一个远端写入前持久化旧修订。超时或进程重启后沿同一安装身份释放。
            atomic_json(marker, record)
        if record['released']:
            raise ValueError('该操作已释放节点，迟到的冻结请求已失效')
        command = NodeGateCommand.model_validate({**command.model_dump(), 'action': action, 'expected_revision': record['revision']})
        result = _call(service, runtime, peer, command)
        if action == 'freeze':
            if result['phase'] == 'idle' and result['active']:
                return False
            if (result['phase'], result['operation_id'], result['epoch']) != ('blocked', gate['operation_id'], gate['epoch']):
                raise ValueError('原节点未确认本次冻结')
            return result['active'] == 0
        if (result['phase'], result['operation_id'], result['epoch']) == ('blocked',gate['operation_id'],gate['epoch']) and result['active']:
            return False
        if (result['phase'], result['operation_id'], result['epoch']) != ('idle', None, gate['epoch']):
            raise ValueError('原节点未确认释放')
        atomic_json(marker, {**record, 'released': True})
        return True
    finally:
        os.close(lock)
