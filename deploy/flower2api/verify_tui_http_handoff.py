#!/usr/bin/env python3
"""用实际 v1.33.3 Gateway 验收已占用进程的公开 Messages 工具续轮。"""

import argparse
from base64 import b64decode, b64encode
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack, contextmanager
from dataclasses import asdict, replace
from hashlib import file_digest, sha256
from http.client import HTTPConnection
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
from select import select
import socket
from subprocess import Popen, TimeoutExpired, check_output, run
import sys
from tempfile import mkdtemp
from threading import Event, Lock, Thread, Timer
from time import sleep, time
from urllib.parse import urlsplit
from uuid import uuid4

from fixtures.file_activity import monitor_read, read_counts
from verify_tui_concurrency import CLEAN_ENV, MIB, ROOT, frame, record, wait_for, write_json

sys.path.insert(0, str(ROOT / 'images' / 'account'))


MODEL = 'claude-sonnet-4-6'
AGENT = 'flower-tui-handoff/1'
ORIGINAL = 'Read the isolated note and report its content.'
COMPETING = 'Run a separate ordinary turn.'
ARGUMENTS = {'path': 'isolated-note.txt'}
CANDIDATE_RELEASE = 'fixture-tui-v2-candidate'
BASELINE = '25b50904f89e6b3c89b790c6d751a72c3da4381b'


def json_bytes(value):
    """编码合成 HTTP 和私有 IPC 的数据。@param value 数据。@return UTF-8 JSON。"""
    return json.dumps(value, ensure_ascii=False, separators=(',', ':')).encode()


def http_request(port, method, path, token=None, value=None, *, timeout=20, extra_headers=None, connection=None):
    """调用真实本地 HTTP。@param port 端口。@param method 方法。@param path 路径。
    @param token 合成权限。@param value 可选请求。@param timeout 秒。@param extra_headers 附加头。
    @param connection 可从外部断开的连接。@return 状态及原响应字节。
    """
    client = connection if connection is not None else HTTPConnection('127.0.0.1', port, timeout=timeout)
    headers = {'Content-Type':'application/json', 'User-Agent':AGENT, 'anthropic-version':'2023-06-01'}
    if token:
        headers['Authorization'] = 'Bearer ' + token
    if extra_headers:
        headers.update(extra_headers)
    try:
        client.request(method, path, None if value is None else json_bytes(value), headers)
        response = client.getresponse()
        return response.status, response.read()
    finally:
        client.close()


def serve(stack, handler, port=0):
    """启动角色的独立回环服务器。@param stack 生命周期。@param handler 处理器。@param port 端口。@return 服务。"""
    server = ThreadingHTTPServer(('127.0.0.1', port), handler)
    stack.callback(server.server_close)
    Thread(target=server.serve_forever, daemon=True).start()
    stack.callback(server.shutdown)
    return server


def stop(process):
    """回收验证器的进程。@param process 进程句柄。@return 无。"""
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=4)
        except TimeoutExpired:
            process.kill()
            process.wait(timeout=4)


class Endpoint(BaseHTTPRequestHandler):
    """夹具的最小 HTTP 编码和日志约定。"""

    def log_message(self, *_):
        """结构化证据由场景写入。@return 无。"""

    def reply(self, status, value, media='application/json', *, headers=()):
        """返回实际 HTTP 状态与正文。@param status 状态。@param value 数据。@param media 媒体类型。
        @param headers 受信 sender 的附加响应头。@return 无。
        """
        raw = value if type(value) is bytes else json_bytes(value)
        self.send_response(status)
        self.send_header('Content-Type', media)
        self.send_header('Content-Length', str(len(raw)))
        self.send_header('Connection', 'close')
        for name, header in headers:
            self.send_header(name,header)
        self.end_headers()
        self.wfile.write(raw)
        self.wfile.flush()
        self.close_connection = True

    def read_json(self):
        """读取本次请求的 JSON 正文。@return 数据。"""
        return json.loads(self.rfile.read(int(self.headers['Content-Length'])))


def ipc_write(pipe, value):
    """给本次进程的私有管道写完整消息。@param pipe 管道。@param value 请求。@return 无。"""
    pipe.write(json_bytes(value) + b'\n')
    pipe.flush()


def ipc_read(pipe):
    """有界等待私有 IPC 的回执。@param pipe 管道。@return 消息。"""
    if not select([pipe], [], [], 8)[0]:
        raise TimeoutError('私有 IPC 等待超时')
    raw = pipe.readline()
    if not raw:
        raise EOFError('私有 IPC 提前关闭')
    return json.loads(raw)


def worker(model_port):
    """真实本地子进程执行回环模型与固定私有 IPC。@param model_port 模拟模型端口。@return 退出码。"""
    import os

    pid = os.getpid()
    first = json.loads(sys.stdin.buffer.readline())
    role = first['role']
    status, raw = http_request(model_port, 'POST', '/model', value={'role':role,'stage':'first','pid':pid})
    assert status == 200
    initial = json.loads(raw)
    ipc_write(sys.stdout.buffer, {**initial, 'pid':pid})
    if role == 'original':
        result = json.loads(sys.stdin.buffer.readline())
        assert result['tool_use_id'] == initial['internal_id'] and result['type'] == 'tool_result'
        ipc_write(sys.stdout.buffer, {'kind':'ack','pid':pid,'internal_id':result['tool_use_id']})
        status, raw = http_request(model_port, 'POST', '/model', value={
            'role':role,'stage':'continuation','pid':pid,'result':result})
        assert status == 200
        ipc_write(sys.stdout.buffer, {**json.loads(raw),'pid':pid})
    # 留到执行器实际 close，进程退出之前持续占用原名额。
    sys.stdin.buffer.read()
    return 0


def message_sse(content, stop_reason, message_id):
    """将一个结果放入普通 Messages SSE。@param content 内容块。@param stop_reason 终态。@param message_id 消息 ID。@return 字节。"""
    tool = content['type'] == 'tool_use'
    start = {**content, 'input':{}} if tool else {'type':'text','text':''}
    delta = ({'type':'input_json_delta','partial_json':json_bytes(content['input']).decode()} if tool
             else {'type':'text_delta','text':content['text']})
    events = [
        {'type':'message_start','message':{'id':message_id,'role':'assistant','type':'message',
            'model':MODEL,'content':[],'stop_reason':None,'stop_sequence':None,
            'usage':{'input_tokens':10,'output_tokens':1}}},
        {'type':'content_block_start','index':0,'content_block':start},
        {'type':'content_block_delta','index':0,'delta':delta},
        {'type':'content_block_stop','index':0},
        {'type':'message_delta','delta':{'stop_reason':stop_reason,'stop_sequence':None},'usage':{'output_tokens':8}},
        {'type':'message_stop'},
    ]
    return b''.join(map(frame, events))


class HandoffFixture:
    """把实际交接组件接到验收用 sender、真实子进程和模拟模型。"""

    def __init__(self, folder, account_id, principal):
        """创建单账号测试边界。@param folder 证据目录。@param account_id Gateway 签发的账号。@return 无。"""
        from tui_capacity import TuiCapacity
        from tui_handoff import TuiToolHandoff
        from tui_process import TuiProcessExecutor
        from tui_tool_receipts import ToolReceiptStore, ToolTurn

        self.folder = folder
        self.log = folder/'fixture.jsonl'
        self.account_id = account_id
        self.capacity = TuiCapacity(4, budget_bytes=512*MIB, fixed_reserve_bytes=256*MIB,
                                    per_process_reserve_bytes=256*MIB, max_waiters=1)
        self.executor = TuiProcessExecutor(self.capacity, self.spawn)
        self.store = ToolReceiptStore(folder/'receipts')
        self.handoff_type = TuiToolHandoff
        self.turn = ToolTurn(str(account_id), principal, str(uuid4()), 'original')
        self.accept_server_session = False
        self.new_turn = ToolTurn(str(account_id), principal, str(uuid4()), 'competing')
        self.external_id = 'toolu_public_' + uuid4().hex
        self.internal_id = 'toolu_private_' + uuid4().hex
        self.handoff = None
        self.processes = []
        self.session_keys = []
        self.reservations = {}
        self.cancelled_reservations = set()
        self.sent_identities = {}
        self.continuation_gate = None
        self.response_gate = None
        self.quiesce_gate = None
        self.status_known = True
        self.quiesce_allowed = True
        self.interrupt_response = False
        self.model_activity = []
        self.sender_requests = []
        self.fixture_errors = []
        self.acknowledged = 0
        self.cancel_new = Event()
        self.lock = Lock()
        self.model_port = None

    def attach_model(self, stack):
        """运行真实子进程可访问的合成模型。@param stack 生命周期。@return 无。"""
        fixture = self

        class Model(Endpoint):
            """仅实现本场景的三种回环模型请求。"""

            def do_POST(self):
                """接收子进程的实际请求并记录。@return 无。"""
                try:
                    body = self.read_json()
                    assert self.path == '/model'
                    role, stage, pid = (body[key] for key in ('role','stage','pid'))
                    with fixture.lock:
                        fixture.model_activity.append((role, stage, pid))
                    record(fixture.log, 'model_post', role=role, stage=stage, pid=pid)
                    if (role, stage) == ('original','first'):
                        value = {'kind':'offer','internal_id':fixture.internal_id,'name':'Read','arguments':ARGUMENTS}
                    elif (role, stage) == ('original','continuation'):
                        result = body['result']
                        assert result['tool_use_id'] == fixture.internal_id and pid == fixture.processes[0].pid
                        value = {'kind':'final', 'text':'READ_RESULT_' + sha256(result['content'].encode()).hexdigest()}
                    else:
                        assert (role, stage) == ('competing','first')
                        value = {'kind':'final','text':'COMPETING_TURN_RAN'}
                    self.reply(200, value)
                except Exception as error:
                    fixture.failure(error)
                    self.reply(400, {'error':'fixture model rejected request'})

        self.model_port = serve(stack, Model).server_port

    def spawn(self, session_key):
        """为执行器提供真正的私有 Popen。@param session_key 组件的会话键。@return 子进程。"""
        from subprocess import PIPE

        with self.lock:
            prior = {item.pid:item.poll() for item in self.processes}
            assert all(code is not None for code in prior.values())
            destination = self.folder/f'worker-{len(self.processes)}.stderr'
            with destination.open('wb') as stderr:
                process = Popen([sys.executable, str(Path(__file__).resolve()), '--worker', str(self.model_port)],
                                stdin=PIPE, stdout=PIPE, stderr=stderr, env=CLEAN_ENV, cwd=self.folder, bufsize=0)
            self.processes.append(process)
            self.session_keys.append(session_key)
            record(self.log, 'worker_spawned', pid=process.pid, prior_exit_codes=prior)
            return process

    def failure(self, error):
        """保留夹具内部失败。@param error 异常。@return 无。"""
        self.fixture_errors.append(repr(error))
        record(self.log, 'fixture_error', reason=repr(error))

    def events(self, name, **fields):
        """读取同阶段及指定归属的实际事件。@param name 事件名。@param fields 归属键。@return 匹配记录。"""
        rows = (json.loads(line) for line in self.log.read_text().splitlines())
        return [row for row in rows if row['event']==name and all(row.get(k)==v for k,v in fields.items())]

    def model_snapshot(self):
        """读取回环模型已接收的请求。@return 同一时刻的请求清单。"""
        with self.lock:
            return tuple(self.model_activity)

    def parse_public(self, body):
        """校验公开消息及工具关联。@param body 正文。@return 逻辑入口及可选工具结果。"""
        messages = body['messages']
        tail = messages[-1]
        content = tail['content'] if type(tail['content']) is list else [{'type':'text','text':tail['content']}]
        result = [part for part in content if part.get('type') == 'tool_result']
        text = [part['text'] for part in content if part.get('type') == 'text']
        assert tail['role']=='user' and body['stream'] is True
        if result:
            block, = result
            previous = messages[-2]
            assert previous['role']=='assistant' and any(part.get('type')=='tool_use'
                and part.get('id')==block['tool_use_id'] and part.get('name')=='Read'
                and part.get('input')==ARGUMENTS for part in previous['content'])
            return 'continuation', block
        if ORIGINAL in text:
            return 'original', None
        assert COMPETING in text
        return 'competing', None

    def capture_sender(self, request, prepared):
        """接入 v1 的普通 sender 封套。@param request 请求。@param prepared 网关封套。@return 无。"""
        kind, result = self.parse_public(request.read_json())
        self.dispatch(request, prepared, kind, result)

    def dispatch(self, request, prepared, kind, result, handoff=None):
        """只有已经入 HTTP 槽的请求可以执行。@param request 请求。@param prepared 身份。
        @param kind 业务阶段。@param result 工具结果。@param handoff 可选的已保留进程。@return 无。
        """
        with self.lock:
            assert not any(item['kind'] == kind for item in self.sender_requests)
            entry = {'kind':kind,'request_id':prepared['request_id'],'account_id':prepared['account_id']}
            self.sender_requests.append(entry)
        record(self.log, 'gateway_sender_arrival', **entry, capacity=asdict(self.capacity.snapshot()))
        if kind == 'original':
            self.original(request, handoff)
        elif kind == 'competing':
            self.competing(request, handoff)
        else:
            self.continue_original(request, result)

    def candidate_prepare(self, request, identity):
        """在 HTTP 槽之外等待或验证原进程。@param request 请求。@param identity 真实 Gateway 身份。@return 无。"""
        from tui_capacity import TuiCapacityError
        from tui_messages import input_message
        from tui_tool_receipts import UnknownToolCall

        request_id = identity['reservation_id']
        body = request.read_json()
        # 夹具与正式 sender 校验同一份带会话 metadata 的请求，再向网关声明本轮支持输入策略。
        try:
            input_message(json_bytes(body), session_id=identity['session_id'])
        except ValueError:
            request.reply(422, {'error':'交互请求未通过输入校验'})
            return
        kind, result = self.parse_public(body)
        if (self.accept_server_session and kind == 'original' and self.handoff is None
                and str(identity['principal_id']) == self.turn.principal_id
                and identity['session_id'].startswith('gateway-tools-')):
            self.turn = replace(self.turn, session_id=identity['session_id'])
        turn = self.new_turn if kind == 'competing' else self.turn
        if str(identity['principal_id']) != turn.principal_id or identity['session_id'] != turn.session_id:
            record(self.log,'foreign_candidate_rejected',kind=kind,principal_id=identity['principal_id'])
            request.reply(403, {'error':'foreign turn'})
            return
        if identity.get('continuation_only') and result is None:
            record(self.log,'candidate_new_turn_during_drain',request_id=request_id)
            request.reply(429, {'error':'account is draining'})
            return
        if result is not None:
            try:
                receipt = self.store.read(turn, result['tool_use_id'])
            except UnknownToolCall:
                record(self.log,'candidate_unknown_tool_rejected',request_id=request_id)
                request.reply(403, {'error':'unknown tool call'})
                return
            assert self.handoff is not None
            assert (receipt.internal_id, receipt.backend, receipt.generation, receipt.state) == (
                self.internal_id,'tui',self.handoff.handle.generation,'delivery_unknown')
            process = self.executor.resume(self.session_keys[0], self.handoff.handle)
            assert process is self.processes[0] and process.poll() is None
            record(self.log,'candidate_continuation_verified',pid=process.pid,internal_id=receipt.internal_id,
                   principal_id=identity['principal_id'],generation=receipt.generation)
        timeout = min(15, identity['deadline_unix_ms']/1000-time())
        if timeout <= 0:
            request.reply(429, {'error':'deadline'})
            return
        cancel = Event()
        expiry = Timer(timeout, self.candidate_cancel, (identity,'deadline'))
        expiry.daemon = True
        entry = {'identity':identity,'kind':kind,'result':result,'cancel':cancel,'timer':expiry,
                 'phase':'waiting','handoff':None}
        with self.lock:
            if request_id in self.cancelled_reservations or request_id in self.reservations:
                request.reply(409, {'error':'reservation unavailable'})
                return
            if any(row['kind']==kind for row in self.reservations.values()):
                request.reply(409, {'error':'turn already reserved'})
                return
            self.reservations[request_id] = entry
            expiry.start()
        record(self.log,'candidate_prepare',kind=kind,request_id=request_id,principal_id=identity['principal_id'])
        handoff = None
        try:
            if result is None:
                handoff = self.handoff_type.start(turn,self.store,self.executor,timeout=timeout,cancel_event=cancel)
        except TuiCapacityError as error:
            self.candidate_cancel(identity)
            record(self.log,'candidate_capacity_rejected',kind=kind,reason=error.code)
            request.reply(429, {'error':error.code})
            return
        with self.lock:
            if not cancel.is_set():
                entry.update(phase='ready',handoff=handoff)
                record(self.log,'candidate_prepared',kind=kind,request_id=request_id,
                       model_posts=len(self.model_activity))
                handoff_kind = 'continuation' if result is not None else 'new'
                request.reply(204,b'',headers=(('x-v3-tui-handoff-kind',handoff_kind),('x-v3-tui-input-policy','1')))
                return
        if handoff is not None:
            self.executor.close(handoff.handle)
        request.reply(429, {'error':'reservation cancelled'})

    def candidate_cancel(self, identity, source='fixture'):
        """回收未提交预留。@param identity 受信请求身份。@param source 触发方。@return 无。"""
        key = identity['reservation_id']
        with self.lock:
            entry = self.reservations.get(key)
            if entry is not None and (entry['identity']!=identity or entry['phase']=='submitted'):
                return
            if key in self.cancelled_reservations:
                return
            self.cancelled_reservations.add(key)
            if entry is None:
                return
            self.reservations.pop(key)
            entry['cancel'].set()
            entry['timer'].cancel()
        if entry['handoff'] is not None:
            self.executor.close(entry['handoff'].handle)
        record(self.log,'candidate_aborted',kind=entry['kind'],request_id=key,source=source)

    def candidate_send(self, request, identity):
        """只消费一次先前冻结的预留。@param request 请求。@param identity 受信身份。@return 无。"""
        key = identity['reservation_id']
        with self.lock:
            entry = self.reservations.get(key)
            if not entry or entry['identity']!=identity or entry['phase']!='ready':
                record(self.log,'candidate_send_rejected',request_id=key,model_posts=len(self.model_activity))
                request.reply(409,{'error':'reservation unavailable'})
                return
            entry['phase'] = 'submitted'
            entry['timer'].cancel()
            self.sent_identities[entry['kind']] = identity
            record(self.log,'candidate_send',kind=entry['kind'],request_id=key,
                   model_posts=len(self.model_activity))
        try:
            self.dispatch(request,{**identity,'request_id':key},entry['kind'],entry['result'],entry['handoff'])
        finally:
            with self.lock:
                self.reservations.pop(key, None)
                self.cancelled_reservations.add(key)

    def original(self, request, handoff=None):
        """通过真实 Handoff 发布一次工具调用。@param request 请求。@param handoff 已保留进程。@return 无。"""
        self.handoff = handoff or self.handoff_type.start(self.turn, self.store, self.executor, timeout=3)
        process = self.processes[0]
        ipc_write(process.stdin, {'role':'original'})
        offer = ipc_read(process.stdout)
        assert offer['kind']=='offer' and offer['pid']==process.pid and offer['internal_id']==self.internal_id
        kwargs = {'internal_id':offer['internal_id'],'name':offer['name'],'arguments':offer['arguments']}
        block = self.handoff.offer(self.external_id, **kwargs)
        assert block and self.handoff.offer(self.external_id, **kwargs) is None
        state = self.store.read(self.turn, self.external_id).state
        assert state == 'delivery_unknown'
        record(self.log, 'offer_once', external_id=self.external_id, internal_id=self.internal_id,
               pid=process.pid, state=state)
        request.reply(200, message_sse(block, 'tool_use', 'msg_fixture_original'), 'text/event-stream')

    def competing(self, request, handoff=None):
        """执行新轮。@param request 请求。@param handoff 已保留进程。@return 无。"""
        from tui_capacity import TuiCapacityError

        try:
            handoff = handoff or self.handoff_type.start(self.new_turn, self.store, self.executor,
                                                        timeout=15, cancel_event=self.cancel_new)
        except TuiCapacityError as error:
            assert error.code == 'capacity_cancelled'
            record(self.log, 'competing_cancelled', reason=error.code)
            request.reply(400, {'type':'error','error':{'type':'invalid_request_error',
                'message':'FIXTURE_QUEUE_CANCELLED'}})
            return
        process = self.processes[1]
        try:
            ipc_write(process.stdin, {'role':'competing'})
            answer = ipc_read(process.stdout)
            assert answer['kind']=='final' and answer['pid']==process.pid
        finally:
            self.executor.close(handoff.handle)
        request.reply(200, message_sse({'type':'text','text':answer['text']},
            'end_turn','msg_fixture_competing'), 'text/event-stream')

    def send_and_ack(self, process, block):
        """从原 Popen 的私有 IPC 读取真实子进程确认。@param process 进程。@param block 内部工具结果。@return ACK ID。"""
        assert process is self.processes[0] and process.poll() is None
        assert block['tool_use_id'] == self.internal_id
        ipc_write(process.stdin, block)
        ack = ipc_read(process.stdout)
        assert ack['kind']=='ack' and ack['pid']==process.pid and ack['internal_id']==self.internal_id
        self.acknowledged += 1
        record(self.log,'private_ipc_ack',pid=ack['pid'],internal_id=ack['internal_id'])
        return ack['internal_id']

    def continue_original(self, request, result):
        """由实际持久回执与原进程收口原轮。@param request 请求。@param result 外部块。@return 无。"""
        assert result['tool_use_id'] == self.external_id and self.handoff is not None
        assert self.store.submit(self.turn, result)
        assert not self.store.submit(self.turn, result)
        state = self.store.read(self.turn,self.external_id).state
        assert state == 'received'
        record(self.log,'result_saved_once',state=state,capacity=asdict(self.capacity.snapshot()))
        if self.continuation_gate is not None:
            assert self.continuation_gate.wait(8)
        assert self.handoff.deliver(self.external_id, internal_id=self.internal_id, send_and_ack=self.send_and_ack)
        assert not self.handoff.deliver(self.external_id, internal_id=self.internal_id, send_and_ack=self.send_and_ack)
        assert self.store.read(self.turn, self.external_id).state == 'confirmed'
        record(self.log,'result_confirmed',pid=self.processes[0].pid)
        answer = ipc_read(self.processes[0].stdout)
        assert answer['kind']=='final' and answer['pid']==self.processes[0].pid
        if self.interrupt_response:
            # 原进程已收到工具结果并调用模型。只切断答复通道，等待外部检查后再收尾。
            record(self.log,'sender_response_disconnected',pid=self.processes[0].pid)
            request.close_connection = True
            request.connection.shutdown(socket.SHUT_RDWR)
            assert self.response_gate.wait(12)
        self.store.close_turn(self.turn)
        receipt = self.store.read(self.turn,self.external_id)
        assert receipt.state=='closed' and receipt.result is None
        self.executor.close(self.handoff.handle)
        if not self.interrupt_response:
            if self.response_gate is not None:
                # 先退还物理名额，仍持有 Gateway 的普通槽，给新轮制造已准备但未提交的窗口。
                record(self.log,'original_waiting_to_reply')
                assert self.response_gate.wait(12)
            request.reply(200, message_sse({'type':'text','text':answer['text']},
                'end_turn','msg_fixture_continuation'), 'text/event-stream')

    def cleanup(self):
        """只回收夹具创建的进程和管道。@return 无。"""
        self.cancel_new.set()
        for entry in list(self.reservations.values()):
            self.candidate_cancel(entry['identity'])
        if self.handoff is not None:
            self.executor.close(self.handoff.handle)
        for process in self.processes:
            stop(process)
            process.stdin.close()
            process.stdout.close()


@contextmanager
def gateway_ingress(folder, binary, concurrency, candidate, *, wait_seconds=None, fixture_factory=HandoffFixture,
                    second_account=False, native_sender=None, account_options=None, log_filter='warn'):
    """启动真实 Gateway 和回环 v3 登记。@param folder 输出。@param binary 固定基线制品。
    @param concurrency 公开 HTTP 槽数。@param candidate 候选模式。@param wait_seconds 可选准入期限。
    @param fixture_factory 仅供回环验收替换模拟 sender。@param second_account 额外旧转发账号。
    @param native_sender 可选真实原生 sender 启动函数。@param account_options 合成账号附加参数。
    @param log_filter 隔离 Gateway 的日志过滤器。
    @return 配置后的夹具及私有重放探针。
    """
    folder.mkdir()
    internal, sender_secret, admin = (uuid4().hex + uuid4().hex for _ in range(3))
    deployment, environment = 'local-handoff-' + uuid4().hex[:10], uuid4().hex
    host = 'flower2api-' + sha256(deployment.encode()).hexdigest()[:12] + '-' + environment
    other_environment = uuid4().hex
    other_host = 'flower2api-' + sha256(deployment.encode()).hexdigest()[:12] + '-' + other_environment
    (folder/'hosts').write_text('127.0.0.1 localhost ' + host + ' ' + other_host + '\n')
    release = CANDIDATE_RELEASE if candidate else 'fixture'
    binding = {'account_id':1, 'release_id':release, 'environment_id':environment, 'generation':1,
               'secret':sender_secret, 'endpoint':'http://'+host+':8091'}
    other = {**binding,'account_id':2,'environment_id':other_environment,'secret':uuid4().hex,
             'endpoint':'http://'+other_host+':8091'}
    bindings = {1:binding, **({2:other} if second_account else {})}
    adapter = {}

    def idle():
        fixture = adapter.get('fixture')
        if fixture is None:
            return False
        with fixture.lock:
            if fixture.reservations or any(process.poll() is None for process in fixture.processes):
                return False
        if fixture.handoff is not None:
            from tui_tool_receipts import UnknownToolCall

            try:
                return fixture.store.read(fixture.turn,fixture.external_id).state=='closed'
            except UnknownToolCall:
                return False
        return True

    class Registry(Endpoint):
        """返回 Gateway 请求的实际实验账号 transport 绑定。"""

        def do_GET(self):
            """验证合成内部访问令牌。@return 无。"""
            path = urlsplit(self.path).path
            if self.headers.get('Authorization') != 'Bearer '+internal or not path.startswith('/internal/v3/transport/'):
                self.send_error(404)
                return
            account_id = int(path.rsplit('/',1)[-1])
            record(folder/'fixture.jsonl','registry_lookup',account_id=account_id,query=urlsplit(self.path).query)
            self.reply(200, bindings.get(account_id))

        def do_POST(self):
            """让真实配置租约复用既有 quiesce 端点。@return 无。"""
            if self.headers.get('Authorization') != 'Bearer '+internal or self.path!='/internal/v3/quiesce/1':
                self.send_error(404)
                return
            lease = self.read_json()
            assert lease['owner'].startswith('gateway-config:') and lease['generation']
            ready = idle()
            admitted = ready and adapter['fixture'].quiesce_allowed
            record(folder/'fixture.jsonl','orchestrator_quiesce',idle=ready,admitted=admitted)
            gate = adapter['fixture'].quiesce_gate
            if admitted and gate is not None:
                assert gate.wait(10), '验收未放行后台排空'
            self.reply(200 if admitted else 409,{})

    class Sender(Endpoint):
        """收到真实 Gateway 的 /internal/send 才进入交接组件。"""

        def bound(self):
            """由合成 bearer 识别受信回环账号。@return 匹配绑定。"""
            return next((item for item in bindings.values()
                         if self.headers.get('Authorization')=='Bearer '+item['secret']),None)

        def native(self):
            """把原生标准端点交给已固定制品的独立 sender。@return 无。"""
            native_port = adapter.get('native_port')
            record(folder/'fixture.jsonl','native_endpoint',method=self.command,route=self.path,
                   forwarded=native_port is not None)
            if native_port is None:
                self.reply(503,{'error':'native293 sender unavailable in fixture'})
                return
            body = self.read_json() if self.command=='POST' else None
            connection = HTTPConnection('127.0.0.1',native_port,timeout=25)
            try:
                connection.request(self.command,self.path,None if body is None else json_bytes(body),
                    {'Authorization':'Bearer '+sender_secret,'Content-Type':'application/json'})
                source = connection.getresponse()
                payload = source.read()
                self.send_response(source.status)
                for name,value in source.getheaders():
                    if name.lower() not in ('server','date','content-length','transfer-encoding','connection'):
                        self.send_header(name,value)
                self.send_header('Content-Length',str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)
                self.close_connection = True
            finally:
                connection.close()

        def do_GET(self):
            """用现有 sender 状态返回归属明确的候选能力。@return 无。"""
            actual = self.bound()
            if actual is None:
                self.send_error(403)
                return
            if self.path.startswith('/internal/native/') and actual['account_id']==1:
                self.native()
            elif self.path=='/internal/status':
                value = {key:actual[key] for key in ('environment_id','generation')}
                if candidate and actual['account_id']==1:
                    available = actual['generation']!=1 or idle()
                    reported = available if adapter['fixture'].status_known else None
                    value['tui_v2']={'protocol':1,'ready':True,'idle':reported}
                    record(folder/'fixture.jsonl','candidate_status_report',idle=reported)
                self.reply(200,value)
            else:
                self.send_error(404)

        def do_POST(self):
            """验证 v3 封套和隔离候选预留，再进实际组件。@return 无。"""
            action = self.path.removeprefix('/internal/tui-v2/') if candidate else ''
            actual = self.bound()
            if actual is None:
                self.send_error(403)
                return
            if self.path.startswith('/internal/native/') and actual['account_id']==1:
                self.native()
                return
            if self.path != '/internal/send' and (actual['account_id']!=1 or action not in ('prepare','send','cancel')):
                self.send_error(404)
                return
            fixture = adapter['fixture']
            try:
                header = 'x-v3-tui-reservation' if action in ('prepare','send','cancel') else 'x-v3-request'
                envelope = json.loads(b64decode(self.headers[header], validate=True))
                for key in ('account_id','environment_id','generation'):
                    assert envelope[key] == actual[key]
                if action == 'prepare':
                    record(fixture.log,'candidate_prepare_rpc',request_id=envelope['reservation_id'])
                    fixture.candidate_prepare(self,envelope)
                elif action == 'send':
                    record(fixture.log,'candidate_send_rpc',request_id=envelope['reservation_id'])
                    fixture.candidate_send(self,envelope)
                elif action == 'cancel':
                    record(fixture.log,'candidate_cancel_rpc',request_id=envelope['reservation_id'])
                    fixture.candidate_cancel(envelope,'gateway')
                    self.reply(204,b'')
                else:
                    assert envelope['method']=='POST' and urlsplit(envelope['target_url']).path=='/v1/messages'
                    if actual['account_id']==2:
                        self.read_json()
                        record(fixture.log,'other_legacy_sent',account_id=2)
                        self.reply(200,message_sse({'type':'text','text':'OTHER_LEGACY_ACCOUNT'},'end_turn',
                            'msg_fixture_other'),'text/event-stream')
                    else:
                        assert not candidate
                        fixture.capture_sender(self,envelope)
            except Exception as error:
                fixture.failure(error)
                self.reply(400, {'type':'error','error':{'type':'invalid_request_error',
                    'message':'fixture sender failed'}})


    with ExitStack() as stack:
        registry = serve(stack, Registry)
        serve(stack, Sender, 8091)
        with socket.socket() as address:
            address.bind(('127.0.0.1',0))
            port = address.getsockname()[1]
        options = {
            'SERVER_HOST':'127.0.0.1', 'SERVER_PORT':str(port), 'DATABASE_DRIVER':'sqlite',
            'DATABASE_DSN':'/work/gateway.db', 'ADMIN_PASSWORD':admin, 'LOG_LEVEL':log_filter,
            'V3_DEPLOYMENT_ID':deployment, 'V3_RELEASE':release, 'V3_INTERNAL_TOKEN':internal,
            'V3_RUNTIME_URL':f'http://127.0.0.1:{registry.server_port}', 'PATH':'/usr/bin:/bin', 'HOME':'/work',
        }
        flags = [item for key, value in options.items() for item in ('--setenv',key,value)]
        command = [
            'bwrap','--die-with-parent','--unshare-pid','--unshare-ipc','--clearenv','--cap-drop','ALL',
            '--ro-bind','/usr','/usr','--symlink','usr/bin','/bin','--symlink','usr/lib','/lib',
            '--symlink','usr/lib64','/lib64','--dir','/etc','--ro-bind',str(folder/'hosts'),'/etc/hosts',
            '--ro-bind','/etc/nsswitch.conf','/etc/nsswitch.conf','--ro-bind','/etc/passwd','/etc/passwd',
            '--ro-bind','/etc/group','/etc/group','--proc','/proc','--dev','/dev','--tmpfs','/tmp',
            '--bind',str(folder),'/work','--chdir','/work','--ro-bind',str(binary),'/lab/gateway',
            *flags,'--','/lab/gateway',
        ]
        log = stack.enter_context((folder/'gateway.log').open('wb'))
        process = Popen(command, stdout=log, stderr=log, env=CLEAN_ENV)
        stack.callback(stop,process)

        def admin_api(method, path, value=None):
            status, raw = http_request(port, method, path, admin, value, timeout=5)
            if status not in (200,201):
                raise RuntimeError(f'Gateway 本地管理入口 {path} 返回 {status}')
            return json.loads(raw)

        def ready():
            if process.poll() is not None:
                raise RuntimeError(f'Gateway 提前退出，状态 {process.returncode}，详见 gateway.log')
            try:
                admin_api('GET','/admin/accounts')
            except OSError:
                return False
            return True

        wait_for(ready,'实际 Gateway 未就绪，详见 gateway.log',35)
        settings = {'allowed_user_agents':'flower-tui-handoff*'}
        if wait_seconds is not None:
            settings['v3_admission_wait_seconds'] = str(wait_seconds)
        admin_api('PUT','/admin/settings',settings)
        account = admin_api('POST','/admin/accounts',{
            'email':'handoff@fixture.test','request_backend':'legacy','setup_token':'fixture-'+uuid4().hex,
            'concurrency':concurrency,'rpm_limit':0,'auto_telemetry':False,'auto_poll_usage':False,
            **(account_options or {})})
        assert account['id']==binding['account_id'] and account['concurrency']==concurrency
        ingress = admin_api('POST','/admin/tokens',{'name':'fixture-scoped','allowed_accounts':str(account['id'])})
        stored, = [row for row in admin_api('GET','/admin/tokens')['data'] if row['name']=='fixture-scoped']
        assert stored['id'] > 0
        fixture = fixture_factory(folder,account['id'],str(stored['id']))
        if candidate:
            fixture.continuation_gate = Event()
            fixture.response_gate = Event()
            fixture.foreign_key = admin_api('POST','/admin/tokens',
                {'name':'fixture-foreign','allowed_accounts':str(account['id'])})['token']
            fixture.blocked_key = admin_api('POST','/admin/tokens',
                {'name':'fixture-blocked','blocked_accounts':str(account['id'])})['token']
        adapter['fixture'] = fixture
        fixture.attach_model(stack)
        stack.callback(fixture.cleanup)
        if native_sender is not None:
            adapter['native_port'] = native_sender(stack,binding)
        if candidate:
            selected = admin_api('PUT','/admin/accounts/1',{'request_backend':'tui_v2'})
            assert selected['request_backend']=='tui_v2' and selected['request_backend_pending'] is None
        if second_account:
            peer = admin_api('POST','/admin/accounts',{'email':'other@fixture.test','setup_token':'fixture-'+uuid4().hex,
                'request_backend':'legacy','auto_telemetry':False,'auto_poll_usage':False})
            assert peer['id']==2
            fixture.other_key = admin_api('POST','/admin/tokens',{'name':'other-scoped','allowed_accounts':'2'})['token']
        fixture.admin_token = admin
        def restart_gateway():
            """保留同一数据库、账号 sender 和端口，重新运行真实网关。@return 无。"""
            nonlocal process
            stop(process)
            process = Popen(command, stdout=log, stderr=log, env=CLEAN_ENV)
            stack.callback(stop,process)
            wait_for(ready,'重启后的实际 Gateway 未就绪，详见 gateway.log',35)

        fixture.restart_gateway = restart_gateway
        def set_test_generation(generation):
            # 仅为错代负例模拟一个空的新 sender，以验证旧轮不能用它证明排空。
            binding['generation'] = generation

        fixture.set_test_generation = set_test_generation
        write_json(folder/'binding.json', {'gateway_account_id':account['id'],'gateway_backend':'tui_v2' if candidate else 'legacy',
            'gateway_environment_id':environment,'gateway_environment_generation':1,'gateway_http_slots':concurrency,
            'validation_route':'candidate' if candidate else 'legacy',
            'adapter_principal':fixture.turn.principal_id,'adapter_session_id':fixture.turn.session_id,
            'adapter_turn_id':fixture.turn.turn_id,'external_tool_id':fixture.external_id,'internal_tool_id':fixture.internal_id})
        def replay(kind):
            identity = fixture.sent_identities[kind]
            status, _ = http_request(8091,'POST','/internal/tui-v2/send',sender_secret,
                                     extra_headers={'x-v3-tui-reservation':b64encode(json_bytes(identity)).decode()})
            return identity['reservation_id'], status

        yield port, ingress['token'], admin_api, fixture, replay


def stream_body(messages, session):
    """构造公开 Messages 请求。@param messages 会话结构。@return 请求正文。"""
    body = {'model':MODEL,'stream':True,'max_tokens':128,'messages':messages,
            'tools':[{'name':'Read','description':'Read the fixture note.',
                'input_schema':{'type':'object','properties':{'path':{'type':'string'}},'required':['path']}}]}
    if session is not None:
        body['metadata'] = {'user_id':json.dumps({'session_id':session})}
    return body


def public_post(folder, name, port, key, messages, session, *, connection=None):
    """通过实际 Gateway 公开接口记录一次 POST 的原始应答。@param folder 证据。@param name 阶段。
    @param port 网关端口。@param key 测试令牌。@param messages 消息。@param session 公开会话。
    @param connection 可由测试关闭的连接。@return 状态和 SSE。
    """
    record(folder/'client.jsonl','client_post',name=name)
    status, raw = http_request(port,'POST','/v1/messages',key,stream_body(messages, session),connection=connection)
    (folder/(name+'.body')).write_bytes(raw)
    record(folder/'client.jsonl','client_reply',name=name,status=status)
    events = [json.loads(line[5:]) for line in raw.splitlines() if line.startswith(b'data:')]
    return status, events


def delivered_tool(result):
    """按公开 SSE 重组工具，保留真实外部 ID。@param result HTTP 应答。@return 工具块。"""
    status, events = result
    assert status==200 and events[-1]['type']=='message_stop'
    call, = [event['content_block'] for event in events if event['type']=='content_block_start'
             and event['content_block']['type']=='tool_use']
    partial = ''.join(event['delta']['partial_json'] for event in events if event['type']=='content_block_delta'
                      and event['delta']['type']=='input_json_delta')
    assert any(e['type']=='message_delta' and e['delta']['stop_reason']=='tool_use' for e in events)
    return {**call,'input':json.loads(partial)}


def final_text(result):
    """核对公开成功终态并重组正文。@param result HTTP 应答。@return 文本。"""
    status, events = result
    assert status==200 and events[-1]['type']=='message_stop'
    assert any(e['type']=='message_delta' and e['delta']['stop_reason']=='end_turn' for e in events)
    return ''.join(event['delta']['text'] for event in events if event['type']=='content_block_delta')


def check_replay(fixture, replay):
    """使用原已消费预留向私有 sender 重放。@param fixture 计数。@param replay 受信连接。@return HTTP 证据。"""
    key = fixture.sent_identities['continuation']['reservation_id']
    before = fixture.model_snapshot()
    assert len(fixture.events('candidate_send_rpc',request_id=key))==1
    replayed_key, status = replay('continuation')
    assert replayed_key==key and status==409
    assert len(fixture.events('candidate_send_rpc',request_id=key))==2
    assert len(fixture.events('candidate_send',request_id=key))==1
    assert len(fixture.events('candidate_send_rejected',request_id=key))==1
    assert fixture.model_snapshot()==before and fixture.acknowledged==1
    record(fixture.folder/'client.jsonl','private_reservation_replay',status=status,request_id=key,
           model_posts_before=len(before),model_posts_after=len(before))
    return {'status':status,'added_model_posts':0}


def scenario(folder, binary, concurrency, *, candidate=False, boundary=None):
    """对照有、无 Gateway 剩余槽时的真实工具续轮。@param folder 证据。
    @param binary Gateway。@param concurrency 网关槽数。@param candidate 候选模式。
    @param boundary 可选断点。@return 结论和证据。
    """
    opts = {'wait_seconds':4} if boundary=='deadline' else {}
    with gateway_ingress(folder,binary,concurrency,candidate,**opts) as (
            port,key,admin,fixture,replay), ExitStack() as stack:
        fixture.interrupt_response = boundary=='unknown'
        with ThreadPoolExecutor(max_workers=2) as threads:
            original = [{'role':'user','content':ORIGINAL}]
            def capacity_view():
                listing = admin('GET', '/admin/accounts')
                value, = [row for row in listing['data'] if row['id'] == fixture.account_id]
                return {name:value[name] for name in ('active_requests','queued_requests','current_concurrency_units')}

            try:
                offer = delivered_tool(public_post(folder,'original',port,key,original,fixture.turn.session_id))
                assert offer == {'type':'tool_use','name':'Read','id':fixture.external_id,'input':ARGUMENTS}
                wait_for(lambda:capacity_view()['active_requests']==0,'第一响应结束后 Gateway 槽位未释放')
                assert fixture.capacity.snapshot().in_use == 1
                process = fixture.processes[0]
                assert process.poll() is None
                local_dir = folder/'outer-client'
                local_dir.mkdir(mode=0o700)
                note = local_dir/'isolated-note.txt'
                expected = f'NOTE_ONLY_{uuid4().hex}\n只读回环样本。\n'
                note.write_text(expected)
                note.chmod(0o400)
                file_monitor = monitor_read(stack,note)
                # 发起一个不同会话的新轮，当前占用的是真实 sender 排队和 Gateway HTTP 槽。
                queued_connection = HTTPConnection('127.0.0.1',port,timeout=20) if boundary=='disconnect' else None
                queued = threads.submit(public_post,folder,'competing',port,key,
                                        [{'role':'user','content':COMPETING}],fixture.new_turn.session_id,
                                        connection=queued_connection)
                wait_for(lambda:fixture.capacity.snapshot().waiting==1,'公开新轮未到账号进程等待队列')
                gateway_waiter = capacity_view()
                assert gateway_waiter['active_requests']==(0 if candidate else 1)
                assert len(fixture.processes)==1 and not queued.done()
                record(folder/'client.jsonl','new_turn_queued',gateway=gateway_waiter,
                       tui=asdict(fixture.capacity.snapshot()))
                assert offer['input']['path'] == note.name
                content = note.read_text()
                assert content == expected
                record(folder/'client.jsonl','client_read_returned_tool',tool_id=offer['id'],bytes=len(content.encode()))
                follow = [*original,{'role':'assistant','content':[offer]},
                          {'role':'user','content':[{'type':'tool_result','tool_use_id':offer['id'],'content':content}]}]
                foreign = {}
                if candidate and boundary is None:
                    unknown_id = 'toolu_unknown_' + uuid4().hex
                    unknown = [*original,{'role':'assistant','content':[{**offer,'id':unknown_id}]},
                               {'role':'user','content':[{**follow[-1]['content'][0],'tool_use_id':unknown_id}]}]
                    for name, test_key, session, messages, expected_status, prepare_calls in (
                        ('unauthenticated',None,fixture.turn.session_id,follow,401,0),
                        ('blocked_account',fixture.blocked_key,fixture.turn.session_id,follow,503,0),
                        ('unknown_tool',key,fixture.turn.session_id,unknown,400,1),
                        ('foreign_principal',fixture.foreign_key,fixture.turn.session_id,follow,400,1),
                        ('foreign_session',key,str(uuid4()),follow,400,1),
                    ):
                        before = fixture.model_snapshot()
                        prepared_before = len(fixture.events('candidate_prepare_rpc'))
                        outcome = public_post(folder,name,port,test_key,messages,session)
                        assert outcome[0]==expected_status, (name,outcome[0])
                        assert fixture.model_snapshot()==before
                        assert len(fixture.events('candidate_prepare_rpc'))-prepared_before==prepare_calls
                        foreign[name] = {'status':outcome[0],'added_model_posts':0,'prepare_calls':prepare_calls}
                        record(folder/'client.jsonl','rejected_without_model',name=name,
                               model_posts_before=len(before),model_posts_after=len(before))
                    assert fixture.store.read(fixture.turn,offer['id']).state=='delivery_unknown'
                    assert fixture.acknowledged==0 and capacity_view()==gateway_waiter
                continuing = threads.submit(public_post,folder,'continuation',port,key,follow,fixture.turn.session_id)
                blocked = None
                admitted = None
                presubmit = None
                abandoned = None
                replayed = None
                unknown_submission = None
                public_answer = None
                continuation_status = 200
                if candidate:
                    wait_for(lambda:fixture.store.read(fixture.turn,offer['id']).state=='received',
                             '受信原轮在普通 HTTP 准入后没有保存结果',8)
                    admitted = capacity_view()
                    assert admitted['active_requests']==1 and admitted['queued_requests']==0
                    assert fixture.capacity.snapshot().waiting==1 and not queued.done() and not continuing.done()
                    record(folder/'client.jsonl','ordinary_slot_used_by_continuation',gateway=admitted,
                           tui=asdict(fixture.capacity.snapshot()))
                    fixture.continuation_gate.set()
                    if boundary=='unknown':
                        continuation_status, _ = continuing.result(timeout=8)
                        assert continuation_status==502
                        assert json.loads((folder/'continuation.body').read_bytes())['error']['type']=='upstream_error'
                        assert fixture.events('sender_response_disconnected',pid=process.pid)
                        assert fixture.store.read(fixture.turn,offer['id']).state=='confirmed'
                        assert process.poll() is None and not queued.done()
                        assert fixture.model_snapshot()==(('original','first',process.pid),
                                                          ('original','continuation',process.pid))
                        replayed = check_replay(fixture,replay)
                        assert not fixture.events('candidate_cancel_rpc',
                            request_id=fixture.sent_identities['continuation']['reservation_id'])
                        unknown_submission = {'original_pid_alive_after_502':True,'send_calls_before_replay':1,
                                              'gateway_cancel_calls':0,'model_posts_at_disconnect':2,
                                              'continuation_model_posts':1,'private_ipc_acks':1}
                        record(folder/'client.jsonl','submission_unknown',**unknown_submission)
                    else:
                        prepared, = wait_for(lambda:fixture.events('candidate_prepared',kind='competing'),
                                             '新轮没有完成实际 prepare')
                        waiting = wait_for(lambda:(view if (view:=capacity_view())['queued_requests']==1 else None),
                                           '已准备的新轮未进入真实 HTTP 队列',3)
                        assert waiting['active_requests']==1 and not continuing.done()
                        assert fixture.capacity.snapshot().in_use==1 and not queued.done()
                        assert fixture.events('original_waiting_to_reply') and process.poll() is not None
                        assert len(fixture.processes)==2 and fixture.processes[1].poll() is None
                        assert fixture.model_snapshot()==(('original','first',process.pid),
                                                          ('original','continuation',process.pid))
                        reservation_id = prepared['request_id']
                        assert prepared['model_posts']==2
                        assert not fixture.events('candidate_send_rpc',request_id=reservation_id)
                        presubmit = {'reservation_id':reservation_id,'gateway':waiting,'model_posts':2,
                                     'added_model_posts_since_prepare':0,'send_calls':0}
                        record(folder/'client.jsonl','prepared_waiting_for_http_slot',**presubmit)
                        if boundary=='disconnect':
                            queued_connection.sock.shutdown(socket.SHUT_RDWR)
                            try:
                                queued.result(timeout=5)
                            except ConnectionError:
                                record(folder/'client.jsonl','client_disconnect',name='competing')
                            else:
                                raise AssertionError('新轮连接关闭后仍收到应答')
                        elif boundary=='deadline':
                            assert queued.result(timeout=7)[0]==429
                        if boundary in ('disconnect','deadline'):
                            wait_for(lambda:fixture.events('candidate_cancel_rpc',request_id=reservation_id),
                                     'Gateway 未通知 sender 回收预留',4)
                            aborted, = wait_for(lambda:fixture.events('candidate_aborted',request_id=reservation_id),
                                                'sender 未回收已准备的预留',4)
                            if boundary=='disconnect':
                                assert aborted['source']=='gateway'
                            assert fixture.processes[1].poll() is not None
                            assert not fixture.events('candidate_send_rpc',request_id=reservation_id)
                            assert fixture.model_snapshot()==(('original','first',process.pid),
                                                              ('original','continuation',process.pid))
                            assert fixture.capacity.snapshot().in_use==0
                            assert capacity_view()['queued_requests']==0 and not continuing.done()
                            abandoned = {'source':aborted['source'],'gateway_cancel_calls':1,'added_model_posts':0,
                                         'status':429 if boundary=='deadline' else None,'reserved_process_exited':True}
                            assert len(fixture.events('candidate_cancel_rpc',request_id=reservation_id))==1
                            record(folder/'client.jsonl','reservation_reclaimed_before_send',**abandoned)
                    fixture.response_gate.set()
                elif concurrency == 1:
                    blocked = wait_for(lambda:(view if (view:=capacity_view())['queued_requests']>=1 else None),
                                       '未能观测到续轮在实际 Gateway 队列中',8)
                    assert blocked['active_requests']==1 and not continuing.done()
                    assert [item['kind'] for item in fixture.sender_requests]==['original','competing']
                    assert fixture.capacity.snapshot().waiting==1 and fixture.acknowledged==0
                    assert fixture.store.read(fixture.turn,offer['id']).state=='delivery_unknown'
                    assert process.poll() is None
                    record(folder/'client.jsonl','gateway_slot_interlock',gateway=blocked,
                           tui=asdict(fixture.capacity.snapshot()))
                    sleep(0.25)
                    assert capacity_view() == blocked and not continuing.done() and not queued.done()
                    fixture.cancel_new.set()
                if boundary!='unknown':
                    public_answer = final_text(continuing.result(timeout=12))
                    assert public_answer == 'READ_RESULT_'+sha256(expected.encode()).hexdigest()
                if boundary=='disconnect':
                    queued_outcome = (None,[])
                else:
                    queued_outcome = queued.result(timeout=12)
                completed_competing = concurrency==2 or (candidate and abandoned is None)
                if completed_competing:
                    assert final_text(queued_outcome)=='COMPETING_TURN_RAN'
                elif not candidate:
                    assert queued_outcome[0]==400
                    assert b'FIXTURE_QUEUE_CANCELLED' in (folder/'competing.body').read_bytes()
                masks = read_counts(file_monitor)
                assert masks==[0x20,0x01,0x10] and fixture.acknowledged==1
                assert not fixture.fixture_errors, fixture.fixture_errors
                order = ['original','continuation'] if candidate else ['original','competing','continuation']
                if candidate and completed_competing:
                    order.append('competing')
                assert [item['kind'] for item in fixture.sender_requests]==order
                sender = [json.loads(line) for line in fixture.log.read_text().splitlines()]
                saved, = [row for row in sender if row['event']=='result_saved_once']
                assert saved['capacity']['in_use']==1 and saved['capacity']['waiting']==int(candidate or completed_competing)
                models_at_send = {}
                if candidate:
                    assert len(fixture.events('candidate_aborted'))==int(abandoned is not None)
                    assert not fixture.events('competing_cancelled')
                    assert len(fixture.events('candidate_continuation_verified'))==1
                    assert len(fixture.events('foreign_candidate_rejected'))==(2 if boundary is None else 0)
                    assert len(fixture.events('candidate_unknown_tool_rejected'))==int(boundary is None)
                    assert len(fixture.events('candidate_prepared'))==3
                    for kind in order:
                        prepared, = fixture.events('candidate_prepared',kind=kind)
                        sent, = fixture.events('candidate_send',kind=kind,request_id=prepared['request_id'])
                        assert sent['ns']>=prepared['ns'] and sent['model_posts']==prepared['model_posts']
                        models_at_send[kind] = sent['model_posts']
                    assert models_at_send['original']==0
                    if boundary is None:
                        replayed = check_replay(fixture,replay)
                    if boundary=='unknown':
                        assert not fixture.events('candidate_cancel_rpc',
                            request_id=fixture.sent_identities['continuation']['reservation_id'])
                assert fixture.model_activity[:2]==[('original','first',process.pid),('original','continuation',process.pid)]
                assert len(fixture.model_activity)==(3 if completed_competing else 2)
                assert all(owned.poll() is not None for owned in fixture.processes)
                final = asdict(fixture.capacity.snapshot())
                assert final=={'limit':1,'in_use':0,'waiting':0}
                final_gateway = wait_for(
                    lambda:(view if not any((view:=capacity_view()).values()) else None),
                    'Gateway HTTP 槽位和等待队列未清零')
                return {'route':'candidate' if candidate else 'legacy',
                        'boundary':boundary,'continuation_status':continuation_status,
                        'gateway_http_slots':concurrency,'original_public_posts':2,'business_public_posts':3,
                        'rejected_foreign_continuations':foreign,'ordinary_slot_used_by_continuation':admitted,
                        'models_at_send':models_at_send,'prepared_without_send':presubmit,
                        'presubmit_reclaimed':abandoned,'private_replay':replayed,
                        'unknown_submission':unknown_submission,
                        'gateway_during_physical_wait':gateway_waiter,
                        'original_pid':process.pid,'ipc_ack_count':fixture.acknowledged,'external_id':offer['id'],
                        'internal_id':fixture.internal_id,'kernel_read_events':masks,'receipt_final_state':'closed',
                        'queued_new_turn_status':queued_outcome[0],'final_tui_capacity':final,
                        'final_gateway_capacity':final_gateway,
                        'continued_with_tui_waiter':saved['capacity']['waiting']==1,'full_gateway_blocked':blocked,
                        'model_posts':len(fixture.model_activity),'final_text':public_answer}
            finally:
                fixture.cancel_new.set()
                if fixture.continuation_gate is not None:
                    fixture.continuation_gate.set()
                if fixture.response_gate is not None:
                    fixture.response_gate.set()


def main():
    """从仅回环命名空间复跑实际 Gateway 工具交接。@return 进程退出码。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--gateway',type=Path,help='独立检出 v1.33.3 构建的实际 Gateway')
    parser.add_argument('--mode',choices=('legacy','candidate','all'),default='all',
                        help='候选须用 cargo build --features tui-v2-candidate；legacy 可用原版')
    parser.add_argument('--isolated',action='store_true',help=argparse.SUPPRESS)
    parser.add_argument('--worker',type=int,help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.worker is not None:
        return worker(args.worker)
    if args.gateway is None:
        parser.error('必须传入实际 Gateway 二进制 --gateway')
    binary = args.gateway.resolve(strict=True)
    if not args.isolated:
        command = [sys.executable,str(Path(__file__).resolve()),'--gateway',str(binary),'--isolated','--mode',args.mode]
        return run(['unshare','--net','--','/bin/bash','-c','ip link set lo up && exec "$@"','public-handoff',
                    *command],env=CLEAN_ENV,check=False).returncode
    if ([row['ifname'] for row in json.loads(check_output(['ip','-j','link']))] != ['lo']
            or json.loads(check_output(['ip','-j','route']))):
        raise SystemExit('必须在仅回环的网络命名空间运行')
    orchestrator = ROOT/'services/orchestrator'
    sys.path.insert(0,str(orchestrator))
    components = ('tui_capacity.py','tui_process.py','tui_handoff.py','tui_tool_receipts.py','tui_tool_receipts_schema.py')
    hashes = {name:sha256((orchestrator/name).read_bytes()).hexdigest() for name in components}
    root = Path(mkdtemp(prefix='flower2api-tui-http-handoff-'))
    print('证据目录',root,flush=True)
    with binary.open('rb') as file:
        write_json(root/'environment.json',{'gateway_path':str(binary),'gateway_sha256':file_digest(file,'sha256').hexdigest(),
            'acceptance_baseline':BASELINE,'transport':'actual Gateway and isolated v3 sender adapter','mode':args.mode,
            'worker':'local synthetic-model Python Popen over private pipes','public_client':'real HTTP fixture',
            'component_sha256':hashes,'network':['lo']})
    observations = []
    modes = []
    if args.mode in ('legacy','all'):
        modes += [('legacy-slots-2',2,False,None),('legacy-slots-1',1,False,None)]
    if args.mode in ('candidate','all'):
        modes += [
            ('candidate-slots-1',1,True,None),
            ('candidate-client-disconnect',1,True,'disconnect'),
            ('candidate-queue-deadline',1,True,'deadline'),
            ('candidate-unknown-submission',1,True,'unknown'),
        ]
    for name, concurrency, candidate, boundary in modes:
        try:
            observations.append(scenario(root/name,binary,concurrency,candidate=candidate,boundary=boundary))
        except Exception as error:
            write_json(root/'results.json',{'status':'failed','case':name,
                'error':repr(error),'observations':observations})
            raise
    write_json(root/'results.json',{'status':'passed','observations':observations})
    print('公开工具续轮与满 Gateway 槽位对照通过',flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
