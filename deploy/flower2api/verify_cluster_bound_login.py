"""真实SSH节点绑定登录验证，Gateway租约和发布快照在此使用显式合成输入。"""
from __future__ import annotations

import json
import os
import select
import sqlite3
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
from uuid import uuid4

from fastapi.testclient import TestClient

import main
from credential_ownership import CredentialOwnership
from cluster_bound_login_runner import ClusterBoundAccountLogins
from cluster_deployment import node_container_name
from cluster_credential_refresh import RemoteCredentialRefresh
from cluster_bound_login_contract import BoundLoginIdentity, BoundLoginPublish, BoundLoginStart, BoundLoginWork
from cluster_continue_runner import RemoteContinuePty
from cluster_execution_grants import ExecutionGrant, ExecutionLeaseProof, ExecutionScope
from cluster_execution_store import NodeExecutions
from cluster_login_contract import AccountLoginAccept, AccountLoginCode
from cluster_terminal_sessions import TerminalSessions
from cluster_owner_runner import RemoteOwnerTransitions
from runtime_files import atomic_json


def verify_product_bound_login(testcase,service,runtime,node,account,gateway,root) -> None:
    """原管理HTTP/WS、实际SSH、Rust导入与原Owner完整重授权及响应未知恢复。

    :param testcase: 本次随机隔离部署。
    :param service: 中央受信节点服务。
    :param runtime: 原中央环境登记。
    :param node: 原所属SSH节点。
    :param account: 合成绑定账号。
    :param gateway: 实际Rust管理客户端。
    :param root: 本次Node实际环境根。
    :return: None；新授权由离线CLI夹具生成，全部HTTP只访问隔离部署。
    """
    if os.environ.get('CLUSTER_DOCKER_TEST')!='1' or not runtime.deployment.startswith('cluster-test-'):
        raise ValueError('绑定产品验证仅用于本次隔离部署')
    manually_disabled=os.environ.get('CLUSTER_TEST_BOUND_LOGIN_DISABLED')=='1'
    if manually_disabled:
        gateway._request('PUT',f"/admin/accounts/{account['cc2api_account_id']}",{'status':'disabled'})
        with service.store.database() as connection:
            connection.execute('UPDATE accounts SET enabled=0 WHERE id=?',(account['id'],))
    current=gateway._request('GET',f"/admin/accounts/{account['cc2api_account_id']}")
    # 仅初始化本次合成账号的统一设备；重授权开始后核对这一原设备保持。
    device=current['device_id']
    for location in (service.data/'profiles'/account['name'],root/'home',root.parents[1]/'profiles'/account['name']):
        top=json.loads((location/'.claude.json').read_text())
        top['userID']=device
        top['oauthAccount']['emailAddress']=current['email']
        atomic_json(location/'.claude.json',top)
        os.chown(location/'.claude.json',1000,1000)
    prefix=root/'cli/2.1.293'
    program=prefix/'node_modules/.bin/claude'
    program.parent.mkdir(parents=True,exist_ok=True)
    source=(Path(__file__).parent/'fixtures/mock_cli.py').read_text()
    program.write_text(source.replace('9.9.9 (Synthetic lifecycle fixture)','2.1.293 (Synthetic lifecycle fixture)'))
    program.chmod(0o755)
    (prefix/'.ready').touch()
    for directory in (prefix,prefix/'node_modules',program.parent):
        directory.chmod(0o755)
    control=root/'home/.synthetic-login.json'
    atomic_json(control,{'wait_for_code':True,'access_token':'synthetic-bound-authorized-access',
        'refresh_token':'synthetic-bound-authorized-refresh','account_uuid':current['account_uuid'],
        'organization_uuid':current['organization_uuid'],'email':current['email']})
    os.chown(control,1000,1000)
    sessions=TerminalSessions(NodeExecutions(service.store,runtime.release_id),service,runtime,gateway,
        Mock(side_effect=AssertionError('绑定登录不得认领模型额度')),Mock())
    testcase.addCleanup(sessions.close)
    callbacks=Mock(side_effect=AssertionError('本次SSH重授权不得读取中央HOME或交换本地RT'))
    ownership=CredentialOwnership(runtime,gateway,service.store.database,service.store.lock,
        read_profile=main._read_bench_profile_identity,mirror=main._sync_cc2api_credentials_to_profile,
        mirror_locked=main._sync_cc2api_credentials_to_profile_locked,profile_lock=main._profile_lock,
        identity=callbacks,read_identity=callbacks,validate=callbacks,find=callbacks,idle=callbacks,available=callbacks,
        creation_payload=callbacks,refresh=callbacks,read_bound_identity=main._read_remote_bound_identity,
        reauth_idle=main._remote_reauth_idle,reauth_publish=main._remote_reauth_publish)
    credentials=RemoteCredentialRefresh(sessions,ownership,main._oauth_owner_lock,lambda account:'synthetic-quota',lambda account:'2.1.293')
    testcase.addCleanup(credentials.close)
    logins=ClusterBoundAccountLogins(sessions,credentials,main._oauth_owner_lock,
        main._save_remote_bound_login_authorization,main._remote_login_admission)
    testcase.addCleanup(logins.close)
    manager=main.LoginManager(Mock())
    owners=RemoteOwnerTransitions(sessions,ownership,main._read_bench_profile_identity)
    with service.store.database() as connection:
        account_before=dict(connection.execute('SELECT * FROM accounts WHERE id=?',(account['id'],)).fetchone())
        connection.execute('INSERT INTO account_quota_states(account_id,identity,state_json,updated_at) VALUES(?,?,?,1)',
            (account['id'],'synthetic-bound-keep','{"blocked":true}'))
    with patch.multiple(main,account_runtime=runtime,cluster_service=service,cluster_terminal_sessions=sessions,cc2api_client=gateway,
            cluster_runner=SimpleNamespace(credentials=credentials,owners=owners,project_io=None),cluster_logins=None,cluster_bound_logins=logins,
            login_manager=manager,credential_ownership=ownership,continue_manager=None,pi_owners=None,get_db=service.store.database,
            _db_lock=service.store.lock,BENCH_DATA=service.data,PROFILES_DIR=service.data/'profiles',V3_ENABLED=True,
            WEBUI_USER='synthetic-admin',WEBUI_PASS='synthetic-password',
            _resolve_account_cli_version=lambda account,version=None:(version or '2.1.293','fixture')):
        client=TestClient(main.app,headers={'Authorization':'Bearer '+os.environ['V3_INTERNAL_TOKEN']})
        testcase.addCleanup(client.close)
        response=client.post('/api/accounts/login/start',json={'name':account['name'],'force_reauth':True})
        testcase.assertEqual(200,response.status_code,response.text)
        sid=response.json()['session_id']
        operation=manager.get(sid).remote_operation
        testcase.assertEqual(account['cc2api_account_id'],response.json()['cc2api_account_id'])
        deadline=time.monotonic()+90
        while True:
            response=client.get('/api/accounts/login/'+sid+'/status')
            if response.status_code!=200:
                row=sessions.ledger.get(operation)
                scope=row['record']['scope']
                try:
                    receipt=sessions._call(row,'account-bound-login-get',scope)
                    detail=json.dumps(receipt,ensure_ascii=False)
                    try:
                        sessions._call(row,'account-bound-login-observe',scope)
                    except Exception as error:
                        detail+='；观察失败：'+str(error)
                except Exception as error:
                    detail='原节点回执读取失败：'+str(error)
                testcase.fail('原管理状态失败：'+response.text+'；'+detail)
            if response.json().get('authorization_url'):
                break
            testcase.assertLess(time.monotonic(),deadline,'原绑定产品登录准备超时')
            time.sleep(.2)
        client.cookies.set(main._SESSION_COOKIE,main._make_session_token(main.WEBUI_USER),path='/')
        path='/api/accounts/login/ws/'+sid
        ticket=client.post('/api/terminal-ticket',json={'path':path})
        testcase.assertEqual(200,ticket.status_code,ticket.text)
        with client.websocket_connect(path+'?ticket='+ticket.json()['ticket']) as websocket:
            websocket.send_json({'type':'ping'})
            while True:
                message=websocket.receive()
                if message.get('text') and json.loads(message['text']).get('type')=='pong':
                    break
                testcase.assertEqual('websocket.send',message['type'],message)
            websocket.send_json({'type':'resize','rows':30,'cols':100})
            websocket.send_json({'type':'input','data':'synthetic-invalid-code\r'})
            deadline=time.monotonic()+15
            while not (root/'home/.synthetic-code-count.json').exists():
                testcase.assertLess(time.monotonic(),deadline,'原绑定PTY输入尚未到达CLI')
                time.sleep(.1)
        code={'request_id':uuid4().hex,'code':'synthetic-code'}
        delivered=client.post('/api/accounts/login/'+sid+'/code',json=code)
        testcase.assertEqual(200,delivered.status_code,delivered.text)
        testcase.assertEqual('delivered',delivered.json()['status'])
        testcase.assertEqual(delivered.json(),client.post('/api/accounts/login/'+sid+'/code',json=code).json())
        testcase.assertEqual(delivered.json(),client.get('/api/accounts/login/'+sid+'/code/'+code['request_id']).json())
        deadline=time.monotonic()+15
        while not client.get('/api/accounts/login/'+sid+'/status').json().get('credentials_ready'):
            testcase.assertLess(time.monotonic(),deadline,'原绑定CLI认证检查尚未通过')
            time.sleep(.1)
        testcase.assertEqual(2,json.loads((root/'home/.synthetic-code-count.json').read_text())['count'])
        imported=gateway.import_credentials
        def lose_import(remote_id,payload):
            """原真实Rust已持久导入后丢响应，后续只能查同一回执。:return: 抛出合成断连。"""
            imported(remote_id,payload)
            raise ConnectionError('合成Rust实际导入响应丢失')
        with patch.object(gateway,'import_credentials',side_effect=lose_import) as importing:
            response=client.post('/api/accounts/login/'+sid+'/commit',json={'name':account['name']})
        testcase.assertEqual(503,response.status_code,response.text)
        testcase.assertEqual(1,importing.call_count)
        testcase.assertEqual('reauth',ownership.state(account['id'])['phase'])
        testcase.assertEqual('synthetic-bound-authorized-refresh',gateway.import_status(account['cc2api_account_id'],operation)['refresh_token'])
        call=sessions._call
        def lose_accept(row,action,payload):
            """原Node实际停止与清理后丢响应，中央继续保留原长期门禁。:return: 其它原SSH结果。"""
            result=call(row,action,payload)
            if action=='account-bound-login-accept':
                raise ConnectionError('合成Node实际清理响应丢失')
            return result
        with patch.object(sessions,'_call',side_effect=lose_accept):
            response=client.post('/api/accounts/login/'+sid+'/commit',json={'name':account['name']})
        testcase.assertEqual(503,response.status_code,response.text)
        testcase.assertFalse((root/'runtime/execution.json').exists())
        testcase.assertFalse((root/'home/.v3-login'/sid).exists())
        logins.close()
        restored=ClusterBoundAccountLogins(sessions,credentials,main._oauth_owner_lock,
            main._save_remote_bound_login_authorization,main._remote_login_admission)
        testcase.addCleanup(restored.close)
        with patch.object(main,'cluster_bound_logins',restored),patch.object(main,'login_manager',main.LoginManager(Mock())):
            restored.recover_pending()
            response=client.post('/api/accounts/login/'+sid+'/commit',json={'name':account['name']})
            testcase.assertEqual(200,response.status_code,response.text)
            testcase.assertEqual(account['cc2api_account_id'],response.json()['cc2api_account_id'])
            testcase.assertEqual('committed',client.get('/api/accounts/login/'+sid+'/status').json()['phase'])
            before_cancel=gateway.import_status(account['cc2api_account_id'],operation)
            cancelled=json.loads(control.read_text())
            cancelled.update(access_token='synthetic-bound-cancelled-access',refresh_token='synthetic-bound-cancelled-refresh')
            atomic_json(control,cancelled)
            os.chown(control,1000,1000)
            response=client.post('/api/accounts/login/start',json={'name':account['name'],'force_reauth':True})
            testcase.assertEqual(200,response.status_code,response.text)
            cancel_sid=response.json()['session_id']
            cancel_operation=main.login_manager.get(cancel_sid).remote_operation
            deadline=time.monotonic()+90
            while True:
                response=client.get('/api/accounts/login/'+cancel_sid+'/status')
                testcase.assertEqual(200,response.status_code,response.text)
                if response.json().get('authorization_url'):
                    break
                testcase.assertLess(time.monotonic(),deadline,'原绑定取消场景准备超时')
                time.sleep(.2)
            code={'request_id':uuid4().hex,'code':'synthetic-code'}
            delivered=client.post('/api/accounts/login/'+cancel_sid+'/code',json=code)
            testcase.assertEqual(200,delivered.status_code,delivered.text)
            testcase.assertEqual('delivered',delivered.json()['status'])
            deadline=time.monotonic()+15
            while not client.get('/api/accounts/login/'+cancel_sid+'/status').json().get('credentials_ready'):
                testcase.assertLess(time.monotonic(),deadline,'原绑定取消场景认证检查超时')
                time.sleep(.1)
            row,request=restored._row(cancel_operation)
            frozen=restored._call(row,'commit',request.scope.model_dump())
            testcase.assertEqual('frozen',frozen['commit']['stage'])
            testcase.assertIsNone(gateway.import_status(account['cc2api_account_id'],cancel_operation))
            response=client.delete('/api/accounts/login/'+cancel_sid)
            testcase.assertEqual(200,response.status_code,response.text)
            cancelled=sessions.ledger.get(cancel_operation)
            testcase.assertEqual('closed',cancelled['phase'])
            testcase.assertTrue(cancelled['record']['node_receipt']['commit']['aborted'])
            testcase.assertFalse(cancelled['record']['node_receipt']['commit']['cleanup_pending'])
            testcase.assertFalse((root/'runtime/execution.json').exists())
            testcase.assertFalse((root/'home/.v3-login'/cancel_sid).exists())
            testcase.assertEqual(404,client.get('/api/accounts/login/'+cancel_sid+'/status').status_code)
            current_after_cancel=gateway._request('GET',f"/admin/accounts/{account['cc2api_account_id']}")
            for key in ('access_token','refresh_token','expires_at'):
                testcase.assertEqual(before_cancel[key],current_after_cancel[key])
        testcase.assertEqual([],sessions.ledger.pending())
        testcase.assertEqual({},sessions.activities)
        testcase.assertEqual('ready',ownership.state(account['id'])['phase'])
        testcase.assertEqual([],gateway._request('GET',f"/admin/runtime/accounts/{account['cc2api_account_id']}/lease")['holders'])
        testcase.assertEqual('ready',gateway._request('GET',f"/admin/accounts/{account['cc2api_account_id']}/oauth-ownership")['ownership']['phase'])
        if manually_disabled:
            testcase.assertEqual(current['status'],gateway._request('GET',f"/admin/accounts/{account['cc2api_account_id']}")['status'])
        for path in (root/'home/.claude/.credentials.json',root.parents[1]/'profiles'/account['name']/'.credentials.json',
                root/'runtime/access/.credentials.json',root/'runtime/network/access/.credentials.json'):
            oauth=json.loads(path.read_text())['claudeAiOauth']
            testcase.assertEqual('synthetic-bound-authorized-access',oauth['accessToken'])
            testcase.assertNotIn('refreshToken',oauth)
        testcase.assertEqual(device,json.loads((root/'home/.claude.json').read_text())['userID'])
        testcase.assertEqual('synthetic-bound-authorized-refresh',json.loads((main.PROFILES_DIR/account['name']/'.credentials.json').read_text())['claudeAiOauth']['refreshToken'])
        with service.store.database() as connection:
            testcase.assertEqual(account_before,dict(connection.execute('SELECT * FROM accounts WHERE id=?',(account['id'],)).fetchone()))
            testcase.assertEqual(1,connection.execute('SELECT count(*) FROM account_quota_states WHERE account_id=?',(account['id'],)).fetchone()[0])
            testcase.assertEqual(0,connection.execute('SELECT count(*) FROM local_credential_authorizations').fetchone()[0])
        if os.environ.get('CLUSTER_TEST_OWNER_API')=='1':
            if not manually_disabled:
                process=client.post(f"/api/accounts/{account['id']}/cc2api/process")
                testcase.assertEqual(200,process.status_code,process.text+'；Node位置：'+runtime.client.containers.get(node_container_name(runtime.deployment,node['node_key'])).logs(tail=8).decode(errors='replace'))
                testcase.assertEqual(account['cc2api_account_id'],process.json()['cc2api_account_id'])
                testcase.assertIn('canonical_process',process.json())
            ownership.transition=main._account_owner_transition
            ownership.sync_bound=main._sync_owner_credentials
            ownership.matched_identity=main._v3_matched_cli_identity
            ownership.identity=main._v3_cli_identity
            ownership.read_identity=main._v3_cli_identity_readonly
            ownership.read_material=main._read_current_owner_material
            ownership.idle=main._require_oauth_owner_transition_idle
            ownership.validate=main._validate_cc2api_identity
            ownership.available=main._require_cc2api_binding_available
            credentials.identity=main._quota_identity
            peer=service.connection(node['id'])
            actual=peer.execution_environment
            fault={'operation':'credential-owner-prepare'}
            def execution(container,payload,operation):
                """真实Node处理之后丢一次指定回包。:return: 原真实SSH结果。"""
                try:
                    result=actual(container,payload,operation)
                except ValueError as error:
                    if operation.startswith('credential-owner-'):
                        details=runtime.client.containers.get(container).logs(tail=6).decode(errors='replace')
                        raise AssertionError('原Node交接诊断：'+details) from error
                    raise
                if operation==fault['operation']:
                    fault['operation']=None
                    raise ConnectionError('合成原凭据交接响应丢失')
                return result
            url=f"/api/accounts/{account['id']}/cc2api-binding"
            with patch.object(peer,'execution_environment',side_effect=execution):
                response=client.delete(url)
                testcase.assertEqual(503,response.status_code,response.text)
                fault['operation']='credential-owner-publish'
                response=client.delete(url)
                testcase.assertEqual(503,response.status_code,response.text)
                response=client.delete(url)
                testcase.assertEqual(200,response.status_code,response.text)
            oauth_path=root/'home/.claude/.credentials.json'
            document=json.loads(oauth_path.read_text())
            testcase.assertEqual('synthetic-bound-authorized-refresh',document['claudeAiOauth']['refreshToken'])
            document['claudeAiOauth'].update(accessToken='synthetic-owner-rotated-at',refreshToken='synthetic-owner-rotated-rt')
            atomic_json(oauth_path,document)
            os.chown(oauth_path,1000,1000)
            response=client.post(f"/api/accounts/{account['id']}/cc2api/bind",json={'cc2api_account_id':account['cc2api_account_id']})
            testcase.assertEqual(200,response.status_code,response.text)
            testcase.assertEqual('synthetic-owner-rotated-rt',gateway._request('GET',f"/admin/accounts/{account['cc2api_account_id']}")['refresh_token'])
            testcase.assertNotIn('refreshToken',json.loads(oauth_path.read_text())['claudeAiOauth'])
            response=client.delete(f"/api/accounts/{account['id']}")
            testcase.assertEqual(200,response.status_code,response.text)
            testcase.assertTrue(response.json()['deleted'])
            testcase.assertTrue(root.exists())
            with service.store.database() as connection:
                cursor=connection.execute("INSERT INTO accounts(name,profile_path) VALUES('synthetic_unprepared','profiles/synthetic_unprepared')")
                initial=dict(connection.execute('SELECT * FROM accounts WHERE id=?',(cursor.lastrowid,)).fetchone())
            service.assign_initial(initial,runtime,node['id'],1)
            initial_row=runtime._row(initial['name'],initial['id'])
            response=client.delete(f"/api/accounts/{initial['id']}")
            testcase.assertEqual(200,response.status_code,response.text)
            with sqlite3.connect(root.parents[1]/'node-execution.sqlite') as connection:
                testcase.assertEqual((None,0),connection.execute('SELECT cc2api_account_id,enabled FROM accounts WHERE id=?',(initial['id'],)).fetchone())
            testcase.assertFalse((root.parents[1]/'environments'/initial_row['environment_id']/'home').exists())


def verify_bound_node_login(testcase,service,runtime,node,account,gateway,root) -> None:
    """真实原tmux/SSH/私有WS/码、冻结RT、AT-only发布及实际停止清理。

    :param testcase: 随机隔离部署夹具。
    :param service: 原SSH节点服务。
    :param runtime: 原中央环境登记。
    :param node: 原绑定节点。
    :param account: 合成绑定账号。
    :param gateway: 原合成配置提供器；本用例不验证真实Gateway导入。
    :param root: 本次Node实际账号根。
    :return: None；真实Gateway长期门禁、导入及原中央产品消费者由后续纵向链路覆盖。
    """
    if os.environ.get('CLUSTER_DOCKER_TEST')!='1' or not runtime.deployment.startswith('cluster-test-'):
        raise ValueError('绑定Node登录验证仅用于本次隔离部署')
    prefix=root/'cli/2.1.293'
    program=prefix/'node_modules/.bin/claude'
    program.parent.mkdir(parents=True,exist_ok=True)
    source=(Path(__file__).parent/'fixtures/mock_cli.py').read_text()
    program.write_text(source.replace('9.9.9 (Synthetic lifecycle fixture)','2.1.293 (Synthetic lifecycle fixture)'))
    program.chmod(0o755)
    (prefix/'.ready').touch()
    for directory in (prefix,prefix/'node_modules',program.parent):
        directory.chmod(0o755)
    control=root/'home/.synthetic-login.json'
    atomic_json(control,{'wait_for_code':True,'access_token':'synthetic-bound-authorized-access',
        'refresh_token':'synthetic-bound-authorized-refresh','account_uuid':'synthetic-account',
        'organization_uuid':'synthetic-org','email':'synthetic@example.invalid'})
    os.chown(control,1000,1000)
    original_top=json.loads((root/'home/.claude.json').read_text())
    sessions=TerminalSessions(NodeExecutions(service.store,runtime.release_id),service,runtime,gateway,
        Mock(side_effect=AssertionError('绑定登录不应认领模型额度')),Mock())
    testcase.addCleanup(sessions.close)
    actual=runtime._row(account['name'],account['id'])
    assignment=service.store.assignment(account['id'])
    identity=BoundLoginIdentity(email='synthetic@example.invalid',account_uuid='synthetic-account',organization_uuid='synthetic-org')
    work=BoundLoginWork(id=uuid4().hex,sid=uuid4().hex[:12],account_id=account['id'],gateway_account_id=account['cc2api_account_id'],
        device_id=original_top['userID'],expected_identity=identity,version='2.1.293',expires_at=int(time.time())+1800,
        account_identity=json.dumps({'account_id':account['id'],'binding':account['cc2api_account_id'],
            'uuid':identity.account_uuid,'org':identity.organization_uuid},sort_keys=True))
    scope=ExecutionScope(operation_id=work.id,node_key=node['node_key'],account_id=account['id'],gateway_account_id=account['cc2api_account_id'],
        environment_id=actual['environment_id'],assignment_revision=assignment['revision'],generation=actual['generation'],
        source=work.source,role='login')
    request=BoundLoginStart(scope=scope,work=work)
    row=sessions.ledger.begin(scope,work)
    sessions.activities[scope.operation_id]=sessions.activity_gate.reserve('synthetic-bound-login:'+scope.source)
    sessions._save(work.id,gateway_prepare_intent=True)
    # 此用例显式提供合成中央租约，Node仍执行真实有限证明及原运行时排他认领。
    lease=ExecutionLeaseProof(owner=scope.source,generation='synthetic-bound-lease',expires_at=int(time.time())+30,exclusive=True)
    grant=ExecutionGrant(**scope.model_dump(),not_after=lease.expires_at,lease=lease)
    row=sessions._save(work.id,'claimed',lease=lease.model_dump(),grant=grant.model_dump())
    sessions._call(row,'grant-create',grant.model_dump())
    row=sessions._save(work.id,'starting')
    renew_at=time.monotonic()+5
    renew_enabled=True

    def call(operation,payload):
        """仅续接同范围的合成证明，原节点操作只提交一次。:return: 原真实SSH回执。"""
        nonlocal row,grant,lease,renew_at,renew_enabled
        if renew_enabled and time.monotonic()>=renew_at:
            lease=lease.model_copy(update={'expires_at':min(int(time.time())+30,work.expires_at)})
            grant=grant.model_copy(update={'sequence':grant.sequence+1,'not_after':lease.expires_at,'lease':lease})
            row=sessions._save(work.id,lease=lease.model_dump(),grant=grant.model_dump())
            sessions._call(row,'grant-renew',grant.model_dump())
            renew_at=time.monotonic()+5
        result=sessions._call(row,operation,payload)
        if operation=='account-bound-login-accept' and result.get('phase')=='closed':
            renew_enabled=False
        return result

    receipt=call('account-bound-login-start',request.model_dump())
    deadline=time.monotonic()+90
    while receipt['phase']=='starting':
        testcase.assertLess(time.monotonic(),deadline,'真实Node绑定登录准备超时')
        time.sleep(.1)
        receipt=call('account-bound-login-get',scope.model_dump())
    testcase.assertEqual('ready',receipt['phase'],receipt)
    row=sessions._save(work.id,'running',node_receipt=receipt)
    testcase.assertEqual(receipt,call('account-bound-login-start',request.model_dump()))
    bridge=RemoteContinuePty(SimpleNamespace(sessions=sessions),row,purpose='bound-login')
    try:
        testcase.assertTrue(select.select([bridge],[],[],5)[0])
        bridge.recv(4096)
        bridge.resize(30,100)
        data=b'synthetic-invalid-code\r'
        testcase.assertEqual(len(data),bridge.send(data))
        deadline=time.monotonic()+10
        while not (root/'home/.synthetic-code-count.json').exists():
            testcase.assertLess(time.monotonic(),deadline,'原绑定PTY输入尚未到达CLI')
            time.sleep(.1)
    finally:
        bridge.close()
    code=AccountLoginCode(scope=scope,request_id=uuid4().hex,code='synthetic-code')
    receipt=call('account-bound-login-code',code.model_dump())
    testcase.assertEqual('delivered',receipt['status'])
    testcase.assertEqual(receipt,call('account-bound-login-code',code.model_dump()))
    deadline=time.monotonic()+15
    while True:
        observed=call('account-bound-login-observe',scope.model_dump())
        if observed['credentials_ready']:
            break
        testcase.assertLess(time.monotonic(),deadline,'原绑定CLI认证检查尚未通过')
        time.sleep(.1)
    testcase.assertEqual(2,json.loads((root/'home/.synthetic-code-count.json').read_text())['count'])
    frozen=call('account-bound-login-commit',scope.model_dump())
    testcase.assertEqual('frozen',frozen['commit']['stage'])
    testcase.assertNotIn('synthetic-bound-authorized-refresh',json.dumps(frozen))
    snapshot=call('account-bound-login-snapshot',scope.model_dump())
    testcase.assertEqual('synthetic-bound-authorized-refresh',snapshot['material']['refresh_token'])
    for target in (root/'home/.claude/.credentials.json',root.parent.parent/'profiles'/account['name']/'.credentials.json'):
        if target.exists():
            testcase.assertNotIn('refreshToken',json.loads(target.read_text()).get('claudeAiOauth',{}))
    publish=BoundLoginPublish(scope=scope,authorization_sha256=frozen['commit']['authorization_sha256'],
        access_token='synthetic-gateway-current-access',expires_at=int((time.time()+3600)*1000))
    published=call('account-bound-login-publish',publish.model_dump())
    testcase.assertEqual('saved',published['commit']['stage'])
    testcase.assertNotIn(publish.access_token,json.dumps(published))
    accepted=AccountLoginAccept(scope=scope,authorization_sha256=publish.authorization_sha256)
    closed=call('account-bound-login-accept',accepted.model_dump())
    testcase.assertEqual('closed',closed['phase'])
    testcase.assertFalse(closed['commit']['cleanup_pending'])
    testcase.assertEqual(closed,call('account-bound-login-accept',accepted.model_dump()))
    testcase.assertFalse((root/'runtime/execution.json').exists())
    testcase.assertFalse((root/'home/.v3-login'/work.sid).exists())
    testcase.assertFalse((root.parent.parent/'node-bound-logins'/scope.environment_id/work.id/'authorization').exists())
    for target in (root/'home/.claude/.credentials.json',root.parent.parent/'profiles'/account['name']/'.credentials.json',
            root/'runtime/access/.credentials.json',root/'runtime/network/access/.credentials.json'):
        oauth=json.loads(target.read_text())['claudeAiOauth']
        testcase.assertEqual(publish.access_token,oauth['accessToken'])
        testcase.assertNotIn('refreshToken',oauth)
    testcase.assertEqual(original_top['userID'],json.loads((root/'home/.claude.json').read_text())['userID'])
    sessions._save(work.id,'stopping',node_receipt=closed)
    sessions._save(work.id,'closed',lease_released={'owner':lease.owner,'generation':lease.generation,'released':True})
    sessions._release_activity(work.id)
    testcase.assertEqual([],sessions.ledger.pending())
    testcase.assertEqual({},sessions.activities)
