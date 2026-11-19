"""账号发送器内的AGY进程监督，跨HTTP工具收尾与凭据换代共享同一所有者。"""
import argparse
import base64
import copy
import hashlib
import json
import os
import queue
import shutil
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path

from runtime_files import atomic_json

from .contract import InputError
from .credentials import publish_access_document, read_private
from .gemini_contract import continuation_results
from .image_pool import Broker, ImagePool
from .models import native_identifier
from .process_memory import cgroup_memory, memory
from .storage import Output, private_dir, verify_resources
from .system_prompt import decode_policy, default_policy


def deadline(value: int) -> float:
    """把私有墙钟截止冻结为本次单调截止。@param value UTC毫秒。@return 单调截止。"""
    remaining = value / 1000 - time.time() if type(value) is int else -1
    if not 0 < remaining <= 125:
        raise InputError('invalid_request_deadline')
    return time.monotonic() + min(120, remaining)


def validate_submission(value: dict, config: dict) -> dict:
    """核对受信账号、调用方和凭据快照。@param value 私有输入。@param config 冻结配置。@return 独立请求副本。"""
    expected = {'schema_version', 'type', 'request_id', 'account_id', 'environment_id',
        'environment_generation', 'api_token_id', 'credential_snapshot', 'model', 'native_model',
        'body', 'deadline_unix_ms'}
    if not isinstance(value, dict) or set(value)-{'capture_enabled','system_prompt_policy'} != expected or type(value['schema_version']) is not int or value['schema_version'] != 1 or value['type'] not in ['submit', 'prepare']:
        raise InputError('invalid_submission')
    for key in ['account_id', 'environment_id', 'environment_generation']:
        if type(value[key]) is not type(config[key]) or value[key] != config[key]:
            raise InputError('submission_binding_mismatch')
    if type(value['api_token_id']) is not int or value['api_token_id'] < 1:
        raise InputError('invalid_caller_identity')
    if not isinstance(value['request_id'], str) or len(value['request_id']) > 128:
        raise InputError('invalid_request_id')
    try:
        uuid.UUID(value['request_id'])
    except (ValueError, AttributeError):
        raise InputError('invalid_request_id') from None
    snapshot = value['credential_snapshot']
    if not isinstance(snapshot, dict) or set(snapshot) != {'account_id','credential_generation','access_token','expires_at','email'} or type(snapshot.get('account_id')) is not int or snapshot.get('account_id') != config['account_id'] or type(snapshot.get('credential_generation')) is not int or snapshot['credential_generation'] < 1:
        raise InputError('credential_binding_mismatch')
    access = snapshot['access_token']
    if not isinstance(access,str) or not 1<=len(access)<=16384 or any(ord(c)<=32 or ord(c)>=127 for c in access) or type(snapshot['expires_at']) is not int or snapshot['expires_at']<=time.time()*1000 or not isinstance(snapshot['email'],str):
        raise InputError('invalid_access_snapshot')
    if not isinstance(value['model'], str) or not native_identifier(value['native_model']) or not isinstance(value['body'], dict):
        raise InputError('invalid_model_or_body')
    if type(value.get('capture_enabled',False)) is not bool:
        raise InputError('invalid_capture_policy')
    deadline(value['deadline_unix_ms'])
    result=copy.deepcopy(value)
    result.setdefault('capture_enabled',False)
    result['system_prompt_policy']=decode_policy(value.get('system_prompt_policy',default_policy()))
    return result


class Worker:
    """持有一个账号、模型和凭据代次的真实原生子进程。"""

    def __init__(self, owner, value):
        """冻结进程身份及独立HOME。@param owner 账号监督器。@param value 已核验提交。@return 无。"""
        self.owner = owner
        self.key = owner.worker_key(value)
        # 管理采集只发布有界脱敏快照；完整原生调试材料使用原作业临时目录。
        base=owner.root/'workers'
        if base is None:
            raise InputError('capture_storage_unavailable')
        self.folder = private_dir(base / uuid.uuid4().hex)
        self.home = private_dir(self.folder / 'home')
        publish_access_document(self.home, value['credential_snapshot'])
        self.config = dict(home=str(self.home), account_id=value['account_id'],
            credential_generation=value['credential_snapshot']['credential_generation'],
            public_model=value['model'], native_model=value['native_model'],
            binary_path=owner.config['binary_path'], proxy_url=owner.config['proxy_url'],
            capture_enabled=False, startup_timeout=90,
            retire_timeout=60, cancel_timeout=10)
        atomic_json(self.folder / 'config.json', self.config)
        if value.get('capture_enabled', False):
            self.config['capture_root']=str(owner.capture_root)
            atomic_json(self.folder / 'config.json', self.config)
        self.process = None
        self.events = queue.Queue(maxsize=128)
        self.write_lock = threading.Lock()
        self.lifecycle_lock = threading.RLock()
        self.event_budget = threading.Condition()
        self.event_bytes = 0
        self.busy = True
        self.closed = False
        self.ready = None
        self.reader = None
        self.last_used = time.monotonic()

    def start(self, until):
        """在同UID隔离角色中启动并核对真实就绪。@param until 原单调截止。@return 无。"""
        # 与发送器的冻结模块路径一致，共享私有文件助手由正式镜像放在/usr/local/bin。
        environment = {'PATH': '/usr/local/bin:/usr/bin:/bin', 'PYTHONPATH': str(Path(__file__).resolve().parents[1])+':/usr/local/bin',
            'AGY_RUNTIME_IMAGE_SOCKET': str(self.owner.socket_path), 'AGY_RUNTIME_SUPERVISOR_PID':str(os.getpid()), 'TMPDIR':str(self.folder)}
        with self.lifecycle_lock:
            if self.closed or self.owner.closed:
                raise InputError('supervisor_closed')
            if time.monotonic() >= until:
                raise InputError('request_deadline_exceeded')
            self.process = subprocess.Popen([sys.executable, '-m', 'agy_runtime.kernel',
                '--config', str(self.folder / 'config.json'), '--state-dir', str(self.folder / 'state')],
                env=environment, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                start_new_session=True)
            self.reader = threading.Thread(target=self.read, daemon=True)
            self.reader.start()
        while True:
            event = self.next(until)
            if event.get('type') == 'worker_ready':
                if event.get('source_sha256') != self.owner.image_sha or type(event.get('native_pid')) is not int:
                    raise InputError('worker_identity_mismatch')
                self.ready = event
                return
            if event.get('type') in ['worker_error', 'process_closed']:
                raise InputError('worker_start_failed')

    def read(self):
        """唯一读取器持续消费原生事件，积压时关闭该进程。@return 无。"""
        try:
            while True:
                line = self.process.stdout.readline(67108865)
                if not line:
                    break
                if len(line) > 67108864:
                    raise ValueError('AGY原生协议帧超限')
                event = json.loads(line)
                if not isinstance(event, dict) or event.get('protocol') != 'agy-native-stdio' or event.get('schema_version') != 1:
                    raise ValueError('AGY原生协议身份无效')
                if not self.busy and event.get('type') == 'telemetry':
                    continue
                with self.event_budget:
                    if self.event_bytes + len(line) > 67108864:
                        raise ValueError('AGY原生事件积压超限')
                    self.event_bytes += len(line)
                self.events.put((event, len(line)), timeout=5)
        except Exception:
            if self.process.poll() is None:
                self.process.kill()
        finally:
            try:
                self.events.put(({'type': 'process_closed'}, 0), timeout=1)
            except queue.Full:
                pass

    def next(self, until):
        """读取原预算内的下一事件。@param until 单调截止。@return 原生事件。"""
        remaining = until - time.monotonic()
        if remaining <= 0:
            raise InputError('request_deadline_exceeded')
        try:
            event, size = self.events.get(timeout=remaining)
            with self.event_budget:
                self.event_bytes -= size
            return event
        except queue.Empty:
            raise InputError('request_deadline_exceeded') from None

    def send(self, value):
        """串行向唯一控制输入投递。@param value 私有版本化指令。@return 无。"""
        with self.write_lock:
            if self.closed or not self.process or self.process.poll() is not None:
                raise InputError('worker_closed')
            self.process.stdin.write((json.dumps(value, separators=(',', ':')) + '\n').encode())
            self.process.stdin.flush()

    def close(self):
        """先请求原生排空，再有界回收本进程组。@return 无。"""
        with self.lifecycle_lock:
            self._close()

    def _close(self):
        if self.closed:
            return
        try:
            if self.process and self.process.poll() is None:
                self.send({'schema_version': 1, 'type': 'shutdown'})
                self.process.wait(timeout=75)
        except Exception:
            if self.process and self.process.poll() is None:
                self.process.kill()
                self.process.wait(timeout=10)
        finally:
            self.closed = True
            if self.process:
                for stream in [self.process.stdin, self.process.stdout]:
                    if stream:
                        stream.close()
            if self.reader:
                self.reader.join(timeout=2)
            # 采集只保留业务证据，退役后始终回收访问凭据副本。
            shutil.rmtree(self.home, ignore_errors=True)
            if not self.config.get('capture_enabled', False):
                shutil.rmtree(self.folder, ignore_errors=True)
            else:
                atomic_json(self.folder/'retired.json',{'retired_at':time.time()})


class Supervisor:
    """管理同账号进程池、原工具轮和真实凭据代次。"""

    def __init__(self, config, output=None):
        """建立单账号监督器。@param config 冻结的部署配置。@param output 私有事件输出。@return 无。"""
        self.config = config
        if 'memory_mib' in config:
            memory_mib=config['memory_mib']
            actual=cgroup_memory()['max_bytes']
            if type(memory_mib) is not int or memory_mib<0 or actual!=('unlimited' if memory_mib==0 else memory_mib*1024**2):
                raise ValueError('AGY发送器实际cgroup与冻结RAM预算不一致')
        for name in ['account_id', 'environment_generation', 'max_workers']:
            if type(config.get(name)) is not int or config[name] < 1:
                raise ValueError('AGY监督器数量或归属无效')
        if not isinstance(config.get('environment_id'), str) or not config['environment_id']:
            raise ValueError('AGY监督器环境身份无效')
        self.root = private_dir(config['work_root'])
        self.capture_root=private_dir(config['capture_root']) if config.get('capture_root') else None
        if self.capture_root:
            for folder in self.capture_root.iterdir():
                marker=folder/'retired.json'
                if folder.is_dir() and not folder.is_symlink() and marker.is_file() and not marker.is_symlink():
                    retired=read_private(marker)
                    if type(retired.get('retired_at')) in (int,float) and time.time()-retired['retired_at']>7*86400:
                        shutil.rmtree(folder)
        private_dir(self.root / 'workers')
        verify_resources()
        self.condition = threading.Condition(threading.RLock())
        self.workers = []
        self.jobs = {}
        self.credential_generation=0
        self.credential_identity=None
        self.controls = {}
        self.closed = False
        self.output = output or Output()
        self.pool = ImagePool(config['binary_path'])
        self.image_sha = '39816d49d5ab92229952987225c23ea3fed7580699dcb4a444e0388e0ac1ce43'
        self.socket_path = self.root / 'image.sock'
        if self.socket_path.exists():
            raise ValueError('AGY映像端点仍被原监督器持有')
        self.broker = Broker(self.socket_path, self.pool, {os.getuid()})
        self.reaper = threading.Thread(target=self.reap_idle, daemon=True)
        self.reaper.start()

    def reap_idle(self):
        """只回收闲置五分钟的物理worker，工具等待保持原截止。@return 无。"""
        while True:
            with self.condition:
                if self.closed:
                    return
                idle=[worker for worker in self.workers if not worker.busy and time.monotonic()-worker.last_used>=300]
                for worker in idle:
                    worker.busy=True
                if not idle:
                    self.condition.wait(1)
            for worker in idle:
                worker.close()
                with self.condition:
                    if worker in self.workers:
                        self.workers.remove(worker)
                    self.condition.notify_all()

    def emit(self, kind, request_id=None, **fields):
        """输出带环境归属的唯一协议事件。@param kind 事件。@param request_id 请求。@param fields 已核验字段。@return 无。"""
        self.output.emit({'protocol': 'agy-account-supervisor', 'schema_version': 1, 'type': kind,
            'account_id': self.config['account_id'], 'environment_id': self.config['environment_id'],
            'environment_generation': self.config['environment_generation'], 'request_id': request_id, **fields})

    def worker_key(self, value):
        """冻结进程复用身份。@param value 已核验提交。@return 含代次和私有AT摘要的池键。"""
        snapshot = value['credential_snapshot']
        return (snapshot['credential_generation'], hashlib.sha256(snapshot['access_token'].encode()).digest(),
            value['model'], str(value['native_model']), self.config['proxy_url'], value.get('capture_enabled',False))

    def acquire(self, value, until):
        """在物理上限内选择或建立当前代次进程。@param value 提交。@param until 截止。@return 独占worker。"""
        key = self.worker_key(value)
        while True:
            stale = None
            with self.condition:
                if self.closed:
                    raise InputError('supervisor_closed')
                # 旧代退役也消费原请求预算，截止后禁止复用或启动下一代。
                if time.monotonic() >= until:
                    raise InputError('request_deadline_exceeded')
                for worker in self.workers:
                    if not worker.busy and not worker.closed and worker.key == key:
                        worker.busy = True
                        return worker
                stale = next((worker for worker in self.workers if not worker.busy), None)
                if stale:
                    stale.busy = True
                elif len(self.workers) < self.config['max_workers']:
                    worker = Worker(self, value)
                    self.workers.append(worker)
                    break
                else:
                    remaining = until - time.monotonic()
                    if remaining <= 0:
                        raise InputError('worker_capacity_deadline')
                    self.condition.wait(min(remaining, .25))
            if stale:
                stale.close()
                with self.condition:
                    self.workers.remove(stale)
                    self.condition.notify_all()
        try:
            worker.start(until)
            return worker
        except Exception:
            worker.close()
            with self.condition:
                self.workers.remove(worker)
                self.condition.notify_all()
            raise

    def continuation(self, value, until):
        """先完成原worker工具收尾，再允许下一次模型生成。@param value 新请求。@param until 截止。@return 无。"""
        matches = []
        matching_prefix = False
        with self.condition:
            for job in self.jobs.values():
                previous = job['value']
                if not job.get('waiting') or previous['model'] != value['model']:
                    continue
                old_contents = previous['body'].get('contents')
                new_contents = value['body'].get('contents')
                if not isinstance(old_contents,list) or not isinstance(new_contents,list) or len(new_contents)!=len(old_contents)+2 or new_contents[:len(old_contents)]!=old_contents:
                    continue
                matching_prefix = True
                if previous['api_token_id'] != value['api_token_id']:
                    continue
                try:
                    continuation_results(previous['body'], job['calls'], value['body'])
                except (InputError, KeyError, TypeError):
                    continue
                matches.append(job)
            if len(matches) > 1:
                raise InputError('ambiguous_tool_continuation')
            if not matches:
                if matching_prefix:
                    raise InputError('tool_continuation_identity')
                return
            job = matches[0]
            if job.get('claimed'):
                raise InputError('tool_continuation_already_claimed')
            job['claimed'] = True
            identity = job['identity']
            job['worker'].send({'schema_version': 1, 'type': 'finish_tool_turn', **identity, 'body': value['body']})
        if not job['finished'].wait(max(0, min(until, job['until']) - time.monotonic())) or job.get('final_status') != 'completed':
            raise InputError('previous_tool_turn_failed')

    def submit(self, raw):
        """登记唯一HTTP请求并在线程中执行。@param raw 受信提交。@return 无。"""
        value = validate_submission(raw, self.config)
        until = deadline(value['deadline_unix_ms'])
        with self.condition:
            if self.closed or value['request_id'] in self.jobs:
                raise InputError('request_already_registered')
            generation=value['credential_snapshot']['credential_generation']
            identity=hashlib.sha256(value['credential_snapshot']['access_token'].encode()).digest()
            if generation<self.credential_generation or generation==self.credential_generation and identity!=self.credential_identity:
                raise InputError('stale_credential_generation')
            self.credential_generation=generation
            self.credential_identity=identity
            self.jobs[value['request_id']] = {'value': value, 'until': until, 'finished': threading.Event(),
                'cancelled': threading.Event(), 'worker': None, 'calls': [], 'waiting': False}
        threading.Thread(target=self.execute, args=(value, until), daemon=True).start()

    def finish_tools_command(self, value):
        """只投递原工具结果，保持零模型发送和原截止。@param value 无凭据控制信封。@return 无。"""
        expected={'schema_version','type','request_id','account_id','environment_id','environment_generation','api_token_id','previous_request_id','body'}
        if set(value)!=expected or value['type']!='finish_tools' or type(value['api_token_id']) is not int or value['api_token_id']<1 or not isinstance(value['body'],dict):
            raise InputError('invalid_tool_completion')
        for key in ['account_id','environment_id','environment_generation']:
            if type(value[key]) is not type(self.config[key]) or value[key]!=self.config[key]:raise InputError('submission_binding_mismatch')
        for key in ['request_id','previous_request_id']:
            if not isinstance(value[key],str):raise InputError('invalid_request_id')
            try:uuid.UUID(value[key])
            except ValueError:raise InputError('invalid_request_id') from None
        with self.condition:
            if self.closed or value['request_id'] in self.controls:raise InputError('request_already_registered')
            done=threading.Event();self.controls[value['request_id']]=done
        threading.Thread(target=self.finish_tools, args=(copy.deepcopy(value),done),daemon=True).start()

    def finish_tools(self, value, done):
        """等待原工具轮真实收口，并保存幂等回填凭据。@param value 控制输入。@param done 控制完成通知。@return 无。"""
        try:
            digest=hashlib.sha256(json.dumps(value['body'],sort_keys=True,separators=(',',':')).encode()).hexdigest()
            with self.condition:
                job=self.jobs.get(value['previous_request_id'])
                if not job or job['value']['api_token_id']!=value['api_token_id'] or job['until']<=time.monotonic():raise InputError('tool_continuation_identity')
                if job.get('continuation_digest'):
                    if job['continuation_digest']!=digest:raise InputError('tool_completion_receipt_mismatch')
                else:
                    if not job['waiting'] or job.get('claimed'):raise InputError('tool_turn_not_waiting')
                    continuation_results(job['value']['body'],job['calls'],value['body'])
                    job['claimed']=True;job['continuation_digest']=digest
                    job['worker'].send({'schema_version':1,'type':'finish_tool_turn',**job['identity'],'body':value['body']})
            if not job['finished'].wait(max(0,job['until']-time.monotonic())) or job.get('final_status')!='completed':raise InputError('previous_tool_turn_failed')
            self.emit('tools_finished',value['request_id'],previous_request_id=value['previous_request_id'])
        except Exception as error:
            self.emit('control_error',value['request_id'],code=str(error) if isinstance(error,InputError) else 'tool_completion_failed')
        finally:
            done.set()
            with self.condition:self.controls.pop(value['request_id'],None)

    def execute(self, value, until):
        """持有进程直到真实idle，HTTP工具完成时保留原工具归属。@param value 提交。@param until 原截止。@return 无。"""
        job = self.jobs[value['request_id']]
        worker = None
        failed = False
        try:
            self.continuation(value, until)
            worker = self.acquire(value, until)
            job['worker'] = worker
            if job['cancelled'].is_set():
                raise InputError('request_cancelled')
            if value['type'] == 'prepare':
                self.emit('prepared', value['request_id'], native=worker.ready)
                return
            worker.send({'schema_version': 1, 'type': 'gemini_request', 'request_id': value['request_id'],
                'model': value['model'], 'body': value['body'], 'system_prompt_policy':value['system_prompt_policy']})
            while True:
                event = worker.next(until)
                kind = event.get('type')
                if kind in ['worker_error', 'process_closed']:
                    raise InputError('native_worker_closed')
                if event.get('request_id') != value['request_id']:
                    continue
                if kind == 'request_accepted':
                    job['identity'] = {key: event[key] for key in ['request_id', 'request_seq', 'generation']}
                if job['cancelled'].is_set() and 'identity' in job and not job.get('cancel_sent'):
                    worker.send({'schema_version': 1, 'type': 'cancel', **job['identity']})
                    job['cancel_sent'] = True
                if kind == 'gemini_response':
                    frame = json.loads(base64.b64decode(event['data']['data_base64'], validate=True))
                    for candidate in frame.get('candidates', []):
                        job['calls'].extend(part['functionCall'] for part in candidate.get('content', {}).get('parts', []) if 'functionCall' in part)
                if kind == 'completed':
                    job['waiting'] = event.get('native_tool_pending') is True
                    if not job['waiting']:
                        job['final_status'] = 'completed'
                if kind == 'tool_turn_finalized':
                    job['waiting'] = False
                    job['final_status'] = event.get('status')
                self.emit('native_event', value['request_id'], event=event,
                    credential_generation=value['credential_snapshot']['credential_generation'])
                if kind in ['error', 'cancelled', 'rejected']:
                    failed = True
                if kind == 'rejected':
                    raise InputError('native_input_rejected')
                if kind == 'idle':
                    failed = failed or not event.get('next_generation')
                    return
        except Exception as error:
            failed = True
            self.emit('error', value['request_id'], code=str(error) if isinstance(error, InputError) else 'supervisor_execution_failed')
        finally:
            if worker:
                if failed:
                    worker.close()
                with self.condition:
                    worker.busy = False
                    worker.last_used = time.monotonic()
                    if worker.closed and worker in self.workers:
                        self.workers.remove(worker)
                    self.condition.notify_all()
            with self.condition:
                job['waiting'] = False
                # 完成条目只保留有限的去重标识，不保留AT、提示词或工具结果。
                job['value'] = {'request_id': value['request_id'], 'api_token_id': value['api_token_id'], 'model': value['model']}
                job.pop('calls', None)
            try:
                self.emit('job_finalized', value['request_id'], status=job.get('final_status', 'error' if failed else 'prepared'))
            finally:
                with self.condition:
                    # 收口事件先进入唯一输出游标，再唤醒续轮和关闭器，避免退出时丢失最后回执。
                    job['finished'].set()
                    completed = [key for key, item in self.jobs.items() if item['finished'].is_set()]
                    for key in completed[:-256]:
                        self.jobs.pop(key, None)
                    self.condition.notify_all()

    def status(self):
        """返回实际进程、工具等待与资源分项，读取不唤醒。@return 脱敏状态。"""
        with self.condition:
            return {'state': 'busy' if any(worker.busy for worker in self.workers) else 'ready',
                'workers': len(self.workers), 'active': sum(worker.busy for worker in self.workers),
                'tool_waiting': sum(job['waiting'] for job in self.jobs.values()), 'max_workers': self.config['max_workers'],
                'controller': memory(os.getpid()), 'image_bytes': self.pool.decoded_bytes,
                'cgroup_memory':cgroup_memory(),
                'image_decode_calls': self.pool.decode_calls, 'image_scope': 'account_workers',
                'processes': [{'controller': memory(worker.process.pid), 'native': memory(worker.ready['native_pid']) if worker.ready else None,
                    'observer': memory(worker.ready['observer_pid']) if worker.ready else None,
                    'busy': worker.busy, 'credential_generation':worker.config['credential_generation']} for worker in self.workers if worker.process]}

    def cancel(self, request_id, api_token_id):
        """撤销同调用方的原请求。@param request_id 原HTTP请求。@param api_token_id 原调用方。@return 是否登记。"""
        with self.condition:
            job = self.jobs.get(request_id)
            if not job or job['value']['api_token_id'] != api_token_id or job['finished'].is_set():
                return False
            job['cancelled'].set()
            if job['worker'] and 'identity' in job:
                job['worker'].send({'schema_version': 1, 'type': 'cancel', **job['identity']})
                job['cancel_sent'] = True
            return True

    def close(self):
        """关闭准入，收口所有原worker，再释放映像。@return 无。"""
        with self.condition:
            if self.closed:
                return
            self.closed = True
            for job in self.jobs.values():
                if not job['finished'].is_set():
                    self.cancel(job['value']['request_id'], job['value']['api_token_id'])
            self.condition.notify_all()
            workers = list(self.workers)
        # 并行排空共享同一个停止窗口，避免把每个worker的等待时间相加。
        threads = [threading.Thread(target=worker.close, daemon=True) for worker in workers]
        for thread in threads:
            thread.start()
        until = time.monotonic() + 85
        for thread in threads:
            thread.join(timeout=max(0, until-time.monotonic()))
        for job in list(self.jobs.values()):
            job['finished'].wait(max(0, until-time.monotonic()))
        for done in list(self.controls.values()):
            done.wait(max(0,until-time.monotonic()))
        self.reaper.join(timeout=max(0, until-time.monotonic()))
        self.broker.close()
        self.pool.close()
        self.output.close()
        if all(job['finished'].is_set() for job in self.jobs.values()) and all(not worker.process or worker.process.poll() is not None for worker in workers):
            atomic_json(self.root/'stopped.json',{'schema_version':1,'account_id':self.config['account_id'],
                'environment_id':self.config['environment_id'],'environment_generation':self.config['environment_generation']})


def main():
    """提供账号发送器使用的私有监督协议。@return 进程退出码。"""
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', type=Path, required=True)
    args = parser.parse_args()
    os.umask(0o077)
    supervisor = Supervisor(read_private(args.config))
    supervisor.emit('supervisor_ready')
    try:
        while True:
            line = sys.stdin.buffer.readline(67108865)
            if not line:
                break
            value = None
            try:
                if len(line) > 67108864 or not line.endswith(b'\n'):
                    raise InputError('supervisor_input_limit')
                value = json.loads(line)
                if not isinstance(value, dict) or type(value.get('schema_version')) is not int or value['schema_version'] != 1:
                    raise InputError('invalid_supervisor_input')
                kind = value.get('type')
                if kind in ['submit', 'prepare']:
                    supervisor.submit(value)
                elif kind=='finish_tools':
                    supervisor.finish_tools_command(value)
                elif kind == 'status':
                    if set(value) != {'schema_version', 'type', 'request_id'}:
                        raise InputError('invalid_supervisor_input')
                    supervisor.emit('status', value.get('request_id'), status=supervisor.status())
                elif kind == 'cancel':
                    if set(value) != {'schema_version', 'type', 'request_id', 'api_token_id'} or type(value['api_token_id']) is not int:
                        raise InputError('invalid_supervisor_input')
                    accepted = supervisor.cancel(value['request_id'], value['api_token_id'])
                    supervisor.emit('cancel_ack', value['request_id'], accepted=accepted)
                elif kind == 'shutdown':
                    if set(value) != {'schema_version', 'type'}:
                        raise InputError('invalid_supervisor_input')
                    break
                else:
                    raise InputError('unsupported_supervisor_command')
            except Exception as error:
                supervisor.emit('rejected', value.get('request_id') if isinstance(value, dict) else None,
                    code=str(error) if isinstance(error, InputError) else 'invalid_supervisor_input')
    finally:
        supervisor.close()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
