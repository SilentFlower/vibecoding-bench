"""使用合成凭据和纯本地上游运行官方 CLI，核对状态栏额度。"""
import fcntl
import json
import os
import pty
import select
import struct
import subprocess
import termios
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

root = Path('/lab')
collect = os.environ.get('LAB_COLLECTOR', '1') == '1'
cwd = Path('/workspace')
cwd.mkdir(exist_ok=True)
home = Path('/home/node')
(home / '.claude').mkdir(exist_ok=True)
started = time.time()
requests_seen = []
reset5 = int(started) + 7200
reset7 = int(started) + 172800

class Handler(BaseHTTPRequestHandler):
    """只为合成模型请求返回符合官方协议的 SSE。"""
    def do_POST(self):
        """处理本地合成请求，返回 None。"""
        body = self.rfile.read(int(self.headers.get('Content-Length', '0')))
        payload = json.loads(body)
        user_id = payload.get('metadata', {}).get('user_id')
        identity = json.loads(user_id) if isinstance(user_id, str) else {}
        requests_seen.append({'method':'POST','path':self.path,'model':payload.get('model'),
            'device_identity':{key:identity.get(key) for key in ('device_id','account_uuid')}})
        if '/messages' in self.path:
            model = json.loads(body).get('model', 'claude-opus-4-6')
            self.send_response(200)
            self.send_header('Content-Type', 'text/event-stream')
            self.send_header('anthropic-ratelimit-unified-status', 'allowed')
            self.send_header('anthropic-ratelimit-unified-5h-utilization', '0.42')
            self.send_header('anthropic-ratelimit-unified-5h-reset', str(reset5))
            self.send_header('anthropic-ratelimit-unified-7d-utilization', '0.35')
            self.send_header('anthropic-ratelimit-unified-7d-reset', str(reset7))
            self.send_header('request-id', 'synthetic-quota-message')
            self.end_headers()
            sequence = [
              ('message_start', {'type':'message_start','message':{'id':'msg_synthetic_quota','type':'message','role':'assistant','content':[], 'model':model,'stop_reason':None,'stop_sequence':None,'usage':{'input_tokens':10,'output_tokens':0,'cache_creation_input_tokens':0,'cache_read_input_tokens':0}}}),
              ('content_block_start', {'type':'content_block_start','index':0,'content_block':{'type':'text','text':''}}),
              ('content_block_delta', {'type':'content_block_delta','index':0,'delta':{'type':'text_delta','text':'Synthetic coding response.'}}),
              ('content_block_stop', {'type':'content_block_stop','index':0}),
              ('message_delta', {'type':'message_delta','delta':{'stop_reason':'end_turn','stop_sequence':None},'usage':{'output_tokens':5}}),
              ('message_stop', {'type':'message_stop'})]
            for event, payload in sequence:
                self.wfile.write(('event: '+event+'\ndata: '+json.dumps(payload)+'\n\n').encode())
                self.wfile.flush()
            self.close_connection = True
        else:
            self.send_response(200)
            self.send_header('Content-Type','application/json')
            self.end_headers()
            self.wfile.write(b'{}')
            self.close_connection = True
    def do_GET(self):
        """记录本地读取请求，返回 None。"""
        requests_seen.append({'method':'GET','path':self.path})
        self.send_response(200)
        self.send_header('Content-Type','application/json')
        self.end_headers()
        self.wfile.write(b'{}')
        self.close_connection = True
    def log_message(self, *args):
        """静默合成服务的默认日志，返回 None。"""
        pass

server = ThreadingHTTPServer(('127.0.0.1',0),Handler)
threading.Thread(target=server.serve_forever,daemon=True).start()
config = {'source':'cli:run:synthetic-official','identity':'synthetic-identity','cwd':str(cwd),'session_dir':str(home / '.claude/projects/-workspace'), 'output':'/lab/cli-quota.jsonl','started_at':started,'previous_command':'printf ORIGINAL_STATUSLINE'}
(root / 'quota-config.json').write_text(json.dumps(config))
(home / '.claude/settings.json').write_text(json.dumps({'statusLine':{'type':'command','command':'python3 /lab/wrapper.py' if collect else 'printf ORIGINAL_STATUSLINE'}, 'autoMemoryEnabled':False,'model':'claude-opus-4-6','skipDangerousModePermissionPrompt':True,'permissions':{'defaultMode':'bypassPermissions'}}))
(home / '.claude.json').write_text(json.dumps({'userID':'a'*64,'machineID':'b'*64,
    'oauthAccount':{'accountUuid':'synthetic-account','emailAddress':'synthetic@example.invalid','organizationUuid':'synthetic-org'},
    'hasCompletedOnboarding':True,'bypassPermissionsModeAccepted':True,'hasSeenAutoDefaultNudge':True,'projects':{'/workspace':{'hasTrustDialogAccepted':True}}}))
(home / '.claude/.credentials.json').write_text(json.dumps({'claudeAiOauth':{'accessToken':'synthetic-oauth','refreshToken':'synthetic-refresh','expiresAt':(started+36000)*1000,'scopes':['user:inference','user:profile'],'subscriptionType':'max','rateLimitTier':'default_claude_max_5x'}}))
subprocess.run(['chown','-R','1000:1000','/home/node','/workspace','/lab'],check=True)
master, slave = pty.openpty()
fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack('HHHH',60,220,0,0))
environment = {**os.environ,'HOME':str(home),'TERM':'xterm-256color','ANTHROPIC_BASE_URL':f'http://127.0.0.1:{server.server_port}', 'CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC':'1'}
process = subprocess.Popen(['setpriv','--reuid=1000','--regid=1000','--init-groups','/official/claude','--dangerously-skip-permissions'],cwd=cwd,env=environment,stdin=slave,stdout=slave,stderr=slave,start_new_session=True)
os.close(slave)
transcript = bytearray()
prompt_sent = False
try:
    deadline = time.monotonic()+40
    while time.monotonic()<deadline and process.poll() is None:
        if select.select([master],[],[],0.2)[0]:
            try:
                chunk=os.read(master,65536)
            except OSError:
                break
            transcript.extend(chunk)
        if not prompt_sent and time.monotonic() > deadline-35:
            os.write(master,b'Please give a short coding reply.\r')
            prompt_sent=True
        if ((root / 'cli-quota.jsonl').is_file() if collect else b'Synthetic coding response.' in transcript) and b'ORIGINAL_STATUSLINE' in transcript:
            deadline = min(deadline, time.monotonic() + 3)
finally:
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill(); process.wait()
    os.close(master)
    (root / 'terminal.log').write_bytes(transcript)
    (root / 'requests.json').write_text(json.dumps(requests_seen,indent=2))
    server.shutdown()
print(json.dumps({'version':subprocess.check_output(['/official/claude','--version'],text=True).strip(),'requests':requests_seen,'quota':(root / 'cli-quota.jsonl').read_text() if (root / 'cli-quota.jsonl').is_file() else None,'statusline_calls':len((root / 'statusline.jsonl').read_text().splitlines()) if (root / 'statusline.jsonl').is_file() else 0},ensure_ascii=False))
