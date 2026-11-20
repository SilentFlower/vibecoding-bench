"""提供隔离实验用的原生会话桥接；逐次调用从原生返回流交付数据。"""
import hashlib
import json
import os
from pathlib import Path
import queue
import re
import select
import secrets
import signal
import subprocess
import sys
import threading
import time
import uuid

ROOT = Path(__file__).parent
PARENT = ROOT
FIXTURE = ROOT/'resources'
EXPECTED_SHA = '39816d49d5ab92229952987225c23ea3fed7580699dcb4a444e0388e0ac1ce43'
from .process_memory import memory, pids_for


def verify_binary(path):
    """核对固定执行体。@param path 执行路径。@return SHA256。"""
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024*1024), b''):
            digest.update(block)
    if digest.hexdigest() != EXPECTED_SHA:
        raise ValueError('执行体身份不匹配')
    return digest.hexdigest()


class NativeBridge:
    """串行绑定作业、原生模型调用和独立返回通道。"""

    def __init__(self, folder, reclaim=False, event_sink=None):
        """配置隔离工作进程。@param folder 独立目录。@param reclaim 冷页回收开关。@param event_sink 在线事件接收器。@return 无返回值。"""
        self.runtime_env = {};self.native_home = None;self.binary = None;self.ca_file = None;self.proxy_url = '';self.startup_timeout=90;self.retire_timeout=60
        self.csrf = secrets.token_urlsafe(32)
        self.folder = Path(folder)
        self.folder.mkdir(parents=True, exist_ok=True)
        self.reclaim = reclaim
        self.backend = os.environ.get('AGY_BRIDGE_BACKEND', 'native')
        self.event_sink = event_sink
        self.proc = None
        self.native_pid = None
        self.native_ready = False
        self.active_id = None
        self.cancel_requested = False
        self.state_lock = threading.RLock()
        self.request_lock = threading.Lock()
        self.used_ids = set()
        self.native_events = []
        self.cli_events = []
        self.processes = []
        self.partial = {}
        self.log = None
        self.capture_enabled = False
        self.events = open(os.devnull, 'w')

    def _emit(self, event):
        """持续保存原型输出。@param event 完整事件。@return 无返回值。"""
        self.events.write(json.dumps(event, ensure_ascii=False)+'\n')
        self.events.flush()
        if self.event_sink:
            self.event_sink(event)

    def _start(self):
        """惰性启动新代次并核对观察器准入。@return 无返回值。"""
        if self.proc and self.proc.poll() is None:
            return
        self.generation = str(uuid.uuid4())
        self.run_folder = self.folder/self.generation
        self.run_folder.mkdir()
        home = self.native_home if self.native_home is not None else self.folder/'home'
        home.mkdir(exist_ok=True)
        binary = self.binary
        if binary is None:raise ValueError('缺少已经解码核验的执行体')
        verify_binary(binary)
        self.input_fifo = self.run_folder/'input.pipe'
        os.mkfifo(self.input_fifo)
        self.pending = queue.Queue()
        event_r, event_w = os.pipe()
        self.event_r = event_r
        env = {'PATH': '/usr/bin:/bin', 'HOME': str(home), 'USER': 'agy-study', 'LANG': 'C.UTF-8', 'TERM': 'dumb',
               'XDG_CONFIG_HOME': str(home/'.config'), 'XDG_CACHE_HOME': str(home/'.cache'),
               'XDG_DATA_HOME': str(home/'.local/share'),
               'AGY_CLI_DISABLE_AUTO_UPDATE': 'true', 'NO_PROXY': '127.0.0.1,localhost',
               'AGY_BRIDGE_FOLDER': str(self.run_folder), 'AGY_BRIDGE_PROFILE': str(ROOT/'resources/admission.json'),
               'AGY_BRIDGE_TYPES': str(ROOT/'resources/admission.json'), 'AGY_BRIDGE_BINARY': str(binary),
               'AGY_BRIDGE_GENERATION': self.generation, 'AGY_BRIDGE_EVENT_FD': str(event_w)}
        env.update(self.runtime_env)
        if getattr(self, 'capture_tls', False):
            env['AGY_BRIDGE_CAPTURE_TLS'] = '1'
        if self.ca_file:
            env['SSL_CERT_FILE'] = str(self.ca_file)
        if self.proxy_url:
            env.update(HTTP_PROXY=self.proxy_url, HTTPS_PROXY=self.proxy_url, ALL_PROXY=self.proxy_url)
        env['ANTIGRAVITY_SERVER_CSRF_TOKEN'] = self.csrf
        env['ANTIGRAVITY_EXTENSION_SERVER_CSRF_TOKEN'] = self.csrf
        env['AGY_BRIDGE_STDIN'] = str(self.input_fifo)
        if self.reclaim:
            env.update(LD_PRELOAD=str(ROOT/'resources/relocation_reclaim.so'), AGY_STUDY_FADVISE='1',AGY_RECLAIM_BINARY=str(binary))
        args = [str(ROOT/'resources/observer-c'),str(binary),'--input-format','stream-json','--output-format','stream-json']
        try:
            self.proc = subprocess.Popen(args,
                                         env=env, cwd=self.run_folder, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                         stderr=subprocess.STDOUT, pass_fds=(event_w,), start_new_session=True)
        except Exception:
            os.close(event_r)
            self.input_fifo.unlink(missing_ok=True)
            raise
        finally:
            os.close(event_w)
        os.set_blocking(event_r, False)
        os.set_blocking(self.proc.stdout.fileno(), False)
        self.partial = {event_r: b'', self.proc.stdout.fileno(): b''}
        self.log = (self.run_folder/'stdout.txt').open('wb') if self.capture_enabled else open(os.devnull, 'wb')
        self.native_pid = None
        self.native_ready = False
        self.current_process = {'generation': self.generation, 'observer_pid': self.proc.pid, 'backend': self.backend,
                                'binary': str(binary), 'forced_cleanup': False}
        self.processes.append(self.current_process)
        self.feeder = threading.Thread(target=self._feed, daemon=True)
        self.feeder.start()
        deadline = time.monotonic()+self.startup_timeout
        while not self.native_ready and time.monotonic() < deadline and self.proc.poll() is None:
            self._pump()
        if not self.native_ready:
            self.close_worker()
            raise RuntimeError('原生观察器握手失败')

    def _feed(self):
        """保持原生输入直到作业队列关闭。@return 无返回值。"""
        try:
            with self.input_fifo.open('wb') as stream:
                while True:
                    text = self.pending.get()
                    if text is None:
                        break
                    stream.write((json.dumps({'event': 'user', 'message': {'content': text}}, ensure_ascii=False)+'\n').encode())
                    stream.flush()
        except (OSError, BrokenPipeError):
            pass

    def _pump(self, wait=0.05):
        """读取唯一私有通道和原版控制输出。@param wait 等待秒数。@return 无返回值。"""
        if not self.proc:
            return
        for fd in select.select(list(self.partial), [], [], wait)[0]:
            try:
                data = os.read(fd, 1024*1024)
            except BlockingIOError:
                continue
            if fd != self.event_r:
                self.log.write(data)
                self.log.flush()
            self.partial[fd] += data
            while b'\n' in self.partial[fd]:
                line, self.partial[fd] = self.partial[fd].split(b'\n', 1)
                if fd == self.event_r:
                    event = json.loads(line)
                    if event['generation'] != self.generation:
                        raise RuntimeError('观察器代次不匹配')
                    if event['event'] == 'model_tls_write':
                        # 头部可能含凭据，仅交给当前作业的脱敏路径。
                        self._emit(event)
                        continue
                    if event['event'] == 'observer_ready':
                        if event['source_sha256'] != EXPECTED_SHA:
                            raise RuntimeError('观察器执行体身份不匹配')
                        self.native_pid = event['native_pid']
                        self.current_process['native_pid'] = self.native_pid
                    if event['event'] == 'native_ready':
                        self.native_ready = True
                    self.native_events.append(event)
                    self._emit(event)
                elif line.startswith(b'{"event":'):
                    self.cli_events.append(json.loads(line))

    def cancel(self, request_id):
        """只取消匹配的活动作业。@param request_id 作业标识。@return 是否接受取消。"""
        with self.state_lock:
            if request_id != self.active_id or self.native_pid is None:
                return False
            self.cancel_requested = True
            try:
                os.kill(self.native_pid, signal.SIGINT)
            except ProcessLookupError:
                pass
            return True

    def snapshot(self):
        """分别采集原生进程、观察器和控制进程内存。@return 分项smaps_rollup。"""
        native = memory(self.native_pid) if self.native_pid else None
        observer = memory(self.proc.pid) if self.proc else None
        helpers = [item for pid in (pids_for(self.native_pid) if self.native_pid else [])
                   if pid != self.native_pid and (item := memory(pid))]
        return {'native': native, 'observer': observer, 'backend': self.backend,
                'controller': memory(os.getpid()), 'native_helpers': helpers}

    def request(self, request_id, prompt, cancel_after_chunks=None):
        """运行原生CLI提示词作业并从实际返回流交付结果。@param request_id 独立标识。@param prompt 原生提示词。@param cancel_after_chunks 测试取消位置。@return 桥接结果及原生对照。"""
        if not self.request_lock.acquire(blocking=False):
            raise RuntimeError('工作进程已有活动作业')
        try:
            return self._request(request_id, prompt, cancel_after_chunks)
        finally:
            self.request_lock.release()

    def _request(self, request_id, prompt, cancel_after_chunks):
        """执行已经取得串行所有权的作业。@param request_id 标识。@param prompt 提示词。@param cancel_after_chunks 测试取消位置。@return 作业结果。"""
        if not isinstance(request_id, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,96}', request_id) or request_id in self.used_ids:
            raise ValueError('请求标识无效或重复')
        if not isinstance(prompt, str):
            raise ValueError('原型只接纳原生CLI文本提示词')
        if self.active_id is not None:
            raise RuntimeError('工作进程已有活动作业')
        self.used_ids.add(request_id)
        self._start()
        with self.state_lock:
            self.active_id = request_id
            self.cancel_requested = False
        before_native = len(self.native_events)
        before_cli = len(self.cli_events)
        path = self.run_folder/'active.json'
        temporary = self.run_folder/'active.tmp'
        temporary.write_text(json.dumps({'request_id': request_id}))
        temporary.replace(path)
        self._emit({'event': 'request_start', 'request_id': request_id, 'generation': self.generation})
        self.pending.put(prompt)
        calls = {}
        cli_result = None
        index = before_native
        cancel_sent = False
        deadline = time.monotonic()+25
        failure = None
        started = time.monotonic()
        while time.monotonic() < deadline:
            self._pump()
            for event in self.native_events[index:]:
                if event['event'] == 'observer_error':
                    failure = event['error']
                    self.cancel(request_id)
                if event['event'] not in ['model_start', 'response_chunk', 'model_end']:
                    continue
                if event['request_id'] != request_id:
                    failure = '原生事件跨作业归属'
                    self.cancel(request_id)
                    continue
                key = event['call_id']
                if event['event'] == 'model_start':
                    if key in calls:
                        raise RuntimeError('原生调用重复开始')
                    calls[key] = {'call_id': key, 'native_context': event['native_context'], 'chunks': [], 'ended': False}
                elif key not in calls or calls[key]['ended']:
                    failure = '原生流顺序无效'
                    self.cancel(request_id)
                elif event['event'] == 'response_chunk':
                    calls[key]['chunks'].append(event['chunk'])
                else:
                    calls[key].update(ended=True, native_error_present=event['native_error_present'])
            index = len(self.native_events)
            terminals = [event['result'] for event in self.cli_events[before_cli:] if event['event'] == 'result']
            if terminals:
                cli_result = terminals[0]
            chunks = sum(len(call['chunks']) for call in calls.values())
            if cancel_after_chunks is not None and chunks >= cancel_after_chunks and not cancel_sent:
                cancel_sent = True
                self.cancel(request_id)
            if self.cancel_requested:
                if self.proc.poll() is not None or (cli_result and cli_result.get('status') == 'ERROR'):
                    break
            elif cli_result and ((calls and all(call['ended'] for call in calls.values())) or cli_result['status'] == 'ERROR'):
                break
            if self.proc.poll() is not None:
                break
        else:
            failure = '隔离实验等待超时'
            self.cancel(request_id)
        # CLI终态只用于等待原生会话收口；正文始终来自带归属的原生流。
        text = ''.join(chunk.get('DeltaText', '') for call in calls.values() for chunk in call['chunks'])
        with self.state_lock:
            cancelled = self.cancel_requested
            last_call = list(calls.values())[-1] if calls else None
            status = 'error' if failure else ('cancelled' if cancelled else ('error' if not cli_result or cli_result['status'] != 'SUCCESS' or
                      (last_call and last_call.get('native_error_present')) else 'success'))
            # 先撤销活动归属，再公开终态，避免迟到取消击中后续作业。
            self.active_id = None
        result = {'request_id': request_id, 'generation': self.generation, 'status': status, 'text': text,
                  'model_calls': list(calls.values()), 'cli_result': cli_result, 'failure': failure,
                  'elapsed_seconds': time.monotonic()-started, 'memory': self.snapshot(),
                  'input_contract': 'native_cli_prompt', 'tool_execution': 'native_harness'}
        self._emit({'event': 'request_end', 'request_id': request_id, 'generation': self.generation, 'status': status})
        if status != 'success':
            self.close_worker()
        (self.folder/(request_id+'.json')).write_text(json.dumps(result, ensure_ascii=False, indent=2))
        return result

    def close_worker(self):
        """关闭输入并等待原生遥测和进程退出。@return 当前代次退出记录。"""
        if self.proc is None:
            return None
        # 原生按周期发送批次；正常关闭先给其排队上报留出实验宽限。
        # 宽限用于工作进程退出，业务数据已通过独立管道交付。
        drain_start = time.monotonic()
        deadline = drain_start
        if not self.cancel_requested:
            while self.proc.poll() is None and time.monotonic() < deadline:
                self._pump()
        self.current_process['telemetry_grace_seconds'] = time.monotonic()-drain_start
        self.pending.put(None)
        deadline = time.monotonic()+self.retire_timeout
        while self.proc.poll() is None and time.monotonic() < deadline:
            self._pump()
        if self.proc.poll() is None:
            self.current_process['forced_cleanup'] = True
            os.killpg(self.proc.pid, signal.SIGTERM)
            try:
                self.proc.wait(timeout=1)
            except subprocess.TimeoutExpired:
                os.killpg(self.proc.pid, signal.SIGKILL)
                self.proc.wait()
        self._pump(0)
        self.current_process['observer_exit_code'] = self.proc.returncode
        self.log.close()
        os.close(self.event_r)
        (self.folder/'processes.json').write_text(json.dumps(self.processes, ensure_ascii=False, indent=2))
        self.proc = None
        self.native_pid = None
        return self.current_process

    def close(self):
        """结束桥接并收口事件文件。@return 无返回值。"""
        self.close_worker()
        self.events.close()
