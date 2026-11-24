#!/usr/bin/env python3
"""用官方交互 CLI 和回环模型验收账号级进程满载、续用与释放。"""

import argparse
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
from dataclasses import asdict
import errno
from fcntl import ioctl
from gzip import decompress
from hashlib import file_digest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
from select import select
from socket import MSG_PEEK
from struct import pack
from subprocess import Popen, TimeoutExpired, check_output, run
import shlex
import shutil
import sys
from tempfile import mkdtemp
from termios import TIOCSWINSZ
from threading import Event, Lock, Thread
from time import monotonic, monotonic_ns, sleep
from urllib.parse import urlsplit
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[2]
VERSION = '2.1.293'
DEFAULT_MODEL = 'claude-sonnet-4-6'
FIRST = 'Please describe this isolated verification.'
NEXT = 'Please continue in the same session.'
CLEAN_ENV = {'PATH': '/usr/sbin:/usr/bin:/sbin:/bin', 'LANG': 'C.UTF-8', 'TERM': 'xterm-256color'}
MIB = 1024 ** 2
WAIT_SECONDS = 45


def write_json(path, value):
    """写入可复核的收口文件。@param path 证据路径。@param value 数据。@return 无。"""
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


def record(path, event, **values):
    """记录同一内核单调时钟的阶段。@param path 日志路径。@param event 事件。@param values 字段。@return 无。"""
    row = json.dumps({'ns': monotonic_ns(), 'event': event, **values}, ensure_ascii=False)
    with path.open('ab', buffering=0) as log:
        log.write((row + '\n').encode())


def wait_for(read, description, timeout=12):
    """等待真实条件。@param read 条件读取。@param description 超时说明。@param timeout 秒。@return 条件值。"""
    deadline = monotonic() + timeout
    while monotonic() < deadline:
        value = read()
        if value:
            return value
        sleep(0.02)
    raise TimeoutError(description)


def record_stop():
    """官方 Stop Hook，只写同一会话的完成信号。@return 无。"""
    payload = json.load(sys.stdin)
    if payload['hook_event_name'] != 'Stop' or payload['session_id'] != os.environ['LAB_SESSION_ID']:
        raise ValueError('Stop 与本次隔离会话不匹配')
    record(Path(os.environ['LAB_STOP_FILE']), 'tui_stop', session_id=payload['session_id'])


def frame(event):
    """编码单个 Messages SSE。@param event 事件。@return UTF-8 帧。"""
    return ('event: ' + event['type'] + '\ndata: ' + json.dumps(event, ensure_ascii=False) + '\n\n').encode()


class LoopbackModel(ThreadingHTTPServer):
    """回环模型，每个业务轮都有独立的暂停门。"""

    def __init__(self, output, token, sessions):
        """冻结实验会话。@param output 证据目录。@param token 合成凭据。@param sessions ID 映射。@return 无。"""
        super().__init__(('127.0.0.1', 0), ModelHandler)
        self.output = output
        self.token = token
        self.sessions = sessions
        self.lock = Lock()
        self.started = {}
        self.active = {}
        self.errors = []
        self.gates = {(label, turn): Event() for label in sessions.values() for turn in (1, 2)}

    def snapshot(self):
        """读取已开始和仍在途的轮。@return 两组不可变键集合。"""
        with self.lock:
            return set(self.started), set(self.active)


class ModelHandler(BaseHTTPRequestHandler):
    """从真实 TUI 接收 Messages 并在首段后保持原 HTTP 请求在途。"""

    protocol_version = 'HTTP/1.1'

    def log_message(self, *_):
        """以结构化事件替代 HTTP 日志。@return 无。"""

    def do_POST(self):
        """检查账号实验的公开请求结构并执行回环响应。@return 无。"""
        model = self.server
        try:
            if self.headers.get('Authorization') != 'Bearer ' + model.token:
                self.send_error(401)
                return
            code_session = self.headers.get('x-claude-code-session-id')
            label = model.sessions[code_session]
            raw = self.rfile.read(int(self.headers['Content-Length']))
            request = json.loads(decompress(raw) if self.headers.get('Content-Encoding') == 'gzip' else raw)
            if urlsplit(self.path).path != '/v1/messages' or request['stream'] is not True:
                raise ValueError('夹具仅接受流式 Messages')
            messages = request['messages']
            latest = messages[-1]
            texts = self._texts(latest)
            if latest['role'] != 'user':
                raise ValueError('缺少最新用户消息')
            if FIRST in texts:
                turn = 1
            elif NEXT in texts and label == 'b':
                if not any(FIRST in self._texts(message) for message in messages[:-1]):
                    raise ValueError('同会话的续轮缺少真实历史')
                turn = 2
            else:
                raise ValueError('收到未登记的模型请求')
            key = (label, turn)
            with model.lock:
                if key in model.started:
                    raise ValueError('同一模型轮重复请求')
                model.started[key] = code_session
            record(model.output/'events.jsonl', 'model_post', label=label, turn=turn, session_id=code_session,
                   user_agent=self.headers.get('User-Agent'))
            self._serve_turn(key, request['model'])
        except (KeyError, OSError, ValueError, TimeoutError) as error:
            with model.lock:
                model.errors.append(str(error))
            record(model.output/'events.jsonl', 'fixture_error', reason=str(error))
            if not getattr(self, 'stream_started', False):
                self.send_error(400)

    @staticmethod
    def _texts(message):
        content = message['content']
        return [content] if isinstance(content, str) else [
            part['text'] for part in content if part['type'] == 'text']

    def _serve_turn(self, key, model_name):
        label, turn = key
        model = self.server
        def delta(text):
            return {'type': 'content_block_delta', 'index': 0, 'delta': {'type': 'text_delta', 'text': text}}

        frames = [
            {'type': 'message_start', 'message': {
                'id': 'msg_' + uuid4().hex, 'type': 'message', 'role': 'assistant', 'model': model_name,
                'content': [], 'stop_reason': None, 'stop_sequence': None,
                'usage': {'input_tokens': 12, 'output_tokens': 1}}},
            {'type': 'content_block_start', 'index': 0, 'content_block': {'type': 'text', 'text': ''}},
            delta('隔离验收首段。'), delta('该轮已由验证器放行。'),
            {'type': 'content_block_stop', 'index': 0},
            {'type': 'message_delta', 'delta': {'stop_reason': 'end_turn', 'stop_sequence': None},
             'usage': {'output_tokens': 10}},
            {'type': 'message_stop'},
        ]
        encoded = list(map(frame, frames))
        self.send_response(200)
        self.send_header('Content-Type', 'text/event-stream')
        self.send_header('Content-Length', str(sum(map(len, encoded))))
        self.send_header('Connection', 'close')
        self.end_headers()
        self.stream_started = True
        self.close_connection = True
        try:
            self.wfile.write(b''.join(encoded[:3]))
            self.wfile.flush()
            with model.lock:
                model.active[key] = True
            record(model.output/'events.jsonl', 'source_held', label=label, turn=turn)
            deadline = monotonic() + WAIT_SECONDS
            while not model.gates[key].is_set():
                if monotonic() >= deadline:
                    raise TimeoutError('真实模型连接未收口')
                if select([self.connection], [], [], 0.05)[0]:
                    try:
                        closed = self.connection.recv(1, MSG_PEEK) == b''
                    except ConnectionResetError:
                        closed = True
                    if closed:
                        record(model.output/'events.jsonl', 'source_peer_closed', label=label, turn=turn)
                        return
                    raise ValueError('回环连接出现未预期的入站数据')
            self.wfile.write(b''.join(encoded[3:]))
            self.wfile.flush()
            record(model.output/'events.jsonl', 'source_finished', label=label, turn=turn)
        except (BrokenPipeError, ConnectionResetError):
            record(model.output/'events.jsonl', 'source_peer_closed', label=label, turn=turn)
        finally:
            with model.lock:
                model.active.pop(key, None)


class Terminal:
    """以普通 PTY 驱动官方进程，名额仍由真正的执行器管理。"""

    def __init__(self, binary, folder, session_id, base_url, token, setsid, *, tools='', extra_args=(), hooks=None):
        """建隔离 HOME 和官方 Popen。@param binary 官方程序。@param folder 私有目录。@param session_id 会话。
        @param base_url 回环端点。@param token 合成凭据。@param setsid PTY 工具。
        @param tools 可用内置工具。@param extra_args 公开 CLI 参数。@param hooks 公开 hook 设置。@return 无。
        """
        self.stop_file = folder/'stop.jsonl'
        self.stopped = Event()
        self.ready = Event()
        folder.mkdir(mode=0o700)
        home, workspace = folder/'home', folder/'work'
        config = home/'.claude'
        config.mkdir(parents=True)
        workspace.mkdir()
        # 使用官方已经写出的最小引导字段，仅信任此次新建的空工作目录。
        write_json(config/'.claude.json', {
            'hasCompletedOnboarding': True, 'lastOnboardingVersion': VERSION,
            'projects': {str(workspace): {'hasTrustDialogAccepted': True}}})
        hook = shlex.join([sys.executable, str(Path(__file__).resolve()), '--record-stop'])
        settings = folder/'settings.json'
        write_json(settings, {'hooks': {'Stop': [{'hooks': [{'type': 'command', 'command': hook}]}], **(hooks or {})}})
        environment = {
            **CLEAN_ENV, 'HOME': str(home), 'CLAUDE_CONFIG_DIR': str(config),
            'ANTHROPIC_BASE_URL': base_url, 'ANTHROPIC_AUTH_TOKEN': token,
            'CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC': '1', 'DISABLE_AUTOUPDATER': '1',
            'CLAUDE_CODE_DISABLE_AUTO_MEMORY': '1', 'CLAUDE_CODE_ENABLE_PROMPT_SUGGESTION': '0',
            'SHELL': '/bin/bash', 'LAB_SESSION_ID': session_id, 'LAB_STOP_FILE': str(self.stop_file),
        }
        self.master, slave = os.openpty()
        try:
            ioctl(slave, TIOCSWINSZ, pack('HHHH', 35, 110, 0, 0))
            self.process = Popen(
                [setsid, '--ctty', str(binary), '--model', DEFAULT_MODEL, '--session-id', session_id,
                 '--name', 'Local capacity verification', '--strict-mcp-config', '--tools', tools,
                 '--settings', str(settings), '--debug-file', str(folder/'cli-debug.log'), *extra_args],
                stdin=slave, stdout=slave, stderr=slave, cwd=workspace, env=environment, close_fds=True,
            )
        except BaseException:
            os.close(self.master)
            raise
        finally:
            os.close(slave)
        self.reader = Thread(target=self._drain, args=(folder/'terminal.raw',), daemon=True)
        self.reader.start()

    def _drain(self, path):
        suffix = b''
        with path.open('wb') as output:
            while not self.stopped.is_set():
                if not select([self.master], [], [], 0.1)[0]:
                    continue
                try:
                    data = os.read(self.master, 65536)
                except OSError as error:
                    if error.errno != errno.EIO:
                        raise
                    return
                if not data:
                    return
                output.write(data)
                output.flush()
                current = suffix + data
                if '❯'.encode() in current:
                    self.ready.set()
                suffix = current[-4:]

    def submit(self, prompt):
        """在已就绪的真实 PTY 输入普通文本。@param prompt 原始提示。@return 无。"""
        if not self.ready.wait(10) or self.process.poll() is not None:
            raise RuntimeError('官方交互提示符未就绪')
        content = prompt.encode()
        os.write(self.master, b'\x1b[200~' + content + b'\x1b[201~' if b'\n' in content else content)
        sleep(0.18)
        os.write(self.master, b'\r')

    def completed(self):
        """从官方 Stop 信号读取真实完成次数。@return 次数。"""
        return len(self.stop_file.read_text().splitlines()) if self.stop_file.is_file() else 0

    def cleanup(self):
        """回收验证器自己创建的异常残留。@return 无。"""
        if self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=3)
            except TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=3)
        self.stopped.set()
        self.reader.join(timeout=1)
        os.close(self.master)


def memory_sample(processes):
    """对照进程树 PSS 和当前 cgroup。@param processes 真实 Popen 映射。@return 观察样本。"""
    from agy_runtime.process_memory import cgroup_memory, memory, pids_for

    group = next(
        (line.split(':', 2)[2] for line in Path('/proc/self/cgroup').read_text().splitlines()
         if line.startswith('0::')), None)
    fallback = Path('/sys/fs/cgroup')
    scope = fallback / group.lstrip('/') if group is not None else fallback
    cgroup = cgroup_memory(scope)
    if group is not None and scope != fallback and cgroup['source'] == 'unknown':
        # 部分容器把自己的 cgroup 挂载为可见根。
        cgroup = cgroup_memory(fallback)
        scope = fallback
    trees = {}
    for name, process in processes.items():
        observed = [memory(pid) for pid in pids_for(process.pid)]
        pss_values = [value['Pss'] for value in observed if value is not None and 'Pss' in value]
        trees[name] = {'pid': process.pid, 'pss_kib': sum(pss_values) if pss_values else None,
                       'complete': len(pss_values) == len(observed), 'processes': observed}
    return {'trees': trees, 'cgroup': {'membership': group, 'read_path': str(scope),
            'scope': 'shared_existing_cgroup', **cgroup}}


def experiment(binary, output, setsid):
    """用真实执行器验证满载、同会话续用和释放。@param binary 版本固定。@param output 证据目录。@param setsid PTY 工具。@return 结果。"""
    from tui_capacity import TuiCapacity, TuiCapacitySnapshot
    from tui_process import TuiProcessExecutor

    labels = {label: str(uuid4()) for label in 'abcd'}
    names = {session: label for label, session in labels.items()}
    token = 'fixture-' + uuid4().hex
    output_log = output/'events.jsonl'
    budget = {'configured_concurrency': 5, 'budget_bytes': 1024*MIB, 'fixed_reserve_bytes': 256*MIB,
              'per_process_reserve_bytes': 256*MIB, 'max_waiters': 1}
    capacity = TuiCapacity(**budget)
    assert capacity.snapshot() == TuiCapacitySnapshot(3, 0, 0)
    memory = {'baseline': memory_sample({})}
    terminals = {}
    spawned = {}
    launch_lock = Lock()

    with ExitStack() as stack:
        model = stack.enter_context(LoopbackModel(output, token, names))
        server = Thread(target=model.serve_forever, daemon=True)
        server.start()
        stack.callback(model.shutdown)
        url = f'http://127.0.0.1:{model.server_port}'

        def spawn(session_id):
            """返回真实官方 Popen，给启动一刻的旧存量留证。"""
            label = names[session_id]
            with launch_lock:
                assert label not in terminals
                older = {name: tui.process.poll() for name, tui in terminals.items()}
                record(output_log, 'spawn_enter', label=label, prior_exit_codes=older)
                assert sum(code is None for code in older.values()) < 3
                if label == 'd':
                    assert older['a'] is not None
                tui = Terminal(binary, output/label, session_id, url, token, setsid)
                terminals[label] = tui
                spawned[label] = tui.process.pid
                record(output_log, 'spawn_popen', label=label, pid=tui.process.pid)
                return tui.process

        executor = TuiProcessExecutor(capacity, spawn)
        handles = {}
        pool = ThreadPoolExecutor(max_workers=1)
        fourth = None
        try:
            for label in 'abc':
                handles[label] = executor.start(labels[label], timeout=8)
            for label in 'abc':
                terminals[label].submit(FIRST)
            expected_first = {(label, 1) for label in 'abc'}
            wait_for(lambda: model.snapshot()[1] == expected_first, '三个真实模型请求没有同时在途')
            for label in 'abc':
                assert Path(f'/proc/{spawned[label]}/exe').resolve() == binary
            record(output_log, 'three_held', active=sorted(expected_first), capacity=asdict(capacity.snapshot()))
            memory['three_held'] = memory_sample({label: terminals[label].process for label in 'abc'})

            fourth = pool.submit(executor.start, labels['d'], timeout=20)
            wait_for(lambda: capacity.snapshot().waiting == 1, '第四个启动没有进入真实等待队列')
            assert capacity.snapshot() == TuiCapacitySnapshot(3, 3, 1)
            assert 'd' not in terminals and not fourth.done()
            assert model.snapshot() == (expected_first, expected_first)
            record(output_log, 'fourth_queued', pids=dict(spawned), capacity=asdict(capacity.snapshot()))

            original = terminals['b'].process
            resumed = executor.resume(labels['b'], handles['b'])
            assert resumed is original and resumed.poll() is None
            assert capacity.snapshot() == TuiCapacitySnapshot(3, 3, 1)
            record(output_log, 'same_popen_resumed', label='b', pid=resumed.pid, capacity=asdict(capacity.snapshot()))
            model.gates['b', 1].set()
            wait_for(lambda: terminals['b'].completed() == 1, '同会话首轮没有触发官方 Stop')
            terminals['b'].submit(NEXT)
            expected_next = {('a', 1), ('b', 2), ('c', 1)}
            wait_for(lambda: model.snapshot()[1] == expected_next, '同 Popen 的真实续轮未到达模型')
            assert executor.resume(labels['b'], handles['b']) is original
            assert capacity.snapshot() == TuiCapacitySnapshot(3, 3, 1)
            assert 'd' not in terminals and not fourth.done()
            record(output_log, 'continuation_while_queued', label='b', pid=original.pid,
                   active=sorted(expected_next), capacity=asdict(capacity.snapshot()))

            record(output_log, 'close_requested', label='a', pid=spawned['a'])
            executor.close(handles['a'])
            assert terminals['a'].process.poll() is not None
            record(output_log, 'close_confirmed', label='a', pid=spawned['a'],
                   exit_code=terminals['a'].process.returncode)
            handles['d'] = fourth.result(timeout=10)
            assert capacity.snapshot() == TuiCapacitySnapshot(3, 3, 0)
            terminals['d'].submit(FIRST)
            expected_replaced = {('b', 2), ('c', 1), ('d', 1)}
            wait_for(lambda: model.snapshot()[1] == expected_replaced, '替换后的三个真实模型请求没有同时在途')
            assert Path(f'/proc/{spawned["d"]}/exe').resolve() == binary
            record(output_log, 'fourth_held_after_close', active=sorted(expected_replaced),
                   pids=dict(spawned), capacity=asdict(capacity.snapshot()))
            memory['after_replacement'] = memory_sample({label: terminals[label].process for label in 'bcd'})

            for label in 'bcd':
                executor.close(handles[label])
                assert terminals[label].process.poll() is not None
            wait_for(lambda: not model.snapshot()[1], '退出后模型连接没有回收')
            assert capacity.snapshot() == TuiCapacitySnapshot(3, 0, 0)
            assert model.snapshot()[0] == {('a', 1), ('b', 1), ('b', 2), ('c', 1), ('d', 1)}
            assert len(set(spawned.values())) == 4 and not model.errors, model.errors
            memory['after_close'] = memory_sample({})
            record(output_log, 'all_closed', capacity=asdict(capacity.snapshot()),
                   exit_codes={label: tui.process.returncode for label, tui in terminals.items()})
            return {'status': 'passed', 'budget': budget, 'effective_limit': 3, 'pids': dict(spawned),
                    'resumed_session': labels['b'], 'resumed_pid': original.pid, 'model_requests': 5,
                    'final_capacity': asdict(capacity.snapshot()), 'memory_observation': memory}
        finally:
            try:
                # 异常时仍先让真正的执行器关闭已登记的进程。
                for label, handle in list(handles.items()):
                    if terminals[label].process.poll() is None:
                        executor.close(handle)
                if fourth is not None:
                    if not fourth.cancel() and 'd' not in handles:
                        try:
                            handle = fourth.result(timeout=10)
                        except Exception:
                            pass  # 主流程保留队列或启动失败；此处只清理已取得的句柄。
                        else:
                            executor.close(handle)
            finally:
                pool.shutdown(wait=True, cancel_futures=True)
                for tui in terminals.values():
                    tui.cleanup()


def main():
    """隔离网络后执行真实进程验收并保留证据。@return 进程退出码。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--claude', default=shutil.which('claude'), help='官方 2.1.293 可执行文件')
    parser.add_argument('--isolated', action='store_true', help=argparse.SUPPRESS)
    parser.add_argument('--record-stop', action='store_true', help=argparse.SUPPRESS)
    options = parser.parse_args()
    if options.record_stop:
        record_stop()
        return 0
    if not options.claude:
        parser.error('请通过 --claude 传入官方 2.1.293 可执行文件')
    binary = Path(options.claude).resolve(strict=True)
    if not options.isolated:
        command = [sys.executable, str(Path(__file__).resolve()), '--isolated', '--claude', str(binary)]
        return run(['unshare', '--net', '--', '/bin/bash', '-c', 'ip link set lo up && exec "$@"',
                    'tui-concurrency', *command], env=CLEAN_ENV, check=False).returncode
    links = json.loads(check_output(['ip', '-j', 'link', 'show']))
    if not (len(links) == 1 and links[0]['ifname'] == 'lo' and 'UP' in links[0]['flags']
            and not json.loads(check_output(['ip', '-j', 'route', 'show']))):
        raise SystemExit('验收必须运行在独立的仅回环网络命名空间')
    setsid = shutil.which('setsid')
    if setsid is None:
        raise SystemExit('缺少 setsid')
    output = Path(mkdtemp(prefix='flower2api-tui-concurrency-'))
    print('证据目录', output, flush=True)
    version = check_output([str(binary), '--version'], env={**CLEAN_ENV, 'HOME': str(output)}).decode().strip()
    if version != f'{VERSION} (Claude Code)':
        raise SystemExit(f'需要官方 {VERSION}，实际为 {version}')
    with binary.open('rb') as executable:
        write_json(output/'environment.json', {'version': version, 'sha256': file_digest(executable, 'sha256').hexdigest(),
                   'network': ['lo'], 'binary': str(binary)})
    sys.path.insert(0, str(ROOT/'services/orchestrator'))
    try:
        results = experiment(binary, output, setsid)
    except Exception as error:
        write_json(output/'results.json', {'status': 'failed', 'error': str(error)})
        raise
    write_json(output/'results.json', results)
    print('满载、续用和退出验收通过', flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
