"""只在既有测试宿主创建 AT-only 原生实验进程，执行受控研究脚本。"""
import argparse
import ast
import base64
import json
import subprocess
from pathlib import Path


REMOTE = r'''import base64,datetime,fcntl,hashlib,json,os,re,secrets,subprocess,time,uuid,zipfile
from pathlib import Path
root=Path('/opt/agy-runtime/oauth-test-1.5.9');base=root/'credential-contract'/('rpc-'+uuid.uuid4().hex[:12]);home=base/'home';work=base/'workspace';dest=home/'.gemini/antigravity-cli/antigravity-oauth-token'
if hashlib.sha256((root/'native/agy').read_bytes()).hexdigest()!='39816d49d5ab92229952987225c23ea3fed7580699dcb4a444e0388e0ac1ce43':raise ValueError('固定原版身份核对失败')
c=json.loads(subprocess.check_output(['docker','inspect','agy-oauth-test-159']))[0]
if not c['State']['Running'] or c['Config']['User']!='1001:1001':raise ValueError('测试环境状态或身份核对失败')
dest.parent.mkdir(mode=0o700,parents=True);work.mkdir(mode=0o700)
v=json.loads((root/'home/.gemini/antigravity-cli/antigravity-oauth-token').read_text());v['token'].pop('refresh_token',None)
next_document=None
if SWAP_CREDENTIALS:
 next_document=v
 old=max((root/'credential-contract').glob('refresh-*/before.json'),key=lambda p:p.stat().st_mtime)
 v=json.loads(old.read_text());v['token'].pop('refresh_token',None)
 if v.get('id_token_email')!=next_document.get('id_token_email') or v['token']['access_token']==next_document['token']['access_token']:raise ValueError('凭据代次身份核对失败')
 if datetime.datetime.fromisoformat(v['token']['expiry'].replace('Z','+00:00')).timestamp()<time.time()+120:raise ValueError('原代次有效期不足')
 q=work/'next-token.json';q.write_text(json.dumps(next_document));q.chmod(0o600);os.chown(q,1001,1001)
dest.write_text(json.dumps(v));dest.chmod(0o600)
for p in [home,work,*home.rglob('*')]:os.chown(p,1001,1001)
budget_root=root/'credential-contract';budget_path=budget_root/'managed-model-budget.json'
with (budget_root/'managed-model-budget.lock').open('a') as lock:
 fcntl.flock(lock.fileno(),fcntl.LOCK_EX)
 budget=json.loads(budget_path.read_text()) if budget_path.exists() else {'limit':8,'reserved':0,'experiments':[]}
 if budget.get('limit')!=8 or type(budget.get('reserved')) is not int or not 0<=budget['reserved']<=8 or not isinstance(budget.get('experiments'),list):raise ValueError('私有模型预算台账无效')
 if budget['reserved']+MODEL_BUDGET>budget['limit']:raise ValueError('真实模型预算已用尽')
 if MODEL_BUDGET:
  budget['reserved']+=MODEL_BUDGET;budget['experiments'].append({'experiment':base.name,'reserved':MODEL_BUDGET})
  temp=budget_path.with_suffix('.new');temp.write_text(json.dumps(budget));temp.chmod(0o600);temp.replace(budget_path)
name='bench-agy-rpc-'+uuid.uuid4().hex[:12];csrf=secrets.token_urlsafe(32)
args=['docker','run','-d','-i','--rm','--name',name,'--user','1001:1001','--network','bridge','--read-only','--tmpfs','/tmp:rw,nosuid,nodev,noexec,size=128m','--cap-drop','ALL','--security-opt','no-new-privileges:true','--env','HOME=/home/agy','--env','USER=agy','--env','LANG=C.UTF-8','--env','AGY_CLI_DISABLE_AUTO_UPDATE=true','--env','ANTIGRAVITY_SERVER_CSRF_TOKEN='+csrf,'--mount','type=bind,src='+str(root/'native/agy')+',dst=/opt/native/agy,readonly','--mount','type=bind,src='+str(home)+',dst=/home/agy','--mount','type=bind,src='+str(work)+',dst=/workspace','--workdir','/workspace','--entrypoint','/opt/native/agy',c['Config']['Image'],'--input-format','stream-json','--output-format','stream-json']
if USE_OBSERVER:
 p=work/'active.json';p.write_text(json.dumps({'request_id':'credential-study'}));p.chmod(0o600);os.chown(p,1001,1001)
 with zipfile.ZipFile('/opt/agy-runtime/releases/deploy-1/runtime') as archive:
  for resource in ['observer-c','admission.json','telemetry-itabs.json']:
   p=work/resource;p.write_bytes(archive.read('resources/'+resource));p.chmod(0o555 if resource=='observer-c' else 0o600);os.chown(p,1001,1001)
  (work/'resources').mkdir(mode=0o700);os.chown(work/'resources',1001,1001)
  (work/'telemetry-itabs.json').replace(work/'resources/telemetry-itabs.json')
  for module in ['queue_reader.py','layer_reader.py']:
   p=work/module;p.write_bytes(archive.read(module));p.chmod(0o600);os.chown(p,1001,1001)
 if AUTH_OBSERVER_DATA:
  p=work/'observer-c';p.write_bytes(base64.b64decode(AUTH_OBSERVER_DATA));p.chmod(0o555);os.chown(p,1001,1001)
 wrapper=OBSERVER_WRAPPER
 p=work/'observer-launch.py';p.write_text(wrapper);p.chmod(0o600);os.chown(p,1001,1001)
 args[args.index('--entrypoint')+1]='python3'
 args=args[:args.index(c['Config']['Image'])+1]+['/workspace/observer-launch.py']
 args.remove('--rm')
try:
 subprocess.run(args,check=True,capture_output=True,timeout=20);port=None;end=time.monotonic()+25
 while not port and time.monotonic()<end:
  for path in (home/'.gemini/antigravity-cli/log').glob('*.log'):
   hits=re.findall(r'Language server listening on random port at (\d+) for HTTP\b',path.read_text(errors='replace'))
   if hits:port=int(hits[-1]);break
  time.sleep(.1)
 if not port:raise ValueError('原生监听器未就绪')
 preamble='from http.client import HTTPConnection\nimport json\nPORT='+str(port)+'\nCSRF='+repr(csrf)+'\n'
 code=preamble+STUDY_CODE
 p=base/'study.py';p.write_text(code);p.chmod(0o600)
 r=subprocess.run(['docker','exec','--user','1001:1001',name,'python3','-c',code],capture_output=True,text=True,timeout=120)
 for label,text in [('study.stdout',r.stdout),('study.stderr',r.stderr)]:
  p=base/label;p.write_text(text);p.chmod(0o600)
 if r.returncode:print(json.dumps({'status':'研究脚本失败','error_type':'container_script','private_root':str(base)}))
 else:print(r.stdout)
 if USE_OBSERVER:
  subprocess.run(['docker','stop','--time','40',name],capture_output=True,timeout=45)
  stopped=json.loads(subprocess.check_output(['docker','inspect',name]))[0]['State']
  counts={};token_reads=[];native_exits=[]
  generations={hashlib.sha256(v['token']['access_token'].encode()).hexdigest():1}
  if next_document:generations[hashlib.sha256(next_document['token']['access_token'].encode()).hexdigest()]=2
  p=work/'observer-events.jsonl'
  for line in p.read_text().splitlines() if p.exists() else []:
   record=json.loads(line);event=record.get('event');counts[event]=counts.get(event,0)+1
   if event=='oauth_token_read':token_reads.append({'wrapper':record['wrapper'],'generation':generations.get(record['token_sha256']),'call_id':record.get('call_id')})
   if event=='native_exit':native_exits.append({'code':record['code'],'signal':record['signal']})
  lifecycle=json.loads((work/'exit-summary.json').read_text()) if (work/'exit-summary.json').exists() else None
  print(json.dumps({'observer_events':counts,'token_reads':token_reads,'native_exits':native_exits,'lifecycle':lifecycle,'container_exit_code':stopped['ExitCode'],'private_root':str(base)}))
 if r.returncode:raise SystemExit(1)
finally:subprocess.run(['docker','rm','--force',name],capture_output=True,timeout=15)
'''

OBSERVER_WRAPPER = '''import json,os,signal,subprocess,threading,time
from pathlib import Path
from types import SimpleNamespace
os.umask(0o077)
fifo=Path('/workspace/input.pipe');os.mkfifo(fifo);held=os.open(fifo,os.O_RDWR)
r,w=os.pipe()
env=dict(os.environ)
env.update(AGY_BRIDGE_FOLDER='/workspace',AGY_BRIDGE_PROFILE='/workspace/admission.json',AGY_BRIDGE_TYPES='/workspace/admission.json',AGY_BRIDGE_BINARY='/opt/native/agy',AGY_BRIDGE_GENERATION='credential-study',AGY_BRIDGE_EVENT_FD=str(w),AGY_BRIDGE_STDIN=str(fifo))
log=Path('/workspace/native.stdout').open('wb')
child=subprocess.Popen(['/workspace/observer-c','/opt/native/agy','--input-format','stream-json','--output-format','stream-json'],env=env,pass_fds=(w,),stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT)
os.close(w)
observed={'native_pid':None}
def collect():
 with os.fdopen(r,'rb') as source,Path('/workspace/observer-events.jsonl').open('wb') as output:
  for line in source:
   output.write(line);output.flush()
   record=json.loads(line)
   if record.get('event')=='observer_ready':observed['native_pid']=record['native_pid']
thread=threading.Thread(target=collect,daemon=True);thread.start()
stopping=False;drain={'state':'unknown'}
def stop(*_):
 global stopping
 if stopping:return
 stopping=True;reader=None
 try:
  from layer_reader import LayerReader
  reader=LayerReader(SimpleNamespace(native_pid=observed['native_pid'],generation='credential-study',proc=child))
  if not hasattr(reader,'origins'):reader.origins={}
  reader.discover();deadline=time.monotonic()+15;empty_since=None
  while time.monotonic()<deadline:
   snapshot=reader.snapshot();clients=snapshot['clients'];layers=snapshot['layers']
   known=bool(layers) and {c['source'] for c in clients}>={327,2747,2992} and not snapshot['errors'] and not snapshot['layer_errors']
   empty=known and all(c['buffered_events']==0 for c in clients if c['source'] in [327,2747])
   empty=empty and all(not x.get('deferred',{}).get('events',0) and (not x['deferred_present'] or x['deferred']['resolved'] or x['deferred']['closed']) and x.get('cel',{}).get('in_flight_events',0)==0 for x in layers)
   if empty:
    if empty_since is None:empty_since=time.monotonic()
    if time.monotonic()-empty_since>=.5:drain.update(state='business_queues_empty',clients=len(clients),layers=len(layers));break
   else:empty_since=None
   time.sleep(.1)
  else:drain.update(state='timeout',clients=len(clients),layers=len(layers))
 except Exception as error:drain.update(state='unknown',error_type=type(error).__name__,attribute=getattr(error,'name',None))
 finally:
  if reader:reader.close()
  os.close(held)
signal.signal(signal.SIGTERM,stop)
code=child.wait();thread.join(3);log.close()
Path('/workspace/exit-summary.json').write_text(json.dumps({'observer_exit_code':code,'events_closed':not thread.is_alive(),'drain':drain}))
raise SystemExit(code)
'''


def main():
    """执行指定的本地受控脚本。@return 无。"""
    parser = argparse.ArgumentParser()
    parser.add_argument('study', type=Path)
    parser.add_argument('--budget', type=int, choices=range(0, 9), default=0,
        help='显式预留的模型请求额度；默认零')
    parser.add_argument('--observer', action='store_true')
    parser.add_argument('--auth-observer', type=Path)
    parser.add_argument('--swap-credentials', action='store_true')
    args = parser.parse_args()
    source = args.study.read_text()
    limits = [node.value for node in ast.parse(source).body if isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == 'MODEL_REQUEST_LIMIT' for target in node.targets)]
    if len(limits) != 1 or not isinstance(limits[0], ast.Constant) or type(limits[0].value) is not int:
        parser.error('场景必须声明唯一整数 MODEL_REQUEST_LIMIT')
    limit = limits[0].value
    if not 0 <= limit <= 8 or args.budget < limit:
        parser.error('模型场景需要显式预留足够预算')
    remote = REMOTE.replace('STUDY_CODE', repr(source)).replace('MODEL_BUDGET', str(args.budget))
    remote = remote.replace('USE_OBSERVER', repr(args.observer or bool(args.auth_observer))).replace('OBSERVER_WRAPPER', repr(OBSERVER_WRAPPER))
    encoded = base64.b64encode(args.auth_observer.read_bytes()).decode() if args.auth_observer else ''
    remote = remote.replace('AUTH_OBSERVER_DATA', repr(encoded)).replace('SWAP_CREDENTIALS', repr(args.swap_credentials))
    result = subprocess.run(['sshpass', '-f', '/root/.local/state/agy-deployment/ssh-password',
        'ssh', '-o', 'ConnectTimeout=10', 'root@main.flower-cli.com', 'python3 -'],
        input=remote, text=True, capture_output=True, timeout=230)
    print(result.stdout)
    if result.returncode:
        print(json.dumps({'status': '实验控制进程失败', 'code': result.returncode}))
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
