"""核对控制器强退后恢复实例的实际退出。"""
import json
import os
import select
import ssl
import subprocess
import time
import urllib.request
from pathlib import Path
from uuid import uuid4
from controller_sender import ROOT, KEY, frame, recv, connect

def main():
    """在一次性客体运行合成验收。@return 合成验证结果或无。"""
    ROOT.mkdir(exist_ok=True)
    sid=str(uuid4());tid=str(uuid4());root=ROOT/sid;root.mkdir()
    for name in ('home','config','cwd'):(root/name).mkdir()
    (root/'config/.claude.json').write_text(json.dumps({'userID':'f'*64,'oauthAccount':{'accountUuid':'11111111-1111-4111-8111-111111111111','organizationUuid':'22222222-2222-4222-8222-222222222222','emailAddress':'fixture@example.test'}}))
    env={'HOME':str(root/'home'),'CLAUDE_CONFIG_DIR':str(root/'config'),'PATH':'/usr/bin:/bin','LANG':'C.UTF-8','CCRB_WORKER_ID':sid,'CCRB_TEMPLATE_ID':tid,'CCRB_CACHE_POLICY':'preserve','CCRB_TELEMETRY':'off','CCRB_NATIVE_INGRESS_POLICY':'local_base_url','CLAUDE_CODE_ENTRYPOINT':'cli','DISABLE_AUTO_COMPACT':'1','CLAUDE_CODE_GATEWAY_HINT_HEADERS':'1','CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC':'1','DISABLE_AUTOUPDATER':'1','DISABLE_TELEMETRY':'1','DISABLE_ERROR_REPORTING':'1','CLAUDE_CODE_OAUTH_TOKEN':'synthetic-controller-bearer','ANTHROPIC_BASE_URL':os.environ['TEST_UPSTREAM'],'NODE_EXTRA_CA_CERTS':'/probe/controller-ca.pem'}
    worker=subprocess.Popen(['/probe/ccrb-runtime','--version'],cwd=root/'cwd',env=env,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,start_new_session=True)
    control=None
    try:
        ready=frame(worker.stdout.fileno());assert ready['restore_template']==tid
        control=connect({'type':'template','key':KEY,'template':tid,'worker':sid,'pid':worker.pid});registered=frame(control.fileno());assert registered['type']=='template_ready'
        wid=str(uuid4());nonce=os.urandom(32).hex()
        connection=connect({'type':'restore','key':KEY,'template':tid,'worker':wid,'nonce':nonce})
        namespace,meta=recv(connection,1);connection.sendall(b'{"type":"start"}\n')
        descriptors,ready=recv(connection,3);incoming,outgoing,pidfd=descriptors
        os.write(incoming,json.dumps({'schema_version':2,'type':'worker_restore_bind','worker_id':sid,'template_id':tid,'new_worker_id':wid,'nonce':nonce}).encode()+b'\n')
        assert frame(outgoing)['worker_id']==wid
        assert not select.select([namespace[0],pidfd],[],[],0)[0]
        response=urllib.request.urlopen('https://api.anthropic.com/__test_kill',context=ssl.create_default_context(cafile='/probe/controller-ca.pem'),timeout=5)
        assert json.loads(response.read())['killed']
        assert select.select(namespace,[],[],5)[0]
        assert select.select([pidfd],[],[],5)[0]
        assert worker.poll() is None
        print('DEATH_RESULT '+json.dumps({'controller_killed':True,'namespace_exited':True,'worker_exited':True,'seed_alive':True,'worker_pid':ready['pid'],'namespace_pid':meta['pid'],'posts':0}),flush=True)
        connection.close()
        for fd in namespace+descriptors:os.close(fd)
    finally:
        if control:control.close()
        worker.kill();worker.wait()
if __name__=='__main__':
    while not Path('/probe/death-start').exists():time.sleep(.02)
    main()
