"""仅在随机隔离部署验证NULL草稿的实际SSH、tmux及原CLI产物恢复。"""
from __future__ import annotations

import json
import os
import select
import threading
import time
from contextlib import ExitStack
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4
from unittest.mock import Mock, patch

from fastapi.testclient import TestClient

from credential_ownership import CredentialOwnership
from cluster_credential_refresh import RemoteCredentialRefresh
from cluster_continue_runner import RemoteContinuePty
from cluster_deployment import node_container_name
from cluster_draft_login_contract import DraftLoginAccept, DraftLoginActivated, DraftLoginActivation, DraftLoginCode, DraftLoginFiles, DraftLoginGrant, DraftLoginPreparation, DraftLoginScope, DraftLoginSettings, DraftLoginSnapshot, DraftLoginStart, DraftLoginWork, draft_preparation_sha256
from cluster_draft_login_files import read_draft_login_documents
from cluster_draft_login_store import NodeLoginDrafts
from cluster_draft_login_runner import ClusterDraftLogins
from cluster_execution_store import NodeExecutions
from cluster_terminal_sessions import TerminalSessions
from cluster_transfer import NodeArchiveTransfer
from runtime_files import atomic_json
from system_update_gate import DeploymentGate
import main


def _install_draft_cli(root: Path) -> None:
    """在本次已准备的随机Node环境中安装离线CLI夹具。"""
    prefix=root/'cli/2.1.293'
    program=prefix/'node_modules/.bin/claude'
    program.parent.mkdir(parents=True,exist_ok=True)
    source=(Path(__file__).parent/'fixtures/mock_cli.py').read_text()
    program.write_text(source.replace('9.9.9 (Synthetic lifecycle fixture)','2.1.293 (Synthetic lifecycle fixture)'))
    program.chmod(0o755)
    for directory in (prefix,prefix/'node_modules',program.parent):
        directory.chmod(0o755)
    (prefix/'.ready').touch()
    control=root/'home/.synthetic-login.json'
    atomic_json(control,{'wait_for_code':True,'access_token':'synthetic-draft-access','refresh_token':'synthetic-draft-refresh',
        'account_uuid':'synthetic-draft-account','organization_uuid':'synthetic-draft-org','email':'draft@example.invalid'})
    os.chown(control,1000,1000,follow_symlinks=False)


def verify_node_draft_login(testcase, service, runtime, node: dict, remote_data: Path) -> None:
    """真实Node始终使用NULL身份，中央首次保存只在原实际收口之后执行。

    :param testcase: 本次随机部署测试。
    :param service: 原受信SSH服务。
    :param runtime: 原中央环境登记。
    :param node: 本次已准备节点。
    :param remote_data: 本次实际Node专属根。
    :return: None；授权产物来自离线CLI夹具，不访问供应商OAuth或模型。
    """
    if os.environ.get('CLUSTER_DOCKER_TEST')!='1' or not runtime.deployment.startswith('cluster-test-'):
        raise ValueError('草稿实际验证仅允许本次随机隔离部署')
    name='draft_'+uuid4().hex[:8]
    environment=runtime._row(name,timezone='UTC')
    settings=DraftLoginSettings(name=name,timezone='UTC',upstream_socks5_host='cluster-test-proxy')
    files={'.claude.json':json.dumps({'userID':'d'*64,'synthetic_unknown':{'preserved':True},'synthetic_large':'x'*(80*1024)}),
        'settings.json':json.dumps({'permissions':{'defaultMode':'bypassPermissions'},'synthetic_unknown':{'preserved':True}})}
    sid=uuid4().hex[:12]
    work=DraftLoginWork(id=uuid4().hex,sid=sid,environment_id=environment['environment_id'],name=name,
        draft_generation=uuid4().hex,version='2.1.293',home='/home/node/.v3-login/'+sid,
        preparation_sha256=draft_preparation_sha256(settings,environment['fingerprint_json'],files),expires_at=int(time.time())+900)
    preparation=DraftLoginPreparation(node_key=node['node_key'],work=work,settings=settings,
        fingerprint_json=environment['fingerprint_json'],profile_files=files)
    ledger=NodeLoginDrafts(service.store,os.environ['V3_RELEASE'],runtime.data)
    row=ledger.begin(node['id'],preparation)
    peer=service.connection(node['id'])
    container=node_container_name(runtime.deployment,node['node_key'])

    def rpc(operation, payload):
        """沿原固定SSH入口读取Node回执，并在失败时保留受控调用位置。:return: 原受信结果。"""
        try:
            value=peer.execution_environment(container,payload,operation)
        except Exception:
            control=runtime.client.containers.get(container)
            testcase.fail('草稿Node操作失败 '+operation+'；原调用位置：'+control.logs(tail=12).decode(errors='replace'))
        return value.get('login',value.get('record'))

    marker=rpc('draft-login-prepare',preparation.model_dump())
    scope=DraftLoginScope.model_validate(marker['scope'])
    row=ledger.checkpoint(work.id,row['revision'],'preparing',scope=scope)
    root=remote_data/'environments'/environment['environment_id']
    _install_draft_cli(root)
    grant=DraftLoginGrant(**scope.model_dump(),not_after=int(time.time())+30)
    row=ledger.checkpoint(work.id,row['revision'],'preparing',grant=grant,start_intent=True)
    rpc('draft-login-grant-create',grant.model_dump())
    renew_at=time.monotonic()+5

    def call(operation,payload):
        """原操作内按中央账本续接证明；已停止后只查询原回执。:return: 原Node事实。"""
        nonlocal row,grant,renew_at
        if time.monotonic()>=renew_at and row['phase'] not in ('closed','stopping'):
            grant=grant.model_copy(update={'sequence':grant.sequence+1,'not_after':int(time.time())+30})
            row=ledger.checkpoint(work.id,row['revision'],row['phase'],grant=grant)
            rpc('draft-login-grant-renew',grant.model_dump())
            renew_at=time.monotonic()+5
        return rpc(operation,payload)

    receipt=call('draft-login-start',DraftLoginStart(scope=scope,work=work).model_dump())
    deadline=time.monotonic()+90
    while receipt['phase']=='starting':
        testcase.assertLess(time.monotonic(),deadline,'原草稿tmux准备超时')
        time.sleep(.1)
        receipt=call('draft-login-get',scope.model_dump())
    testcase.assertEqual('ready',receipt['phase'],receipt)
    row=ledger.checkpoint(work.id,row['revision'],'active',node_receipt=receipt)
    testcase.assertEqual(receipt,call('draft-login-start',DraftLoginStart(scope=scope,work=work).model_dump()))
    observed=call('draft-login-observe',scope.model_dump())
    deadline=time.monotonic()+15
    while not observed['authorization_url']:
        testcase.assertLess(time.monotonic(),deadline,'草稿CLI授权链接等待超时')
        time.sleep(.1)
        observed=call('draft-login-observe',scope.model_dump())
    testcase.assertFalse(observed['credentials_ready'])
    # 原共享PTY传输直接消费草稿Scope，真实键盘输入仍经过Node单次输入账本。
    isolated=[]
    sessions=SimpleNamespace(service=service,_call=lambda current,operation,payload:call(operation,payload),
        _isolate=lambda operation,reason:isolated.append((operation,reason)))
    pty=RemoteContinuePty(SimpleNamespace(sessions=sessions),row,purpose='draft-login')
    try:
        pty.resize(30,100)
        testcase.assertEqual(1,pty.send(b'\x15'))
        select.select([pty],[],[],1)
    finally:
        pty.close()
    code=DraftLoginCode(scope=scope,request_id=uuid4().hex,code='synthetic-code')
    delivered=call('draft-login-code',code.model_dump())
    testcase.assertEqual('delivered',delivered['status'])
    testcase.assertEqual(delivered,call('draft-login-code',code.model_dump()))
    deadline=time.monotonic()+15
    while not call('draft-login-observe',scope.model_dump())['credentials_ready']:
        testcase.assertLess(time.monotonic(),deadline,'原草稿CLI认证检查等待超时')
        time.sleep(.1)
    testcase.assertEqual(1,json.loads((root/'home/.synthetic-code-count.json').read_text())['count'])
    row=ledger.checkpoint(work.id,row['revision'],'stopping')
    closed=call('draft-login-discard',scope.model_dump())
    testcase.assertEqual('closed',closed['phase'])
    row=ledger.checkpoint(work.id,row['revision'],'closed',node_receipt=closed)
    original=scope
    original_home=work.home
    staged=root/'home/.v3-login'/work.sid
    testcase.assertTrue((staged/'.claude/.credentials.json').is_file())
    work=DraftLoginWork.model_validate({**work.model_dump(),'id':uuid4().hex,'sid':uuid4().hex[:12],
        'draft_generation':uuid4().hex,'mode':'recover'})
    preparation=DraftLoginPreparation(**{**preparation.model_dump(),'work':work,'previous':original})
    row=ledger.begin(node['id'],preparation,previous_revision=row['revision'])
    scope=DraftLoginScope.model_validate(rpc('draft-login-prepare',preparation.model_dump())['scope'])
    row=ledger.checkpoint(work.id,row['revision'],'preparing',scope=scope)
    grant=DraftLoginGrant(**scope.model_dump(),not_after=int(time.time())+30)
    row=ledger.checkpoint(work.id,row['revision'],'preparing',grant=grant,start_intent=True)
    rpc('draft-login-grant-create',grant.model_dump())
    renew_at=time.monotonic()+5
    receipt=call('draft-login-start',DraftLoginStart(scope=scope,work=work).model_dump())
    deadline=time.monotonic()+90
    while receipt['phase']=='starting':
        testcase.assertLess(time.monotonic(),deadline,'原草稿产物恢复等待超时')
        time.sleep(.1)
        receipt=call('draft-login-get',scope.model_dump())
    testcase.assertEqual('ready',receipt['phase'],receipt)
    row=ledger.checkpoint(work.id,row['revision'],'active',node_receipt=receipt)
    observed=call('draft-login-observe',scope.model_dump())
    testcase.assertTrue(observed['credentials_ready'])
    testcase.assertFalse(observed['reconnectable'])
    testcase.assertEqual(original_home,work.home)
    committed=call('draft-login-commit',scope.model_dump())
    row=ledger.checkpoint(work.id,row['revision'],'submitting',node_receipt=committed)
    snapshot=DraftLoginSnapshot.model_validate(call('draft-login-snapshot',scope.model_dump()))
    testcase.assertEqual('synthetic-draft-refresh',snapshot.material.refresh_token)
    testcase.assertEqual('d'*64,snapshot.identity.user_id)
    index=DraftLoginFiles.model_validate(call('draft-login-files',scope.model_dump()))
    testcase.assertEqual(scope,index.scope)
    testcase.assertEqual(snapshot.authorization_sha256,index.authorization_sha256)
    row=ledger.checkpoint(work.id,row['revision'],'submitting',files=index)
    transfer=NodeArchiveTransfer(peer.docker_socket(),service.docker(node['id']).api._version,container)
    documents=read_draft_login_documents(transfer,index,runtime.data/'draft-authorizations'/scope.operation_id)
    testcase.assertEqual('x'*(80*1024),documents['.claude.json']['synthetic_large'])
    testcase.assertEqual({'preserved':True},documents['.claude/settings.json']['synthetic_unknown'])
    testcase.assertEqual(snapshot.material.refresh_token,documents['.claude/.credentials.json']['claudeAiOauth']['refreshToken'])
    for source_name,target_name in (('.claude.json','.claude.json'),('.claude/.credentials.json','.credentials.json'),
            ('.claude/settings.json','settings.json')):
        if source_name in documents:
            atomic_json(runtime.data/'profiles'/name/target_name,documents[source_name])
    accept=DraftLoginAccept(scope=scope,authorization_sha256=snapshot.authorization_sha256)
    rpc('draft-login-accept',accept.model_dump())
    # 实际Node已接受并清理，中央尚未保存回执；重建账本后只查询同一工作并读原私有副本。
    ledger=NodeLoginDrafts(service.store,os.environ['V3_RELEASE'],runtime.data)
    row=ledger.get(work.id)
    testcase.assertEqual('saved',row['record']['node_receipt']['commit']['stage'])
    accepted=rpc('draft-login-commit',scope.model_dump())
    recovered=read_draft_login_documents(transfer,DraftLoginFiles.model_validate(row['record']['files']),
        runtime.data/'draft-authorizations'/scope.operation_id)
    testcase.assertEqual(documents,recovered)
    testcase.assertEqual('closed',accepted['phase'])
    testcase.assertFalse(accepted['commit']['cleanup_pending'])
    row=ledger.checkpoint(work.id,row['revision'],'submitting',node_receipt=accepted)
    testcase.assertFalse(staged.exists())
    testcase.assertFalse((root/'runtime/execution.json').exists())
    testcase.assertEqual(1,json.loads((root/'home/.synthetic-code-count.json').read_text())['count'])
    testcase.assertEqual({'preserved':True},json.loads((root/'home/.claude.json').read_text())['synthetic_unknown'])
    saved=ledger.save_account(work.id,row['revision'],preparation,80,90)
    testcase.assertEqual(node['id'],service.store.assignment(saved['saved_account_id'])['node_id'])
    testcase.assertEqual([],isolated)
    connection=service.store.database()
    try:
        testcase.assertEqual(0,connection.execute('SELECT enabled FROM accounts WHERE id=?',(saved['saved_account_id'],)).fetchone()[0])
    finally:
        connection.close()
    request=DraftLoginActivation(scope=scope,account_id=saved['saved_account_id'],authorization_sha256=snapshot.authorization_sha256)
    rpc('draft-login-activate',request.model_dump())
    ledger=NodeLoginDrafts(service.store,os.environ['V3_RELEASE'],runtime.data)
    saved=ledger.get(work.id)
    testcase.assertIsNone(saved['record']['activation'])
    activation=DraftLoginActivated.model_validate(rpc('draft-login-activate',request.model_dump()))
    testcase.assertEqual(request,activation.request)
    testcase.assertEqual(activation.model_dump(),rpc('draft-login-activate',request.model_dump()))
    roles=runtime.client.containers.list(all=True,filters={'label':['vibebench.deployment='+runtime.deployment,
        'vibebench.environment='+scope.environment_id,'vibebench.cluster-node='+scope.node_key]})
    testcase.assertEqual([],roles)
    connection=service.store.database()
    try:
        account=dict(connection.execute('SELECT * FROM accounts WHERE id=?',(saved['saved_account_id'],)).fetchone())
    finally:
        connection.close()
    identity=json.dumps({'account_id':account['id'],'binding':None,'uuid':snapshot.identity.account_uuid,
        'org':snapshot.identity.organization_uuid},sort_keys=True)
    credentials=RemoteCredentialRefresh(SimpleNamespace(service=service,runtime=runtime),None,lambda name:None,
        lambda current:identity,lambda current:work.version)
    unused=Mock(side_effect=AssertionError('首次独立授权来源读取超出原只读范围'))
    owner=CredentialOwnership(runtime,runtime.gateway,service.store.database,service.store.lock,
        read_profile=lambda current:main._read_bench_profile_identity(current,runtime.data/'profiles'/current),
        read_identity=credentials.read_identity,read_material=credentials.read_material,
        mirror=unused,mirror_locked=unused,profile_lock=unused,identity=unused,validate=unused,find=unused,
        idle=unused,available=unused,creation_payload=unused,refresh=unused)
    owner.record_local_authorization(account['id'],work.version)
    connection=service.store.database()
    try:
        proof=json.loads(connection.execute('SELECT record_json FROM local_credential_authorizations WHERE account_id=?',
            (account['id'],)).fetchone()[0])
        testcase.assertEqual(activation.refresh_sha256,proof['refresh_sha256'])
        testcase.assertEqual(scope.environment_id,proof['environment_id'])
    finally:
        connection.close()
    completed=ledger.finish(work.id,saved['revision'],activation,runtime.deployment)
    testcase.assertEqual('closed',completed['phase'])
    testcase.assertEqual([],ledger.pending())
    connection=service.store.database()
    try:
        account=dict(connection.execute('SELECT * FROM accounts WHERE id=?',(account['id'],)).fetchone())
    finally:
        connection.close()
    testcase.assertEqual(1,account['enabled'])
    testcase.assertEqual(snapshot.material.refresh_token,credentials.read_material(account)['refresh_token'])
    prepared=service.prepare_remote_cli(account,runtime,runtime.gateway,identity)
    testcase.assertEqual(scope.environment_id,prepared['environment']['environment_id'])
    testcase.assertGreater(prepared['environment']['generation'],scope.generation)
    roles=runtime.client.containers.list(all=True,filters={'label':['vibebench.deployment='+runtime.deployment,
        'vibebench.environment='+scope.environment_id,'vibebench.role=account-network']})
    testcase.assertEqual(1,len(roles))
    roles[0].reload()
    quota=[mount for mount in roles[0].attrs['Mounts'] if mount['Destination']=='/quota-accounts/'+str(account['id'])]
    testcase.assertEqual(1,len(quota))
    testcase.assertEqual('bind',quota[0]['Type'])
    testcase.assertFalse(quota[0]['RW'])
    testcase.assertEqual(str(remote_data/'quota'/str(account['id'])),quota[0]['Source'])


def verify_draft_login_coordinator(testcase, service, runtime, node: dict, remote_data: Path) -> None:
    """正式中央草稿协调器经实际SSH处理两次提交响应未知与重建恢复。

    :param testcase: 本次随机隔离部署。
    :param service: 原实际SSH节点服务。
    :param runtime: 原中央环境登记。
    :param node: 本次已准备节点。
    :param remote_data: 本次实际Node根。
    :return: None；全部授权产物由离线CLI生成。
    """
    if os.environ.get('CLUSTER_DOCKER_TEST')!='1' or not runtime.deployment.startswith('cluster-test-'):
        raise ValueError('中央草稿协调验证仅用于本次随机隔离部署')
    peer=service.connection(node['id'])
    original_call=peer.execution_environment
    def mirror(name,documents):
        """保持完整固定文件的中央镜像。:return: None。"""
        for source,target in (('.claude.json','.claude.json'),('.claude/.credentials.json','.credentials.json'),
                ('.claude/settings.json','settings.json')):
            if source in documents:
                atomic_json(runtime.data/'profiles'/name/target,documents[source])
    def record_authorization(account_id,version):
        """沿原Owner和实际Node纯读取登记来源证明。:return: None。"""
        def identity(account):
            profile=main._read_bench_profile_identity(account['name'],runtime.data/'profiles'/account['name'])
            return json.dumps({'account_id':account['id'],'binding':None,'uuid':profile['account_uuid'],
                'org':profile.get('organization_uuid')},sort_keys=True)
        credentials=RemoteCredentialRefresh(SimpleNamespace(service=service,runtime=runtime),None,lambda name:None,
            identity,lambda account:version)
        unused=Mock(side_effect=AssertionError('首次来源登记超出原只读范围'))
        owner=CredentialOwnership(runtime,runtime.gateway,service.store.database,service.store.lock,
            read_profile=lambda name:main._read_bench_profile_identity(name,runtime.data/'profiles'/name),
            read_identity=credentials.read_identity,read_material=credentials.read_material,
            mirror=unused,mirror_locked=unused,profile_lock=unused,identity=unused,validate=unused,find=unused,
            idle=unused,available=unused,creation_payload=unused,refresh=unused)
        owner.record_local_authorization(account_id,version)
    def coordinator(guard):
        """重建中央进程内协调及活动表，原SQLite和私有文件保持。:return: 具体协调器。"""
        sessions=TerminalSessions(NodeExecutions(service.store,os.environ['V3_RELEASE']),service,runtime,runtime.gateway,
            None,None,activity_gate=DeploymentGate())
        value=ClusterDraftLogins(sessions,lambda name:guard,mirror,record_authorization,80,90)
        testcase.addCleanup(value.close)
        return value
    for loss_operation in ('draft-login-accept','draft-login-activate'):
        name='draft_'+uuid4().hex[:8]
        environment=runtime._row(name,timezone='UTC')
        settings=DraftLoginSettings(name=name,timezone='UTC',upstream_socks5_host='cluster-test-proxy')
        files={'.claude.json':json.dumps({'userID':'d'*64,'synthetic_large':'x'*(80*1024)}),
            'settings.json':json.dumps({'permissions':{'defaultMode':'bypassPermissions'},'synthetic_unknown':{'preserved':True}})}
        sid=uuid4().hex[:12]
        work=DraftLoginWork(id=uuid4().hex,sid=sid,environment_id=environment['environment_id'],name=name,
            draft_generation=uuid4().hex,version='2.1.293',home='/home/node/.v3-login/'+sid,
            preparation_sha256=draft_preparation_sha256(settings,environment['fingerprint_json'],files),expires_at=int(time.time())+900)
        preparation=DraftLoginPreparation(node_key=node['node_key'],work=work,settings=settings,
            fingerprint_json=environment['fingerprint_json'],profile_files=files)
        root=remote_data/'environments'/environment['environment_id']
        state={'lost':False}
        def execution(container,payload,operation):
            """实际Node先执行，原准备后注入离线制品，指定提交响应只丢一次。:return: 原实际回执。"""
            value=original_call(container,payload,operation)
            if operation=='draft-login-prepare':
                _install_draft_cli(root)
            if operation==loss_operation and not state['lost']:
                state['lost']=True
                raise ConnectionError('synthetic response lost after actual Node action')
            return value
        guard=threading.Lock()
        current=coordinator(guard)
        with patch.object(peer,'execution_environment',side_effect=execution):
            row=current.start(node['id'],preparation)
            deadline=time.monotonic()+90
            while True:
                status=current.status(work.id)
                if status.get('authorization_url'):
                    break
                testcase.assertLess(time.monotonic(),deadline,'中央草稿协调原授权链接等待超时')
                time.sleep(.1)
            handle=current.open(work.id)
            try:
                handle.resize(30,100)
                testcase.assertEqual(1,handle.send(b'\x15'))
            finally:
                handle.close()
            delivered=current.code(work.id,uuid4().hex,'synthetic-code')
            testcase.assertEqual('delivered',delivered['status'])
            deadline=time.monotonic()+15
            while not current.status(work.id)['credentials_ready']:
                testcase.assertLess(time.monotonic(),deadline,'中央草稿协调原认证检查等待超时')
                time.sleep(.1)
            with testcase.assertRaises(ConnectionError):
                current.commit(work.id)
            failed=current.ledger.get(work.id)
            testcase.assertEqual('reconcile',failed['phase'])
            if loss_operation=='draft-login-activate':
                testcase.assertGreater(failed['saved_account_id'],0)
                connection=service.store.database()
                try:
                    testcase.assertEqual(0,connection.execute('SELECT enabled FROM accounts WHERE id=?',(failed['saved_account_id'],)).fetchone()[0])
                finally:
                    connection.close()
            current.close()
            restored=coordinator(guard)
            restored.recover_pending()
            result=restored.result(work.id)
            testcase.assertEqual('committed',restored.status(work.id)['phase'])
            testcase.assertEqual({},restored.activities)
            testcase.assertEqual({},restored.activity_gate.active)
            testcase.assertEqual(result,restored.commit(work.id))
        testcase.assertEqual(1,json.loads((root/'home/.synthetic-code-count.json').read_text())['count'])
        testcase.assertFalse((root/'runtime/execution.json').exists())
        connection=service.store.database()
        try:
            account=connection.execute('SELECT * FROM accounts WHERE id=?',(result['id'],)).fetchone()
            testcase.assertEqual((name,1),(account['name'],account['enabled']))
            testcase.assertEqual(node['id'],service.store.assignment(account['id'])['node_id'])
            proof=json.loads(connection.execute('SELECT record_json FROM local_credential_authorizations WHERE account_id=?',
                (account['id'],)).fetchone()[0])
            testcase.assertEqual(environment['environment_id'],proof['environment_id'])
        finally:
            connection.close()
        testcase.assertEqual('x'*(80*1024),json.loads((runtime.data/'profiles'/name/'.claude.json').read_text())['synthetic_large'])


def verify_product_draft_login(testcase, service, runtime, node: dict, remote_data: Path) -> None:
    """原管理HTTP和票据WS通过真实SSH完成草稿恢复、保存及完整清理。

    :param testcase: 本次随机隔离部署。
    :param service: 实际SSH节点服务。
    :param runtime: 原中央运行时。
    :param node: 本次已准备节点。
    :param remote_data: 实际Node私有根。
    :return: None；使用离线合成CLI和合成授权产物。
    """
    if os.environ.get('CLUSTER_DOCKER_TEST')!='1' or not runtime.deployment.startswith('cluster-test-'):
        raise ValueError('原产品草稿验证仅用于本次随机隔离部署')
    peer=service.connection(node['id'])
    original_call=peer.execution_environment
    state={'loss':None,'calls':[]}
    def execution(container,payload,operation):
        """实际执行后仅注入离线CLI和一次指定响应丢失。:return: 原实际回执。"""
        state['calls'].append(operation)
        value=original_call(container,payload,operation)
        if operation=='draft-login-prepare':
            _install_draft_cli(remote_data/'environments'/payload['work']['environment_id'])
        if operation==state['loss']:
            state['loss']=None
            raise ConnectionError('synthetic product response lost after actual Node action')
        return value
    def identity(account):
        """沿原中央镜像建立原所有者身份。:return: 原身份字符串。"""
        profile=main._read_bench_profile_identity(account['name'],runtime.data/'profiles'/account['name'])
        return json.dumps({'account_id':account['id'],'binding':None,'uuid':profile['account_uuid'],
            'org':profile.get('organization_uuid')},sort_keys=True)
    credentials=RemoteCredentialRefresh(SimpleNamespace(service=service,runtime=runtime),None,main._oauth_owner_lock,
        identity,lambda account:'2.1.293')
    unused=Mock(side_effect=AssertionError('首次来源登记超出原Node只读范围'))
    owner=CredentialOwnership(runtime,runtime.gateway,service.store.database,service.store.lock,
        read_profile=lambda name:main._read_bench_profile_identity(name,runtime.data/'profiles'/name),
        read_identity=credentials.read_identity,read_material=credentials.read_material,
        mirror=unused,mirror_locked=unused,profile_lock=unused,identity=unused,validate=unused,find=unused,
        idle=unused,available=unused,creation_payload=unused,refresh=unused)
    def coordinator():
        """重建具体协调器与进程内活动表，复用原数据库及原产品回调。:return: 新协调器。"""
        sessions=TerminalSessions(NodeExecutions(service.store,os.environ['V3_RELEASE']),service,runtime,runtime.gateway,
            None,None,activity_gate=DeploymentGate())
        value=ClusterDraftLogins(sessions,main._oauth_owner_lock,main._save_remote_draft_profile,
            main._record_remote_draft_authorization,80,90,profile_lock=main._profile_lock,
            prepare_admission=main._mark_remote_draft_node_prepare)
        testcase.addCleanup(value.close)
        return value
    current=coordinator()
    with ExitStack() as stack:
        for key,value in {'get_db':service.store.database,'_db_lock':service.store.lock,'BENCH_DATA':runtime.data,
                'PROFILES_DIR':runtime.data/'profiles','account_runtime':runtime,'cluster_service':service,
                'cluster_draft_logins':current,'cluster_logins':None,'cluster_bound_logins':None,
                'cluster_runner':SimpleNamespace(credentials=credentials,project_io=None),'credential_ownership':owner,
                'cc2api_client':runtime.gateway,
                'login_manager':main.LoginManager(Mock()),'continue_manager':None,'pi_owners':None,
                '_resolve_account_cli_version':lambda account,version=None:(version or '2.1.293','synthetic'),
                'V3_ENABLED':True,'WEBUI_USER':'synthetic-admin','WEBUI_PASS':'synthetic-password'}.items():
            stack.enter_context(patch.object(main,key,value))
        stack.enter_context(patch.dict(os.environ,{'V3_INTERNAL_TOKEN':'c'*64}))
        stack.enter_context(patch.object(peer,'execution_environment',side_effect=execution))
        if os.environ.get('CLUSTER_TEST_DRAFT_GATEWAY_BIN'):
            from verify_cluster_draft_gateway import DraftGatewayClient
            client=DraftGatewayClient(testcase,runtime,Path(os.environ['CLUSTER_TEST_DRAFT_GATEWAY_BIN']))
        else:
            client=TestClient(main.app,headers={'Authorization':'Bearer '+'c'*64})
        stack.callback(client.close)
        client.cookies.set(main._SESSION_COOKIE,main._make_session_token(main.WEBUI_USER),path='/')
        def start(name):
            """沿原产品入口选择Node新建。:param name: 合成名称。:return: HTTP响应。"""
            connection=client.proxy_selection if os.environ.get('CLUSTER_TEST_DRAFT_GATEWAY_BIN') else {'upstream_socks5_host':'cluster-test-proxy'}
            return client.post('/api/accounts/login/start',json={'name':name,'node_id':node['id'],
                'timezone':'UTC',**connection})
        def wait_status(sid,ready=False):
            """串行查询实际Node认证状态。:param sid: 原SID。:param ready: 是否等待认证通过。:return: 状态。"""
            deadline=time.monotonic()+90
            while True:
                response=client.get('/api/accounts/login/'+sid+'/status')
                testcase.assertEqual(200,response.status_code,response.text)
                status=response.json()
                if status.get('credentials_ready') if ready else status.get('authorization_url'):
                    return status
                testcase.assertLess(time.monotonic(),deadline,'原产品节点草稿认证等待超时：'+str({
                    key:status.get(key) for key in ('phase','credentials_ready','reconnectable','message')}))
                time.sleep(.1)
        name='draft_api_'+uuid4().hex[:8]
        atomic_json(runtime.data/'profiles'/name/'.claude.json',{'userID':'d'*64,'synthetic_large':'x'*(80*1024)})
        response=start(name)
        if response.status_code!=200:
            frames=service.docker(node['id']).containers.get(node_container_name(runtime.deployment,node['node_key'])).logs(tail=5).decode(errors='replace')
            testcase.fail(response.text+'；合成Root回执：'+str(getattr(client,'last_runtime_error',None))+'；Node位置：'+frames)
        first=response.json()
        testcase.assertEqual(node['id'],first['node_id'])
        sid=first['session_id']
        wait_status(sid)
        path=first['ws_path']
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
            root=remote_data/'environments'/first['environment_id']
            deadline=time.monotonic()+15
            while not (root/'home/.synthetic-code-count.json').exists():
                testcase.assertLess(time.monotonic(),deadline,'原产品PTY输入尚未到达原CLI')
                time.sleep(.1)
            # 输入和ping沿原浏览器消息循环顺序处理，第二个pong确认输入回执已经收口后再断开窗口。
            websocket.send_json({'type':'ping'})
            while True:
                message=websocket.receive()
                if message.get('text') and json.loads(message['text']).get('type')=='pong':
                    break
                testcase.assertEqual('websocket.send',message['type'],message)
        code={'request_id':uuid4().hex,'code':'synthetic-code'}
        response=client.post('/api/accounts/login/'+sid+'/code',json=code)
        testcase.assertEqual(200,response.status_code,response.text)
        testcase.assertEqual('delivered',response.json()['status'],response.text)
        wait_status(sid,ready=True)
        response=client.delete('/api/accounts/login/'+sid)
        testcase.assertEqual(200,response.status_code,response.text)
        draft=next(row for row in client.get('/api/accounts/login-drafts').json() if row['environment_id']==first['environment_id'])
        testcase.assertTrue(draft['can_resume'])
        response=client.post('/api/accounts/login-drafts/'+first['environment_id']+'/resume',json={'generation':draft['generation']})
        testcase.assertEqual(200,response.status_code,response.text)
        resumed=response.json()
        testcase.assertNotEqual(sid,resumed['session_id'])
        sid=resumed['session_id']
        wait_status(sid,ready=True)
        state['loss']='draft-login-activate'
        response=client.post('/api/accounts/login/'+sid+'/commit',json={'name':name})
        testcase.assertEqual(503,response.status_code,response.text)
        current.close()
        current=coordinator()
        main.cluster_draft_logins=current
        main.login_manager=main.LoginManager(Mock())
        response=client.post('/api/accounts/login/'+sid+'/commit',json={'name':name})
        testcase.assertEqual(200,response.status_code,response.text)
        account_id=response.json()['id']
        testcase.assertEqual(node['id'],service.store.assignment(account_id)['node_id'])
        testcase.assertEqual('x'*(80*1024),json.loads((runtime.data/'profiles'/name/'.claude.json').read_text())['synthetic_large'])
        root=remote_data/'environments'/first['environment_id']
        testcase.assertEqual(2,json.loads((root/'home/.synthetic-code-count.json').read_text())['count'])
        with service.store.database() as connection:
            testcase.assertEqual(1,connection.execute('SELECT enabled FROM accounts WHERE id=?',(account_id,)).fetchone()[0])
            testcase.assertIsNotNone(connection.execute('SELECT 1 FROM local_credential_authorizations WHERE account_id=?',(account_id,)).fetchone())
        for loss in ('draft-login-delete','draft-login-prepare'):
            name='draft_delete_'+uuid4().hex[:8]
            state['loss']=loss if loss=='draft-login-prepare' else None
            response=start(name)
            if loss=='draft-login-prepare':
                testcase.assertEqual(503,response.status_code,response.text)
                draft=next(row for row in client.get('/api/accounts/login-drafts').json() if row['name']==name)
                testcase.assertTrue(draft['can_reconcile'])
                response=client.post('/api/accounts/login-drafts/'+draft['environment_id']+'/reconcile',json={'generation':draft['generation']})
                testcase.assertEqual(200,response.status_code,response.text)
                first={'environment_id':draft['environment_id'],'draft_generation':draft['generation']}
            else:
                testcase.assertEqual(200,response.status_code,response.text)
                first=response.json()
                wait_status(first['session_id'])
                state['loss']=loss
            url='/api/accounts/login-drafts/'+first['environment_id']+'?generation='+first['draft_generation']
            response=client.delete(url)
            if loss=='draft-login-delete':
                testcase.assertEqual(503,response.status_code,response.text)
                current.close()
                current=coordinator()
                main.cluster_draft_logins=current
                main.login_manager=main.LoginManager(Mock())
                current.recover_pending()
                response=client.delete(url)
            testcase.assertEqual(200,response.status_code,response.text)
            testcase.assertFalse((remote_data/'environments'/first['environment_id']).exists())
            testcase.assertFalse((runtime.data/'profiles'/name).exists())
            testcase.assertEqual({'ok':True},client.delete(url).json())
        name='draft_zero_'+uuid4().hex[:8]
        body={'name':name,'node_id':node['id'],'timezone':'UTC'}
        if os.environ.get('CLUSTER_TEST_DRAFT_GATEWAY_BIN'):
            body['proxy_id']=None
        response=client.post('/api/accounts/login/start',json=body)
        testcase.assertEqual(400,response.status_code,response.text)
        draft=next(row for row in client.get('/api/accounts/login-drafts').json() if row['name']==name)
        testcase.assertTrue(draft['can_delete'])
        operation=current.ledger.find(draft['environment_id'])
        testcase.assertIsNone(operation['record']['scope'])
        testcase.assertFalse(operation['record']['start_intent'])
        current._preparation_path(operation).unlink()
        state['loss']='draft-login-delete-preparation'
        url='/api/accounts/login-drafts/'+draft['environment_id']+'?generation='+draft['generation']
        testcase.assertEqual(503,client.delete(url).status_code)
        current.close()
        current=coordinator()
        main.cluster_draft_logins=current
        main.login_manager=main.LoginManager(Mock())
        current.recover_pending()
        response=client.delete(url)
        testcase.assertEqual(200,response.status_code,response.text)
        deleted=current.deletion(draft['environment_id'])
        testcase.assertEqual(('login-draft-preparation',0),(deleted.scope.role,deleted.scope.generation))
        with testcase.assertRaises(ValueError):
            original_call(node_container_name(runtime.deployment,node['node_key']),
                {**deleted.scope.model_dump(),'not_after':int(time.time())+30},'draft-login-grant-create')
        testcase.assertFalse((remote_data/'environments'/draft['environment_id']).exists())
        testcase.assertFalse((runtime.data/'profiles'/name).exists())
        with service.store.database() as connection:
            testcase.assertIsNone(connection.execute('SELECT 1 FROM accounts WHERE name=?',(name,)).fetchone())
        testcase.assertEqual([],client.get('/api/accounts/login-drafts').json())
        name='draft_registration_'+uuid4().hex[:8]
        calls=list(state['calls'])
        with patch.object(current.ledger,'begin',side_effect=ValueError('synthetic registration failure')):
            response=start(name)
        testcase.assertEqual(400,response.status_code,response.text)
        draft=next(row for row in client.get('/api/accounts/login-drafts').json() if row['name']==name)
        testcase.assertTrue(draft['can_delete'])
        testcase.assertFalse(draft['can_resume'])
        marker=json.loads((runtime.data/'login-drafts'/(draft['environment_id']+'.json')).read_text())
        testcase.assertIs(marker['node_prepare_intent'],False)
        testcase.assertEqual(calls,state['calls'])
        response=client.delete('/api/accounts/login-drafts/'+draft['environment_id']+'?generation='+draft['generation'])
        testcase.assertEqual(200,response.status_code,response.text)
        testcase.assertEqual(calls,state['calls'])
        testcase.assertFalse((runtime.data/'profiles'/name).exists())
        testcase.assertEqual([],client.get('/api/accounts/login-drafts').json())
