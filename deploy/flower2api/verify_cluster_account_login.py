"""隔离真实SSH验证Node与原中央产品入口的明确重授权。"""
from __future__ import annotations

import json
import os
import time
from types import SimpleNamespace
from unittest.mock import Mock, patch
from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient
import main

from cluster_execution_grants import ExecutionGrant, ExecutionScope
from cluster_login_contract import AccountLoginAccept, AccountLoginCode, AccountLoginStart, AccountLoginWork
from cluster_login_runner import ClusterAccountLogins
from runtime_files import atomic_json


def verify_node_account_login(testcase, runtime, account, coordinator, sessions, root) -> None:
    """真实原tmux、隐藏码输入、CLI认证检查、冻结提交及严格释放。

    :param testcase: 当前随机部署夹具。
    :param runtime: 原中央环境登记。
    :param account: 本次合成独立账号。
    :param coordinator: 原有限证明续接器。
    :param sessions: 原中央执行账本及SSH通道。
    :param root: 本次实际Node环境根。
    :return: None；本用例不调用生产OAuth授权交换或模型。
    """
    if os.environ.get('CLUSTER_DOCKER_TEST')!='1' or not runtime.deployment.startswith('cluster-test-'):
        raise ValueError('Node登录验证仅用于本次隔离部署')
    actual=runtime._row(account['name'],account['id'])
    prefix=root/'cli/2.1.303'
    program=prefix/'node_modules/.bin/claude'
    source=(Path(__file__).parent/'fixtures/mock_cli.py').read_text()
    program.write_text(source.replace('9.9.9 (Synthetic lifecycle fixture)','2.1.303 (Synthetic lifecycle fixture)'))
    program.chmod(0o755)
    control=root/'home/.synthetic-login.json'
    atomic_json(control,{'wait_for_code':True,'access_token':'synthetic-node-authorized-access',
        'refresh_token':'synthetic-node-authorized-refresh','account_uuid':'synthetic-account',
        'organization_uuid':'synthetic-org','email':'synthetic@example.invalid'})
    os.chown(control,1000,1000)
    previous=(root/'home/.claude/.credentials.json').read_bytes()
    top=json.loads((root/'home/.claude.json').read_text())
    identity=json.dumps({'account_id':account['id'],'binding':None,'uuid':top['oauthAccount']['accountUuid'],
        'org':top['oauthAccount'].get('organizationUuid')},sort_keys=True)
    assignment=sessions.service.store.assignment(account['id'])
    work=AccountLoginWork(id=uuid4().hex,sid=uuid4().hex[:12],account_id=account['id'],
        account_identity=identity,version='2.1.303',expires_at=int(time.time())+1800)
    scope=ExecutionScope(operation_id=work.id,node_key=assignment['node_key'],account_id=account['id'],
        environment_id=actual['environment_id'],assignment_revision=assignment['revision'],generation=actual['generation'],
        source=work.source,role='login')
    request=AccountLoginStart(scope=scope,work=work)
    row=sessions.ledger.begin(scope,work,require_new=True)
    activity=sessions.activity_gate.reserve('remote-login-test:'+scope.source)
    sessions.activities[scope.operation_id]=activity
    grant=ExecutionGrant(**scope.model_dump(),not_after=int(time.time())+30)
    row=sessions._save(scope.operation_id,'claimed',local_admission_intent=True,grant=grant.model_dump())
    sessions._call(row,'grant-create',grant.model_dump())
    row=sessions._save(scope.operation_id,'starting')
    renew_at=time.monotonic()+5
    renew_enabled=True

    def call(operation,payload):
        """原范围内续接有限证明并调用一次具体操作。:return: 原固定回执。"""
        nonlocal row,renew_at,renew_enabled
        if renew_enabled and time.monotonic()>=renew_at:
            row=coordinator._renew(row)
            renew_at=time.monotonic()+5
        result=sessions._call(row,operation,payload)
        if operation=='account-login-accept' and result.get('phase')=='closed':
            renew_enabled=False
        return result

    receipt=call('account-login-start',request.model_dump())
    deadline=time.monotonic()+90
    while receipt['phase']=='starting':
        testcase.assertLess(time.monotonic(),deadline,'原Node登录准备超时')
        time.sleep(.1)
        receipt=call('account-login-get',scope.model_dump())
    testcase.assertEqual('ready',receipt['phase'],receipt)
    row=sessions._save(scope.operation_id,'running',node_receipt=receipt)
    testcase.assertEqual(receipt,call('account-login-start',request.model_dump()))
    observed=call('account-login-observe',scope.model_dump())
    deadline=time.monotonic()+15
    while not observed['authorization_url']:
        testcase.assertLess(time.monotonic(),deadline,'原真实tmux授权链接尚未出现')
        time.sleep(.1)
        observed=call('account-login-observe',scope.model_dump())
    testcase.assertEqual('authorizing',observed['phase'])
    testcase.assertFalse(observed['credentials_ready'])
    testcase.assertEqual(previous,(root/'home/.claude/.credentials.json').read_bytes())
    code=AccountLoginCode(scope=scope,request_id=uuid4().hex,code='synthetic-code')
    delivered=call('account-login-code',code.model_dump())
    testcase.assertEqual('delivered',delivered['status'])
    testcase.assertEqual(delivered,call('account-login-code',code.model_dump()))
    deadline=time.monotonic()+15
    while True:
        observed=call('account-login-observe',scope.model_dump())
        if observed['credentials_ready']:
            break
        testcase.assertLess(time.monotonic(),deadline,'原CLI认证检查尚未通过')
        time.sleep(.1)
    testcase.assertEqual(1,json.loads((root/'home/.synthetic-code-count.json').read_text())['count'])
    testcase.assertEqual(previous,(root/'home/.claude/.credentials.json').read_bytes())
    committed=call('account-login-commit',scope.model_dump())
    testcase.assertEqual('saved',committed['commit']['stage'])
    testcase.assertEqual(committed,call('account-login-commit',scope.model_dump()))
    testcase.assertNotIn('synthetic-node-authorized-access',json.dumps(committed))
    testcase.assertNotIn('synthetic-node-authorized-refresh',json.dumps(committed))
    snapshot=call('account-login-snapshot',scope.model_dump())
    testcase.assertEqual('synthetic-node-authorized-refresh',snapshot['material']['refresh_token'])
    testcase.assertEqual(top['userID'],snapshot['identity']['user_id'])
    accepted=AccountLoginAccept(scope=scope,authorization_sha256=committed['commit']['authorization_sha256'])
    closed=call('account-login-accept',accepted.model_dump())
    testcase.assertEqual('closed',closed['phase'])
    testcase.assertFalse(closed['commit']['cleanup_pending'])
    testcase.assertEqual(closed,call('account-login-accept',accepted.model_dump()))
    staged=root/'home/.v3-login'/work.sid
    testcase.assertFalse(staged.exists())
    testcase.assertFalse((root.parent.parent/'node-logins'/scope.environment_id/scope.operation_id/'authorization').exists())
    current=json.loads((root/'home/.claude/.credentials.json').read_text())
    testcase.assertEqual('synthetic-node-authorized-refresh',current['claudeAiOauth']['refreshToken'])
    testcase.assertEqual(top['userID'],json.loads((root/'home/.claude.json').read_text())['userID'])
    testcase.assertFalse((root/'runtime/execution.json').exists())
    sessions._save(scope.operation_id,'stopping',node_receipt=closed)
    sessions._save(scope.operation_id,'closed',local_admission_released=True)
    sessions._release_activity(scope.operation_id)
    testcase.assertEqual([],sessions.ledger.pending())
    testcase.assertEqual({},sessions.activities)


def verify_product_account_login(testcase,runtime,account,coordinator,sessions,root,upstream_root,ownership,owner_lock) -> None:
    """原HTTP/WS经真实SSH完成未知RT后的新授权及中央接受响应丢失恢复。

    :param testcase: 随机隔离部署夹具。
    :param runtime: 原中央账号运行时。
    :param account: 本次合成独立账号。
    :param coordinator: 原具体凭据协调器。
    :param sessions: 原中央执行账本。
    :param root: 原Node账号环境。
    :param upstream_root: 本次本地TLS上游及证据。
    :param ownership: 原持久凭据所有者。
    :param owner_lock: 原不可重入账号锁。
    :return: None；合成CLI仅验证实际生命周期，授权产物由离线夹具生成。
    """
    if os.environ.get('CLUSTER_DOCKER_TEST')!='1' or not runtime.deployment.startswith('cluster-test-'):
        raise ValueError('产品登录验证仅用于本次隔离部署')
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
    atomic_json(control,{'wait_for_code':True,'access_token':'synthetic-node-authorized-access',
        'refresh_token':'synthetic-node-authorized-refresh','account_uuid':'synthetic-account',
        'organization_uuid':'synthetic-org','email':'synthetic@example.invalid'})
    os.chown(control,1000,1000)
    previous=(root/'home/.claude/.credentials.json').read_bytes()
    top=json.loads((root/'home/.claude.json').read_text())
    retired=os.environ.get('CLUSTER_TEST_CREDENTIAL_LOGIN_RETIRED')=='1'
    inactive=retired or os.environ.get('CLUSTER_TEST_CREDENTIAL_LOGIN_INACTIVE')=='1'
    parent=None
    if retired:
        # 本分支从原已归还本地的合成退休状态开始，实际新授权与解除退休使用原Owner。
        record=ownership.state(account['id'])
        record['retired']=True
        ownership._save(record)
    else:
        (upstream_root/'oauth-drop-response').touch()
        with testcase.assertRaises(ValueError):
            coordinator.refresh(account,force_refresh=True)
        parent=sessions.ledger.get(sessions.ledger.pending()[0])
        testcase.assertEqual('closed',parent['record']['node_receipt']['phase'])
        testcase.assertTrue(ownership.state(account['id'])['refresh_pending'])
    if inactive:
        with sessions.service.store.database() as connection:
            connection.execute('UPDATE accounts SET enabled=0 WHERE id=?',(account['id'],))
    manager=main.LoginManager(Mock())
    logins=ClusterAccountLogins(sessions,coordinator,lambda name:owner_lock,
        main._save_remote_login_authorization,main._remote_login_admission)
    testcase.addCleanup(logins.close)
    ownership.read_profile=main._read_bench_profile_identity
    ownership.read_identity=main._v3_cli_identity_readonly
    ownership.read_material=main._read_current_owner_material
    with patch.object(main,'account_runtime',runtime),patch.object(main,'cluster_service',sessions.service), \
            patch.object(main,'cluster_runner',SimpleNamespace(credentials=coordinator,project_io=None)), \
            patch.object(main,'cluster_logins',logins),patch.object(main,'login_manager',manager), \
            patch.object(main,'credential_ownership',ownership),patch.object(main,'continue_manager',None), \
            patch.object(main,'pi_owners',None),patch.object(main,'get_db',sessions.service.store.database), \
            patch.object(main,'_db_lock',sessions.service.store.lock),patch.object(main,'BENCH_DATA',runtime.data), \
            patch.object(main,'PROFILES_DIR',runtime.data/'profiles'),patch.object(main,'_oauth_owner_lock',lambda name:owner_lock), \
            patch.object(main,'_resolve_account_cli_version',lambda account,version=None:(version or '2.1.293','fixture')), \
            patch.object(main,'V3_ENABLED',True),patch.object(main,'WEBUI_USER','synthetic-admin'), \
            patch.object(main,'WEBUI_PASS','synthetic-password'),patch.dict(os.environ,{'V3_INTERNAL_TOKEN':'c'*64}):
        client=TestClient(main.app,headers={'Authorization':'Bearer '+'c'*64})
        testcase.addCleanup(client.close)
        response=client.post('/api/accounts/login/start',json={'name':account['name'],'force_reauth':True})
        testcase.assertEqual(200,response.status_code,response.text)
        sid=response.json()['session_id']
        operation=manager.get(sid).remote_operation
        testcase.assertEqual(2 if parent else 1,len(sessions.ledger.active(account['id'])))
        if inactive:
            with main.get_db() as connection:
                testcase.assertEqual(0,connection.execute('SELECT enabled FROM accounts WHERE id=?',(account['id'],)).fetchone()[0])
        deadline=time.monotonic()+90
        while True:
            response=client.get('/api/accounts/login/'+sid+'/status')
            testcase.assertEqual(200,response.status_code,response.text)
            if response.json().get('authorization_url'):
                break
            testcase.assertLess(time.monotonic(),deadline,'原产品登录准备超时')
            time.sleep(.2)
        testcase.assertEqual(previous,(root/'home/.claude/.credentials.json').read_bytes())
        # 走原浏览器会话与按路径票据，Node自身仍验证独立私有服务认证。
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
                testcase.assertLess(time.monotonic(),deadline,'原PTY输入尚未到达同一CLI')
                time.sleep(.1)
        testcase.assertEqual(1,json.loads((root/'home/.synthetic-code-count.json').read_text())['count'])
        code={'request_id':uuid4().hex,'code':'synthetic-code'}
        delivered=client.post('/api/accounts/login/'+sid+'/code',json=code)
        testcase.assertEqual(200,delivered.status_code,delivered.text)
        testcase.assertEqual('delivered',delivered.json()['status'])
        testcase.assertEqual(delivered.json(),client.post('/api/accounts/login/'+sid+'/code',json=code).json())
        testcase.assertEqual(delivered.json(),client.get('/api/accounts/login/'+sid+'/code/'+code['request_id']).json())
        deadline=time.monotonic()+15
        while not client.get('/api/accounts/login/'+sid+'/status').json().get('credentials_ready'):
            testcase.assertLess(time.monotonic(),deadline,'原产品CLI认证检查尚未通过')
            time.sleep(.1)
        testcase.assertEqual(2,json.loads((root/'home/.synthetic-code-count.json').read_text())['count'])
        call=sessions._call
        dropped=False
        def lose_accept(row,action,payload):
            """实际接受和清理完成后丢一次中央响应。:return: 其它原真实SSH结果。"""
            nonlocal dropped
            result=call(row,action,payload)
            if action=='account-login-accept' and not dropped:
                dropped=True
                raise ConnectionError('合成中央接受响应丢失')
            return result
        with patch.object(sessions,'_call',side_effect=lose_accept):
            response=client.post('/api/accounts/login/'+sid+'/commit',json={'name':account['name']})
        testcase.assertEqual(503,response.status_code,response.text)
        testcase.assertTrue(dropped)
        testcase.assertEqual(2 if parent else 1,len(sessions.ledger.active(account['id'])))
        testcase.assertFalse((root/'runtime/execution.json').exists())
        testcase.assertFalse((root/'home/.v3-login'/sid).exists())
        logins.close()
        restored=ClusterAccountLogins(sessions,coordinator,lambda name:owner_lock,
            main._save_remote_login_authorization,main._remote_login_admission)
        testcase.addCleanup(restored.close)
        with patch.object(main,'cluster_logins',restored),patch.object(main,'login_manager',main.LoginManager(Mock())):
            restored.recover_pending()
            response=client.post('/api/accounts/login/'+sid+'/commit',json={'name':account['name']})
            testcase.assertEqual(200,response.status_code,response.text)
            testcase.assertEqual(account['id'],response.json()['id'])
            testcase.assertEqual('committed',client.get('/api/accounts/login/'+sid+'/status').json()['phase'])
        testcase.assertEqual([],sessions.ledger.pending())
        testcase.assertEqual({},sessions.activities)
        testcase.assertFalse(ownership.state(account['id'])['refresh_pending'])
        if parent:
            testcase.assertEqual('superseded_by_new_authorization',sessions.ledger.get(parent['operation_id'])['record']['failure'])
        if retired:
            testcase.assertFalse(ownership.state(account['id'])['retired'])
        testcase.assertEqual('closed',sessions.ledger.get(operation)['phase'])
        current=json.loads((root/'home/.claude/.credentials.json').read_text())['claudeAiOauth']
        testcase.assertEqual('synthetic-node-authorized-refresh',current['refreshToken'])
        testcase.assertEqual(top['userID'],json.loads((root/'home/.claude.json').read_text())['userID'])
        testcase.assertEqual(current['refreshToken'],json.loads((main.PROFILES_DIR/account['name']/'.credentials.json').read_text())['claudeAiOauth']['refreshToken'])
        with main.get_db() as connection:
            proof=json.loads(connection.execute('SELECT record_json FROM local_credential_authorizations WHERE account_id=?',(account['id'],)).fetchone()[0])
        testcase.assertEqual('2.1.293',proof['cli_version'])
        testcase.assertEqual(top['userID'],proof['device_id'])
        with main.get_db() as connection:
            testcase.assertEqual(1,connection.execute('SELECT enabled FROM accounts WHERE id=?',(account['id'],)).fetchone()[0])
        testcase.assertEqual(2 if parent else 1,sum(json.loads(line)['kind']=='oauth-refresh' for line in (upstream_root/'evidence.jsonl').read_text().splitlines()))
