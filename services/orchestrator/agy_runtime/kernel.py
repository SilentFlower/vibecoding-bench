"""可独立启动的agy私有NDJSON内核原型，单工作进程串行投递。"""
import argparse
import copy
import fcntl
from functools import partial
import hashlib
import http.client
import json
import os
from pathlib import Path
import re
import signal
import shutil
import subprocess
import sys
import threading
import time
import traceback
import uuid
from .contract import CAPABILITIES, InputError, MODEL, fields, history_steps, request
from .storage import ROOT, SOURCE_SHA, Output, binary, config, private_dir
from .stream_controller import DrainBridge, NativeJob, DeliverySpool
from .layer_reader import LayerReader
from .tool_broker import Broker
from .gemini_frames import Frames
from .models import configure_model
from .capture import save_egress, save_submission
from .wire_capture import NativeTlsTrace
from .credentials import read_access_document
from .criu import Template
from .safety_egress import CLOUD_CODE, SafetyEgress

SNAPSHOT_WRITERS=threading.BoundedSemaphore(2)
CONTROL_CLOSE_ERRORS={'native_request_failed','native_transport_error','native_control_timeout','native_not_idle',
    'native_process_exited','native_protocol_error'}
NATIVE_ERRORS=CONTROL_CLOSE_ERRORS|{'cancelled','cancel_timeout','native_stream_incomplete','native_delivery_error',
    'native_start_rejected','tool_protocol_error','native_tool_yield_timeout','native_tool_yield_failed',
    'ambiguous_parallel_function_calls','unsupported_gemini_candidate_count','invalid_native_gemini_parts',
    'native_safety_endpoint_rejected','native_safety_egress_unobserved'}
CONTROL_EXCEPTION_TYPES={'AssertionError','AttributeError','IndexError','JSONDecodeError','KeyError',
    'OSError','RuntimeError','TimeoutError','TypeError','ValueError'}
PROTOCOL_READER_ERRORS={'native_root_identity.unfinished_stream':'native_root_identity.unfinished_stream',
    'native_root_identity.call_reused':'native_root_identity.call_reused',
    'native_root_identity.additional_call':'native_root_identity.additional_call',
    'native_root_identity.invalid_context':'native_root_identity.invalid_context',
    'native_root_identity.missing_cascade':'native_root_identity.missing_cascade',
    'source_request_identity':'source_request_identity','source_call_identity':'source_call_identity',
    '源事件活动作业归属冲突':'active_job_mismatch'}
PROTOCOL_OBSERVER_ERRORS={'活动作业缺失':'active_job_missing','活动原生调用数量越界':'active_call_limit',
    'SDK原始帧缺少活动作业':'sdk_job_missing','SDK原始帧存在多个活动模型调用':'sdk_multiple_calls',
    'SDK原始帧缺少模型调用':'sdk_call_missing','SDK原始帧采集长度越界':'sdk_frame_limit',
    'SDK原始帧读取失败':'sdk_frame_unreadable','原生返回缺少调用归属':'receive_call_missing',
    '结束后原生返回发生变化':'receive_after_eof','原生成功接收缺少消息对象':'receive_message_missing'}


class RPC:
    """独立等待真实原生HTTP响应。"""

    def __init__(self, worker, method, body, scope, timeout=None):
        """启动RPC。@param worker 物理工作进程。@param method 原生方法。@param body 正文。@param scope 归属。@param timeout 连接预算。@return 无返回值。"""
        self.done=threading.Event();self.value=None;self.error=None;self.response_status=None
        def run():
            """归档实际原生结果。@return 无返回值。"""
            connection=http.client.HTTPConnection('127.0.0.1',worker.port,timeout=timeout)
            record={'method':method,'body':body,'request_seq':scope.seq if scope else None,'generation':worker.bridge.generation,'history_step_count':scope.history_count if scope else 0}
            if method=='SetCloudCodeURL' and body.get('url','').startswith('http://127.0.0.1:'):
                record['body']={'target':'request_scoped_loopback'}
            try:
                connection.request('POST','/exa.language_server_pb.LanguageServerService/'+method,json.dumps(body,ensure_ascii=False).encode(),
                    {'Content-Type':'application/json','x-codeium-csrf-token':worker.bridge.csrf})
                response=connection.getresponse();self.response_status=response.status
                self.value={'status':self.response_status,'response':json.loads(response.read())};record.update(self.value)
            except Exception as exc:self.error=type(exc).__name__;record['transport_error']=self.error
            finally:
                connection.close()
                if worker.owner.cfg['capture_enabled']:
                    with worker.rpc_lock:
                        with (worker.bridge.folder/'rpc.ndjson').open('a') as stream:stream.write(json.dumps(record,ensure_ascii=False)+'\n')
                self.done.set()
        self.thread=threading.Thread(target=run,daemon=True);self.thread.start()


class Scope:
    """绑定一次已受理请求与真实原生代次。"""

    def __init__(self, value, seq, worker):
        """创建请求归属。@param value 已验证请求。@param seq 内核序号。@param worker 工作进程。@return 无返回值。"""
        self.history_count=len(value['native_steps']) if 'native_steps' in value else len(history_steps(value['messages']));self.value=value;self.seq=seq;self.worker=worker;self.route=f'r-{seq}';self.root=None;self.job=None
        self.frames=Frames();self.native_tool_calls=None;self.compatibility_error=None;self.tool_wait_ready=threading.Event();self.tool_wait_published=False;self.resume_claimed=False;self.final_status=None;self.yield_tools=threading.Event();self.yield_cancelled=threading.Event();self.yield_started=None;self.yield_rpc=None
        self.broker=None;self.cancel=threading.Event();self.cancel_started=None;self.cancel_sent=False;self.finished=threading.Event()
        self.safety_egress=None;self.tls_trace=None
        self.isolated_call_ids=set()
        self.tool_native_ids=()

    def identity(self):
        """返回公开协议身份。@return 身份字段。"""
        return {'request_id':self.value['request_id'],'request_seq':self.seq,'generation':self.worker.bridge.generation}

    def result_recovery_blocker(self, code, spool):
        """诊断阻止保留已交付结果的首个条件。@param code 原生失败码。@param spool 已交付观察。@return 受控代码，允许保留时返回空。"""
        job=self.job
        if code not in CONTROL_CLOSE_ERRORS:return 'ineligible_error'
        if self.value.get('request_format')!='gemini':return 'unsupported_protocol'
        if self.cancel.is_set():return 'cancelled'
        if self.compatibility_error:return 'compatibility_error'
        if not job or job.calls!=1:return 'model_call_count'
        if job.ends!=1 or not job.ended.is_set():return 'missing_model_eof'
        if job.native_error:return 'model_error'
        if self.native_tool_calls or self.tool_wait_ready.is_set() or self.yield_tools.is_set():return 'tool_pending'
        if blocker:=self.frames.recovery_blocker():return blocker
        if not spool or spool.overflow or spool.failure:return 'delivery_error'
        if self.safety_egress and self.safety_egress.model_status!=200:
            return 'model_http_status'
        # 读取器在第一个异常后退出。观察器仍可排空，必须核对较早的错误没有破坏已交付的结果。
        if any(type(event.get('ns')) is not int or event['ns']<=job.end_ns for event in self.worker.bridge.errors):
            return 'observer_before_eof'
        return None


class Bridge(DrainBridge):
    """保持唯一原生读取器，并交付完整源事件。"""

    def __init__(self, folder, worker):
        """创建固定观察后端。@param folder 私有路径。@param worker 所属物理进程。@return 无返回值。"""
        super().__init__(folder,True);self.worker=worker

    def _emit(self, event):
        """先校验原生归属，再归档、计数和转发。@param event 源事件。@return 无返回值。"""
        if not self.worker.owns_source(event):
            return
        if event['event'] != 'model_tls_write':
            super()._emit(event)
        self.worker.on_source(event)

    def protocol_failure(self):
        """归类原生协议失败。@return 允许写入网关日志的来源与错误码。"""
        if self.errors:
            return 'observer.'+PROTOCOL_OBSERVER_ERRORS.get(self.errors[0].get('error'),'other')
        error=self.reader_error or {}
        exception=error.get('type')
        return 'reader.'+PROTOCOL_READER_ERRORS.get(error.get('message'),
            exception if exception in CONTROL_EXCEPTION_TYPES else 'other')


class Worker:
    """持有固定官方执行体与一代原生进程。"""

    def __init__(self, owner):
        """初始化独立代次。@param owner 内核控制器。@return 无返回值。"""
        self.owner=owner;self.rpc_lock=threading.Lock();self.telemetry={};self.jobs=0
        self.bridge=Bridge(owner.state/'workers'/str(uuid.uuid4()),self)
        self.bridge.native_home=private_dir(owner.cfg['home']);self.bridge.binary=owner.binary;self.bridge.ca_file=owner.cfg.get('ca_file');self.bridge.proxy_url=owner.cfg['proxy_url']
        self.bridge.capture_enabled=owner.cfg['capture_enabled'];
        self.bridge.checkpoint_enabled=owner.template_enabled
        # 单环境候选可运行在旧发送器上。只有新平台声明支持快照格式后才启用原生 TLS。
        self.bridge.capture_tls=bool(owner.cfg.get('capture_root')) and os.environ.get('AGY_CAPTURE_NATIVE_TLS')=='1'
        if self.bridge.capture_enabled:
            self.bridge.events.close();self.bridge.events=(self.bridge.folder/'bridge-events.jsonl').open('w')
        self.bridge.runtime_env=dict(owner.cfg['runtime_env']);self.bridge.startup_timeout=owner.cfg['startup_timeout'];self.bridge.retire_timeout=owner.cfg['retire_timeout']
        self.port=None;self.ready=False;self.template=None

    def start(self):
        """按真实init与PID套接字绑定就绪。@return 无返回值。"""
        started=time.monotonic();logdir=self.bridge.native_home/'.gemini/antigravity-cli/log'
        previous={}
        for path in logdir.glob('*.log'):
            info=path.stat();previous[str(path)]=(info.st_dev,info.st_ino,info.st_size)
        self.bridge._start();attempts=[];deadline=started+self.owner.cfg['startup_timeout']
        while time.monotonic()<deadline and self.bridge.proc.poll() is None:
            inodes=set()
            for path in Path(f'/proc/{self.bridge.native_pid}/fd').iterdir():
                try:target=os.readlink(path)
                except FileNotFoundError:continue
                if target.startswith('socket:['):inodes.add(target[8:-1])
            ports=set()
            for table in ['tcp','tcp6']:
                for line in Path(f'/proc/{self.bridge.native_pid}/net/{table}').read_text().splitlines()[1:]:
                    row=line.split()
                    if row[3]=='0A' and row[9] in inodes:ports.add(int(row[1].split(':')[1],16))
            candidates=set()
            for path in logdir.glob('*.log'):
                info=path.stat();old=previous.get(str(path));offset=old[2] if old and old[:2]==(info.st_dev,info.st_ino) and info.st_size>=old[2] else 0
                with path.open('rb') as stream:stream.seek(offset);content=stream.read().decode(errors='replace')
                for value in re.findall(r'Language server listening on random port at (\d+) for HTTP\b',content):
                    if int(value) in ports:candidates.add(int(value))
            confirmed=[]
            for port in sorted(candidates):
                connection=http.client.HTTPConnection('127.0.0.1',port,timeout=.5);record={'port':port,'native_pid':self.bridge.native_pid}
                try:
                    connection.request('POST','/exa.language_server_pb.LanguageServerService/GetCapabilities',b'{}',{'Content-Type':'application/json','x-codeium-csrf-token':self.bridge.csrf})
                    response=connection.getresponse();data=json.loads(response.read());record.update(status=response.status,response=data)
                    if response.status==200 and isinstance(data,dict) and set(data)<={'supportsHookResultProtoBytes'} and type(data.get('supportsHookResultProtoBytes',False)) is bool:confirmed.append(port)
                except Exception as exc:record['error']=type(exc).__name__
                finally:connection.close();attempts.append(record)
            (self.bridge.folder/'listener-identity.json').write_text(json.dumps({'previous_logs':previous,'attempts':attempts,'confirmed':confirmed},ensure_ascii=False,indent=2))
            if len(confirmed)==1:self.port=confirmed[0];break
            if len(confirmed)>1:raise RuntimeError('native_listener_identity_conflict')
            time.sleep(.02)
        if self.port is None:raise RuntimeError('native_listener_identity_timeout')
        self.ready=True;self.bridge.start_reader()
        self.owner.emit('worker_ready',generation=self.bridge.generation,native_pid=self.bridge.native_pid,observer_pid=self.bridge.proc.pid,
            source_sha256=SOURCE_SHA,capabilities=CAPABILITIES,runtime_policy={'runtime_env':self.bridge.runtime_env,'rotate_after':self.owner.cfg['rotate_after']})

    def owns_source(self, event):
        """在调用计数前核对作业与 Cascade。@param event 原生观察。@return 是否属于当前作业。"""
        kind=event['event']
        if kind not in ('model_start','response_chunk','model_end','gemini_response','model_tls_write'):
            return True
        scope=self.owner.active
        if scope is None or scope.worker is not self or event['request_id']!=scope.route:
            if kind=='model_tls_write':return False
            raise RuntimeError('source_request_identity')
        job=scope.job;call_id=event.get('call_id')
        if call_id in scope.isolated_call_ids:
            if kind=='model_start':raise RuntimeError('native_root_identity.call_reused')
            return False
        if kind!='model_start':
            if call_id and job and call_id==job.call_id:return True
            if kind=='model_tls_write':return False
            raise RuntimeError('source_call_identity')
        conversation=event['native_context'].get('ConversationID')
        if not isinstance(conversation,str) or not isinstance(call_id,str) or not call_id:
            raise RuntimeError('native_root_identity.invalid_context')
        if job and call_id==job.call_id:raise RuntimeError('native_root_identity.call_reused')
        if conversation==scope.root:return True
        if scope.isolated_call_ids and not (scope.tool_wait_published and scope.broker
                and scope.broker.gemini_results is not None):
            raise RuntimeError('native_root_identity.additional_call')
        if (scope.value.get('request_format')!='gemini' or not job or job.calls!=1 or job.ends!=1
                or not job.ended.is_set() or scope.frames.finish_reason!='STOP'):
            raise RuntimeError('native_root_identity.unfinished_stream')
        if not conversation and not scope.frames.calls:
            raise RuntimeError('native_root_identity.missing_cascade')
        # 旧轮已接纳结果后，独立调用仍与原根不同。隔离其全部帧，并在原轮收尾后退役进程。
        scope.isolated_call_ids.add(call_id)
        self.owner.emit('foreign_model_observed' if conversation else 'unassigned_model_observed',**scope.identity())
        return False

    def on_source(self, event):
        """核对来源并输出独立协议事件。@param event 实际观察事件。@return 无返回值。"""
        kind=event['event']
        if kind == 'model_tls_write':
            scope = self.owner.active
            if scope and scope.worker is self and scope.route == event.get('request_id') and scope.tls_trace:
                scope.tls_trace.append(event)
            return
        if kind=='telemetry_upload_sample':
            source=str(event['source'])
            state=self.telemetry.setdefault(source,{'permanent_error_observed':False,'retry_error_observed':False,'successful_nonempty_return_observed':False})
            state['last_status']=event['upload_status_raw'];state['last_error_present']=event['error_present']
            if event['error_present']:
                state['permanent_error_observed'] |= event['upload_status_raw'] not in range(2,11)
                state['retry_error_observed'] |= event['upload_status_raw'] in range(2,11)
            elif event['upload_status_raw']==1 and event['returned_count']>0:state['successful_nonempty_return_observed']=True
            self.owner.emit('telemetry',generation=self.bridge.generation,data=event,state=copy.deepcopy(state))
        if kind in ['model_start','response_chunk','model_end','gemini_response']:
            scope=self.owner.active
            if kind=='gemini_response' and scope.value.get('request_format')=='gemini':
                if scope.safety_egress and not scope.safety_egress.model_started:
                    scope.compatibility_error='native_safety_egress_unobserved';scope.yield_tools.set();return
                try:frames=scope.frames.project(event)
                except RuntimeError as exc:
                    # 兼容拒绝仍让原生读取器继续排空，并使用同一取消路径收回运行态。
                    scope.compatibility_error=str(exc);scope.yield_tools.set();frames=[]
                for frame in frames:self.owner.emit(kind,**scope.identity(),data=frame)
            else:self.owner.emit(kind,**scope.identity(),data=event)

    def call(self, method, body, scope, timeout=30):
        """完成控制RPC。@param method 方法。@param body 正文。@param scope 归属。@param timeout 秒。@return 实际响应。"""
        future=RPC(self,method,body,scope,timeout)
        if not future.done.wait(timeout+1):raise RuntimeError('native_control_timeout')
        if future.error:
            # 错误正文可能不是 JSON，实际收到的 HTTP 错误状态仍然有效。
            if future.response_status is not None and 400 <= future.response_status < 600:
                return {'status': future.response_status, 'response': None}
            raise RuntimeError('native_transport_error')
        return future.value

    def park(self, until):
        """封存尚未发出模型请求的工作进程。@param until 原单调截止。@return 保存耗时，普通启动时为空。"""
        self.template=Template(self.bridge)
        try:
            return self.template.park(until)
        except (OSError, ValueError, subprocess.TimeoutExpired):
            self.template.close()
            if self.template.suspended:
                self.abort_template()
                raise
            self.template=None
            return None

    def restore(self, until):
        """重新核对观察和原控制端点，之后才准入模型请求。@param until 原单调截止。@return 恢复耗时。"""
        if not self.template or not self.template.parked:
            raise InputError('agy_criu_not_parked')
        try:
            elapsed=self.template.restore(until)
            remaining=until-time.monotonic()
            if remaining<=0 or self.bridge.reader_error or self.bridge.errors:
                raise RuntimeError('agy_criu_observer')
            response=self.call('GetCapabilities',{},None,min(.5,remaining))
            if response['status']!=200 or not isinstance(response['response'],dict):
                raise RuntimeError('agy_criu_listener')
            return elapsed
        except Exception:
            self.abort_template()
            raise

    def abort_template(self):
        """业务投递前撤销控制器租约并快速收回停态原进程。@return 无。"""
        self.template.close()
        self.template.suspended=True
        process=self.bridge.proc
        if isinstance(process, subprocess.Popen) and process.poll() is None:
            os.killpg(process.pid,signal.SIGKILL)
            process.wait(timeout=2)
        self.bridge.retire_timeout=0

    def retire(self, reason):
        """先观察业务队列再交还原生关闭，等待物理退出。@param reason 退役原因。@return 退出证据。"""
        self.ready=False
        self.owner.emit('retirement_start',generation=self.bridge.generation,reason=reason)
        reader=None;drain={'state':'unknown'};started=time.monotonic()
        try:
            if self.template and self.template.suspended:
                self.template.close()
                raise RuntimeError('agy_criu_parked')
            reader=LayerReader(self.bridge);reader.discover();empty_since=None
            deadline=started+max(1,self.owner.cfg['retire_timeout']-15)
            while time.monotonic()<deadline:
                state=reader.snapshot();layers=state['layers'];clients=state['clients']
                known=bool(layers) and {c['source'] for c in clients}>={327,2747,2992} and not state['errors'] and not state['layer_errors']
                empty=known and all(c['buffered_events']==0 for c in clients if c['source'] in [327,2747])
                empty=empty and all(not r.get('deferred',{}).get('events',0) and (not r['deferred_present'] or r['deferred']['resolved'] or r['deferred']['closed']) and r.get('cel',{}).get('in_flight_events',0)==0 for r in layers)
                if empty:
                    if empty_since is None:empty_since=time.monotonic()
                    if time.monotonic()-empty_since>=.5:drain={'state':'business_queues_empty','sample':state};break
                else:empty_since=None
                time.sleep(.1)
            else:drain={'state':'timeout','sample':state}
        except Exception as exc:drain={'state':'unknown','error':type(exc).__name__}
        finally:
            if reader:reader.close()
        self.bridge.stop_reader();self.bridge.retire_timeout=max(1,self.owner.cfg['retire_timeout']-(time.monotonic()-started))
        if self.template and self.template.suspended and not self.ready:
            self.bridge.retire_timeout=1
        process=self.bridge.close_worker();self.bridge.events.close()
        evidence={'process':process,'pre_shutdown':drain,'telemetry':copy.deepcopy(self.telemetry),'seconds':time.monotonic()-started}
        self.owner.emit('worker_retired',generation=self.bridge.generation,reason=reason,**evidence)
        return evidence


class Kernel:
    """管理私有协议、串行请求、历史引用与原生轮换。"""

    def __init__(self, cfg, state):
        """建立当前账号的独立内核。@param cfg 固定配置。@param state 私有根。@return 无返回值。"""
        global MODEL
        MODEL = configure_model(cfg['public_model'], cfg['native_model'])
        self.cfg=cfg;self.state=state;self.queued=None;self.queued_thread=None;self.lock=threading.RLock();self.active=None;self.closing=False;self.seq=0;self.worker_id=str(uuid.uuid4())
        self.template_enabled=os.environ.get('AGY_CRIU_TEMPLATE')=='1'
        self.sequence_file=state/'request-sequence.json'
        if self.sequence_file.is_symlink():raise ValueError('序号状态类型错误')
        if self.sequence_file.exists():
            self.seq=json.loads(self.sequence_file.read_text())
            if type(self.seq) is not int or self.seq<0:raise ValueError('序号状态损坏')
        private_dir(state/'workers');private_dir(state/'histories');private_dir(state/'requests')
        self.binary=binary(state, cfg['binary_path']);self.worker=None;self.output=Output(state/'protocol-output.ndjson' if cfg['capture_enabled'] else None)
        self.base_config=json.loads((ROOT/'resources/cascade-config.json').read_text())

    def emit(self, kind, **data):
        """追加一个版本化协议事件。@param kind 类型。@param data 已核对数据。@return 无返回值。"""
        self.output.emit({'schema_version':1,'protocol':'agy-native-stdio','type':kind,'worker_id':self.worker_id,**data})

    def boot(self):
        """启动新物理代次。@return 无返回值。"""
        self.worker=Worker(self)
        try:self.worker.start()
        except Exception:
            if self.worker.bridge.proc:self.worker.retire('startup_failed')
            raise

    def accept(self, raw, _queued=False):
        """验证请求或绑定待回填续轮。@param raw JSON 输入。@param _queued 内部已保留的续轮。@return 无。"""
        value=request(raw)
        if value['history_id']:
            path=self.state/'histories'/(value['history_id']+'.json')
            if path.is_symlink():raise InputError('invalid_history_id')
            try:stored=json.loads(path.read_text())
            except OSError as exc:raise InputError('unknown_history_id') from exc
            value['messages']=stored['messages']
            if value['system'] is None:value['system']=stored['system']
            history_steps(value['messages'])
        value['system']=value['system'] if value['system'] is not None else ''
        with self.lock:
            if self.closing:raise InputError('closing')
            if self.worker.template and self.worker.template.parked:raise InputError('agy_criu_not_restored')
            if self.queued is not None and not _queued:raise InputError('busy')
            if self.active:
                previous=self.active
                if value.get('request_format')!='gemini' or not previous.tool_wait_published or previous.resume_claimed:raise InputError('busy')
                from .gemini_contract import continuation_results
                results=continuation_results(previous.value['gemini_body'],previous.frames.calls,value['gemini_body'])
                previous.resume_claimed=True;self.queued=copy.deepcopy(raw)
                self.emit('continuation_queued',request_id=value['request_id'],pending_request_id=previous.value['request_id'])
                self.queued_thread=threading.Thread(target=self.resume,args=(previous,results),daemon=True);self.queued_thread.start();return
            if _queued:self.queued=None
            self.seq+=1;sequence_temp=self.sequence_file.with_suffix('.new');sequence_temp.write_text(json.dumps(self.seq));sequence_temp.replace(self.sequence_file)
            scope=Scope(value,self.seq,self.worker);self.active=scope
            self.emit('request_accepted',**scope.identity(),parameter_policy=value.get('compatibility_notes',[]),system_prompt_policy=value.get('system_prompt_policy'),capture_status='queued' if self.cfg.get('capture_root') else 'disabled')
            threading.Thread(target=self.execute,args=(scope,),daemon=True).start()

    def resume(self, previous, results):
        """先完成旧轮真实工具及 Hook，再创建独立的新轮。@param previous 待回填轮次。@param results 真实结果。@return 无。"""
        raw=self.queued
        try:
            previous.broker.complete_gemini(results);previous.finished.wait()
            if previous.final_status!='completed':raise InputError('previous_tool_turn_failed')
            self.accept(raw,_queued=True)
        except Exception as exc:
            with self.lock:self.queued=None
            self.emit('rejected',request_id=raw['request_id'],code=str(exc) if isinstance(exc,InputError) else 'gemini_continuation_failed')

    def publish_tool_wait(self, scope):
        """完成公开响应并保留原生工具轮直到真实结果到达。@param scope 当前轮次。@return 无。"""
        source=[(c['name'],c.get('args',{})) for c in scope.frames.calls]
        native=[(c['name'],json.loads(c['argumentsJson'])) for c in scope.native_tool_calls]
        ids=tuple(c['id'] for c in scope.native_tool_calls)
        known_ids=set(ids)
        if (source!=native or len(known_ids)!=len(ids)
                or any(call['id'] in known_ids and call['id']!=identifier
                       for call,identifier in zip(scope.frames.calls,ids))):
            raise RuntimeError('tool_protocol_error')
        scope.tool_native_ids=ids
        scope.tool_wait_published=True
        self.emit('completed',**scope.identity(),finish_reason='tool_calls',history_id=None,history_error=None,native_cascade_id=scope.root,native_trajectory_id=scope.broker.trajectory_id,native_model_calls=scope.job.calls,native_empty=False,native_tool_pending=True)

    def finish_tool_turn(self, raw):
        """只完成原工具轮，由监督层选择下一代进程。@param raw 同归属工具续轮。@return 无。"""
        fields(raw, {'schema_version', 'type', 'request_id', 'request_seq', 'generation', 'body'})
        with self.lock:
            scope = self.active
            if not scope or not scope.tool_wait_published or scope.resume_claimed or not scope.broker:
                raise InputError('gemini_tool_turn_closed')
            if any(raw.get(key) != value for key, value in scope.identity().items()):
                raise InputError('gemini_tool_turn_identity')
            from .gemini_contract import continuation_results
            results = continuation_results(scope.value['gemini_body'], scope.frames.calls, raw['body'])
            scope.broker.complete_gemini(results)
            scope.resume_claimed = True
            self.emit('tool_continuation_accepted', **scope.identity())

    def cancel(self, raw):
        """只取消完全匹配的活动请求。@param raw 命令。@return 无返回值。"""
        fields(raw,{'schema_version','type','request_id','request_seq','generation'})
        with self.lock:
            scope=self.active;matched=bool(scope and type(raw.get('request_seq')) is int and all(raw.get(k)==v for k,v in scope.identity().items()))
            if matched:scope.cancel.set();scope.cancel_started=scope.cancel_started or time.monotonic()
            self.emit('cancel_ack',accepted=matched,request_id=raw.get('request_id'),request_seq=raw.get('request_seq'),generation=raw.get('generation'))

    def export_history(self, scope, trajectory):
        """保存内核签发的历史引用。@param scope 当前归属。@param trajectory 实际完整轨迹。@return 引用或显式不可用状态。"""
        messages=copy.deepcopy(scope.value['messages'])
        offset=scope.history_count
        for step in trajectory['steps'][offset:]:
            if 'userInput' in step:messages.append({'role':'user','text':step['userInput'].get('userResponse','')})
            elif 'plannerResponse' in step:
                planner=step['plannerResponse'];message={'role':'assistant','text':planner.get('response','')}
                if planner.get('modifiedResponse',planner.get('response',''))!=planner.get('response',''):return None,'unsupported_native_export'
                if planner.get('thinking'):message.update(thinking=planner['thinking'],thinking_signature=planner.get('thinkingSignature'))
                if planner.get('toolCalls'):
                    message['tool_calls']=[{'id':c['id'],'name':c['name'],'arguments':json.loads(c['argumentsJson']),'thinking_signature':c.get('thinkingSignature')} for c in planner['toolCalls']]
                messages.append(message)
            elif 'generic' in step:
                call=step['metadata']['toolCall'];result=step['generic']['result']
                if not isinstance(result.get('result'),str):return None,'unsupported_native_export'
                messages.append({'role':'tool','tool_call_id':call['id'],'text':result['result']})
            else:return None,'unsupported_native_export'
        try:history_steps(messages)
        except InputError:return None,'unsupported_native_export'
        ident=str(uuid.uuid4());path=self.state/'histories'/(ident+'.json')
        path.write_text(json.dumps({'messages':messages,'system':scope.value['system'],'native_cascade':scope.root,'native_trajectory':trajectory['trajectoryId']},ensure_ascii=False))
        return ident,None

    def execute(self, scope):
        """执行唯一模型发送并公开唯一终态及空闲。@param scope 已受理请求。@return 无返回值。"""
        worker=scope.worker;retire=False;failed=False;spool=None;future=None
        phase='prepare';control_status=None
        folder=private_dir(self.state/'requests'/scope.route)
        try:
            if scope.value.get('gemini_body') is not None:(folder/'gemini-input.json').write_text(json.dumps(scope.value['gemini_body'],ensure_ascii=False))
            steps=copy.deepcopy(scope.value['native_steps']) if 'native_steps' in scope.value else history_steps(scope.value['messages']);cfg=copy.deepcopy(self.base_config)
            (folder/'input-mapping.json').write_text(json.dumps({'schema_changes':scope.value.get('schema_changes',[]),'completion':scope.value.get('native_completion',{}),'history_steps':len(steps),'compatibility_notes':scope.value.get('compatibility_notes',[]),'system_prompt_policy':scope.value.get('system_prompt_policy'),'input_view':'decoded_gemini_input','submission_view':'native_cascade_prompt_sections'},ensure_ascii=False))
            cfg['plannerConfig']['planModel']=MODEL
            cfg['plannerConfig']['declarativeMixinConfig']['promptSections']=[{'custom':{'content':scope.value['system']}}]
            if scope.value.get('request_format')=='gemini':cfg['plannerConfig']['retryConfig']['modelOutputRetry']={'maxRetries':0}
            if scope.value.get('native_completion'):cfg['plannerConfig']['completionConfigOverride']=scope.value['native_completion']
            cfg['executorConfig']['maxGeneratorInvocations']=scope.value['max_generations']
            if scope.value['tools']:
                scope.broker=Broker(self,scope,folder);scope.broker.configure(cfg)
            cfg['trajectoryConversionConfig'].update(useStructuredToolResponses=True,wrapToolResponses=False)
            if worker.bridge.capture_tls and not scope.value.get('safety_egress_rules'):
                scope.tls_trace = NativeTlsTrace()
            active=worker.bridge.run_folder/'active.json';temporary=active.with_suffix('.new');temporary.write_text(json.dumps({'request_id':scope.route}));temporary.replace(active)
            if rules:=scope.value.get('safety_egress_rules'):
                token=read_access_document(worker.bridge.native_home)['token']['access_token']
                capture=partial(self.capture_egress,scope,token) if self.cfg.get('capture_root') else None
                scope.safety_egress=SafetyEgress(rules,token,worker.bridge.proxy_url,worker.bridge.ca_file,capture)
                switched=worker.call('SetCloudCodeURL',{'url':scope.safety_egress.url},scope)
                if switched['status']!=200:
                    control_status=switched['status']
                    raise RuntimeError('native_safety_endpoint_rejected')
            root=worker.call('StartCascade',{'source':'CORTEX_TRAJECTORY_SOURCE_AGENT_API','requestedModel':MODEL},scope)
            control_status=root['status']
            if root['status']!=200:raise RuntimeError('native_start_rejected')
            scope.root=root['response']['cascadeId']
            if scope.cancel.is_set():raise RuntimeError('cancelled')
            spool=DeliverySpool(folder/'native-stream.ndjson',worker.bridge.generation,scope.route,pending_limit=67108864,total_limit=268435456)
            scope.job=NativeJob(scope.route,spool);worker.bridge.active_job=scope.job
            # 原生先处理items再追加additionalSteps，导入历史时将新输入显式放在历史末尾。
            items=[{'text':scope.value['prompt']}]
            if 'native_steps' in scope.value:items=[]
            elif scope.history_count:
                steps.append({'type':'CORTEX_STEP_TYPE_USER_INPUT','status':'CORTEX_STEP_STATUS_DONE','metadata':{},'userInput':{'userResponse':scope.value['prompt']}});items=[]
            body={'cascadeId':scope.root,'items':items,'additionalSteps':steps,'cascadeConfig':cfg,'blocking':True,'propagateError':True}
            if self.cfg.get('capture_root'):
                self.capture_submission(scope,body)
            self.emit('request_prepared', **scope.identity())
            phase='submission';control_status=None
            future=RPC(worker,'SendUserCascadeMessage',body,scope)
            while not future.done.wait(.05):
                if scope.value.get('request_format')=='gemini' and scope.job.ended.is_set() and not scope.frames.terminal:
                    raise RuntimeError('native_stream_incomplete')
                if scope.broker and scope.broker.failure:raise RuntimeError('tool_protocol_error')
                if worker.bridge.reader_error or worker.bridge.errors:raise RuntimeError('native_protocol_error')
                if (scope.tool_wait_ready.is_set() and not scope.tool_wait_published and not scope.cancel.is_set()
                        and scope.job.calls==scope.job.ends==1 and scope.job.ended.is_set() and not scope.job.native_error
                        and not scope.frames.source_error and not scope.compatibility_error
                        and scope.native_tool_calls is not None and len(scope.frames.calls)==len(scope.native_tool_calls)):
                    self.publish_tool_wait(scope)
                if scope.yield_tools.is_set() and scope.yield_rpc is None:
                    # 客户端负责工具执行；使用原生取消收回当前 RPC，再由下一请求导入真实结果。
                    scope.cancel_sent=True;scope.yield_started=time.monotonic();scope.yield_rpc=RPC(worker,'CancelCascadeInvocation',{'cascadeId':scope.root,'killBackgroundTasks':True,'notifyParent':False},scope,10)
                if scope.yield_rpc and scope.yield_rpc.done.is_set():scope.yield_cancelled.set()
                if scope.yield_started and time.monotonic()-scope.yield_started>self.cfg['cancel_timeout']:raise RuntimeError('native_tool_yield_timeout')
                if scope.cancel.is_set() and not scope.cancel_sent:
                    scope.cancel_sent=True;RPC(worker,'CancelCascadeInvocation',{'cascadeId':scope.root,'killBackgroundTasks':True,'notifyParent':False},scope,10)
                if scope.cancel_started and time.monotonic()-scope.cancel_started>self.cfg['cancel_timeout']:raise RuntimeError('cancel_timeout')
                if worker.bridge.proc.poll() is not None:raise RuntimeError('native_process_exited')
            if scope.cancel.is_set():raise RuntimeError('cancelled')
            if future.error:raise RuntimeError('native_transport_error')
            yielded=scope.yield_tools.is_set()
            if yielded:
                if scope.yield_rpc is None or not scope.yield_rpc.done.wait(11) or scope.yield_rpc.error or scope.yield_rpc.value['status']!=200:raise RuntimeError('native_tool_yield_failed')
                scope.yield_cancelled.set();retire=True
            elif future.value['status']!=200:raise RuntimeError('native_request_failed')
            if scope.compatibility_error:raise RuntimeError(scope.compatibility_error)
            if not scope.job.ended.wait(3):raise RuntimeError('native_stream_incomplete')
            phase='trajectory'
            current=worker.call('GetCascadeTrajectory',{'cascadeId':scope.root},scope)
            control_status=current['status']
            if current['status']!=200 or current['response']['status']!='CASCADE_RUN_STATUS_IDLE':raise RuntimeError('native_not_idle')
            # 收尾 RPC 期间仍可能到达观察事件，确认轨迹空闲后再冻结本次计数。
            if worker.bridge.reader_error or worker.bridge.errors:raise RuntimeError('native_protocol_error')
            if scope.job.calls<1 or scope.job.calls!=scope.job.ends or scope.job.calls>scope.value['max_generations'] or scope.job.native_error:raise RuntimeError('native_stream_incomplete')
            if scope.value.get('request_format')=='gemini' and not scope.frames.terminal:raise RuntimeError('native_stream_incomplete')
            if scope.frames.calls and not scope.tool_wait_published:raise RuntimeError('tool_protocol_error')
            if spool.overflow or spool.failure:raise RuntimeError('native_delivery_error')
            phase='finalize'
            trajectory=current['response']['trajectory'];(folder/'trajectory.json').write_text(json.dumps(trajectory,ensure_ascii=False))
            try:
                if scope.value.get('request_format')=='gemini':ident,history_error=None,None
                else:ident,history_error=self.export_history(scope,trajectory)
            except Exception:
                ident=None;history_error='native_history_export_failed'
                with (folder/'history-error.log').open('a') as stream:traceback.print_exc(file=stream)
            worker.jobs+=1;retire=retire or bool(scope.isolated_call_ids) or self.cfg['rotate_after'] is not None and worker.jobs>=self.cfg['rotate_after']
            if scope.safety_egress and not retire and not self.closing:
                # 空值不能恢复原生端点。恢复失败时退役当前进程，避免影响下一次请求。
                try:retire=worker.call('SetCloudCodeURL',{'url':CLOUD_CODE},scope)['status']!=200
                except RuntimeError:retire=True
            last_planner=next((s['plannerResponse'] for s in reversed(trajectory['steps']) if 'plannerResponse' in s),{})
            finish_reason='tool_calls' if scope.value.get('request_format')=='gemini' and scope.frames.calls else 'generation_limit' if last_planner.get('toolCalls') else 'stop'
            scope.final_status='completed'
            self.emit('tool_turn_finalized' if scope.tool_wait_published else 'completed',**scope.identity(),finish_reason=finish_reason,status='completed',history_id=ident,history_error=history_error,native_cascade_id=scope.root,native_trajectory_id=trajectory['trajectoryId'],native_empty=scope.job.chunks==0,native_model_calls=scope.job.calls,native_tool_pending=False)
        except Exception as exc:
            retire=True;failed=True;code=str(exc) if isinstance(exc,RuntimeError) else 'kernel_internal_error'
            if code not in NATIVE_ERRORS:code='kernel_internal_error'
            blocker=scope.result_recovery_blocker(code,spool)
            recovery=blocker or 'kept'
            if phase=='submission' and future:
                control_status=future.response_status
            status=control_status if type(control_status) is int and 100<=control_status<=599 else 'unknown'
            exception=type(exc).__name__
            if exception not in CONTROL_EXCEPTION_TYPES:exception='other'
            # 旧网关只输出事件类型。固定枚举和状态码进入类型，保留请求关联并避免输出原生错误正文。
            if code=='native_protocol_error':
                self.emit('native_protocol.'+worker.bridge.protocol_failure(),**scope.identity())
            self.emit(f'native_control.{phase}.{code}.{status}.{exception}.{recovery}',**scope.identity())
            try:
                with (folder/'error.log').open('a') as stream:traceback.print_exc(file=stream)
            except OSError:
                pass
            if blocker is None:
                # 已按顺序交付原始 STOP 和用量。控制失败由真实退役收口，原模型结果不重放。
                scope.final_status='completed'
                self.emit('completed',**scope.identity(),finish_reason='stop',status='completed',
                    native_cascade_id=scope.root,native_model_calls=1,native_empty=False,native_tool_pending=False,
                    control_error_code=code,control_recovery=recovery)
            else:
                kind='cancelled' if scope.cancel.is_set() else 'error'
                scope.final_status=kind
                failure_status={}
                if kind=='error':
                    if type(control_status) is int and 400<=control_status<600:
                        failure_status['control_http_status']=control_status
                    if scope.safety_egress and scope.safety_egress.model_status==429:
                        failure_status['upstream_http_status']=429
                self.emit('tool_turn_finalized' if scope.tool_wait_published else kind,**scope.identity(),status=kind,code=code,control_recovery=recovery,
                    native_stream_complete=bool(scope.job and scope.job.ended.is_set()),native_model_calls=scope.job.calls if scope.job else 0,
                    native_cascade_id=scope.root,native_trajectory_id=scope.broker.trajectory_id if scope.broker else None,**failure_status)
        finally:
            try:
                if scope.broker:scope.broker.close()
                if scope.safety_egress:scope.safety_egress.close()
                if scope.tls_trace and scope.tls_trace.call_id:
                    try:
                        token = read_access_document(self.cfg['home'])['token']['access_token']
                        self.capture_egress(scope, token, scope.tls_trace, None, [], [], native_tls=True)
                    except (OSError, ValueError, KeyError):
                        pass
                if retire or self.closing:
                    worker.retire('shutdown' if self.closing else 'request_error' if failed else 'gemini_tool_yield' if scope.yield_tools.is_set() else 'rotation')
                if spool:
                    spool.finish();(folder/'delivery-summary.json').write_text(json.dumps(scope.job.summary(),ensure_ascii=False))
                worker.bridge.active_job=None
                # 每个内核进程只持有一个物理代次，替换由账号监督层统一准入。
                if retire:self.closing=True
            except Exception:
                self.closing=True
                with (folder/'error.log').open('a') as stream:traceback.print_exc(file=stream)
                self.emit('worker_error',generation=worker.bridge.generation,code='retirement_or_restart_failed')
            finally:
                if not self.cfg['capture_enabled']:
                    shutil.rmtree(folder, ignore_errors=True)
                with self.lock:
                    self.emit('idle',**scope.identity(),next_generation=self.worker.bridge.generation if self.worker and self.worker.ready and not self.closing else None)
                    self.active=None;scope.finished.set()

    def capture_submission(self, scope, submitted):
        """有界后台保存脱敏副本，失败仅产生采集状态。@param scope 原请求。@param submitted 实际RPC对象。@return 无。"""
        if not SNAPSHOT_WRITERS.acquire(blocking=False):
            self.emit('capture_status',**scope.identity(),capture_status='dropped');return
        def save():
            """只读取当前worker的AT进行重复秘密脱敏。@return 无。"""
            status='failed'
            try:
                token=read_access_document(self.cfg['home'])['token']['access_token']
                save_submission(self.cfg['capture_root'],self.cfg['account_id'],scope.value['request_id'],scope.value['gemini_body'],submitted,token,scope.value.get('system_prompt_policy'))
                status='saved'
            except Exception:pass
            finally:
                SNAPSHOT_WRITERS.release()
                self.emit('capture_status',**scope.identity(),capture_status=status)
        threading.Thread(target=save,daemon=True).start()

    def capture_egress(self, scope, token, trace, raw, incoming, forwarded, *, native_tls=False):
        """后台保存同一作业的出站观察。@param scope 原请求。@param token 访问凭据。@param trace 实际观察。@param raw 提交实体。@param incoming 原生头。@param forwarded 适配头。@param native_tls 来源为原生TLS。@return 无。"""
        if not SNAPSHOT_WRITERS.acquire(blocking=False):return
        def save():
            try:
                save_egress(self.cfg['capture_root'],self.cfg['account_id'],scope.value['request_id'],trace,raw,incoming,forwarded,token,native_tls=native_tls,full_body=scope.value.get('full_egress',False))
            except (OSError,ValueError):pass
            finally:SNAPSHOT_WRITERS.release()
        threading.Thread(target=save,daemon=True).start()

    def shutdown(self):
        """停止准入并等待当前请求和物理进程退出。@return 无返回值。"""
        with self.lock:
            self.closing=True;scope=self.active
            if scope:scope.cancel.set();scope.cancel_started=scope.cancel_started or time.monotonic()
        if scope:scope.finished.wait(self.cfg['cancel_timeout']+self.cfg['retire_timeout']+20)
        if self.queued_thread:self.queued_thread.join(timeout=15)
        if self.worker and self.worker.bridge.proc:self.worker.retire('shutdown')
        self.emit('shutdown_complete');self.output.close()


def main():
    """运行固定版本NDJSON内核。@return 进程退出码。"""
    parser=argparse.ArgumentParser(description='固定agy 1.5.9的私有NDJSON研究内核')
    parser.add_argument('--config');parser.add_argument('--state-dir');parser.add_argument('--capabilities',action='store_true');args=parser.parse_args()
    if args.capabilities:print(json.dumps(CAPABILITIES,ensure_ascii=False));return 0
    if not args.config or not args.state_dir:parser.error('需要--config与--state-dir')
    os.umask(0o077);state=private_dir(args.state_dir);lock=(state/'kernel.lock').open('a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    parent=os.environ.get('AGY_RUNTIME_SUPERVISOR_PID')
    if parent:
        expected_parent=int(parent)
        def watch_parent():
            # worker由请求线程创建；按整个监督进程核对，避免Linux线程PDEATHSIG误杀暖进程。
            while True:
                if os.getppid()!=expected_parent:
                    os._exit(72)
                time.sleep(.25)
        threading.Thread(target=watch_parent,daemon=True).start()
    service=None
    try:
        service=Kernel(config(args.config),state);service.boot()
        if service.template_enabled:
            elapsed=service.worker.park(float(os.environ['AGY_CRIU_DEADLINE']))
            service.emit('criu_prepared',template_ready=elapsed is not None,dump_ms=elapsed)
        for line in sys.stdin:
            raw=None
            try:
                raw=json.loads(line)
                if not isinstance(raw,dict) or type(raw.get('schema_version')) is not int or raw.get('schema_version')!=1:raise InputError('invalid_schema')
                kind=raw.get('type')
                if kind=='gemini_request':service.accept(raw)
                elif kind=='criu_restore':
                    fields(raw,{'schema_version','type','until'})
                    elapsed=service.worker.restore(raw['until'])
                    service.emit('criu_restored',restore_ms=elapsed)
                elif kind=='cancel':service.cancel(raw)
                elif kind=='finish_tool_turn':service.finish_tool_turn(raw)
                elif kind=='tool_result':
                    scope=service.active
                    if scope and scope.broker:scope.broker.complete(raw)
                    else:service.emit('tool_result_ack',accepted=False,request_id=raw.get('request_id'),request_seq=raw.get('request_seq'),generation=raw.get('generation'),tool_call_id=raw.get('tool_call_id'),tool_execution_id=raw.get('tool_execution_id'))
                elif kind=='status':
                    fields(raw,{'schema_version','type'});service.emit('status',generation=service.worker.bridge.generation,native=service.worker.bridge.snapshot(),active=service.active.identity() if service.active else None,telemetry=service.worker.telemetry)
                elif kind=='shutdown':fields(raw,{'schema_version','type'});break
                else:raise InputError('unsupported_command')
            except (InputError,ValueError,TypeError) as exc:service.emit('rejected',code=str(exc) if isinstance(exc,InputError) else 'invalid_or_unsupported_input',request_id=raw.get('request_id') if isinstance(raw,dict) else None)
    except Exception as error:
        if service and service.cfg['capture_enabled']:
            with (state/'kernel-error.log').open('a') as stream:traceback.print_exc(file=stream)
        if service:service.emit('worker_error',code='kernel_startup_or_protocol_failed',error_type=type(error).__name__)
        else:print(json.dumps({'schema_version':1,'protocol':'agy-native-stdio','type':'worker_error','code':'native_configuration'}),flush=True)
        return 2
    finally:
        if service:service.shutdown()
    return 0


if __name__=='__main__':raise SystemExit(main())
