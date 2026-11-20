"""在断网容器使用真实网关HTTP和SQLite验证Gemini接入，原生发送边界使用合成替身。"""
import argparse
import base64
import copy
import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

ENVIRONMENT='a'*32
SECRET='synthetic-internal-proof-at-least-32-bytes'


def require(condition, message):
    """保持优化模式下的测试断言。@param condition 实际条件。@param message 固定失败说明。@return 无。"""
    if not condition:raise ValueError(message)


class Fixture(BaseHTTPRequestHandler):
    """提供内部环境绑定和可阻塞的原生工具轮事件。"""
    calls=[]
    waiting=threading.Event()
    tool_finished=threading.Event()
    tool_drained=threading.Event()
    tool_completions=[]
    refreshes=0
    cancelled=threading.Event()
    policy_failed=False

    def log_message(self,*args):
        """避免把查询密钥和私有正文打印到测试日志。@param args HTTP日志参数。@return 无。"""

    def do_GET(self):
        """返回唯一合成账号的受信运行绑定。@return 无。"""
        require(self.path in ['/internal/v3/transport/1','/internal/v3/transport/2'],'请求偏离合成运行时')
        account=int(self.path.rsplit('/',1)[1]);environment=ENVIRONMENT if account==1 else 'b'*32
        host='flower2api-'+hashlib.sha256(b'synthetic').hexdigest()[:12]+'-'+environment
        value={'account_id':account,'environment_id':environment,'generation':1,'endpoint':f'http://{host}:8091',
            'secret':SECRET,'release_id':'synthetic-release'}
        self.send_response(200);self.send_header('content-type','application/json');self.end_headers()
        self.wfile.write(json.dumps(value).encode())

    def do_POST(self):
        """按真实私有信封输出源帧、HTTP终态和物理收口。@return 无。"""
        if self.path=='/internal/v3/agy-auth/refresh':
            require(self.headers.get('Authorization')=='Bearer '+SECRET,'管理证明错误')
            value=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            document=value['document'];document['token']['access_token']='synthetic-refreshed-'+str(value['generation'])
            document['token']['expiry']='2099-01-01T00:00:00Z'
            Fixture.refreshes+=1
            self.send_response(200);self.send_header('content-type','application/json');self.end_headers()
            self.wfile.write(json.dumps({'email_address':'synthetic@example.test','document':document}).encode());return
        if self.path=='/internal/agy/tools':
            require(self.headers.get('Authorization')=='Bearer '+SECRET,'内部证明错误')
            value=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            require('credential_snapshot' not in value,'工具收口意外发布凭据')
            require(any(item['request']['request_id']==value['previous_request_id'] and item['api_token_id']==value['api_token_id'] for item in Fixture.calls),'工具控制归属错误')
            Fixture.tool_completions.append(value['previous_request_id'])
            Fixture.tool_finished.set();require(Fixture.tool_drained.wait(5),'原工具物理收口失败')
            self.send_response(200);self.send_header('content-type','application/json');self.end_headers()
            self.wfile.write(json.dumps({'finished':True,'request_id':value['request']['request_id'],'previous_request_id':value['previous_request_id']}).encode())
            return
        require(self.path=='/internal/agy/generate','请求偏离合成发送器')
        require(self.headers.get('Authorization')=='Bearer '+SECRET,'内部证明错误')
        value=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        require('refresh_token' not in value['credential_snapshot'],'业务副本包含RT')
        account=value['request']['account_id'];environment=ENVIRONMENT if account==1 else 'b'*32
        require(account in [1,2] and value['request']['environment_id']==environment,'私有归属错误')
        Fixture.calls.append(copy.deepcopy(value))
        request=value['request']['request_id']
        def emit(kind,**fields):
            event={'protocol':'agy-account-supervisor','schema_version':1,'type':kind,'request_id':request,
                'account_id':account,'environment_id':environment,'environment_generation':1,**fields}
            self.wfile.write((json.dumps(event)+'\n').encode());self.wfile.flush()
        def native(kind,**fields):
            emit('native_event',credential_generation=value['credential_snapshot']['credential_generation'],
                event={'type':kind,'request_id':request,'generation':'synthetic-worker',**fields})
        body=value['body'];contents=body['contents']
        results=any('functionResponse' in part for part in contents[-1]['parts'])
        tools=body.get('tools') and not results
        self.send_response(200);self.send_header('content-type','application/x-ndjson');self.end_headers()
        mode=contents[0]['parts'][0].get('text','')
        policy=value.get('system_prompt_policy',{'schema_version':1,'enabled':False,'rule_version':'new-api-homoglyph-v1'})
        report={**policy,'source':'cortex_custom_system','rule_sha256':'c'*64,'changed':False,
            'replaced_codepoints':0,'system_codepoints':len('\n'.join(part.get('text','') for part in body.get('systemInstruction',{}).get('parts',[])))}
        if mode=='policy-wrong-receipt':report['rule_version']='unknown'
        native('request_accepted',parameter_policy=[{'field':'generationConfig.temperature','policy':'native_default'}],
            **({} if mode=='policy-no-receipt' else {'system_prompt_policy':report}))
        if mode in ['policy-no-receipt','policy-wrong-receipt']:
            emit('job_finalized',status='error');return
        control_cases = {'control-400': 400, 'control-502': 502, 'control-200': 200,
            'control-legacy': None, 'control-after-frame': 400}
        if results and mode.startswith('replay-control-'):
            mode = mode.removeprefix('replay-')
        if mode in control_cases:
            after_frame = mode == 'control-after-frame'
            if after_frame:
                frame = {'candidates': [{'content': {'role': 'model', 'parts': [{'text': '合成首帧'}]}}]}
                native('gemini_response', data={'data_base64': base64.b64encode(json.dumps(frame).encode()).decode()})
            status = control_cases[mode]
            http_status = {} if status is None else {'control_http_status': status}
            native('error', code='native_request_failed', native_model_calls=int(after_frame), **http_status)
            emit('job_finalized', status='error')
            return
        policy_auth=mode=='policy-auth-recover' and not Fixture.policy_failed
        if policy_auth:
            Fixture.policy_failed=True
            with sqlite3.connect('/state/gateway.sqlite') as database:
                database.execute('UPDATE accounts SET agy_system_prompt_homoglyph_enabled=0 WHERE id=1')
        if mode=='cancel-stream':
            frame={'candidates':[{'content':{'role':'model','parts':[{'text':'合成首帧'}]}}]}
            native('gemini_response',data={'data_base64':base64.b64encode(json.dumps(frame).encode()).decode()})
            try:
                for _ in range(200):
                    native('stream_event',data={'event':'synthetic_keepalive'})
                    time.sleep(.05)
            except OSError:
                Fixture.cancelled.set()
            return
        auth_error=policy_auth or mode=='auth-always' or mode=='auth-recover' and value['credential_snapshot']['credential_generation']==2 or mode=='auth-after-frame'
        if auth_error or mode=='capacity-error':
            if mode=='auth-after-frame':
                frame={'candidates':[{'content':{'role':'model','parts':[{'text':'已经交付的合成片段'}]}}]}
                native('gemini_response',data={'data_base64':base64.b64encode(json.dumps(frame).encode()).decode()})
            frame={'error':{'code':401 if auth_error else 429,'status':'UNAUTHENTICATED' if auth_error else 'RESOURCE_EXHAUSTED'}}
            native('gemini_response',data={'data_base64':base64.b64encode(json.dumps(frame).encode()).decode()})
            native('error',code='native_stream_incomplete',native_model_calls=1)
            emit('job_finalized',status='error');return
        part={'functionCall':{'id':'synthetic-call','name':'synthetic_tool','args':{'x':1}},'thoughtSignature':'synthetic-signature'} if tools else {'text':'合成回复'}
        frame={'candidates':[{'content':{'role':'model','parts':[part]},'finishReason':'STOP'}],'usageMetadata':{'totalTokenCount':7}}
        native('gemini_response',data={'data_base64':base64.b64encode(json.dumps(frame).encode()).decode()})
        native('completed',native_tool_pending=bool(tools),native_model_calls=1)
        if tools:
            Fixture.waiting.set()
            require(Fixture.tool_finished.wait(45),'原工具轮未完成')
        elif results:
            require(value['credential_snapshot']['credential_generation']==2,'续轮没有采用新代AT')
            Fixture.tool_finished.set()
        emit('job_finalized',status='completed')
        if tools:Fixture.tool_drained.set()


def inside() -> dict:
    """在隔离容器执行真实HTTP、数据库及工具许可场景。@return 测试摘要。"""
    for port in (8765,8091):
        server=ThreadingHTTPServer(('127.0.0.1',port),Fixture)
        threading.Thread(target=server.serve_forever,daemon=True).start()
    output=open('/state/gateway.log','wb')
    child=subprocess.Popen(['/opt/gateway'],stdout=output,stderr=subprocess.STDOUT)
    def request(path,body=None,key='synthetic-key',admin=False):
        headers={'x-api-key':'synthetic-admin' if admin else key}
        if body is not None:headers['content-type']='application/json'
        value=Request('http://127.0.0.1:5674'+path,data=json.dumps(body).encode() if body is not None else None,headers=headers)
        try:
            with urlopen(value,timeout=8) as response:return response.status,response.read()
        except HTTPError as error:return error.code,error.read()
    try:
        until=time.monotonic()+30
        while time.monotonic()<until:
            if child.poll() is not None:raise ValueError('合成网关启动失败')
            try:
                request('/api/hello')
                break
            except OSError:time.sleep(.1)
        database=sqlite3.connect('/state/gateway.sqlite')
        with database:
            database.execute("INSERT INTO accounts(id,name,email,platform,token,device_id,auth_type,access_token,refresh_token,oauth_expires_at,concurrency,auto_telemetry,auto_poll_usage,usage_data) VALUES(1,'synthetic','synthetic@example.test','antigravity','','','oauth','synthetic-at-1','synthetic-rt','2099-01-01T00:00:00Z',1,0,0,?)",
                (json.dumps({'capabilities':{'model_mappings':{
                    'gemini-synthetic':'MODEL_PLACEHOLDER_M36','gemini-synthetic-low':'MODEL_PLACEHOLDER_M37',
                    'claude-synthetic':'MODEL_PLACEHOLDER_M320','claude-synthetic-high':'MODEL_SYNTHETIC_CLAUDE_HIGH',
                    'gemini-4-neon-low':'MODEL_SYNTHETIC_NEON_LOW','gemini-4-neon-high':'MODEL_SYNTHETIC_NEON_HIGH',
                    'gemini-4-hydrogen-medium':'MODEL_SYNTHETIC_HYDROGEN_MEDIUM',
                }}}),))
            database.execute("INSERT INTO account_credential_states(account_id,generation,phase,updated_at_ms) VALUES(1,1,'ready',1)")
            database.executemany("INSERT INTO api_tokens(name,token,allowed_accounts,status) VALUES('synthetic',?,'1','active')",[('synthetic-key',),('synthetic-other',)])
        base='/v1beta/models/gemini-synthetic:'
        body={'contents':[{'role':'user','parts':[{'text':'合成问题'}]}],'generationConfig':{'temperature':.2,'topP':.8,'maxOutputTokens':128}}
        status,raw=request('/v1beta/models')
        names=[item['name'] for item in json.loads(raw)['models']]
        require(status==200 and names==[
            'models/claude-synthetic','models/claude-synthetic-high',
            'models/gemini-4-hydrogen','models/gemini-4-neon','models/gemini-synthetic',
        ],'公开目录未按 Gemini 基础名称聚合')
        before=len(Fixture.calls)
        for action in ('generateContent','streamGenerateContent?alt=sse'):
            status,raw=request('/v1beta/models/gemini-unknown:'+action,body)
            require(status==404 and json.loads(raw)['error']['status']=='NOT_FOUND','未知模型错误码错误')
        require(len(Fixture.calls)==before,'未知模型进入发送边界')
        catalog=database.execute('SELECT usage_data FROM accounts WHERE id=1').fetchone()[0]
        with database:
            database.execute("UPDATE accounts SET usage_data='{}' WHERE id=1")
        require(request(base+'generateContent',body)[0]==503,'目录未观测时应保留503')
        with database:
            database.execute('UPDATE accounts SET usage_data=? WHERE id=1',(catalog,))
            database.execute("UPDATE account_credential_states SET phase='reconcile' WHERE account_id=1")
        require(request(base+'generateContent',body)[0]==503,'目录已知模型暂不可用时应返回503')
        require(len(Fixture.calls)==before,'待对账模型进入发送边界')
        with database:
            database.execute("UPDATE account_credential_states SET phase='ready' WHERE account_id=1")
        status,raw=request(base+'generateContent',body);require(status==200 and json.loads(raw)['usageMetadata']['totalTokenCount']==7,'真实非流式聚合失败')
        status,raw=request(base+'streamGenerateContent?alt=sse',body);require(status==200 and raw.startswith(b'data: ') and b'[DONE]' not in raw,'真实SSE协议失败')
        cases=[
            ('gemini-4-neon',{'thinkingLevel':'LOW','thinkingBudget':-1,'includeThoughts':True},'generateContent','gemini-4-neon-low','MODEL_SYNTHETIC_NEON_LOW'),
            ('gemini-4-neon',None,'streamGenerateContent?alt=sse','gemini-4-neon-high','MODEL_SYNTHETIC_NEON_HIGH'),
            ('gemini-4-hydrogen',{'thinkingBudget':1025},'generateContent','gemini-4-hydrogen-medium','MODEL_SYNTHETIC_HYDROGEN_MEDIUM'),
            ('gemini-4-hydrogen',None,'generateContent','gemini-4-hydrogen-medium','MODEL_SYNTHETIC_HYDROGEN_MEDIUM'),
            ('gemini-4-neon-low',{'thinkingLevel':'HIGH'},'generateContent','gemini-4-neon-low','MODEL_SYNTHETIC_NEON_LOW'),
            ('gemini-synthetic',{'thinkingLevel':'LOW'},'generateContent','gemini-synthetic-low','MODEL_PLACEHOLDER_M37'),
            ('gemini-synthetic',{'thinkingLevel':'HIGH'},'generateContent','gemini-synthetic','MODEL_PLACEHOLDER_M36'),
        ]
        for model,thinking,action,resolved,native_model in cases:
            candidate=copy.deepcopy(body)
            if thinking is not None:candidate['generationConfig']['thinkingConfig']=thinking
            status,_=request('/v1beta/models/'+model+':'+action,candidate)
            sent=Fixture.calls[-1]
            require(status==200 and (sent['model'],sent['native_model'])==(resolved,native_model),'Gemini 目录型号与执行ID不匹配')
            require(sent['body']==body,'档位字段进入了原生正文或改动其他入站参数')
        before=len(Fixture.calls)
        for model,thinking,expected in [
            ('gemini-4-neon',{'thinkingLevel':'MEDIUM'},404),
            ('gemini-4-neon-medium',None,404),
            ('gemini-4-neon',{'thinkingLevel':'broken'},400),
            ('gemini-4-neon',{'thinkingBudget':True},400),
        ]:
            candidate=copy.deepcopy(body)
            if thinking is not None:candidate['generationConfig']['thinkingConfig']=thinking
            status,_=request('/v1beta/models/'+model+':generateContent',candidate)
            require(status==expected,'Gemini 无可用档位或无效参数的错误不符')
        require(len(Fixture.calls)==before,'未匹配的型号进入发送边界')

        tool_base='/v1beta/models/gemini-4-neon:generateContent'
        tool=copy.deepcopy(body);tool['tools']=[{'functionDeclarations':[{'name':'synthetic_tool','parameters':{'type':'OBJECT','properties':{'x':{'type':'INTEGER'}}}}]}]
        tool['generationConfig']['thinkingConfig']={'thinkingLevel':'LOW'}
        status,raw=request(tool_base,tool);require(status==200 and Fixture.calls[-1]['model']=='gemini-4-neon-low','首工具轮失败')
        response=json.loads(raw)
        require(Fixture.waiting.wait(2),'原工具轮归属缺失')
        continuation=copy.deepcopy(tool)
        continuation['generationConfig']['thinkingConfig']={'thinkingLevel':'HIGH'}
        continuation['contents']+=[response['candidates'][0]['content'],{'role':'user','parts':[{'functionResponse':{'id':'synthetic-call','name':'synthetic_tool','response':{'value':'真实合成结果'}}}]}]
        previous=len(Fixture.calls)
        require(request(tool_base,continuation,key='synthetic-other')[0]==400,'跨调用方结果被接纳')
        wrong=copy.deepcopy(continuation);wrong['contents'][-1]['parts'][0]['functionResponse']['id']='other'
        require(request(tool_base,wrong)[0]==400,'错误工具ID被接纳')
        require(len(Fixture.calls)==previous,'错误结果进入模型发送边界')
        with database:
            database.execute("UPDATE account_credential_states SET phase='reconcile' WHERE account_id=1")
        require(request(tool_base,continuation)[0]==503,'待对账凭据被发布')
        require(Fixture.tool_drained.is_set() and len(Fixture.calls)==previous,'待对账期间旧工具没有独立收口')
        with database:
            database.execute("UPDATE account_credential_states SET phase='ready',generation=2 WHERE account_id=1")
            database.execute("UPDATE accounts SET access_token='synthetic-at-2' WHERE id=1")
        status,raw=request(tool_base,continuation)
        require(status==200 and json.loads(raw)['candidates'][0]['content']['parts'][0]['text']=='合成回复','concurrency=1续轮失败')
        require(Fixture.calls[-1]['model']=='gemini-4-neon-low','续轮改变了已绑定的型号')
        require(Fixture.tool_finished.is_set(),'真实工具回填未完成')
        require(request(tool_base,continuation)==(status,raw) and len(Fixture.calls)==previous+1,
            '重复工具结果未返回原响应或再次提交模型')
        require(len(Fixture.tool_completions)==1,'原生工具结果重复回填')
        for mode,operation,expected in [('control-502','generateContent',502),
                ('control-after-frame','streamGenerateContent?alt=sse',200)]:
            Fixture.tool_finished.clear()
            Fixture.tool_drained.clear()
            failed=copy.deepcopy(tool)
            failed['contents'][0]['parts'][0]['text']='replay-'+mode
            status,raw=request(tool_base,failed)
            require(status==200,'错误终态用例缺少原工具轮')
            failed['contents']+=[json.loads(raw)['candidates'][0]['content'], continuation['contents'][-1]]
            before,before_tools=len(Fixture.calls),len(Fixture.tool_completions)
            path=tool_base.rsplit(':',1)[0]+':'+operation
            first=request(path,failed)
            require(first[0]==expected and b'AGY' in first[1],'接续错误未返回实际原生终态')
            require(request(path,failed)==first and len(Fixture.calls)==before+1
                and len(Fixture.tool_completions)==before_tools+1,'失败续轮重试改变终态或重复发送')
        for mode,expected,attempts,refreshes in [('auth-recover',200,2,1),('capacity-error',429,1,0),('auth-always',503,2,1),('auth-after-frame',200,1,0)]:
            current=copy.deepcopy(body);current['contents'][0]['parts'][0]['text']=mode
            before=len(Fixture.calls);before_refresh=Fixture.refreshes
            action='streamGenerateContent?alt=sse' if mode=='auth-after-frame' else 'generateContent'
            status,raw=request(base+action,current)
            require(status==expected and len(Fixture.calls)-before==attempts and Fixture.refreshes-before_refresh==refreshes,
                '认证恢复预算或首帧门禁错误：'+mode+' '+str((status,len(Fixture.calls)-before,Fixture.refreshes-before_refresh)))
        for mode, operation, expected, code, reason in [
            ('control-400', 'generateContent', 400, 400, 'INVALID_ARGUMENT'),
            ('control-400', 'streamGenerateContent?alt=sse', 400, 400, 'INVALID_ARGUMENT'),
            ('control-502', 'generateContent', 502, 502, 'UNAVAILABLE'),
            ('control-200', 'generateContent', 503, 503, 'UNAVAILABLE'),
            ('control-legacy', 'generateContent', 503, 503, 'UNAVAILABLE'),
            ('control-after-frame', 'streamGenerateContent?alt=sse', 200, 400, 'INVALID_ARGUMENT'),
        ]:
            current = copy.deepcopy(body)
            current['contents'][0]['parts'][0]['text'] = mode
            before = len(Fixture.calls)
            status, raw = request(base + operation, current)
            if mode == 'control-after-frame':
                frames = [json.loads(line[6:]) for line in raw.decode().splitlines() if line.startswith('data: ')]
                require(len(frames) == 2 and frames[0].get('candidates'), '控制错误前已交付的 SSE 首帧丢失')
                error = frames[-1]['error']
            else:
                error = json.loads(raw)['error']
            require((status, error['code'], error['status']) == (expected, code, reason)
                and len(Fixture.calls) == before + 1, '原生控制状态投影或提交次数错误：' + mode)
        current=copy.deepcopy(body);current['contents'][0]['parts'][0]['text']='cancel-stream'
        stream=Request('http://127.0.0.1:5674'+base+'streamGenerateContent?alt=sse',data=json.dumps(current).encode(),
            headers={'x-api-key':'synthetic-key','content-type':'application/json'})
        response=urlopen(stream,timeout=8);require(response.readline().startswith(b'data: '),'取消场景缺少原首帧');response.close()
        require(Fixture.cancelled.wait(5),'SSE断连没有关闭原发送连接')
        require(request(base+'generateContent',body)[0]==200,'取消后原账号许可没有释放')
        with database:database.execute("UPDATE api_tokens SET status='disabled' WHERE token='synthetic-other'")
        require(request('/v1beta/models',key='synthetic-other')[0]==401,'禁用令牌被接纳')
        with database:
            database.execute("INSERT INTO accounts(id,name,email,platform,token,device_id,auth_type,access_token,refresh_token,oauth_expires_at,concurrency,auto_telemetry,auto_poll_usage,usage_data) VALUES(2,'synthetic-two','two@example.test','antigravity','','','oauth','synthetic-two-at','synthetic-two-rt','2099-01-01T00:00:00Z',1,0,0,?)",
                (json.dumps({'capabilities':{'model_mappings':{
                    'gemini-synthetic':'MODEL_PLACEHOLDER_M36','gemini-4-hydrogen-high':'MODEL_SYNTHETIC_HYDROGEN_HIGH',
                }}}),))
            database.execute("INSERT INTO account_credential_states(account_id,generation,phase,updated_at_ms) VALUES(2,1,'ready',1)")
            database.execute("INSERT INTO api_tokens(name,token,allowed_accounts,status) VALUES('two','synthetic-two-key','2','active')")
            database.execute("INSERT INTO api_tokens(name,token,allowed_accounts,status) VALUES('both','synthetic-both-key','1,2','active')")
            database.execute('UPDATE accounts SET agy_system_prompt_homoglyph_enabled=1 WHERE id=1')
        before=len(Fixture.calls)
        status,raw=request('/v1beta/models',key='synthetic-two-key')
        require(status==200 and [item['name'] for item in json.loads(raw)['models']]==[
            'models/gemini-4-hydrogen','models/gemini-synthetic',
        ],'公开目录包含令牌范围外的模型')
        status,raw=request('/v1beta/models',key='synthetic-both-key')
        require(status==200 and [item['name'] for item in json.loads(raw)['models']]==names,
            '同一模型的多账号档位未聚合')
        require(request('/v1beta/models/gemini-4-hydrogen:generateContent',
            {**body,'generationConfig':{'thinkingConfig':{'thinkingLevel':'MEDIUM'}}},key='synthetic-two-key')[0]==404,
            '指定档位缺失时使用了令牌范围外的账号或改用其他档位')
        require(request('/v1beta/models/claude-synthetic:generateContent',body,key='synthetic-two-key')[0]==404,
            '其他账号的模型目录进入当前令牌范围')
        require(request('/v1beta/models/gemini-4-neon:generateContent',body,key='synthetic-two-key')[0]==404,
            'Gemini 档位匹配使用了其他账号的目录')
        require(len(Fixture.calls)==before,'令牌范围外的模型进入发送边界')
        status,_=request('/v1beta/models/gemini-4-hydrogen:generateContent',body,key='synthetic-both-key')
        require(status==200 and Fixture.calls[-1]['request']['account_id']==2
            and Fixture.calls[-1]['model']=='gemini-4-hydrogen-high','默认档位优先级未跨账号生效')
        candidate=copy.deepcopy(body);candidate['systemInstruction']={'parts':[{'text':'ABC system 中文'}]}
        for key,account,enabled in [('synthetic-key',1,True),('synthetic-two-key',2,False)]:
            require(request(base+'generateContent',candidate,key=key)[0]==200,'账号独立策略请求失败')
            sent=Fixture.calls[-1]
            require(sent['request']['account_id']==account and sent.get('system_prompt_policy',{}).get('enabled',False)==enabled,'账号策略快照串用')
            require(sent['body']==candidate,'网关改变了原始Gemini入站视图')
        before=len(Fixture.calls);current=copy.deepcopy(candidate);current['contents'][0]['parts'][0]['text']='policy-auth-recover'
        require(request(base+'generateContent',current)[0]==200,'策略认证恢复失败')
        require(len(Fixture.calls)==before+2 and all(value['system_prompt_policy']['enabled'] for value in Fixture.calls[before:]),'认证恢复重新读取了变化后的开关')
        require(database.execute('SELECT agy_system_prompt_homoglyph_enabled FROM accounts WHERE id=1').fetchone()[0]==0,'并发开关变化未进入真实存储')
        require(request(base+'generateContent',candidate)[0]==200 and 'system_prompt_policy' not in Fixture.calls[-1],'后续HTTP没有读取关闭策略')
        with database:database.execute('UPDATE accounts SET agy_system_prompt_homoglyph_enabled=1 WHERE id=1')
        for mode in ['policy-no-receipt','policy-wrong-receipt']:
            current=copy.deepcopy(candidate);current['contents'][0]['parts'][0]['text']=mode
            require(request(base+'generateContent',current)[0]==503,'缺失或不匹配的策略回执被接纳')
        require(request('/v1beta/models/claude-synthetic:generateContent',body)[0]==200,'AGY上Claude模型请求失败')
        generation=database.execute('SELECT generation FROM account_credential_states WHERE account_id=1').fetchone()[0]
        refreshes,before=Fixture.refreshes,len(Fixture.calls)
        # 310 秒足够立即启动原生，但需要为后续的请求预算留余量。
        with database:
            database.execute("UPDATE accounts SET oauth_expires_at=strftime('%Y-%m-%dT%H:%M:%SZ', 'now', '+310 seconds') WHERE id=1")
        require(request(base+'generateContent',body)[0]==200,'临近到期的凭据未完成请求')
        require(Fixture.refreshes==refreshes+1 and len(Fixture.calls)==before+1,'凭据预刷新次数或提交次数不符')
        require(Fixture.calls[-1]['credential_snapshot']['credential_generation']==generation+1,'原生业务仍收到临近到期的凭据代次')
        with database:
            database.execute("UPDATE accounts SET oauth_expires_at=strftime('%Y-%m-%dT%H:%M:%SZ', 'now', '+650 seconds') WHERE id=1")
        require(request(base+'generateContent',body)[0]==200 and Fixture.refreshes==refreshes+1,
            '有效期充足的凭据被重复刷新')
        # 从真实持久摘要按私有attempt关联，避免用当前账号资料替代历史事实。
        until=time.monotonic()+10
        while time.monotonic()<until:
            attempts=[json.loads(row[0]) for row in database.execute('SELECT summary_json FROM request_diagnostic_attempts')]
            if len(attempts)==len(Fixture.calls) and all(a.get('finished_at') for a in attempts):break
            time.sleep(.02)
        require(len(attempts)==len(Fixture.calls),'真实发送和持久尝试计数不一致')
        by_id={value['request']['request_id']:value for value in Fixture.calls}
        for attempt in attempts:
            source=by_id[attempt['attempt_id']];context=attempt.get('context',{})
            require(context.get('platform')=='antigravity' and context.get('entry_protocol')=='gemini','持久平台或协议被模型名覆盖')
            require(context.get('credential_generation')==source['credential_snapshot']['credential_generation'],'尝试凭据代次漂移')
            require(attempt['account_id']==source['request']['account_id'],'持久尝试跨账号')
            mode = source['body']['contents'][0]['parts'][0].get('text')
            if mode in ('control-400', 'control-502', 'control-after-frame'):
                require(attempt['status_code'] == (502 if mode == 'control-502' else 400)
                    and attempt['error_stage'] == 'native_control', '请求记录遗漏控制状态或阶段')
        require(any(a.get('context',{}).get('requested_model')=='claude-synthetic' for a in attempts),'Claude模型记录缺失')
        require(any(a.get('context',{}).get('requested_model')=='gemini-4-neon'
            and a['context'].get('submitted_model')=='MODEL_SYNTHETIC_NEON_LOW' for a in attempts),'档位匹配覆盖了原始请求名')
        recovered=[a for a in attempts if a.get('retry_reason')=='oauth_recovery']
        require(len(recovered)>=3,'401恢复尝试原因缺失')
        roots={row[0]:json.loads(row[1]) for row in database.execute('SELECT request_id,summary_json FROM request_diagnostics')}
        for attempt in recovered:
            same=[a for a in attempts if a['request_id']==attempt['request_id']]
            require(len(same)==2 and roots[attempt['request_id']]['attempt_count']==2,'401恢复未保留同根两尝试')
            require(same[0]['context']['credential_generation']!=same[1]['context']['credential_generation'],'401恢复代次未分别记录')
        database.close()
        return {'passed':True,'evidence':'real_http_sqlite_synthetic_sender','network':'none','real_model_submissions':0,
            'synthetic_submissions':len(Fixture.calls),'checks':['真实Gemini目录与令牌','按档位匹配目录、保留精确型号与令牌范围','非流式源usage','SSE','函数签名和结果','错调用方和ID拒绝',
                '待对账期间旧工具独立收口和新模型拒绝','concurrency=1原许可接续','新AT代次','重复回填复用原响应','禁用令牌',
                '明确401仅恢复一次','容量错误零恢复','SSE首帧后零重放','SSE断连关闭原发送和释放许可',
                '原生控制状态在HTTP、SSE尾帧及诊断中一致',
                '两账号策略隔离','认证恢复冻结策略','后续HTTP采用新开关','缺失和错误策略回执拒绝','原始入站视图保持',
                '真实SQLite尝试计数和凭据代次','401同根两尝试及恢复原因','AGY调用Claude平台保持']}
    finally:
        child.terminate()
        try:child.wait(timeout=5)
        except subprocess.TimeoutExpired:child.kill();child.wait()
        output.close()


def main() -> None:
    """选择明确镜像运行零真实模型的跨层探针。@return 无。"""
    parser=argparse.ArgumentParser();parser.add_argument('--image');parser.add_argument('--inside',action='store_true');args=parser.parse_args()
    if args.inside:
        print(json.dumps(inside(),ensure_ascii=False));return
    require(bool(args.image),'需要明确的测试镜像')
    import docker
    root=Path(__file__).resolve().parents[2]
    folder=Path(tempfile.mkdtemp(prefix='agy-gemini-http-'))
    client=docker.from_env(timeout=15);container=None
    try:
        host='flower2api-'+hashlib.sha256(b'synthetic').hexdigest()[:12]+'-'+ENVIRONMENT
        container=client.containers.run(args.image,['/opt/probe.py','--inside'],entrypoint=['python3'],detach=True,network_mode='none',
            read_only=True,cap_drop=['ALL'],security_opt=['no-new-privileges:true'],mem_limit='768m',pids_limit=256,
            extra_hosts={host:'127.0.0.1',host.replace(ENVIRONMENT,'b'*32):'127.0.0.1'},tmpfs={'/tmp':'rw,nosuid,nodev,size=64m'},
            volumes={str(root/'services/gateway/target/debug/claude-code-gateway'):{'bind':'/opt/gateway','mode':'ro'},
                str(Path(__file__).resolve()):{'bind':'/opt/probe.py','mode':'ro'},str(folder):{'bind':'/state','mode':'rw'}},
            environment={'DATABASE_DRIVER':'sqlite','DATABASE_DSN':'/state/gateway.sqlite','ADMIN_PASSWORD':'synthetic-admin',
                'V3_RUNTIME_URL':'http://127.0.0.1:8765','V3_INTERNAL_TOKEN':SECRET,'V3_DEPLOYMENT_ID':'synthetic',
                'V3_RELEASE':'synthetic-release','LOG_LEVEL':'warn','TOKIO_WORKER_THREADS':'2'},labels={'vibebench.test-task':'agy-account-runtime'})
        result=container.wait(timeout=110)
        logs=container.logs().decode(errors='replace')
        if result['StatusCode']:
            (root/'.trellis/.runtime/agy-runtime-http-gateway-private.log').write_text((folder/'gateway.log').read_text() if (folder/'gateway.log').exists() else '')
            raise ValueError(logs)
        print(logs.strip())
    finally:
        if container:container.remove(force=True)
        shutil.rmtree(folder)


if __name__=='__main__':main()
