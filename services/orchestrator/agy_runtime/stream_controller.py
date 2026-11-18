"""研究独立原生读取器、按游标消费的磁盘暂存和有界内存诊断窗口。"""
from .validation import require
import collections
import hashlib
import json
from pathlib import Path
import threading
import time
import sys

from .capture_bridge import ResearchBridge


class EventWindow:
    """只在内存保存有界的近期私有诊断，完整源事件另存文件。"""

    def __init__(self, byte_limit=131072, event_limit=32):
        """设置序列化诊断预算。@param byte_limit JSON字节预算。@param event_limit 条数。@return 无返回值。"""
        self.items=collections.deque();self.bytes=0;self.peak=0;self.evicted=0
        self.byte_limit=byte_limit;self.event_limit=event_limit

    def append(self, event):
        """保存近期原始事件引用。@param event 原生事件。@return 无返回值。"""
        size=len(json.dumps(event,ensure_ascii=False).encode())
        if size>self.byte_limit:self.evicted+=1;return
        self.items.append((size,event));self.bytes+=size
        while self.bytes>self.byte_limit or len(self.items)>self.event_limit:
            size,_=self.items.popleft();self.bytes-=size;self.evicted+=1
        self.peak=max(self.peak,self.bytes)

    def __len__(self):
        """取得当前诊断条数。@return 条数。"""
        return len(self.items)


class ArchiveRecords(list):
    """将完整RPC归档到磁盘并保持空的内存历史列表。"""

    def __init__(self, path):
        """创建独立实验归档。@param path 输出文件。@return 无返回值。"""
        super().__init__();self.stream=Path(path).open('w');self.lock=threading.Lock();self.count=0

    def append(self, record):
        """保存真实RPC并释放历史保留。@param record 完整RPC。@return 无返回值。"""
        with self.lock:
            self.stream.write(json.dumps(record,ensure_ascii=False)+'\n');self.stream.flush();self.count+=1

    def close(self):
        """关闭已完成的磁盘归档。@return 无返回值。"""
        self.stream.close()


class DeliverySpool:
    """用独立文件游标交付完整事件，限制未消费字节及单作业磁盘体积。"""

    def __init__(self, path, generation, job, pending_limit=1048576, total_limit=16777216, delay=0, hold=False):
        """设置研究消费策略。@param path 暂存文件。@param generation 原生代次。@param job 作业。@param pending_limit 未消费字节。@param total_limit 文件字节。@param delay 每条事件消费秒数。@param hold 先保持消费。@return 无返回值。"""
        self.path=Path(path);self.writer=self.path.open('wb',buffering=0)
        self.generation=generation;self.job=job;self.pending_limit=pending_limit;self.total_limit=total_limit;self.delay=delay
        self.condition=threading.Condition();self.gate=threading.Event();self.done=threading.Event()
        if not hold:self.gate.set()
        self.written=0;self.consumed=0;self.peak_pending=0;self.finished=False;self.overflow=None;self.failure=None
        self.text_hash=hashlib.sha256();self.text_bytes=0;self.chunks=0;self.model_ends=0;self.last_epoch=0
        self.thread=threading.Thread(target=self._consume,daemon=True);self.thread.start()

    def offer(self, event):
        """向磁盘交付完整的单次模型事件。@param event 真实原生事件。@return 是否进入消费流。"""
        raw=(json.dumps(event,ensure_ascii=False)+'\n').encode()
        with self.condition:
            if self.overflow:return False
            if self.written-self.consumed+len(raw)>self.pending_limit or self.written+len(raw)>self.total_limit:
                self.overflow={'code':'consumer_backlog_limit' if self.written-self.consumed+len(raw)>self.pending_limit else 'delivery_file_limit',
                    'ns':time.monotonic_ns(),'event':event['event'],'receive_epoch':event.get('receive_epoch'),
                    'offered_bytes':len(raw),'written':self.written,'consumed':self.consumed}
                self.condition.notify_all();return False
            count=self.writer.write(raw)
            if count!=len(raw):raise OSError('研究暂存文件出现部分写入')
            self.written+=count;self.peak_pending=max(self.peak_pending,self.written-self.consumed)
            self.condition.notify_all();return True

    def _consume(self):
        """单独消费已确认完整写入的事件，并保留逻辑正文摘要。@return 无返回值。"""
        try:
            self.gate.wait()
            with self.path.open('rb',buffering=0) as stream:
                while True:
                    with self.condition:
                        while self.consumed==self.written and not self.finished:self.condition.wait(0.05)
                        if self.consumed==self.written and self.finished:break
                    raw=stream.readline();event=json.loads(raw)
                    require(event['generation']==self.generation and event['request_id']==self.job)
                    if event['event']=='model_start':self.last_epoch=0
                    if event['event']=='response_chunk':
                        require(event['receive_epoch']==self.last_epoch+1);self.last_epoch=event['receive_epoch']
                        value=event['chunk']['DeltaText'].encode();self.text_hash.update(value);self.text_bytes+=len(value);self.chunks+=1
                    if event['event']=='model_end':self.model_ends+=1
                    if self.delay:time.sleep(self.delay)
                    with self.condition:self.consumed+=len(raw);self.condition.notify_all()
        except Exception as exc:self.failure={'type':type(exc).__name__,'message':str(exc)}
        finally:self.done.set()

    def finish(self):
        """原生收口后消费暂存前缀并等待独立消费线程。@return 无返回值。"""
        with self.condition:self.finished=True;self.condition.notify_all()
        self.gate.set()
        if not self.done.wait(30):raise TimeoutError('研究消费线程收口超时')
        self.writer.close()

    def summary(self):
        """汇总实际交付与预算。@return 完整计数。"""
        return {'written':self.written,'consumed':self.consumed,'peak_pending':self.peak_pending,
            'pending_limit':self.pending_limit,'total_limit':self.total_limit,'overflow':self.overflow,'failure':self.failure,
            'text_bytes':self.text_bytes,'text_sha256':self.text_hash.hexdigest(),'chunks':self.chunks,'model_ends':self.model_ends}


class NativeJob:
    """只保留一个活动作业的原生调用、正文摘要和所有权。"""

    def __init__(self, job, spool):
        """绑定独立交付通道。@param job 作业。@param spool 暂存。@return 无返回值。"""
        self.job=job;self.spool=spool;self.calls=0;self.ends=0;self.chunks=0;self.text_bytes=0;self.text_hash=hashlib.sha256()
        self.context=None;self.first_ns=None;self.end_ns=None;self.native_error=None;self.failure=None;self.last_epoch=0
        self.call_id=None;self.ended=threading.Event()

    def observe(self, event):
        """核对当前真实原生调用并向独立暂存交付。@param event 源事件。@return 无返回值。"""
        if event['event']=='model_start':
            require(self.calls==self.ends)
            self.calls+=1;self.context=event['native_context'];self.first_ns=self.first_ns or event['ns']
            self.call_id=event['call_id'];self.last_epoch=0;self.ended.clear()
        elif event['event']=='response_chunk':
            require(event['call_id']==self.call_id)
            require(event['receive_epoch']==self.last_epoch+1);self.last_epoch=event['receive_epoch']
            value=event['chunk']['DeltaText'].encode();self.text_hash.update(value);self.text_bytes+=len(value);self.chunks+=1
        elif event['event']=='model_end':
            self.ends+=1;self.end_ns=event['ns']
            # OAuth的Receive只确认EOF；错误结果由官方控制RPC独立确认，未知标记保持原义。
            if event['native_error_present'] is not None:self.native_error=bool(self.native_error or event['native_error_present'])
        if event['event'] in ['model_start','response_chunk','model_end']:self.spool.offer(event)
        if event['event']=='model_end':self.ended.set()

    def summary(self):
        """返回当前源流的有界统计。@return 摘要。"""
        return {'job':self.job,'calls':self.calls,'ends':self.ends,'chunks':self.chunks,'text_bytes':self.text_bytes,
            'text_sha256':self.text_hash.hexdigest(),'native_context':self.context,'first_ns':self.first_ns,'end_ns':self.end_ns,
            'native_error':self.native_error,'delivery':self.spool.summary()}


class DrainBridge(ResearchBridge):
    """保持一个独立读取器，把消费延迟与原生事件读取分开。"""

    def __init__(self, folder, reclaim=True):
        """创建固定后端及有界诊断窗口。@param folder 独立HOME。@param reclaim 冷页。@return 无返回值。"""
        super().__init__(folder,'candidate-unified',reclaim,None)
        self.native_events=EventWindow();self.active_job=None;self.reader_stop=threading.Event();self.reader=None;self.reader_error=None
        self.source_events=0;self.errors=[];self.max_partial_bytes=0

    def _emit(self, event):
        """完整归档源事件，业务流交付另由磁盘游标消费。@param event 原始事件。@return 无返回值。"""
        self.events.write(json.dumps(event,ensure_ascii=False)+'\n');self.events.flush();self.source_events+=1
        if event['event']=='observer_error':self.errors.append(event)
        if event.get('request_id'):
            if self.active_job is None or event['request_id']!=self.active_job.job:
                raise RuntimeError('源事件活动作业归属冲突')
            self.active_job.observe(event)

    def start_reader(self):
        """完成真实初始化后启动唯一读取线程。@return 无返回值。"""
        def run():
            """持续排空原生管道并记录读取失败。@return 无返回值。"""
            try:
                while not self.reader_stop.is_set():
                    self._pump(0.01)
                    self.max_partial_bytes=max(self.max_partial_bytes,sum(map(len,self.partial.values())))
            except Exception as exc:self.reader_error={'type':type(exc).__name__,'message':str(exc)}
        self.reader=threading.Thread(target=run,daemon=True);self.reader.start()

    def stop_reader(self):
        """关闭工作进程前交还唯一读取所有权。@return 无返回值。"""
        self.reader_stop.set()
        if self.reader:self.reader.join(timeout=2)
        if self.reader and self.reader.is_alive():raise RuntimeError('独立读取器退出超时')

    def control_summary(self):
        """输出自有控制层的实际保留计数。@return 窗口及源归档统计。"""
        return {'source_events':self.source_events,'window_events':len(self.native_events),'window_json_bytes':self.native_events.bytes,
            'window_peak_json_bytes':self.native_events.peak,'window_evicted':self.native_events.evicted,
            'window_limit_json_bytes':self.native_events.byte_limit,'window_limit_events':self.native_events.event_limit,
            'partial_buffer_peak_observed':self.max_partial_bytes,'reader_error':self.reader_error,'observer_errors':self.errors}
