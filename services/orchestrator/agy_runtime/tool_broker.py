"""把真实原生MCP调用绑定到私有NDJSON请求，外部执行方回填文本结果。"""
import copy
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import secrets
import threading
import time
import uuid
from .contract import InputError, fields, text


class Broker:
    """持有单次请求的工具定义、真实原生调用与待交还结果。"""

    def __init__(self, owner, scope, folder):
        """创建只监听回环的私有工具端点。@param owner 内核。@param scope 归属。@param folder 私有归档。@return 无返回值。"""
        self.owner=owner;self.scope=scope;self.folder=folder;self.condition=threading.Condition();self.pending={};self.closed=False;self.failure=None
        self.gemini_results=None;self.trajectory_id=None
        self.definitions=copy.deepcopy(scope.value['tools']);self.path='/mcp/'+secrets.token_urlsafe(32);self.archive_lock=threading.Lock()
        self.server=ThreadingHTTPServer(('127.0.0.1',0),Handler);self.server.broker=self;self.server.daemon_threads=True
        self.url='http://127.0.0.1:'+str(self.server.server_port)+self.path
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()

    def record(self, row):
        """追加完整MCP往返与归属证据。@param row 原始记录。@return 无返回值。"""
        if not self.owner.cfg['capture_enabled']:
            return
        with self.archive_lock:
            with (self.folder/'mcp.ndjson').open('a') as stream:stream.write(json.dumps({'ns':time.monotonic_ns(),**row},ensure_ascii=False)+'\n')

    def configure(self, cfg):
        """根据已核对原生字段接入本请求工具。@param cfg 原生配置。@return 无返回值。"""
        name='caller_'+str(self.scope.seq)
        spec={'serverName':name,'serverUrl':self.url,'skipToolNamePrefix':True,'skipToolDescriptionPrefix':True,'forceAllToolsEager':True,'disableStandaloneSse':True}
        planner=cfg['plannerConfig'];planner['customizationConfig']={'mcpServers':[spec],'skipToolNamePrefix':True,'skipToolDescriptionPrefix':True}
        mixin=planner['declarativeMixinConfig'];mixin['providers']=[{'name':name,'url':self.url,'protocol':'PROTOCOL_MCP'}]
        mixin['tools']=[{'name':d['name'],'providerName':name} for d in self.definitions]
        planner['toolConfig']['descriptionOverrideMap']={'toolOverrides':{d['name']:{'argumentValueOverrides':{'toolSummary':{'omit':True}}} for d in self.definitions}}

    def invoke(self, params):
        """从真实MCP元数据核对轨迹并交给外部执行方。@param params 原生参数。@return MCP结果。"""
        scope=self.scope;metadata=params.get('_meta',{})
        if self.closed or scope.cancel.is_set():raise RuntimeError('tool_request_cancelled')
        if metadata.get('antigravity.google/conversation_id')!=scope.root:raise RuntimeError('tool_native_root_identity')
        token=metadata.get('progressToken');trajectory_id,index=text(token).rsplit(':',1)
        current=scope.worker.call('GetCascadeTrajectory',{'cascadeId':scope.root},scope)
        if current['status']!=200:raise RuntimeError('tool_native_trajectory_unavailable')
        trajectory=current['response']['trajectory']
        if trajectory['trajectoryId']!=trajectory_id:raise RuntimeError('tool_native_trajectory_identity')
        step=trajectory['steps'][int(index)];call=step['metadata']['toolCall']
        args=params.get('arguments',{})
        if call['name']!=params.get('name') or json.loads(call['argumentsJson'])!=args:raise RuntimeError('tool_native_call_identity')
        if params['name'] not in {d['name'] for d in self.definitions}:raise RuntimeError('tool_not_declared')
        self.trajectory_id=trajectory_id
        if scope.value.get('request_format')=='gemini':
            scope.native_tool_calls=copy.deepcopy(next((s['plannerResponse']['toolCalls'] for s in reversed(trajectory['steps'][:int(index)]) if s.get('plannerResponse',{}).get('toolCalls')),None))
            if scope.native_tool_calls is None:raise RuntimeError('tool_native_planner_missing')
        ident=call['id'];execution=str(uuid.uuid4());pending={'native_call':copy.deepcopy(call),'execution_id':execution,'result':None,'token':token,'step_index':int(index)}
        with self.condition:
            if ident in self.pending:raise RuntimeError('duplicate_native_tool_call')
            self.pending[ident]=pending
            if scope.value.get('request_format')=='gemini':
                if self.gemini_results is not None:pending['result']=self.gemini_result(ident)
                self.owner.emit('tool_waiting',**scope.identity(),tool_call_id=ident,tool_execution_id=execution,
                    native_cascade_id=scope.root,native_trajectory_id=trajectory_id)
                scope.tool_wait_ready.set()
            else:
                self.owner.emit('tool_call',**scope.identity(),tool_call_id=ident,tool_execution_id=execution,name=params['name'],arguments=args,
                    thinking_signature=call.get('thinkingSignature'),native_trajectory_id=trajectory_id,native_step_index=int(index),native_progress_token=token)
            while pending['result'] is None and not self.closed and not scope.cancel.is_set():self.condition.wait(.1)
            if pending['result'] is None:
                self.owner.emit('tool_aborted',**scope.identity(),tool_call_id=ident,tool_execution_id=execution)
                raise RuntimeError('tool_request_cancelled')
            return pending['result']

    def gemini_result(self, identifier):
        """构造来自真实调用方结果的 MCP 响应。@param identifier 已核对原生调用 ID。@return MCP 结果。"""
        value=self.gemini_results[identifier]
        result_text=value['content'] if set(value)=={'content'} and isinstance(value['content'],str) else json.dumps(value,ensure_ascii=False,separators=(',',':'))
        return {'content':[{'type':'text','text':result_text}],'structuredContent':copy.deepcopy(value),'isError':False}

    def complete_gemini(self, values):
        """为已经绑定的工具轮缓存一次真实回填。@param values 按原调用顺序排列的结果。@return 无。"""
        with self.condition:
            if self.closed or self.scope.cancel.is_set() or self.gemini_results is not None:raise InputError('gemini_tool_turn_closed')
            # 发布工具轮时已逐项核对原生和公开调用的顺序、名称及参数。
            identities=self.scope.tool_native_ids
            if len(identities)!=len(values) or not self.pending.keys()<=set(identities):
                raise InputError('gemini_pending_results_mismatch')
            self.gemini_results=copy.deepcopy(dict(zip(identities,values)))
            self.record({'gemini_results':values,'request_id':self.scope.value['request_id']})
            for identifier,item in self.pending.items():item['result']=self.gemini_result(identifier)
            self.condition.notify_all()

    def complete(self, raw):
        """只接纳完整匹配且尚待回填的结果。@param raw 公开协议。@return 是否接纳。"""
        fields(raw,{'schema_version','type','request_id','request_seq','generation','tool_call_id','tool_execution_id','text','is_error'})
        result=text(raw.get('text'));is_error=raw.get('is_error',False)
        if type(is_error) is not bool:raise InputError('invalid_tool_error_flag')
        with self.condition:
            entry=self.pending.get(raw.get('tool_call_id'))
            matched=bool(not self.closed and not self.scope.cancel.is_set() and type(raw.get('request_seq')) is int and all(raw.get(k)==v for k,v in self.scope.identity().items())
                and entry and raw.get('tool_execution_id')==entry['execution_id'] and entry['result'] is None)
            if matched:entry['result']={'content':[{'type':'text','text':result}],'isError':is_error}
            self.owner.emit('tool_result_ack',request_id=raw.get('request_id'),request_seq=raw.get('request_seq'),generation=raw.get('generation'),tool_call_id=raw.get('tool_call_id'),tool_execution_id=raw.get('tool_execution_id'),accepted=matched)
            self.condition.notify_all();return matched

    def close(self):
        """唤醒等待调用并收回私有端口。@return 无返回值。"""
        with self.condition:self.closed=True;self.condition.notify_all()
        self.server.shutdown();self.server.server_close();self.thread.join(2)


class Handler(BaseHTTPRequestHandler):
    """接收由固定原生运行时发出的MCP HTTP请求。"""

    def do_POST(self):
        """处理初始化、工具列表及真实工具调用。@return 无返回值。"""
        broker=self.server.broker
        if self.path!=broker.path:self.send_error(404);return
        request=json.loads(self.rfile.read(int(self.headers.get('content-length',0))));broker.record({'request':request})
        if 'id' not in request:
            self.send_response(202);self.send_header('Content-Length','0');self.end_headers();return
        try:
            method=request.get('method')
            if method=='initialize':result={'protocolVersion':request['params']['protocolVersion'],'capabilities':{'tools':{}},'serverInfo':{'name':'agy-caller-tools','version':'1'}}
            elif method=='tools/list':result={'tools':[{'name':d['name'],'description':d.get('description',''),'inputSchema':d['input_schema']} for d in broker.definitions]}
            elif method=='tools/call':result=broker.invoke(request['params'])
            elif method=='ping':result={}
            else:raise RuntimeError('unsupported_mcp_method')
            response={'jsonrpc':'2.0','id':request['id'],'result':result}
        except Exception as exc:
            code=str(exc) if isinstance(exc,RuntimeError) else type(exc).__name__
            if method=='tools/call' and code!='tool_request_cancelled':broker.failure=code
            response={'jsonrpc':'2.0','id':request['id'],'error':{'code':-32601 if code=='unsupported_mcp_method' else -32603,'message':code}}
        broker.record({'response':response});raw=json.dumps(response,ensure_ascii=False).encode()
        try:
            self.send_response(200);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
        except OSError as exc:broker.record({'write_error':type(exc).__name__})

    def do_GET(self):
        """本地通道采用POST响应。@return 无返回值。"""
        self.send_response(405);self.send_header('Content-Length','0');self.end_headers()

    def log_message(self, fmt, *args):
        """请求及响应归档由Broker负责。@param fmt 模板。@param args 参数。@return 无返回值。"""
        pass
