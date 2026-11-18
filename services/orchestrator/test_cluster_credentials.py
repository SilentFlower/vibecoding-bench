"""具体节点凭据维护的一次提交、原执行停止及崩溃恢复回归。"""
from __future__ import annotations

import json
import hashlib
import threading
import time
import unittest
from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import Mock, patch

from cluster_credentials import NodeCredentials
from cluster_credentials_contract import CredentialRefreshStart, CredentialRefreshWork, CredentialStatusRead, CredentialUsageStart, CredentialUsageWork
from cluster_execution_grants import ExecutionGrant, ExecutionGrants
from cluster_runtime_host import NodeRuntimeHost
from runtime_files import atomic_json
from test_cluster_runtime_host import _HostedRuntime
import test_cluster_execution as execution_fixture


class _ProbeStream:
    """可观察关闭的原Docker响应替身。"""

    def __init__(self, read) -> None:
        """保存单次读取。:param read: 本次字节读取。:return: None。"""
        self.read,self.closed=read,False

    def __iter__(self):
        """延迟读取本次响应。:return: 字节迭代器。"""
        yield self.read()

    def close(self) -> None:
        """标记原响应已释放。:return: None。"""
        self.closed=True


class NodeCredentialTests(unittest.TestCase):
    """真实节点SQLite和有限证明，原Docker执行使用可观察替身。"""

    def setUp(self) -> None:
        """建立独立Node投影和一次具体刷新许可。:return: None。"""
        fixture=execution_fixture.NodeExecutionTests(methodName='runTest')
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        self.fixture,self.executor=fixture,fixture.executor
        self.host=NodeRuntimeHost(self.executor,runtime_factory=_HostedRuntime)
        self.addCleanup(self.host.close)
        self.grants=ExecutionGrants(fixture.root,fixture.node_key,'synthetic',self.executor.database,lambda:1000)
        self.host.attach_grants(self.grants)
        identity=json.dumps({'account_id':1,'binding':None,'uuid':'original-uuid','org':'original-org'},sort_keys=True)
        request=fixture.request.model_copy(update={'account':{**fixture.request.account,'cc2api_account_id':None},
            'gateway_config':{},'cli_only':True,'quota_identity':identity,
            'profile_files':{**fixture.request.profile_files,'.claude.json':json.dumps({'oauthAccount':{
                'accountUuid':'original-uuid','organizationUuid':'original-org'}})}})
        def ensure(runtime,current,*,prepare_sender):
            """投影原固定CLI代次。:param runtime: 原节点。:param current: 账号。:param prepare_sender: 原参数。:return: None。"""
            with runtime.database() as connection:
                connection.execute("UPDATE account_environments SET generation=1,state='ready',container_id='original-cli'")
        with patch.object(_HostedRuntime,'ensure',ensure,create=True):
            self.executor.prepare(request)
        self.work=CredentialRefreshWork(id='d'*32,account_id=1,account_identity=identity,version='2.1.303',force_refresh=True)
        grant=ExecutionGrant(operation_id=self.work.id,node_key=fixture.node_key,account_id=1,gateway_account_id=None,
            environment_id='e'*32,assignment_revision=1,generation=1,source=self.work.source,role='login',not_after=1020)
        self.scope=grant.scope()
        self.grants.create(grant)
        self.request=CredentialRefreshStart(scope=self.scope,work=self.work)
        self.runtime=self.host.runtime
        self.runtime.client=self.executor.client
        atomic_json(fixture.root/'environments'/('e'*32)/'home/.claude.json',{
            'oauthAccount':{'accountUuid':'original-uuid','organizationUuid':'original-org'}})
        self.job=None
        self.active=False
        self.execution_path=fixture.root/'original-execution.json'
        @contextmanager
        def setup(account,source,version,*,exclusive):
            """模拟原独占准备。:param account: 原账号。:param source: 原来源。:param version: 原版本。:param exclusive: 独占。:return: 原作业。"""
            self.assertTrue(exclusive)
            self.active=True
            row=self.runtime._row(account['name'],account['id'])
            self.job={'row':row,'account':account,'source':source,'token':'original-refresh-token','exclusive':True}
            yield row,SimpleNamespace(id='original-cli'),self.job
        self.runtime._cli_setup=setup
        self.runtime.sync_credentials=Mock()
        self.runtime._network_runtime=lambda row:fixture.root/'environments'/row['environment_id']/'runtime/network'
        self.runtime._network_runtime({'environment_id':'e'*32}).mkdir(parents=True)
        self.runtime._configure_network_context=Mock()
        self.runtime._save_execution=lambda job:atomic_json(self.execution_path,{'source':job['source']})
        self.runtime.execution_environment=lambda row:{'TZ':'UTC'}
        self.runtime.authorize_input=lambda job:self.grants.authorize(self.scope)
        self.runtime.register_exec=Mock(side_effect=lambda token,identity:self.job.update(exec=identity))
        self.runtime.restore_execution=Mock(side_effect=lambda *args,**kwargs:self.job if self.active else None)
        self.runtime._execution_path=lambda job:self.execution_path
        self.runtime.environment_jobs=lambda environment:[]
        self.runtime.cleanup=Mock(side_effect=self._cleanup)
        self.runtime._container=Mock(return_value=SimpleNamespace(status='exited',reload=Mock()))
        api=self.runtime.client.api
        api.exec_create.return_value={'Id':'original-refresh-exec'}
        api.exec_inspect.return_value={'Running':False,'ExitCode':0}
        self.stream=_ProbeStream(lambda:b'{"refreshed":true,"expiresAt":9999999,"submitted":true}')
        api.exec_start.return_value=self.stream
        self.actor=NodeCredentials(self.executor,self.host,self.grants,Mock())
        self.addCleanup(self.actor.close)

    def _cleanup(self, token: str) -> None:
        self.assertEqual('original-refresh-token',token)
        self.active=False
        self.execution_path.unlink(missing_ok=True)

    def test_status_reads_current_home_without_starting_or_exporting_credentials(self) -> None:
        """当前HOME与旧profile不一致时只采当前值，实际执行与上游请求保持零。:return: None。"""
        request=CredentialStatusRead(**{key:getattr(self.scope,key) for key in
            ('node_key','account_id','environment_id','assignment_revision','generation')},
            account_identity=self.work.account_identity,version=self.work.version)
        home=self.fixture.root/'environments'/self.scope.environment_id/'home'
        home.mkdir(exist_ok=True)
        atomic_json(home/'.claude.json',{'oauthAccount':{'accountUuid':'original-uuid','organizationUuid':'original-org'}})
        expiry=int((time.time()+3600)*1000)
        atomic_json(home/'.claude/.credentials.json',{'claudeAiOauth':{'accessToken':'current-home-at',
            'refreshToken':'current-home-rt','expiresAt':expiry}})
        value=self.actor.status(request)
        self.assertEqual(expiry,value['status']['oauth_expires_at_ms'])
        self.assertEqual('valid',value['status']['oauth_token_state'])
        self.assertEqual(request.model_dump(),{key:value[key] for key in request.model_dump()})
        self.assertNotIn('current-home-at',json.dumps(value))
        self.assertNotIn('current-home-rt',json.dumps(value))
        self.runtime.client.api.exec_create.assert_not_called()
        self.runtime.sync_credentials.assert_not_called()
        with self.assertRaisesRegex(ValueError,'代次'):
            self.actor.status(request.model_copy(update={'generation':2}))
        with self.assertRaisesRegex(ValueError,'身份'):
            self.actor.status(request.model_copy(update={'account_identity':'other-identity'}))
        (home/'.claude/.credentials.json').unlink()
        self.assertEqual('missing',self.actor.status(request)['status']['oauth_token_state'])
        (home/'.claude.json').unlink()
        self.assertEqual('unknown',self.actor.status(request)['status']['oauth_token_state'])

    def _wait(self, phase: str) -> dict:
        deadline=time.monotonic()+5
        while time.monotonic()<deadline:
            receipt=self.actor.get(self.scope)
            if receipt['phase']==phase:
                return receipt
            time.sleep(.01)
        self.fail('原凭据回执阶段等待超时：'+str(receipt))

    def test_private_material_and_identity_read_current_home_without_runtime_mutation(self) -> None:
        """受信材料读取用当前HOME，身份单独核验冻结版本，全程保持只读。:return: None。"""
        request=CredentialStatusRead(**{key:getattr(self.scope,key) for key in
            ('node_key','account_id','environment_id','assignment_revision','generation')},
            account_identity=self.work.account_identity,version='2.1.293')
        home=self.fixture.root/'environments'/self.scope.environment_id/'home'
        top={'userID':'a'*64,'oauthAccount':{'accountUuid':'original-uuid','organizationUuid':'original-org'}}
        atomic_json(home/'.claude.json',top)
        atomic_json(self.fixture.root/'profiles/synthetic/.claude.json',top)
        expiry=int((time.time()+3600)*1000)
        atomic_json(home/'.claude/.credentials.json',{'claudeAiOauth':{'accessToken':'current-home-at',
            'refreshToken':'current-home-rt','expiresAt':expiry}})
        value=self.actor.material(request)
        self.assertEqual({'access_token':'current-home-at','refresh_token':'current-home-rt','expires_at':expiry},value['material'])
        identity=self.actor.identity(request)
        self.assertEqual('a'*64,identity['identity']['device_id'])
        self.assertEqual('cli:2.1.293:config.userID',identity['identity']['source'])
        self.assertNotIn('current-home-at',json.dumps(identity))
        self.assertNotIn('current-home-rt',json.dumps(identity))
        with self.assertRaisesRegex(ValueError,'尚未验证'):
            self.actor.identity(request.model_copy(update={'version':'2.1.303'}))
        with self.assertRaisesRegex(ValueError,'代次'):
            self.actor.material(request.model_copy(update={'generation':2}))
        self.runtime.client.api.exec_create.assert_not_called()
        self.runtime.sync_credentials.assert_not_called()

    def test_inactive_owner_material_and_identity_stay_pure_while_refresh_and_deleted_reads_refuse(self) -> None:
        """原停用账号仅受信所有者纯读可用，刷新及删除账号继续拒绝。:return: None。"""
        request=CredentialStatusRead(**{key:getattr(self.scope,key) for key in
            ('node_key','account_id','environment_id','assignment_revision','generation')},
            account_identity=self.work.account_identity,version='2.1.293')
        home=self.fixture.root/'environments'/self.scope.environment_id/'home'
        top={'userID':'a'*64,'oauthAccount':{'accountUuid':'original-uuid','organizationUuid':'original-org'}}
        atomic_json(home/'.claude.json',top)
        atomic_json(self.fixture.root/'profiles/synthetic/.claude.json',top)
        atomic_json(home/'.claude/.credentials.json',{'claudeAiOauth':{'accessToken':'inactive-owner-at',
            'refreshToken':'inactive-owner-rt','expiresAt':int((time.time()+3600)*1000)}})
        with self.executor.database() as connection:
            connection.execute('UPDATE accounts SET enabled=0 WHERE id=1')
        self.assertEqual('inactive-owner-rt',self.actor.material(request)['material']['refresh_token'])
        self.assertEqual('a'*64,self.actor.identity(request)['identity']['device_id'])
        with self.assertRaises(ValueError):
            self.actor.start(self.request)
        self.runtime.client.api.exec_create.assert_not_called()
        with self.executor.database() as connection:
            connection.execute('UPDATE accounts SET deleted_at=1 WHERE id=1')
        for operation in (self.actor.material,self.actor.identity):
            with self.subTest(operation=operation.__name__),self.assertRaises(ValueError):
                operation(request)

    def test_usage_claims_nonexclusive_cli_and_releases_only_actual_exec(self) -> None:
        """额度查询复用当前HOME与代理，固定CLI版本安装和RT修改保持关闭。:return: None。"""
        work=CredentialUsageWork(id='f'*32,account_id=1,account_identity=self.work.account_identity,version='2.1.303')
        self.scope=self.scope.model_copy(update={'operation_id':work.id,'source':work.source})
        self.grants.create(ExecutionGrant(**self.scope.model_dump(),not_after=1020))
        request=CredentialUsageStart(scope=self.scope,work=work)
        row=self.runtime._row('synthetic',1)
        self.runtime.ensure=Mock(return_value=(row,SimpleNamespace(id='original-cli')))
        def claim(current,account,source):
            """投影原非独占实际作业。:return: 原执行句柄。"""
            self.active=True
            self.job={'row':current,'account':account,'source':source,'token':'original-refresh-token',
                'exclusive':False,'shared_cli':False}
            return self.job
        self.runtime.claim=Mock(side_effect=claim)
        self.runtime._cli_setup=Mock(side_effect=AssertionError('usage不得安装CLI版本'))
        home=self.runtime._root(row)/'home/.claude/.credentials.json'
        atomic_json(home,{'claudeAiOauth':{'accessToken':'synthetic-current-at','refreshToken':'synthetic-current-rt'}})
        self.stream=_ProbeStream(lambda:b'{"five_hour":{"utilization":23,"resets_at":"2030-01-01T00:00:00Z"}}')
        self.runtime.client.api.exec_start.return_value=self.stream
        self.actor.start(request)
        receipt=self._wait('closed')
        self.assertEqual(23,receipt['outcome']['usage']['five_hour']['utilization'])
        self.assertEqual(receipt,self.actor.start(request))
        self.runtime._cli_setup.assert_not_called()
        self.runtime.claim.assert_called_once_with(row,self.job['account'],work.source)
        self.runtime.client.api.exec_start.assert_called_once()
        options=self.runtime.client.api.exec_create.call_args.kwargs
        self.assertEqual('1',options['environment']['V3_NATIVE_USAGE'])
        self.assertEqual('1020',options['environment']['V3_USAGE_NOT_AFTER'])
        self.assertNotIn('OAUTH_FORCE_REFRESH',options['environment'])
        self.assertFalse(self.job['exclusive'])
        self.runtime.cleanup.assert_called_once()
        self.assertEqual('closed',self.grants.get(self.scope)['phase'])

    def test_refresh_uses_original_home_once_and_releases_actual_execution(self) -> None:
        """重复操作只返回原结果，回执保持固定白名单且实际停止后关闭证明。:return: None。"""
        self.actor.start(self.request)
        receipt=self._wait('closed')
        self.assertEqual('complete',receipt['outcome']['status'])
        self.assertEqual(receipt,self.actor.start(self.request))
        self.runtime.client.api.exec_create.assert_called_once()
        self.runtime.client.api.exec_start.assert_called_once_with('original-refresh-exec',stream=True)
        self.runtime.cleanup.assert_called_once()
        self.runtime.sync_credentials.assert_called_once_with(self.job['row'],self.job['account'])
        options=self.runtime.client.api.exec_create.call_args.kwargs
        self.assertEqual('1000',options['user'])
        self.assertEqual('/home/node',options['environment']['HOME'])
        self.assertEqual('1020',options['environment']['V3_OAUTH_REFRESH_NOT_AFTER'])
        self.assertEqual('closed',self.grants.get(self.scope)['phase'])
        self.assertTrue(self.stream.closed)
        self.assertNotIn('refreshToken',json.dumps(receipt))
        self.assertNotIn('original-uuid',json.dumps(receipt))
        self.assertEqual({},self.host.gateway.snapshots)

    def test_expired_permission_after_exec_create_prevents_actual_start(self) -> None:
        """准备完成后证明过期，原exec保持未提交并可精确停止。:return: None。"""
        def created(*args,**kwargs):
            """模拟创建之后的真实截止。:return: 原execID。"""
            self.grants.clock=lambda:1021
            return {'Id':'unsubmitted-exec'}
        self.runtime.client.api.exec_create.side_effect=created
        self.actor.start(self.request)
        self._wait('reconcile')
        self.runtime.client.api.exec_start.assert_not_called()
        receipt=self.actor.stop(self.scope)
        self.assertEqual({'status':'unsubmitted'},receipt['outcome'])
        self.assertEqual('closed',receipt['phase'])

    def test_unknown_response_survives_actor_restart_without_refresh_replay(self) -> None:
        """已发送后的连接故障保留未知结论，新actor仅恢复原独占停止能力。:return: None。"""
        def failed_read():
            """模拟已提交后的断流。:return: 抛出连接故障。"""
            raise OSError('合成私有刷新正文')
        self.runtime.client.api.exec_start.return_value=_ProbeStream(failed_read)
        self.actor.start(self.request)
        self._wait('reconcile')
        actor=NodeCredentials(self.executor,self.host,self.grants,Mock())
        self.addCleanup(actor.close)
        receipt=actor.stop(self.scope)
        self.assertEqual({'status':'uncertain'},receipt['outcome'])
        self.assertEqual(receipt,actor.start(self.request))
        self.runtime.client.api.exec_start.assert_called_once()
        self.assertTrue(self.runtime.restore_execution.call_args.kwargs['credential_refresh'])
        self.assertNotIn('合成私有刷新正文',json.dumps(receipt))

    def test_home_identity_change_before_exec_start_refuses_original_rt(self) -> None:
        """当前HOME在准备后被换号时，实际exec启动前拒绝使用原许可。:return: None。"""
        def created(*args,**kwargs):
            """在实际启动前替换当前HOME身份。:return: 原未启动exec。"""
            atomic_json(self.fixture.root/'environments'/self.scope.environment_id/'home/.claude.json',{
                'oauthAccount':{'accountUuid':'other-account','organizationUuid':'original-org'}})
            return {'Id':'unsubmitted-exec'}
        self.runtime.client.api.exec_create.side_effect=created
        self.actor.start(self.request)
        self._wait('reconcile')
        self.runtime.client.api.exec_start.assert_not_called()
        receipt=self.actor.stop(self.scope)
        self.assertEqual({'status':'unsubmitted'},receipt['outcome'])
        self.assertEqual('closed',receipt['phase'])

    def test_prepared_cancellation_fences_late_start_and_profile_identity_change(self) -> None:
        """先取消再到达的启动保持墓碑，错误当前身份在激活前拒绝。:return: None。"""
        bad=self.work.model_copy(update={'account_identity':'changed-identity'})
        with self.assertRaisesRegex(ValueError,'身份已经变化'):
            self.actor.start(CredentialRefreshStart(scope=self.scope,work=bad))
        self.assertEqual('prepared',self.grants.get(self.scope)['phase'])
        receipt=self.actor.stop(self.scope)
        self.assertEqual({'status':'unsubmitted'},receipt['outcome'])
        self.assertEqual(receipt,self.actor.start(self.request))
        self.runtime.client.api.exec_create.assert_not_called()

    def test_stop_can_close_during_response_read_without_waiting_for_network(self) -> None:
        """正文读取释放环境锁，原停止可在网络响应未返回时定向收口。:return: None。"""
        reading,release=threading.Event(),threading.Event()
        self.addCleanup(release.set)
        def waiting_read():
            """模拟已启动但上游未结束。:return: 合成不确定结果。"""
            reading.set()
            if not release.wait(5):
                raise TimeoutError('测试响应等待超时')
            return b'not-json'
        self.runtime.client.api.exec_start.return_value=_ProbeStream(waiting_read)
        self.actor.start(self.request)
        self.assertTrue(reading.wait(5))
        receipt=self.actor.stop(self.scope)
        self.assertEqual('closed',receipt['phase'])
        self.assertEqual({'status':'uncertain'},receipt['outcome'])
        self.runtime.cleanup.assert_called_once()
        release.set()

    def test_review_owner_result_is_idempotent_and_bounds_unsubmitted_retries(self) -> None:
        """已知未提交按原待办有限复验，完成事实明确结束同AT待办。:return: None。"""
        parent=self.scope.model_copy(update={'operation_id':'b'*32,'role':'cli','source':'run:abcdef123456:0'})
        request_id=hashlib.sha256(parent.source.encode()).hexdigest()
        work=self.work.model_copy(update={'review_scope':parent,'review_request_id':request_id})
        request=CredentialRefreshStart(scope=self.scope,work=work)
        path=self.fixture.root/'project-review-owner-refresh/1.json'
        atomic_json(path,{'request_id':request_id,'identity':work.account_identity,'source':parent.source,
            'environment_id':parent.environment_id,'environment_generation':parent.generation,'status':'waiting','attempts':0})
        self.runtime.reviews=SimpleNamespace(_refresh_lock=threading.Lock())
        self.actor._finish_review(request,{'status':'unsubmitted'})
        self.actor._finish_review(request,{'status':'unsubmitted'})
        self.assertEqual(1,json.loads(path.read_text())['attempts'])
        next_work=work.model_copy(update={'id':'e'*32})
        next_scope=self.scope.model_copy(update={'operation_id':next_work.id,'source':next_work.source})
        next_request=CredentialRefreshStart(scope=next_scope,work=next_work)
        self.actor._finish_review(next_request,{'status':'unsubmitted'})
        self.assertEqual('error',json.loads(path.read_text())['status'])
        state=json.loads(path.read_text())
        state.update(status='waiting',attempts=0)
        state.pop('maintenance_operation')
        atomic_json(path,state)
        self.actor._finish_review(request,{'status':'complete'})
        self.assertEqual('complete',json.loads(path.read_text())['status'])
