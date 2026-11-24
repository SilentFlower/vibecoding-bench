#!/usr/bin/env python3
"""验收显式候选的账号转发切换；可接固定 native293 制品验证真实 V1。"""

import argparse
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from hashlib import sha256
from importlib import import_module
import json
from pathlib import Path
from sqlite3 import connect
from subprocess import check_output, run
import sys
from tempfile import mkdtemp
from threading import Event
from time import monotonic_ns
from uuid import uuid4

from verify_tui_concurrency import CLEAN_ENV, ROOT, wait_for, write_json
from verify_tui_http_handoff import (
    ARGUMENTS, COMPETING, ORIGINAL, delivered_tool, final_text, gateway_ingress, http_request,
    message_sse, public_post,
)

SCRIPT = Path(__file__).resolve()
V1_LAUNCHER = '017ec892b9dfbf08bf4cb2e5bf59048cb41a0ecfc21b1ad518751a23a911b9b7'
V1_IMAGE = 'eec33dc1466f4180f0448b2524c67b10656764603592aad73e26b0389d3c26eb'
V1_TOOL_PROMPT = 'Return the client-side Read tool before completing the native turn.'


def native_bridge(args, root, bearer, tool_id=None):
    """复用回环 V1 装置。@param args 制品。@param root 证据。@param bearer 合成认证。
    @param tool_id 可选的真实内核上游工具。@return sender 工厂。
    """
    if args.v1_probe_dir is None:
        return None
    sys.path.insert(0,str(args.v1_probe_dir))
    helper = import_module('gateway_v1')
    model = import_module('v1_bridge')
    model.UPSTREAM_BEARER = bearer
    assert model.digest(args.native_kernel)==V1_LAUNCHER
    if tool_id is not None:
        normal_payload = model.upstream_payload

        def payload(body, marker):
            raw = body['messages'][-1]['content']
            texts = [raw] if isinstance(raw,str) else [part.get('text') for part in raw if part['type']=='text']
            if V1_TOOL_PROMPT in texts:
                block = {'type':'tool_use','id':tool_id,'name':'Read','input':ARGUMENTS}
                return message_sse(block,'tool_use','msg_native_offer'), 'text/event-stream'
            return normal_payload(body,marker)

        model.upstream_payload = payload

    def start(stack, binding):
        root.mkdir()
        (root/'hosts').write_text('127.0.0.1 localhost\n')
        ca, proxy, services = model.start_upstream(root)
        for server in services:
            stack.callback(server.server_close)
            stack.callback(server.shutdown)
        run(['openssl','x509','-in',str(ca),'-outform','DER','-out',str(root/'verification-ca.der')],check=True)
        write_json(root/'sender.json', {
            'binding':binding,'proxy_url':proxy,'allowed_origin':'https://api.anthropic.com',
            'native':{'source_version':'2.1.293','binary_path':'/opt/ccrb-runtime',
                      'release':{'release':'v0.1.0-beta.7','launcher_sha256':V1_LAUNCHER},
                      'work_root':'/lab/workers','memory_mib':0,'max_workers':4},
            'native_adaptive_prewarm':False,'native_capture_dir':'/lab/captures',
        })
        port = helper.port()
        process = helper.sandbox(stack,root,args.native_sender,args.native_kernel,'sender', {
            'V3_SENDER_CONFIG':'/lab/sender.json','V3_SENDER_LISTEN':f'127.0.0.1:{port}',
        })
        helper.ready(port,process,'native sender')
        status, raw = http_request(port,'GET','/internal/native/status',binding['secret'])
        assert status==200 and json.loads(raw)['raw_input_protocol']==1
        write_json(root/'artifacts.json',{'launcher_sha256':V1_LAUNCHER,'image_sha256':V1_IMAGE,
            'sender_sha256':model.digest(args.native_sender),'kernel_path':str(args.native_kernel),
            'sender_path':str(args.native_sender)})
        return port

    return start


def verify(root, args):
    """在同一独立 Gateway 核对账号状态与切换。@param root 证据根。@param args 制品参数。@return 对照结果。"""
    bearer = 'fixture-' + uuid4().hex
    start_native = native_bridge(args,root/'native',bearer)
    options = {'setup_token':bearer,'account_uuid':'11111111-1111-4111-8111-111111111111',
               'organization_uuid':'22222222-2222-4222-8222-222222222222'}
    with gateway_ingress(root/'gateway',args.gateway,1,True,second_account=True,
                         native_sender=start_native,account_options=options) as (
            port,key,admin,fixture,_), ThreadPoolExecutor(max_workers=2) as pool:
        log = []
        primary, peer = '/admin/accounts/1','/admin/accounts/2'

        def view(path, event):
            state = admin('GET',path)
            row = {field:state.get(field) for field in ('request_backend','request_backend_pending',
                    'request_backend_revision','tui_v2_available','request_backend_wait_reason')}
            log.append({'event':event,'path':path,**row})
            write_json(root/'management.json',log)
            return state

        def switch(target, revision):
            return admin('PUT',primary,{'request_backend':target,'request_backend_revision':revision})

        def persisted():
            with closing(connect(f"file:{fixture.folder/'gateway.db'}?mode=ro",uri=True)) as db:
                return db.execute('SELECT a.request_backend, i.target, i.binding, i.revision '
                                  'FROM accounts a JOIN tui_backend_intents i ON a.id=i.account_id '
                                  'WHERE a.id=1').fetchone()

        def capacity():
            row, = [row for row in admin('GET','/admin/accounts')['data'] if row['id']==1]
            return row['active_requests'],row['queued_requests']

        def assert_no_write(revision, label):
            old = persisted()
            quiesces = len(fixture.events('orchestrator_quiesce'))
            lookups = len(fixture.events('registry_lookup'))
            snap = view(primary,label)
            listed, = [row for row in admin('GET','/admin/accounts')['data'] if row['id']==1]
            assert snap['request_backend']==listed['request_backend']==old[0]
            assert snap['request_backend_pending']==listed['request_backend_pending']==(old[1] or None)
            assert snap['request_backend_revision']==listed['request_backend_revision']==old[3]
            assert persisted()==old and len(fixture.events('orchestrator_quiesce'))==quiesces
            repeat = switch(old[1] or old[0],revision)
            assert repeat['request_backend_revision']==old[3]
            assert persisted()==old and len(fixture.events('orchestrator_quiesce'))==quiesces
            probes = fixture.events('registry_lookup')[lookups:]
            assert probes and all(row['query']=='wake=false' for row in probes)
            log.append({'event':'read_and_idempotent_put','stage':label,'revision':old[3],
                        'wake_calls':0,'quiesce_calls':0})
            write_json(root/'management.json',log)
            return snap

        initial = view(primary,'v2_effective')
        assert initial['request_backend']=='tui_v2' and initial['tui_v2_available'] is True
        other = view(peer,'peer_legacy')
        assert other['request_backend']=='legacy' and other['tui_v2_available'] is False
        timestamp = other['request_backend_revision']
        denied, _ = http_request(port,'PUT',peer,fixture.admin_token,{'request_backend':'tui_v2'})
        assert denied==503
        prompt = [{'role':'user','content':ORIGINAL}]
        first = delivered_tool(public_post(fixture.folder,'original',port,key,prompt,fixture.turn.session_id))
        process = fixture.processes[0]
        assert process.poll() is None and fixture.capacity.snapshot().in_use==1
        stored = fixture.store.read(fixture.turn,first['id'])
        assert stored.state=='delivery_unknown'
        waiting = switch('native293',initial['request_backend_revision'])
        assert waiting['request_backend']=='tui_v2' and waiting['request_backend_pending']=='native293'
        reread = assert_no_write(initial['request_backend_revision'],'waiting_before_tool_result')
        assert reread['request_backend_pending']=='native293'
        assert persisted()==('tui_v2',reread['request_backend_pending'],
                             json.loads((fixture.folder/'binding.json').read_text())['gateway_environment_id']+':1',
                             reread['request_backend_revision'])
        try:
            before = fixture.model_snapshot()
            status, _ = public_post(fixture.folder,'new_during_drain',port,key,
                [{'role':'user','content':COMPETING}],fixture.new_turn.session_id)
            assert status==429 and fixture.model_snapshot()==before
            peer_result = public_post(fixture.folder,'other_while_draining',port,fixture.other_key,
                [{'role':'user','content':COMPETING}],str(uuid4()))
            assert final_text(peer_result)=='OTHER_LEGACY_ACCOUNT'
            assert view(peer,'peer_served_independently')['request_backend_revision']==timestamp
            cancelled = switch('tui_v2',reread['request_backend_revision'])
            assert cancelled['request_backend']=='tui_v2' and cancelled['request_backend_pending'] is None
            assert view(primary,'cancelled')['request_backend_pending'] is None
            stale, _ = http_request(port,'PUT',primary,fixture.admin_token,
                {'request_backend':'native293','request_backend_revision':reread['request_backend_revision']})
            assert stale==503
            second = switch('native293',cancelled['request_backend_revision'])
            assert view(primary,'waiting_again')['request_backend_pending']=='native293'

            local = root/'only-client-note.txt'
            content = 'LOCAL_ONLY_' + uuid4().hex + '\n只读。\n'
            local.write_text(content)
            follow = [*prompt,{'role':'assistant','content':[first]},
                      {'role':'user','content':[{'type':'tool_result','tool_use_id':first['id'],
                                                'content':local.read_text()}]}]
            fixture.set_test_generation(2)
            try:
                mismatch = view(primary,'new_generation_reports_idle')
                assert mismatch['request_backend']=='tui_v2' and mismatch['request_backend_pending']=='native293'
                assert mismatch['request_backend_wait_reason']=='runtime_unconfirmed'
                prepares = len(fixture.events('candidate_prepare_rpc'))
                generation_status, _ = public_post(fixture.folder,'wrong_generation',port,key,follow,fixture.turn.session_id)
                assert generation_status==503 and fixture.acknowledged==0 and fixture.model_snapshot()==before
                assert len(fixture.events('candidate_prepare_rpc'))==prepares
                cleared = switch('tui_v2',second['request_backend_revision'])
                assert cleared['request_backend_pending'] is None
                assert view(primary,'cancelled_with_wrong_generation')['request_backend']=='tui_v2'
                cleared_status, _ = public_post(fixture.folder,'wrong_generation_after_cancel',port,key,follow,
                                                fixture.turn.session_id)
                assert cleared_status==503 and len(fixture.events('candidate_prepare_rpc'))==prepares
            finally:
                fixture.set_test_generation(1)

            continuing = pool.submit(public_post,fixture.folder,'continuation',port,key,follow,fixture.turn.session_id)
            wait_for(lambda:fixture.store.read(fixture.turn,first['id']).state=='received','原结果未进入真实交接组件')
            assert view(primary,'continuation_in_flight')['request_backend']=='tui_v2'
            queued = pool.submit(public_post,fixture.folder,'prepared_new',port,key,
                                 [{'role':'user','content':COMPETING}],fixture.new_turn.session_id)
            wait_for(lambda:fixture.capacity.snapshot().waiting==1 and capacity()==(1,0),
                     '新轮等待物理名额时不应持有普通槽')
            fixture.continuation_gate.set()
            wait_for(lambda:fixture.events('original_waiting_to_reply'),'原轮未到达响应交付边界')
            prepared, = wait_for(lambda:fixture.events('candidate_prepared',kind='competing'),'新轮尚未完成 prepare')
            wait_for(lambda:capacity()==(1,1),'新预留未在等待唯一普通槽')
            reservation = prepared['request_id']
            assert process.poll() is not None and not continuing.done() and not queued.done()
            wait_intent = switch('native293',cleared['request_backend_revision'])
            assert wait_intent['request_backend']=='tui_v2' and wait_intent['request_backend_pending']=='native293'
            assert_no_write(cleared['request_backend_revision'],'prepared_new_waiting_for_slot')
            assert not fixture.events('candidate_send_rpc',request_id=reservation)
            assert len(fixture.model_snapshot())==2
            if args.cancel_prepared:
                withdrawn = switch('tui_v2',wait_intent['request_backend_revision'])
                assert withdrawn['request_backend_pending'] is None
                assert_no_write(wait_intent['request_backend_revision'],'withdraw_while_prepared')
            fixture.response_gate.set()
            assert final_text(continuing.result(timeout=12))=='READ_RESULT_'+sha256(content.encode()).hexdigest()
            assert fixture.store.read(fixture.turn,first['id']).state=='closed' and fixture.acknowledged==1
            admitted = queued.result(timeout=12)
            regular_models = (('original','first',process.pid),('original','continuation',process.pid))
            claims = {'status':'passed','gateway_http_slots':1,'accounts':[1,2],'positive_v2_posts':2,
                      'rejected_in_drain':status,'missing_capability':denied,'stale_revision':stale,
                      'wrong_generation_status':generation_status,'wrong_generation_after_cancel':cleared_status,
                      'pending_persisted':True,'readonly_get_and_repeated_put':True,
                      'external_tool_id':first['id'],'internal_tool_id':stored.internal_id,
                      'same_process':process.pid,'delivery_count':fixture.acknowledged}
            if args.cancel_prepared:
                assert final_text(admitted)=='COMPETING_TURN_RAN'
                assert len(fixture.events('candidate_send_rpc',request_id=reservation))==1
                assert not fixture.events('candidate_cancel_rpc',request_id=reservation)
                assert fixture.model_snapshot()==(*regular_models,('competing','first',fixture.processes[1].pid))
                assert view(primary,'after_withdrawal')['request_backend']=='tui_v2'
                return {**claims,'prepared_new':{'status':200,'send_calls':1,'added_model_posts':1}}

            assert admitted[0]==429
            aborted, = wait_for(lambda:fixture.events('candidate_aborted',request_id=reservation),
                                'Gateway 未回收待发的新轮预留')
            assert aborted['source']=='gateway' and fixture.processes[1].poll() is not None
            assert len(fixture.events('candidate_cancel_rpc',request_id=reservation))==1
            assert not fixture.events('candidate_send_rpc',request_id=reservation)
            assert fixture.model_snapshot()==regular_models
            wait_for(lambda:persisted()[:2]==('native293',''),'后台未在排空后提交切换')
            next_request = public_post(fixture.folder,'first_v1',port,key,
                [{'role':'user','content':'Report the isolated native runtime marker.'}],str(uuid4()))
            next_view = view(primary,'after_delivery')
            assert next_view['request_backend']=='native293' and next_view['request_backend_pending'] is None
            applied = persisted()
            quiesces = len(fixture.events('orchestrator_quiesce'))
            replayed = switch('native293',cleared['request_backend_revision'])
            assert replayed['request_backend']=='native293' and replayed['request_backend_revision']==applied[3]
            assert persisted()==applied and len(fixture.events('orchestrator_quiesce'))==quiesces
            assert view(peer,'peer_still_legacy')['request_backend']=='legacy'
            assert fixture.model_snapshot()==regular_models
            requests = fixture.events('native_endpoint')
            assert any(row['route']=='/internal/native/status' for row in requests)
            if start_native is None:
                assert next_request[0]==503
                assert not any(row['route']=='/internal/native/messages' for row in requests)
                v1 = {'status':503,'first_error':'native sender status unavailable','native_model_posts':0}
            else:
                upstream = root/'native'/'upstream.jsonl'
                posted = [json.loads(row) for row in upstream.read_text().splitlines()] if upstream.is_file() else []
                if next_request[0]!=200:
                    return {'status':'failed','first_error':'真实 native293 首请求失败',
                            'v1_http_status':next_request[0],'native_model_posts':len(posted),'native_calls':requests}
                assert any(row['route']=='/internal/native/messages' and row['forwarded'] for row in requests)
                model_call, = posted
                assert final_text(next_request)==model_call['marker']
                v1 = {'status':200,'marker':model_call['marker'],'native_model_posts':1}
            return {**claims,'prepared_new':{'status':429,'send_calls':0,'cancel_calls':1,'added_model_posts':0},
                    'next_v1':v1}
        finally:
            fixture.continuation_gate.set()
            fixture.response_gate.set()


def verify_native_origin(root, args):
    """用真实 native293 证明 V1 待排空只放行已登记旧轮。@param root 证据。@param args 制品。@return 结果。"""
    bearer = 'fixture-' + uuid4().hex
    external_id = 'toolu_v1_' + uuid4().hex
    start_native = native_bridge(args,root/'native',bearer,external_id)
    options = {'setup_token':bearer,'account_uuid':'11111111-1111-4111-8111-111111111111',
               'organization_uuid':'22222222-2222-4222-8222-222222222222'}
    with gateway_ingress(root/'gateway',args.gateway,1,True,native_sender=start_native,
                         account_options=options) as (port,key,admin,fixture,_):
        account = '/admin/accounts/1'
        upstream = root/'native'/'upstream.jsonl'
        history = [{'role':'user','content':V1_TOOL_PROMPT}]
        session = fixture.turn.session_id

        def rows():
            return [json.loads(line) for line in upstream.read_text().splitlines()] if upstream.is_file() else []

        def intent():
            with closing(connect(f"file:{fixture.folder/'gateway.db'}?mode=ro",uri=True)) as db:
                return db.execute('SELECT a.request_backend, i.target, i.revision FROM accounts a '
                                  'JOIN tui_backend_intents i ON a.id=i.account_id WHERE a.id=1').fetchone()

        def switch(target, version):
            return admin('PUT',account,{'request_backend':target,'request_backend_revision':version})

        active = switch('native293',intent()[2])
        assert active['request_backend']=='native293'
        call = delivered_tool(public_post(fixture.folder,'native_offer',port,key,history,session))
        assert call=={'type':'tool_use','id':external_id,'name':'Read','input':ARGUMENTS}
        assert len(rows())==1
        with closing(connect(f"file:{fixture.folder/'gateway.db'}?mode=ro",uri=True)) as db:
            owner, stored_session, binding, version, tools = db.execute(
                'SELECT principal_id, session_id, binding, version, tools FROM tui_native_turns WHERE account_id=1'
            ).fetchone()
        assert str(owner)==fixture.turn.principal_id and stored_session==session
        assert binding.endswith(':1') and version=='2.1.293' and json.loads(tools)==[external_id]
        marker = 'NATIVE_LOCAL_ONLY_' + uuid4().hex
        private_file = root/'client-note.txt'
        private_file.write_text(marker)
        follow = history + [{'role':'assistant','content':[call]}, {'role':'user','content':[
            {'type':'tool_result','tool_use_id':external_id,'content':private_file.read_text()}]}]
        quiesces = len(fixture.events('orchestrator_quiesce'))
        requested = switch('tui_v2',active['request_backend_revision'])
        waiting = intent()
        assert waiting[:2]==('native293','tui_v2')
        assert requested['request_backend_revision']==waiting[2]
        fixture.restart_gateway()
        assert intent()==waiting and len(rows())==1

        rejected = {}
        for name, token, owner_session, messages, status in (
            ('new_v1',key,str(uuid4()),[{'role':'user','content':'Another turn'}],429),
            ('wrong_session',key,str(uuid4()),follow,400),
            ('wrong_subject',fixture.foreign_key,session,follow,400),
            ('unknown_result',key,session,[*follow[:-1],{'role':'user','content':[
                {'type':'tool_result','tool_use_id':'toolu_unknown','content':'unrelated'}]}],400),
        ):
            actual, _ = public_post(fixture.folder,name,port,token,messages,owner_session)
            assert actual==status and len(rows())==1 and intent()==waiting
            rejected[name] = actual
        fixture.set_test_generation(2)
        try:
            state = admin('GET',account)
            assert state['request_backend_wait_reason']=='runtime_unconfirmed'
            rejected['wrong_generation'], _ = public_post(fixture.folder,'wrong_generation',port,key,follow,session)
            assert rejected['wrong_generation']==503 and len(rows())==1
        finally:
            fixture.set_test_generation(1)
        assert len(fixture.events('orchestrator_quiesce'))==quiesces

        fixture.quiesce_gate = Event()
        try:
            final = public_post(fixture.folder,'native_continuation',port,key,follow,session)
            model_rows = rows()
            assert len(model_rows)==2 and final_text(final)==model_rows[1]['marker']
            matched = model_rows[1]['body']['messages'][-1]['content']
            assert any(item['type']=='tool_result' and item['tool_use_id']==external_id
                       and marker in json.dumps(item['content']) for item in matched)
            wait_for(lambda:len(fixture.events('orchestrator_quiesce'))==quiesces+1,
                     'V1 原轮收口后后台未进入配置门禁')
            # 后台占着配置锁时，GET 必须仍能完成；意向保持不变，直到授权对账的门禁返回。
            detail = admin('GET',account)
            entry, = admin('GET','/admin/accounts')['data']
            assert detail['request_backend']==entry['request_backend']=='native293'
            assert detail['request_backend_pending']==entry['request_backend_pending']=='tui_v2'
            assert intent()==waiting and len(fixture.events('orchestrator_quiesce'))==quiesces+1
        finally:
            fixture.quiesce_gate.set()
        wait_for(lambda:intent()[:2]==('tui_v2',''),'后台未推进 V1→V2')
        with closing(connect(f"file:{fixture.folder/'gateway.db'}?mode=ro",uri=True)) as db:
            assert db.execute("SELECT COUNT(*) FROM tui_native_turns WHERE account_id=1 AND tools NOT LIKE '#%'").fetchone()[0]==0
        # 再切回允许导入历史的 V1，验证首轮已消费的工具结果不会重新投递，终态在重启后仍有效。
        for backend in ('tui_v2','native293'):
            assert switch(backend,intent()[2])['request_backend']==backend
            if backend=='native293':
                fixture.restart_gateway()
            name = 'completed_tool_on_'+backend
            status, _ = public_post(fixture.folder,name,port,key,follow,session)
            assert status==400 and len(rows())==2 and not fixture.model_snapshot()
            assert '已处理' in (fixture.folder/(name+'.body')).read_text()
            rejected[name] = status
        next_history = [*follow,{'role':'assistant','content':final_text(final)},
                        {'role':'user','content':'请在已完成的工具历史后继续。'}]
        next_response = public_post(fixture.folder,'next_question',port,key,next_history,session)
        assert final_text(next_response)==rows()[2]['marker'] and len(rows())==3
        assert switch('tui_v2',intent()[2])['request_backend']=='tui_v2'
        switched = delivered_tool(public_post(fixture.folder,'first_v2',port,key,
                                  [{'role':'user','content':ORIGINAL}],fixture.turn.session_id))
        assert switched['id']==fixture.external_id and len(fixture.model_snapshot())==1 and len(rows())==3
        return {'status':'passed','direction':'native293_to_tui_v2','native_model_posts':3,
                'readonly_get_during_quiesce':True,'matched_tool_id':external_id,'rejections':rejected,
                'gateway_restart_during_drain_and_after_switchback':True,
                'next_question_after_completed_history':next_response[0],
                'v1_final_marker':model_rows[1]['marker'],'first_v2':{'status':200,'model_posts':1}}


def verify_sessionless(root, args, *, native):
    """在单槽公共入口验证缺省会话的归属。@param root 证据目录。@param args 制品。@param native 使用固定 V1。@return 实测。"""
    external_id = 'toolu_' + uuid4().hex * 10
    bearer = 'fixture-' + uuid4().hex
    options = {'setup_token':bearer,'account_uuid':'11111111-1111-4111-8111-111111111111',
               'organization_uuid':'22222222-2222-4222-8222-222222222222'}
    root.mkdir()
    start_native = native_bridge(args,root/'native',bearer,external_id) if native else None
    with gateway_ingress(root/'gateway',args.gateway,1,True,native_sender=start_native,second_account=True,
                         account_options=options) as (port,key,admin,fixture,_):
        account = '/admin/accounts/1'
        upstream = root/'native'/'upstream.jsonl'

        def model_calls():
            if native:
                return [json.loads(line) for line in upstream.read_text().splitlines()] if upstream.is_file() else []
            return fixture.model_snapshot()

        def outstanding():
            with closing(connect(f"file:{fixture.folder/'gateway.db'}?mode=ro",uri=True)) as db:
                return db.execute('SELECT t.principal_id, t.session_id, t.binding, t.version, t.tools '
                                  'FROM tui_native_turns t JOIN tui_stateless_turn_proofs p ON p.turn_id=t.id '
                                  'WHERE t.account_id=1').fetchall()

        def switch(target):
            view = admin('GET',account)
            return admin('PUT',account,{'request_backend':target,
                                       'request_backend_revision':view['request_backend_revision']})

        backend = 'native293' if native else 'tui_v2'
        target = 'tui_v2' if native else 'legacy'
        if native:
            assert switch(backend)['request_backend']==backend
        else:
            fixture.accept_server_session = True
            fixture.external_id = external_id
            fixture.continuation_gate.set()
            fixture.response_gate.set()
        history = [{'role':'user','content':V1_TOOL_PROMPT if native else ORIGINAL}]
        call = delivered_tool(public_post(fixture.folder,'offer',port,key,history,None))
        assert call=={'type':'tool_use','id':external_id,'name':'Read','input':ARGUMENTS}
        assert len(model_calls())==1
        [(owner, session, binding, version, tools)] = outstanding()
        assert str(owner)==fixture.turn.principal_id and binding.endswith(':1')
        assert version==('2.1.293' if native else 'tui-v2:2.1.293:1') and json.loads(tools)==[external_id]
        if not native:
            assert fixture.turn.session_id=='gateway-tools-'+session
        write_json(root/'tool-owner.json',{'principal_id':owner,'account_id':1,
                   'server_session_id':session,'binding':binding,'version':version,'tool_id':external_id})
        marker = 'SESSIONLESS_LOCAL_' + uuid4().hex
        private_file = root/'client-note.txt'
        private_file.write_text(marker)
        result = {'role':'user','content':[
            {'type':'tool_result','tool_use_id':external_id,'content':private_file.read_text()}]}
        follow = history + [{'role':'assistant','content':[call]},result]
        explicit = session if native else fixture.turn.session_id
        status, _ = public_post(fixture.folder,'claimed_session_before_drain',port,key,follow,explicit)
        assert status==400 and len(model_calls())==1 and len(outstanding())==1
        rejected = {'claimed_session_before_drain':status}
        if native:
            for name, token in (('arbitrary_session_before_drain',key),
                                ('foreign_arbitrary_session_before_drain',fixture.foreign_key)):
                status, _ = public_post(fixture.folder,name,port,token,follow,str(uuid4()))
                assert status==400 and len(model_calls())==1 and len(outstanding())==1
                rejected[name] = status
            # 模拟旧构建留下的已发出工具、无真实主体的记录。
            with closing(connect(fixture.folder/'gateway.db')) as db, db:
                db.execute('INSERT INTO tui_native_turns (id,account_id,principal_id,session_id,binding,version,tools) '
                           'VALUES (?,?,?,?,?,?,?)',
                           (str(uuid4()),1,0,str(uuid4()),binding,version,tools))
        assert switch(target)['request_backend_pending']==target
        prepares = len(fixture.events('candidate_prepare'))
        for name, token, messages, explicit, expected in (
            ('foreign_subject',fixture.foreign_key,follow,None,400),
            ('different_history',key,[{'role':'user','content':'A different history'},*follow[1:]],None,400),
            ('different_declaration',key,[*history,{'role':'assistant','content':[
                {**call,'input':{'path':'other.txt'}}]},result],None,400),
            ('claimed_session',key,follow,explicit,400),
        ):
            status, _ = public_post(fixture.folder,name,port,token,messages,explicit)
            assert status==expected and len(model_calls())==1 and len(outstanding())==1, (name,status)
            if not native:
                assert len(fixture.events('candidate_prepare'))==prepares
            rejected[name] = status
        token_path = '/admin/tokens/'+str(owner)
        admin('PUT',token_path,{'allowed_accounts':'2'})
        status, _ = public_post(fixture.folder,'account_out_of_scope',port,key,follow,None)
        assert status==400 and len(model_calls())==1 and len(outstanding())==1
        rejected['account_out_of_scope'] = status
        admin('PUT',token_path,{'allowed_accounts':'1,2'})
        fixture.set_test_generation(2)
        try:
            status, _ = public_post(fixture.folder,'wrong_generation',port,key,follow,None)
            assert status==503 and len(model_calls())==1 and len(outstanding())==1
            rejected['wrong_generation'] = status
        finally:
            fixture.set_test_generation(1)

        wait_for(lambda: len(rows := outstanding())==1 and rows[0][4]==tools,
                 '错代次拒绝后原工具组尚未恢复可认领')
        # 标准 Messages 允许原来的字符串正文以等价的 text block 带回。
        normalized = [{'role':'user','content':[{'type':'text','text':history[0]['content']}]}]
        completed = public_post(fixture.folder,'continuation',port,key,[*normalized,*follow[1:]],None)
        calls = model_calls()
        assert len(calls)==2
        if native:
            assert final_text(completed)==calls[1]['marker']
            matched = calls[1]['body']['messages'][-1]['content']
            assert any(item['type']=='tool_result' and item['tool_use_id']==external_id
                       and marker in json.dumps(item['content']) for item in matched)
        else:
            assert final_text(completed)=='READ_RESULT_'+sha256(marker.encode()).hexdigest()
            first, continuation = calls
            assert first[2]==continuation[2] and fixture.acknowledged==1
        wait_for(lambda:not outstanding(),'缺省会话的旧轮未退场')
        # 只读 GET 读取后台对账的结果。此处没有后续业务请求。
        wait_for(lambda:admin('GET',account)['request_backend']==target,'空闲后台未完成切换')
        after_retirement = len(model_calls())
        assert after_retirement==2
        collided = None
        if native:
            assert switch(backend)['request_backend']==backend
            # 另一主体的两份新登记仍是歧义，首个主体的已消费摘要不能遮蔽它们。
            for index in range(2):
                assert delivered_tool(public_post(fixture.folder,f'collision_offer_{index}',port,fixture.foreign_key,history,None))==call
            proof_rows = outstanding()
            assert len(proof_rows)==2 and len({row[1] for row in proof_rows})==2
            collided, _ = public_post(fixture.folder,'collision_continuation',port,fixture.foreign_key,follow,None)
            assert collided==503 and len(model_calls())==4 and outstanding()==proof_rows
        return {'status':'passed','backend':backend,'tool_id_bytes':len(external_id),
                'offer_http':200,'continuation_http':completed[0],
                'rejections':rejected,'model_posts':after_retirement,'background_switch':target,
                'legacy_owner_zero_ignored_for_drain':native,
                'original_process_ipc_acks':fixture.acknowledged,'collision_status':collided,
                'collision_added_model_posts':len(model_calls())-4 if native else None}


def verify_idle_retirement(folder, gateway, *, hold_gates):
    """旧轮退出后暂停所有公开访问，只凭后台推进切换。@param folder 证据。@param gateway 显式构建。
    @param hold_gates 是否先让 sender 状态未知、再拒绝配置许可。@return 时序证据。
    """
    with gateway_ingress(folder,gateway,1,True,log_filter='warn,claude_code_gateway::service::tui_backend=debug') as (
            port,key,admin,fixture,_), ThreadPoolExecutor(max_workers=1) as pool:
        path = '/admin/accounts/1'
        history = [{'role':'user','content':ORIGINAL}]
        session = fixture.turn.session_id

        def persisted():
            with closing(connect(f"file:{folder/'gateway.db'}?mode=ro",uri=True)) as db:
                return db.execute('SELECT a.request_backend, i.target, i.revision FROM accounts a '
                                  'JOIN tui_backend_intents i ON a.id=i.account_id WHERE a.id=1').fetchone()

        def trace(reason, trigger=None):
            return [line for line in (folder/'gateway.log').read_text().splitlines()
                    if reason in line and (trigger is None or trigger in line)]

        initial = persisted()
        offered = delivered_tool(public_post(folder,'old_offer',port,key,history,session))
        pending = admin('PUT',path,{'request_backend':'native293','request_backend_revision':initial[2]})
        assert pending['request_backend']=='tui_v2' and pending['request_backend_pending']=='native293'
        staged = persisted()
        marker = 'RETIRE_ONLY_' + uuid4().hex
        follow = [*history,{'role':'assistant','content':[offered]}, {'role':'user','content':[
            {'type':'tool_result','tool_use_id':offered['id'],'content':marker}]}]
        checks = {}
        try:
            result = pool.submit(public_post,folder,'old_continuation',port,key,follow,session)
            wait_for(lambda:fixture.store.read(fixture.turn,offered['id']).state=='received',
                     '旧轮未收到工具结果')
            fixture.continuation_gate.set()
            wait_for(lambda:fixture.events('original_waiting_to_reply'),'旧响应尚未到达退场边界')
            assert fixture.processes[0].poll() is not None and persisted()==staged
            assert not result.done()
            previous_attempts = len(trace('tui_reconcile_attempt','response_retired'))
            previous_quiesces = len(fixture.events('orchestrator_quiesce'))
            if hold_gates:
                fixture.status_known = False
                fixture.quiesce_allowed = False
            else:
                # 让一次周期检查在旧响应仍占槽时结束，给退场通知留出独立窗口。
                periodic_probes = len(trace('tui_reconcile_attempt','periodic'))
                wait_for(lambda:len(trace('tui_reconcile_attempt','periodic'))>periodic_probes,
                         '旧响应仍在途时未观察到周期对账')
                assert persisted()==staged and not result.done()
            fixture.response_gate.set()
            assert final_text(result.result(timeout=10))=='READ_RESULT_'+sha256(marker.encode()).hexdigest()
            exit_seen = monotonic_ns()

            if hold_gates:
                wait_for(lambda:len(trace('tui_reconcile_attempt','response_retired'))==previous_attempts+1,
                         '旧响应退场未定向唤醒账号对账')
                wait_for(lambda:len(fixture.events('candidate_status_report',idle=None))>=2,
                         'sender 状态未知后未补查')
                assert persisted()==staged and len(fixture.events('orchestrator_quiesce'))==previous_quiesces
                checks['unknown_sender_kept_pending'] = True
                fixture.status_known = True
                wait_for(lambda:fixture.events('orchestrator_quiesce',idle=True,admitted=False),
                         'sender 空闲后未尝试现有配置门禁')
                assert persisted()==staged
                checks['idle_with_denied_config_kept_pending'] = True
                fixture.quiesce_allowed = True

            wait_for(lambda:persisted()[:2]==('native293',''),'无新流量时后台未完成切换')
            observed_ms = (monotonic_ns()-exit_seen)/1_000_000
            applied = persisted()
            assert applied[2]==staged[2]+1
            entry, = wait_for(lambda:trace('tui_reconcile_applied'),'缺少应用切换的后台记录')
            trigger = 'response_retired' if 'response_retired' in entry else 'periodic'
            assert [row['name'] for row in (json.loads(line) for line in (folder/'client.jsonl').read_text().splitlines())
                    if row['event']=='client_post']==['old_offer','old_continuation']
            assert len(fixture.model_snapshot())==2 and fixture.acknowledged==1
            # 首次普通管理读取在只读库已确认生效之后，必须保持原修订。
            visible = admin('GET',path)
            listed, = admin('GET','/admin/accounts')['data']
            assert visible['request_backend']==listed['request_backend']=='native293'
            assert visible['request_backend_pending'] is listed['request_backend_pending'] is None
            assert visible['request_backend_revision']==listed['request_backend_revision']==applied[2]
            assert persisted()==applied
            return {**checks,'data_plane_posts_after_exit':0,'mode_seen_before_get':'native293',
                    'revision_before_get':applied[2],'milliseconds_to_sql_observation':round(observed_ms,1),
                    'direct_retirement_checks':len(trace('tui_reconcile_attempt','response_retired'))-previous_attempts,
                    'applied_by':trigger}
        finally:
            fixture.status_known = True
            fixture.quiesce_allowed = True
            fixture.continuation_gate.set()
            fixture.response_gate.set()


def main():
    """在只回环网路内执行。@return 进程状态。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--gateway',required=True,type=Path)
    parser.add_argument('--v1-probe-dir',type=Path)
    parser.add_argument('--native-sender',type=Path)
    parser.add_argument('--native-kernel',type=Path)
    parser.add_argument('--cancel-prepared',action='store_true',help='在新轮已准备且等待普通槽时撤销切换')
    parser.add_argument('--v1-to-v2',action='store_true',help='用真实 V1 工具续轮验收切向 V2')
    parser.add_argument('--idle-retirement',action='store_true',help='验证没有新请求时的旧轮退场对账')
    parser.add_argument('--sessionless',action='store_true',help='验证缺省会话的 V1/V2 工具归属和碰撞')
    parser.add_argument('--isolated',action='store_true',help=argparse.SUPPRESS)
    args = parser.parse_args()
    files = ('gateway','v1_probe_dir','native_sender','native_kernel')
    if len([name for name in files if getattr(args,name) is not None]) not in (1,4):
        parser.error('实测 V1 须同时传入原探针目录、sender 和 native293 入口')
    if args.v1_to_v2 and (args.native_kernel is None or args.cancel_prepared):
        parser.error('V1→V2 验收需要真实 V1 制品且独立运行')
    if args.idle_retirement and (args.v1_to_v2 or args.cancel_prepared):
        parser.error('无新请求的验收须独立运行')
    if args.sessionless and (args.native_kernel is None or args.v1_to_v2 or args.cancel_prepared or args.idle_retirement):
        parser.error('缺省会话验收需要真实 V1 制品且独立运行')
    for name in files:
        if getattr(args,name) is not None:
            setattr(args,name,getattr(args,name).resolve(strict=True))
    if not args.isolated:
        command = [sys.executable,str(SCRIPT),'--isolated']
        for name in files:
            if getattr(args,name) is not None:
                command.extend(('--'+name.replace('_','-'),str(getattr(args,name))))
        if args.cancel_prepared:
            command.append('--cancel-prepared')
        if args.v1_to_v2:
            command.append('--v1-to-v2')
        if args.idle_retirement:
            command.append('--idle-retirement')
        if args.sessionless:
            command.append('--sessionless')
        return run(['unshare','--net','--','/bin/bash','-c','ip link set lo up && exec "$@"','tui-switch',
                    *command],env=CLEAN_ENV,check=False).returncode
    assert [row['ifname'] for row in json.loads(check_output(['ip','-j','link']))]==['lo']
    assert json.loads(check_output(['ip','-j','route']))==[]
    sys.path.insert(0,str(ROOT/'services/orchestrator'))
    root = Path(mkdtemp(prefix='flower2api-tui-account-switch-'))
    print('证据目录',root,flush=True)
    try:
        if args.sessionless:
            result = {'status':'passed','v2':verify_sessionless(root/'v2',args,native=False),
                      'v1':verify_sessionless(root/'v1',args,native=True)}
        elif args.idle_retirement:
            result = {'status':'passed',
                      'direct':verify_idle_retirement(root/'direct',args.gateway,hold_gates=False),
                      'held_gates':verify_idle_retirement(root/'held-gates',args.gateway,hold_gates=True)}
        else:
            result = verify_native_origin(root,args) if args.v1_to_v2 else verify(root,args)
    except Exception as error:
        write_json(root/'results.json',{'status':'failed','error':repr(error)})
        raise
    write_json(root/'results.json',result)
    return int(result['status']!='passed')


if __name__=='__main__':
    raise SystemExit(main())
