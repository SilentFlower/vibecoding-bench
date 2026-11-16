"""验证控制器SIGKILL后的内核收口及下一入口的遗留清理。"""
from fixture_guard import require_disposable_guest
require_disposable_guest()
import asyncio,ctypes,hashlib,json,os,shutil,signal,socket,ssl,subprocess,threading
from pathlib import Path
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
class Receiver(BaseHTTPRequestHandler):
    """通过持有的pidfd注入控制器强退。@return 合成验证结果或无。"""
    def log_message(self,*args):
        """屏蔽默认访问日志。@return 无。"""
        pass
    def do_GET(self):
        """注入仅实验使用的模板污染或控制器强退。@return 合成验证结果或无。"""
        signal.pidfd_send_signal(self.server.controller_fd,signal.SIGKILL)
        data=b'{"killed":true}';self.send_response(200);self.send_header('content-length',str(len(data)));self.end_headers();self.wfile.write(data)
async def main():
    """在一次性客体运行合成验收。@return 合成验证结果或无。"""
    subprocess.run(['ip','link','set','lo','up'],check=True)
    Path('/etc/hosts').write_text('127.0.0.1 localhost api.anthropic.com\n');Path('/probe/death-start').unlink(missing_ok=True)
    for name in ['/probe/native','/var/lib/ccrb-criu','/run/ccrb-criu']:
        shutil.rmtree(name,ignore_errors=True);Path(name).mkdir(mode=0o700,parents=True)
    for name in ['templates','instances']:Path('/var/lib/ccrb-criu',name).mkdir(mode=0o700)
    os.chown('/probe/native',1001,1001);os.chown('/run/ccrb-criu',0,1001);Path('/run/ccrb-criu').chmod(0o750)
    listener=socket.socket(socket.AF_UNIX);listener.bind('/run/ccrb-criu/control.sock');listener.listen();os.chown('/run/ccrb-criu/control.sock',0,1001);Path('/run/ccrb-criu/control.sock').chmod(0o660)
    subprocess.run(['openssl','req','-x509','-newkey','rsa:2048','-nodes','-days','1','-subj','/CN=api.anthropic.com','-addext','subjectAltName=DNS:api.anthropic.com','-keyout','/probe/controller-ca.key','-out','/probe/controller-ca.pem'],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    server=ThreadingHTTPServer(('127.0.0.1',443),Receiver);tls=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER);tls.load_cert_chain('/probe/controller-ca.pem','/probe/controller-ca.key');server.socket=tls.wrap_socket(server.socket,server_side=True)
    mask=sum(1<<cap for cap in (0,1,3,5,6,7,8,12,18,19,21,24,25));libc=ctypes.CDLL(None)
    for cap in range(int(Path('/proc/sys/kernel/cap_last_cap').read_text())+1):
        if not mask&(1<<cap):assert libc.prctl(24,cap,0,0,0)==0
    header=(ctypes.c_uint*2)(0x20080522,0);data=(ctypes.c_uint*6)(mask,mask,0,0,0,0)
    assert libc.capset(ctypes.byref(header),ctypes.byref(data))==0
    assert libc.prctl(38,1,0,0,0)==0
    sender=await asyncio.create_subprocess_exec('/probe/restricted-launch','/probe/production-filter.bpf','/usr/local/bin/python3','-B','/probe/death_sender.py',env={**os.environ,'TEST_UPSTREAM':'https://api.anthropic.com'},stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE)
    controller=await asyncio.create_subprocess_exec('/usr/local/bin/python3','-u','/probe/death_controller.py',str(sender.pid),str(listener.fileno()),pass_fds=(listener.fileno(),),stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE)
    assert await asyncio.wait_for(controller.stdout.readline(),5)==b'READY\n';listener.close();server.controller_fd=os.pidfd_open(controller.pid)
    threading.Thread(target=server.serve_forever,daemon=True).start();Path('/probe/death-start').touch(mode=0o644)
    out,err=await asyncio.wait_for(sender.communicate(),45);await controller.communicate()
    print(out.decode(),flush=True);print('DEATH_EXIT',sender.returncode,controller.returncode,err.decode()[-1000:],flush=True)
    assert sender.returncode==0 and controller.returncode==-signal.SIGKILL
    remaining={name:len(list(Path('/var/lib/ccrb-criu',name).iterdir())) for name in ('templates','instances')}
    assert remaining['templates']==1 and remaining['instances']==1,remaining
    Path('/usr/local/bin/account-sender').write_text('#!/bin/sh\nsleep .2\nexit 0\n');Path('/usr/local/bin/account-sender').chmod(0o755)
    Path('/run/v3').mkdir(exist_ok=True);Path('/run/v3/sender.json').write_bytes(Path('/probe/criu-config.json').read_bytes())
    tools=Path('/opt/ccrb-criu');profile={'protocol':1,'entropy_profile':'bun143-wipeonfork-v1','image_sha256':'564019c9560e960e96875c9663975491534b27c789ea3d23e5c13309ff293c79','image_bytes':112843960,'criu':json.loads(Path('/probe/bookworm-profile.json').read_text())['criu'],'files':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in tools.iterdir() if p.is_file() and p.name!='profile.json'}}
    (tools/'profile.json').write_text(json.dumps(profile));(tools/'profile.json').chmod(0o644)
    restarted=await asyncio.create_subprocess_exec('/usr/local/bin/python3','-E','-s','/opt/ccrb-criu/entry.py',stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE)
    output,error=await asyncio.wait_for(restarted.communicate(),10);assert restarted.returncode==0,(output,error)
    after={name:len(list(Path('/var/lib/ccrb-criu',name).iterdir())) for name in ('templates','instances')};assert set(after.values())=={0},after
    print('DEATH_RECOVERY',json.dumps({'before':remaining,'after':after,'entry_exit':restarted.returncode}),flush=True)
    os.close(server.controller_fd)
asyncio.run(main())
