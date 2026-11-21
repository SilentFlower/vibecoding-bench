"""在断网容器中连接真实网关、发送器、固定AGY原版和本地TLS合成上游。"""
import argparse
import base64
import copy
import gzip
import io
import hashlib
import json
import os
import random
import shutil
import signal
import sqlite3
import ssl
import struct
import subprocess
import tempfile
import threading
import time
import uuid
import wave
import zlib
from concurrent.futures import ThreadPoolExecutor
from http.client import HTTPConnection
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from source_layout import source_path

ENVIRONMENT='a'*32
SECRET='synthetic-internal-proof-at-least-32-bytes'
MODEL='gemini-3.1-pro-preview'
SHARED_MODELS = {MODEL: 'MODEL_PLACEHOLDER_M36', 'gemini-3.8-flash-low': 'MODEL_PLACEHOLDER_M320'}
MESSAGES_LOW_MODEL = MODEL + '-low'
SOURCE_SHA='39816d49d5ab92229952987225c23ea3fed7580699dcb4a444e0388e0ac1ce43'
SCHEMA_TOOL_ARGS = {'x': 1, 'action': 'query', 'where': [['count', '>=', 7], ['ready', '==', True]]}
SEARCH_QUERY = 'IANA Example Domains'
SEARCH_URL = 'https://www.iana.org/help/example-domains'
SEARCH_REDIRECT = 'https://vertexaisearch.cloud.google.com/grounding-api-redirect/fixture'
SEARCH_REDIRECT_TITLE = 'IANA Redirect Fixture'
MESSAGES_READ_PATH = '/fixture/large.txt'
CUT_OFF_REWRITE = 'Your response above was cut off mid-stream and only your next message is delivered. Write the complete response again from the start — no apology, no mention of the cut-off.'


def require(condition, message):
    """校验隔离验收条件。@param condition 实际条件。@param message 固定说明。@return 无。"""
    if not condition:
        raise ValueError(message)


def sse_frames(raw):
    """读取隔离回包事件。@param raw SSE 字节。@return 原顺序的事件。"""
    return [json.loads(line[6:]) for line in raw.splitlines() if line.startswith(b'data: ')]


class Upstream(BaseHTTPRequestHandler):
    """只处理固定原版经TLS实际发送的合成请求。"""

    protocol_version='HTTP/1.1'
    calls=[]
    requests=[]
    wire=[]
    cancelled=threading.Event()
    png_support=False
    model_catalog_host=None
    model_mappings = {MODEL: SHARED_MODELS[MODEL]}
    held_requests = {}
    messages_search = False
    system_reminder = False
    search_held = threading.Event()
    search_release = threading.Event()
    receipt_side_barrier = threading.Barrier(2)

    def log_message(self,*args):
        """避免将请求头体输出到公共日志。@param args 日志参数。@return 无。"""

    def do_POST(self):
        """返回合成初始化响应或真实SSE线字节。@return 无。"""
        raw=bytearray()
        if self.headers.get('transfer-encoding','').lower()=='chunked':
            while True:
                size=int(self.rfile.readline().split(b';',1)[0],16)
                require(len(raw)+size<=67108864,'合成上游请求超过验证预算')
                if not size:
                    while self.rfile.readline()!=b'\r\n':pass
                    break
                raw.extend(self.rfile.read(size));require(self.rfile.read(2)==b'\r\n','chunked请求边界错误')
        else:
            size=int(self.headers.get('content-length','0'))
            require(0<=size<=67108864,'合成上游请求超过验证预算')
            raw.extend(self.rfile.read(size))
        entity_sha256=hashlib.sha256(raw).hexdigest()
        if self.headers.get('content-encoding')=='gzip':
            raw=gzip.decompress(raw)
        self.wire.append({'path':self.path,'content_type':self.headers.get('content-type'),'encoding':self.headers.get('content-encoding'),
            'bytes':len(raw),'prefix':bytes(raw[:4]).hex()})
        Path('/state/wire.json').write_text(json.dumps(self.wire))
        if self.path=='/log' and self.headers.get('content-type')=='application/octet-stream':
            # Clearcut使用独立protobuf上传；空成功响应使真实业务队列按官方逻辑排空。
            self.send_response(200);self.send_header('Content-Length','0');self.end_headers();return
        body=json.loads(raw) if raw else {}
        record={'path':self.path,'body':body,'authorization':self.headers.get('authorization')}
        self.requests.append(record)
        Path('/state/upstream.json').write_text(json.dumps(self.requests))
        if self.messages_search and ':generateContent' in self.path:
            request = body['request']
            require(any('googleSearch' in tool for tool in request['tools']), 'AGY 搜索没有调用原版的联网工具')
            text = request['contents'][0]['parts'][0]['text']
            if text=='Cancelled search fixture':
                self.search_held.set()
                self.search_release.wait(20)
                self.send_response(503);self.send_header('content-length','0');self.end_headers()
                return
            candidate = {'content': {'role':'model','parts':[{'text':'IANA explains reserved example domains.'}]},
                'index':0, 'finishReason':'STOP', 'groundingMetadata': {'webSearchQueries':[text],
                    'groundingChunks':[{'web':{'uri':SEARCH_URL,'title':SEARCH_QUERY}},
                        {'web':{'uri':SEARCH_REDIRECT,'title':SEARCH_REDIRECT_TITLE,'domain':'www.iana.org'}}],
                    'groundingSupports':[{'segment':{'startIndex':0,'endIndex':37},'groundingChunkIndices':[0,1]}]}}
            if text == 'Empty search fixture':
                candidate['groundingMetadata']['groundingChunks'] = []
                candidate['groundingMetadata']['groundingSupports'] = []
            envelope = {'response':{'candidates':[candidate]}} if text != 'Failed search fixture' else {'response':{}}
            raw = json.dumps(envelope).encode()
            self.send_response(200);self.send_header('content-type','application/json')
            self.send_header('content-length',str(len(raw)));self.end_headers();self.wfile.write(raw)
            return
        if ':streamGenerateContent' in self.path:
            record['request_headers']={name.lower():value for name,value in self.headers.items()
                if name.lower() in ('host','content-type','content-length','content-encoding','transfer-encoding',
                    'accept','accept-encoding','user-agent','expect','x-goog-api-client')}
            record['request_header_names']=sorted({name.lower() for name in self.headers.keys()})
            record['proxy_headers']=getattr(self.connection,'request_header_preview',{})
            record['entity_sha256']=entity_sha256
            self.calls.append(record)
            encoded=json.dumps(body)
            receipt_side=next((f'AGY_RECEIPT_SIDE_{index}' for index in range(2)
                if f'AGY_RECEIPT_SIDE_{index}' in encoded),None)
            if receipt_side:
                self.receipt_side_barrier.wait(timeout=8)
            for marker, (entered, release) in self.held_requests.items():
                if marker in encoded:
                    entered.set()
                    require(release.wait(90), '隔离容量实验未释放请求')
                    break
            if 'TLS_SYNTHETIC_USAGE_EOF' in encoded:
                self.usage_then_eof(truncated='TLS_SYNTHETIC_EOF_SHORT' in encoded,
                    with_text='TLS_SYNTHETIC_EOF_TEXT' in encoded)
                return
            recover_once = 'AGY_RECEIPT_FAIL_ONCE' in encoded and 'functionResponse' in encoded
            if 'AGY_RECEIPT_FAIL' in encoded and 'functionResponse' in encoded:
                seen = sum('AGY_RECEIPT_FAIL_ONCE' in json.dumps(record['body'])
                    and 'functionResponse' in json.dumps(record['body']) for record in self.calls)
                if not recover_once or seen==1:
                    self.usage_then_eof(truncated=True,with_text=False)
                    return
            rejected=next((result for marker,result in (
                ('TLS_SYNTHETIC_UPSTREAM_UNAVAILABLE',(503,'UNAVAILABLE')),
                ('TLS_SYNTHETIC_UPSTREAM_QUOTA',(429,'RESOURCE_EXHAUSTED')),
            ) if marker in encoded),None)
            if rejected:
                status,reason=rejected
                error=json.dumps({'error':{'code':status,'status':reason,'message':'private synthetic detail'}}).encode()
                self.send_response(status)
                self.send_header('Content-Type','application/json')
                self.send_header('Content-Length',str(len(error)))
                self.end_headers()
                self.wfile.write(error)
                return
            tools=body.get('request',body).get('tools',[])
            results='functionResponse' in encoded
            tool='TLS_SYNTHETIC_TOOL' in encoded and not results
            receipt_result_count=None
            if any(marker in encoded for marker in ('AGY_RECEIPT_OWNERSHIP','AGY_RECEIPT_FAIL','AGY_RECEIPT_DROP')) and not receipt_side:
                receipt_result_count=sum('functionResponse' in part for turn in body['request']['contents'] for part in turn['parts'])
                tool=receipt_result_count<2 and not recover_once and not ('AGY_RECEIPT_DROP' in encoded and results)
            deadline_chain='TLS_SYNTHETIC_LONG_TOOL_CHAIN' in encoded
            if deadline_chain:
                returned=sum('functionResponse' in part for content in body['request']['contents']
                    for part in content['parts'])
                tool=returned<6
            parallel_chain='TLS_SYNTHETIC_TOOL_PARALLEL_CHAIN' in encoded
            replay_chain='TLS_SYNTHETIC_TOOL_REPLAY' in encoded
            if parallel_chain or replay_chain:
                returned=sum('functionResponse' in part for content in body['request']['contents']
                    for part in content['parts'])
                count=({0:1,1:1,2:4,6:2} if replay_chain else {0:6,6:4,10:3}).get(returned,0)
                tool=count>0
            cancel='TLS_SYNTHETIC_CANCEL' in encoded
            repeated='TLS_SYNTHETIC_REPEAT' in encoded
            truncated='TLS_SYNTHETIC_TRUNCATED' in encoded
            capacity='TLS_SYNTHETIC_CAPACITY' in encoded
            failed_tool='TLS_SYNTHETIC_TOOL_THEN_ERROR' in encoded
            self.send_response(200)
            self.send_header('Content-Type','text/event-stream')
            self.send_header('Connection','close')
            self.end_headers()
            self.close_connection=True
            tool_id='call_'+('a1b2'*8) if self.png_support else 'synthetic-call'
            if self.system_reminder:
                tool_id = f'call_{len(self.calls):032x}'
            if deadline_chain:tool_id=f'call_{returned+1:032x}'
            if receipt_result_count is not None:tool_id=f'call_{receipt_result_count+1:032x}'
            arguments = SCHEMA_TOOL_ARGS if 'TLS_SYNTHETIC_TOOL_SCHEMA' in encoded else {'x':1}
            part={'functionCall':{'name':'synthetic_tool','args':arguments,'id':tool_id},'thoughtSignature':'c3ludGhldGljLXNpZw=='} if tool else {'text':receipt_side or '本地TLS回复'}
            frames=[{'candidates':[{'index':0,'content':{'role':'model','parts':[part]}}]}]
            if self.messages_search:
                if 'Messages image response fixture' in encoded:
                    image = {'inlineData': {'mimeType': 'image/png', 'data': fixture_png((19, 73, 211))}}
                    frames[0]['candidates'][0]['content']['parts'] = [{'text': '图片前文'}, image, {'text': '图片后文'}]
                names = {entry['name'] for tool in tools for entry in tool.get('functionDeclarations', [])}
                if 'search_web' in names:
                    require(names <= {'search_web','manage_task'}, '独立搜索继承了普通执行工具')
                    if not results and len(body['request']['contents']) == 1:
                        prompt = body['request']['contents'][0]['parts'][0]['text']
                        query = json.loads(prompt.split('</USER_REQUEST>',1)[0].splitlines()[-1])
                        parts = [{'functionCall':{'name':'search_web','args':{'query':query},'id':'call_search'}}]
                        if query=='Tool isolation fixture':
                            parts = [{'functionCall':{'name':'run_command','args':{
                                'CommandLine':'touch /state/forbidden-search-probe','Cwd':'/state'},'id':'call_denied'}}]
                    else:
                        parts = [{'text':'模型总结中的伪造网址 https://irrelevant.example.invalid'}]
                    frames = [{'candidates':[{'index':0,'content':{'role':'model','parts':parts}}]}]
                elif 'WebSearch' in names and 'Messages search fixture' in encoded and not results:
                    parts = [{'functionCall':{'name':'WebSearch','args':{'query':SEARCH_QUERY},'id':'call_msg_search'},
                        'thoughtSignature':'c3ludGhldGljLXNpZw=='}]
                    if 'mcp__fixture__read_item' in names:
                        parts.extend({'functionCall':{'name':'mcp__fixture__read_item','args':{'n':n},'id':f'call_msg_read_{n}'}} for n in (1,2,3))
                    frames = [{'candidates':[{'index':0,'content':{'role':'model','parts':parts}}]}]
                elif 'Read' in names and 'Messages Read truncation fixture' in encoded and not results:
                    part = {'functionCall': {'name': 'Read', 'args': {'file_path': MESSAGES_READ_PATH},
                        'id': 'call_msg_truncated_read'}}
                    frames[0]['candidates'][0]['content']['parts'] = [part]
            if tool and (parallel_chain or replay_chain):
                part['functionCall']['id']=f'call_{returned+1:032x}'
                part['functionCall']['args']={'x':returned+1}
                if replay_chain and count==4:
                    part['functionCall']['name']='synthetic_lookup'
                parts=[part]+[{'functionCall':{'name':'synthetic_lookup' if parallel_chain and i==count-1 else 'synthetic_tool',
                    'args':{'x':returned+i+1},'id':f'call_{returned+i+1:032x}'}}
                    for i in range(1,count)]
                frames=[
                    {'candidates':[{'index':0,'content':{'role':'model','parts':batch}}]}
                    for batch in ([{'text':'准备工具'}],parts[:2],parts[2:]) if batch
                ]
            elif tool and 'TLS_SYNTHETIC_TOOL_PARALLEL' in encoded:
                frames[0]['candidates'][0]['content']['parts'].append(
                    {'functionCall':{'name':'synthetic_tool','args':{'x':2}}})
            if 'AGY_RELIABILITY_LONG' in encoded:
                frames=[{'candidates':[{'index':0,'content':{'role':'model','parts':[{'text':'深思考已开始','thought':True}]}}]},
                    {'candidates':[{'index':0,'content':{'role':'model','parts':[{'text':'长生成结束'}]}}]}]
            if not results and 'AGY_RELIABILITY_SEARCH' in encoded:
                frames=[{'candidates':[{'index':0,'content':{'role':'model','parts':[
                    {'functionCall':{'name':'web_search','id':'fixture-search','args':{'query':'合成查询'}}}]}}]}]
            if not results and 'AGY_RELIABILITY_DUPLICATE' in encoded:
                second=1 if 'AGY_RELIABILITY_DUPLICATE_IDENTICAL' in encoded else 2
                frames=[{'candidates':[{'index':0,'content':{'role':'model','parts':[
                    {'functionCall':{'name':'synthetic_tool','id':'fixture-repeat','args':{'x':x}}}]}}]}
                    for x in (1,second)]
            if not results and 'AGY_RELIABILITY_NUMERIC_ID' in encoded:
                frames=[{'candidates':[{'index':0,'content':{'role':'model','parts':[
                    {'functionCall':{'name':'synthetic_tool','id':17,'args':{'x':1}}}]}}]}]
            if repeated:frames*=64
            if capacity:
                error={'error':{'code':429,'status':'RESOURCE_EXHAUSTED','message':'private synthetic detail'}}
                frames=[frames[0],error] if 'TLS_SYNTHETIC_CAPACITY_AFTER_OUTPUT' in encoded else [error]
            if failed_tool:
                frames.append({'error':{'code':503,'status':'UNAVAILABLE'}})
            if not cancel and not truncated and not capacity and not failed_tool:
                frames.append({'candidates':[{'index':0,'content':{'role':'model','parts':[{'text':''}]},'finishReason':'STOP'}],
                    'usageMetadata':{'promptTokenCount':3,'candidatesTokenCount':4,'totalTokenCount':7,'cachedContentTokenCount':2,'thoughtsTokenCount':1}})
            elif cancel:
                frames*=200
            try:
                native=None
                if repeated:
                    value=Request('http://127.0.0.1:8091/internal/status',headers={'authorization':'Bearer '+SECRET})
                    with urlopen(value,timeout=5) as response:state=json.load(response)
                    native=next((process['native']['pid'] for process in state['agy']['processes'] if process.get('native')),None)
                    require(native is not None,'重复帧实验缺少真实原生PID')
                for index,frame in enumerate(frames):
                    if native:os.kill(native,signal.SIGURG)
                    envelope=frame if 'error' in frame else {'response':frame}
                    self.wfile.write(('data: '+json.dumps(envelope,ensure_ascii=False)+'\n\n').encode())
                    self.wfile.flush()
                    if 'AGY_RELIABILITY_LONG' in encoded and index==0:time.sleep(121)
                    if 'AGY_RECEIPT_DROP' in encoded and results and index==0:
                        time.sleep(5 if 'RECEIPT_GATE_CUTOVER' in encoded else .8)
                    time.sleep(.1 if cancel else .02)
            except OSError:
                if cancel:
                    self.cancelled.set()
            return
        if ':loadCodeAssist' in self.path:
            value={'cloudaicompanionProject':'synthetic-project','currentTier':{'id':'standard-tier','name':'Standard'}}
        elif ':fetchAvailableModels' in self.path:
            value = {'models': {name: {'model': native, 'displayName': name} for name, native in self.model_mappings.items()}}
            if self.messages_search:
                value.update(defaultAgentModelId=MODEL, webSearchModelIds=[MODEL], agentModelSorts=[{
                    'displayName':'Gemini','groups':[{'displayName':'Gemini','modelIds':[MODEL]}]}])
                value['models'][MODEL]['supportedMimeTypes'] = {'image/png':True}
            if self.png_support:
                value['models'][MODEL]['supportedMimeTypes']={mime:True for mime in ('image/png','image/jpeg','image/gif','audio/wav')}
                value['defaultAgentModelId']=MODEL
            if self.model_catalog_host and self.headers.get('host')!=self.model_catalog_host:
                value={'models':{}}
        else:
            value={}
        raw=json.dumps(value).encode()
        self.send_response(200)
        self.send_header('Content-Type','application/json')
        self.send_header('Content-Length',str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def usage_then_eof(self, *, truncated: bool, with_text: bool):
        """交付用量并按指定方式结束实际 HTTP 响应。@param truncated 截断分块。@param with_text 已交付可见文本。@return 无。"""
        frame={'usageMetadata':{'promptTokenCount':14,'cachedContentTokenCount':9,'totalTokenCount':14}}
        if with_text:
            frame['candidates']=[{'content':{'role':'model','parts':[{'text':'已交付的正文'}]}}]
        data=('data: '+json.dumps({'response':frame},ensure_ascii=False)+'\n\n').encode()
        self.send_response(200)
        self.send_header('Content-Type','text/event-stream')
        self.send_header('Transfer-Encoding','chunked')
        self.send_header('Connection','close')
        self.end_headers()
        self.close_connection=True
        self.wfile.write(('%x\r\n'%len(data)).encode()+data+b'\r\n')
        self.wfile.write(b'200\r\ndata: {' if truncated else b'0\r\n\r\n')
        self.wfile.flush()

    def do_GET(self):
        """提供固定原版启动所需的合成身份，禁止读取真实账号。@return 无。"""
        require(self.path=='/oauth2/v2/userinfo','原生GET偏离合成身份入口')
        raw=json.dumps({'id':'synthetic-user','email':'synthetic@example.test','verified_email':True}).encode()
        self.send_response(200);self.send_header('Content-Type','application/json')
        self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)


class Proxy(BaseHTTPRequestHandler):
    """将允许的官方目标域终止到隔离TLS夹具，禁止建立外部连接。"""

    def log_message(self,*args):
        """保持连接日志脱敏。@param args 日志参数。@return 无。"""

    def do_CONNECT(self):
        """保留目标主机名与证书校验，在回环处理TLS。@return 无。"""
        host,port=self.path.rsplit(':',1)
        require(port=='443' and host in {'cloudcode-pa.googleapis.com','daily-cloudcode-pa.googleapis.com',
            'oauth2.googleapis.com','play.googleapis.com','aicode.googleapis.com','www.googleapis.com'},'原生请求偏离本地夹具允许的目标')
        self.send_response(200,'Connection Established')
        self.end_headers()
        self.wfile.flush()
        with self.server.context.wrap_socket(self.connection,server_side=True) as connection:
            connection.request_header_preview={name.lower():value for name,value in self.headers.items()
                if name.lower() in ('host','user-agent','proxy-connection')}
            Upstream(connection,self.client_address,self.server)
        self.close_connection=True


class Binding(BaseHTTPRequestHandler):
    """复用真实网关传输准备边界，返回唯一合成环境。"""
    continuation_mode = 'claim'
    long_generation = False
    hold_preparation = None

    def log_message(self,*args):
        """保持私有证明不进入日志。@param args 日志参数。@return 无。"""

    def do_GET(self):
        """返回真实发送器的固定绑定或合成请求快照。@return 无。"""
        if self.path=='/internal/v3/transport/1':
            barrier = type(self).hold_preparation
            if barrier is not None:
                type(self).hold_preparation = None
                entered, release = barrier
                entered.set()
                require(release.wait(20), '隔离续轮准备未解除等待')
            host='flower2api-'+hashlib.sha256(b'synthetic').hexdigest()[:12]+'-'+ENVIRONMENT
            value={'account_id':1,'environment_id':ENVIRONMENT,'generation':1,'endpoint':f'http://{host}:8091',
                'secret':SECRET,'release_id':'synthetic-release'}
            if self.long_generation:
                value['agy_generation_seconds']=240
            if self.continuation_mode != 'claim':
                value.update(agy_tool_continuation_protocol=1, agy_tool_continuation_mode=self.continuation_mode)
        else:
            from agy_runtime.capture import read_snapshot
            require(self.headers.get('authorization')=='Bearer '+SECRET,'合成快照鉴权错误')
            route,_,query=self.path.partition('?')
            parts=route.split('/')
            require(len(parts)==6 and parts[1:5]==['internal','v3','native-captures','1']
                and query=='platform=antigravity','合成快照路径错误')
            try:
                value=read_snapshot(Path('/'),1,parts[5])
            except FileNotFoundError:
                self.send_response(404);self.send_header('Content-Length','0');self.end_headers();return
        raw=json.dumps(value).encode()
        self.send_response(200);self.send_header('Content-Length',str(len(raw)));self.end_headers()
        self.wfile.write(raw)

    def do_POST(self):
        """通过产品写入器核对独立入口旁路，不触发模型。@return 无。"""
        from agy_runtime.capture import save_ingress
        require(self.headers.get('authorization')=='Bearer '+SECRET,'入口旁路鉴权错误')
        if self.path.partition('?')[0] == '/internal/v3/agy-environments/1':
            self.send_response(404)
            self.send_header('Content-Length', '0')
            self.end_headers()
            return
        if self.path == '/internal/v3/agy-capacity/1' and Upstream.held_requests:
            self.capacity_edit()
            return
        parts=self.path.split('/')
        require(len(parts)==6 and parts[1:5]==['internal','v3','agy-ingress','1'],'入口旁路路径错误')
        value=json.loads(self.rfile.read(int(self.headers['content-length'])))
        require(value['environment_generation']==1,'入口旁路代次错误')
        save_ingress(Path('/state/capture/api/agy-prepared'),1,parts[5],value['ingress'])
        raw=b'{"state":"saved"}';self.send_response(200);self.send_header('content-length',str(len(raw)));self.end_headers();self.wfile.write(raw)

    def capacity_edit(self):
        """用预留的隔离容器额度检验真实网关和发送器的生效顺序。@return 无。"""
        from runtime_files import atomic_json
        value = json.loads(self.rfile.read(int(self.headers['content-length'])))
        operation = value['operation_id']
        state = Request('http://127.0.0.1:5674/admin/runtime/accounts/1/config?capacity_operation=' + operation,
            headers={'x-api-key': 'synthetic-admin'})
        with urlopen(state, timeout=5) as response:
            account = json.load(response)
        require(account['capacity_edit_active'] is True, '网关没有持有原容量操作')
        phase = value['phase']
        if phase == 'prepare':
            require(account['concurrency'] == value['before'], '网关在资源准备前写入了新额度')
        target = value['target'] if phase == 'prepare' else account['concurrency']
        if phase == 'settle' or target > value['before']:
            path = Path('/state/sender.json')
            config = json.loads(path.read_text())
            config['agy']['max_workers'] = target
            atomic_json(path, config)
            body = {'account_id': 1, 'environment_id': ENVIRONMENT, 'generation': 1, 'max_workers': target}
            control = Request('http://127.0.0.1:8091/internal/agy/capacity', data=json.dumps(body).encode(),
                headers={'authorization': 'Bearer ' + SECRET, 'content-type': 'application/json'})
            with urlopen(control, timeout=10) as response:
                require(json.load(response)['max_workers'] == target, '实际发送器额度不符')
        raw = json.dumps({'ok': True, 'operation_id': operation}).encode()
        self.send_response(200)
        self.send_header('Content-Length', str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)


def homoglyph_cases(database, request, base, wait_idle):
    """对照真实TLS系统段、历史及策略账本，覆盖暖worker和工具下一HTTP。@param database 合成库。@param request 公共调用。@param base Gemini路径。@param wait_idle 实际收口等待。@return 场景名称。"""
    original='ABC system 中文 {x: 3}\nSYSTEM 漢字 😀'
    converted='ΑΒС ѕуѕtеm 中文 {х: 3}\nЅΥЅΤЕΜ 漢字 😀'
    body={'systemInstruction':{'parts':[{'text':'ABC system 中文 {x: 3}'},{'text':'SYSTEM 漢字 😀'}]},
        'contents':[{'role':'user','parts':[{'text':'ABC system 用户'}]},
            {'role':'model','parts':[{'text':'ABC model 历史'}]},
            {'role':'user','parts':[{'text':'ABC next 用户'}]}],
        'generationConfig':{'maxOutputTokens':128}}
    def enabled(value):
        """修改合成账号的真实持久字段。@param value 新开关。@return 无。"""
        with database:
            database.execute('UPDATE accounts SET agy_system_prompt_homoglyph_enabled=? WHERE id=1',(int(value),))
    def check(value,expected,streaming=False,pending=False):
        """验证一次实际提交及其系统段。@param value 输入。@param expected 预期系统文本。@param streaming 是否SSE。@param pending 是否保留工具许可。@return 公共正文和实际请求。"""
        before=len(Upstream.calls)
        status,raw=request(base+('streamGenerateContent?alt=sse' if streaming else 'generateContent'),value)
        require(status==200,'同形体原生场景失败：'+str(status)+' '+raw.decode()[:250])
        if not pending:wait_idle()
        require(len(Upstream.calls)==before+1,'同形体场景实际入口数不符')
        wire=Upstream.calls[-1]['body']['request']
        require(''.join(part.get('text','') for part in wire['systemInstruction']['parts'])==expected,'实际TLS系统文本转换边界错误')
        return raw,wire
    def native_pid():
        """读取现有worker的实际PID，证明开关变化保持暖进程。@return 原生PID。"""
        value=Request('http://127.0.0.1:8091/internal/status',headers={'authorization':'Bearer '+SECRET})
        with urlopen(value,timeout=5) as response:state=json.load(response)
        return state['agy']['processes'][0]['native']['pid']
    enabled(False)
    _,off=check(body,original);pid=native_pid()
    enabled(True)
    raw,on=check(body,converted)
    require(off['contents']==on['contents'],'系统策略改写了用户或模型历史')
    require(native_pid()==pid,'切换策略重建了暖worker')
    usage=json.loads(raw)['usageMetadata']
    require(usage['cachedContentTokenCount']==2 and usage['thoughtsTokenCount']==1,'策略改写了源缓存或思考用量')
    _,stream=check(body,converted,True)
    require(stream['contents']==off['contents'],'SSE策略改写了历史')
    already=copy.deepcopy(body);already['systemInstruction']={'parts':[{'text':converted}]}
    check(already,converted)
    enabled(False);check(body,original)
    require(native_pid()==pid,'关闭策略改变原生进程归属')
    large=copy.deepcopy(body);large['systemInstruction']={'parts':[{'text':'ABC 中文 😀\n'*65536}]}
    enabled(True)
    before=len(Upstream.calls)
    status, raw = request(base + 'generateContent', large)
    require(400 <= status < 600 and json.loads(raw)['error']['code'] == status,
        '超过原生上下文预算的系统文本未返回对应错误：' + str(status))
    wait_idle()
    require(len(Upstream.calls)==before,'超过原生上下文预算仍产生模型提交')
    large['systemInstruction']={'parts':[{'text':'ABC 中文 😀\n'*4096}]}
    check(large,'ΑΒС 中文 😀\n'*4096)
    tool=copy.deepcopy(body);tool['contents']=[{'role':'user','parts':[{'text':'TLS_SYNTHETIC_TOOL'}]}]
    tool['tools']=[{'functionDeclarations':[{'name':'synthetic_tool','parameters':{'type':'OBJECT','properties':{'x':{'type':'INTEGER'}}}}]}]
    raw,wire=check(tool,converted,pending=True)
    continuation=copy.deepcopy(tool)
    continuation['contents'] += [json.loads(raw)['candidates'][0]['content'],{'role':'user','parts':[
        {'functionResponse':{'id':'synthetic-call','name':'synthetic_tool','response':{'value':'TLS_SYNTHETIC_RESULT'}}}]}]
    # 原工具已向调用方返回时仍占用许可，关闭开关只影响新的HTTP模型轮。
    enabled(False)
    raw,wire=check(continuation,original)
    require('TLS_SYNTHETIC_RESULT' in json.dumps(wire['contents']) and 'synthetic_tool' in json.dumps(wire['contents']),'工具结果或函数名被替换')
    previews=[json.loads(path.read_text()) for path in Path('/state/capture').rglob('snapshots/*.json')]
    require(any(row.get('system_prompt_policy',{}).get('changed') is True and row.get('representation')=='native_cascade_prompt_sections' for row in previews),'缺少实际处理策略及提交视图来源')
    require(any(json.loads(row['decoded_gemini']['body']).get('systemInstruction')==body['systemInstruction'] for row in previews),'转换前已解码视图丢失')
    return ['固定同形映射实际出站','普通和SSE一致','用户及历史保护','重复经过幂等','预算内大文本及超限零提交','暖worker复用','工具下一HTTP策略','源缓存及思考用量','策略账本与入站视图']


def fixture_png(color):
    """生成可核对的像素输入。@param color RGB 像素。@return Base64 PNG。"""
    def chunk(kind, data):
        return struct.pack('>I', len(data))+kind+data+struct.pack('>I', zlib.crc32(kind+data))
    pixels=(b'\0'+bytes(color)*32)*32
    png=b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',32,32,8,2,0,0,0))
    png+=chunk(b'IDAT',zlib.compress(pixels))+chunk(b'IEND',b'')
    return base64.b64encode(png).decode('ascii')


def verify_png(request, request_ids, wait_idle, database, base):
    """验证历史恢复、工具续轮与真实图片出站。@param request 真实网关入口。@param request_ids 公共请求标识。@param wait_idle 排空观察。@param database 合成账号库。@param base Gemini 路径。@return 脱敏结果。"""

    def set_support(value):
        capabilities={'model_mappings':{MODEL:'MODEL_PLACEHOLDER_M36'}}
        if value is not None:
            capabilities['png_inputs']={MODEL:value}
        with database:
            database.execute('UPDATE accounts SET usage_data=? WHERE id=1',(json.dumps({'capabilities':capabilities}),))

    historical,current=fixture_png((255,0,0)),fixture_png((0,0,255))
    urlsafe=str.maketrans('+/','-_')
    first={'role':'user','parts':[{'text':'历史图'},{'inlineData':{'mimeType':'image/png','data':historical.translate(urlsafe)}}]}
    last={'role':'user','parts':[{'inline_data':{'mime_type':'image/png','data':current.translate(urlsafe).rstrip('=')}}]}
    body={'contents':[first], 'tools':[{'functionDeclarations':[{'name':'synthetic_lookup'}]}],
        'generationConfig':{'responseModalities':['TEXT']}}
    for index in range(76):
        body['contents'].extend([
            {'role':'model','parts':[{'functionCall':{'name':'synthetic_lookup','args':{'index':index}},
                'thoughtSignature':'-_8=' if index % 2 else '-_8'}]},
            {'role':'user','parts':[{'functionResponse':{'name':f'call_{index+1}','response':{'index':index}}}]},
        ])
    body['contents'].append(last)
    set_support(True)
    observed_pid=None
    for count,operation in enumerate(('generateContent','streamGenerateContent?alt=sse'),1):
        status,raw=request(base+operation,body)
        require(status==200,'含工具历史及 PNG 的公共请求失败：'+str(status)+' '+raw.decode()[:350])
        wait_idle()
        require(len(Upstream.calls)==count,'合法请求的上游提交次数错误')
        rid=request_ids[-1]
        deadline=time.monotonic()+8
        while True:
            code,raw=request('/admin/request-diagnostics/'+rid,admin=True)
            if code==200 and (attempts:=json.loads(raw)['attempts']):
                attempt=attempts[-1]
                code,raw=request(f'/admin/request-diagnostics/{rid}/captures/{attempt["attempt_id"]}',admin=True)
                if code==200 and (tls:=(json.loads(raw).get('snapshot') or {}).get('wire_final')):
                    break
            require(time.monotonic()<deadline,'普通AGY请求缺少原生TLS写入快照');time.sleep(.1)
        require(tls['source']=='agy_native_tls' and tls['complete']
            and tls['original_body_sha256']==Upstream.calls[-1]['entity_sha256'], '原生TLS接受实体与回环实收不符')
        require('synthetic-at-1' not in json.dumps(tls),'原生TLS快照包含未脱敏凭据')
        runtime=attempt['runtime']
        require(runtime and runtime['prepared_ms']>=runtime['preparation_wait_ms']+runtime['checkout_ms']
            and runtime['warm_hit']==(count==2),'原生冷、热准备阶段无有效耗时')
        if count==1:
            require(runtime['worker_start_ms'] is not None,'冷启动计时缺失')
            observed_pid=runtime['worker_pid']
        else:
            require(runtime['worker_start_ms'] is None and runtime['worker_pid']==observed_pid,'热进程记录错误')
        wire=Upstream.calls[-1]['body']['request']['contents']
        parts=[part for message in wire for part in message.get('parts',[])]
        photos=[part['inlineData'] for part in parts if 'inlineData' in part]
        require([(part['mimeType'],part['data']) for part in photos]==[('image/png',historical),('image/png',current)],
            '上游未收到对应历史和当前轮的原始 PNG')
        owners=[message for message in wire if any('inlineData' in part for part in message.get('parts',[]))]
        require(len(owners)==2 and all(message['role']=='user' for message in owners)
            and any('历史图' in part.get('text','') for part in owners[0]['parts']), '图片的原用户轮次丢失')
        tool_results=[part['functionResponse'] for part in parts if 'functionResponse' in part]
        require(len(tool_results)==76 and all(part['name']=='synthetic_lookup' for part in tool_results),
            '旧格式 76 组工具结果未以真实工具名提交：'+str(len(tool_results)))
        signatures=[part.get('thoughtSignature','') for part in parts if 'functionCall' in part]
        require(len(signatures)==76 and all(base64.b64decode(value,altchars=b'-_',validate=True)==b'\xfb\xff'
            for value in signatures),'出站工具历史的签名字节发生变化')

    count=len(Upstream.calls)
    invalid_image={'contents':[{'parts':[{'inlineData':{'mimeType':'image/png','data':'aW52YWxpZA=='}}]}]}
    corrupted=bytearray(base64.b64decode(current));corrupted[-1]^=1
    corrupt_png={'contents':[{'parts':[{'inlineData':{'mimeType':'image/png',
        'data':base64.urlsafe_b64encode(corrupted).decode('ascii')}}]}]}
    invalid_tool=copy.deepcopy(body)
    invalid_tool['contents'][4]['parts'][0]['functionResponse']['name']='call_1'
    for value,request_body,reason in ((True,invalid_image,'AGY_INVALID_PNG'),(True,corrupt_png,'AGY_INVALID_PNG'),
            (True,invalid_tool,'AGY_TOOL_RESULT_MISMATCH'),(None,body,'AGY_PNG_CAPABILITY_UNKNOWN'),
            (False,body,'AGY_PNG_UNSUPPORTED')):
        set_support(value)
        status,raw=request(base+'streamGenerateContent?alt=sse',request_body)
        error=json.loads(raw)['error']
        require(status==400 and error['details'][0]['reason']==reason,'公开错误分类不符：'+str(error))
        wait_idle()
    require(len(Upstream.calls)==count==2,'拒绝请求触发了额外模型提交')
    set_support(True)
    tool={'contents':[{'role':'user','parts':[{'text':'TLS_SYNTHETIC_TOOL'}]}],
        'tools':[{'functionDeclarations':[{'name':'synthetic_tool','parameters':{'type':'OBJECT',
            'properties':{'x':{'type':'INTEGER'}}}}]}]}
    status,raw=request(base+'generateContent',tool)
    require(status==200,'真实工具首轮失败：'+str(status)+' '+raw.decode()[:350])
    history=tool['contents']+[json.loads(raw)['candidates'][0]['content']]
    result={'functionResponse':{'name':'call_'+('a1b2'*8),'response':{'value':'TLS_SYNTHETIC_RESULT'}}}
    invalid_live={**tool,'contents':history+[{'role':'user','parts':[result,*invalid_image['contents'][0]['parts']]}]}
    status,raw=request(base+'generateContent',invalid_live)
    detail=json.loads(raw)['error']
    require(status==400 and detail['details'][0]['reason']=='AGY_INVALID_PNG'
        and detail['details'][1]['fieldViolations'][0]['field']=='contents[2].parts[1].inlineData',
        '原工具续轮缺少 PNG 拒绝位置：'+str(detail))
    require(len(Upstream.calls)==3,'坏图触发模型提交')
    valid_live={**tool,'contents':history+[{'role':'user','parts':[result,*last['parts']]}]}
    status,raw=request(base+'generateContent',valid_live)
    require(status==200,'修正 PNG 后原工具轮未能完成：'+str(status)+' '+raw.decode()[:350])
    wait_idle()
    parts=[part for message in Upstream.calls[-1]['body']['request']['contents'] for part in message['parts']]
    require(any(part.get('inlineData',{}).get('data')==current for part in parts)
        and any(part.get('functionResponse',{}).get('name')=='synthetic_tool' for part in parts),
        '原工具续轮缺少 PNG 或工具结果')
    require(request(base+'generateContent',valid_live)==(status,raw) and len(Upstream.calls)==4,'重复 PNG 回填产生额外模型提交或响应变化')

    from PIL import Image

    first=Image.new('RGB',(16,16),(255,0,0));second=Image.new('RGB',(16,16),(0,0,255))
    gif=io.BytesIO();first.save(gif,format='GIF',save_all=True,append_images=[second],duration=100,disposal=2)
    jpeg=io.BytesIO();first.save(jpeg,format='JPEG')
    sound=io.BytesIO()
    with wave.open(sound,'wb') as writer:
        writer.setnchannels(1);writer.setsampwidth(2);writer.setframerate(8000);writer.writeframes(b'\0\1'*160)
    media_parts=[{'inlineData':{'mimeType':kind,'data':base64.b64encode(blob.getvalue()).decode()}}
        for kind,blob in [('image/jpeg',jpeg),('image/gif',gif),('audio/wav',sound)]]
    attached={'contents':[{'role':'user','parts':[{'text':'带媒体输入'},*media_parts]}]}
    def save_capabilities(gif_allowed):
        capabilities={'model_mappings':{MODEL:'MODEL_PLACEHOLDER_M36'},'media_inputs':{MODEL:{'image/png':True,
            'image/jpeg':True,'image/gif':gif_allowed,'audio/wav':True,'video/mp4':False}}}
        with database:database.execute('UPDATE accounts SET usage_data=? WHERE id=1',(json.dumps({'capabilities':capabilities}),))
    def native_media():
        messages=Upstream.calls[-1]['body']['request']['contents']
        return [part['inlineData'] for message in messages for part in message['parts'] if 'inlineData' in part]

    save_capabilities(True)
    status,raw=request('/admin/accounts/1',admin=True)
    require(status==200 and json.loads(raw)['agy_gif_frames_enabled'] is False,'旧账号 GIF 开关缺省值错误')
    require(request(base+'generateContent',attached)[0]==200,'关闭开关时媒体原样请求失败')
    wait_idle()
    require(native_media()==[part['inlineData'] for part in media_parts],'JPEG、GIF 或 WAV 原始字节丢失')
    status,raw=request('/admin/accounts/1',{'agy_gif_frames_enabled':True},admin=True)
    require(status==200 and json.loads(raw)['agy_gif_frames_enabled'] is True,'账号 GIF 开关保存失败')
    save_capabilities(False)
    require(request(base+'generateContent',attached)[0]==200,'已启用转换时 GIF 未按 PNG 能力准入')
    wait_idle()
    sent=native_media()
    require([item['mimeType'] for item in sent]==['image/jpeg','image/png','image/png','audio/wav'],'转换顺序或媒体 MIME 错误')
    require(sent[0]==media_parts[0]['inlineData'] and sent[-1]==media_parts[-1]['inlineData'],'混合媒体转发字节变化')
    for frame,expected in zip(sent[1:3],[(255,0,0),(0,0,255)]):
        with Image.open(io.BytesIO(base64.b64decode(frame['data']))) as observed:
            require(observed.convert('RGB').getpixel((0,0))==expected,'GIF 抽帧颜色或顺序错误')
    rejected={'contents':[{'parts':[{'inlineData':{'mimeType':'video/mp4','data':'aW52YWxpZA=='}}]}]}
    status,raw=request(base+'generateContent',rejected)
    require(status==400 and json.loads(raw)['error']['details'][0]['reason']=='AGY_MEDIA_UNSUPPORTED'
        and len(Upstream.calls)==6,'型号明确拒绝媒体后仍有模型提交')

    status,raw=request(base+'generateContent',tool)
    require(status==200,'GIF 工具首轮失败')
    history=tool['contents']+[json.loads(raw)['candidates'][0]['content']]
    damaged_gif=base64.b64encode(gif.getvalue()[:-8]+b';').decode()
    bad_gif={'inlineData':{'mimeType':'image/gif','data':damaged_gif}}
    invalid_live={**tool,'contents':history+[{'role':'user','parts':[result,bad_gif]}]}
    status,raw=request(base+'generateContent',invalid_live)
    require(status==400 and json.loads(raw)['error']['details'][0]['reason']=='AGY_INVALID_MEDIA'
        and len(Upstream.calls)==7,'坏 GIF 提交或错误分类异常')
    valid_live={**tool,'contents':history+[{'role':'user','parts':[result,media_parts[1]]}]}
    status,raw=request(base+'generateContent',valid_live)
    require(status==200,'修正 GIF 后原工具轮未能完成')
    wait_idle()
    require(native_media()==sent[1:3] and len(Upstream.calls)==8,'工具续轮的 GIF 转换结果错误')
    require(request(base+'generateContent',valid_live)==(status,raw) and len(Upstream.calls)==8,'重复 GIF 回填产生额外模型提交或响应变化')

    invalid_config={'contents':[{'parts':[{'text':'合成拒绝诊断'}]}],'generationConfig':{'topK':10}}
    status,raw=request(base+'generateContent',invalid_config)
    error=json.loads(raw)['error']
    require(status==400 and error['details'][0]['reason']=='AGY_UNSUPPORTED_INPUT'
        and error['details'][1]['fieldViolations'][0]['field']=='generationConfig.topK',
        '原生拒绝未返回生成配置字段')
    require(len(Upstream.calls)==8,'无效生成配置触发了额外模型提交')

    until=time.monotonic()+10
    while True:
        status,raw=request('/admin/request-diagnostics?platform=antigravity&entry_protocol=gemini&page_size=50',admin=True)
        require(status==200,'请求诊断查询失败')
        rows=json.loads(raw)['items']
        rejected=next((row for row in rows if row['context'].get('input_rejection_reason')=='AGY_UNSUPPORTED_INPUT'
            and row['finished_at']),None)
        if rejected:break
        require(time.monotonic()<until,'请求诊断落账条数不足');time.sleep(.1)
    reasons={row['context'].get('input_rejection_reason') for row in rows}
    require({'AGY_INVALID_PNG','AGY_TOOL_RESULT_MISMATCH','AGY_PNG_CAPABILITY_UNKNOWN','AGY_PNG_UNSUPPORTED'}<=reasons,
        '根请求缺少受控输入拒绝分类')
    require(rejected['context']['input_rejection_field']=='generationConfig.topK','根诊断缺少生成配置字段')
    verify_rejected_snapshot(request,rejected['request_id'],rejected['last_attempt']['attempt_id'],
        'agy_ingress',invalid_config)
    return {'passed':True,'network':'none','real_model_submissions':0,'synthetic_native_model_submissions':len(Upstream.calls),
        'legacy_tool_results_per_request':76,'outbound_pngs_per_history_request':2,'live_tool_retry':True,
        'diagnostic_requests':len(rows),'account_gif_switch':True,'original_jpeg_and_wav':True,'live_gif_retry':True,
        'agy_rejected_ingress':True}


def verify_rejected_snapshot(request, request_id, attempt_id, stage, body=None):
    """从管理 API 校验实际入站证据。@param request HTTP 入口。@param request_id 根请求。@param attempt_id 快照绑定。@param stage 预期阶段。@param body 可选的预期脱敏正文。@return 快照。"""
    until=time.monotonic()+10
    while True:
        status,raw=request(f'/admin/request-diagnostics/{request_id}/captures/{attempt_id}',admin=True)
        require(status==200,'拒绝入站管理接口返回 '+str(status))
        value=json.loads(raw)
        if value['state']=='saved':break
        require(time.monotonic()<until,'拒绝入站快照尚未保存：'+value['state']);time.sleep(.1)
    snapshot=value['snapshot']
    require(snapshot['stage']==stage and [item['stage'] for item in snapshot['stages']]==['ingress'],
        '拒绝快照包含未实际发生的阶段')
    require('synthetic-key' not in snapshot['ingress']['body']
        and 'synthetic-key' not in json.dumps(snapshot['ingress']['headers']), '入口密钥未脱敏')
    if body is not None:
        require(json.loads(snapshot['ingress']['body'])==body,'拒绝快照未保存预期正文')
    return snapshot


def verify_gateway_rejections(request):
    """校验 Claude Code 及其准入策略的本地拒绝。@param request HTTP 入口。@return 已验证状态码。"""
    body={'model':'claude-sonnet-4-6','max_tokens':32,'messages':[
        {'role':'user','content':'合成请求'},{'role':'assistant','content':'合成预填'}]}
    require(request('/admin/settings',{'intercept_assistant_prefill_enabled':'true',
        'intercept_assistant_prefill_models':body['model'],'allowed_user_agents':''},admin=True)[0]==200,
        '测试预填拦截设置失败')
    for expected,stage in ((400,'request_policy'),(403,'access_policy')):
        if expected==403:
            require(request('/admin/settings',{'allowed_user_agents':'synthetic-only*'},admin=True)[0]==200,
                '测试准入策略设置失败')
        status,_=request('/v1/messages',body)
        require(status==expected,'本地拒绝状态错误：'+str(status))
        until=time.monotonic()+10
        while True:
            status,raw=request('/admin/request-diagnostics?page_size=50',admin=True)
            require(status==200,'本地拒绝诊断查询失败')
            row=next((row for row in json.loads(raw)['items'] if row['error_stage']==stage and row['finished_at']),None)
            if row:break
            require(time.monotonic()<until,'本地拒绝尚未入账：'+stage);time.sleep(.1)
        require(row['attempt_count']==0 and row['native_rejection']['capture_id']==row['request_id'],
            '本地拒绝未绑定到根请求')
        verify_rejected_snapshot(request,row['request_id'],row['request_id'],'ingress_rejected',body)
    return [400,403]


def verify_rejection_body_modes(request, request_ids, base):
    """用同一组真实入口验证完整、预览和摘要。@param request HTTP 入口。@param request_ids 入口关联 ID。@param base Gemini 模型路径。@return 验证的平台。"""
    size=7*1024*1024
    filler='x'*size
    agy={'contents':[{'parts':[{'text':filler}]}],
        'generationConfig':{'responseModalities':['IMAGE']},'toolConfig':{'private_secret':{'value':'synthetic-private'}}}
    expected_agy={**agy,'toolConfig':{'private_secret':'[REDACTED]'}}
    cc={'model':'claude-sonnet-4-6','max_tokens':32,'messages':[{'role':'user','content':filler},
        {'role':'assistant','content':'synthetic-key'}]}
    expected_cc={**cc,'messages':[cc['messages'][0],{'role':'assistant','content':'[REDACTED]'}]}
    calls=len(Upstream.calls)
    require(request('/admin/settings',{'request_diagnostics_log_mode':'info',
        'request_diagnostics_rejected_body':'invalid'},admin=True)[0]==400,'非法正文设置未拒绝')
    status,raw=request('/admin/settings',admin=True)
    settings=json.loads(raw)
    require(status==200 and settings['request_diagnostics_rejected_body']=='preview'
        and settings['request_diagnostics_log_mode']=='debug','非法保存改变了已生效设置')
    for mode,expected_setting in [('debug','full'),('debug','preview'),('info','full')]:
        require(request('/admin/settings',{'request_diagnostics_log_mode':mode,
            'request_diagnostics_rejected_body':expected_setting},admin=True)[0]==200,'诊断设置保存失败')
        status,raw=request('/admin/settings',admin=True)
        require(status==200 and json.loads(raw)['request_diagnostics_rejected_body']==expected_setting,'读取到的正文设置与保存不符')
        for path,body,expected_status,expected in [(base+'generateContent',agy,400,expected_agy),('/v1/messages',cc,403,expected_cc)]:
            if mode=='info' and path=='/v1/messages':
                # 摘要模式的准入拒绝可在客户端传完正文前关闭连接。
                body={**cc,'messages':[{'role':'user','content':'合成请求'},cc['messages'][1]]}
            status,_=request(path,body)
            require(status==expected_status,'本地拒绝的 HTTP 状态发生变化：'+str(status))
            request_id=request_ids[-1]
            until=time.monotonic()+10
            while True:
                status,raw=request(f'/admin/request-diagnostics/{request_id}',admin=True)
                detail=json.loads(raw)
                if status==200 and detail['request']['finished_at']:break
                require(time.monotonic()<until,'诊断尚未入账');time.sleep(.1)
            row=detail['request'];rejected=row.get('native_rejection')
            require(row['log_mode']==mode,'未记录请求入口冻结的模式')
            if mode=='info':
                require(not rejected,'摘要模式产生了拒绝正文')
                continue
            full=expected_setting=='full'
            gateway_archive=full or path=='/v1/messages'
            capture_id=rejected['capture_id'] if gateway_archive else detail['attempts'][-1]['attempt_id']
            require(not gateway_archive or capture_id==request_id,'网关入站证据未绑定到同一根请求')
            snapshot=verify_rejected_snapshot(request,request_id,capture_id,
                'ingress_rejected' if gateway_archive else 'agy_ingress',expected if full else None)
            preview=snapshot['ingress']
            require(preview['body_truncated']!=full and preview['original_body_bytes']>size,'正文采集大小或完整状态错误')
    require(len(Upstream.calls)==calls,'诊断模式切换产生了额外上游调用')
    return ['antigravity','claude_code']


def verify_egress_body_modes(request, request_ids, wait_idle, base):
    """用真实出站验证完整、预览和摘要。@param request HTTP 入口。@param request_ids 入口关联 ID。@param wait_idle 原生排空。@param base Gemini 模型路径。@return 验证的采集来源。"""
    from PIL import Image

    def image(side, seed):
        # 原生运行时会缩减长纯文本，使用真实 PNG 保留足够大的出站字节。
        raw=io.BytesIO()
        Image.frombytes('RGB',(side,side),random.Random(seed).randbytes(side*side*3)).save(raw,format='PNG')
        return {'inlineData':{'mimeType':'image/png','data':base64.b64encode(raw.getvalue()).decode()}}

    marker={'text':'合成完整正文 synthetic-at-1'}
    body={'contents':[{'parts':[marker,image(700,1)]}]}
    large={'contents':[{'parts':[marker,image(1040,2),image(1040,3)]}]}
    adapted={**body,'safetySettings':[{'category':'HARM_CATEGORY_HARASSMENT','threshold':'BLOCK_MEDIUM_AND_ABOVE'}]}
    sources=[]
    for mode,setting,payload,source in [('debug','preview',body,'agy_native_tls'),
            ('debug','full',large,'agy_native_tls'),('debug','full',adapted,'agy_http_transport'),
            ('info','full',body,None)]:
        require(request('/admin/settings',{'request_diagnostics_log_mode':mode,
            'request_diagnostics_rejected_body':setting},admin=True)[0]==200,'出站设置保存失败')
        count=len(Upstream.calls)
        status,raw=request(base+'generateContent',payload)
        require(status==200,'大正文实际出站失败：'+str(status)+' '+raw.decode()[:240])
        wait_idle()
        require(len(Upstream.calls)==count+1,'正文策略改变模型实际提交次数')
        rid=request_ids[-1]
        deadline=time.monotonic()+10
        while True:
            status,raw=request('/admin/request-diagnostics/'+rid,admin=True)
            if status==200 and (attempts:=json.loads(raw)['attempts']):
                status,raw=request(f'/admin/request-diagnostics/{rid}/captures/{attempts[-1]["attempt_id"]}',admin=True)
                if status==200:
                    capture=json.loads(raw)
                    if mode=='info' or (capture.get('snapshot') or {}).get('wire_final'):break
            require(time.monotonic()<deadline,'大正文出站快照缺失');time.sleep(.1)
        if mode=='info':
            require(attempts[-1]['log_mode']=='info' and capture['state'] in ('summary','disabled')
                and 'snapshot' not in capture,'摘要模式仍发布出站正文')
            continue
        snapshot=capture['snapshot'];wire=snapshot['wire_final']
        require(wire['source']==source and wire['complete'] and wire['original_body_sha256']==Upstream.calls[-1]['entity_sha256'],
            '大正文采集来源或哈希不符')
        stage=next(stage for stage in snapshot['stages'] if stage['stage']=='wire_final')
        if setting=='full':
            require(not wire['body_truncated'] and stage['status']=='complete' and '合成完整正文 [redacted]' in wire['body']
                and 'synthetic-at-1' not in wire['body'],'完整模式缺少尾部或泄露凭据')
            parts=[part for content in json.loads(wire['body'])['request']['contents'] for part in content['parts']]
            require([part['inlineData'] for part in parts if 'inlineData' in part]
                ==[part['inlineData'] for part in payload['contents'][0]['parts'] if 'inlineData' in part], '出站图片数据不完整')
            require(len(wire['body'].encode())>(8 if payload is large else 1)*1024*1024,'测试未覆盖读写预算边界')
            sources.append(source)
        else:
            require(wire['body_truncated'] and stage['status']=='truncated' and wire['original_body_bytes']>1024*1024,
                '预览模式没有按原预算标记截断')
    return sources


def verify_native_safety(request, request_ids, wait_idle, base):
    """核对原生 AGY 组装、逐类阈值出站及回到普通路径。@param request HTTP 入口。@param request_ids 入口关联ID。@param wait_idle 原生排空。@param base 模型路径。@return 校验范围。"""
    require(request('/admin/settings',{'request_diagnostics_log_mode':'debug'},admin=True)[0]==200,
        '测试安全阈值日志设置失败')
    Upstream.model_catalog_host='daily-cloudcode-pa.googleapis.com'
    rules=[{'category':category,'threshold':'BLOCK_MEDIUM_AND_ABOVE'} for category in (
        'HARM_CATEGORY_HARASSMENT','HARM_CATEGORY_HATE_SPEECH',
        'HARM_CATEGORY_SEXUALLY_EXPLICIT','HARM_CATEGORY_DANGEROUS_CONTENT')]
    body={'contents':[{'parts':[{'text':'合成安全阈值测试'}]}],
        'generationConfig':{'responseModalities':['TEXT']}}
    count=len(Upstream.calls)
    with_safety={**body,'safetySettings':rules}
    def capture_for(request_id):
        """等待同次实际出站采集。@param request_id 根请求标识。@return 采集快照。"""
        end=time.monotonic()+10
        while True:
            detail_status,detail=request('/admin/request-diagnostics/'+request_id,admin=True)
            if detail_status==200 and (attempts:=json.loads(detail)['attempts']):
                capture_status,capture=request(f'/admin/request-diagnostics/{request_id}/captures/{attempts[-1]["attempt_id"]}',admin=True)
                if capture_status==200 and (snapshot:=json.loads(capture).get('snapshot')) and 'wire_final' in snapshot:
                    return snapshot
            require(time.monotonic()<end,'实际出站快照尚未保存');time.sleep(.1)

    for operation in ('generateContent','streamGenerateContent?alt=sse'):
        status,raw=request(base+operation,with_safety)
        require(status==200,'逐类安全阈值未通过原生请求：'+str(status)+' '+raw.decode()[:240])
        wait_idle()
        count+=1
        require(len(Upstream.calls)==count,'原生安全阈值请求发生重放或缺少出站')
        upstream=Upstream.calls[-1]
        require(upstream['path']=='/v1internal:streamGenerateContent?alt=sse'
            and upstream['authorization']=='Bearer synthetic-at-1'
            and upstream['body']['request']['safetySettings']==rules,
            '上游未收到同账号和完整安全规则')
        require('本地TLS回复'.encode() in raw and b'usageMetadata' in raw,'原生响应或用量丢失')
        snapshot=capture_for(request_ids[-1])
        wire=snapshot['wire_final']
        require(wire['complete'] and wire['http_status']==200
            and wire['original_body_sha256']==upstream['entity_sha256'], '出站摘要与真实接收实体不符')
        require('synthetic-at-1' not in json.dumps(wire)
            and json.loads(wire['body'])['request']['safetySettings']==rules, '出站捕获缺少阈值或访问凭据未脱敏')
        actions=snapshot['header_policy']['decisions']
        require(any(row['name']=='x-synthetic-ingress' and row['action']=='drop' for row in actions)
            and any(row['name']=='host' and row['action']=='runtime' for row in actions)
            and any(row['name']=='user-agent' and row['action']=='keep' for row in actions), '逐头处理记录缺失')
    status,_=request(base+'generateContent',{**body,'safetySettings':[rules[0],rules[0]]})
    require(status==400 and len(Upstream.calls)==count,'重复类别触发了出站')
    status,_=request(base+'generateContent',body)
    wait_idle()
    require(status==200 and len(Upstream.calls)==count+1
        and 'safetySettings' not in Upstream.calls[-1]['body']['request'],'普通请求继承了前一请求的安全规则')
    native=Upstream.calls[-1]
    adapted=Upstream.calls[count-1]
    require(adapted['request_header_names']==native['request_header_names']
        and adapted['request_headers']==native['request_headers'],
        '模型请求头或实际目标与原生请求不一致')
    require(adapted['proxy_headers']==native['proxy_headers'],'HTTP 代理握手头与原生请求不一致')
    truncated={**with_safety,'contents':[{'parts':[{'text':'TLS_SYNTHETIC_TRUNCATED'}]}]}
    status,_=request(base+'generateContent',truncated)
    wait_idle()
    require(status==503 and len(Upstream.calls)==count+2,'阈值请求截断时返回成功或产生额外提交')
    failed={**with_safety,'contents':[{'parts':[{'text':'TLS_SYNTHETIC_UPSTREAM_UNAVAILABLE'}]}]}
    status,_=request(base+'generateContent',failed)
    wait_idle()
    require(status==503 and len(Upstream.calls)==count+3,'上游拒绝后发生重复提交或错误映射')
    wire=capture_for(request_ids[-1])['wire_final']
    require(wire['http_status']==503 and wire['original_body_sha256']==Upstream.calls[-1]['entity_sha256'],
        '失败请求未保留同次实际出站和上游状态')
    quota={**with_safety,'contents':[{'parts':[{'text':'TLS_SYNTHETIC_UPSTREAM_QUOTA'}]}]}
    for occurrence,operation in enumerate(('generateContent','streamGenerateContent?alt=sse'),1):
        if occurrence==2:
            require(request('/admin/settings',{'request_diagnostics_log_mode':'info'},admin=True)[0]==200,
                '切换摘要日志模式失败')
        status,raw=request(base+operation,quota)
        wait_idle()
        error=json.loads(raw)['error']
        require(status==429 and error['code']==429 and error['status']=='RESOURCE_EXHAUSTED'
            and 'private synthetic detail' not in error['message'] and len(Upstream.calls)==count+3+occurrence,
            '上游限流错误未准确返回或发生重复提交')
        rid=request_ids[-1]
        status,raw=request('/admin/request-diagnostics/'+rid,admin=True)
        require(status==200 and json.loads(raw)['attempts'][-1]['error_type']=='RESOURCE_EXHAUSTED',
            '诊断记录未区分上游限流')
    late={**body,'contents':[{'parts':[{'text':'TLS_SYNTHETIC_CAPACITY_AFTER_OUTPUT'}]}]}
    status,raw=request(base+'streamGenerateContent?alt=sse',late)
    wait_idle()
    frames=[json.loads(line[6:]) for line in raw.decode().splitlines() if line.startswith('data: ')]
    require(status==200 and len(frames)==2 and 'candidates' in frames[0]
        and frames[-1]['error']['code']==429 and frames[-1]['error']['status']=='RESOURCE_EXHAUSTED'
        and 'private synthetic detail' not in frames[-1]['error']['message'] and len(Upstream.calls)==count+6,
        '已返回首帧的 SSE 未保留实际限流错误')
    account_safety=verify_native_account_safety(request,request_ids,wait_idle,base,with_safety)
    before=len(Upstream.calls)
    broken_tool={'contents':[{'parts':[{'text':'TLS_SYNTHETIC_TOOL_THEN_ERROR'}]}],
        'tools':[{'functionDeclarations':[{'name':'synthetic_tool','parameters':{'type':'OBJECT',
            'properties':{'x':{'type':'INTEGER'}}}}]}]}
    status,raw=request(base+'streamGenerateContent?alt=sse',broken_tool)
    wait_idle()
    require(status==503 and 'functionCall' not in raw.decode() and len(Upstream.calls)==before+1,
        '原生失败前的调用泄漏到客户端，或触发重复模型发送')
    return {'thresholds':len(rules),'native_streaming':True,'ordinary_request_restored':True,
        'truncated_rejected':True,'upstream_host':adapted['request_headers']['host'],'request_headers_preserved':True,
        'wire_capture_matches_upstream':True,'header_policy':True,'upstream_503_observed':True,
        'quota_429_preserved':True,'quota_after_first_output':True,'account_native_safety':account_safety,
        'unowned_tool_call_withheld':True}


def verify_native_account_safety(request, request_ids, wait_idle, base, body):
    """通过账号接口验证开关与实际模型出站。@param request HTTP 入口。@param request_ids 公共请求标识。@param wait_idle 原生排空。@param base 模型路径。@param body 带逐类阈值的请求。@return 开关验证通过。"""
    path='/admin/accounts/1'
    key='agy_disable_safety_filtering'
    status,raw=request(path,admin=True)
    require(status==200 and json.loads(raw)[key] is False,'历史账户默认关闭')
    require(request(path,{key:'true'},admin=True)[0]==400,'账号开关接受了无效类型')
    require(request('/admin/settings',{'request_diagnostics_log_mode':'debug'},admin=True)[0]==200,
        '启用账号开关验证采集失败')
    # 同一模型的已有原生布尔路径提供实际出站基线。
    native_only={**body,'safetySettings':[{**rule,'threshold':'OFF'} for rule in body['safetySettings']]}
    require(request(base+'generateContent',native_only)[0]==200,'原生安全开关基线失败')
    wait_idle()
    native_rules=Upstream.calls[-1]['body']['request'].get('safetySettings')
    count=len(Upstream.calls)
    no_thresholds={name:value for name,value in body.items() if name!='safetySettings'}
    for enabled,cases in ((True,(body,no_thresholds)),(False,(body,))):
        status,raw=request(path,{key:enabled},admin=True)
        require(status==200 and json.loads(raw)[key] is enabled,'账号开关写入失败')
        status,raw=request(path,admin=True)
        require(status==200 and json.loads(raw)[key] is enabled,'账号开关读取失败')
        for payload in cases:
            status,raw=request(base+'generateContent',payload)
            require(status==200,'账号开关后的模型请求失败：'+str(status)+' '+raw.decode()[:240])
            wait_idle()
            count+=1
            require(len(Upstream.calls)==count,'账号开关产生了额外模型调用')
            sent=Upstream.calls[-1]['body']['request'].get('safetySettings')
            if enabled:
                require(sent==native_rules and sent!=body['safetySettings'],
                    '账号开关启用时实际出站偏离原生处理')
                rid=request_ids[-1]
                end=time.monotonic()+10
                while True:
                    status,raw=request('/admin/request-diagnostics/'+rid,admin=True)
                    if status==200 and (attempts:=json.loads(raw)['attempts']):
                        capture=f'/admin/request-diagnostics/{rid}/captures/{attempts[-1]["attempt_id"]}'
                        status,raw=request(capture,admin=True)
                        if status==200 and (snapshot:=json.loads(raw).get('snapshot')) and snapshot.get('stage')=='agy_prepared':
                            break
                    require(time.monotonic()<end,'账号开关的原生提交回执未就绪');time.sleep(.1)
                prepared=json.loads(snapshot['body'])
                require(prepared['cascadeConfig']['plannerConfig']['completionConfigOverride']['disableSafetyFiltering'] is True
                    and (snapshot.get('wire_final') or {}).get('source')!='agy_http_transport','账号开关缺少原生布尔值或进入出站改写')
            else:
                require(sent==body['safetySettings'],'关闭开关后未恢复客户端逐类阈值')
    return True


def verify_kernel_selection(request, wait_idle, base):
    """用真实内核验证切换、原生工作进程换代和恢复。@param request Gemini 入口。@param wait_idle 实际排空。@param base 模型入口。@return 验证摘要。"""
    configuration_path = Path('/state/sender.json')
    configuration = json.loads(configuration_path.read_bytes())
    builtin = configuration['agy'].copy()
    target = Path('/state/agy-kernels') / ('a' * 64)
    target.parent.mkdir()
    source = Path(builtin['module_root']) / 'agy_runtime'
    shutil.copytree(source, target / 'agy_runtime')
    mapping = target / 'agy_runtime/gemini_contract.py'
    with mapping.open('a') as output:
        output.write('''
_base_history = native_history
def native_history(*args, **kwargs):
    steps = _base_history(*args, **kwargs)
    steps[-1]['userInput']['userResponse'] += ' TLS_SYNTHETIC_CANDIDATE'
    return steps
''')

    body = {'contents': [{'role': 'user', 'parts': [{'text': 'TLS_SYNTHETIC_TEXT'}]}]}
    def check(native, uses_candidate):
        configuration['agy'] = native
        staged = configuration_path.with_suffix('.tmp')
        staged.write_text(json.dumps(configuration))
        staged.replace(configuration_path)
        status, raw = request(base + 'generateContent', body)
        require(status == 200, '切换后请求失败：' + str(status) + ' ' + raw.decode()[:350])
        wait_idle()
        wire = Upstream.calls[-1]['body']['request']['contents']
        require(('TLS_SYNTHETIC_CANDIDATE' in json.dumps(wire)) == uses_candidate, '实际 worker 没有使用所选映射')
        query = Request('http://127.0.0.1:8091/internal/status', headers={'authorization': 'Bearer ' + SECRET})
        with urlopen(query, timeout=5) as response:
            state = json.load(response)['agy']
        require(state['module_root'] == native['module_root'], '进程内核来源报告不一致')
        return state['processes'][0]['native']['pid']

    first = check(builtin, False)
    # 使用与线上候选相同的摘要层级，覆盖监督器与 worker 共用的 Unix 端点长度。
    second = check({**builtin, 'module_root': str(target), 'work_root': '/state/native/kernels/' + target.name}, True)
    third = check(builtin, False)
    require(len({first, second, third}) == 3 and len(Upstream.calls) == 3, '未完成独立进程换代及单次提交')
    return {'passed': True, 'candidate_wire_observed': True, 'builtin_restored': True,
        'distinct_native_processes': 3, 'synthetic_submissions': len(Upstream.calls)}


def verify_tool_deadlines(request, wait_idle, base):
    """验证单个工具在生成期限之后仍能回填。@param request 网关入口。@param wait_idle 原生排空。@param base 模型路径。@return 实际轮数和耗时。"""
    body={'contents':[{'role':'user','parts':[{'text':'TLS_SYNTHETIC_LONG_TOOL_CHAIN'}]}],
        'tools':[{'functionDeclarations':[{'name':'synthetic_tool','parameters':{'type':'OBJECT',
            'properties':{'x':{'type':'INTEGER'}}}}]}]}
    started=time.monotonic()
    tool_wait_seconds=0
    for round_number in range(6):
        streaming=round_number%2==0
        operation='streamGenerateContent?alt=sse' if streaming else 'generateContent'
        status,raw=request(base+operation,body)
        require(status==200,'工具链第 '+str(round_number+1)+' 轮失败 '+str(status)+' '+raw.decode()[:200])
        frames=[json.loads(line[6:]) for line in raw.decode().splitlines() if line.startswith('data: ')] if streaming else [json.loads(raw)]
        parts=[part for frame in frames for candidate in frame.get('candidates',[])
            for part in candidate.get('content',{}).get('parts',[]) if 'functionCall' in part]
        require(len(parts)==1,'工具轮缺少唯一回填对象')
        call=parts[0]['functionCall']
        result={'name':call['name'],'response':{'value':round_number+1}}
        if 'id' in call:result['id']=call['id']
        body['contents'].extend([{'role':'model','parts':parts},
            {'role':'user','parts':[{'functionResponse':result}]}])
        if round_number==1:
            # 等待超过生成预算。已交付的响应到期，下一轮工具仍能正常回填。
            expired={**body,'contents':body['contents'][:-2]}
            delivered=time.monotonic()
            time.sleep(125)
            tool_wait_seconds=round(time.monotonic()-delivered,2)
            status,raw=request(base+operation,expired)
            require(status==410 and '原工具回填响应已过期'.encode() in raw and len(Upstream.calls)==2,
                '响应回收后缺少提交回执或产生了新模型提交')
    status,raw=request(base+'generateContent',body)
    wait_idle()
    require(status==200 and '本地TLS回复'.encode() in raw and len(Upstream.calls)==7,
        '跨首轮截止的工具结果未完成或触发了额外模型调用')
    require(request(base+'generateContent',body)==(status,raw) and len(Upstream.calls)==7,
        '长工具链重试产生额外模型调用或响应变化')
    return {'passed':True,'tool_rounds':6,'model_calls':7,'tool_wait_seconds':tool_wait_seconds,
        'expired_replay_status':410,'elapsed_seconds':round(time.monotonic()-started,2)}


def verify_parallel_tool_turn(parts, id_mode, expected_count):
    """从一轮流式调用构造客户端回填。@param parts 模型输出。@param id_mode 回填 ID 的表示。@param expected_count 预期调用数。@return 用户回填。"""
    calls=[part['functionCall'] for part in parts]
    require(len(calls)==expected_count and len({call['id'] for call in calls})==expected_count,
        '首条工具 SSE 缺少完整调用或独立 ID')
    require([part.get('thoughtSignature') for part in parts]==['c3ludGhldGljLXNpZw==']+[None]*(expected_count-1),
        '聚合改变了调用签名的归属')
    replies=[{'functionResponse':{'name':call['name'],'response':{'value':call['args']['x']}}}
        for call in calls]
    if id_mode=='explicit':
        for call, reply in zip(calls, replies):
            reply['functionResponse']['id']=call['id']
        replies.reverse()
    else:
        if id_mode=='mixed':
            # 先回填第二个同名调用，并仅在第一个调用的结果上保留真实 ID。
            require(calls[0]['name']==calls[1]['name'],'混合回填需要两个同名调用')
            replies[0]['functionResponse']['id']=calls[0]['id']
            replies[0],replies[1]=replies[1],replies[0]
        for call, reply in zip(calls,replies):
            # AstrBot 省略专用 ID 字段，并可能把 ID 放进结果名称。
            if id_mode=='alias':reply['functionResponse']['name']=call['id']
            del call['id']
    return replies


def verify_parallel_tool_mapping(expected_count):
    """核对真实出站中全部工具参数和对应结果。@param expected_count 历史调用数。@return 无。"""
    submitted_parts=[part for message in Upstream.calls[-1]['body']['request']['contents']
        for part in message['parts']]
    submitted_calls={part['functionCall']['id']:part['functionCall']['args']['x']
        for part in submitted_parts if 'functionCall' in part}
    submitted_results={part['functionResponse']['id']:json.loads(part['functionResponse']['response']['output'])['value']
        for part in submitted_parts if 'functionResponse' in part}
    require(len(submitted_calls)==expected_count and submitted_results==submitted_calls,
        '续轮出站交换或遗漏了同名工具结果')


def verify_parallel_tools(request, wait_idle, base):
    """首条工具 SSE 后断开，按真实 AGY 回环覆盖连续并行回填。@param request 公共入口。@param wait_idle 实际排空。@param base 模型路径。@return 验证摘要。"""
    for counts, id_modes in [((2,), ('ordered',)), ((6,4,3), ('alias','explicit','mixed'))]:
        initial_count=len(Upstream.calls)
        marker='TLS_SYNTHETIC_TOOL_PARALLEL' + ('_CHAIN' if len(counts)>1 else '')
        body={'contents':[{'role':'user','parts':[{'text':marker}]}], 'tools':[{'functionDeclarations':[
            {'name':name,'parameters':{'type':'OBJECT','properties':{'x':{'type':'INTEGER'}}}}
            for name in ('synthetic_tool','synthetic_lookup')]}]}
        previous_count=0
        for count, id_mode in zip(counts,id_modes):
            status,raw=request(base+'streamGenerateContent?alt=sse',body,first_tool_frame=True)
            require(status==200,'同名工具流失败：'+str(status)+' '+raw.decode()[:220])
            if previous_count:
                verify_parallel_tool_mapping(previous_count)
            frames=[json.loads(line[6:]) for line in raw.decode().splitlines() if line.startswith('data: ')]
            final=frames[-1]
            require(final['candidates'][0]['finishReason']=='STOP' and final['usageMetadata']['totalTokenCount']==7,
                '首条工具 SSE 缺少原生终态或用量')
            if len(counts)>1:
                require(any(part.get('text')=='准备工具' for frame in frames[:-1]
                    for part in frame['candidates'][0]['content']['parts']),'工具前文本没有单独流式发送')
            parts=[part for part in final['candidates'][0]['content']['parts'] if 'functionCall' in part]
            replies=verify_parallel_tool_turn(parts,id_mode,count)
            if id_mode=='alias':
                partial={**body,'contents':body['contents']+[
                    {'role':'model','parts':parts[:1]},{'role':'user','parts':replies[:1]}]}
                status,raw=request(base+'generateContent',partial)
                require(status==400 and b'AGY_TOOL_RESULT_MISMATCH' in raw and len(Upstream.calls)==initial_count+1,
                    '缺失结果没有在上游提交前拒绝')
            body['contents'].extend([{'role':'model','parts':parts},{'role':'user','parts':replies}])
            previous_count+=count
        status,raw=request(base+'generateContent',body)
        wait_idle()
        expected_requests=initial_count+len(counts)+1
        require(status==200 and '本地TLS回复'.encode() in raw and len(Upstream.calls)==expected_requests,
            '工具回填失败或发生了额外模型发送：'+str(status)+' '+raw.decode()[:220])
        verify_parallel_tool_mapping(previous_count)
        require(request(base+'generateContent',body)==(status,raw) and len(Upstream.calls)==expected_requests,
            '并行工具重试产生额外模型发送或响应变化')
        if len(counts)==1:
            # 同样的初始历史可以启动独立原生请求。裸工具结果此时同时匹配两个归属。
            second={**body,'contents':body['contents'][:1]}
            status,raw=request(base+'streamGenerateContent?alt=sse',second,first_tool_frame=True)
            require(status==200,'无法建立相同历史的新工具归属')
            frame=[json.loads(line[6:]) for line in raw.splitlines() if line.startswith(b'data: ')][-1]
            status,raw=request(base+'generateContent',body)
            require(status==400 and b'AGY_TOOL_RESULT_MISMATCH' in raw and len(Upstream.calls)==expected_requests+1,
                '另一个活跃归属被已缓存的响应覆盖')
            parts=[part for part in frame['candidates'][0]['content']['parts'] if 'functionCall' in part]
            replies=verify_parallel_tool_turn(parts,'explicit',2)
            second['contents'].extend([{'role':'model','parts':parts},{'role':'user','parts':replies}])
            status,raw=request(base+'generateContent',second)
            wait_idle()
            require(status==200 and '本地TLS回复'.encode() in raw and len(Upstream.calls)==expected_requests+2,
                '指定真实调用 ID 后独立工具轮仍无法完成')
    return {'passed':True,'parallel_calls':2,'round_sizes':[6,4,3],'first_tool_sse':True,
        'ambiguous_replay_status':400,'model_calls':len(Upstream.calls)}


def verify_tool_result_retries(request, wait_idle, base, database, request_ids):
    """重现无 ID 混排工具结果和并发重复回填。@param request 网关入口。@param wait_idle 原生排空。@param base 模型路径。@param database 测试库。@param request_ids 网关根 ID。@return 实际模型次数。"""
    initial_count=len(Upstream.calls)
    stream=base+'streamGenerateContent?alt=sse'
    body={'contents':[
        {'role':'user','parts':[{'text':'合成历史问题'}]},
        {'role':'model','parts':[{'text':'合成历史回复'}]},
        {'role':'user','parts':[{'text':'TLS_SYNTHETIC_TOOL_REPLAY'}]},
    ], 'tools':[{'functionDeclarations':[{'name':name,'parameters':{
        'type':'OBJECT','properties':{'x':{'type':'INTEGER'}}}}
        for name in ('synthetic_tool','synthetic_lookup')]}]}

    def append_results(raw, count):
        """按中转省略 ID 的形状追加工具结果。@param raw 首条工具 SSE。@param count 调用数。@return 本轮回填 Part。"""
        frame=[json.loads(line[6:]) for line in raw.splitlines() if line.startswith(b'data: ')][-1]
        parts=[part for part in frame['candidates'][0]['content']['parts'] if 'functionCall' in part]
        replies=verify_parallel_tool_turn(parts,'ordered',count)
        if count==4:
            require([reply['functionResponse']['name'] for reply in replies]
                ==['synthetic_lookup','synthetic_tool','synthetic_tool','synthetic_tool'], '四项调用形状与现场不符')
            replies=replies[1:]+replies[:1]
        body['contents'].extend([{'role':'model','parts':parts},{'role':'user','parts':replies}])
        return replies

    for count in (1,1,4):
        status, raw=request(stream,body,first_tool_frame=True)
        require(status==200,'准备重复回填的前驱工具轮失败')
        replies=append_results(raw,count)
    require(len(body['contents'])==9,'重复回填必须覆盖 contents[8]')
    marker='synthetic-replay-barrier'
    replies[-1]['functionResponse']['response']['marker']=marker
    entered, release=threading.Event(), threading.Event()
    Upstream.held_requests[marker]=(entered,release)
    replay_count_query=("SELECT COUNT(*) FROM request_diagnostics "
        "WHERE json_extract(summary_json,'$.context.replay_of_request_id') IS NOT NULL")
    previous_replays=database.execute(replay_count_query).fetchone()[0]
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            first=pool.submit(request,stream,body,first_tool_frame=True)
            try:
                require(entered.wait(20),'四项回填未实际进入新模型')
                concurrent=pool.submit(request,stream,body,first_tool_frame=True)
                # 检查重试在解除真实上游阻塞前已绑定原根，而不是晚到后的缓存命中。
                until=time.monotonic()+5
                while time.monotonic()<until and not concurrent.done():
                    if database.execute(replay_count_query).fetchone()[0]>previous_replays:
                        break
                    time.sleep(.03)
                require(database.execute(replay_count_query).fetchone()[0]>previous_replays,
                    '并发重试没有在原模型继续前关联同一生成')
            finally:
                release.set()
            original=first.result(timeout=20)
            require(original[0]==200,'首次四项回填失败')
            observed=concurrent.result(timeout=20)
            reordered=copy.deepcopy(dict(reversed(list(body.items()))))
            result=reordered['contents'][8]['parts'][-1]['functionResponse']
            result['response']=dict(reversed(list(result['response'].items())))
            # 完成后的重读消费到 EOF，让诊断按正常 HTTP 收口。
            replay=request(stream,reordered)
            require(observed==original and replay[0]==original[0] and replay[1].rstrip(b'\n')==original[1].rstrip(b'\n'),
                f'重复工具回填应接回原响应，并发状态 {observed[0]}，完成后状态 {replay[0]}')
        replay_id=request_ids[-1]
        until=time.monotonic()+5
        source_id=None
        while time.monotonic()<until:
            status, raw=request('/admin/request-diagnostics/'+replay_id,admin=True)
            if status==200:
                detail=json.loads(raw)
                source_id=detail['request']['context'].get('replay_of_request_id')
                if source_id:
                    break
            time.sleep(.03)
        require(source_id,'重试诊断缺少原生成关联')
        require(status==200 and replay_id!=source_id and detail['request']['attempt_count']==0 and not detail['attempts'],
            '重复请求的 HTTP 根或上游尝试诊断错误')
        status, raw=request('/admin/request-diagnostics/'+source_id,admin=True)
        detail=json.loads(raw)
        require(status==200 and detail['request']['attempt_count']==1 and len(detail['attempts'])==1,
            '原接续轮缺少唯一模型尝试')
        changed=copy.deepcopy(body)
        changed['contents'][-1]['parts'][0]['functionResponse']['response']['value']=-1
        for payload, key in ((changed,'synthetic-key'),(body,'synthetic-other')):
            status,raw=request(stream,payload,token=key)
            require(status==400 and b'AGY_TOOL_RESULT_MISMATCH' in raw,'不同结果或令牌接回了私有响应')
        with database:
            database.execute("UPDATE api_tokens SET blocked_accounts='1' WHERE token='synthetic-key'")
        try:
            require(request(stream,body)[0]==400,'撤销账号权限后仍可接回响应')
        finally:
            with database:
                database.execute("UPDATE api_tokens SET blocked_accounts='' WHERE token='synthetic-key'")
        require(len(Upstream.calls)==initial_count+4,'重复回填产生了新模型提交')
        verify_parallel_tool_mapping(6)
        append_results(original[1],2)
        status,raw=request(base+'generateContent',body)
        wait_idle()
        require(status==200 and '本地TLS回复'.encode() in raw and len(Upstream.calls)==initial_count+5,
            '重复响应的下一轮工具调用无法回填')
        require(request(base+'generateContent',body)==(status,raw) and len(Upstream.calls)==initial_count+5,
            '普通 JSON 重试产生了新生成或变更结果')
    finally:
        Upstream.held_requests.pop(marker,None)
    return len(Upstream.calls)-initial_count


def verify_shared_models(request, request_ids, wait_idle):
    """交替调用两个目录模型。@param request 真实网关入口。@param request_ids 根请求记录。@param wait_idle 实际收口。@return 上游和进程证据。"""
    runtime = []
    submitted = []
    body = {'contents': [{'role': 'user', 'parts': [{'text': '合成跨模型验证'}]}]}
    expected = [*SHARED_MODELS, MODEL]
    for model in expected:
        status, raw = request('/v1beta/models/' + model + ':generateContent', body)
        require(status == 200 and json.loads(raw)['usageMetadata']['totalTokenCount'] == 7,
            '跨模型请求失败：' + model + ' ' + str(status) + ' ' + raw.decode()[:350])
        wait_idle()
        request_id = request_ids[-1]
        until = time.monotonic() + 10
        while True:
            status, raw = request('/admin/request-diagnostics/' + request_id, admin=True)
            detail = json.loads(raw)
            if status == 200 and detail['request']['finished_at']:
                break
            require(time.monotonic() < until, '跨模型请求诊断尚未收口')
            time.sleep(.1)
        attempt, = detail['attempts']
        require(attempt['context']['submitted_model'] == SHARED_MODELS[model], '提交的原生模型与目录不一致')
        runtime.append(attempt['runtime'])
        submitted.append(Upstream.calls[-1]['body']['model'])
    require(len(Upstream.calls) == len(expected) and submitted == expected, '实际上游模型或调用次数不符')
    require(len({item['worker_pid'] for item in runtime}) == 1
        and len({item['worker_id'] for item in runtime}) == 1, '切换模型造成热进程重建')
    require([item['warm_hit'] for item in runtime] == [False, True, True]
        and all(item['start_source'] == 'exec' for item in runtime), '请求诊断与实际热复用不一致')
    return {'passed': True, 'same_pid': runtime[0]['worker_pid'], 'upstream_models': submitted,
        'warm_hits': [item['warm_hit'] for item in runtime], 'synthetic_native_model_submissions': len(Upstream.calls)}


def verify_live_capacity(request, wait_idle, base):
    """在真实流仍打开时验证 3→4→3。@param request 公共入口。@param wait_idle 真实退役观察。@param base 模型地址。@return 脱敏结果。"""
    def generate(marker):
        """提交一个被合成上游暂停的流。@param marker 测试标记。@return HTTP 结果。"""
        body = {'contents': [{'role': 'user', 'parts': [{'text': marker}]}]}
        return request(base + 'streamGenerateContent?alt=sse', body)

    def sender_status():
        """读取实际同代监督器和进程数。@return 当前状态。"""
        call = Request('http://127.0.0.1:8091/internal/status', headers={'authorization': 'Bearer ' + SECRET})
        with urlopen(call, timeout=5) as response:
            return json.load(response)['agy']

    def wait_queued():
        """确认网关实际登记了一笔排队。@return 无。"""
        until = time.monotonic() + 10
        while time.monotonic() < until:
            status, raw = request('/admin/runtime/accounts/1/lease', admin=True)
            if status == 200 and json.loads(raw)['waiting']:
                return
            time.sleep(.05)
        raise ValueError('网关未登记待执行请求')

    markers = [f'AGY_LIVE_RESIZE_PROBE_{index}' for index in range(1, 6)]
    Upstream.held_requests.update((marker, (threading.Event(), threading.Event())) for marker in markers)
    events = [Upstream.held_requests[marker] for marker in markers]
    with ThreadPoolExecutor(max_workers=5) as pool:
        try:
            runs = [pool.submit(generate, marker) for marker in markers[:3]]
            require(all(event.wait(30) for event, _ in events[:3]), '原三路未到达合成上游')
            original = sender_status()
            runs.append(pool.submit(generate, markers[3]))
            wait_queued()
            require(not events[3][0].is_set(), '扩容前第四笔已经发送')
            status, raw = request('/admin/accounts/1', {'concurrency': 4}, admin=True)
            require(status == 200 and json.loads(raw)['concurrency'] == 4, '在线扩容失败：'+raw.decode()[:300])
            require(events[3][0].wait(30), '扩容后第四笔未到达合成上游')
            grown = sender_status()
            require(grown['max_workers'] == grown['allocated_workers'] == 4, '扩容后的实际物理进程不符')
            status, raw = request('/admin/accounts/1', {'concurrency': 3}, admin=True)
            require(status == 200 and json.loads(raw)['concurrency'] == 3, '在线缩容失败：'+raw.decode()[:300])
            shrunk = sender_status()
            require(shrunk['max_workers'] == 3 and shrunk['allocated_workers'] == 4, '缩容中断了既有进程')
            require(shrunk['controller']['pid'] == original['controller']['pid'], '监督器在调整中更换')
            runs.append(pool.submit(generate, markers[4]))
            wait_queued()
            events[0][1].set()
            require(runs[0].result(timeout=15)[0] == 200, '缩容后原请求失败')
            require(not events[4][0].is_set(), '缩容后新流抢占在途容量')
            events[1][1].set()
            require(events[4][0].wait(30), '在途收口后新流仍未执行')
            require(sender_status()['allocated_workers'] == 3, '缩容后实际进程未收敛')
        finally:
            for _, release in events:
                release.set()
        require(all(run.result(timeout=20)[0] == 200 for run in runs), '存在未完成的请求')
    wait_idle()
    require(len(Upstream.calls) == 5, '模型提交次数不符')
    return {'passed': True, 'capacity': [3, 4, 3], 'same_supervisor': True, 'model_submissions': len(Upstream.calls)}


def verify_messages_thinking_and_images(request, wait_idle, database):
    """核对 Messages 选号及两种协议下的图片回包。@param request 公共入口。
    @param wait_idle 发送器回收检查。@param database 合成账号库。@return 验证摘要。"""
    messages_path = '/v1/messages'
    gemini_base = '/v1beta/models/' + MODEL + ':'
    body = {'model': MODEL, 'max_tokens': 128, 'messages': [{'role': 'user', 'content': 'Messages reasoning fixture'}]}
    tier_cases = [
        ({}, MODEL),
        ({'thinking': {'type': 'enabled', 'budget_tokens': 1024}}, MESSAGES_LOW_MODEL),
        ({'thinking': {'type': 'adaptive'}, 'output_config': {'effort': 'low'}}, MESSAGES_LOW_MODEL),
        ({'thinking': {'type': 'enabled', 'budget_tokens': 1024}, 'output_config': {'effort': 'high'}}, MESSAGES_LOW_MODEL),
        ({'model': MESSAGES_LOW_MODEL, 'output_config': {'effort': 'high'}}, MESSAGES_LOW_MODEL),
        ({'output_config': {'effort': 'unknown'}}, MODEL),
    ]
    for config, expected in tier_cases:
        status, raw = request(messages_path, {**body, **config})
        require(status == 200 and Upstream.calls[-1]['body']['model'] == expected,
            f'Messages 思考档位未匹配原生目录：{config!r} {status} {raw[:350]!r}')
        wait_idle()

    native_body = {'contents': [{'role': 'user', 'parts': [{'text': 'Messages reasoning fixture'}]}],
        'generationConfig': {'maxOutputTokens': 128, 'thinkingConfig': {'thinkingLevel': 'LOW'}}}
    status, raw = request(gemini_base + 'generateContent', native_body)
    require(status == 200 and Upstream.calls[-1]['body']['model'] == MESSAGES_LOW_MODEL,
        f'原生 Gemini 思考档位回归失败：{status} {raw[:350]!r}')
    wait_idle()

    # 暂时只保留一个低档变体，分别验证 Messages 的可用性和 Gemini 的原匹配合同。
    usage, = database.execute("SELECT usage_data FROM accounts WHERE id=1").fetchone()
    variant_only = json.loads(usage)
    variant_only['capabilities']['model_mappings'].pop(MODEL)
    try:
        with database:
            database.execute("UPDATE accounts SET usage_data=? WHERE id=1", (json.dumps(variant_only),))
        status, raw = request(messages_path, {**body, 'output_config': {'effort': 'max'}})
        require(status == 200 and Upstream.calls[-1]['body']['model'] == MESSAGES_LOW_MODEL,
            f'Messages 目录缺档时未沿用原候选：{status} {raw[:350]!r}')
        wait_idle()
        before = len(Upstream.calls)
        native_body['generationConfig']['thinkingConfig'] = {'thinkingLevel': 'XHIGH'}
        status, raw = request(gemini_base + 'generateContent', native_body)
        require(status == 404 and len(Upstream.calls) == before and json.loads(raw)['error']['status'] == 'NOT_FOUND',
            f'原生 Gemini 的显式缺档语义改变：{status} {raw[:350]!r}')
    finally:
        with database:
            database.execute("UPDATE accounts SET usage_data=? WHERE id=1", (usage,))

    prompt = 'Messages image response fixture'
    image = {'mimeType': 'image/png', 'data': fixture_png((19, 73, 211))}
    expected_text = ['图片前文', f"![image](data:image/png;base64,{image['data']})", '图片后文']
    for streaming in (False, True):
        status, raw = request(messages_path, {**body, 'stream': streaming, 'messages': [{'role': 'user', 'content': prompt}]})
        require(status == 200, f'Messages 图片回包失败：{status} {raw[:350]!r}')
        if streaming:
            events = sse_frames(raw)
            text = [frame['delta']['text'] for frame in events
                if frame['type'] == 'content_block_delta' and frame['delta']['type'] == 'text_delta']
            require(events[-1]['type'] == 'message_stop' and events[-2]['delta']['stop_reason'] == 'end_turn',
                'Messages 图片流终态不完整')
        else:
            result = json.loads(raw)
            text = [part['text'] for part in result['content'] if part['type'] == 'text' and part['text']]
            require(result['stop_reason'] == 'end_turn', 'Messages 图片 JSON 终态不完整')
        require([part for part in text if part] == expected_text, 'Messages 图片数据或文本顺序发生变化')
        wait_idle()

        method = 'streamGenerateContent?alt=sse' if streaming else 'generateContent'
        status, raw = request(gemini_base + method, {'contents': [{'role': 'user', 'parts': [{'text': prompt}]}]})
        require(status == 200, f'原生 Gemini 图片回包失败：{status} {raw[:350]!r}')
        frames = sse_frames(raw) if streaming else [json.loads(raw)]
        responses = [candidate for frame in frames for candidate in frame.get('candidates', [])]
        parts = [part for candidate in responses for part in candidate['content']['parts'] if part != {'text': ''}]
        require(parts == [{'text': '图片前文'}, {'inlineData': image}, {'text': '图片后文'}]
            and responses[-1]['finishReason'] == 'STOP', '原生 Gemini 的 Part 或终态发生变化')
        wait_idle()
    return {'messages_thinking_cases': len(tier_cases) + 1, 'messages_image_response': 'json_and_sse',
        'gemini_native_format': 'json_and_sse'}


def verify_messages_read_truncation(request, wait_idle):
    """核对工具补充及旧前缀在真实 AGY 出站中的位置。@param request 公共 HTTP 入口。@param wait_idle 发送器回收检查。@return 实际请求数。"""
    path = '/v1/messages'
    initial_count = len(Upstream.calls)
    main = {'model': MODEL, 'max_tokens': 128, 'system': '固定的合成系统提示',
        'metadata': {'user_id': json.dumps({'session_id': 'synthetic-read-truncation'})},
        'messages': [{'role': 'user', 'content': 'Messages Read truncation fixture'}],
        'tools': [{'name': 'Read', 'input_schema': {'type': 'object', 'properties': {'file_path': {'type': 'string'}}}}]}
    status, raw = request(path, main)
    require(status == 200, f'Read 首轮失败：{status} {raw[:350]!r}')
    calls = [block for block in json.loads(raw)['content'] if block['type'] == 'tool_use']
    require(len(calls) == 1 and calls[0]['name'] == 'Read', '首轮未返回 Read 工具调用')
    notice = (f'[Truncated: {MESSAGES_READ_PATH}. Showing lines 1–200 of 420 total (24000 tokens). '
        'Read with offset=201 limit=200 for the next portion.]')
    notification = '<task-notification><status>completed</status></task-notification>'
    returned = '合成文件片段'
    history = main['messages'] + [{'role': 'assistant', 'content': calls}, {'role': 'user', 'content': [
        {'type': 'tool_result', 'tool_use_id': calls[0]['id'], 'content': returned}]}]
    continuation = {**main, 'messages': history + [{'role': 'system', 'content': [
        {'type': 'text', 'text': notice, 'cache_control': {'type': 'ephemeral'}},
        {'type': 'text', 'text': notification}]}]}
    status, raw = request(path, continuation)
    require(status == 200, f'带截断提示的续轮失败：{status} {raw[:350]!r}')
    reply = json.loads(raw)['content']
    wait_idle()
    later = {**main, 'messages': history + [{'role': 'system', 'content': notice},
        {'role': 'system', 'content': notification},
        {'role': 'assistant', 'content': reply}, {'role': 'user', 'content': '继续读取。'}]}
    status, raw = request(path, later)
    require(status == 200, f'带历史截断提示的下一轮失败：{status} {raw[:350]!r}')
    wait_idle()
    sent = [item['body']['request'] for item in Upstream.calls[initial_count:]]
    require(len(sent) == 3, 'Read 三轮的实际上游发送次数错误')
    for previous, current in zip(sent, sent[1:]):
        require(all(current[key] == previous[key] for key in ('systemInstruction', 'tools', 'sessionId')),
            '截断提示改变了出站系统提示、工具声明或会话')
        prefix = previous['contents']
        require(current['contents'][:len(prefix)] == prefix, 'Read 续轮改变了已发送的历史前缀')
        parts = [part for message in current['contents'] for part in message['parts']]
        results = [(index, part['functionResponse']) for index, part in enumerate(parts) if 'functionResponse' in part]
        require(len(results) == 1, '工具回填的出站次数错误')
        result_index, result = results[0]
        before = '\n'.join(part.get('text', '') for part in parts[:result_index])
        after = '\n'.join(part.get('text', '') for part in parts[result_index+1:])
        require(all(text not in before and after.count(text) == 1 for text in (notice, notification))
            and after.index(notice) < after.index(notification), '补充文本未按原顺序追加在工具回填之后')
        require(result['id'] == calls[0]['id'] and json.loads(result['response']['output'])['result'] == returned,
            'Read 续轮改变了工具 ID 或回填正文')
    return len(sent)


def verify_messages_search(request, wait_idle, database):
    """运行真实 Messages、同名工具回填和原版 WebSearch。@param request 公共 HTTP 入口。
    @param wait_idle 发送器回收检查。@param database 隔离账号库。@return 验证摘要。"""
    path = '/v1/messages'
    metadata = {'user_id':json.dumps({'session_id':'synthetic-messages-session'})}
    main = {'model':MODEL,'metadata':metadata,'max_tokens':128,'stream':True,
        'thinking':{'type':'adaptive'},'output_config':{'effort':'medium'},
        'system':[{'type':'text','text':'Messages system fixture'}],
        'messages':[{'role':'user','content':'Messages search fixture'},
            {'role':'system','content':[{'type':'text','text':'Trailing environment fixture'}]}],
        'tools':[{'name':'WebSearch','input_schema':{'type':'object','properties':{'query':{'type':'string'}}}},
            {'name':'mcp__fixture__read_item','input_schema':{'type':'object','properties':{'n':{'type':'integer'}}}}]}

    Binding.continuation_mode='history'
    try:
        status, raw = request(path, main)
    finally:
        Binding.continuation_mode='claim'
    require(status==200, f'Messages 主请求失败：{status} {raw[:350]!r}')
    require(Upstream.calls[-1]['body']['model'] == MODEL, '无目标档位时未选原同名模型')
    events=sse_frames(raw)
    require(events[0]['type']=='message_start' and events[-1]['type']=='message_stop', 'Messages SSE 事件边界错误')
    calls=[item['content_block'].copy() for item in events if item['type']=='content_block_start'
        and item['content_block']['type']=='tool_use']
    arguments=[json.loads(item['delta']['partial_json']) for item in events if item['type']=='content_block_delta'
        and item['delta']['type']=='input_json_delta']
    require([call['name'] for call in calls]==['WebSearch']+['mcp__fixture__read_item']*3, 'Messages 并行函数声明不完整')
    require([call['id'] for call in calls]==['call_msg_search','call_msg_read_1','call_msg_read_2','call_msg_read_3'], 'Messages 原生调用 ID 不一致')
    for call, args in zip(calls, arguments):
        call['input']=args

    with database:
        usage=json.dumps({'capabilities':{'model_mappings':Upstream.model_mappings}})
        database.execute("INSERT INTO accounts(id,name,email,platform,token,device_id,auth_type,access_token,refresh_token,oauth_expires_at,concurrency,auto_telemetry,auto_poll_usage,usage_data) VALUES(2,'alternate','alternate@example.test','antigravity','','','oauth','synthetic-alternate','synthetic-rt','2099-01-01T00:00:00Z',1,0,0,?)", (usage,))
        database.execute("INSERT INTO account_credential_states(account_id,generation,phase,updated_at_ms) VALUES(2,1,'ready',1)")
        database.execute("UPDATE api_tokens SET allowed_accounts='1,2' WHERE token='synthetic-key'")
        database.execute("INSERT INTO api_tokens(name,token,allowed_accounts,status) VALUES('other','synthetic-other','999','active')")

    def search(query, **tool_options):
        return {'model':MODEL,'metadata':metadata,'max_tokens':128,
            'messages':[{'role':'user','content':[{'type':'text','text':'Perform a web search for the query: '+query}]}],
            'tools':[{'name':'web_search','type':'web_search_20250305','max_uses':8,**tool_options}]}

    require(request(path, search('Different query'))[0]==400, '同会话查询串到了未关联的工具')
    status,_=request(path, search(SEARCH_QUERY), token='synthetic-other')
    require(status in (403,404,503), '另一个令牌取得了原搜索许可')
    status,raw=request(path,{**search(SEARCH_QUERY,allowed_domains=['iana.org']),'stream':True})
    require(status==200, f'关联 WebSearch 失败：{status} {raw[:350]!r}')
    blocks=[item['content_block'] for item in sse_frames(raw) if item['type']=='content_block_start']
    require([item['type'] for item in blocks]==['server_tool_use','web_search_tool_result'] and blocks[0]['id']==blocks[1]['tool_use_id'],
        'WebSearch SSE 调用和回执没有成对')
    require(isinstance(blocks[1]['content'],list) and [(item['title'],item['url']) for item in blocks[1]['content']]==[(SEARCH_QUERY,SEARCH_URL)],
        'WebSearch 原生来源不正确：'+str(blocks[1]['content']))
    require(sse_frames(raw)[-2]['usage']['server_tool_use']['web_search_requests']==1,'WebSearch 计数不正确')
    domain_cases=[
        ({'blocked_domains':['iana.org']},[]),
        ({'blocked_domains':['example.org']},[(SEARCH_QUERY,SEARCH_URL)]),
        ({'allowed_domains':['vertexaisearch.cloud.google.com']},[]),
        ({},[(SEARCH_QUERY,SEARCH_URL),(SEARCH_REDIRECT_TITLE,SEARCH_REDIRECT)]),
    ]
    for rules,expected in domain_cases:
        status,raw=request(path,search(SEARCH_QUERY,**rules))
        require(status==200, f'带域名规则的查询重读失败：{status} {raw[:350]!r}')
        found=json.loads(raw)['content'][1]['content']
        require(isinstance(found,list) and [(item['title'],item['url']) for item in found]==expected,
            f'域名过滤结果异常：{rules!r} {found!r}')
    grounded=[item for item in Upstream.requests if ':generateContent' in item['path']]
    require(len(grounded)==1 and grounded[0]['authorization']=='Bearer synthetic-at-1','WebSearch 未沿原账号执行或重复调用')

    response_parts=[{'type':'tool_result','tool_use_id':calls[i]['id'],'content':[{'type':'text','text':f'callback-{i}'}]}
        for i in (3,2,0,1)]
    continuation={**main,'stream':False,'output_config':{'effort':'low'},'messages':main['messages']+[
        {'role':'assistant','content':calls},{'role':'user','content':response_parts}]}
    status, raw = request(path, continuation)
    require(status==200 and json.loads(raw)['type']=='message' and json.loads(raw)['stop_reason']=='end_turn',
        f'Messages 回填未继续生成：{status} {raw[:350]!r}')
    wait_idle()
    require(Upstream.calls[-1]['body']['model'] == MODEL
        and Upstream.calls[-1]['authorization'] == 'Bearer synthetic-at-1', '不同 effort 的回填改变原账号或原生型号')
    sent=Upstream.calls[-1]['body']['request']['contents']
    results=[part['functionResponse'] for message in sent for part in message['parts'] if 'functionResponse' in part]
    require([item['id'] for item in results]==[item['id'] for item in calls], '工具回填没有按原调用身份归位')
    require([json.loads(item['response']['output'])['result'][0]['text'] for item in results]==[f'callback-{i}' for i in range(4)],
        '同名工具回填串值')
    require(any(part.get('thoughtSignature')=='c3ludGhldGljLXNpZw==' and part.get('functionCall',{}).get('id')==calls[0]['id']
        for message in sent for part in message['parts']), 'Messages 回填丢失了原生函数签名')

    status,raw=request(path,{'model':MODEL,'metadata':metadata,'max_tokens':128,
        'messages':[{'role':'user','content':'Next sticky turn fixture'}]})
    require(status==200 and Upstream.calls[-1]['authorization']=='Bearer synthetic-at-1','原始 Session ID 未延续选中账号')
    wait_idle()
    with database:
        database.execute("UPDATE api_tokens SET allowed_accounts='1' WHERE token='synthetic-key'")
        usage=json.dumps({'capabilities':{'model_mappings':Upstream.model_mappings,'media_inputs':{MODEL:{'image/png':True}}}})
        database.execute("UPDATE accounts SET usage_data=? WHERE id=1", (usage,))
    for query, success in [('Empty search fixture',True),('Failed search fixture',False),('Tool isolation fixture',False)]:
        status,raw=request(path,search(query))
        require(status==200, f'独立 WebSearch 未正常结束：{status} {raw[:350]!r}')
        content=json.loads(raw)['content'][1]['content']
        require(content==([] if success else {'type':'web_search_tool_result_error','error_code':'unavailable'}),
            f'搜索空结果和故障合同异常：{content!r}')
        wait_idle()
    require(not list(Path('/state/native').glob('*/state/search-*')), '搜索凭据目录未回收')
    require(not Path('/state/forbidden-search-probe').exists(), '独立 WebSearch 运行了未授权的命令工具')
    verify_messages_search_cancel(search('Cancelled search fixture'))
    data=fixture_png((231,194,7))
    status, raw=request(path,{'model':MODEL,'max_tokens':128,'messages':[{'role':'user','content':[
        {'type':'text','text':'After search fixture'},{'type':'image','source':{'type':'base64','media_type':'image/png','data':data}}]}]})
    require(status==200 and json.loads(raw)['content'][0]['text']=='本地TLS回复',f'搜索后图片请求未恢复：{status} {raw[:350]!r}')
    require(any(part.get('inlineData')=={'mimeType':'image/png','data':data}
        for message in Upstream.calls[-1]['body']['request']['contents'] for part in message['parts']), '图片没有进入真实 AGY 请求')
    wait_idle()
    result={'passed':True,'messages_sse_json':True,'parallel_results':4,'grounded_searches':4,'domain_filter_cases':1+len(domain_cases),
        'single_concurrency':True,'original_session_id':True,'image/png':True,'cancellation':True,'fixed_native_version':'1.5.9'}
    result.update(verify_messages_thinking_and_images(request, wait_idle, database))
    result['read_truncation_rounds'] = verify_messages_read_truncation(request, wait_idle)
    if Path('/opt/claude-code').is_file():
        result['claude_code_search_count']=verify_claude_code_search(wait_idle)
    status,raw=request('/admin/request-diagnostics?platform=antigravity&entry_protocol=anthropic_messages&page_size=50',admin=True)
    require(status==200 and any(row.get('original_session_id')=='synthetic-messages-session' for row in json.loads(raw)['items']),
        'Messages 诊断没有原始 Session ID')
    return result


def verify_messages_search_cancel(body):
    """在搜索上游待回包时关闭客户端。@param body 独立搜索请求。@return 无。"""
    connection=HTTPConnection('127.0.0.1',5674,timeout=15)
    try:
        connection.request('POST','/v1/messages',json.dumps({**body,'stream':True}),{
            'x-api-key':'synthetic-key','content-type':'application/json','user-agent':'claude-cli/2.1.293 (external, cli)'})
        require(Upstream.search_held.wait(12),'取消试验未达到真实搜索上游')
        connection.close()
        until=time.monotonic()+8
        request=Request('http://127.0.0.1:8091/internal/status',headers={'authorization':'Bearer '+SECRET})
        while time.monotonic()<until:
            with urlopen(request,timeout=3) as reply:
                if json.load(reply)['active']==0:
                    break
            time.sleep(.1)
        else:
            raise ValueError('客户端断开后发送器仍持有搜索活动')
        require(not list(Path('/state/native').glob('*/state/search-*')), '取消搜索留下凭据工作目录')
    finally:
        connection.close()
        Upstream.search_release.set()


def verify_claude_code_search(wait_idle):
    """真实客户端沿隔离网关执行一次搜索。@param wait_idle 发送器清理检查。@return 客户端已识别的搜索数。"""
    with tempfile.TemporaryDirectory(dir='/state') as directory:
        env={'HOME':directory,'PATH':'/usr/bin:/bin','TERM':'dumb','LANG':'C.UTF-8',
            'ANTHROPIC_BASE_URL':'http://127.0.0.1:5674','ANTHROPIC_API_KEY':'synthetic-key',
            'ANTHROPIC_MODEL':MODEL,'ANTHROPIC_DEFAULT_HAIKU_MODEL':MODEL,
            'CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC':'1','DISABLE_AUTOUPDATER':'1'}
        prompt='Messages search fixture. Use WebSearch for IANA Example Domains and report the source.'
        completed=subprocess.run(['/opt/claude-code','--print',prompt,'--model',MODEL,
            '--allowedTools','WebSearch','--output-format','stream-json','--verbose',
            '--no-session-persistence'],cwd=directory,env=env,text=True,capture_output=True,timeout=90)
        Path('/state/claude-code-stream.jsonl').write_text(completed.stdout,encoding='utf-8')
        events=[json.loads(line) for line in completed.stdout.splitlines()]
        callbacks=[block for event in events if event.get('type')=='user' for block in event['message']['content']
            if isinstance(block,dict) and block['type']=='tool_result']
        actual=sum(block.get('tool_use_id')=='call_msg_search' and SEARCH_URL in json.dumps(block) for block in callbacks)
        counts=[event['tool_use_result'].get('searchCount') for event in events if event.get('type')=='user'
            and isinstance(event.get('tool_use_result'),dict) and event['tool_use_result'].get('query')==SEARCH_QUERY]
        require(completed.returncode==0 and actual==1 and counts==[1] and events[-1].get('subtype')=='success',
            'Claude Code 未识别搜索回填或未继续生成：'+json.dumps(events[-2:],ensure_ascii=False)[:1800]+completed.stderr[:350])
        wait_idle()
        return counts[0]


def model_attempt(request, root):
    """读取指定根下的唯一真实发送尝试。@param request 网关入口。@param root HTTP 根。@return 尝试详情。"""
    until = time.monotonic() + 8
    while time.monotonic() < until:
        status, raw = request('/admin/request-diagnostics/' + root, admin=True)
        attempts = json.loads(raw).get('attempts', []) if status == 200 else []
        if len(attempts) == 1 and attempts[0].get('context', {}).get('native_model_calls'):
            return attempts[0]
        time.sleep(.04)
    raise ValueError('续轮样本缺少真实尝试记录')


def cancel_original_tool_turn(request, root, database):
    """通过本地发送器确认原工具请求退出。@param request 网关入口。@param root HTTP 根。@param database 合成库。@return 无。"""
    prior = model_attempt(request, root)
    token_id = database.execute("SELECT id FROM api_tokens WHERE token='synthetic-key'").fetchone()[0]
    command = Request('http://127.0.0.1:8091/internal/agy/cancel',
        data=json.dumps({'account_id': 1, 'environment_id': ENVIRONMENT, 'generation': 1,
            'request_id': prior['attempt_id'], 'api_token_id': token_id}).encode(),
        headers={'authorization': 'Bearer ' + SECRET, 'content-type': 'application/json'})
    with urlopen(command, timeout=5) as response:
        require(response.status == 204, '未登记隔离旧原生轮退出')


def verify_continuation_modes(request, wait_idle, database, request_ids):
    """通过真实网关、发送器和原版内核验证三种续轮及空流。@param request 网关入口。@param wait_idle 原生收口。@param database 合成库。@param request_ids 请求根。@return 脱敏验收摘要。"""
    path='/v1/messages'
    observed={}

    def issue(label):
        """交付完整工具回调并构造真实客户端回填。@param label 合成标记。@return 原请求和回填。"""
        body={'model':MODEL,'max_tokens':128,'messages':[{'role':'user','content':'TLS_SYNTHETIC_TOOL '+label}],
              'metadata':{'user_id':json.dumps({'session_id':'synthetic-continuation'})},
              'tools':[{'name':'synthetic_tool','input_schema':{'type':'object','properties':{'x':{'type':'integer'}}}}]}
        status,raw=request(path,body)
        require(status==200,'原版工具轮未交付 '+raw[:180].decode(errors='replace'))
        result=json.loads(raw)
        calls=[item for item in result['content'] if item['type']=='tool_use']
        require(len(calls)==1 and result['stop_reason']=='tool_use','合成工具轮归属错误')
        body['messages'].extend([{'role':'assistant','content':result['content']},
            {'role':'user','content':[{'type':'tool_result','tool_use_id':calls[0]['id'],'content':'真实合成工具结果'}]}])
        return request_ids[-1],body

    prompt='''Describe your most recent action in 3-5 words using present tense (-ing). Name the file or function, not the branch. Do not use tools.

Good: "Reading runAgent.ts"
Good: "Fixing null check in validate.ts"
Good: "Running auth module tests"
Good: "Adding retry logic to fetchUser"

Bad (past tense): "Analyzed the branch diff"
Bad (too vague): "Investigating the issue"
Bad (too long): "Reviewing full branch diff and AgentTool.tsx integration"
Bad (branch name): "Analyzed adam/background-summary branch diff"'''

    def summary(body, streaming=False, previous=False):
        """核对本地后台摘要响应。@param body 主请求回填。@param streaming 是否 SSE。@param previous 有无上次摘要。@return 无。"""
        root=copy.deepcopy(body)
        text=prompt.replace('\n\nGood:', '\n\nPrevious: "Checking earlier tool results" — say something NEW.\n\nGood:',1) if previous else prompt
        root['messages'][-1]['content'].append({'type':'text','text':text})
        if streaming:
            root['messages'].append({'role':'system','content':'UserPromptSubmit hook additional context: 合成当轮状态'})
        root['stream']=streaming
        status,raw=request(path,root)
        require(status==200,'后台摘要抢占真实工具结果 '+raw[:200].decode(errors='replace'))
        if streaming:
            require(any(item.get('delta',{}).get('text')=='Checking the tool result' for item in sse_frames(raw)),
                '后台摘要 SSE 缺少短状态')
        else:
            value=json.loads(raw)
            require(value['content']==[{'type':'text','text':'Checking the tool result'}]
                and value['usage']['input_tokens']==value['usage']['output_tokens']==0,'后台摘要非本地零用量回复')

    _,claim=issue('摘要并发')
    summary(claim)
    initial=len(Upstream.calls)
    entered,release=threading.Event(),threading.Event()
    Binding.hold_preparation=(entered,release)
    with ThreadPoolExecutor(max_workers=2) as pool:
        continued=pool.submit(request,path,claim)
        try:
            require(entered.wait(20),'真实回填未进入领取后的发送准备')
            summary(claim,streaming=True,previous=True)
        finally:
            release.set()
        require(continued.result()[0]==200,'真实工具回填失败')
    wait_idle()
    summary(claim,previous=True)
    require(len(Upstream.calls)==initial+1,'摘要导致重复原生提交')

    for mode, close_worker, expected_path in [('claim',False,'claim'),('history',False,'history'),
            ('claim_with_history',False,'claim'),('claim_with_history',True,'history')]:
        Binding.continuation_mode=mode
        start=len(Upstream.calls)
        root,body=issue(f'{mode} {close_worker}')
        old_contents=Upstream.calls[-1]['body']['request']['contents']
        closed_at=time.monotonic()
        if close_worker:
            cancel_original_tool_turn(request, root, database)
        if expected_path=='history':wait_idle()
        closed_ms=round(1000*(time.monotonic()-closed_at)) if expected_path=='history' else None
        Binding.continuation_mode='claim'
        if mode=='history':
            foreign_session={**body,'metadata':{'user_id':json.dumps({'session_id':'synthetic-other-session'})}}
            bad_signature=copy.deepcopy(body)
            next(block for block in bad_signature['messages'][-2]['content'] if block['type']=='tool_use')['signature']='foreign-signature'
            require(request(path,foreign_session)[0]==400 and request(path,bad_signature)[0]==400
                and request(path,body,token='synthetic-other')[0]==400 and len(Upstream.calls)==start+1,
                '历史接续接受了其他会话、签名或调用方的回填')
        resumed_at=time.monotonic()
        status,raw=request(path,body)
        continuation_root=request_ids[-1]
        require(status==200 and json.loads(raw)['stop_reason']=='end_turn',
            '真实接续失败 '+raw[:230].decode(errors='replace'))
        resumed_ms=round(1000*(time.monotonic()-resumed_at))
        wait_idle()
        replay_status,replay_raw=request(path,body)
        require(replay_status==200 and json.loads(raw)['content']==json.loads(replay_raw)['content']
            and len(Upstream.calls)==start+2,'同一回填未复用原调度结果')
        if mode=='history':
            conflicting=copy.deepcopy(body)
            conflicting['messages'][-1]['content'][0]['content']='不同的合成工具结果'
            require(request(path,foreign_session)[0]==400 and request(path,conflicting)[0]==400
                and len(Upstream.calls)==start+2,'历史重读接受了其他会话或不同正文')
        sample=model_attempt(request, continuation_root)
        context=sample['context']
        require(context['tool_continuation_mode']==mode and context['tool_continuation_path']==expected_path,
            '保存新配置影响已发出工具批次')
        if close_worker:
            require(context.get('tool_continuation_reason')=='original_closed','领取兜底缺少确认退出的原因')
        contents=Upstream.calls[-1]['body']['request']['contents']
        require(contents[:len(old_contents)]==old_contents,'接续更改了缓存前缀')
        items=[part for turn in contents for part in turn['parts']]
        require(any(item.get('thoughtSignature')=='c3ludGhldGljLXNpZw==' for item in items)
            and sum('functionResponse' in item for item in items)==1,'历史接续漏掉真实结果或签名')
        observed[f'{mode}/{expected_path}']={'close_ms':closed_ms,'resume_ms':resumed_ms,
            'first_output_ms':sample['first_output_ms']}

    gemini_path=f'/v1beta/models/{MODEL}:generateContent'
    gemini={'contents':[{'role':'user','parts':[{'text':'TLS_SYNTHETIC_TOOL GEMINI_CLAIM_SIGNATURE'}]}],
        'tools':[{'functionDeclarations':[{'name':'synthetic_tool','parameters':{
            'type':'object','properties':{'x':{'type':'integer'}}}}]}]}
    Binding.continuation_mode='claim'
    status,raw=request(gemini_path,gemini)
    require(status==200,'Gemini Claim 签名夹具未交付工具轮')
    content=json.loads(raw)['candidates'][0]['content']
    part=next(item for item in content['parts'] if 'functionCall' in item)
    require(part['thoughtSignature']=='c3ludGhldGljLXNpZw==','Gemini Claim 缺少实际源签名')
    part['thoughtSignature']='skip_thought_signature_validator'
    call=part['functionCall']
    gemini['contents'].extend([content,{'role':'user','parts':[{'functionResponse':{
        'id':call['id'],'name':call['name'],'response':{'value':'合成结果'}}}]}])
    before=len(Upstream.calls)
    status,raw=request(gemini_path,gemini)
    require(status==200 and request(gemini_path,gemini)==(status,raw) and len(Upstream.calls)==before+1,
        'Gemini Claim 添加占位签名后未续轮或重复发送 '+raw[:200].decode(errors='replace'))
    require(any(item.get('thoughtSignature')=='c3ludGhldGljLXNpZw=='
        for turn in Upstream.calls[-1]['body']['request']['contents'] for item in turn['parts']),
        'Gemini Claim 回填未还原实际源签名')
    wait_idle()

    for marker, expected, source_status in [('',503,200),('TLS_SYNTHETIC_EOF_SHORT',500,500),
            ('TLS_SYNTHETIC_EOF_SHORT TLS_SYNTHETIC_EOF_TEXT',200,500)]:
        body={'model':MODEL,'max_tokens':128,'stream':True,
            'messages':[{'role':'user','content':'TLS_SYNTHETIC_USAGE_EOF '+marker}]}
        status,raw=request(path,body)
        root=request_ids[-1]
        wait_idle()
        require(status==expected,f'用量开流门槛不符 {status} '+raw[:180].decode(errors='replace'))
        if status==200:
            require(b'event: error' in raw and b'event: message_stop' not in raw,'有效正文后的错误终态丢失')
        else:
            require(json.loads(raw)['type']=='error','首块前没有返回 Messages HTTP 错误')
        fields=model_attempt(request, root)['context']
        require(fields.get('observed_control_http_status')==source_status
            and fields.get('native_source_terminal') is False and fields.get('native_receive_ended') is True,
            '原生收流证据缺少实际控制状态')
        if source_status==500:
            require(fields.get('control_error_detail')=='unexpected_eof','截断未保留原生响应读取错误')
    return {'continuation_modes':observed,'agent_summary':True,'empty_streams':True,
        'gemini_claim_signature_rewritten':True,'real_model_submissions':0}


def verify_system_reminder(request, wait_idle, database, request_ids):
    """比较账号开关的原生出站与续轮。@param request 网关入口。@param wait_idle 原生收口。@param database 合成库。@param request_ids 请求根。@return 脱敏结果。"""
    option = 'agy_system_prompt_as_user_reminder'
    homoglyph = 'agy_system_prompt_homoglyph_enabled'
    account_path = '/admin/accounts/1'
    messages_path = '/v1/messages'
    neutral = (
        "Use the provided context to answer the user's request. "
        "When working on multi-step tasks or calling tools, briefly share your progress and explain what you are doing and why. "
        "For strict-format requests such as JSON-only output, or auxiliary tasks such as compaction, summaries, titles, and classification, "
        "return only the requested output."
    )
    sample = ['ABC system', '中文 {x: 3}']
    converted = ['ΑΒС ѕуѕtеm', '中文 {х: 3}']
    user_prompt = 'TLS_SYNTHETIC_TOOL read a sample record'
    result_text = 'SYNTHETIC_RECORD_OK'

    def save(enabled, glyphs):
        status, raw = request(account_path, {option: enabled, homoglyph: glyphs}, admin=True)
        require(status == 200 and json.loads(raw)[option] is enabled
            and json.loads(raw)[homoglyph] is glyphs, '账号开关未保存')

    def verify_wire(body, texts, moved):
        sys_text = '\n'.join(part.get('text', '') for part in body['systemInstruction']['parts'])
        user_text = '\n'.join(part.get('text', '') for part in body['contents'][0]['parts'])
        source = '\n'.join(texts)
        wrapped = f'<system-reminder>\n{source}\n</system-reminder>'
        require(body['contents'][0]['role'] == 'user' and user_prompt in user_text, '首条用户消息内容异常')
        require(sys_text == (neutral if moved else source)
            and user_text.count(wrapped) == int(moved), '实际 TLS 的系统文本及提醒位置异常')

    status, raw = request(account_path, admin=True)
    require(status == 200 and json.loads(raw)[option] is False, '已创建账号的试验开关默认值错误')
    declarations = []
    observed = {}
    configured = (False, False)
    cases = [
        ('off', 'claim', False, False, False, False),
        ('on', 'claim', True, True, False, False),
        ('homoglyph_only', 'claim', False, False, True, False),
        ('both', 'claim', True, True, True, False),
        ('close_while_waiting', 'claim', True, False, False, False),
        ('open_while_waiting', 'history', False, True, False, False),
        ('history_fallback', 'claim_with_history', True, True, True, True),
    ]
    for label, mode, original, current, glyphs, forced_exit in cases:
        if configured != (original, glyphs):
            save(original, glyphs)
        Binding.continuation_mode = mode
        session_id = f'synthetic-reminder-{label}'
        body = {
            'model': MODEL, 'max_tokens': 128,
            'system': [{'type': 'text', 'text': text} for text in sample],
            'messages': [{'role': 'user', 'content': user_prompt}],
            'tools': [{'name': 'synthetic_tool', 'input_schema': {
                'type': 'object', 'properties': {'x': {'type': 'integer'}},
            }}],
        }
        first = len(Upstream.calls)
        status, raw = request(messages_path, body, session_id=session_id)
        require(status == 200, f'{label} 原工具轮请求失败 {status} {raw[:180]!r}')
        root = request_ids[-1]
        output = json.loads(raw)
        calls = [block for block in output['content'] if block['type'] == 'tool_use']
        require(output['stop_reason'] == 'tool_use' and len(calls) == 1
            and calls[0]['name'] == 'synthetic_tool'
            and calls[0]['input'] == {'x': 1}, f'{label} 客户端工具调用不完整')
        initial = Upstream.calls[first]['body']['request']
        declarations.append(initial['tools'])
        expected = converted if glyphs else sample
        verify_wire(initial, expected, original)
        body['messages'].extend([
            {'role': 'assistant', 'content': output['content']},
            {'role': 'user', 'content': [
                {'type': 'tool_result', 'tool_use_id': calls[0]['id'], 'content': result_text},
            ]},
        ])
        next_texts = expected
        if label == 'close_while_waiting':
            next_texts = ['Synthetic instruction for the next generation.']
            body['system'] = next_texts[0]
        if current != original:
            save(current, glyphs)
        configured = (current, glyphs)
        if forced_exit:
            cancel_original_tool_turn(request, root, database)
        expected_path = 'history' if mode == 'history' or forced_exit else 'claim'
        if expected_path == 'history':
            wait_idle()

        status, raw = request(messages_path, body, session_id=session_id)
        continuation = request_ids[-1]
        require(status == 200, f'{label} 回填失败 {status} {raw[:180]!r}')
        response = json.loads(raw)
        text = ''.join(block.get('text', '') for block in response['content'] if block['type'] == 'text')
        require(response['stop_reason'] == 'end_turn' and text == '本地TLS回复', f'{label} 缺少有效回填终态')
        wait_idle()
        context = model_attempt(request, continuation)['context']
        replay_status, replay_raw = request(messages_path, body, session_id=session_id)
        require(replay_status == 200 and json.loads(replay_raw)['content'] == response['content']
            and len(Upstream.calls) == first + 2,
            f'{label} 回填重读异常 {replay_status} 提交次数 {len(Upstream.calls) - first} {replay_raw[:180]!r}')
        require(context['tool_continuation_mode'] == mode
            and context['tool_continuation_path'] == expected_path, f'{label} 实际续轮模式异常')
        policy = context['system_prompt_policy']
        require(policy['source'] == ('cortex_user_reminder' if current else 'cortex_custom_system')
            and policy['changed'] is glyphs, f'{label} 原生处理回执来源或转换标记异常')
        if forced_exit:
            require(context.get('tool_continuation_reason') == 'original_closed', '历史兜底缺少退出确认')

        wire = Upstream.calls[first + 1]['body']['request']
        verify_wire(wire, next_texts, current)
        parts = [part for content in wire['contents'] for part in content['parts']]
        actual_calls = [part for part in parts if 'functionCall' in part]
        actual_results = [part['functionResponse'] for part in parts if 'functionResponse' in part]
        require(len(actual_calls) == len(actual_results) == 1
            and actual_calls[0]['thoughtSignature'] == 'c3ludGhldGljLXNpZw=='
            and actual_results[0]['id'] == actual_calls[0]['functionCall']['id']
            and actual_results[0]['name'] == 'synthetic_tool'
            and result_text in json.dumps(actual_results[0]), f'{label} 真实调用、签名或结果错误')
        observed[label] = {'path': expected_path, 'synthetic_model_calls': 2}
    require(all(definitions == declarations[0] for definitions in declarations), '两组工具声明存在差异')

    start = len(Upstream.calls)
    status, _ = request(f'/v1beta/models/{MODEL}:generateContent', {
        'systemInstruction': {'parts': [{'text': sample[0]}]},
        'contents': [{'role': 'user', 'parts': [{'text': 'Inspect the synthetic sample.'}]}],
    })
    wait_idle()
    require(status == 200 and len(Upstream.calls) == start + 1, 'Gemini 原生直连接口执行异常')
    wire = Upstream.calls[-1]['body']['request']
    require(wire['systemInstruction']['parts'] == [{'text': converted[0]}],
        'Messages 账号开关改变了 Gemini 直连系统段')
    return {'system_reminder': observed, 'gemini_direct': True, 'real_model_submissions': 0}


def receipt_fixture_gate(operation=None):
    """向断网夹具发布本地维护门禁。@param operation 维护 UUID。@return 本次代次。"""
    directory=Path('/state/receipt-gate')
    directory.mkdir(exist_ok=True)
    epoch=str(uuid.uuid4())
    record={'schema_version':1,'deployment':'synthetic','operation_id':operation,'epoch':epoch,
        'phase':'blocked' if operation else 'idle','target_release':None,
        'revision':str(uuid.uuid4()),'created_at':'2026-01-01T00:00:00Z'}
    temporary=directory/'admission.tmp'
    with os.fdopen(os.open(temporary,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600),'w') as stream:
        json.dump(record,stream)
    temporary.replace(directory/'admission.json')
    return epoch


def verify_tool_receipts(request, wait_idle, database, request_ids, restart_gateway):
    """核对并发帧及续轮回执。@param request 公开请求。@param wait_idle 原生收口。@param database 合成 SQLite。@param request_ids 请求根。@param restart_gateway 重启合成网关。@return 验证摘要。"""
    path='/v1/messages'

    def append_results(body, message):
        """以真实工具 ID 续轮。@param body 原请求。@param message 原响应。@return 无。"""
        calls=[part for part in message['content'] if part['type']=='tool_use']
        require(len(calls)==1 and message['stop_reason']=='tool_use','主工具批次缺失')
        body['messages'].extend([{'role':'assistant','content':message['content']},
            {'role':'user','content':[{'type':'tool_result','tool_use_id':calls[0]['id'],'content':'真实合成回填'}]}])

    def issue(marker):
        """生成真实待回填工具轮。@param marker 合成场景。@return 回填请求。"""
        body={'model':MODEL,'max_tokens':128,'thinking':{'type':'enabled','budget_tokens':1024,'display':'summarized'},
            'metadata':{'user_id':json.dumps({'session_id':'fixture-tool-receipt'})},
            'messages':[{'role':'user','content':marker}],
            'tools':[{'name':'synthetic_tool','input_schema':{'type':'object','properties':{'x':{'type':'integer'}}}}]}
        status,raw=request(path,body)
        require(status==200,'前驱工具轮请求失败 '+raw[:200].decode(errors='replace'))
        append_results(body,json.loads(raw))
        return body

    def detail(root, *, replay=False):
        """等待实际诊断写入。@param root 请求根。@param replay 是否重读。@return 诊断详情。"""
        until=time.monotonic()+20
        while time.monotonic()<until:
            status,raw=request('/admin/request-diagnostics/'+root,admin=True)
            if status==200:
                value=json.loads(raw)
                if value['request'].get('finished_at') and (replay or value['attempts']):return value
            time.sleep(.04)
        raise ValueError('回填请求缺少诊断终态')

    success=issue('AGY_RECEIPT_OWNERSHIP')
    status,raw=request(path,{**success,'stream':True})
    success_root=request_ids[-1]
    require(status==200 and b'event: message_stop' in raw and b'event: error' not in raw
        and b'AGY_RECEIPT_SIDE_' not in raw,'两笔并发独立调用影响了主工具交付 '+raw[-250:].decode(errors='replace'))
    lines=[json.loads(line) for line in Path('/state/fixture-tool-owners.ndjson').read_text().splitlines()]
    starts={line['side']:line['call_id'] for line in lines if line['event']=='model_start' and line['side'] is not None}
    start_offsets=[index for index,line in enumerate(lines) if line['event']=='model_start' and line['side'] is not None]
    side_frames=[(index,line) for index,line in enumerate(lines) if line['event']=='gemini_response' and line['side'] is not None]
    require(set(starts)=={0,1} and {line['side'] for _,line in side_frames}=={0,1}
        and all(line['call_id']==starts[line['side']] and line['raw_epoch']==1 for _,line in side_frames)
        and max(start_offsets)<side_frames[0][0]
        and all(line['event']!='model_end' for line in lines[:side_frames[0][0]+1]),
        '并发 SDK 原始帧与实际独立调用归属不一致')
    status,raw=request(path,success)
    require(status==200,'流式转非流式重读丢失主工具批次')
    next_body=copy.deepcopy(success)
    append_results(next_body,json.loads(raw))
    require(request(path,next_body)[0]==200,'主批次未沿原轨迹完成回填')
    wait_idle()

    failed=issue('AGY_RECEIPT_FAIL')
    started=time.monotonic()
    status,_=request(path,{**failed,'stream':True})
    failure_root=request_ids[-1]
    require(status==500,'原失败样本应保留真实控制 500')
    wait_idle()
    failure_context=detail(failure_root)['attempts'][0]['context']
    require(failure_context.get('observed_control_http_status')==500
        and failure_context.get('control_error_detail')=='unexpected_eof'
        and failure_context.get('native_source_terminal') is False,'真实失败应来自用量后的原生读取截断')
    count=len(Upstream.calls)
    retry=copy.deepcopy(failed)
    retry['thinking'].pop('display')
    with ThreadPoolExecutor(max_workers=4) as pool:
        results=list(pool.map(lambda _:request(path,retry),range(16)))
    require(all(status==400 and b'AGY_TOOL_CONTINUATION_TERMINAL' in raw for status,raw in results)
        and len(Upstream.calls)==count+1,'失败恢复没有共享唯一次历史尝试 '+str([status for status,_ in results]))
    wait_idle()

    time.sleep(max(0,125-(time.monotonic()-started)))
    status,raw=request(path,success)
    require(status==410,'成功响应帧未按生成预算回收 '+raw[:200].decode(errors='replace'))
    recorded=detail(request_ids[-1],replay=True)
    original=detail(success_root)
    context=recorded['request']['context']
    require(recorded['request']['attempt_count']==0 and not recorded['attempts']
        and context['replay_of_request_id']==success_root and context['replay_of_attempt_id']==original['attempts'][0]['attempt_id']
        and context['replay_submission_state']=='model_observed','成功过期诊断未关联原尝试')
    status,raw=request(path,retry)
    require(status==400 and b'AGY_TOOL_CONTINUATION_TERMINAL' in raw,'失败回执到期后恢复上限丢失')
    different=copy.deepcopy(retry)
    different['messages'][-1]['content'][0]['content']='不同合成回填'
    other_session={**retry,'metadata':{'user_id':json.dumps({'session_id':'fixture-other-receipt'})}}
    require(request(path,other_session)[0]==400 and request(path,different)[0]==400
        and request(path,retry,token='synthetic-other')[0]==400,'原回执接受了错误的会话、正文或令牌')
    with database:
        database.execute("UPDATE api_tokens SET blocked_accounts='1' WHERE token='synthetic-key'")
    try:
        require(request(path,retry)[0]==400,'撤销账号访问后仍接受原回执')
    finally:
        with database:
            database.execute("UPDATE api_tokens SET blocked_accounts='' WHERE token='synthetic-key'")
    require(len(Upstream.calls)==count+1,'失败终态后的重放产生额外模型调用')

    dropped=issue('AGY_RECEIPT_DROP')
    before=len(Upstream.calls)
    status,raw=request(path,{**dropped,'stream':True},first_chunk=True)
    require(status==200 and b'content_block_delta' in raw and b'message_stop' not in raw,'未在实际生成时断开客户端')
    status,raw=request(path,dropped)
    require(status==200 and '本地TLS回复'.encode() in raw and len(Upstream.calls)==before+1,
        '断开后同正文没有接回原生成')
    wait_idle()

    recoverable=issue('AGY_RECEIPT_FAIL_ONCE')
    require(request(path,recoverable)[0]==500,'重启前样本没有触发真实控制面失败')
    wait_idle()
    restart_gateway()
    amended=copy.deepcopy(recoverable)
    amended['messages'][-1]['content'].append({'type':'text','text':CUT_OFF_REWRITE})
    before=len(Upstream.calls)
    with ThreadPoolExecutor(max_workers=6) as pool:
        recovered=list(pool.map(lambda body:request(path,body),[amended,recoverable]*3))
    require(all(status==200 and '本地TLS回复'.encode() in raw for status,raw in recovered)
        and len(Upstream.calls)==before+1,'重启后未共用一次历史恢复 '+str([status for status,_ in recovered]))
    require(CUT_OFF_REWRITE in json.dumps(Upstream.calls[-1]['body'],ensure_ascii=False)
        or request(path,amended)[0]==200,'断流提示无法接回已生成的结果')
    wait_idle()

    persisted=issue('TLS_SYNTHETIC_TOOL RECEIPT_SUCCESS_STORAGE_ERROR')
    with database:
        database.execute("""CREATE TRIGGER fixture_fail_success BEFORE UPDATE OF phase ON agy_tool_receipts
            WHEN NEW.phase='success' BEGIN SELECT RAISE(ABORT,'synthetic receipt write failure'); END""")
    try:
        before=len(Upstream.calls)
        status,raw=request(path,{**persisted,'stream':True})
        require(status==200 and b'event: message_stop' in raw and b'event: error' not in raw,
            '成功回执存储失败污染了已交付流')
        require(request(path,persisted)[0]==200 and len(Upstream.calls)==before+1,
            '成功回执存储失败触发重复模型发送')
    finally:
        with database:
            database.execute('DROP TRIGGER fixture_fail_success')
    wait_idle()

    interrupted=issue('AGY_RECEIPT_DROP RECEIPT_GATE_CUTOVER')
    before=len(Upstream.calls)
    retry_rows=database.execute("SELECT COUNT(*) FROM agy_tool_receipts WHERE phase='retry'").fetchone()[0]
    with ThreadPoolExecutor(max_workers=1) as executor:
        in_flight=executor.submit(request,path,{**interrupted,'stream':True})
        until=time.monotonic()+30
        while len(Upstream.calls)==before:
            require(time.monotonic()<until,'维护夹具未进入模型发送')
            time.sleep(.02)
        operation=str(uuid.uuid4())
        epoch=receipt_fixture_gate(operation)
        try:
            cutover=Request('http://127.0.0.1:5674/admin/runtime/system-update/cutover',
                data=json.dumps({'operation_id':operation,'epoch':epoch}).encode(),
                headers={'x-v3-service-token':SECRET,'x-api-key':'synthetic-admin','content-type':'application/json'})
            with urlopen(cutover,timeout=10) as response:
                require(json.load(response)['accepted'],'本地网关未接纳维护中断')
            require(b'event: message_stop' not in in_flight.result()[1],'维护夹具在原流成功后才触发')
            until=time.monotonic()+30
            while database.execute("SELECT COUNT(*) FROM agy_tool_receipts WHERE phase='retry'").fetchone()[0]<=retry_rows:
                require(time.monotonic()<until,'维护物理收口未保留恢复权')
                time.sleep(.05)
        finally:
            receipt_fixture_gate()
    status,raw=request(path,interrupted)
    require(status==200 and '本地TLS回复'.encode() in raw and len(Upstream.calls)==before+2,
        '维护已收口的同批回填未从完整历史恢复一次')
    wait_idle()
    return {'auxiliary_calls':2,'main_tool_delivered':True,'same_body_failure_retries':len(results),
        'recovery_attempts_after_original_failure':1,'expired_success_status':410,'exhausted_status':400,
        'restart_recovered':True,'reconnected_in_flight':True,'late_replays_linked':True,'synthetic_model_calls':len(Upstream.calls),
        'success_despite_storage_error':True,'cutover_recovered':True,'real_model_submissions':0}


def verify_reliability(request, wait_idle, base):
    """验证原生重复工具、外部搜索、无内存历史和超旧截止的长流。@param request 公开入口。@param wait_idle 真正原生收口。@param base 路由。@return 真实回环结果。"""
    def run_tool(marker, function, schema, expected, value_key):
        body={'contents':[{'role':'user','parts':[{'text':marker}]}],
            'tools':[{'functionDeclarations':[{'name':function,'parameters':schema}]}]}
        status,raw=request(base+'generateContent',body)
        require(status==200, f'{marker} 返回 {status} {raw[:300]!r}')
        parts=[part for part in json.loads(raw)['candidates'][0]['content']['parts'] if 'functionCall' in part]
        ids={part['functionCall']['id'] for part in parts}
        require(len(parts)==len(ids)==expected,'公开批次缺失、重复或未核对')
        results=[{'functionResponse':{'id':part['functionCall']['id'],'name':function,
            'response':{'value':part['functionCall']['args'][value_key]}}} for part in reversed(parts)]
        body['contents'].extend([{'role':'model','parts':parts},
            {'role':'user','parts':results+[{'text':'根据工具结果继续'}]}])
        status,raw=request(base+'generateContent',body)
        require(status==200 and '本地TLS回复'.encode() in raw, f'回填后续轮失败 {status} {raw[:250]!r}')
        wait_idle()
        if expected==2:verify_parallel_tool_mapping(2)
    schema={'type':'OBJECT','properties':{'x':{'type':'INTEGER'}}}
    run_tool('AGY_RELIABILITY_DUPLICATE','synthetic_tool',schema,2,'x')
    run_tool('AGY_RELIABILITY_DUPLICATE_IDENTICAL','synthetic_tool',schema,2,'x')
    run_tool('AGY_RELIABILITY_SEARCH','web_search',{},1,'query')

    invalid={'contents':[{'role':'user','parts':[{'text':'AGY_RELIABILITY_NUMERIC_ID'}]}],
        'tools':[{'functionDeclarations':[{'name':'synthetic_tool','parameters':schema}]}]}
    status,raw=request(base+'generateContent',invalid)
    require(status>=400 and b'functionCall' not in raw,'非法工具 ID 获得待回填批次')
    wait_idle()
    before=len(Upstream.calls)
    history={'contents':[{ 'role':'user','parts':[{'text':'历史启动'}]},
        {'role':'model','parts':[{'functionCall':{'name':'synthetic_tool','id':'independent-history','args':{'x':4}}}]},
        {'role':'user','parts':[{'functionResponse':{'name':'synthetic_tool','id':'independent-history','response':{'value':4}}}]},
        {'role':'user','parts':[{'text':CUT_OFF_REWRITE}]}],
        'tools':invalid['tools']}
    status,raw=request(base+'generateContent',history)
    require(status==200 and '本地TLS回复'.encode() in raw,'合法独立历史无法续轮 '+str(status))
    require(request(base+'generateContent',history)==(status,raw) and len(Upstream.calls)==before+1,
        '无内存历史重读重复提交')
    malformed=copy.deepcopy(history)
    malformed['contents'][2]['parts'][0]['functionResponse']['id']='unknown'
    require(request(base+'generateContent',malformed)[0]==400 and len(Upstream.calls)==before+1,'错误历史进入原生生成')
    wait_idle()
    Binding.long_generation=True
    Upstream.model_catalog_host='daily-cloudcode-pa.googleapis.com'
    rules=[{'category':category,'threshold':'BLOCK_MEDIUM_AND_ABOVE'} for category in (
        'HARM_CATEGORY_HARASSMENT','HARM_CATEGORY_HATE_SPEECH',
        'HARM_CATEGORY_SEXUALLY_EXPLICIT','HARM_CATEGORY_DANGEROUS_CONTENT')]
    start=time.monotonic()
    status,raw=request(base+'streamGenerateContent?alt=sse',
        {'contents':[{'role':'user','parts':[{'text':'AGY_RELIABILITY_LONG'}]}],'safetySettings':rules})
    elapsed=time.monotonic()-start
    frames=sse_frames(raw)
    final=frames[-1] if frames else {}
    require(status==200 and 120<elapsed<240 and final['candidates'][0]['finishReason']=='STOP'
        and final['usageMetadata']['totalTokenCount']==7 and '长生成结束'.encode() in raw
        and Upstream.calls[-1]['body']['request']['safetySettings']==rules,'长流没有越过 120 秒完整结束')
    wait_idle()
    return {'duplicate_id_batches':2,'external_search_query':True,'invalid_id_rejected':True,
        'history_without_turn':True,'elapsed_seconds':round(elapsed,3),'real_model_submissions':0}


def inside(homoglyph=False,capture_off=False,png=False,installed_adapter=False,kernel_selection=False,tool_deadlines=False,parallel_tools=False,
           *, shared_models=False, live_capacity=False, messages_search=False, continuation_modes=False,
           tool_receipts=False, system_reminder=False, reliability=False):
    """执行真实公共业务。@param homoglyph 检验系统策略。@param capture_off 验证关闭采集。@param png 核对图片与工具历史。@param installed_adapter 使用镜像内适配器。@param kernel_selection 验证内核切换。@param tool_deadlines 验证跨首轮期限的工具链。@param parallel_tools 验证同名工具。@return 脱敏验证摘要。"""
    require(os.geteuid()==1001,'原生业务探针必须使用UID1001')
    os.umask(0o077)
    Upstream.png_support=png
    Upstream.messages_search=messages_search
    Upstream.system_reminder=system_reminder
    if messages_search:
        Upstream.model_mappings = {**Upstream.model_mappings, MESSAGES_LOW_MODEL: SHARED_MODELS['gemini-3.8-flash-low']}
    if shared_models:
        Upstream.model_mappings = SHARED_MODELS
    context=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain('/state/server.crt','/state/server.key')
    proxy=ThreadingHTTPServer(('127.0.0.1',19090),Proxy)
    proxy.context=context;proxy.daemon_threads=True
    binding=ThreadingHTTPServer(('127.0.0.1',8765),Binding)
    for server in [proxy,binding]:
        threading.Thread(target=server.serve_forever,daemon=True).start()
    config={'binding':{'account_id':1,'environment_id':ENVIRONMENT,'generation':1,'endpoint':'http://localhost:8091',
        'secret':SECRET,'release_id':'synthetic-release'},'proxy_url':'http://127.0.0.1:19090',
        'allowed_origin':'https://cloudcode-pa.googleapis.com','native_capture_dir':'/state/capture',
        'agy':{'protocol_version':1,'source_sha256':SOURCE_SHA,'module_root':'/opt/v3/python' if installed_adapter else '/opt/orchestrator',
            'binary_path':'/usr/local/bin/agy-1.5.9','work_root':'/state/native',
            'max_workers':3 if live_capacity else 1,'memory_mib':1536 if png or live_capacity or Path('/opt/claude-code').is_file() else 768}}
    if capture_off:config.pop('native_capture_dir')
    Path('/state/sender.json').write_text(json.dumps(config))
    if tool_receipts:
        receipt_fixture_gate()
        os.environ['V3_UPDATE_GATE_DIR']='/state/receipt-gate'
        os.environ['V3_ACCOUNT_RELEASE']=os.environ['V3_RELEASE']
    outputs=[];children=[]
    for executable,name in [('/opt/sender','sender'),('/opt/gateway','gateway')]:
        output=open('/state/'+name+'.log','wb');outputs.append(output)
        command=[executable]
        if Path('/opt/verify-lib/ld-linux-x86-64.so.2').is_file():
            command=['/opt/verify-lib/ld-linux-x86-64.so.2','--library-path','/opt/verify-lib',executable]
        children.append(subprocess.Popen(command,stdout=output,stderr=subprocess.STDOUT))
    request_ids=[]
    def request(path,body=None,admin=False,first_tool_frame=False,token='synthetic-key',*,session_id=None,first_chunk=False):
        """使用真实 HTTP 请求。@param path 路径。@param body 正文。@param admin 管理调用。@param first_tool_frame 首工具后退出。@param token 合成令牌。@param session_id 会话。@param first_chunk 首内容后退出。@return 状态与正文。"""
        headers={'x-api-key':'synthetic-admin' if admin else token,'content-type':'application/json'}
        if not admin:headers['X-Synthetic-Ingress']='never-upstream'
        if session_id is not None:headers['X-Session-Id']=session_id
        if (messages_search or continuation_modes or tool_receipts or system_reminder) and path=='/v1/messages':
            headers['user-agent']='claude-cli/2.1.293 (external, cli)' if body.get('stream') else 'python-httpx/0.28.1'
        value=Request('http://127.0.0.1:5674'+path,data=json.dumps(body).encode() if body is not None else None,headers=headers,
            method='PUT' if body is not None and (path=='/admin/settings' or path.startswith('/admin/accounts/')) else None)
        try:
            with urlopen(value,timeout=255 if reliability else 125) as response:
                if response.headers.get('x-cc2api-request-id'):request_ids.append(response.headers['x-cc2api-request-id'])
                if first_tool_frame or first_chunk:
                    received=[]
                    for line in response:
                        received.append(line)
                        if first_chunk and line.startswith(b'data: ') and json.loads(line[6:]).get('type')=='content_block_delta':
                            break
                        if line.startswith(b'data: ') and any('functionCall' in part
                            for candidate in json.loads(line[6:]).get('candidates',[])
                            for part in candidate.get('content',{}).get('parts',[])):
                            break
                    return response.status,b''.join(received)
                return response.status,response.read()
        except HTTPError as error:
            if error.headers.get('x-cc2api-request-id'):request_ids.append(error.headers['x-cc2api-request-id'])
            return error.code,error.read()
    def restart_gateway():
        """重启合成网关进程，保留同一个测试数据库。@return 无。"""
        children[-1].terminate()
        children[-1].wait(12)
        children[-1]=subprocess.Popen(command,stdout=outputs[-1],stderr=subprocess.STDOUT)
        until=time.monotonic()+25
        while time.monotonic()<until:
            require(children[-1].poll() is None,'重启后的隔离网关进程退出')
            try:
                if request('/api/hello')[0]==200:return
            except OSError:
                pass
            time.sleep(.05)
        raise ValueError('重启后隔离网关未就绪')
    def wait_idle():
        """等待原生退役及许可实际释放。@return 无。"""
        until=time.monotonic()+85
        while time.monotonic()<until:
            value=Request('http://127.0.0.1:8091/internal/status',headers={'authorization':'Bearer '+SECRET})
            with urlopen(value,timeout=5) as response:state=json.load(response)
            if state['active']==0:return
            time.sleep(.1)
        raise ValueError('固定原版活动许可未释放')
    try:
        until=time.monotonic()+30
        while time.monotonic()<until:
            require(all(child.poll() is None for child in children),'真实服务启动失败')
            try:
                status,_=request('/api/hello')
                sender_status=Request('http://127.0.0.1:8091/internal/status',
                    headers={'authorization':'Bearer '+SECRET})
                with urlopen(sender_status,timeout=2) as response:
                    sender=json.load(response)
                if status==200 and sender['environment_id']==ENVIRONMENT and sender['generation']==1:
                    break
            except OSError:
                time.sleep(.1)
        else:
            raise ValueError('隔离网关与发送器未同时就绪')
        database=sqlite3.connect('/state/gateway.sqlite')
        with database:
            database.execute("INSERT INTO accounts(id,name,email,platform,token,device_id,auth_type,access_token,refresh_token,oauth_expires_at,concurrency,auto_telemetry,auto_poll_usage,usage_data) VALUES(1,'synthetic','synthetic@example.test','antigravity','','','oauth','synthetic-at-1','synthetic-rt','2099-01-01T00:00:00Z',1,0,0,?)",
                (json.dumps({'capabilities':{'model_mappings':Upstream.model_mappings}}),))
            database.execute("INSERT INTO account_credential_states(account_id,generation,phase,updated_at_ms) VALUES(1,1,'ready',1)")
            database.execute("INSERT INTO api_tokens(name,token,allowed_accounts,status) VALUES('synthetic','synthetic-key','1','active')")
            if parallel_tools or continuation_modes or tool_receipts:
                database.execute("INSERT INTO api_tokens(name,token,allowed_accounts,status) VALUES('other','synthetic-other','1','active')")
            if live_capacity:
                database.execute('UPDATE accounts SET concurrency=3 WHERE id=1')
        require(request('/admin/settings',{'request_diagnostics_log_mode':'debug'},admin=True)[0]==200,'测试日志模式设置失败')
        base='/v1beta/models/'+MODEL+':'
        if system_reminder:
            result = verify_system_reminder(request, wait_idle, database, request_ids)
            database.close()
            return result
        if tool_receipts:
            result=verify_tool_receipts(request,wait_idle,database,request_ids,restart_gateway)
            database.close()
            return result
        if reliability:
            result=verify_reliability(request,wait_idle,base)
            database.close()
            return result
        if continuation_modes:
            result=verify_continuation_modes(request,wait_idle,database,request_ids)
            Binding.continuation_mode='history'
            result['history_parallel_round_sizes']=verify_parallel_tools(request,wait_idle,base)['round_sizes']
            result['history_replay_model_calls']=verify_tool_result_retries(request,wait_idle,base,database,request_ids)
            database.close()
            return result
        if messages_search:
            result=verify_messages_search(request,wait_idle,database)
            database.close()
            return result
        if live_capacity:
            database.close()
            return verify_live_capacity(request, wait_idle, base)
        if shared_models:
            result = verify_shared_models(request, request_ids, wait_idle)
            database.close()
            return result
        if parallel_tools:
            result=verify_parallel_tools(request,wait_idle,base)
            result['replay_model_calls']=verify_tool_result_retries(request,wait_idle,base,database,request_ids)
            database.close()
            return result
        if tool_deadlines:
            result=verify_tool_deadlines(request,wait_idle,base)
            database.close()
            return result
        if kernel_selection:
            result = verify_kernel_selection(request, wait_idle, base)
            database.close()
            return result
        if png:
            result=verify_png(request,request_ids,wait_idle,database,base)
            result['native_tls_and_runtime']=True
            result['claude_gateway_rejected_ingress']=verify_gateway_rejections(request)
            result['rejection_body_modes']=verify_rejection_body_modes(request,request_ids,base)
            result['native_safety_settings']=verify_native_safety(request,request_ids,wait_idle,base)
            result['full_egress_sources']=verify_egress_body_modes(request,request_ids,wait_idle,base)
            database.close()
            return result
        body={'contents':[{'role':'user','parts':[{'text':'TLS_SYNTHETIC_TEXT'}]}],
            'generationConfig':{'temperature':.2,'topP':.8,'maxOutputTokens':128}}
        if capture_off:
            with database:database.execute('UPDATE accounts SET agy_system_prompt_homoglyph_enabled=1 WHERE id=1')
            body['systemInstruction']={'parts':[{'text':'ABC system 中文'}]}
            require(request(base+'generateContent',body)[0]==200,'关闭采集的真实系统策略执行失败')
            wait_idle()
            require(len(Upstream.calls)==1,'关闭采集场景实际提交次数错误')
            wire=Upstream.calls[0]['body']['request']
            require(''.join(part.get('text','') for part in wire['systemInstruction']['parts'])=='ΑΒС ѕуѕtеm 中文','关闭采集时系统转换失效')
            request_id=request_ids[-1]
            until=time.monotonic()+10
            while True:
                status,raw=request(f'/admin/request-diagnostics/{request_id}',admin=True)
                if status==200 and (attempts:=json.loads(raw)['attempts']) and attempts[-1]['finished_at']:break
                require(time.monotonic()<until,'关闭采集时请求诊断尚未入账');time.sleep(.1)
            attempt=attempts[-1]
            require(attempt['runtime'] and attempt['runtime']['prepared_ms']>0,'关闭正文采集丢失本地准备耗时')
            status,raw=request(f'/admin/request-diagnostics/{request_id}/captures/{attempt["attempt_id"]}',admin=True)
            capture=json.loads(raw)
            require(status==200 and capture['state']=='disabled' and 'snapshot' not in capture,
                '关闭采集时快照接口未报告已关闭')
            for name in ['gemini-input.json','input-mapping.json','rpc.ndjson','native-stream.ndjson','protocol-output.ndjson']:
                require(not list(Path('/state').rglob(name)),'关闭采集仍保留请求正文归档：'+name)
            require(request('/admin/settings',{'request_diagnostics_rejected_body':'full'},admin=True)[0]==200,
                '完整正文设置保存失败')
            rejected={**body,'generationConfig':{'responseModalities':['IMAGE']}}
            require(request(base+'generateContent',rejected)[0]==400,'合成原生拒绝状态异常')
            request_id=request_ids[-1]
            until=time.monotonic()+10
            while True:
                status,raw=request(f'/admin/request-diagnostics/{request_id}',admin=True)
                detail=json.loads(raw)
                if status==200 and detail['request']['finished_at']:break
                require(time.monotonic()<until,'关闭采集的拒绝请求尚未入账');time.sleep(.1)
            require(detail['attempts'] and not detail['request'].get('native_rejection')
                and request(f'/admin/request-diagnostics/{request_id}/captures/{request_id}',admin=True)[0]==404,
                '完整正文绕过了账号内容采集开关')
            database.close()
            return {'passed':True,'evidence':'real_gateway_sender_native_tls_capture_off','network':'none',
                'real_model_submissions':0,'synthetic_native_model_submissions':1,'checks':['采集关闭仍实际转换','采集关闭保留本地准备耗时','收口后无请求正文归档','完整正文遵循账号内容采集开关']}
        status,raw=request(base+'generateContent',body)
        require(status==200,'固定原版非流式生成失败：'+str(status)+' '+raw.decode()[:500])
        result=json.loads(raw)
        require(result['usageMetadata']['totalTokenCount']==7 and result['candidates'][0]['content']['parts'][0]['text']=='本地TLS回复','原生响应或usage错误')
        status,raw=request(base+'streamGenerateContent?alt=sse',body)
        require(status==200 and raw.startswith(b'data: ') and b'[DONE]' not in raw,'固定原版SSE失败')
        tool=copy.deepcopy(body);tool['contents'][0]['parts'][0]['text']='TLS_SYNTHETIC_TOOL_SCHEMA'
        elements = [{'type': 'STRING'}, {'type': 'STRING'}, {'type': 'NUMBER'}, {'type': 'BOOLEAN'}]
        tool['tools'] = [{'functionDeclarations': [{'name': 'synthetic_tool', 'parameters': {
            'type': 'OBJECT', 'properties': {
                'x': {'type': 'INTEGER'}, 'action': {'const': 'query'},
                'where': {'type': 'ARRAY', 'items': {'type': 'ARRAY'}},
                'prefix': {'type': 'ARRAY', 'prefixItems': elements, 'items': False, 'maxItems': '3'},
                'legacy': {'type': 'ARRAY', 'items': elements, 'additionalItems': False},
            },
        }}]}]
        status,raw=request(base+'generateContent',tool)
        require(status==200,'固定原版工具首轮失败：'+str(status)+' '+raw.decode()[:500])
        result=json.loads(raw);content=result['candidates'][0]['content']
        calls = [part['functionCall'] for part in content['parts'] if 'functionCall' in part]
        require(len(calls) == 1 and calls[0]['args'] == SCHEMA_TOOL_ARGS
            and calls[0]['args']['where'][1][2] is True, '原生工具源帧缺失或筛选值类型改变')
        native_request = Upstream.calls[2]['body'].get('request', Upstream.calls[2]['body'])
        declarations = [declaration for group in native_request['tools']
            for declaration in group.get('functionDeclarations', []) if declaration.get('name') == 'synthetic_tool']
        require(len(declarations) == 1, '原生出站工具定义缺失或重复')
        properties = declarations[0]['parameters']['properties']
        require(isinstance(properties['where']['items'].get('items'), dict), '原生出站遗漏嵌套数组的 items')
        require(all(isinstance(properties[name].get('items'), dict) and str(properties[name].get('maxItems')) == maximum
            for name, maximum in (('prefix', '3'), ('legacy', '4'))), '原生出站遗漏新版或旧版元组的 items 或长度上限')
        require(properties['action'].get('enum') == ['query'], '原生出站遗失字符串常量约束')
        continuation=copy.deepcopy(tool)
        continuation['contents']+=[content,{'role':'user','parts':[{'functionResponse':{
            'id':'synthetic-call','name':'synthetic_tool','response':{'value':'TLS_SYNTHETIC_RESULT'}}}]}]
        with database:
            database.execute("UPDATE account_credential_states SET generation=2 WHERE account_id=1")
            database.execute("UPDATE accounts SET access_token='synthetic-at-2' WHERE id=1")
        status,raw=request(base+'generateContent',continuation)
        require(status==200,'固定原版工具新代续轮失败：'+str(status)+' '+raw.decode()[:500])
        require(request(base+'generateContent',continuation)==(status,raw),'重复工具回填未返回原响应')
        require(len(Upstream.calls)==4,'原生业务发生额外模型提交')
        require([call['authorization'] for call in Upstream.calls]==['Bearer synthetic-at-1']*3+['Bearer synthetic-at-2'],'原生AT代次错误')
        for call in Upstream.calls:
            generation=call['body'].get('request',call['body']).get('generationConfig',{})
            require('temperature' not in generation and 'topP' not in generation and generation.get('maxOutputTokens')==128,'实际出站参数策略错误')
        require(any('TLS_SYNTHETIC_RESULT' in json.dumps(call['body']) for call in Upstream.calls),'工具结果没有进入真实原生提交')
        repeat=copy.deepcopy(body);repeat['contents'][0]['parts'][0]['text']='TLS_SYNTHETIC_REPEAT'
        status,raw=request(base+'generateContent',repeat)
        require(status==200 and ''.join(part.get('text','') for part in json.loads(raw)['candidates'][0]['content']['parts'])=='本地TLS回复'*64,'原生重复源帧丢失或重复')
        for mode in ['TLS_SYNTHETIC_TRUNCATED','TLS_SYNTHETIC_CAPACITY']:
            failure=copy.deepcopy(body);failure['contents'][0]['parts'][0]['text']=mode
            expected=429 if mode=='TLS_SYNTHETIC_CAPACITY' else 503
            require(request(base+'generateContent',failure)[0]==expected,'原生错误或截断流被误分类：'+mode)
            wait_idle()
        invalid_schema = copy.deepcopy(body)
        invalid_schema['tools'] = [{'functionDeclarations': [{'name': 'synthetic_tool', 'parameters': {
            'type': 'OBJECT', 'properties': {'value': {'type': 'STRING', 'pattern': '('}},
        }}]}]
        before = len(Upstream.calls)
        status, raw = request(base + 'generateContent', invalid_schema)
        error = json.loads(raw)['error']
        require((status, error['code'], error['status']) == (500, 500, 'INTERNAL')
            and len(Upstream.calls) == before, '原版拒绝非法工具正则时未保留控制 HTTP 500')
        wait_idle()
        cancel=copy.deepcopy(body);cancel['contents'][0]['parts'][0]['text']='TLS_SYNTHETIC_CANCEL'
        value=Request('http://127.0.0.1:5674'+base+'streamGenerateContent?alt=sse',
            data=json.dumps(cancel).encode(),headers={'x-api-key':'synthetic-key','content-type':'application/json'})
        stream=urlopen(value,timeout=125)
        require(stream.readline().startswith(b'data: '),'原生取消场景缺少源首帧');stream.close()
        require(Upstream.cancelled.wait(15),'公共断连未关闭固定原版上游')
        # 私有active包含原生退役，确认真实收口后再观察后续请求。
        wait_idle()
        require(request(base+'generateContent',body)[0]==200,'原生取消后账号未恢复服务')
        require(len(Upstream.calls)==9,'错误或取消场景发生额外原生提交')
        wait_idle()
        value=Request('http://127.0.0.1:8091/internal/status',headers={'authorization':'Bearer '+SECRET})
        with urlopen(value,timeout=5) as response:state=json.load(response)
        require(state['agy']['image_decode_calls']==1 and state['agy']['workers']==1,'原生回归破坏共享映像或物理并发上限')
        policy_checks=homoglyph_cases(database,request,base,wait_idle) if homoglyph else []
        require(len(Upstream.calls)==(17 if homoglyph else 9),'原生策略回归入口数不符')
        until=time.monotonic()+10
        while True:
            status,raw=request('/admin/request-diagnostics?platform=antigravity&entry_protocol=gemini&page_size=200',admin=True)
            require(status==200,'真实原生诊断查询失败')
            records=json.loads(raw)
            if records['total']>=len(set(request_ids)):break
            require(time.monotonic()<until,'真实原生根记录没有持久化');time.sleep(.1)
        require(len(request_ids)==len(set(request_ids)),'HTTP根关联ID重复')
        require(records['total']==len(request_ids)+1,'目录、控制操作或后台任务混入HTTP根记录')
        require(all(row['context']['platform']=='antigravity' and row['context']['entry_protocol']=='gemini' for row in records['items']),'原生诊断平台或协议错误')
        require(records['health']['write_failures']==0 and records['health']['dropped_records']==0,'正常原生诊断存在写入缺口')
        attempts=[]
        for row in records['items']:
            status,raw=request('/admin/request-diagnostics/'+row['request_id'],admin=True)
            detail=json.loads(raw);attempts.extend(detail['attempts'])
            require(len(detail['attempts'])==row['attempt_count'],'实际尝试计数与详情不符')
        require(any(a['context']['tool_turn']['state']=='completed' for a in attempts if a['context'].get('tool_turn')),'原工具实际收口未记录')
        require(any(a['context']['tool_turn'].get('continuation_of_request_id') for a in attempts if a['context'].get('tool_turn')),'工具跨HTTP关联缺失')
        require(any(a['context']['usage']['usage_metadata'].get('cachedContentTokenCount')==2 for a in attempts if a['context'].get('usage')),'源缓存用量未记录')
        require(any(a['context'].get('control_state')=='completed' for a in attempts),'实际原生控制收口未记录')
        ingress=list(Path('/state/capture/api/agy-prepared/ingress/snapshots').glob('*.json'))
        require(bool(ingress),'实际HTTP入口独立旁路缺失')
        database.close()
        return {'policy_checks':policy_checks,'diagnostic_requests':records['total'],'diagnostic_attempts':len(attempts),'passed':True,'evidence':'real_gateway_sender_native_tls','network':'none','real_model_submissions':0,
            'synthetic_native_model_submissions':len(Upstream.calls),'credential_generations':[1,2],
            'cgroup_memory':state['agy']['cgroup_memory'],
            'checks':['公共Gemini非流式与SSE','原版TLS与证书校验','源响应及usage','实际出站参数','原生MCP结果回填',
                'concurrency=1新代续轮','重复回填复用原响应','64个重复源帧','截断及容量错误终态','控制 HTTP 500 原样交付','公共断连取消原生上游','真实收口及账号许可释放']}
    finally:
        for child in children:
            child.terminate()
        for child in children:
            try:child.wait(timeout=10)
            except subprocess.TimeoutExpired:child.kill();child.wait()
        for output in outputs:output.close()
        for server in [proxy,binding]:server.shutdown();server.server_close()


def main():
    """创建一次性CA并启动明确镜像，正式运行配置保持正常信任规则。@return 无。"""
    parser=argparse.ArgumentParser()
    parser.add_argument('--image')
    parser.add_argument('--loader-root',type=Path)
    parser.add_argument('--inside',action='store_true')
    parser.add_argument('--homoglyph',action='store_true')
    parser.add_argument('--capture-off',action='store_true')
    parser.add_argument('--png',action='store_true')
    parser.add_argument('--installed-adapter',action='store_true')
    parser.add_argument('--kernel-selection',action='store_true')
    parser.add_argument('--tool-deadlines',action='store_true')
    parser.add_argument('--parallel-tools',action='store_true')
    parser.add_argument('--shared-models', action='store_true')
    parser.add_argument('--live-capacity', action='store_true')
    parser.add_argument('--messages-search', action='store_true')
    parser.add_argument('--continuation-modes', action='store_true')
    parser.add_argument('--tool-receipts', action='store_true')
    parser.add_argument('--reliability', action='store_true')
    parser.add_argument('--system-reminder', action='store_true')
    parser.add_argument('--claude-code', type=Path)
    args=parser.parse_args()
    installed_adapter=args.installed_adapter or args.png or args.kernel_selection
    if args.inside:
        result = inside(args.homoglyph,args.capture_off,args.png,installed_adapter,args.kernel_selection,args.tool_deadlines,args.parallel_tools,
            shared_models=args.shared_models,live_capacity=args.live_capacity,messages_search=args.messages_search,
            continuation_modes=args.continuation_modes,tool_receipts=args.tool_receipts,
            system_reminder=args.system_reminder,reliability=args.reliability)
        print(json.dumps(result, ensure_ascii=False))
        return
    require(bool(args.image),'需要明确的固定原版测试镜像')
    import docker
    root=Path(__file__).resolve().parents[2]
    package=source_path(root,'orchestrator')
    folder=Path(tempfile.mkdtemp(prefix='agy-native-tls-'))
    client=docker.from_env(timeout=60);container=None;receipt_adapter=None
    try:
        subprocess.run(['openssl','req','-x509','-newkey','rsa:2048','-nodes','-days','1','-subj','/CN=AGY local verification',
            '-addext','subjectAltName=DNS:*.googleapis.com','-keyout',str(folder/'server.key'),'-out',str(folder/'server.crt')],
            check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        trust=Path('/etc/ssl/certs/ca-certificates.crt').read_bytes()+(folder/'server.crt').read_bytes()
        (folder/'trust.pem').write_bytes(trust)
        # 只向一次性断网容器挂载信任根；正式适配无测试CA字段或跳过证书验证入口。
        folder.chmod(0o700);os.chown(folder,1001,1001)
        for path in folder.iterdir():
            path.chmod(0o600);os.chown(path,1001,1001)
        (folder/'capture').mkdir(mode=0o700);os.chown(folder/'capture',1001,1001)
        if args.png:
            # 复现升级写入共享采集区的 root 标记。新发送器须照常冷启动并保留采集。
            captures=folder/'capture/api/agy-prepared'
            for path in (captures.parent,captures,captures/'snapshots',captures/'ingress'):
                path.mkdir(mode=0o700);os.chown(path,1001,1001)
            for name in ('snapshots','ingress'):
                marker=captures/name/'retired.json'
                marker.write_text(json.dumps({'retired_at':time.time()-8*86400}))
                marker.chmod(0o600)
        host='flower2api-'+hashlib.sha256(b'synthetic').hexdigest()[:12]+'-'+ENVIRONMENT
        volumes={str(root/'services/gateway/target/debug/claude-code-gateway'):{'bind':'/opt/gateway','mode':'ro'},
            str(root/'services/gateway/target/debug/account-sender'):{'bind':'/opt/sender','mode':'ro'},
            str(Path(__file__).resolve()):{'bind':'/opt/probe.py','mode':'ro'},
            str(Path(__file__).with_name('source_layout.py')):{'bind':'/opt/source_layout.py','mode':'ro'},
            str(package/'agy_runtime'):{'bind':'/opt/orchestrator/agy_runtime','mode':'ro'},
            str(package/'runtime_files.py'):{'bind':'/usr/local/bin/runtime_files.py','mode':'ro'},
            str(folder):{'bind':'/state','mode':'rw'},
            str(folder/'capture'):{'bind':'/flows','mode':'rw'},
            str(folder/'trust.pem'):{'bind':'/etc/ssl/certs/ca-certificates.crt','mode':'ro'}}
        if installed_adapter:
            del volumes[str(package/'agy_runtime')]
        if args.tool_receipts:
            require(not installed_adapter,'回填回执夹具需要本地构建的观察器')
            receipt_adapter=Path(tempfile.mkdtemp(prefix='agy-tool-receipt-adapter-'))
            receipt_adapter.chmod(0o755)
            runtime=receipt_adapter/'agy_runtime'
            shutil.copytree(package/'agy_runtime',runtime,ignore=shutil.ignore_patterns('__pycache__'))
            shutil.copy2(Path(__file__).with_name('fixtures')/'agy_tool_receipt.py',runtime/'tool_receipt_fixture.py')
            kernel=runtime/'kernel.py'
            entry="if __name__=='__main__':raise SystemExit(main())"
            source=kernel.read_text()
            require(source.count(entry)==1,'隔离内核入口已变化')
            kernel.write_text(source.replace(entry,'from .tool_receipt_fixture import install\ninstall(Kernel, Bridge, RPC)\n'+entry))
            volumes[str(runtime)]=volumes.pop(str(package/'agy_runtime'))
        if args.claude_code:
            require(args.messages_search,'Claude Code 验证需要 Messages 搜索场景')
            volumes[str(args.claude_code.resolve(strict=True))]={'bind':'/opt/claude-code','mode':'ro'}
        python_package='/opt/v3/python' if installed_adapter else '/opt/orchestrator'
        if args.loader_root:
            # 开发机调试产物可能依赖较新glibc，加载器只作用于测试Rust进程。
            for name in ['ld-linux-x86-64.so.2','libc.so.6','libm.so.6','libgcc_s.so.1']:
                library=(args.loader_root/name).resolve(strict=True)
                volumes[str(library)]={'bind':'/opt/verify-lib/'+name,'mode':'ro'}
        probe=['/opt/probe.py','--inside']
        for flag,enabled in (('--homoglyph',args.homoglyph),('--capture-off',args.capture_off),('--png',args.png),
                ('--installed-adapter',installed_adapter),('--kernel-selection',args.kernel_selection),('--parallel-tools',args.parallel_tools),
                ('--tool-deadlines',args.tool_deadlines),('--shared-models',args.shared_models),
                ('--live-capacity',args.live_capacity),('--messages-search',args.messages_search),
                ('--continuation-modes',args.continuation_modes),('--tool-receipts',args.tool_receipts),
                ('--system-reminder', args.system_reminder),('--reliability',args.reliability)):
            if enabled:probe.append(flag)
        container=client.containers.run(args.image,probe,entrypoint=['python3'],detach=True,
            user='1001:1001',network_mode='none',read_only=True,cap_drop=['ALL'],security_opt=['no-new-privileges:true'],
            mem_limit='1536m' if args.png or args.live_capacity or args.claude_code else '768m',pids_limit=512,extra_hosts={host:'127.0.0.1'},tmpfs={'/tmp':'rw,nosuid,nodev,size=128m'},
            volumes=volumes,environment={'PYTHONPATH':python_package+':/usr/local/bin','DATABASE_DRIVER':'sqlite',
                'DATABASE_DSN':'/state/gateway.sqlite','ADMIN_PASSWORD':'synthetic-admin','V3_SENDER_CONFIG':'/state/sender.json',
                'V3_RUNTIME_URL':'http://127.0.0.1:8765','V3_INTERNAL_TOKEN':SECRET,'V3_DEPLOYMENT_ID':'synthetic',
                'V3_RELEASE':'synthetic-release','LOG_LEVEL':'warn','TOKIO_WORKER_THREADS':'2'},
            labels={'vibebench.test-task':'agy-request-records'})
        result=container.wait(timeout=540)
        logs=container.logs().decode(errors='replace')
        evidence=root/('.trellis/.runtime/agy-continuation-modes-private' if args.continuation_modes else '.trellis/.runtime/agy-messages-search-private' if args.messages_search else '.trellis/.runtime/agy-live-capacity-private' if args.live_capacity else '.trellis/.runtime/agy-shared-models-private' if args.shared_models else '.trellis/.runtime/agy-parallel-tools-private' if args.parallel_tools else '.trellis/.runtime/agy-tool-deadlines-private' if args.tool_deadlines else '.trellis/.runtime/agy-kernel-selection-private' if args.kernel_selection else '.trellis/.runtime/agy-png-loopback-private' if args.png else '.trellis/.runtime/agy-homoglyph-capture-off-private' if args.capture_off else '.trellis/.runtime/agy-homoglyph-loopback-private' if args.homoglyph else '.trellis/.runtime/agy-runtime-loopback-private')
        if args.tool_receipts:evidence=root/'.trellis/.runtime/agy-tool-receipts-private'
        if args.reliability:evidence=root/'.trellis/.runtime/agy-tool-reliability-private'
        if args.system_reminder:evidence=root/'.trellis/.runtime/agy-system-reminder-private'
        if evidence.exists():shutil.rmtree(evidence)
        shutil.copytree(folder,evidence,ignore=lambda directory,names:[name for name in names
            if not (Path(directory)/name).is_file() and not (Path(directory)/name).is_dir()])
        require(result['StatusCode']==0,logs)
        print(logs.strip())
    finally:
        if container:container.remove(force=True)
        if receipt_adapter:shutil.rmtree(receipt_adapter)
        shutil.rmtree(folder)


if __name__=='__main__':
    main()
