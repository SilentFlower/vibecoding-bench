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
import tempfile
import threading
import time
import uuid
from pathlib import Path

from runtime_files import atomic_json

from .contract import InputError
from .credentials import publish_access_document, read_private
from .criu import CONTROL as CRIU_CONTROL, failure_detail, read_failure
from .gemini_contract import continuation_results
from .headless_search import run_search
from .input_media import preflight_gif
from .image_pool import Broker, ImagePool
from .models import valid_model_mapping
from .process_memory import cgroup_memory, memory
from .storage import Output, private_dir, verify_resources
from .system_prompt import decode_policy, default_policy


TOOL_WAIT_SECONDS = 3600
EXTRA_WORKER_IDLE_SECONDS = 120


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
    if not isinstance(value, dict) or set(value)-{'capture_enabled','system_prompt_policy','gif_frames','disable_safety_filtering','full_egress'} != expected or type(value['schema_version']) is not int or value['schema_version'] != 1 or value['type'] not in ['submit', 'prepare', 'search']:
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
    if not valid_model_mapping(value['model'], value['native_model']) or not isinstance(value['body'], dict):
        raise InputError('invalid_model_or_body')
    if value['type'] == 'search':
        body = value['body']
        if set(body) != {'query', 'previous_request_id'} or not isinstance(body['query'], str) or not body['query'].strip():
            raise InputError('invalid_search_submission')
        parent = body['previous_request_id']
        if parent is not None:
            try:
                if not isinstance(parent, str) or str(uuid.UUID(parent)) != parent:
                    raise ValueError()
            except ValueError:
                raise InputError('invalid_search_parent') from None
    if type(value.get('capture_enabled',False)) is not bool:
        raise InputError('invalid_capture_policy')
    if type(value.get('full_egress',False)) is not bool:
        raise InputError('invalid_capture_policy')
    if type(value.get('gif_frames',False)) is not bool:
        raise InputError('invalid_media_policy')
    if type(value.get('disable_safety_filtering',False)) is not bool:
        raise InputError('invalid_safety_policy')
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
        self.prewarming = False
        self.closed = False
        self.ready = None
        self.reader = None
        self.last_used = time.monotonic()
        self.credential_expires_at = value['credential_snapshot']['expires_at']
        self.seed_template = False
        self.parked = False
        self.start_source = 'exec'
        self.criu_failure = None

    def start(self, until):
        """在同UID隔离角色中启动并核对真实就绪。@param until 原单调截止。@return 无。"""
        # 与发送器的冻结模块路径一致，共享私有文件助手由正式镜像放在/usr/local/bin。
        environment = {'PATH': '/usr/local/bin:/usr/bin:/bin', 'PYTHONPATH': str(Path(__file__).resolve().parents[1])+':/opt/v3/python:/usr/local/bin',
            'AGY_RUNTIME_IMAGE_SOCKET': str(self.owner.socket_path), 'AGY_RUNTIME_SUPERVISOR_PID':str(os.getpid()), 'TMPDIR':str(self.folder)}
        if self.seed_template:
            # 镜像文件可由 CRIU 稳定打开，旧候选和普通启动继续使用封存 memfd。
            environment.pop('AGY_RUNTIME_IMAGE_SOCKET')
            environment.update(AGY_CRIU_TEMPLATE='1', AGY_CRIU_DEADLINE=str(until))
        if self.config.get('capture_root') and os.environ.get('AGY_CAPTURE_NATIVE_TLS')=='1':
            environment['AGY_CAPTURE_NATIVE_TLS']='1'
        self.started_at = time.monotonic()
        with self.lifecycle_lock:
            if self.closed or self.owner.closed:
                raise InputError('supervisor_closed')
            if time.monotonic() >= until:
                raise InputError('request_deadline_exceeded')
            self.process = subprocess.Popen([sys.executable, '-P', '-m', 'agy_runtime.kernel',
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
                self.ready_at = time.monotonic()
                if not self.seed_template:
                    return
            if event.get('type') == 'criu_prepared' and self.seed_template and self.ready:
                self.parked = event['template_ready'] is True
                self.criu_failure = read_failure(event.get('failure'))
                self.seed_template = self.parked
                return
            if event.get('type') in ['worker_error', 'process_closed']:
                self.criu_failure = read_failure(event.get('failure'))
                raise InputError('worker_start_failed')

    def resume(self, until):
        """恢复本进程持有的同代模板。@param until 本次请求原截止。@return 无。"""
        self.send({'schema_version':1,'type':'criu_restore','until':until})
        while True:
            event = self.next(until)
            if event.get('type') == 'criu_restored':
                self.parked = False
                self.seed_template = False
                self.start_source = 'criu_restore'
                self.ready_at = time.monotonic()
                return
            if event.get('type') in {'worker_error','process_closed','rejected'}:
                self.criu_failure = read_failure(event.get('failure'))
                raise InputError('worker_restore_failed')

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
        # 编排端独立按归属清理历史采集。发送器启动只依赖当前监督器的私有状态。
        private_dir(self.root / 'workers')
        verify_resources()
        self.condition = threading.Condition(threading.RLock())
        self.workers = []
        self.search_slots = 0
        self.jobs = {}
        self.credential_generation=0
        self.credential_identity=None
        self.restore_enabled=(os.environ.get('AGY_CRIU')=='1'
            and Path(__file__).resolve().parent==Path('/opt/v3/python/agy_runtime'))
        self.restore_allowed = config.get('restore_allowed', True) is True
        self.template_failure=None
        self.last_start_source=None
        self.controls = {}
        self.closed = False
        self.output = output or Output()
        self.pool = ImagePool(config['binary_path'])
        self.image_sha = '39816d49d5ab92229952987225c23ea3fed7580699dcb4a444e0388e0ac1ce43'
        # 候选摘要与监督代次叠加后会超过 Unix socket 路径上限。端点使用发送器私有临时目录。
        self.socket_directory = tempfile.TemporaryDirectory(prefix='agy-image-', dir='/tmp')
        self.socket_path = Path(self.socket_directory.name) / 'image.sock'
        try:
            self.broker = Broker(self.socket_path, self.pool, {os.getuid()})
        except Exception:
            self.socket_directory.cleanup()
            raise
        self.reaper = threading.Thread(target=self.reap_idle, daemon=True)
        self.reaper.start()

    def reap_idle(self):
        """保留一个基础热进程，按各自寿命回收额外热进程和模板。@return 无。"""
        while True:
            with self.condition:
                if self.closed:
                    return
                now = time.monotonic()
                now_ms = time.time_ns() // 1_000_000
                idle = []
                retained_warm = False
                retained_templates = set()
                # 工具等待和正在预热的 worker 仍持有独占标志；仅回收已归还的空闲进程。
                for worker in sorted(self.workers, key=lambda item: item.last_used, reverse=True):
                    if worker.busy:
                        continue
                    parked = worker.parked
                    # 基础热进程服务下一笔请求，额外热进程覆盖短间隔的连续并发。
                    if parked:
                        idle_expired = not self.restore_allowed or worker.key in retained_templates
                    else:
                        idle_expired = retained_warm and now - worker.last_used >= EXTRA_WORKER_IDLE_SECONDS
                    if (idle_expired or worker.key[0] < self.credential_generation or worker.credential_expires_at <= now_ms
                            or worker.process is None or worker.process.poll() is not None):
                        idle.append(worker)
                    elif parked:
                        retained_templates.add(worker.key)
                    else:
                        retained_warm = True
                excess = len(self.workers) + self.search_slots - len(idle) - self.config['max_workers']
                if excess > 0:
                    # 缩容优先回收模板和最久未使用的空闲实例，保留执行和待回填实例。
                    available = [worker for worker in self.workers if not worker.busy and worker not in idle]
                    idle.extend(sorted(available, key=lambda worker: (not worker.parked, worker.last_used))[:excess])
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
            self.config['proxy_url'], value.get('capture_enabled',False))

    def acquire(self, value, until, seed=True):
        """在物理上限内选择或建立当前代次进程。@param value 提交。@param until 截止。@param seed 是否尝试建模板。@return 独占worker。"""
        key = self.worker_key(value)
        while True:
            stale = None
            with self.condition:
                if self.closed:
                    raise InputError('supervisor_closed')
                # 旧代退役也消费原请求预算，截止后禁止复用或启动下一代。
                if time.monotonic() >= until:
                    raise InputError('request_deadline_exceeded')
                if len(self.workers) + self.search_slots > self.config['max_workers']:
                    self.condition.wait(until - time.monotonic())
                    continue
                # 优先复用已经启动的进程，把单次快照留给需要扩容的请求。
                now_ms = time.time_ns() // 1_000_000
                for worker in sorted(self.workers, key=lambda item: item.parked):
                    if (not worker.busy and not worker.closed and worker.key == key
                            and (not worker.parked or self.restore_allowed)
                            and worker.credential_expires_at > now_ms and worker.process is not None
                            and worker.process.poll() is None):
                        worker.busy = True
                        return worker
                if any(worker.prewarming and worker.key==key for worker in self.workers):
                    # 当前身份已有进程在握手，后续请求沿自己的截止等待同一次准备。
                    self.condition.wait(max(0, until-time.monotonic()))
                    continue
                stale = next((worker for worker in self.workers if not worker.busy), None)
                if stale:
                    stale.busy = True
                elif len(self.workers) + self.search_slots < self.config['max_workers']:
                    worker = Worker(self, value)
                    worker.seed_template=seed and value['type']=='prepare' and self.can_seed_template()
                    requested_template=worker.seed_template
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
            if requested_template:
                with self.condition:
                    self.record_template_attempt(worker,worker.parked)
            return worker
        except Exception:
            if requested_template:
                with self.condition:
                    self.record_template_attempt(worker,False)
            worker.close()
            with self.condition:
                self.workers.remove(worker)
                self.condition.notify_all()
            if requested_template and time.monotonic()<until:
                return self.acquire(value,until,seed=False)
            raise

    def restore_available(self):
        """只认实际挂载的可信控制入口。@return 能否登记启动模板。"""
        return self.restore_enabled and self.restore_allowed and Path(CRIU_CONTROL).exists()

    def record_template_attempt(self, worker: Worker, ready: bool, stage: str = 'worker_start') -> None:
        """在池锁内保存同代结果。@param worker 原进程。@param ready 模板是否就绪。@param stage 未收到细节时的阶段。@return 无。"""
        if worker.key[0]==self.credential_generation and worker.credential_expires_at>time.time_ns()//1_000_000:
            self.template_failure=None if ready else worker.criu_failure or failure_detail(stage)

    def prewarm_replacement(self, source, value, until, template=False):
        """用空余名额预热替代进程。@param source 原工作进程。@param value 同代凭据及启动配置。@param until 原生成截止。@param template 是否保存启动模板。@return 无返回值。"""
        worker=None
        snapshot=value['credential_snapshot']
        try:
            with self.condition:
                if (self.closed or source not in self.workers or source.closed
                        or snapshot['credential_generation']!=self.credential_generation
                        or time.monotonic()>=until or snapshot['expires_at']<=time.time_ns()//1_000_000):
                    return
                if template:
                    if not self.can_seed_template():
                        return
                elif self.config['max_workers']<2+self.search_slots or self.workers!=[source] or not source.busy:
                    return
                # 暖进程先登记到同一个物理池，业务与后台同时启动时共用并发上限。
                worker=Worker(self, value)
                worker.seed_template=template
                worker.prewarming=True
                self.workers.append(worker)
            worker.start(until)
            with self.condition:
                if (not self.closed and not worker.closed and snapshot['credential_generation']==self.credential_generation
                        and snapshot['expires_at']>time.time_ns()//1_000_000):
                    if template:
                        self.record_template_attempt(worker,worker.parked)
                    else:
                        self.last_start_source = worker.start_source
                    worker.prewarming=False
                    worker.busy=False
                    worker.last_used=time.monotonic()
                    self.condition.notify_all()
        except Exception:
            # 补位失败后允许普通 checkout 按原路径恢复，原工具轮仍由原进程完成。
            with self.condition:
                if template and worker:
                    self.record_template_attempt(worker,False)
                elif template and snapshot['credential_generation']==self.credential_generation:
                    self.template_failure=failure_detail('worker_start')
        finally:
            if worker and worker.prewarming:
                try:
                    worker.close()
                finally:
                    with self.condition:
                        if worker.closed and (not worker.process or worker.process.poll() is not None):
                            self.workers.remove(worker)
                        worker.prewarming=False
                        self.condition.notify_all()

    def can_seed_template(self):
        """在池锁内检查模板租约和剩余进程名额。@return 是否可启动零业务模板。"""
        return (self.restore_available() and len(self.workers)+self.search_slots<self.config['max_workers']
            and not any(getattr(worker,'seed_template',False) for worker in self.workers))

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
            if job.get('claimed') or job.get('headless_request'):
                raise InputError('tool_continuation_already_claimed')
            job['claimed'] = True
            identity = job['identity']
            job['worker'].send({'schema_version': 1, 'type': 'finish_tool_turn', **identity, 'body': value['body']})
        self.await_tools_finalized(job, min(until, job['until']))

    def submit(self, raw):
        """登记唯一HTTP请求并在线程中执行。@param raw 受信提交。@return 无。"""
        value = validate_submission(raw, self.config)
        until = deadline(value['deadline_unix_ms'])
        with self.condition:
            if self.closed or value['request_id'] in self.jobs:
                raise InputError('request_already_registered')
            previous = value['body'].get('previous_request_id') if value['type'] == 'search' else None
            parent = self.jobs.get(previous) if previous else None
            if previous and (not parent or not parent['waiting'] or parent.get('claimed') or parent['cancelled'].is_set()
                    or parent.get('headless_request') or parent['until'] <= time.monotonic()
                    or parent['value']['api_token_id'] != value['api_token_id'] or parent['value']['model'] != value['model']
                    or not any(call.get('name') in ('WebSearch', 'web_search') and isinstance(call.get('args', {}).get('query'), str)
                        and call['args']['query'].strip() == value['body']['query'] for call in parent['calls'])):
                raise InputError('search_parent_mismatch')
            generation=value['credential_snapshot']['credential_generation']
            identity=hashlib.sha256(value['credential_snapshot']['access_token'].encode()).digest()
            if generation<self.credential_generation or generation==self.credential_generation and identity!=self.credential_identity:
                raise InputError('stale_credential_generation')
            if generation>self.credential_generation:
                self.template_failure=None
                self.last_start_source=None
                self.condition.notify_all()
            self.credential_generation=generation
            self.credential_identity=identity
            self.jobs[value['request_id']] = {'value': value, 'until': until, 'received': time.monotonic(), 'finished': threading.Event(),
                'cancelled': threading.Event(), 'worker': None, 'calls': [], 'waiting': False}
            if parent:
                parent['headless_request'] = value['request_id']
        if value['type'] == 'search':
            try:
                threading.Thread(target=self.execute_search, args=(value, until, parent), daemon=True).start()
            except RuntimeError:
                with self.condition:
                    self.jobs.pop(value['request_id'], None)
                    if parent:
                        parent.pop('headless_request', None)
                raise InputError('search_start_failed') from None
        else:
            threading.Thread(target=self.execute, args=(value, until), daemon=True).start()

    def reserve_search_slot(self, until, cancelled):
        """独立搜索占用现有物理容量。@param until 原单调截止。@param cancelled 原取消通知。@return 无。"""
        while True:
            with self.condition:
                if self.closed or cancelled.is_set():
                    raise InputError('request_cancelled')
                remaining = until - time.monotonic()
                if remaining <= 0:
                    raise InputError('request_deadline_exceeded')
                if len(self.workers) + self.search_slots < self.config['max_workers']:
                    self.search_slots += 1
                    return
                idle = next((worker for worker in self.workers if not worker.busy), None)
                if idle is None:
                    self.condition.wait(min(remaining, .25))
                    continue
                idle.busy = True
            idle.close()
            with self.condition:
                if idle in self.workers:
                    self.workers.remove(idle)
                self.condition.notify_all()

    def execute_search(self, value, until, parent):
        """在独立或原等待许可内执行原版搜索。@param value 已核验查询。
        @param until 原单调截止。@param parent 已核验的待回填任务或空。@return 无。"""
        request_id = value['request_id']
        job = self.jobs[request_id]
        reserved = False
        status = 'error'
        try:
            if parent is None:
                self.reserve_search_slot(until, job['cancelled'])
                reserved = True
            # 有原回合时原 worker 正在等待客户端，headless 与回填共享许可并串行执行。
            image = self.pool.acquire()
            try:
                with tempfile.TemporaryDirectory(prefix='search-', dir=self.root) as folder:
                    result = run_search(image, private_dir(folder), value['model'], value['credential_snapshot'],
                        self.config['proxy_url'], value['body']['query'], until, job['cancelled'])
            finally:
                os.close(image)
            if job['cancelled'].is_set():
                raise InputError('request_cancelled')
            self.emit('search_result', request_id, result=result)
            status = 'completed'
        except Exception as error:
            self.emit('error', request_id, code=str(error) if isinstance(error, InputError) else 'headless_search_failed')
        finally:
            with self.condition:
                if reserved:
                    self.search_slots -= 1
                if parent:
                    parent.pop('headless_request', None)
                job['value'] = {key: value[key] for key in ('request_id', 'api_token_id', 'model')}
                self.condition.notify_all()
            try:
                self.emit('job_finalized', request_id, status=status)
            finally:
                self.record_finished(job)

    def finish_tools_command(self, value):
        """只投递原工具结果，保持零模型发送和原截止。@param value 无凭据控制信封。@return 无。"""
        expected={'schema_version','type','request_id','account_id','environment_id','environment_generation','api_token_id','previous_request_id','body'}
        if set(value)-{'gif_frames'}!=expected or type(value.get('gif_frames',False)) is not bool or value['type']!='finish_tools' or type(value['api_token_id']) is not int or value['api_token_id']<1 or not isinstance(value['body'],dict):
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
            if value.get('gif_frames'):
                preflight_gif(value['body'])
            with self.condition:
                job=self.jobs.get(value['previous_request_id'])
                if not job or job['value']['api_token_id']!=value['api_token_id'] or job['until']<=time.monotonic():raise InputError('tool_continuation_identity')
                if job.get('continuation_digest'):
                    if job['continuation_digest']!=digest:raise InputError('tool_completion_receipt_mismatch')
                else:
                    if not job['waiting'] or job.get('claimed') or job.get('headless_request'):raise InputError('tool_turn_not_waiting')
                    continuation_results(job['value']['body'],job['calls'],value['body'])
                    job['claimed']=True;job['continuation_digest']=digest
                    job['worker'].send({'schema_version':1,'type':'finish_tool_turn',**job['identity'],'body':value['body']})
            self.await_tools_finalized(job,job['until'])
            self.emit('tools_finished',value['request_id'],previous_request_id=value['previous_request_id'])
        except Exception as error:
            self.emit('control_error',value['request_id'],code=str(error) if isinstance(error,InputError) else 'tool_completion_failed')
        finally:
            done.set()
            with self.condition:self.controls.pop(value['request_id'],None)

    def await_tools_finalized(self, job, until):
        """区分原生已接纳后的失败与回执暂未确认。@param job 原生作业。@param until 单调截止。@return 正常收口时无返回值。"""
        if not job['finished'].wait(max(0,until-time.monotonic())):
            raise InputError('tool_completion_pending')
        if job.get('final_status')!='completed':
            raise InputError('previous_tool_turn_failed' if job.get('tool_results_accepted') else 'tool_completion_failed')

    def execute(self, value, until):
        """持有进程直到真实idle，HTTP工具完成时保留原工具归属。@param value 提交。@param until 原截止。@return 无。"""
        job = self.jobs[value['request_id']]
        worker = None
        failed = False
        replacement_required = False
        replacement_scheduled = False
        preparation_deadline = until
        try:
            self.continuation(value, until)
            checkout_started = time.monotonic()
            worker = self.acquire(value, until)
            job['worker'] = worker
            if job['cancelled'].is_set():
                raise InputError('request_cancelled')
            if value['type'] == 'prepare':
                with self.condition:
                    if not worker.parked and worker.started_at >= checkout_started and worker.key[0] == self.credential_generation:
                        self.last_start_source = worker.start_source
                self.emit('prepared', value['request_id'], native={**worker.ready,'template_ready':worker.parked})
                return
            restore_started = None
            if worker.parked:
                try:
                    restore_started = time.monotonic()
                    worker.resume(min(until, restore_started + 25))
                except (InputError, OSError, ValueError):
                    restore_started = None
                    with self.condition:
                        self.record_template_attempt(worker,False,'checkpoint_restore')
                    worker.close()
                    with self.condition:
                        self.workers.remove(worker)
                        self.condition.notify_all()
                    worker = self.acquire(value,until,seed=False)
                    job['worker']=worker
            checkout_finished = time.monotonic()
            started_at = worker.started_at if restore_started is None else restore_started
            if job['cancelled'].is_set() or time.monotonic()>=until:
                raise InputError('request_cancelled' if job['cancelled'].is_set() else 'request_deadline_exceeded')
            with self.condition:
                if started_at >= checkout_started and worker.key[0] == self.credential_generation:
                    self.last_start_source = worker.start_source
                should_seed=self.can_seed_template()
            if should_seed:
                seed={key:value[key] for key in ('account_id','credential_snapshot','capture_enabled')}
                try:
                    threading.Thread(target=self.prewarm_replacement,args=(worker,seed,until,True),daemon=True).start()
                except RuntimeError:
                    # 背景预热失败时优先完成已接纳的模型请求。
                    pass
            payload={'schema_version': 1, 'type': 'gemini_request', 'request_id': value['request_id'],
                'model': value['model'], 'native_model': value['native_model'],
                'body': value['body'], 'system_prompt_policy':value['system_prompt_policy']}
            if value.get('gif_frames'):payload['gif_frames']=True
            if value.get('disable_safety_filtering'):payload['disable_safety_filtering']=True
            if value.get('capture_enabled') and value.get('full_egress'):payload['full_egress']=True
            worker.send(payload)
            while True:
                event = worker.next(until)
                kind = event.get('type')
                if kind in ['worker_error', 'process_closed']:
                    raise InputError('native_worker_closed')
                if event.get('request_id') != value['request_id']:
                    continue
                if kind in ('foreign_model_observed', 'unassigned_model_observed'):
                    replacement_required = True
                if kind == 'request_accepted':
                    job['identity'] = {key: event[key] for key in ['request_id', 'request_seq', 'generation']}
                if kind == 'request_prepared':
                    # 以同一单调时钟覆盖原生组装。进程启动属于获取进程的一部分。
                    received = job['received']
                    event['runtime'] = {
                        'worker_id': event['worker_id'], 'worker_pid': worker.ready['native_pid'],
                        'kernel_generation': event['generation'], 'warm_hit': worker.ready_at <= received,
                        'start_source': worker.start_source,
                        'preparation_wait_ms': int((checkout_started - received) * 1000),
                        'checkout_ms': int((checkout_finished - checkout_started) * 1000),
                        'worker_start_ms': int((worker.ready_at - started_at) * 1000) if started_at >= checkout_started else None,
                        'prepared_ms': int((time.monotonic() - received) * 1000),
                    }
                if job['cancelled'].is_set() and 'identity' in job and not job.get('cancel_sent'):
                    worker.send({'schema_version': 1, 'type': 'cancel', **job['identity']})
                    job['cancel_sent'] = True
                if kind == 'gemini_response':
                    frame = json.loads(base64.b64decode(event['data']['data_base64'], validate=True))
                    for candidate in frame.get('candidates', []):
                        job['calls'].extend(part['functionCall'] for part in candidate.get('content', {}).get('parts', []) if 'functionCall' in part)
                if kind == 'completed':
                    with self.condition:
                        if event.get('native_tool_pending') is True:
                            # 只有已确认的原生工具调用进入独立等待期，普通生成仍遵守提交截止。
                            expires_at_ms = time.time_ns() // 1_000_000 + TOOL_WAIT_SECONDS * 1000
                            until = time.monotonic() + TOOL_WAIT_SECONDS
                            job['until'] = until
                            event['tool_wait_expires_at_ms'] = expires_at_ms
                            job['waiting'] = True
                        else:
                            job['waiting'] = False
                            job['final_status'] = 'error' if event.get('control_error_code') else 'completed'
                if kind == 'tool_continuation_accepted':
                    job['tool_results_accepted'] = True
                if kind == 'tool_turn_finalized':
                    job['waiting'] = False
                    job['final_status'] = event.get('status')
                if kind == 'rejected' and value.get('capture_enabled'):
                    # 解析拒绝没有原生提交，仍让网关保存同次脱敏入站。
                    event['capture_status'] = 'queued'
                self.emit('native_event', value['request_id'], event=event,
                    credential_generation=value['credential_snapshot']['credential_generation'])
                if replacement_required and job['waiting'] and not replacement_scheduled and not job['cancelled'].is_set():
                    replacement_scheduled = True
                    seed={key:value[key] for key in ('account_id','credential_snapshot','capture_enabled')}
                    try:
                        threading.Thread(target=self.prewarm_replacement,args=(worker,seed,preparation_deadline),daemon=True).start()
                    except RuntimeError:
                        pass
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
            with self.condition:
                job['waiting'] = False
                search = self.jobs.get(job.get('headless_request'))
                if search:
                    search['cancelled'].set()
            if search:
                search['finished'].wait(max(0, search['until']-time.monotonic()))
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
                self.record_finished(job)

    def record_finished(self, job):
        """关闭退出通知并修剪终态回执。@param job 已发布收口的作业。@return 无。"""
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
            active=sum(worker.busy for worker in self.workers)+self.search_slots
            idle=[worker for worker in self.workers if not worker.busy and not worker.closed and worker.ready is not None
                and not getattr(worker,'parked',False) and worker.process is not None and worker.process.poll() is None]
            available=self.restore_available()
            template=available and any(worker.parked and not worker.closed and not worker.busy
                and worker.process is not None and worker.process.poll() is None
                and worker.key[0]==self.credential_generation and worker.credential_expires_at>time.time_ns()//1_000_000
                for worker in self.workers)
            preparing=available and any(worker.busy and worker.seed_template and not worker.parked
                for worker in self.workers)
            if not available:
                restore_state, restore_reason = 'unavailable', 'controller_unavailable'
            elif template:
                restore_state, restore_reason = 'ready', None
            elif preparing:
                restore_state, restore_reason = 'preparing', 'template_preparing'
            elif self.template_failure:
                restore_state, restore_reason = 'unavailable', 'template_failed'
            else:
                restore_state, restore_reason = 'waiting', None
            return {'state': 'busy' if active else 'ready', 'capacity_protocol': 1,
                'allocated_workers': len(self.workers)+self.search_slots,
                'workers': sum(not getattr(worker,'parked',False) for worker in self.workers), 'active': active, 'idle_workers': len(idle),
                'idle_pid': idle[0].ready['native_pid'] if idle else None,
                'warming_workers': sum(worker.prewarming for worker in self.workers),
                'tool_waiting': sum(job['waiting'] for job in self.jobs.values()), 'max_workers': self.config['max_workers'],
                'headless_searches': sum(job['value'].get('type')=='search' for job in self.jobs.values()),
                'controller': memory(os.getpid()), 'image_bytes': self.pool.decoded_bytes,
                'cgroup_memory':cgroup_memory(),
                'image_decode_calls': self.pool.decode_calls, 'image_scope': 'account_workers',
                'restore': {'schema_version':1,'state':restore_state,
                    'reason':restore_reason,'template_ready':template,
                    'last_start_source':self.last_start_source,
                    **({'failure':self.template_failure.copy()} if restore_reason=='template_failed' else {})},
                'processes': [{'controller': memory(worker.process.pid), 'native': memory(worker.ready['native_pid']) if worker.ready else None,
                    'observer': memory(worker.ready['observer_pid']) if worker.ready else None,
                    'busy': worker.busy, 'credential_generation':worker.config['credential_generation']} for worker in self.workers if worker.process]}

    def set_capacity(self, max_workers: int, restore_allowed: bool) -> int:
        """应用同一代次的新上限。@param max_workers 已核验的进程上限。@param restore_allowed 当前恢复预算是否允许。@return 已生效上限。"""
        if type(max_workers) is not int or not 1 <= max_workers <= 64 or type(restore_allowed) is not bool:
            raise InputError('invalid_worker_capacity')
        with self.condition:
            self.config['max_workers'] = max_workers
            self.restore_allowed = restore_allowed
            self.condition.notify_all()
            return max_workers

    def cancel(self, request_id, api_token_id):
        """撤销同调用方的原请求。@param request_id 原HTTP请求。@param api_token_id 原调用方。@return 是否登记。"""
        with self.condition:
            job = self.jobs.get(request_id)
            if not job or job['value']['api_token_id'] != api_token_id or job['finished'].is_set():
                return False
            job['cancelled'].set()
            search = self.jobs.get(job.get('headless_request'))
            if search:
                search['cancelled'].set()
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
        try:
            self.broker.close()
        finally:
            self.socket_directory.cleanup()
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
                if kind in ['submit', 'prepare', 'search']:
                    supervisor.submit(value)
                elif kind=='finish_tools':
                    supervisor.finish_tools_command(value)
                elif kind == 'status':
                    if set(value) != {'schema_version', 'type', 'request_id'}:
                        raise InputError('invalid_supervisor_input')
                    supervisor.emit('status', value.get('request_id'), status=supervisor.status())
                elif kind == 'capacity':
                    if set(value) != {'schema_version', 'type', 'request_id', 'max_workers', 'restore_allowed'}:
                        raise InputError('invalid_supervisor_input')
                    supervisor.emit('capacity_applied', value['request_id'],
                        max_workers=supervisor.set_capacity(value['max_workers'], value['restore_allowed']))
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
