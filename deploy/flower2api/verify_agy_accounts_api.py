"""隔离运行真实网关HTTP与SQLite，原生管理桥使用合成服务，模型提交为零。"""
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


def main():
    """验证平台管理、唯一刷新、持久对账与原账号回填。@return 无。"""
    sessions, tokens, receipts, retired = {}, {}, {}, {}
    counts = {'refresh':0,'proxy_refresh':0,'observation':0}
    fail_reply = threading.Event()
    fail_before_start = threading.Event()

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
                identity = uuid.uuid4().hex
                sessions[identity] = body
                result = {'session_id':identity,'auth_url':'https://accounts.google.com/synthetic'}
            elif action=='exchange':
                target = sessions[body['session_id']]['account_id']
                sessions[body['session_id']]['code_sent'] = True
                email = 'wrong@example.test' if body['code']=='synthetic-wrong-account' else 'same@example.test' if target else 'new@example.test'
                result = native(email,'synthetic-auth-'+body['session_id'])
            elif action=='cancel':
                session = sessions.get(body['session_id'],{})
                result = {'phase':'reconcile' if session.get('code_sent') else 'cancelled','cancelled':True}
            elif action=='refresh' and fail_before_start.is_set():
                status=503
                result={'error':'合成请求在驱动持久化之前失败'}
            elif action=='refresh':
                assert body['operation_id'] not in retired
                counts['refresh']+=1
                time.sleep(.3)
                result = native(tokens[body['document']['token']['access_token']], 'synthetic-refreshed-'+str(counts['refresh']),
                    'synthetic-rotated-'+str(counts['refresh']))
                receipts[body['operation_id']] = result
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
            elif action=='retire' or action=='recover' and body['operation_id'] not in receipts:
                identity=body['operation_id']
                result=retired.setdefault(identity,{'retired':True,'account_id':body['account_id'],
                    'generation':body['generation'],'operation_id':identity,'phase':'retired' if identity in sessions or identity in receipts else 'not_started'})
                assert result['account_id']==body['account_id'] and result['generation']==body['generation']
            elif action=='recover':
                assert body['operation_id'] not in retired
                result = receipts[body['operation_id']]
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
        with socket.socket() as probe:
            probe.bind(('127.0.0.1',0))
            port=probe.getsockname()[1]
        base=f'http://127.0.0.1:{port}'
        environment={'PATH':os.environ['PATH'],'HOME':str(folder),'DATABASE_DRIVER':'sqlite',
            'DATABASE_DSN':str(folder/'gateway.sqlite'),'SERVER_HOST':'127.0.0.1','SERVER_PORT':str(port),
            'ADMIN_PASSWORD':'synthetic-admin','LOG_LEVEL':'error','USAGE_POLL_INTERVAL_SECS':'86400',
            'V3_RUNTIME_URL':f'http://127.0.0.1:{server.server_port}','V3_INTERNAL_TOKEN':SECRET}
        log=(folder/'gateway.log').open('wb')
        process=subprocess.Popen([str(ROOT/'services/gateway/target/debug/claude-code-gateway')],cwd=folder,
            env=environment,stdout=log,stderr=log)

        def request(method,path,body=None,expected=200):
            """调用真实管理HTTP。@param method 方法。@param path 路径。@param body 合成请求。@param expected 预期状态。@return JSON。"""
            req=Request(base+path,data=json.dumps(body).encode() if body is not None else None,method=method,
                headers={'Authorization':'Bearer synthetic-admin','Content-Type':'application/json'})
            try:
                response=opener.open(req,timeout=15)
            except HTTPError as error:
                response=error
            with response:
                assert response.status==expected,(path,response.status,expected)
                return json.load(response)

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
            with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
                results=list(executor.map(lambda _:request('POST',path,{'force_refresh':True}),range(2)))
            assert counts['refresh']==1,counts
            assert results[0]['refresh_token']==results[1]['refresh_token']=='synthetic-rotated-1'
            fail_reply.set()
            request('POST',path,{'force_refresh':True},503)
            assert request('GET',f'/admin/accounts/{account}/agy-credentials')['phase']=='reconcile'
            request('POST',path,{},503)
            assert counts['refresh']==2
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
            request('POST',path,{},503)
            assert counts['refresh']==2
            assert request('GET',f'/admin/accounts/{account}')['usage_data']['capabilities']['source']=='synthetic-native'
            request('POST',f'/admin/accounts/{account}/agy-credentials/recover',{})
            assert request('GET',f'/admin/accounts/{account}')['refresh_token']=='synthetic-rotated-2'
            generated=request('POST','/admin/oauth/generate-auth-url',{'platform':'antigravity','account_id':account})
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
            request('PUT',f'/admin/accounts/{account}',{'access_token':'synthetic-manual-at','refresh_token':'synthetic-manual-rt','expires_at':4070908800000},503)
            assert request('GET',f'/admin/accounts/{account}/agy-credentials')['phase']=='reconcile'
            request('POST',f'/admin/accounts/{account}/agy-credentials/recover',{})
            assert request('GET',f'/admin/accounts/{account}')['refresh_token']=='synthetic-manual-rt'
            with sqlite3.connect(folder/'gateway.sqlite') as database:
                state=database.execute('SELECT generation,phase FROM account_credential_states WHERE account_id=?',(account,)).fetchone()
                assert state==(6,'ready'),state
            fail_reply.clear()
            fail_before_start.set()
            request('POST',path,{'force_refresh':True},503)
            missing=request('GET',f'/admin/accounts/{account}/agy-credentials')
            request('POST',f'/admin/accounts/{account}/agy-credentials/recover',{})
            assert retired[missing['operation_id']]['phase']=='not_started'
            assert request('GET',f'/admin/accounts/{account}/agy-credentials')['phase']=='ready'
            request('POST',path,{'force_refresh':True},503)
            missing_reauth=request('GET',f'/admin/accounts/{account}/agy-credentials')
            replacement=request('POST','/admin/oauth/generate-auth-url',{'platform':'antigravity','account_id':account})
            assert retired[missing_reauth['operation_id']]['phase']=='not_started'
            request('POST','/admin/oauth/exchange-code',{'session_id':replacement['session_id'],'code':'synthetic-code'})
            fail_before_start.clear()
            with sqlite3.connect(folder/'gateway.sqlite') as database:
                database.execute("UPDATE accounts SET oauth_expires_at='2000-01-01T00:00:00Z' WHERE id=?",(account,))
            previous=request('GET',f'/admin/accounts/{account}')
            fail_reply.set()
            request('PUT',f'/admin/accounts/{account}',{'proxy_url':'http://new-proxy.example.test:8080'},503)
            pending=request('GET',f'/admin/accounts/{account}')
            assert pending['proxy_url']==previous['proxy_url'] and pending['refresh_token']==previous['refresh_token']
            request('POST',f'/admin/accounts/{account}/agy-credentials/recover',{})
            saved=request('GET',f'/admin/accounts/{account}')
            assert counts['proxy_refresh']==1
            assert saved['proxy_url']=='http://new-proxy.example.test:8080' and saved['refresh_token']=='synthetic-proxy-rt'
            assert saved['usage_data']['capabilities']==receipts[next(reversed(receipts))]['capabilities'] and saved['usage_fetched_at']
            assert request('GET',f'/admin/accounts/{account}/agy-credentials')['phase']=='ready'
            print(json.dumps({'passed':True,'evidence':'gateway_http_sqlite_synthetic_native',
                'capabilities_persisted':True,'missing_operation_recovered':True,'missing_operation_reauthorized':True,
                'expired_proxy_refresh_recovered':True,
                'concurrent_refresh_calls':1,'lost_reply_recovered':True,'restart_recovered':True,'wrong_identity_rejected':True,'manual_import_recovered':True,'reauth_original_account':True,'model_submissions':0}))
        finally:
            process.terminate()
            process.wait(timeout=10)
            log.close()
            (ROOT/'.trellis/.runtime/agy-account-api-startup.log').write_bytes((folder/'gateway.log').read_bytes())
            server.shutdown()
            server.server_close()


if __name__=='__main__':
    main()
