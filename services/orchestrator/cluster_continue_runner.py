"""中央原续聊路由及私有PTY桥，浏览器继续使用原鉴权和输入门禁。"""
from __future__ import annotations

import base64
import hashlib
import json
import re
import socket
import threading
import time
from uuid import uuid4
from typing import Literal

from websockets.sync.client import connect

from account_runtime import RuntimeBusy
from cluster_continue_contract import ContinueStart, ContinueWork
from cluster_execution_grants import ExecutionScope
from cluster_quota import QuotaFileChunk
from cluster_runner import ClusterRunner
from system_update_contract import safe_read, strict_json

PTY_ACK_TIMEOUT = 10


class RemoteContinuePty:
    """通过独立SSH私有WS连接原PTY，保持原socket消费接口。

    :param owner: 原具体中央操作协调器。
    :param row: 原冻结操作。
    :param purpose: 固定续聊、独立登录或绑定登录用途。
    """

    def __init__(self, owner, row: dict, *, purpose: Literal['continue','login','bound-login','draft-login'] = 'continue') -> None:
        """一次建立原PTY连接，接入失败保留原操作。

        :param owner: 原续聊路由。
        :param row: 原执行账本。
        :param purpose: 固定私有PTY用途及对应一次输入回执。
        :return: None。
        """
        endpoints={'continue':('continue-pty','continue-input'),'login':('account-login-pty','account-login-input'),
            'bound-login':('account-bound-login-pty','account-bound-login-input'),
            'draft-login':('draft-login-pty','draft-login-input')}
        if purpose not in endpoints:
            raise ValueError('具体PTY连接用途无效')
        endpoint,self.input_operation=endpoints[purpose]
        self.owner, self.row = owner, row
        self.scope = row['record']['scope']
        self.condition, self.input_lock = threading.Condition(), threading.Lock()
        self.receipts, self.closed = {}, False
        self.pending_input = None
        self.websocket, self.reader = None, None
        self.output, self.writer = socket.socketpair()
        self.output.setblocking(False)
        self.writer.settimeout(10)
        peer = owner.sessions.service.connection(row['node_id'])
        stream = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            stream.settimeout(10)
            stream.connect(str(peer.pty_socket()))
            token = safe_read(peer.private / 'execution-token', 128, private=True).decode()
            if not re.fullmatch('[a-f0-9]{64}', token):
                raise ValueError('原节点PTY服务认证无效')
            self.websocket = connect('ws://node.internal/'+endpoint, sock=stream, legacy=True,
                additional_headers={'x-v3-node-token': token}, proxy=None, compression=None,
                open_timeout=10, close_timeout=1, ping_interval=10, ping_timeout=10, max_size=32768, max_queue=4)
            self.websocket.send(json.dumps(self.scope, ensure_ascii=False))
            value = strict_json(self.websocket.recv(timeout=15).encode(), 16384)
            if value != {'type': 'ready', 'scope': self.scope}:
                raise ValueError('原节点PTY就绪回执无效')
            self.reader = threading.Thread(target=self._read, name='remote-continue-pty', daemon=True)
            self.reader.start()
        except BaseException:
            stream.close()
            self.close()
            owner.sessions._isolate(row['operation_id'], 'remote_pty_open_unconfirmed')
            raise

    def fileno(self) -> int:
        """提供原异步输出桥使用的描述符。:return: 本地有界输出socket。"""
        return self.output.fileno()

    def recv(self, size: int) -> bytes:
        """读取已由原Node输出的PTY字节。:param size: 本次字节上限。:return: 原字节。"""
        return self.output.recv(size)

    def gettimeout(self):
        """供原事件循环核对非阻塞模式。:return: 当前输出socket超时。"""
        return self.output.gettimeout()

    def _read(self) -> None:
        try:
            while True:
                message = self.websocket.recv()
                if isinstance(message, bytes):
                    if len(message) > 4096:
                        raise ValueError('原PTY输出帧超过读取上限')
                    self.writer.sendall(message)
                else:
                    value = strict_json(message.encode(), 16384)
                    if set(value) != {'type', 'receipt'} or value['type'] != 'input_ack':
                        raise ValueError('原PTY输入回执帧无效')
                    receipt = self._validate_receipt(value['receipt'])
                    with self.condition:
                        if receipt['operation_id'] != self.pending_input:
                            continue
                        self.receipts[receipt['operation_id']] = receipt
                        self.condition.notify_all()
        except Exception:
            # WS断开不创建第二份原生会话；调用方继续沿原scope取得实际停止事实。
            pass
        finally:
            with self.condition:
                self.closed = True
                self.condition.notify_all()
            self.writer.close()

    def _validate_receipt(self, value: dict) -> dict:
        if (not isinstance(value, dict) or set(value) != {'scope', 'operation_id', 'payload_sha256', 'status'}
                or value['scope'] != self.scope or not isinstance(value['operation_id'], str)
                or not re.fullmatch('[a-f0-9]{32}', value['operation_id'])
                or not isinstance(value['payload_sha256'], str) or not re.fullmatch('[a-f0-9]{64}', value['payload_sha256'])
                or value['status'] not in ('sent', 'not_sent', 'unknown')):
            raise ValueError('原PTY输入回执范围无效')
        return value

    def send(self, data: bytes) -> int:
        """每片只写入一次，丢回执后仅查询原操作。

        :param data: 已通过原ContinueManager窗口/额度检查的字节。
        :return: 全部片段明确sent后的原长度。
        """
        if not isinstance(data, bytes) or len(data) > 256 * 1024:
            raise ValueError('续聊单次输入超过256KiB上限')
        with self.input_lock:
            for offset in range(0, len(data), 16384):
                content, operation_id = data[offset:offset + 16384], uuid4().hex
                try:
                    with self.condition:
                        if self.closed:
                            raise ValueError('原PTY连接已关闭')
                        self.pending_input = operation_id
                    receipt = None
                    try:
                        self.websocket.send(json.dumps({'type': 'input', 'operation_id': operation_id,
                            'data': base64.b64encode(content).decode()}))
                        deadline = time.monotonic() + PTY_ACK_TIMEOUT
                        with self.condition:
                            while operation_id not in self.receipts and not self.closed and time.monotonic() < deadline:
                                self.condition.wait(max(0.001, deadline - time.monotonic()))
                            receipt = self.receipts.pop(operation_id, None)
                    except Exception:
                        # 发送异常可能发生在Node落盘之后，继续查询同一输入，绝不重复写入。
                        pass
                    if receipt is None:
                        receipt = self.owner.sessions._call(self.row, self.input_operation,
                            {'scope': self.scope, 'operation_id': operation_id})
                    receipt = self._validate_receipt(receipt)
                    if (receipt['operation_id'] != operation_id or receipt['payload_sha256'] != hashlib.sha256(content).hexdigest()
                            or receipt['status'] != 'sent'):
                        raise ValueError('原PTY输入尚未确认sent')
                    with self.condition:
                        self.pending_input = None
                        self.receipts.pop(operation_id, None)
                except Exception:
                    self.owner.sessions._isolate(self.row['operation_id'], 'remote_pty_input_unconfirmed')
                    raise
        return len(data)

    def resize(self, rows: int, cols: int) -> None:
        """只发送原PTY窗口尺寸。:param rows: 行。:param cols: 列。:return: None。"""
        if type(rows) is not int or type(cols) is not int or not 1 <= rows <= 1000 or not 1 <= cols <= 1000:
            raise ValueError('续聊窗口尺寸无效')
        with self.input_lock:
            self.websocket.send(json.dumps({'type': 'resize', 'rows': rows, 'cols': cols}))

    def close(self) -> None:
        """有界关闭本连接，实际作业由原停止协议收口。:return: None。"""
        with self.condition:
            self.closed = True
            self.condition.notify_all()
        try:
            self.writer.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        self.writer.close()
        self.output.close()
        if self.websocket is not None:
            self.websocket.close()
        if self.reader is not None and self.reader is not threading.current_thread():
            self.reader.join(timeout=2)


class ClusterContinues(ClusterRunner):
    """沿原中央续聊状态机使用具体节点许可及PTY。

    :param sessions: 原许可协调器。
    :param identity: 原额度身份。
    """

    def __init__(self, sessions, identity) -> None:
        """保存原依赖和恢复集合锁。:param sessions: 原协调器。:param identity: 原身份。:return: None。"""
        super().__init__(sessions, identity)
        self.recovery_lock = threading.RLock()

    def handles(self, token: str | None) -> bool:
        """识别仅由中央解析的续聊定位。:param token: 原worker字段。:return: 是否为原节点续聊。"""
        return isinstance(token, str) and re.fullmatch(r'remote-continue:[a-f0-9]{32}', token) is not None

    def _row(self, token: str) -> dict:
        if not self.handles(token):
            raise ValueError('原远程续聊定位无效')
        row = self.sessions.ledger.get(token.removeprefix('remote-continue:'))
        work = ContinueWork.model_validate(row['record']['work'])
        if row['role'] != 'cli' or row['source'] != work.source:
            raise ValueError('原远程定位属于其他执行')
        return row

    def start(self, work: ContinueWork, account: dict) -> tuple[str, str]:
        """准备原续聊，未知启动只登记同一操作的实际收口。

        :param work: 原冻结工作。
        :param account: 原账号。
        :return: 原操作定位。
        """
        try:
            return self._start_continue(work, account)
        except Exception:
            try:
                row = self.sessions.ledger.by_source(account['id'], work.source, active_only=True)
                if row is not None:
                    try:
                        self.sessions._isolate(row['operation_id'], 'remote_continue_start_unconfirmed')
                    finally:
                        with self.recovery_lock:
                            if self.recovery_sources is None:
                                self.recovery_sources = set()
                            self.recovery_sources.add(row['operation_id'])
            except Exception:
                # 原账本继续阻塞该账号，重启仍会恢复原操作。
                pass
            raise

    def _start_continue(self, work: ContinueWork, account: dict) -> tuple[str, str]:
        """按冻结source准备一次原续聊作业。

        :param work: 原Run/Claude会话/模式与代次。
        :param account: 原账号。
        :return: 原实际操作的兼容定位二元组。
        """
        with self.sessions._operation_lock('source:' + str(account['id']) + ':' + work.source):
            previous = self.sessions.ledger.by_source(account['id'], work.source, active_only=False)
            if previous is not None:
                if previous['record']['work'] != work.model_dump():
                    raise ValueError('原节点续聊冻结工作已变化')
                row = previous
            else:
                if self.sessions.ledger.active(account['id']):
                    raise RuntimeBusy('续聊等待原节点作业实际收口')
                service, runtime = self.sessions.service, self.sessions.runtime
                service.prepare_remote_cli(account, runtime, self.sessions.gateway, self.identity(account))
                assignment = service.store.assignment(account['id'])
                actual = runtime._row(account['name'], account['id'])
                scope = ExecutionScope(operation_id=uuid4().hex, node_key=assignment['node_key'], account_id=account['id'],
                    gateway_account_id=account.get('cc2api_account_id'), environment_id=actual['environment_id'],
                    assignment_revision=assignment['revision'], generation=actual['generation'], source=work.source, role='cli')
                row = self.sessions.start(ContinueStart(scope=scope, work=work))
            if row['phase'] != 'running' or row['record']['node_receipt']['phase'] != 'ready':
                raise RuntimeBusy('原节点续聊启动等待核对')
            token = 'remote-continue:' + row['operation_id']
            return token, token

    def open(self, token: str) -> RemoteContinuePty:
        """一次连接原节点PTY，接入未知保持原scope。:param token: 原定位。:return: 原输出桥。"""
        row = self._row(token)
        self.sessions.ledger.admit(row['operation_id'])
        observed = self.sessions.node_state(row['operation_id'])
        if observed['phase'] != 'ready':
            raise RuntimeBusy('原节点续聊PTY需要核对')
        return RemoteContinuePty(self, row)

    def for_source(self, run_id: str, source: str) -> dict | None:
        """按原Run及续聊source读取已登记操作。:param run_id: 原Run。:param source: 原continue来源。:return: 原冻结行或None。"""
        if not re.fullmatch(r'continue:[a-f0-9]{12}:[0-9]+', source):
            return None
        connection = self.sessions.service.store.database()
        try:
            run = connection.execute('SELECT account_id FROM runs WHERE id=?', (run_id,)).fetchone()
        finally:
            connection.close()
        row = self.sessions.ledger.by_source(run['account_id'], source, active_only=False) if run else None
        if row is not None and ContinueWork.model_validate(row['record']['work']).id != run_id:
            raise ValueError('原续聊来源属于其他Run')
        return row

    def quota_control(self, row: dict) -> dict | None:
        """读取原Node的root额度控制补证。:param row: 原执行。:return: 原有界补证或None。"""
        result = self._read(row, 'continue-quota-control', row['record']['scope'])
        if result.pop('scope', None) != row['record']['scope']:
            raise ValueError('原续聊额度补证属于其他执行')
        chunk = QuotaFileChunk.model_validate(result)
        if chunk.file_identity is None:
            return None
        if chunk.offset != 0 or chunk.size > 65536:
            raise ValueError('原续聊额度补证超过读取上限')
        raw = base64.b64decode(chunk.content, validate=True)
        if len(raw) != chunk.size:
            raise ValueError('原续聊额度补证不完整')
        return strict_json(raw, 65536)

    def sync_credentials(self, token: str) -> None:
        """发布原中央唯一所有者已更新的AT。:param token: 原续聊。:return: None。"""
        row = self._row(token)
        scope = ExecutionScope.model_validate(row['record']['scope'])
        account = self.sessions._account(scope)
        self.sessions.service.prepare_remote_cli(account, self.sessions.runtime, self.sessions.gateway, self.identity(account))
        result = self.sessions._call(row, 'continue-credentials', scope.model_dump())
        if result != {'scope': scope.model_dump(), 'synced': True}:
            raise ValueError('原节点续聊凭据发布尚未确认')

    def cleanup(self, token: str) -> None:
        """确认原节点实际停止，失败保存后台收口集合。:param token: 原续聊。:return: None。"""
        row = self._row(token)
        try:
            self.sessions.stop(row['operation_id'])
        except Exception:
            try:
                self.sessions._isolate(row['operation_id'], 'remote_continue_stop_unconfirmed')
            except Exception:
                # 原许可仍登记；后台继续重试同一作业的实际停止。
                pass
            with self.recovery_lock:
                if self.recovery_sources is None:
                    self.recovery_sources = set()
                self.recovery_sources.add(row['operation_id'])
            raise

    def _recovery_sources(self) -> set[str]:
        result = set()
        for operation_id in self.sessions.ledger.pending():
            try:
                row = self.sessions.ledger.get(operation_id)
                if row['source'].startswith('continue:'):
                    ContinueWork.model_validate(row['record']['work'])
                    result.add(operation_id)
            except (ValueError, OSError):
                # 单个坏账本继续隔离该账号，其余原续聊可独立收口。
                pass
        return result

    def recover_once(self, completed) -> None:
        """只恢复旧续聊或明确停止失败的原操作。:param completed: 实际停止后的原会话收口回调。:return: None。"""
        with self.recovery_lock:
            if self.recovery_sources is None:
                self.recovery_sources = self._recovery_sources()
            sources = list(self.recovery_sources)
        for operation_id in sources:
            if self.recovery_stop.is_set():
                return
            try:
                self.sessions.stop(operation_id)
                completed(operation_id)
                with self.recovery_lock:
                    self.recovery_sources.discard(operation_id)
            except Exception:
                # 同一scope继续保留许可；后台只查询/停止原执行，禁止重建原PTY。
                pass
