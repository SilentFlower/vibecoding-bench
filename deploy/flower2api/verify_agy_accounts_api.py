"""隔离运行真实网关HTTP与SQLite，原生管理桥使用合成服务，模型提交为零。"""
import argparse
import concurrent.futures
import copy
import json
import os
import socket
import sqlite3
import subprocess
import tempfile
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, build_opener, ProxyHandler

ROOT = Path(__file__).resolve().parents[2]
SECRET = 'synthetic-agy-internal-token-' * 2


def main(slow: bool = False):
    """验证平台管理和原账号回填。@param slow 追加真实时间的慢刷新回归。@return 无。"""
    sessions, tokens, receipts, retired = {}, {}, {}, {}
    unstarted_refreshes = []
    counts = {'refresh':0,'proxy_refresh':0,'observation':0}
    fail_reply = threading.Event()
    fail_exchange_reply = threading.Event()
    fail_before_start = threading.Event()
    verify_identity_only = threading.Event()
    suspend_recovery = threading.Event()
    fail_authorization_start = threading.Event()
    hold_authorization = threading.Event()
    authorization_reserved = threading.Event()
    release_authorization = threading.Event()
    hold_refresh, refresh_started, release_refresh = (threading.Event() for _ in range(3))
    native_busy = threading.Event()
    active_refreshes = set()

    def native(email, access, refresh='synthetic-rt1'):
        """生成合成原生回执。@param email 已核验身份。@param access AT。@param refresh RT。@return 私有结果。"""
        tokens[access] = email
        counts['observation']+=1
        return {'email_address':email,'document':{'auth_method':'consumer','id_token_email':email,
            'token':{'access_token':access,'refresh_token':refresh,'expiry':'2099-01-01T00:00:00Z'}},
            'capabilities':{'source':'synthetic-native','observed_at_ms':int(time.time()*1000),'models':['gemini-synthetic'],'observation_marker':counts['observation']}}

    class Helper(BaseHTTPRequestHandler):
        """受信管理通道的合成原生驱动。"""

        def log_message(self, *_):
            """测试日志保持脱敏。@return 无。"""

        def do_GET(self):
            """提供合成任务线路引用。@return 无。"""
            assert self.headers['Authorization']=='Bearer '+SECRET
            known = self.path == '/internal/v3/proxy-references'
            payload = b'{"complete":true,"references":[]}' if known else '{"detail":"合成入口未配置"}'.encode()
            self.send_response(200 if known else 404)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def do_POST(self):
            """处理受信白名单操作。@return 无。"""
            assert self.headers['Authorization']=='Bearer '+SECRET
            path = self.path.partition('?')[0]
            if path.startswith('/internal/v3/agy-environments/'):
                self.send_response(404)
                self.send_header('Content-Length', '0')
                self.end_headers()
                return
            body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            action = path.rsplit('/',1)[-1]
            status = 200
            if path.startswith('/internal/v3/quiesce/'):
                assert body['owner'].startswith('gateway-config:') and body['generation']
                result = {'ok': True}
            elif action=='verify':
                email = tokens[body['document']['token']['access_token']]
                result = native(email, body['document']['token']['access_token'])
            elif action=='start':
                identity = body.get('operation_id') or uuid.uuid4().hex
                if body['account_id'] is not None:
                    with sqlite3.connect(database_path) as database:
                        assert database.execute('SELECT operation_id,generation,phase FROM account_credential_states WHERE account_id=?',
                            (body['account_id'],)).fetchone() == (identity, body['generation'], 'reauth')
                if hold_authorization.is_set():
                    authorization_reserved.set()
                    assert release_authorization.wait(10)
                result = {'session_id':identity,'auth_url':'https://accounts.google.com/synthetic'}
                if fail_authorization_start.is_set():
                    status = 503
                else:
                    assert identity not in retired
                    sessions[identity] = body
            elif action=='exchange':
                identity = body['session_id']
                session = sessions[identity]
                target = session['account_id']
                session['code_sent'] = True
                email = 'wrong@example.test' if body['code']=='synthetic-wrong-account' else 'same@example.test' if target else 'new@example.test'
                result = native(email, 'synthetic-auth-'+identity)
                result['proxy_url'] = session['proxy_url']
                receipts[identity] = result
                if fail_exchange_reply.is_set(): status=503
            elif action=='proxy-references':
                result = {'references': [[identity, sessions[identity]['proxy_url']]
                    for identity in body['operations'] if sessions.get(identity, {}).get('proxy_url')]}
            elif action=='cancel':
                session = sessions.get(body['session_id'],{})
                result = {'phase':'reconcile' if session.get('code_sent') else 'cancelled','cancelled':True}
            elif action=='refresh' and fail_before_start.is_set():
                unstarted_refreshes.append(body['operation_id'])
                status=503
                result={'error':'合成请求在驱动持久化之前失败'}
            elif action=='refresh':
                assert body['operation_id'] not in retired
                counts['refresh']+=1
                if hold_refresh.is_set():
                    active_refreshes.add(body['operation_id'])
                    refresh_started.set()
                    assert release_refresh.wait(65)
                else:
                    time.sleep(.3)
                result = native(tokens[body['document']['token']['access_token']], 'synthetic-refreshed-'+str(counts['refresh']),
                    'synthetic-rotated-'+str(counts['refresh']))
                if verify_identity_only.is_set():
                    result.pop('capabilities')
                if fail_reply.is_set():
                    result['first_failure'] = 'identity_check'
                receipts[body['operation_id']] = result
                active_refreshes.discard(body['operation_id'])
                if fail_reply.is_set(): status=503
            elif action=='prepare':
                assert body['operation_id'] not in retired
                candidate=copy.deepcopy(body['document'])
                email=tokens[candidate['token']['access_token']]
                if candidate['token']['expiry'].startswith('2000-'):
                    counts['proxy_refresh']+=1
                    assert body['proxy_url']=='http://new-proxy.example.test:8080'
                    result=native(email,'synthetic-proxy-at','synthetic-proxy-rt')
                else:
                    result=native(email,candidate['token']['access_token'],candidate['token']['refresh_token'])
                    result['document']=candidate
                result['proxy_url']=body['proxy_url']
                receipts[body['operation_id']]=result
                if fail_reply.is_set(): status=503
            elif action=='recover-status' and body['operation_id'] in active_refreshes:
                native_busy.set()
                result = dict(body, recovery_status='in_flight')
            elif action=='recover-status' and suspend_recovery.is_set():
                result = dict(body, recovery_status='retrying', first_failure='identity_check')
            elif action=='recover-status' and body['operation_id'] in sessions and body['operation_id'] not in receipts:
                result = dict(body, recovery_status='authorizing')
            elif action=='retire' or action in ('recover', 'recover-status') and body['operation_id'] not in receipts:
                identity=body['operation_id']
                result=retired.setdefault(identity,{'retired':True,'account_id':body['account_id'],
                    'generation':body['generation'],'operation_id':identity,'phase':'retired' if identity in sessions or identity in receipts else 'not_started'})
                assert result['account_id']==body['account_id'] and result['generation']==body['generation']
            elif action in ('recover', 'recover-status'):
                assert body['operation_id'] not in retired
                result = {**receipts[body['operation_id']], **body}
            else:
                raise AssertionError('意外的上游请求')
            payload=json.dumps(result).encode()
            self.send_response(status)
            self.send_header('Content-Type','application/json')
            self.send_header('Content-Length',str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

    server = ThreadingHTTPServer(('127.0.0.1',0),Helper)
    threading.Thread(target=server.serve_forever,daemon=True).start()
    opener=build_opener(ProxyHandler({}))
    with tempfile.TemporaryDirectory(prefix='agy-account-api-') as temporary:
        folder=Path(temporary)
        database_path = folder / 'gateway.sqlite'
        with socket.socket() as probe:
            probe.bind(('127.0.0.1',0))
            port=probe.getsockname()[1]
        base=f'http://127.0.0.1:{port}'
        environment={'PATH':os.environ['PATH'],'HOME':str(folder),'DATABASE_DRIVER':'sqlite',
            'DATABASE_DSN':str(folder/'gateway.sqlite'),'SERVER_HOST':'127.0.0.1','SERVER_PORT':str(port),
            'ADMIN_PASSWORD':'synthetic-admin','LOG_LEVEL':'error','USAGE_POLL_INTERVAL_SECS':'86400',
            'V3_RUNTIME_URL':f'http://127.0.0.1:{server.server_port}','V3_INTERNAL_TOKEN':SECRET}
        gate_dir = folder / 'gate'

        def write_gate(blocked: bool):
            """原子发布隔离网关门禁。@param blocked 是否关闭准入。@return 无。"""
            candidate = gate_dir / 'next.json'
            candidate.write_text(json.dumps({'schema_version': 1, 'deployment': 'agy-slow-fixture',
                'phase': 'blocked' if blocked else 'idle', 'epoch': str(uuid.uuid4()),
                'revision': str(uuid.uuid4()), 'operation_id': str(uuid.uuid4()) if blocked else None,
                'target_release': None, 'created_at': '2026-11-25T00:00:00Z'}))
            candidate.chmod(0o600)
            candidate.replace(gate_dir / 'admission.json')

        if slow:
            gate_dir.mkdir()
            write_gate(False)
            environment.update(V3_DEPLOYMENT_ID='agy-slow-fixture', V3_UPDATE_GATE_DIR=str(gate_dir))
        log=(folder/'gateway.log').open('wb')
        process=subprocess.Popen([str(ROOT/'services/gateway/target/debug/claude-code-gateway')],cwd=folder,
            env=environment,stdout=log,stderr=log)

        def request(method,path,body=None,expected=200):
            """调用真实管理HTTP。@param method 方法。@param path 路径。@param body 合成请求。@param expected 预期状态。@return JSON。"""
            req=Request(base+path,data=json.dumps(body).encode() if body is not None else None,method=method,
                headers={'Authorization':'Bearer synthetic-admin','Content-Type':'application/json'})
            try:
                response=opener.open(req,timeout=60 if slow else 15)
            except HTTPError as error:
                response=error
            with response:
                result = json.load(response)
                assert response.status==expected,(path,response.status,expected,result.get('error'))
                return result

        try:
            for _ in range(600):
                if process.poll() is not None: raise RuntimeError('隔离网关启动失败，请核对本地构建')
                try:
                    request('GET','/admin/accounts')
                    break
                except OSError:
                    time.sleep(.1)
            else: raise RuntimeError('隔离网关启动超时')
            cc=request('POST','/admin/accounts',{'email':'same@example.test','setup_token':'synthetic-cc'},201)
            native('same@example.test','synthetic-at1')
            agy=request('POST','/admin/accounts',{'platform':'antigravity','email':'same@example.test','auth_type':'oauth',
                'access_token':'synthetic-at1','refresh_token':'synthetic-rt1','expires_at':4070908800000},201)
            account=agy['id']
            assert cc['platform']=='claude_code' and not agy['agy_system_prompt_homoglyph_enabled']
            created=request('GET',f'/admin/accounts/{account}')
            assert created['usage_data']['capabilities']==agy['usage_data']['capabilities']
            assert created['usage_data']['capabilities']['source']=='synthetic-native'
            assert created['usage_data']['capabilities']['observed_at_ms']>0 and created['usage_fetched_at']
            assert request('GET','/admin/accounts')['total']==1
            assert request('GET','/admin/accounts?platform=all')['total']==2
            assert request('GET','/admin/accounts?platform=antigravity&page=2&page_size=1')['data']==[]
            reminder = 'agy_system_prompt_as_user_reminder'
            assert created[reminder] is False and cc[reminder] is False
            request('POST', '/admin/accounts', {
                'email': 'fixture-cc@example.test', 'setup_token': 'synthetic-cc', reminder: True,
            }, 400)
            request('PUT', f"/admin/accounts/{cc['id']}", {reminder: True}, 400)
            request('PUT', f'/admin/accounts/{account}', {reminder: 'true'}, 400)
            assert request('PUT', f'/admin/accounts/{account}', {reminder: True})[reminder] is True
            native('experiment@example.test', 'synthetic-experiment-at')
            experiment = request('POST', '/admin/accounts', {
                'platform': 'antigravity', 'email': 'experiment@example.test', 'auth_type': 'oauth',
                'access_token': 'synthetic-experiment-at', 'refresh_token': 'synthetic-rt1',
                'expires_at': 4070908800000, reminder: True,
            }, 201)
            assert experiment[reminder] is True
            request('PUT', f"/admin/accounts/{experiment['id']}", {reminder: False})
            listed = request('GET', '/admin/accounts?platform=antigravity')['data']
            assert {row['id']: row[reminder] for row in listed} == {account: True, experiment['id']: False}
            request('PUT',f'/admin/accounts/{account}',{'platform':'claude_code'},400)
            request('PUT',f'/admin/accounts/{account}',{'proxy_url':'invalid-proxy'},400)
            request('POST','/admin/oauth/generate-auth-url',{'platform':'antigravity','proxy_url':'invalid-proxy'},400)
            request('POST','/admin/accounts',{'platform':'unknown','email':'unknown@example.test'},400)
            request('POST','/admin/oauth/generate-setup-token-url',{'platform':'antigravity'},400)
            runtime = request('GET', f'/admin/runtime/accounts/{account}/config')
            assert runtime['account_id'] == account and runtime['platform'] == 'antigravity'
            assert 'access_token' not in runtime and 'refresh_token' not in runtime
            request('PUT',f'/admin/accounts/{account}',{'agy_system_prompt_homoglyph_enabled':True})
            assert request('GET',f'/admin/accounts/{account}')['agy_system_prompt_homoglyph_enabled']
            path=f'/admin/accounts/{account}/oauth-credentials/resolve'
            state_path = f'/admin/accounts/{account}/agy-credentials'
            with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
                results=list(executor.map(lambda _:request('POST',path,{'force_refresh':True}),range(2)))
            assert counts['refresh']==1,counts
            assert results[0]['refresh_token']==results[1]['refresh_token']=='synthetic-rotated-1'
            fail_reply.set()
            suspend_recovery.set()
            request('POST',path,{'force_refresh':True},503)
            assert request('GET',f'/admin/accounts/{account}/agy-credentials')['phase']=='reconcile'
            request('POST',path,{},503)
            assert counts['refresh']==2
            # 模拟上一个网关在远端起链前中断。另一账号与当前刷新独立收口。
            abandoned = uuid.uuid4().hex
            process.terminate()
            process.wait(timeout=10)
            with sqlite3.connect(database_path) as database:
                database.execute("UPDATE account_credential_states SET phase='reauth',recovery_status='starting',operation_id=?,updated_at_ms=0 WHERE account_id=?",
                    (abandoned, experiment['id']))
            suspend_recovery.clear()
            process=subprocess.Popen([str(ROOT/'services/gateway/target/debug/claude-code-gateway')],cwd=folder,
                env=environment,stdout=log,stderr=log)
            for _ in range(600):
                try:
                    request('GET','/admin/accounts')
                    break
                except OSError: time.sleep(.1)
            else: raise RuntimeError('隔离网关恢复启动超时')
            for _ in range(100):
                refreshed_state = request('GET', state_path)
                if refreshed_state['phase'] == 'ready':
                    break
                time.sleep(.1)
            else:
                raise AssertionError('空闲账号重启后未自动对账')
            assert refreshed_state['first_failure'] == 'identity_check' and counts['refresh']==2
            for _ in range(100):
                if request('GET', f"/admin/accounts/{experiment['id']}/agy-credentials")['phase'] == 'ready':
                    break
                time.sleep(.1)
            else:
                raise AssertionError('启动前的孤立重授权预占未收口')
            assert retired[abandoned]['account_id'] == experiment['id']
            assert request('GET',f'/admin/accounts/{account}')['usage_data']['capabilities']['source']=='synthetic-native'
            assert request('GET',f'/admin/accounts/{account}')['refresh_token']=='synthetic-rotated-2'
            generate = '/admin/oauth/generate-auth-url'
            reauthorize = {'platform':'antigravity','account_id':account}
            fail_authorization_start.set()
            request('POST',generate,reauthorize,503)
            assert request('GET',state_path)['phase']=='ready'
            fail_authorization_start.clear()
            hold_authorization.set()
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                launching = executor.submit(request, 'POST', generate, reauthorize)
                assert authorization_reserved.wait(5)
                try:
                    assert request('GET',state_path)['phase']=='reauth'
                    request('POST',path,{'force_refresh':True},503)
                    assert counts['refresh']==2
                finally:
                    release_authorization.set()
                generated = launching.result(timeout=10)
            hold_authorization.clear()
            exchanged=request('POST','/admin/oauth/exchange-code',{'session_id':generated['session_id'],'code':'synthetic-code'})
            current=request('GET',f'/admin/accounts/{account}')
            assert current['agy_system_prompt_homoglyph_enabled'] and current['id']==account
            assert current[reminder] is True
            assert current['usage_data']['capabilities']==exchanged['capabilities']
            assert current['usage_data']['capabilities']!=created['usage_data']['capabilities'] and current['usage_fetched_at']
            wrong=request('POST','/admin/oauth/generate-auth-url',{'platform':'antigravity','account_id':account})
            request('POST','/admin/oauth/exchange-code',{'session_id':wrong['session_id'],'code':'synthetic-wrong-account'},400)
            assert request('GET',f'/admin/accounts/{account}')['access_token']==current['access_token']
            request('POST','/admin/oauth/'+wrong['session_id']+'/cancel?platform=antigravity',{})
            replacement=request('POST','/admin/oauth/generate-auth-url',{'platform':'antigravity','account_id':account})
            request('POST','/admin/oauth/exchange-code',{'session_id':replacement['session_id'],'code':'synthetic-code'})
            request('POST','/admin/oauth/exchange-code',{'session_id':wrong['session_id'],'code':'synthetic-wrong-account'},400)
            native('same@example.test','synthetic-manual-at','synthetic-manual-rt')
            suspend_recovery.set()
            request('PUT',f'/admin/accounts/{account}',{'access_token':'synthetic-manual-at','refresh_token':'synthetic-manual-rt','expires_at':4070908800000},503)
            assert request('GET',f'/admin/accounts/{account}/agy-credentials')['phase']=='reconcile'
            request('POST',f'/admin/accounts/{account}/agy-credentials/recover',{})
            suspend_recovery.clear()
            assert request('GET',f'/admin/accounts/{account}')['refresh_token']=='synthetic-manual-rt'
            with sqlite3.connect(folder/'gateway.sqlite') as database:
                state=database.execute('SELECT generation,phase FROM account_credential_states WHERE account_id=?',(account,)).fetchone()
                assert state==(6,'ready'),state
            fail_reply.clear()
            fail_before_start.set()
            request('POST',path,{'force_refresh':True},503)
            request('POST',f'/admin/accounts/{account}/agy-credentials/recover',{})
            assert retired[unstarted_refreshes[-1]]['phase']=='not_started'
            assert request('GET',f'/admin/accounts/{account}/agy-credentials')['phase']=='ready'
            request('POST',path,{'force_refresh':True},503)
            replacement=request('POST','/admin/oauth/generate-auth-url',{'platform':'antigravity','account_id':account})
            assert retired[unstarted_refreshes[-1]]['phase']=='not_started'
            request('POST','/admin/oauth/exchange-code',{'session_id':replacement['session_id'],'code':'synthetic-code'})
            fail_before_start.clear()
            with sqlite3.connect(folder/'gateway.sqlite') as database:
                database.execute("UPDATE accounts SET oauth_expires_at='2000-01-01T00:00:00Z' WHERE id=?",(account,))
            previous=request('GET',f'/admin/accounts/{account}')
            fail_reply.set()
            suspend_recovery.set()
            request('PUT',f'/admin/accounts/{account}',{'proxy_url':'http://new-proxy.example.test:8080'},503)
            pending=request('GET',f'/admin/accounts/{account}')
            assert pending['proxy_url']==previous['proxy_url'] and pending['refresh_token']==previous['refresh_token']
            request('POST',f'/admin/accounts/{account}/agy-credentials/recover',{})
            suspend_recovery.clear()
            saved=request('GET',f'/admin/accounts/{account}')
            assert counts['proxy_refresh']==1
            assert saved['proxy_url']=='http://new-proxy.example.test:8080' and saved['refresh_token']=='synthetic-proxy-rt'
            assert saved['usage_data']['capabilities']==receipts[next(reversed(receipts))]['capabilities'] and saved['usage_fetched_at']
            assert request('GET',f'/admin/accounts/{account}/agy-credentials')['phase']=='ready'
            # 只核验身份的续期与丢失回执恢复都保留已有额度、能力和采集时刻。
            with sqlite3.connect(folder/'gateway.sqlite') as database:
                database.execute("UPDATE accounts SET usage_fetched_at='2001-01-01T00:00:00Z' WHERE id=?", (account,))
            prior_usage = request('GET', f'/admin/accounts/{account}')
            generation = request('GET', state_path)['generation']
            fail_reply.clear()
            verify_identity_only.set()
            request('POST', path, {'force_refresh': True})
            assert request('GET', state_path)['generation'] == generation + 1
            fail_reply.set()
            request('POST', path, {'force_refresh': True}, 503)
            for _ in range(100):
                if request('GET', state_path)['phase'] == 'ready':
                    break
                time.sleep(.1)
            else:
                raise AssertionError('空闲账号未自动恢复原操作')
            state = request('GET', state_path)
            assert (state['phase'], state['generation']) == ('ready', generation + 2)
            recovered = request('GET', f'/admin/accounts/{account}')
            assert counts['refresh'] == 4 and recovered['refresh_token'] == 'synthetic-rotated-4'
            assert recovered['usage_data'] == prior_usage['usage_data']
            assert recovered['usage_fetched_at'] == prior_usage['usage_fetched_at']
            # 候选线路在原生回包丢失及网关重启后仍能通过原凭据操作提交。
            proxy_input = {'name':'合成线路','protocol':'http','host':'reauth-proxy.example.test','port':8080}
            proxy_id = request('POST','/admin/proxies',proxy_input)['id']
            proxy = next(row for row in request('GET','/admin/proxies?usage=false')['data'] if row['id']==proxy_id)
            target = {'platform':'antigravity','account_id':account,'replace_proxy':True,'proxy_id':proxy_id,
                'proxy_revision':proxy['revision']}
            exchange = '/admin/oauth/exchange-code'
            request('POST', generate, {**target,'proxy_revision':'stale'}, 400)
            chosen = request('POST', generate, target)['session_id']
            assert sessions[chosen]['proxy_url']=='http://reauth-proxy.example.test:8080'
            assert sessions[chosen]['replace_proxy'] is True
            assert request('GET',f'/admin/accounts/{account}')['proxy_url']==recovered['proxy_url']
            fail_exchange_reply.set()
            request('POST', exchange, {'session_id':chosen,'code':'synthetic-code'}, 503)
            process.terminate()
            process.wait(timeout=10)
            process=subprocess.Popen([str(ROOT/'services/gateway/target/debug/claude-code-gateway')],cwd=folder,
                env=environment,stdout=log,stderr=log)
            for _ in range(600):
                try:
                    request('GET','/admin/accounts')
                    break
                except OSError: time.sleep(.1)
            else: raise RuntimeError('隔离网关恢复启动超时')
            protected = next(row for row in request('GET','/admin/proxies')['data'] if row['id']==proxy_id)
            assert any(item['kind']=='authorization' and item['id']==chosen for item in protected['users']), protected
            request('DELETE',f'/admin/proxies/{proxy_id}',{'revision':proxy['revision']},400)
            request('PUT',f'/admin/proxies/{proxy_id}',{**proxy_input,'revision':proxy['revision'],'port':8081},400)
            request('POST',state_path+'/recover',{})
            changed = request('GET',f'/admin/accounts/{account}')
            assert changed['id']==account and changed['proxy_url']==sessions[chosen]['proxy_url']
            assert changed['access_token']=='synthetic-auth-'+chosen
            fail_exchange_reply.clear()
            original = request('POST', generate, {'platform':'antigravity','account_id':account})['session_id']
            assert sessions[original]['proxy_url']==changed['proxy_url']
            request('POST','/admin/oauth/'+original+'/cancel?platform=antigravity',{})
            direct = request('POST', generate, {'platform':'antigravity','account_id':account,
                'replace_proxy':True,'proxy_url':''})['session_id']
            exchange_result = request('POST', exchange, {'session_id':direct,'code':'synthetic-code'})
            assert 'proxy_url' not in exchange_result
            assert request('GET',f'/admin/accounts/{account}')['proxy_url']==''
            request('DELETE',f'/admin/proxies/{proxy_id}',{'revision':proxy['revision']})

            slow_results = {}
            if slow:
                fail_reply.clear()

                def wait_for_change(predicate):
                    deadline = time.monotonic() + 5
                    while not predicate():
                        assert time.monotonic() < deadline, '等待中的授权活动未按预期变化'
                        time.sleep(.05)

                status_path = '/admin/runtime/system-update/status'
                for scenario in ('12_seconds', 'past_lease', 'maintenance', 'disconnect'):
                    before = request('GET', state_path)
                    previous_starts, previous_refreshes = len(sessions), counts['refresh']
                    hold_refresh.set()
                    refresh_started.clear()
                    release_refresh.clear()
                    native_busy.clear()
                    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
                        original_refresh = executor.submit(request, 'POST', path, {'force_refresh': True})
                        try:
                            assert refresh_started.wait(5)
                            started_at = time.monotonic()
                            prior_active = request('GET', status_path)['active']
                            if scenario == 'disconnect':
                                payload = json.dumps(reauthorize).encode()
                                with socket.create_connection(('127.0.0.1', port), timeout=5) as conn:
                                    conn.sendall((f'POST {generate} HTTP/1.1\r\nHost: 127.0.0.1\r\n'
                                        'Authorization: Bearer synthetic-admin\r\nContent-Type: application/json\r\n'
                                        f'Content-Length: {len(payload)}\r\n\r\n').encode() + payload)
                                    wait_for_change(lambda: request('GET', status_path)['active'] > prior_active)
                                wait_for_change(lambda: request('GET', status_path)['active'] <= prior_active)
                            else:
                                authorization = executor.submit(request, 'POST', generate, reauthorize,
                                    503 if scenario == 'maintenance' else 200)
                                wait_for_change(lambda: request('GET', status_path)['active'] > prior_active)
                                if scenario == 'maintenance':
                                    write_gate(True)
                                    denied = authorization.result(timeout=5)
                                    assert '维护' in json.dumps(denied, ensure_ascii=False)
                                elif scenario == '12_seconds':
                                    time.sleep(max(0, started_at + 11 - time.monotonic()))
                                    assert not authorization.done(), '授权越过原 10 秒预算时提前结束'
                                    time.sleep(max(0, started_at + 12 - time.monotonic()))
                                else:
                                    assert native_busy.wait(40), '跨缓存租期后未观察到实际写者持锁'
                                    assert time.monotonic() - started_at >= 29
                                    time.sleep(max(0, started_at + 33 - time.monotonic()))
                                    assert not authorization.done(), '实际原生刷新仍在途时授权提前结束'
                            assert not original_refresh.done()
                            assert request('GET', state_path)['operation_id'] in active_refreshes
                            assert len(sessions) == previous_starts
                        finally:
                            release_refresh.set()
                            hold_refresh.clear()
                        try:
                            original_refresh.result(timeout=8)
                        finally:
                            if scenario == 'maintenance':
                                write_gate(False)
                        if scenario in ('12_seconds', 'past_lease'):
                            session = authorization.result(timeout=8)['session_id']
                            assert sessions[session]['generation'] == before['generation'] + 1
                            assert len(sessions) == previous_starts + 1
                            request('POST', f'/admin/oauth/{session}/cancel?platform=antigravity', {})
                        else:
                            assert len(sessions) == previous_starts
                        assert request('GET', state_path)['phase'] == 'ready'
                        assert counts['refresh'] == previous_refreshes + 1
                        slow_results[scenario] = True
            print(json.dumps({'passed':True,'evidence':'gateway_http_sqlite_synthetic_native',
                'capabilities_persisted':True,'missing_operation_recovered':True,'missing_operation_reauthorized':True,
                'stale_reservation_released':True,'first_failure_retained':True,'reserved_before_link':True,
                'reauth_proxy_after_restart':True,'proxy_revision_rejected':True,'reauth_direct':True,
                'expired_proxy_refresh_recovered':True, 'identity_only_refresh_kept_usage':True,
                'concurrent_refresh_calls':1,'lost_reply_recovered':True,'restart_recovered':True,'wrong_identity_rejected':True,'manual_import_recovered':True,'reauth_original_account':True,'model_submissions':0,
                **({'slow_refresh':slow_results} if slow else {})}))
        finally:
            process.terminate()
            process.wait(timeout=10)
            log.close()
            evidence = ROOT / '.trellis/.runtime/agy-account-api-startup.log'
            evidence.parent.mkdir(parents=True, exist_ok=True)
            evidence.write_bytes((folder/'gateway.log').read_bytes())
            server.shutdown()
            server.server_close()


if __name__=='__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--slow-refresh', action='store_true', help='追加 12 秒、跨缓存租期、维护与断连测试')
    main(parser.parse_args().slow_refresh)
