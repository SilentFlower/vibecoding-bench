"""NULL草稿Node登录、取消保留、产物恢复和共享登录核心回归。"""
from __future__ import annotations

import json
import shutil
import threading
import time
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from account_runtime import AccountRuntime
from cluster_draft_login import NodeDraftLogins
from cluster_draft_login_contract import DraftLoginAccept, DraftLoginActivation, DraftLoginCode, DraftLoginGrant, DraftLoginPreparation, DraftLoginScope, DraftLoginSnapshot, DraftLoginStart, DraftLoginWork, DraftLoginSettings, draft_preparation_sha256
from cluster_draft_login_grants import DraftLoginGrants
from cluster_execution import _GatewaySnapshot
from cluster_execution_grants import ExecutionGrants
from cluster_runtime_host import NodeRuntimeHost
from runtime_files import atomic_json
from test_cluster_runtime_host import _HostedRuntime
import test_cluster_execution as execution_fixture


class _DraftRuntime(_HostedRuntime):
    """沿真实Host构造与SQLite投影，Docker和CLI采用可观察的离线替身。"""

    def __init__(self, client, data, host_data, database, fingerprint, gateway, quota_identity) -> None:
        """登记真实Host依赖及合成CLI状态。

        :param client: 本次Docker替身。
        :param data: 原私有根。
        :param host_data: 原宿主根。
        :param database: 原SQLite。
        :param fingerprint: 原画像提供器。
        :param gateway: 原受限配置。
        :param quota_identity: 原额度提供器。
        :return: None。
        """
        super().__init__(client,data,host_data,database,fingerprint,gateway,quota_identity)
        self.client,self.jobs,self.lock=client,{},threading.RLock()
        self.container=SimpleNamespace(id='synthetic-draft-cli',status='running',reload=Mock(),exec_run=Mock(return_value=SimpleNamespace(exit_code=1)))
        self.begin_calls,self.recover_calls=0,0
        self.cleanup_failure=False
        self.stop_calls=0
        self.client.containers.list.return_value=[]
        self.reviews=SimpleNamespace(serial_state=Mock(return_value=None),check_orphans=Mock())
        self._running_sender_active=Mock(return_value=False)
        self.role_status=Mock(return_value={'cli':'running'})
        self.exec_cli=Mock(return_value=SimpleNamespace(exit_code=0,output=b'{"loggedIn":true,"authMethod":"oauth"}'))
        self.login_terminal_alive=Mock(return_value=True)
        self.capture_login_pane=Mock(return_value='')
        self.send_login_code=Mock()
        self.read_cli_identity=Mock(return_value={'device_id':'original-device','source':'synthetic:config.userID'})

    _row=AccountRuntime._row
    execution_token=staticmethod(AccountRuntime.execution_token)
    authorize_input=AccountRuntime.authorize_input
    _save_execution=AccountRuntime._save_execution
    _publish_login_home=AccountRuntime._publish_login_home
    restore_execution=AccountRuntime.restore_execution
    _update=AccountRuntime._update
    _labels=AccountRuntime._labels

    def ensure(self, account: dict, **options):
        """模拟同一NULL环境的准备，重复准备保留真实代次。:param account: 原草稿。:param options: 原参数。:return: 环境与容器。"""
        if account.get('id') is not None or options.get('prepare_sender') is not False:
            raise ValueError('合成草稿准备范围错误')
        connection=self.database()
        try:
            with connection:
                connection.execute("UPDATE account_environments SET generation=CASE WHEN generation=0 THEN 2 ELSE generation END,"
                    "state='ready',container_id='synthetic-draft-cli' WHERE name=?",(account['name'],))
        finally:
            connection.close()
        return self._row(account['name']),self.container

    def environment_jobs(self, environment_id: str) -> list[dict]:
        """读取本替身原实际工作。:param environment_id: 原环境。:return: 原作业。"""
        return [job for job in self.jobs.values() if job['row']['environment_id']==environment_id]

    def _claim(self, sid, account, version):
        row=self._row(account['name'])
        job={'row':row,'account':account,'source':'login:'+sid,'token':self.execution_token(self.container.id,'login:'+sid),
            'exclusive':True,'shared_cli':False,'lease':None,'claimed':True,'version':version}
        self.jobs[row['environment_id']]=job
        self._save_execution(job)
        self.authorize_input(job)
        return row,job

    def begin_login(self, sid, account, version, force):
        """模拟实际一次授权并写合成产物，真实许可在输入前核对。:return: 原NULL环境、容器、profile和HOME。"""
        self.begin_calls+=1
        row,job=self._claim(sid,account,version)
        home='/home/node/.v3-login/'+sid
        profile=self._root(row)/'home/.v3-login'/sid/'.claude'
        atomic_json(profile/'.credentials.json',{'claudeAiOauth':{'accessToken':'synthetic-at','refreshToken':'synthetic-rt',
            'expiresAt':int((time.time()+3600)*1000)},'unknown_credentials':{'preserved':True}})
        atomic_json(profile.parent/'.claude.json',{'userID':'original-device','unknown_top':{'preserved':True},
            'oauthAccount':{'emailAddress':'draft@example.invalid','accountUuid':'synthetic-uuid'}})
        atomic_json(profile/'settings.json',{'unknown_settings':{'preserved':True}})
        job.update(tmux=sid,tmux_socket='/tmp/v3-login-'+sid+'.sock',home=home)
        self._save_execution(job)
        return row,self.container,profile,home

    def recover_login(self, sid, account, version, home):
        """只认领产物检查的维护作业。:return: 原环境和容器。"""
        self.recover_calls+=1
        row,job=self._claim(sid,account,version)
        job['execution_role']='draft-login-recovery'
        self._save_execution(job)
        return row,self.container

    def job_for_container(self, token):
        """定位本次实际作业。:return: 原job。"""
        return next(job for job in self.jobs.values() if job['token']==token)

    def _execution_path(self, job):
        return self._root(job['row'])/'runtime/execution.json'

    def environment_lock(self, environment_id):
        """真实恢复函数沿原环境锁顺序核对内存作业。:return: 本次RLock。"""
        return self.lock

    def cleanup(self, token):
        """模拟实际停止与登记删除，注入故障时保留现场。:return: None。"""
        if self.cleanup_failure:
            raise RuntimeError('synthetic stop failure')
        job=self.job_for_container(token)
        self.jobs.pop(job['row']['environment_id'])
        self._execution_path(job).unlink()

    def _container(self, row):
        return self.container

    def _stop_environment(self, row, remove=False):
        self.stop_calls+=1
        if remove:
            self._update(row,container_id=None,network_container_id=None,sender_container_id=None)


class NodeDraftLoginTests(unittest.TestCase):
    """真实私有文件/SQLite/NodeHost与草稿许可，CLI使用离线替身。"""

    def setUp(self) -> None:
        """建立独立节点，准备原NULL草稿资源。:return: None。"""
        fixture=execution_fixture.NodeExecutionTests(methodName='runTest')
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        self.executor,self.data=fixture.executor,fixture.root
        self.host=NodeRuntimeHost(self.executor,runtime_factory=_DraftRuntime)
        self.addCleanup(self.host.close)
        self.formal_grants=ExecutionGrants(self.data,self.executor.node_key,'synthetic',self.executor.database)
        self.host.attach_grants(self.formal_grants)
        self.grants=DraftLoginGrants(self.data,self.executor.node_key,'synthetic',self.executor.database)
        self.actor=NodeDraftLogins(self.executor,self.host,self.grants)
        self.addCleanup(self.actor.close)
        settings=DraftLoginSettings(name='draft_only',timezone='UTC',upstream_socks5_pass='synthetic-private-proxy')
        fingerprint='{"tz":"UTC"}'
        files={'.claude.json':'{"userID":"original-device"}','settings.json':'{}'}
        self.work=DraftLoginWork(id='a'*32,sid='c'*12,environment_id='e'*32,name=settings.name,draft_generation='d'*32,
            version='2.1.293',home='/home/node/.v3-login/'+'c'*12,
            preparation_sha256=draft_preparation_sha256(settings,fingerprint,files),expires_at=int(time.time())+900)
        self.preparation=DraftLoginPreparation(node_key=self.executor.node_key,work=self.work,settings=settings,
            fingerprint_json=fingerprint,profile_files=files)

    def prepared(self):
        """准备资源后发放原实际范围的有限证明。:return: 本次原Scope。"""
        marker=self.actor.prepare(self.preparation)
        scope=DraftLoginScope.model_validate(marker['scope'])
        self.grants.create(DraftLoginGrant(**scope.model_dump(),not_after=int(time.time())+30))
        self.scope=scope
        return scope

    def ready(self):
        """等待原异步登录实际准备完成。:return: 原ready回执。"""
        self.actor.start(DraftLoginStart(scope=self.scope,work=self.work))
        deadline=time.monotonic()+5
        while time.monotonic()<deadline:
            receipt=self.actor.get(self.scope)
            if receipt['phase']=='ready':
                return receipt
            if receipt['phase']=='reconcile':
                self.fail('合成草稿登录需要核对：'+str(receipt))
            time.sleep(.01)
        self.fail('合成草稿登录准备超时')

    def test_prepare_keeps_null_and_borrows_existing_host_without_replacing_gateway_configuration(self) -> None:
        """草稿准备复用同一真实Host，已有网关配置继续保持原对象。:return: None。"""
        original=_GatewaySnapshot(7,{'synthetic':'existing'},bench_account_id=19)
        self.host.gateway.adopt(original,lambda account:'synthetic-quota')
        marker=self.actor.prepare(self.preparation)
        self.assertEqual(marker,self.actor.prepare(self.preparation))
        self.assertIs(original,self.host.gateway.snapshots[7])
        runtime=self.host.runtime
        runtime.start.assert_called_once()
        self.assertEqual(0,runtime.begin_calls)
        connection=self.executor.database()
        try:
            self.assertEqual(0,connection.execute('SELECT count(*) FROM accounts').fetchone()[0])
            self.assertIsNone(connection.execute('SELECT account_id FROM account_environments').fetchone()[0])
        finally:
            connection.close()
        self.assertNotIn('synthetic-private-proxy',json.dumps(marker))

    def test_first_prepare_refuses_orphan_profile_before_adopting_its_credentials(self) -> None:
        """没有原准备证明的旧profile不能被新NULL草稿接管。:return: None。"""
        atomic_json(self.data/'profiles'/self.work.name/'.credentials.json',{'synthetic':'orphan-private'})
        with self.assertRaisesRegex(ValueError,'遗留profile'):
            self.actor.prepare(self.preparation)
        self.assertIsNone(self.host.runtime)

    def test_summary_reads_presence_without_starting_runtime_or_certifying_credentials(self) -> None:
        """只读摘要保持原代次，运行时未装载时显示未知角色；文件存在单独表达。:return: None。"""
        self.prepared()
        runtime=self.host.runtime
        self.host.runtime=None
        try:
            summary=self.actor.summary(self.scope)
            self.assertFalse(summary['credentials_present'])
            self.assertEqual('unknown',summary['container_status'])
            self.assertIsNone(self.host.runtime)
        finally:
            self.host.runtime=runtime
        self.ready()
        self.actor.discard(self.scope)
        summary=self.actor.summary(self.scope)
        self.assertTrue(summary['credentials_present'])
        self.assertNotIn('credentials_ready',summary)
        self.assertNotIn('synthetic-private-proxy',json.dumps(summary))
        self.assertNotIn('synthetic-rt',json.dumps(summary))
        runtime.start.assert_called_once()

    def test_login_starts_once_and_authorization_code_duplicate_only_reads_original_receipt(self) -> None:
        """同操作只启动一次，重复码请求沿草稿Scope复用原回执。:return: None。"""
        self.prepared()
        receipt=self.ready()
        self.assertEqual(receipt,self.actor.start(DraftLoginStart(scope=self.scope,work=self.work)))
        self.assertEqual(1,self.host.runtime.begin_calls)
        code=DraftLoginCode(scope=self.scope,request_id='f'*32,code='synthetic-auth-code')
        delivered=self.actor.code(code)
        self.assertEqual('delivered',delivered['status'])
        self.assertEqual(delivered,self.actor.code(code))
        self.host.runtime.send_login_code.assert_called_once()
        self.assertNotIn('synthetic-auth-code',(self.actor._directory(self.scope)/'codes'/('f'*32+'.json')).read_text())

    def test_cancel_stops_and_preserves_products_then_recover_checks_same_home_without_new_authorization(self) -> None:
        """取消保留原产物，新SID恢复只检查原HOME，不创建第二次授权。:return: None。"""
        self.prepared()
        self.ready()
        old_scope,old_home=self.scope,self.work.home
        product=self.actor._session_profile(DraftLoginStart(scope=self.scope,work=self.work)) / '.credentials.json'
        closed=self.actor.discard(self.scope)
        self.assertEqual('closed',closed['phase'])
        self.assertTrue(product.is_file())
        self.work=self.work.model_copy(update={'id':'f'*32,'sid':'f'*12,'draft_generation':'f'*32,'mode':'recover'})
        self.preparation=DraftLoginPreparation(**{**self.preparation.model_dump(),'work':self.work,'previous':old_scope})
        self.prepared()
        self.ready()
        self.assertEqual((1,1),(self.host.runtime.begin_calls,self.host.runtime.recover_calls))
        self.assertEqual(old_home,self.actor.sessions[self.scope.operation_id].home)
        observed=self.actor.observe(self.scope)
        self.assertTrue(observed['credentials_ready'])
        self.assertFalse(observed['reconnectable'])
        committed=self.actor.commit(self.scope)
        snapshot=DraftLoginSnapshot.model_validate(self.actor.snapshot(self.scope))
        self.assertEqual('synthetic-rt',snapshot.material.refresh_token)
        self.actor.accept(DraftLoginAccept(scope=self.scope,authorization_sha256=committed['commit']['authorization_sha256']))
        self.assertFalse(product.parent.parent.exists())

    def test_commit_preserves_unknown_files_and_formal_identity_stays_null_until_central_transaction(self) -> None:
        """原完整文件在Node冻结与发布时保留未知字段，接受后实际停止并清理暂存。:return: None。"""
        self.prepared()
        self.ready()
        committed=self.actor.commit(self.scope)
        self.assertEqual('saved',committed['commit']['stage'])
        index=self.actor.files(self.scope)
        self.assertEqual(committed['commit']['authorization_sha256'],index['authorization_sha256'])
        self.assertEqual(set(committed['commit']['files']),set(index['files']))
        self.assertNotIn('synthetic-rt',json.dumps(index))
        home=self.data/'environments'/self.scope.environment_id/'home'
        self.assertEqual({'preserved':True},json.loads((home/'.claude.json').read_text())['unknown_top'])
        self.assertEqual({'preserved':True},json.loads((home/'.claude/.credentials.json').read_text())['unknown_credentials'])
        self.assertEqual({'preserved':True},json.loads((home/'.claude/settings.json').read_text())['unknown_settings'])
        with self.assertRaises(ValueError):
            self.actor.discard(self.scope)
        accepted=self.actor.accept(DraftLoginAccept(scope=self.scope,authorization_sha256=committed['commit']['authorization_sha256']))
        self.assertEqual(('closed',False),(accepted['phase'],accepted['commit']['cleanup_pending']))
        with self.assertRaises(ValueError):
            self.actor.files(self.scope)
        self.assertEqual([],self.host.runtime.environment_jobs(self.scope.environment_id))
        connection=self.executor.database()
        try:
            self.assertIsNone(connection.execute('SELECT account_id FROM account_environments').fetchone()[0])
            self.assertEqual(0,connection.execute('SELECT count(*) FROM accounts').fetchone()[0])
        finally:
            connection.close()

    def test_failed_stop_keeps_proof_and_products_for_same_operation_retry(self) -> None:
        """实际停止失败保留原工作和授权文件，重试沿原范围收口。:return: None。"""
        self.prepared()
        self.ready()
        self.host.runtime.cleanup_failure=True
        with self.assertRaises(RuntimeError):
            self.actor.discard(self.scope)
        self.assertEqual('active',self.grants.get(self.scope)['phase'])
        self.assertEqual('ready',self.actor.get(self.scope)['phase'])
        self.host.runtime.cleanup_failure=False
        self.assertEqual('closed',self.actor.discard(self.scope)['phase'])

    def test_runtime_null_permission_does_not_allow_formal_or_non_login_work(self) -> None:
        """原运行时回调只给精确NULL登录放行，其他身份保持原正ID合同。:return: None。"""
        self.prepared()
        self.ready()
        runtime=self.host.runtime
        job=next(iter(runtime.jobs.values()))
        self.host.gateway.lease_mirror.authorize_job(job)
        for changed in ({'account':{**job['account'],'id':17}}, {'source':'run:synthetic:0'},
                {'row':{**job['row'],'account_id':17}}, {'exclusive':False}):
            with self.subTest(changed=changed),self.assertRaises(ValueError):
                self.host.gateway.lease_mirror.authorize_job({**job,**changed})

    def test_reconcile_state_closes_input_and_still_allows_original_actual_stop(self) -> None:
        """重启隔离后停止能力仍沿原NULL范围，新的码输入保持关闭。:return: None。"""
        self.prepared()
        self.ready()
        connection=self.executor.database()
        try:
            with connection:
                connection.execute("UPDATE account_environments SET state='cli_reconcile'")
        finally:
            connection.close()
        with self.assertRaises(ValueError):
            self.actor.code(DraftLoginCode(scope=self.scope,request_id='f'*32,code='synthetic-code'))
        self.assertEqual('closed',self.actor.stop(self.scope)['phase'])

    def test_activation_after_actual_accept_promotes_real_id_without_reusing_draft_roles(self) -> None:
        """真实ID只在原授权收口后投影，草稿角色移除而HOME/画像保持。:return: None。"""
        self.prepared()
        self.ready()
        committed=self.actor.commit(self.scope)
        request=DraftLoginActivation(scope=self.scope,account_id=17,authorization_sha256=committed['commit']['authorization_sha256'])
        with self.assertRaises(ValueError):
            self.actor.activate(request)
        self.actor.accept(DraftLoginAccept(scope=self.scope,authorization_sha256=request.authorization_sha256))
        home=self.data/'environments'/self.scope.environment_id/'home/.claude/.credentials.json'
        original=home.read_bytes()
        activated=self.actor.activate(request)
        self.assertEqual('activated',activated['phase'])
        self.assertEqual(activated,self.actor.activate(request))
        self.assertEqual(1,self.host.runtime.stop_calls)
        self.assertEqual(original,home.read_bytes())
        connection=self.executor.database()
        try:
            row=connection.execute('SELECT * FROM account_environments').fetchone()
            self.assertEqual((17,None,'stopped'),(row['account_id'],row['container_id'],row['state']))
            account=connection.execute('SELECT * FROM accounts').fetchone()
            self.assertEqual((17,0,None),(account['id'],account['enabled'],account['cc2api_account_id']))
        finally:
            connection.close()
        with self.assertRaises(ValueError):
            self.grants.authorize(self.scope)

    def test_activation_recovers_after_real_id_sql_commit_before_assignment_file(self) -> None:
        """Node真实ID已落库后文件发布中断，重试继续同一激活意图。:return: None。"""
        self.prepared()
        self.ready()
        committed=self.actor.commit(self.scope)
        request=DraftLoginActivation(scope=self.scope,account_id=17,authorization_sha256=committed['commit']['authorization_sha256'])
        self.actor.accept(DraftLoginAccept(scope=self.scope,authorization_sha256=request.authorization_sha256))
        def interrupted(path,value):
            """只中断第一次正式分配发布。:param path: 原文件。:param value: 原投影。:return: None。"""
            if path.name=='node-assignment.json':
                raise OSError('synthetic assignment publish interruption')
            atomic_json(path,value)
        with patch('cluster_draft_login_activation.atomic_json',side_effect=interrupted),self.assertRaises(OSError):
            self.actor.activate(request)
        connection=self.executor.database()
        try:
            self.assertEqual(17,connection.execute('SELECT account_id FROM account_environments').fetchone()[0])
            self.assertEqual(0,connection.execute('SELECT enabled FROM accounts').fetchone()[0])
        finally:
            connection.close()
        self.assertEqual('activated',self.actor.activate(request)['phase'])
        assignment=json.loads((self.data/'environments'/self.scope.environment_id/'runtime/node-assignment.json').read_text())
        self.assertEqual(17,assignment['account_id'])

    def test_partial_deletion_uses_external_intent_after_environment_tree_is_removed(self) -> None:
        """环境树已删而profile失败时，外部意图支持同Scope接续与最终回执重读。:return: None。"""
        self.prepared()
        self.ready()
        self.actor.discard(self.scope)
        root=self.data/'environments'/self.scope.environment_id
        profile=self.data/'profiles'/self.scope.name
        original=shutil.rmtree
        def remove(path,*args,**kwargs):
            """只在原profile清理注入故障。:return: 原清理结果。"""
            if path==profile:
                raise PermissionError('synthetic profile removal failure')
            return original(path,*args,**kwargs)
        with patch('cluster_draft_login_deletion.shutil.rmtree',side_effect=remove),self.assertRaises(PermissionError):
            self.actor.delete(self.scope)
        self.assertFalse(root.exists())
        self.assertTrue(profile.exists())
        receipt=self.actor.delete(self.scope)
        self.assertEqual('deleted',receipt['phase'])
        self.assertEqual(receipt,self.actor.delete(self.scope))
        self.assertFalse(profile.exists())
        with self.assertRaises(ValueError):
            self.actor.prepare(self.preparation)

    def test_unknown_prepare_recovery_after_node_quarantine_only_closes_original_input(self) -> None:
        """Node隔离后的原准备仅恢复停止能力，迟到启动继续拒绝。:return: None。"""
        marker=self.actor.prepare(self.preparation)
        scope=DraftLoginScope.model_validate(marker['scope'])
        with self.executor.database() as connection:
            connection.execute("UPDATE account_environments SET state='cli_reconcile' WHERE environment_id=?",(scope.environment_id,))
        receipt=self.actor.recover_preparation(self.preparation)
        self.assertEqual('closed',receipt['phase'])
        self.assertEqual(scope.model_dump(),receipt['scope'])
        self.assertEqual(0,self.host.runtime.begin_calls)
        self.assertEqual('closed',self.actor.start(DraftLoginStart(scope=scope,work=self.work))['phase'])
        self.assertEqual(0,self.host.runtime.begin_calls)
        self.assertEqual('deleted',self.actor.delete(scope)['phase'])
