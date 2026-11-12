"""离线回环中运行真实产品恢复器。"""
from fixture_guard import require_disposable_guest
require_disposable_guest()
import asyncio,json,os,shutil,socket,sys,threading,subprocess,ssl,ctypes,hashlib,re
from pathlib import Path
from http.server import ThreadingHTTPServer
sys.path.insert(0,'/opt/ccrb-criu')
from controller import Controller
original_remove=shutil.rmtree
def report_remove(path,*args,**kwargs):
    """在私有目录清理前保留合成实验日志。@param path 合成夹具参数。@return 合成验证结果或无。"""
    p=Path(path)
    if p.parent.name=='instances':
        for name in ('namespace.log','restore.log'):
            log=p/name
            if log.exists() and log.stat().st_size:print('PRIVATE_INSTANCE_LOG',name,log.read_text(errors='replace')[-2200:],flush=True)
    return original_remove(path,*args,**kwargs)
shutil.rmtree=report_remove
sys.path.insert(0,'/probe')
from probe_fanout import Upstream,POSTS
class TlsUpstream(Upstream):
    """合成TLS故障接收器。@return 合成验证结果或无。"""
    def do_GET(self):
        """注入仅实验使用的模板污染或控制器强退。@return 合成验证结果或无。"""
        identifier=self.path.split('/')[-1]
        template=self.server.service.templates[identifier]
        target=next(path for path in (template.root/'images').iterdir() if path.is_file())
        with target.open('r+b') as content:
            first=content.read(1);content.seek(0);content.write(bytes([first[0]^1]));content.flush();os.fsync(content.fileno())
        body=b'{"changed":true}'
        self.send_response(200);self.send_header('content-length',str(len(body)));self.end_headers();self.wfile.write(body)
    def do_POST(self):
        """核对并回显合成请求标记。@return 合成验证结果或无。"""
        raw=self.rfile.read(int(self.headers['Content-Length']));body=json.loads(raw)
        matches=re.findall(r'product-restore-[0-9a-f-]{36}',str(body['messages']));assert len(matches)==1,matches
        marker=matches[0]
        headers=[[k.lower(),v.strip()] for k,v in self.headers.items()]
        POSTS.append({'marker':marker,'client_request_id':self.headers.get('x-client-request-id'),'metadata':body.get('metadata'),'model':body['model'],'body_sha256':hashlib.sha256(raw).hexdigest(),'headers_sha256':hashlib.sha256(json.dumps(headers,separators=(',',':')).encode()).hexdigest()})
        content=json.dumps({'id':'msg_synthetic','type':'message','role':'assistant','model':body['model'],'content':[{'type':'text','text':marker}],'stop_reason':'end_turn','usage':{'input_tokens':1,'output_tokens':1}}).encode()
        self.send_response(200);self.send_header('content-type','application/json');self.send_header('content-length',str(len(content)));self.end_headers();self.wfile.write(content)
Upstream=TlsUpstream
class ProbeController(Controller):
    """采集合成恢复失败的受控日志。@return 合成验证结果或无。"""
    async def run(self, arguments, timeout):
        """运行产品恢复命令并采集私有失败证据。@param arguments 合成夹具参数。@param timeout 合成夹具参数。@return 合成验证结果或无。"""
        try:await super().run(arguments,timeout)
        except Exception:
            print('PRIVATE_CRIU_LOG',Path(arguments[arguments.index('-o')+1]).read_text(errors='replace')[-2400:],flush=True)
            raise
    async def template(self,value,connection):
        """登记合成模板并采集私有失败证据。@param value 合成夹具参数。@param connection 合成夹具参数。@return 合成验证结果或无。"""
        try:await super().template(value,connection)
        except Exception as error:
            print('PRIVATE_TEMPLATE_ERROR',repr(error),flush=True)
            raise
async def main():
    """在一次性客体运行合成验收。@return 合成验证结果或无。"""
    subprocess.run(['ip','link','set','lo','up'],check=True)
    for p in ['/var/lib/ccrb-criu','/run/ccrb-criu','/probe/native']:
        shutil.rmtree(p,ignore_errors=True);Path(p).mkdir(parents=True,mode=0o700)
    for n in ['templates','instances']:Path('/var/lib/ccrb-criu',n).mkdir(mode=0o700)
    os.chown('/probe/native',1001,1001)
    os.chown('/run/ccrb-criu',0,1001);os.chmod('/run/ccrb-criu',0o750)
    listener=socket.socket(socket.AF_UNIX);listener.bind('/run/ccrb-criu/control.sock');listener.listen();listener.setblocking(False)
    os.chown('/run/ccrb-criu/control.sock',0,1001);os.chmod('/run/ccrb-criu/control.sock',0o660)
    subprocess.run(['openssl','req','-x509','-newkey','rsa:2048','-nodes','-days','1','-subj','/CN=api.anthropic.com','-addext','subjectAltName=DNS:api.anthropic.com','-keyout','/probe/controller-ca.key','-out','/probe/controller-ca.pem'],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    Path('/etc/hosts').write_text('127.0.0.1 localhost api.anthropic.com\n')
    sys.path.insert(0,'/opt/ccrb-tls-observer')
    from broker import Broker
    observer_path=Path('/run/ccrb-observer');observer_path.mkdir(exist_ok=True);os.chown(observer_path,0,1001);observer_path.chmod(0o750)
    upstream=ThreadingHTTPServer(('127.0.0.1',443),Upstream);tls=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER);tls.load_cert_chain('/probe/controller-ca.pem','/probe/controller-ca.key');upstream.socket=tls.wrap_socket(upstream.socket,server_side=True);
    mask=sum(1<<cap for cap in (0,1,3,5,6,7,8,12,18,19,21,24,25))
    libc=ctypes.CDLL(None,use_errno=True)
    for cap in range(int(Path('/proc/sys/kernel/cap_last_cap').read_text())+1):
        if not mask&(1<<cap):assert libc.prctl(24,cap,0,0,0)==0
    header=(ctypes.c_uint*2)(0x20080522,0);data=(ctypes.c_uint*6)(mask,mask,0,0,0,0)
    assert libc.capset(ctypes.byref(header),ctypes.byref(data))==0
    assert libc.prctl(38,1,0,0,0)==0
    print('CONTROLLER_CONTEXT',json.dumps({k:v.strip() for k,v in (line.split(':',1) for line in Path('/proc/self/status').read_text().splitlines() if ':' in line) if k in ('CapEff','NoNewPrivs','Seccomp')}),flush=True)
    threading.Thread(target=upstream.serve_forever,daemon=True).start()
    sender=await asyncio.create_subprocess_exec('/probe/restricted-launch','/probe/production-filter.bpf','/usr/local/bin/python3','-B','/probe/controller_sender.py',env={**os.environ,'TEST_UPSTREAM':'https://api.anthropic.com'},stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE)
    service=ProbeController(sender.pid,8,'/probe/native',{'image_sha256':'564019c9560e960e96875c9663975491534b27c789ea3d23e5c13309ff293c79','image_bytes':112843960})
    broker=Broker(sender.pid,8,service.owners)
    observer_server=await asyncio.start_unix_server(broker.handle,'/run/ccrb-observer/control.sock',limit=4096)
    os.chown('/run/ccrb-observer/control.sock',0,1001);os.chmod('/run/ccrb-observer/control.sock',0o660)
    upstream.service=service
    serving=asyncio.create_task(service.serve(listener))
    try:
        out,err=await asyncio.wait_for(sender.communicate(),100)
        if sender.returncode==0:
            result=json.loads(next(line for line in out.decode().splitlines() if line.startswith('CONTROLLER_RESULT ')).split(' ',1)[1])
            indexed={entry['client_request_id']:entry for entry in POSTS}
            assert len(POSTS)==7 and len(indexed)==7
            for entry in result['instances']:
                actual=indexed[entry['client_id']]
                assert actual['body_sha256']==entry['tls_body_sha256']
                assert actual['headers_sha256']==entry['tls_headers_sha256']
            print('TLS_RECEIVER_PROOF',json.dumps({'matched':7,'unique_sessions':len({json.loads(x['metadata']['user_id'])['session_id'] for x in POSTS}),'models':sorted({x['model'] for x in POSTS})}),flush=True)
        print(out.decode(),flush=True);print('CONTROLLER_EXIT',sender.returncode,err.decode()[-1800:],flush=True)
    finally:
        if sender.returncode is None:sender.kill();await sender.wait()
        observer_server.close();await observer_server.wait_closed();await broker.close();serving.cancel();await asyncio.gather(serving,return_exceptions=True);listener.close();await service.close()
    print('CONTROLLER_CLEANUP',json.dumps({'active':service.active,'templates':len(service.templates),'owners':len(service.owners),'instances':len(list(Path('/var/lib/ccrb-criu/instances').iterdir())),'posts':len(POSTS)}),flush=True)
asyncio.run(main())
