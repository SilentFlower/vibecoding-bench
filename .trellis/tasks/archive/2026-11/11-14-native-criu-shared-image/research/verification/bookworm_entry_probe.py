"""从实际可信入口驱动完整进程池配对测试。"""
from fixture_guard import require_disposable_guest
require_disposable_guest()
import asyncio,ctypes,hashlib,json,os,shutil,ssl,subprocess,threading
from pathlib import Path
from http.server import ThreadingHTTPServer
import sys
sys.path.insert(0,'/probe')
from probe_fanout import Upstream,POSTS
async def main():
    """在一次性客体运行合成验收。@return 合成验证结果或无。"""
    subprocess.run(['ip','link','set','lo','up'],check=True)
    Path('/etc/hosts').write_text('127.0.0.1 localhost api.anthropic.com\n')
    for name in ('/probe/native','/probe/captures','/var/lib/ccrb-criu'):
        shutil.rmtree(name,ignore_errors=True);Path(name).mkdir(mode=0o700,parents=True)
    os.chown('/probe/native',1001,1001);os.chown('/probe/captures',1001,1001)
    Path('/run/v3').mkdir(exist_ok=True);config=Path('/run/v3/sender.json');config.write_bytes(Path('/probe/criu-config.json').read_bytes());os.chown(config,0,1001);config.chmod(0o640)
    tools=Path('/opt/ccrb-criu')
    profile={'protocol':1,'entropy_profile':'bun143-wipeonfork-v1','image_sha256':'564019c9560e960e96875c9663975491534b27c789ea3d23e5c13309ff293c79','image_bytes':112843960,'criu':json.loads(Path('/probe/bookworm-profile.json').read_text())['criu'],'files':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in tools.iterdir() if p.is_file() and p.name!='profile.json'},'development':True}
    (tools/'profile.json').write_text(json.dumps(profile));(tools/'profile.json').chmod(0o644)
    subprocess.run(['openssl','req','-x509','-newkey','rsa:2048','-nodes','-days','1','-subj','/CN=api.anthropic.com','-addext','subjectAltName=DNS:api.anthropic.com','-keyout','/probe/controller-ca.key','-out','/probe/controller-ca.pem'],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    upstream=ThreadingHTTPServer(('127.0.0.1',443),Upstream);tls=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER);tls.load_cert_chain('/probe/controller-ca.pem','/probe/controller-ca.key');upstream.socket=tls.wrap_socket(upstream.socket,server_side=True)
    mask=sum(1<<cap for cap in (0,1,3,5,6,7,8,12,18,19,21,24,25));libc=ctypes.CDLL(None)
    for cap in range(int(Path('/proc/sys/kernel/cap_last_cap').read_text())+1):
        if not mask&(1<<cap):assert libc.prctl(24,cap,0,0,0)==0
    header=(ctypes.c_uint*2)(0x20080522,0);data=(ctypes.c_uint*6)(mask,mask,0,0,0,0)
    assert libc.capset(ctypes.byref(header),ctypes.byref(data))==0
    assert libc.prctl(38,1,0,0,0)==0
    threading.Thread(target=upstream.serve_forever,daemon=True).start()
    environment={**os.environ,'V3_NATIVE_RELEASE_PUBLIC_KEY':json.loads(Path('/probe/test-public-key.json').read_text()),'CCRB_TEST_RELEASE_ROOT':'/probe/releases','CCRB_TEST_CRIU_CONFIG':'/probe/criu-config.json','CCRB_TEST_CRIU_IDENTITY':'/probe/criu-identity.json','CCRB_TEST_CA_FILE':'/probe/controller-ca.pem','CCRB_TLS_OBSERVER':'/opt/ccrb-tls-observer/client.py'}
    entry=await asyncio.create_subprocess_exec('/usr/local/bin/python3','-E','-s','/opt/ccrb-criu/entry.py',env=environment,stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE)
    async def collect(stream):
        """实时保留离线验收进度。@param stream 子进程流。@return 完整输出。"""
        chunks=[]
        while line:=await stream.readline():
            print(line.decode(errors='replace'),end='',flush=True)
            chunks.append(line)
        return b''.join(chunks)
    out,err,_=await asyncio.wait_for(asyncio.gather(collect(entry.stdout),collect(entry.stderr),entry.wait()),240)
    print(out.decode(),flush=True);print('ENTRY_EXIT',entry.returncode,err.decode()[-1800:],flush=True)
    print('ENTRY_CLEANUP',json.dumps({'instances':len(list(Path('/var/lib/ccrb-criu/instances').iterdir())),'templates':len(list(Path('/var/lib/ccrb-criu/templates').iterdir())),'posts':len(POSTS)}),flush=True)
    assert entry.returncode==0 and len(POSTS)==1
asyncio.run(main())
