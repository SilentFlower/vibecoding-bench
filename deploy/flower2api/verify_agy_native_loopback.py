"""在断网容器中连接真实网关、发送器、固定AGY原版和本地TLS合成上游。"""
import argparse
import base64
import copy
import gzip
import hashlib
import json
import os
import shutil
import signal
import sqlite3
import ssl
import subprocess
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from source_layout import source_path

ENVIRONMENT='a'*32
SECRET='synthetic-internal-proof-at-least-32-bytes'
MODEL='gemini-3.1-pro-preview'
SOURCE_SHA='39816d49d5ab92229952987225c23ea3fed7580699dcb4a444e0388e0ac1ce43'


def require(condition, message):
    """校验隔离验收条件。@param condition 实际条件。@param message 固定说明。@return 无。"""
    if not condition:
        raise ValueError(message)


class Upstream(BaseHTTPRequestHandler):
    """只处理固定原版经TLS实际发送的合成请求。"""

    protocol_version='HTTP/1.1'
    calls=[]
    requests=[]
    wire=[]
    cancelled=threading.Event()

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
        if ':streamGenerateContent' in self.path:
            self.calls.append(record)
            encoded=json.dumps(body)
            tools=body.get('request',body).get('tools',[])
            results='functionResponse' in encoded
            tool='TLS_SYNTHETIC_TOOL' in encoded and not results
            cancel='TLS_SYNTHETIC_CANCEL' in encoded
            repeated='TLS_SYNTHETIC_REPEAT' in encoded
            truncated='TLS_SYNTHETIC_TRUNCATED' in encoded
            capacity='TLS_SYNTHETIC_CAPACITY' in encoded
            self.send_response(200)
            self.send_header('Content-Type','text/event-stream')
            self.send_header('Connection','close')
            self.end_headers()
            self.close_connection=True
            part={'functionCall':{'name':'synthetic_tool','args':{'x':1},'id':'synthetic-call'},'thoughtSignature':'c3ludGhldGljLXNpZw=='} if tool else {'text':'本地TLS回复'}
            frames=[{'candidates':[{'index':0,'content':{'role':'model','parts':[part]}}]}]
            if repeated:frames*=64
            if capacity:frames=[{'error':{'code':429,'status':'RESOURCE_EXHAUSTED'}}]
            if not cancel and not truncated and not capacity:
                frames.append({'candidates':[{'index':0,'content':{'role':'model','parts':[{'text':''}]},'finishReason':'STOP'}],
                    'usageMetadata':{'promptTokenCount':3,'candidatesTokenCount':4,'totalTokenCount':7}})
            elif cancel:
                frames*=200
            try:
                native=None
                if repeated:
                    for path in Path('/state/capture').rglob('protocol-output.ndjson'):
                        for line in path.read_text().splitlines():
                            event=json.loads(line)
                            if event.get('type')=='worker_ready' and Path('/proc/'+str(event['native_pid'])).exists():
                                native=event['native_pid']
                    require(native is not None,'重复帧实验缺少真实原生PID')
                for frame in frames:
                    if native:os.kill(native,signal.SIGURG)
                    envelope=frame if 'error' in frame else {'response':frame}
                    self.wfile.write(('data: '+json.dumps(envelope,ensure_ascii=False)+'\n\n').encode())
                    self.wfile.flush()
                    time.sleep(.1 if cancel else .02)
            except OSError:
                if cancel:
                    self.cancelled.set()
            return
        if ':loadCodeAssist' in self.path:
            value={'cloudaicompanionProject':'synthetic-project','currentTier':{'id':'standard-tier','name':'Standard'}}
        elif ':fetchAvailableModels' in self.path:
            value={'models':{MODEL:{'model':'MODEL_PLACEHOLDER_M36','displayName':MODEL}}}
        else:
            value={}
        raw=json.dumps(value).encode()
        self.send_response(200)
        self.send_header('Content-Type','application/json')
        self.send_header('Content-Length',str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

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
            Upstream(connection,self.client_address,self.server)
        self.close_connection=True


class Binding(BaseHTTPRequestHandler):
    """复用真实网关传输准备边界，返回唯一合成环境。"""

    def log_message(self,*args):
        """保持私有证明不进入日志。@param args 日志参数。@return 无。"""

    def do_GET(self):
        """返回真实发送器的固定绑定。@return 无。"""
        require(self.path=='/internal/v3/transport/1','运行绑定路径错误')
        host='flower2api-'+hashlib.sha256(b'synthetic').hexdigest()[:12]+'-'+ENVIRONMENT
        value={'account_id':1,'environment_id':ENVIRONMENT,'generation':1,'endpoint':f'http://{host}:8091',
            'secret':SECRET,'release_id':'synthetic-release'}
        raw=json.dumps(value).encode()
        self.send_response(200);self.send_header('Content-Length',str(len(raw)));self.end_headers()
        self.wfile.write(raw)


def inside():
    """在无外网容器中执行真实公共Gemini业务与原生工具轮。@return 脱敏验证摘要。"""
    require(os.geteuid()==1001,'原生业务探针必须使用UID1001')
    os.umask(0o077)
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
        'agy':{'protocol_version':1,'source_sha256':SOURCE_SHA,'module_root':'/opt/orchestrator',
            'binary_path':'/usr/local/bin/agy-1.5.9','work_root':'/state/native','max_workers':1,'memory_mib':768}}
    Path('/state/sender.json').write_text(json.dumps(config))
    outputs=[];children=[]
    for executable,name in [('/opt/sender','sender'),('/opt/gateway','gateway')]:
        output=open('/state/'+name+'.log','wb');outputs.append(output)
        command=[executable]
        if Path('/opt/verify-lib/ld-linux-x86-64.so.2').is_file():
            command=['/opt/verify-lib/ld-linux-x86-64.so.2','--library-path','/opt/verify-lib',executable]
        children.append(subprocess.Popen(command,stdout=output,stderr=subprocess.STDOUT))
    def request(path,body=None):
        """通过真实公共HTTP执行一次请求。@param path 路径。@param body Gemini正文。@return 状态与正文。"""
        headers={'x-api-key':'synthetic-key','content-type':'application/json'}
        value=Request('http://127.0.0.1:5674'+path,data=json.dumps(body).encode() if body is not None else None,headers=headers)
        try:
            with urlopen(value,timeout=125) as response:
                return response.status,response.read()
        except HTTPError as error:
            return error.code,error.read()
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
                request('/api/hello');break
            except OSError:
                time.sleep(.1)
        database=sqlite3.connect('/state/gateway.sqlite')
        with database:
            database.execute("INSERT INTO accounts(id,name,email,platform,token,device_id,auth_type,access_token,refresh_token,oauth_expires_at,concurrency,auto_telemetry,auto_poll_usage,usage_data) VALUES(1,'synthetic','synthetic@example.test','antigravity','','','oauth','synthetic-at-1','synthetic-rt','2099-01-01T00:00:00Z',1,0,0,?)",
                (json.dumps({'capabilities':{'model_mappings':{MODEL:'MODEL_PLACEHOLDER_M36'}}}),))
            database.execute("INSERT INTO account_credential_states(account_id,generation,phase,updated_at_ms) VALUES(1,1,'ready',1)")
            database.execute("INSERT INTO api_tokens(name,token,allowed_accounts,status) VALUES('synthetic','synthetic-key','1','active')")
        base='/v1beta/models/'+MODEL+':'
        body={'contents':[{'role':'user','parts':[{'text':'TLS_SYNTHETIC_TEXT'}]}],
            'generationConfig':{'temperature':.2,'topP':.8,'maxOutputTokens':128}}
        status,raw=request(base+'generateContent',body)
        require(status==200,'固定原版非流式生成失败：'+str(status)+' '+raw.decode()[:500])
        result=json.loads(raw)
        require(result['usageMetadata']['totalTokenCount']==7 and result['candidates'][0]['content']['parts'][0]['text']=='本地TLS回复','原生响应或usage错误')
        status,raw=request(base+'streamGenerateContent?alt=sse',body)
        require(status==200 and raw.startswith(b'data: ') and b'[DONE]' not in raw,'固定原版SSE失败')
        tool=copy.deepcopy(body);tool['contents'][0]['parts'][0]['text']='TLS_SYNTHETIC_TOOL'
        tool['tools']=[{'functionDeclarations':[{'name':'synthetic_tool','parameters':{'type':'OBJECT','properties':{'x':{'type':'INTEGER'}}}}]}]
        status,raw=request(base+'generateContent',tool)
        require(status==200,'固定原版工具首轮失败：'+str(status)+' '+raw.decode()[:500])
        result=json.loads(raw);content=result['candidates'][0]['content']
        require(any('functionCall' in part for part in content['parts']),'原生工具源帧缺失')
        continuation=copy.deepcopy(tool)
        continuation['contents']+=[content,{'role':'user','parts':[{'functionResponse':{
            'id':'synthetic-call','name':'synthetic_tool','response':{'value':'TLS_SYNTHETIC_RESULT'}}}]}]
        with database:
            database.execute("UPDATE account_credential_states SET generation=2 WHERE account_id=1")
            database.execute("UPDATE accounts SET access_token='synthetic-at-2' WHERE id=1")
        status,raw=request(base+'generateContent',continuation)
        require(status==200,'固定原版工具新代续轮失败：'+str(status)+' '+raw.decode()[:500])
        require(request(base+'generateContent',continuation)[0]==400,'重复工具回填被接纳')
        require(len(Upstream.calls)==4,'原生业务发生额外模型提交')
        require([call['authorization'] for call in Upstream.calls]==['Bearer synthetic-at-1']*3+['Bearer synthetic-at-2'],'原生AT代次错误')
        for call in Upstream.calls:
            generation=call['body'].get('request',call['body']).get('generationConfig',{})
            require('temperature' not in generation and 'topP' not in generation and generation.get('maxOutputTokens')==128,'实际出站参数策略错误')
        mcp=[json.loads(line) for path in Path('/state/capture').rglob('mcp.ndjson') for line in path.read_text().splitlines()]
        require(any(row.get('response',{}).get('result',{}).get('structuredContent')=={'value':'TLS_SYNTHETIC_RESULT'} for row in mcp),'工具结果未返回真实原生MCP调用')
        repeat=copy.deepcopy(body);repeat['contents'][0]['parts'][0]['text']='TLS_SYNTHETIC_REPEAT'
        status,raw=request(base+'generateContent',repeat)
        require(status==200 and ''.join(part.get('text','') for part in json.loads(raw)['candidates'][0]['content']['parts'])=='本地TLS回复'*64,'原生重复源帧丢失或重复')
        for mode in ['TLS_SYNTHETIC_TRUNCATED','TLS_SYNTHETIC_CAPACITY']:
            failure=copy.deepcopy(body);failure['contents'][0]['parts'][0]['text']=mode
            require(request(base+'generateContent',failure)[0]==503,'原生错误或截断流被当作成功：'+mode)
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
        database.close()
        return {'passed':True,'evidence':'real_gateway_sender_native_tls','network':'none','real_model_submissions':0,
            'synthetic_native_model_submissions':len(Upstream.calls),'credential_generations':[1,2],
            'cgroup_memory':state['agy']['cgroup_memory'],
            'checks':['公共Gemini非流式与SSE','原版TLS与证书校验','源响应及usage','实际出站参数','原生MCP结果回填',
                'concurrency=1新代续轮','重复回填拒绝','64个重复源帧','截断及容量错误终态','公共断连取消原生上游','真实收口及账号许可释放']}
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
    args=parser.parse_args()
    if args.inside:
        print(json.dumps(inside(),ensure_ascii=False));return
    require(bool(args.image),'需要明确的固定原版测试镜像')
    import docker
    root=Path(__file__).resolve().parents[2]
    package=source_path(root,'orchestrator')
    folder=Path(tempfile.mkdtemp(prefix='agy-native-tls-'))
    client=docker.from_env(timeout=15);container=None
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
        if args.loader_root:
            # 开发机调试产物可能依赖较新glibc，加载器只作用于测试Rust进程。
            for name in ['ld-linux-x86-64.so.2','libc.so.6','libm.so.6','libgcc_s.so.1']:
                library=(args.loader_root/name).resolve(strict=True)
                volumes[str(library)]={'bind':'/opt/verify-lib/'+name,'mode':'ro'}
        container=client.containers.run(args.image,['/opt/probe.py','--inside'],entrypoint=['python3'],detach=True,
            user='1001:1001',network_mode='none',read_only=True,cap_drop=['ALL'],security_opt=['no-new-privileges:true'],
            mem_limit='768m',pids_limit=512,extra_hosts={host:'127.0.0.1'},tmpfs={'/tmp':'rw,nosuid,nodev,size=128m'},
            volumes=volumes,environment={'PYTHONPATH':'/opt/orchestrator','DATABASE_DRIVER':'sqlite',
                'DATABASE_DSN':'/state/gateway.sqlite','ADMIN_PASSWORD':'synthetic-admin','V3_SENDER_CONFIG':'/state/sender.json',
                'V3_RUNTIME_URL':'http://127.0.0.1:8765','V3_INTERNAL_TOKEN':SECRET,'V3_DEPLOYMENT_ID':'synthetic',
                'V3_RELEASE':'synthetic-release','LOG_LEVEL':'warn','TOKIO_WORKER_THREADS':'2'},
            labels={'vibebench.test-task':'agy-account-runtime'})
        result=container.wait(timeout=540)
        logs=container.logs().decode(errors='replace')
        evidence=root/'.trellis/.runtime/agy-runtime-loopback-private'
        if evidence.exists():shutil.rmtree(evidence)
        shutil.copytree(folder,evidence,ignore=lambda directory,names:[name for name in names
            if not (Path(directory)/name).is_file() and not (Path(directory)/name).is_dir()])
        require(result['StatusCode']==0,logs)
        print(logs.strip())
    finally:
        if container:container.remove(force=True)
        shutil.rmtree(folder)


if __name__=='__main__':
    main()
