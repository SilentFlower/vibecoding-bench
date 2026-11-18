"""真实SSH与本地TLS上游的独立Node当前HOME刷新验证。"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import threading
import time
from unittest.mock import Mock, patch
from types import SimpleNamespace
from datetime import datetime, timezone

from fastapi.testclient import TestClient
import main

from cluster_credential_refresh import RemoteCredentialRefresh
from cluster_execution_store import NodeExecutions
from cluster_terminal_sessions import TerminalSessions
from credential_ownership import CredentialOwnership
from runtime_files import atomic_json
from verify_cluster_scenario import _restart_node_control
from verify_cluster_account_login import verify_node_account_login, verify_product_account_login


def verify_node_credentials(testcase, service, runtime, node: dict, account: dict, gateway, upstream_root, remote_data) -> None:
    """验证当前HOME权威、严格TLS、实际代理出口及未知RT提交隔离。

    :param testcase: 当前随机部署夹具。
    :param service: 原真实SSH服务。
    :param runtime: 原中央AccountRuntime。
    :param node: 本次隔离节点。
    :param account: 本次合成独立账号。
    :param gateway: 拒绝任何网关调用的替身。
    :param upstream_root: 本次本地TLS上游及脱敏证据。
    :param remote_data: 原节点实际数据根。
    :return: None；所有容器由原随机部署清理。
    """
    if os.environ.get('CLUSTER_DOCKER_TEST')!='1' or not runtime.deployment.startswith('cluster-test-'):
        raise ValueError('凭据验证仅用于本次隔离Docker部署')
    testcase.assertIn('NODE_EXTRA_CA_CERTS=/etc/mitm/cluster-test-ca.pem',
        service.docker(node['id']).images.get(runtime.image).attrs['Config']['Env'])
    actual=runtime._row(account['name'],account['id'])
    root=remote_data/'environments'/actual['environment_id']
    prefix=root/'cli/2.1.303'
    executable=prefix/'node_modules/.bin/claude'
    executable.parent.mkdir(parents=True,exist_ok=True)
    executable.write_text('#!/bin/sh\nprintf "2.1.303\\n"\n')
    executable.chmod(0o755)
    (prefix/'.ready').touch()
    for directory in (prefix,prefix/'node_modules',executable.parent):
        directory.chmod(0o755)
    # 测试镜像仅为本次本地TLS添加CA；证书及主机名继续由Node原生TLS验证。
    authority=root/'public-ca/cluster-test-ca.pem'
    shutil.copyfile(upstream_root/'ca.crt',authority)
    authority.chmod(0o644)
    authority.parent.chmod(0o755)
    home=root/'home/.claude/.credentials.json'
    original=json.loads((remote_data/'profiles'/account['name']/'.credentials.json').read_text())
    original['claudeAiOauth'].update(accessToken='synthetic-current-node-access',refreshToken='synthetic-current-node-refresh')
    atomic_json(home,original)
    os.chown(home,1000,1000)
    stale=runtime.data/'profiles'/account['name']/'.credentials.json'
    copied=json.loads(stale.read_text())
    copied['claudeAiOauth']['refreshToken']='synthetic-stale-central-refresh'
    atomic_json(stale,copied)
    identity=json.dumps({'account_id':account['id'],'binding':None,'uuid':'synthetic-account','org':'synthetic-org'},sort_keys=True)
    owner_lock=threading.Lock()
    callbacks=Mock()
    ownership=CredentialOwnership(runtime,gateway,service.store.database,service.store.lock,
        read_profile=callbacks,mirror=callbacks,mirror_locked=callbacks,profile_lock=callbacks,identity=callbacks,
        read_identity=callbacks,validate=callbacks,find=callbacks,idle=callbacks,available=callbacks,
        creation_payload=callbacks,refresh=callbacks)
    # 原已归还独立所有者的合成持久状态，不包含令牌；实际状态转换使用生产实现。
    operation='a'*32
    ownership._save({'schema':1,'account_id':account['id'],'owner':'local','phase':'ready','stage':'ready',
        'generation':operation,'remote_id':7,'input':{'protocol':1,'operation_id':operation,'action':'prepare','direction':'return',
            'identity':{'bench_account_id':account['id'],'deployment_id':runtime.deployment,
                'environment_id':actual['environment_id'],'device_id':'a'*64,'email':'synthetic@example.invalid',
                'account_uuid':'synthetic-account','organization_uuid':'synthetic-org'}}})
    sessions=TerminalSessions(NodeExecutions(service.store,runtime.release_id),service,runtime,gateway,
        Mock(side_effect=AssertionError('凭据维护不应认领模型额度')),Mock(side_effect=AssertionError('凭据维护不应释放模型额度')))
    testcase.addCleanup(sessions.close)
    coordinator=RemoteCredentialRefresh(sessions,ownership,lambda name:owner_lock,lambda current:identity,lambda current:'2.1.303')
    testcase.addCleanup(coordinator.close)
    testcase.assertTrue(coordinator.refresh(account,force_refresh=True))
    current=json.loads(home.read_text())['claudeAiOauth']
    testcase.assertTrue(current['accessToken'].startswith('synthetic-refreshed-'))
    testcase.assertEqual('synthetic-current-node-refresh',current['refreshToken'])
    testcase.assertEqual(copied,json.loads(stale.read_text()))
    testcase.assertEqual('ready',ownership.state(account['id'])['phase'])
    testcase.assertEqual([],sessions.ledger.pending())
    observed=coordinator.status(account)
    testcase.assertEqual('valid',observed['oauth_token_state'])
    testcase.assertEqual(current['expiresAt'],observed['oauth_expires_at_ms'])
    testcase.assertEqual('node-home',observed['oauth_status_source'])
    testcase.assertIsNotNone(observed['oauth_observed_at'])
    testcase.assertNotIn(current['accessToken'],json.dumps(observed))
    testcase.assertNotIn(current['refreshToken'],json.dumps(observed))
    copied['claudeAiOauth']['expiresAt']=1
    atomic_json(stale,copied)
    testcase.assertEqual('valid',coordinator.status(account,observe=True)['oauth_token_state'])
    testcase.assertEqual(copied,json.loads(stale.read_text()))
    records=[json.loads(line) for line in (upstream_root/'evidence.jsonl').read_text().splitlines()]
    sent=[item for item in records if item['kind']=='oauth-refresh']
    testcase.assertEqual(1,len(sent))
    body={'grant_type':'refresh_token','refresh_token':'synthetic-current-node-refresh','client_id':'9d1c250a-e61b-44d9-88ed-5944d1962f5e'}
    testcase.assertEqual(hashlib.sha256(json.dumps(body,separators=(',',':')).encode()).hexdigest(),sent[0]['body_sha256'])
    testcase.assertEqual('platform.claude.com',sent[0]['host'])
    network=service.docker(node['id']).containers.get(runtime._row(account['name'],account['id'])['network_container_id'])
    network.reload()
    addresses={item['IPAddress'] for item in network.attrs['NetworkSettings']['Networks'].values()}
    testcase.assertTrue(any(item['kind']=='proxy' and item['target']=='198.18.0.10'
        and item['port']==443 and item['peer'] in addresses for item in records))
    testcase.assertFalse(coordinator.refresh(account))
    records=[json.loads(line) for line in (upstream_root/'evidence.jsonl').read_text().splitlines()]
    testcase.assertEqual(1,sum(item['kind']=='oauth-refresh' for item in records))
    if os.environ.get('CLUSTER_TEST_CREDENTIAL_LOGIN')=='1':
        if os.environ.get('CLUSTER_TEST_CREDENTIAL_LOGIN_API')=='1':
            verify_product_account_login(testcase,runtime,account,coordinator,sessions,root,upstream_root,ownership,owner_lock)
            callbacks.assert_not_called()
            return
        verify_node_account_login(testcase,runtime,account,coordinator,sessions,root)
        callbacks.assert_not_called()
        return
    if os.environ.get('CLUSTER_TEST_CREDENTIAL_USAGE')=='1':
        _verify_usage(testcase,service,runtime,node,account,coordinator,sessions,ownership,owner_lock,upstream_root,root)
        callbacks.assert_not_called()
        return
    if os.environ.get('CLUSTER_TEST_CREDENTIAL_RECOVERY')=='1':
        _verify_refresh_restart(testcase,service,runtime,account,coordinator,sessions,ownership,upstream_root,root)
        callbacks.assert_not_called()
        return
    (upstream_root/'oauth-drop-response').touch()
    with testcase.assertRaises(ValueError):
        coordinator.refresh(account,force_refresh=True)
    pending=sessions.ledger.pending()
    testcase.assertEqual(1,len(pending))
    old=sessions.ledger.get(pending[0])
    testcase.assertEqual('closed',old['record']['node_receipt']['phase'])
    testcase.assertEqual({'status':'uncertain'},old['record']['node_receipt']['outcome'])
    testcase.assertTrue(ownership.state(account['id'])['refresh_pending'])
    coordinator.recover_pending()
    with testcase.assertRaises(ValueError):
        coordinator.refresh(account,force_refresh=True)
    records=[json.loads(line) for line in (upstream_root/'evidence.jsonl').read_text().splitlines()]
    testcase.assertEqual(2,sum(item['kind']=='oauth-refresh' for item in records))
    testcase.assertEqual(pending,sessions.ledger.pending())
    callbacks.assert_not_called()


def _verify_usage(testcase,service,runtime,node,account,coordinator,sessions,ownership,owner_lock,upstream_root,root) -> None:
    """沿真实中央HTTP、SSH、当前HOME及Node原生TLS验证手动额度。

    :param testcase: 当前随机部署夹具。
    :param service: 原SSH服务。
    :param runtime: 原中央运行时。
    :param node: 原账号所属节点。
    :param account: 本次合成独立账号。
    :param coordinator: 原凭据及额度协调器。
    :param sessions: 原中央执行账本。
    :param ownership: 原唯一凭据所有权。
    :param owner_lock: 原不可重入owner锁。
    :param upstream_root: 本次合成本地TLS上游。
    :param root: 本次Node实际账号环境。
    :return: None；实际执行与中央许可严格释放后返回。
    """
    now=time.time()
    reset=lambda delta:datetime.fromtimestamp(now+delta,timezone.utc).isoformat()
    windows={'five_hour':{'utilization':12,'resets_at':reset(3600)},
        'seven_day':{'utilization':33,'resets_at':reset(86400)},
        'limits':[{'kind':'weekly_scoped','percent':14,'resets_at':reset(86400),
            'scope':{'model':{'display_name':'Fable'}}}],'spend':{'amount':1},'extra_usage':{'is_enabled':False}}
    atomic_json(upstream_root/'oauth-usage-windows.json',windows)
    central=object.__new__(main.Runner)
    central.client=Mock(side_effect=AssertionError('中央Docker不应执行独立Node额度查询'))
    guard=main.QuotaGuard(central)
    profile=runtime.data/'profiles'/account['name']/'.credentials.json'
    stale=profile.read_bytes()
    home=root/'home/.claude/.credentials.json'
    current=home.read_bytes()
    owner=ownership.state(account['id'])
    with patch.object(main,'runner',central),patch.object(main,'account_runtime',runtime), \
            patch.object(main,'cluster_service',service),patch.object(main,'cluster_runner',SimpleNamespace(credentials=coordinator)), \
            patch.object(main,'get_db',service.store.database),patch.object(main,'_db_lock',service.store.lock), \
            patch.object(main,'BENCH_DATA',runtime.data),patch.object(main,'PROFILES_DIR',runtime.data/'profiles'), \
            patch.object(main,'quota_guard',guard),patch.object(main,'_oauth_owner_lock',lambda name:owner_lock), \
            patch.object(main,'V3_ENABLED',True),patch.dict(os.environ,{'V3_INTERNAL_TOKEN':'c'*64}):
        client=TestClient(main.app,headers={'Authorization':'Bearer '+'c'*64})
        testcase.addCleanup(client.close)
        response=client.post('/api/accounts/'+str(account['id'])+'/quota')
        testcase.assertEqual(200,response.status_code,response.text)
        result=response.json()
        testcase.assertTrue(result['ok'],result)
        testcase.assertEqual(12,result['five_hour']['utilization'])
        testcase.assertEqual(33,result['seven_day']['utilization'])
        testcase.assertEqual(14,result['seven_day_fable']['utilization'])
        testcase.assertEqual(windows,result['raw'])
        observed=guard.snapshot(account)
        testcase.assertEqual(12,observed['windows']['five_hour']['utilization'])
        testcase.assertEqual(33,observed['windows']['seven_day']['utilization'])
        testcase.assertAlmostEqual(14,observed['windows']['seven_day_fable']['utilization'])
        for status,code in ((429,'rate_limit_error'),(401,'authentication_error'),(401,'account_on_hold')):
            atomic_json(upstream_root/'oauth-usage-status.json',{'status':status,'retry_after':17,
                'body':{'error':{'type':code,'message':'synthetic-private-upstream-text'}}})
            response=client.post('/api/accounts/'+str(account['id'])+'/quota')
            testcase.assertEqual(200,response.status_code,response.text)
            testcase.assertFalse(response.json()['ok'])
            testcase.assertNotIn('synthetic-private-upstream-text',response.text)
            observed=guard.snapshot(account)
            testcase.assertEqual('account_on_hold' if code=='account_on_hold' else None,observed.get('account_error'))
            testcase.assertEqual(12,observed['windows']['five_hour']['utilization'])
        (upstream_root/'oauth-usage-status.json').unlink()
        if os.environ.get('CLUSTER_TEST_CREDENTIAL_USAGE_RECOVERY')=='1':
            _verify_usage_restart(testcase,client,service,runtime,account,coordinator,sessions,ownership,upstream_root,root)
    records=[json.loads(line) for line in (upstream_root/'evidence.jsonl').read_text().splitlines()]
    usage=[item for item in records if item['kind']=='oauth-usage']
    testcase.assertEqual(5 if os.environ.get('CLUSTER_TEST_CREDENTIAL_USAGE_RECOVERY')=='1' else 4,len(usage))
    digest=hashlib.sha256(('Bearer '+json.loads(current)['claudeAiOauth']['accessToken']).encode()).hexdigest()
    testcase.assertTrue(all(item['host']=='api.anthropic.com' and item['authorization_sha256']==digest
        and item['tls_version'].startswith('TLS') for item in usage))
    testcase.assertEqual(1,sum(item['kind']=='oauth-refresh' for item in records))
    testcase.assertEqual(stale,profile.read_bytes())
    testcase.assertEqual(current,home.read_bytes())
    testcase.assertEqual(owner,ownership.state(account['id']))
    testcase.assertEqual([],sessions.ledger.pending())
    testcase.assertEqual({},sessions.activities)


def _verify_usage_restart(testcase,client,service,runtime,account,coordinator,sessions,ownership,upstream_root,root) -> None:
    """实际usage已发后强杀NodeControl，中央只读恢复原操作并严格释放。

    :param testcase: 当前合成夹具。
    :param client: 原中央真实HTTP客户端。
    :param service: 原SSH服务。
    :param runtime: 原中央运行时。
    :param account: 原独立账号。
    :param coordinator: 原具体维护协调器。
    :param sessions: 原执行账本。
    :param ownership: 原RT所有者。
    :param upstream_root: 原本地TLS证据根。
    :param root: 原Node账号环境。
    :return: None；原实际exec停止确认后才释放中央占用。
    """
    (upstream_root/'oauth-usage-hold-response').touch()
    (upstream_root/'oauth-usage-drop-response').touch()
    owner=ownership.state(account['id'])
    outcomes=[]
    def query() -> None:
        """发送一次原额度HTTP请求并保存固定结论。:return: None。"""
        try:
            response=client.post('/api/accounts/'+str(account['id'])+'/quota')
            outcomes.append((response.status_code,response.json()))
        except Exception as error:
            outcomes.append(type(error).__name__)
    worker=threading.Thread(target=query,daemon=True)
    worker.start()
    def release_response() -> None:
        """失败路径也结束本次合成响应等待。:return: None。"""
        (upstream_root/'oauth-usage-hold-response').unlink(missing_ok=True)
        worker.join(timeout=15)
    testcase.addCleanup(release_response)
    deadline=time.monotonic()+45
    while True:
        records=[json.loads(line) for line in (upstream_root/'evidence.jsonl').read_text().splitlines()]
        if sum(item['kind']=='oauth-usage' for item in records)==5:
            break
        testcase.assertTrue(worker.is_alive(),'原实际usage发出前查询已结束')
        testcase.assertLess(time.monotonic(),deadline,'原Node usage尚未到达真实TLS上游')
        time.sleep(.05)
    operation=sessions.ledger.get(sessions.ledger.pending()[0])
    execution=json.loads((root/'runtime/execution.json').read_text())
    testcase.assertEqual('credential-usage',execution['execution_role'])
    testcase.assertFalse(execution['exclusive'])
    testcase.assertIsNone(execution['lease'])
    testcase.assertEqual(operation['source'],execution['source'])
    try:
        _restart_node_control(testcase,service,runtime,operation)
        worker.join(timeout=30)
        testcase.assertFalse(worker.is_alive(),'原查询观察仍等待控制进程')
        testcase.assertTrue(outcomes)
        if isinstance(outcomes[0],tuple):
            status,result=outcomes[0]
            testcase.assertIn(status,(200,409))
            testcase.assertFalse(result.get('ok',False))
        coordinator.recover_pending()
        row=sessions.ledger.get(operation['operation_id'])
        testcase.assertEqual('closed',row['phase'])
        testcase.assertEqual('closed',row['record']['node_receipt']['phase'])
        testcase.assertTrue(row['record']['local_admission_released'])
        testcase.assertFalse(service.docker(operation['node_id']).api.exec_inspect(execution['exec'])['Running'])
        testcase.assertFalse((root/'runtime/execution.json').exists())
        testcase.assertEqual(owner,ownership.state(account['id']))
        testcase.assertEqual({},sessions.activities)
        coordinator.recover_pending()
        records=[json.loads(line) for line in (upstream_root/'evidence.jsonl').read_text().splitlines()]
        testcase.assertEqual(5,sum(item['kind']=='oauth-usage' for item in records))
    finally:
        release_response()


def _verify_refresh_restart(testcase,service,runtime,account,coordinator,sessions,ownership,upstream_root,root) -> None:
    """实际RT已发送时强杀NodeControl，旧独占exec恢复停止后继续隔离未知结果。

    :param testcase: 本次合成断言。
    :param service: 原SSH服务。
    :param runtime: 原中央运行时。
    :param account: 原合成独立账号。
    :param coordinator: 原具体刷新协调器。
    :param sessions: 原中央执行账本。
    :param ownership: 原持久所有者。
    :param upstream_root: 原本地TLS证据根。
    :param root: 原实际Node环境根。
    :return: None；实际容器由本次随机部署清理。
    """
    (upstream_root/'oauth-hold-response').touch()
    (upstream_root/'oauth-drop-response').touch()
    failures=[]
    def refresh() -> None:
        """记录受控失败类型，正文与令牌继续留在原Node。:return: None。"""
        try:
            coordinator.refresh(account,force_refresh=True)
        except Exception as error:
            failures.append(type(error).__name__)
    worker=threading.Thread(target=refresh,daemon=True)
    worker.start()
    def release_response() -> None:
        """失败时也结束本次合成响应等待及原观察线程。:return: None。"""
        (upstream_root/'oauth-hold-response').unlink(missing_ok=True)
        worker.join(timeout=15)
    testcase.addCleanup(release_response)
    deadline=time.monotonic()+45
    while True:
        records=[json.loads(line) for line in (upstream_root/'evidence.jsonl').read_text().splitlines()]
        if sum(item['kind']=='oauth-refresh' for item in records)==2:
            break
        testcase.assertTrue(worker.is_alive(),'实际RT发送前刷新线程已结束')
        testcase.assertLess(time.monotonic(),deadline,'原Node RT尚未到达真实TLS上游')
        time.sleep(.05)
    pending=sessions.ledger.pending()
    testcase.assertEqual(1,len(pending))
    operation=sessions.ledger.get(pending[0])
    execution=json.loads((root/'runtime/execution.json').read_text())
    testcase.assertEqual('credential-refresh',execution['execution_role'])
    testcase.assertTrue(execution['exclusive'])
    testcase.assertIsNone(execution['lease'])
    testcase.assertEqual(operation['source'],execution['source'])
    try:
        _restart_node_control(testcase,service,runtime,operation)
        worker.join(timeout=30)
        testcase.assertFalse(worker.is_alive(),'控制进程重启后的原观察线程尚未结束')
        testcase.assertTrue(failures)
        coordinator.recover_pending()
        row=sessions.ledger.get(operation['operation_id'])
        testcase.assertEqual('reconcile',row['phase'])
        testcase.assertEqual('closed',row['record']['node_receipt']['phase'])
        testcase.assertEqual({'status':'uncertain'},row['record']['node_receipt']['outcome'])
        observed=service.docker(operation['node_id']).api.exec_inspect(execution['exec'])
        testcase.assertFalse(observed['Running'])
        testcase.assertFalse((root/'runtime/execution.json').exists())
        testcase.assertTrue(ownership.state(account['id'])['refresh_pending'])
        testcase.assertEqual(1,len(sessions.activities))
        coordinator.recover_pending()
        with testcase.assertRaises(ValueError):
            coordinator.refresh(account,force_refresh=True)
        records=[json.loads(line) for line in (upstream_root/'evidence.jsonl').read_text().splitlines()]
        testcase.assertEqual(2,sum(item['kind']=='oauth-refresh' for item in records))
        testcase.assertEqual(pending,sessions.ledger.pending())
    finally:
        release_response()
