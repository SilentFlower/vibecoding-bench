"""合成身份驱动产品控制器的FD交接与单次模型提交。"""
import ssl,urllib.request,base64,array,concurrent.futures,fcntl,hashlib,json,os,select,socket,subprocess,time,threading
from pathlib import Path
from uuid import uuid4
import probe_memfd_followup as common
ROOT=Path('/probe/native')
KEY='a'*64
CONTROL=None


def peak_snapshot():
    """四个恢复副本同时就绪时请求可信端采样。@return 无。"""
    context=ssl.create_default_context(cafile='/probe/controller-ca.pem')
    with urllib.request.urlopen('https://api.anthropic.com/__test_snapshot',context=context,timeout=10) as response:
        proof=json.loads(response.read())
    assert proof['workers']==5 and proof['unique_image_inodes']==int(os.environ.get('CCRB_TEST_EXPECTED_IMAGE_INODES','1')),proof
    print('SHARED_IMAGE_PEAK '+json.dumps(proof),flush=True)


BARRIER=threading.Barrier(4,action=peak_snapshot)

def frame(fd):
    """有界读取工作帧。@param fd 合成夹具参数。@return 合成验证结果或无。"""
    return common.frame(fd,timeout=20)
def recv(connection,n):
    """接管精确数量的控制描述符与元数据。@param connection 合成夹具参数。@param n 合成夹具参数。@return 合成验证结果或无。"""
    marker,ancillary,flags,_=connection.recvmsg(1,socket.CMSG_SPACE(32))
    assert marker==b'F' and not flags
    result=array.array('i')
    for level,kind,data in ancillary:
        assert level==socket.SOL_SOCKET and kind==socket.SCM_RIGHTS
        result.frombytes(data)
    assert len(result)==n
    return list(result), frame(connection.fileno())
def connect(value):
    """连接固定控制器并发送合成命令。@param value 合成夹具参数。@return 合成验证结果或无。"""
    s=socket.socket(socket.AF_UNIX);s.connect('/run/ccrb-criu/control.sock');s.sendall(json.dumps(value).encode()+b'\n');return s

def clone(index,tid,seed):
    """恢复独立副本并核对TLS接收证据。@param index 合成夹具参数。@param tid 合成夹具参数。@param seed 合成夹具参数。@return 合成验证结果或无。"""
    started=time.monotonic();wid=str(uuid4());nonce=os.urandom(32).hex()
    s=connect({'type':'restore','key':KEY,'template':tid,'worker':wid,'nonce':nonce})
    descriptors=[]
    try:
        first,ns=recv(s,1);descriptors+=first
        s.sendall(b'{"type":"start"}\n')
        pipes,ready=recv(s,3);descriptors+=pipes
        incoming,outgoing,pidfd=pipes
        assert ready['worker']==wid and ready['nonce']==nonce
        bind={'schema_version':2,'type':'worker_restore_bind','worker_id':seed,'template_id':tid,'new_worker_id':wid,'nonce':nonce}
        os.write(incoming,json.dumps(bind).encode()+b'\n');bound=frame(outgoing)
        assert bound['type']=='worker_ready' and bound['worker_id']==wid and bound['restore_binding']['nonce']==nonce
        with open('/proc/'+str(ready['pid'])+'/exe','rb') as f:
            assert hashlib.file_digest(f,'sha256').hexdigest()=='564019c9560e960e96875c9663975491534b27c789ea3d23e5c13309ff293c79'
            f.seek(0x232d5b3);instruction=f.read(15).hex()
            assert instruction=='4883c4185b415c415d415e415f5dc3'
        capture=str(uuid4())
        observer=subprocess.Popen(['/usr/local/bin/python3','-E','-s','/opt/ccrb-tls-observer/client.py','--pid',str(ready['pid']),'--worker',wid,'--capture',capture,'--image',ready['image']],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL)
        observed=frame(observer.stdout.fileno());assert observed.get('ready') is True,observed
        prepared_ms=round((time.monotonic()-started)*1000,2)
        if 3<=index<7:BARRIER.wait(timeout=30)
        if index==8:CONTROL.close()
        rid=str(uuid4());marker='product-restore-'+rid
        command={'schema_version':2,'worker_id':wid,'type':'request_input','request_id':rid,'input':{'schema_version':1,'request_id':rid,'headers':[],'context':{'sessionId':str(uuid4()),'promptId':str(uuid4())},'body':{'model':('claude-sonnet-4-6' if index%2==0 else 'claude-haiku-4-5'),'max_tokens':64,'stream':False,'messages':[{'role':'user','content':marker}]}}}
        os.write(incoming,json.dumps(command).encode()+b'\n')
        terminal=None;prepared=None;chunks=[]
        for _ in range(20):
            event=frame(outgoing)
            assert event['worker_id']==wid and event['request_id']==rid
            if event.get('payload',{}).get('type')=='cc_prepared':prepared=event['payload']
            if event.get('payload',{}).get('type')=='response_chunk':chunks.append(base64.b64decode(event['payload']['data_b64']))
            if event.get('payload',{}).get('type')=='completed':terminal=event['payload']['state']
            if event['type']=='worker_idle':break
        assert terminal=='success',terminal
        assert marker in b''.join(chunks).decode()
        client_id=next(header[1] for header in prepared['headers'] if header[0].lower()=='x-client-request-id')
        observer.stdin.write(json.dumps({'capture_id':capture,'client_request_id':client_id}).encode()+b'\n');observer.stdin.flush()
        evidence=frame(observer.stdout.fileno());observer.wait(timeout=5)
        assert evidence.get('complete') is True,evidence
        assert evidence['worker_pid']==ready['pid']
        original=prepared['body'].encode();actual=evidence['body'].encode()
        differences=[i for i,(a,b) in enumerate(zip(original,actual)) if a!=b]
        delta={'prepared_bytes':len(original),'actual_bytes':len(actual),'changed_bytes':len(differences),'first_offset':differences[0] if differences else None}
        headers=[[k.lower(),v.strip()] for k,v in evidence['headers']]
        header_sha=hashlib.sha256(json.dumps(headers,separators=(',',':')).encode()).hexdigest()
        observer.stdin.close();observer.stdout.close()
        second_id=str(uuid4());second_marker='product-restore-'+second_id
        second={'schema_version':2,'worker_id':wid,'type':'request_input','request_id':second_id,'input':{'schema_version':1,'request_id':second_id,'headers':[],'context':command['input']['context'],'body':{'model':'claude-sonnet-4-6','max_tokens':64,'stream':True,'messages':[{'role':'user','content':second_marker}],'tools':[{'name':'research_echo','description':'合成离线工具','input_schema':{'type':'object','properties':{'marker':{'type':'string'}},'required':['marker']}}]}}}
        os.write(incoming,json.dumps(second).encode()+b'\n')
        streamed=[];terminal=None
        for _ in range(50):
            event=frame(outgoing)
            assert event['worker_id']==wid and event['request_id']==second_id
            payload=event.get('payload',{})
            if payload.get('type')=='response_chunk':streamed.append(base64.b64decode(payload['data_b64']))
            if payload.get('type')=='completed':terminal=payload['state']
            if event['type']=='worker_idle':break
        assert terminal=='success',terminal
        streamed=b''.join(streamed).decode()
        assert second_marker in streamed and 'tool_use' in streamed and 'message_stop' in streamed
        canceled=False
        if index==0:
            cancel_id=str(uuid4());cancel_marker='product-restore-'+cancel_id+' cancel-probe'
            cancel={**second,'request_id':cancel_id,'input':{**second['input'],'request_id':cancel_id,'body':{**second['input']['body'],'messages':[{'role':'user','content':cancel_marker}]}}}
            os.write(incoming,json.dumps(cancel).encode()+b'\n')
            sent_cancel=False
            for _ in range(50):
                event=frame(outgoing);assert event['request_id']==cancel_id
                payload=event.get('payload',{})
                if payload.get('type')=='response_chunk' and not sent_cancel:
                    os.write(incoming,json.dumps({'schema_version':2,'type':'request_cancel','worker_id':wid,'request_id':cancel_id}).encode()+b'\n');sent_cancel=True
                if payload.get('type')=='completed':canceled=payload['state']=='canceled'
                if event['type']=='worker_idle':break
            assert sent_cancel and canceled
        s.close()
        assert select.select(first,[],[],5)[0]
        return {'index':index,'pid':ready['pid'],'namespace':ns['pid'],'worker_id':wid,'prepared_ms':prepared_ms,'success':True,'instruction':instruction,'tls_pid':evidence['worker_pid'],'tls_body_sha256':evidence['body_sha256'],'tls_headers_sha256':header_sha,'client_id':client_id,'prepared_delta':delta,'second_stream_tool_success':True,'business_cancel_verified':canceled,'template_revoked_during_requests':index==8}
    finally:
        s.close()
        for descriptor in descriptors:os.close(descriptor)

def rejected(value):
    """核对非法请求在创建前被拒绝。@param value 合成夹具参数。@return 合成验证结果或无。"""
    connection=connect(value)
    try:
        try:data=connection.recv(1)
        except ConnectionResetError:data=b''
        assert data==b'',data
    finally:connection.close()
def faults(tid,seed,corrupt=True):
    """注入身份、取消、模板损坏与外部对端故障。@param tid 合成夹具参数。@param seed 合成夹具参数。@param corrupt 是否注入快照污染。@return 合成验证结果或无。"""
    original={'type':'restore','key':KEY,'template':tid,'worker':str(uuid4()),'nonce':os.urandom(32).hex()}
    for value in ({**original,'key':'b'*64},{**original,'template':str(uuid4())},{**original,'worker':seed},{**original,'pid':os.getpid()},{**original,'path':'/etc/passwd'}):rejected(value)
    for acknowledge in (False,True):
        value={**original,'worker':str(uuid4()),'nonce':os.urandom(32).hex()}
        connection=connect(value);descriptors,namespace=recv(connection,1)
        if acknowledge:connection.sendall(b'{"type":"start"}\n')
        connection.close()
        assert select.select(descriptors,[],[],5)[0]
        for fd in descriptors:os.close(fd)
    payload=json.dumps(original)
    script="import socket,sys; s=socket.socket(socket.AF_UNIX); s.connect('/run/ccrb-criu/control.sock'); s.sendall(sys.argv[1].encode()+b'\\n');\ntry: value=s.recv(1)\nexcept ConnectionResetError: value=b''\nassert value==b''"
    subprocess.run(['/usr/local/bin/python3','-I','-c',script,payload],check=True,timeout=5)
    if corrupt:
        response=urllib.request.urlopen('https://api.anthropic.com/__test_corrupt/'+tid,context=ssl.create_default_context(cafile='/probe/controller-ca.pem'),timeout=5)
        assert json.loads(response.read())['changed'] is True
        rejected({**original,'worker':str(uuid4()),'nonce':os.urandom(32).hex()})
    return {'invalid_identity_or_schema':5,'cancel_before_ack':True,'cancel_after_ack':True,'foreign_peer':True,'corrupt_snapshot':corrupt}

def main():
    """在一次性客体运行合成验收。@return 合成验证结果或无。"""
    global CONTROL
    ROOT.mkdir(exist_ok=True)
    sid=str(uuid4());tid=str(uuid4());root=ROOT/sid;root.mkdir()
    for name in ('home','config','cwd'):(root/name).mkdir()
    (root/'config/.claude.json').write_text(json.dumps({'userID':'f'*64,'oauthAccount':{'accountUuid':'11111111-1111-4111-8111-111111111111','organizationUuid':'22222222-2222-4222-8222-222222222222','emailAddress':'fixture@example.test'}}))
    env={'HOME':str(root/'home'),'CLAUDE_CONFIG_DIR':str(root/'config'),'PATH':'/usr/bin:/bin','LANG':'C.UTF-8','CCRB_WORKER_ID':sid,'CCRB_TEMPLATE_ID':tid,'CCRB_CACHE_POLICY':'preserve','CCRB_TELEMETRY':'off','CCRB_NATIVE_INGRESS_POLICY':'local_base_url','CLAUDE_CODE_ENTRYPOINT':'cli','DISABLE_AUTO_COMPACT':'1','CLAUDE_CODE_GATEWAY_HINT_HEADERS':'1','CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC':'1','DISABLE_AUTOUPDATER':'1','DISABLE_TELEMETRY':'1','DISABLE_ERROR_REPORTING':'1','CLAUDE_CODE_OAUTH_TOKEN':'synthetic-controller-bearer','ANTHROPIC_BASE_URL':os.environ['TEST_UPSTREAM'],'NODE_EXTRA_CA_CERTS':'/probe/controller-ca.pem'}
    worker=subprocess.Popen(['/probe/ccrb-runtime','--version'],cwd=root/'cwd',env=env,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,start_new_session=True)
    control=None
    try:
        ready=frame(worker.stdout.fileno());assert ready['restore_template']==tid
        control=connect({'type':'template','key':KEY,'template':tid,'worker':sid,'pid':worker.pid});registered=frame(control.fileno());assert registered['type']=='template_ready';CONTROL=control
        results=[clone(i,tid,sid) for i in range(3)]
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:results+=list(pool.map(lambda i:clone(i,tid,sid),range(3,7)))
        assert worker.poll() is None
        worker.kill();worker.wait(timeout=5)
        results.append(clone(7,tid,sid))
        failures=faults(tid,sid,corrupt=False)
        results.append(clone(8,tid,sid))
        control.close();control=None;time.sleep(.05)
        rejected({'type':'restore','key':KEY,'template':tid,'worker':str(uuid4()),'nonce':os.urandom(32).hex()})
        failures['expired_template']=True
        print('CONTROLLER_RESULT '+json.dumps({'success':True,'source_alive_before_retirement':True,'restore_after_seed_exit':True,'instances':results,'faults':failures}),flush=True)
    finally:
        if control:control.close()
        worker.kill();worker.wait()
if __name__=='__main__':main()
