"""中央凭据维护的真实账本、未知提交及原所有权释放回归。"""
from __future__ import annotations

import copy
import threading
import time
import hashlib
import json
import unittest
from oauth_status import oauth_expiry_status
from unittest.mock import Mock, patch
from types import SimpleNamespace

import main
from account_runtime import RuntimeBusy
from cluster_credential_refresh import RemoteCredentialRefresh
from cluster_execution_grants import ExecutionGrant
import test_cluster_scenario_review as review_fixture
import test_cluster_terminal_sessions as session_fixture


class _Owner:
    """沿原pending/source状态转换的可观察所有者替身。"""

    def __init__(self) -> None:
        """建立当前独立所有者。:return: None。"""
        self.value={'owner':'local','phase':'ready','refresh_pending':False}

    def guard(self, account) -> None:
        """保持未决刷新隔离。:param account: 账号。:return: None。"""
        if self.value['phase']!='ready':
            raise ValueError('原凭据所有者等待核对')

    def begin_local_refresh(self, account_id, source) -> bool:
        """保存本次唯一来源。:param account_id: 账号。:param source: 来源。:return: True。"""
        self.guard(account_id)
        self.value.update(phase='reconcile',refresh_pending=True,refresh_source=source)
        return True

    def state(self, account_id) -> dict:
        """读取当前原状态。:param account_id: 账号。:return: 副本。"""
        return dict(self.value)

    def finish_local_refresh(self, account_id, source) -> None:
        """只解除原来源的已知维护。:param account_id: 账号。:param source: 原来源。:return: None。"""
        if not self.value['refresh_pending'] or self.value['refresh_source']!=source:
            raise ValueError('原来源已变化')
        self.value.update(phase='ready',refresh_pending=False)


class _CredentialPeer(session_fixture._Peer):
    """只接受具体刷新及原有限证明的合成Node。"""

    def __init__(self) -> None:
        """建立已知成功结果及可控未知提交。:return: None。"""
        super().__init__()
        self.outcome={'status':'complete','refreshed':True,'expires_at':99999999}

    def execution_environment(self, container, payload, operation):
        """冻结同一Scope并保持查询无发送。:param container: 原控制容器。:param payload: 原工作。:param operation: 固定动作。:return: 回执。"""
        if operation.startswith(('credential-refresh-','credential-usage-')):
            self.calls.append(operation)
            if operation.endswith('-start'):
                self.receipt={'protocol':1,'scope':copy.deepcopy(payload['scope']),'phase':'closed',
                    'result':{'token':'original-refresh-token','source':payload['scope']['source']},'outcome':dict(self.outcome)}
                if self.unknown_start:
                    raise ConnectionError('合成提交后响应丢失')
            elif operation.endswith('-stop'):
                self.receipt['phase']='closed'
            return {'protocol':1,'node_key':payload['scope']['node_key'] if operation.endswith('start') else payload['node_key'],
                'credentials':copy.deepcopy(self.receipt)}
        return super().execution_environment(container,payload,operation)


class RemoteCredentialRefreshTests(unittest.TestCase):
    """真实原中央SQLite与活动账本，Node HTTP由固定语义替身观测。"""

    def setUp(self) -> None:
        """借用原中央Scope和同批节点。:return: None。"""
        fixture=session_fixture.TerminalSessionTests(methodName='runTest')
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        self.fixture,self.sessions=fixture,fixture.sessions
        self.peer=_CredentialPeer()
        self.sessions.service.connection=lambda node:self.peer
        self.sessions.service.prepare_remote_cli=Mock()
        with self.sessions.service.store.database() as connection:
            connection.execute('UPDATE accounts SET cc2api_account_id=NULL WHERE id=1')
            self.account=dict(connection.execute('SELECT * FROM accounts WHERE id=1').fetchone())
        self.sessions.runtime._row=lambda *args:{'environment_id':fixture.request.scope.environment_id,
            'generation':fixture.request.scope.generation}
        self.owner,self.owner_lock=_Owner(),threading.Lock()
        self.coordinator=RemoteCredentialRefresh(self.sessions,self.owner,lambda name:self.owner_lock,
            lambda account:'original-account-identity',lambda account:'2.1.303')
        self.addCleanup(self.coordinator.close)

    def _rows(self) -> list[dict]:
        with self.sessions.service.store.database() as connection:
            keys=[row[0] for row in connection.execute('SELECT operation_id FROM node_executions ORDER BY created_at')]
        return [self.sessions.ledger.get(key) for key in keys]

    def test_status_cache_uses_only_current_node_and_expires_with_assignment(self) -> None:
        """列表只读缓存；实际观察后归属变化、超时和节点断连都显示unknown。:return: None。"""
        original=self.peer.execution_environment
        expiry=int((time.time()+3600)*1000)
        def observe(container,payload,operation):
            """生成当前HOME白名单回执。:return: 原范围观察。"""
            if operation!='credential-status':
                return original(container,payload,operation)
            now=time.time()
            return {'protocol':1,'node_key':payload['node_key'],'credentials':{
                'protocol':1,**payload,'observed_at':now,'status':oauth_expiry_status(expiry,now=now)}}
        self.peer.execution_environment=Mock(side_effect=observe)
        self.assertEqual('unknown',self.coordinator.status(self.account)['oauth_token_state'])
        self.peer.execution_environment.assert_not_called()
        self.assertEqual('valid',self.coordinator.status(self.account,observe=True)['oauth_token_state'])
        result=self.coordinator.status(self.account)
        self.assertEqual(expiry,result['oauth_expires_at_ms'])
        self.assertEqual('node-home',result['oauth_status_source'])
        self.assertEqual(1,self.peer.execution_environment.call_count)
        with patch.object(self.coordinator,'identity',return_value='changed-identity'):
            self.assertEqual('unknown',self.coordinator.status(self.account)['oauth_token_state'])
        with patch('cluster_credential_refresh.time.monotonic',return_value=time.monotonic()+121):
            self.assertEqual('unknown',self.coordinator.status(self.account)['oauth_token_state'])
        self.peer.execution_environment.side_effect=ConnectionError('合成节点断连')
        self.assertEqual('unknown',self.coordinator.status(self.account,observe=True)['oauth_token_state'])
        self.assertEqual('unknown',self.coordinator.status(self.account)['oauth_token_state'])
        self.assertEqual([],self._rows())
        self.fixture.admit.assert_not_called()

    def test_status_rejects_extra_fields_and_other_generation(self) -> None:
        """Node响应多字段或伪造环境代次时关闭观察。:return: None。"""
        def observe(container,payload,operation):
            """模拟错误Node回执。:return: 错代次响应。"""
            now=time.time()
            return {'protocol':1,'node_key':payload['node_key'],'credentials':{'protocol':1,**payload,
                'generation':payload['generation']+1,'observed_at':now,'status':oauth_expiry_status(9999999999999,now=now)}}
        self.peer.execution_environment=Mock(side_effect=observe)
        self.assertEqual('unknown',self.coordinator.status(self.account,observe=True)['oauth_token_state'])

    def test_current_owner_material_and_frozen_identity_are_never_cached_or_downgraded(self) -> None:
        """受信完整材料不进状态缓存，冻结版本错误与节点断连保持失败。:return: None。"""
        self.coordinator.identity=lambda account:json.dumps({'account_id':account['id'],'binding':None,'uuid':'node-uuid','org':None},sort_keys=True)
        material={'access_token':'synthetic-node-at','refresh_token':'synthetic-node-rt','expires_at':int((time.time()+3600)*1000)}
        def read(container,payload,operation):
            """生成明确原归属的受信资料响应。:return: 当前节点资料。"""
            field='material' if operation=='credential-material' else 'identity'
            value=material if field=='material' else {'device_id':'a'*64,'account_uuid':'node-uuid',
                'environment_id':payload['environment_id'],'source':'cli:2.1.293:config.userID'}
            return {'protocol':1,'node_key':payload['node_key'],'credentials':{'protocol':1,**payload,field:value}}
        self.peer.execution_environment=Mock(side_effect=read)
        self.assertEqual(material,self.coordinator.read_material(self.account))
        identity=self.coordinator.read_identity(self.account,'2.1.293')
        self.assertEqual('a'*64,identity['device_id'])
        self.assertEqual('2.1.293',self.peer.execution_environment.call_args.args[1]['version'])
        self.assertEqual({},self.coordinator.observations)
        with self.assertRaisesRegex(ValueError,'版本来源'):
            self.coordinator.read_identity(self.account,'2.1.303')
        material['refresh_token']='secret-with-invalid-whitespace value'
        with self.assertRaises(ValueError) as error:
            self.coordinator.read_material(self.account)
        self.assertNotIn('secret-with-invalid-whitespace',str(error.exception))
        self.peer.execution_environment.side_effect=ConnectionError('合成节点失联')
        with self.assertRaises(ConnectionError):
            self.coordinator.read_material(self.account)
        self.assertEqual([],self._rows())
        self.assertEqual({},self.coordinator.observations)

    def test_normal_refresh_closes_only_after_node_and_owner_confirmation(self) -> None:
        """真实账本使用无模型维护Scope，原模型额度和Gateway调用保持零。:return: None。"""
        self.assertTrue(self.coordinator.refresh(self.account,force_refresh=True))
        row,=self._rows()
        self.assertEqual('closed',row['phase'])
        self.assertEqual('login',row['role'])
        self.assertIsNone(row['record']['quota_identity'])
        self.assertIsNone(row['record']['lease'])
        self.assertTrue(row['record']['local_admission_released'])
        self.assertEqual('ready',self.owner.value['phase'])
        self.fixture.admit.assert_not_called()
        self.fixture.release.assert_not_called()
        self.assertEqual([],self.fixture.gateway.calls)
        self.assertEqual({},self.sessions.activities)
        self.assertEqual(1,self.peer.calls.count('credential-refresh-start'))

    def test_manual_usage_uses_original_node_without_rt_owner_transition(self) -> None:
        """具体usage实际收口后释放中央许可，RT所有权和模型额度保持原状。:return: None。"""
        self.coordinator.status=Mock(return_value={'oauth_token_state':'valid'})
        self.peer.outcome={'status':'complete','usage':{'five_hour':{'utilization':12}}}
        original=self.owner.state(1)
        result=self.coordinator.query_usage(self.account)
        self.assertEqual(12,result['five_hour']['utilization'])
        row,=self._rows()
        self.assertEqual('credential-usage',row['record']['work']['kind'])
        self.assertEqual('closed',row['phase'])
        self.assertEqual(original,self.owner.state(1))
        self.assertTrue(row['record']['local_admission_released'])
        self.fixture.admit.assert_not_called()
        self.fixture.release.assert_not_called()
        self.assertEqual([],self.fixture.gateway.calls)
        self.assertEqual({},self.sessions.activities)
        self.assertEqual(1,self.peer.calls.count('credential-usage-start'))
        self.assertNotIn('credential-refresh-start',self.peer.calls)

    def test_unknown_usage_submit_recovers_only_original_get_without_rt_isolation(self) -> None:
        """响应丢失保留原查询，恢复只读原回执且上游查询保持单次。:return: None。"""
        self.coordinator.status=Mock(return_value={'oauth_token_state':'valid'})
        self.peer.outcome={'status':'uncertain'}
        self.peer.unknown_start=True
        with self.assertRaises(ConnectionError):
            self.coordinator.query_usage(self.account)
        self.assertEqual(1,len(self.sessions.ledger.pending()))
        self.assertEqual('ready',self.owner.state(1)['phase'])
        self.coordinator.recover_pending()
        self.assertEqual([],self.sessions.ledger.pending())
        self.assertEqual(1,self.peer.calls.count('credential-usage-start'))
        self.assertIn('credential-usage-get',self.peer.calls)
        self.assertEqual({},self.sessions.activities)

    def test_manual_usage_unknown_home_state_refuses_upstream_query(self) -> None:
        """当前Node观察未知时保留明确错误，不从中央旧RT猜测凭据。:return: None。"""
        self.coordinator.status=Mock(return_value={'oauth_token_state':'unknown'})
        with self.assertRaisesRegex(ValueError,'HOME凭据'):
            self.coordinator.query_usage(self.account)
        self.assertEqual([],self._rows())
        self.assertEqual([],self.peer.calls)

    def test_main_usage_and_scheduler_follow_remote_home_without_owner_reentry(self) -> None:
        """原Runner与定时判断读取Node状态，原owner锁传入具体协调器。:return: None。"""
        runner=object.__new__(main.Runner)
        account={**self.account,'upstream_socks5_host':'synthetic.invalid'}
        self.coordinator.query_usage=Mock(return_value={'five_hour':{'utilization':12,'resets_at':'2099-01-01T00:00:00Z'}})
        self.coordinator.status=Mock(return_value={'oauth_token_state':'valid','oauth_expires_in_sec':3600})
        with patch.object(main,'account_runtime',self.sessions.runtime), \
                patch.object(main,'cluster_service',self.sessions.service), \
                patch.object(main,'cluster_runner',SimpleNamespace(credentials=self.coordinator)), \
                patch.object(main,'_read_account_oauth_status',side_effect=AssertionError('不能读取中央旧profile')):
            self.assertTrue(runner.query_quota(account)['ok'])
            self.coordinator.query_usage.assert_called_once_with(account,owner_locked=True)
            scheduler=main.OAuthRefreshScheduler(Mock())
            self.assertFalse(scheduler._needs_refresh(account['name'],account=account))
            self.coordinator.status.assert_called_with(account,observe=True)
            self.coordinator.status.return_value={'oauth_token_state':'expired','oauth_expires_in_sec':-1}
            self.assertTrue(scheduler._needs_refresh(account['name'],account=account))
            self.coordinator.status.return_value={'oauth_token_state':'unknown','oauth_expires_in_sec':None}
            self.assertFalse(scheduler._needs_refresh(account['name'],account=account))
            main._account_oauth_status(account)
            self.coordinator.status.assert_called_with(account,observe=False)

    def test_unknown_start_recovery_reads_original_receipt_and_never_replays_refresh(self) -> None:
        """提交响应未知保留维护，恢复读取原成功结论后释放同一Scope。:return: None。"""
        self.peer.unknown_start=True
        with self.assertRaises(ConnectionError):
            self.coordinator.refresh(self.account)
        row,=self._rows()
        self.assertEqual('reconcile',row['phase'])
        self.assertTrue(self.owner.value['refresh_pending'])
        with self.assertRaisesRegex(ValueError,'等待核对'):
            self.coordinator.refresh(self.account)
        self.sessions.recover()
        self.coordinator.recover_pending()
        self.assertEqual('closed',self._rows()[0]['phase'])
        self.assertEqual('ready',self.owner.value['phase'])
        self.assertEqual(1,self.peer.calls.count('credential-refresh-start'))

    def test_uncertain_rt_result_keeps_owner_and_execution_isolated_after_actual_stop(self) -> None:
        """实际停止与RT成功分开核对，未知结果在重启恢复后继续占用维护。:return: None。"""
        self.peer.outcome={'status':'uncertain'}
        with self.assertRaisesRegex(ValueError,'结果未知'):
            self.coordinator.refresh(self.account)
        self.coordinator.recover_pending()
        row,=self._rows()
        self.assertEqual('reconcile',row['phase'])
        self.assertEqual('closed',row['record']['node_receipt']['phase'])
        self.assertTrue(self.owner.value['refresh_pending'])
        self.assertEqual(1,len(self.sessions.activities))
        self.assertEqual(1,self.peer.calls.count('credential-refresh-start'))

    def test_busy_owner_skips_recovery_without_blocking_shared_run_loop(self) -> None:
        """原账号owner锁被占用时跳过该条，循环保留原操作且及时返回。:return: None。"""
        self.peer.unknown_start=True
        with self.assertRaises(ConnectionError):
            self.coordinator.refresh(self.account)
        before=list(self.peer.calls)
        self.owner_lock.acquire()
        worker=threading.Thread(target=self.coordinator.recover_pending,daemon=True)
        try:
            worker.start()
            worker.join(timeout=1)
            self.assertFalse(worker.is_alive(),'共享恢复循环被其他owner操作阻塞')
            self.assertEqual(before,self.peer.calls)
        finally:
            self.owner_lock.release()
            worker.join(timeout=2)
        self.coordinator.recover_pending()
        self.assertEqual('closed',self._rows()[0]['phase'])

    def test_known_http_rejection_releases_maintenance_and_reports_failure(self) -> None:
        """原4xx结果已知且实际停止后允许原所有者结束本次维护。:return: None。"""
        self.peer.outcome={'status':'failed','http_status':401}
        with self.assertRaisesRegex(ValueError,'刷新失败'):
            self.coordinator.refresh(self.account)
        self.assertEqual('closed',self._rows()[0]['phase'])
        self.assertEqual('ready',self.owner.value['phase'])

    def test_original_runner_passes_existing_nonreentrant_owner_lock_to_remote_path(self) -> None:
        """原定时/查询入口持锁调用Runner时，所属Node分支显式沿用该锁。:return: None。"""
        remote=Mock()
        remote.routes.return_value=True
        remote.credentials=self.coordinator
        account={**self.account,'upstream_socks5_host':'synthetic-proxy.invalid'}
        runner=object.__new__(main.Runner)
        with self.owner_lock,patch.object(main,'account_runtime',Mock()),patch.object(main,'cluster_runner',remote):
            self.assertTrue(runner.refresh_account_oauth_token(account,force_refresh=True))
        self.assertEqual('closed',self._rows()[0]['phase'])

    def test_existing_remote_execution_blocks_refresh_before_node_prepare(self) -> None:
        """已有原执行保持活动，新维护等待其实际释放。:return: None。"""
        scope=self.fixture.request.scope.model_copy(update={'gateway_account_id':None})
        self.sessions.ledger.begin(scope,self.fixture.request.work)
        with self.assertRaises(RuntimeBusy):
            self.coordinator.refresh(self.account)
        self.sessions.service.prepare_remote_cli.assert_not_called()
        self.assertEqual([],self.peer.calls)

    def test_review_401_registers_maintenance_before_original_scope_release_and_keeps_frozen_source(self) -> None:
        """原401按Node回执登记，严格释放评审后使用新的无模型维护Scope。:return: None。"""
        review=review_fixture.ScenarioNodeReviewTests(methodName='runTest')
        review.setUp()
        self.addCleanup(review.doCleanups)
        original=review.node.work.model_copy(update={'project':review.work})
        scope=self.fixture.request.scope.model_copy(update={'operation_id':'9'*32,'gateway_account_id':None,
            'role':'cli','source':original.source})
        ledger=self.sessions.ledger
        row=ledger.begin(scope,original)
        grant=ExecutionGrant(**scope.model_dump(),not_after=int(time.time())+30)
        row=self.sessions._save(scope.operation_id,'claimed',local_admission_intent=True,quota_identity='original-account-identity',grant=grant.model_dump())
        row=self.sessions._save(scope.operation_id,'starting')
        receipt={'protocol':1,'scope':scope.model_dump(),'phase':'ready','result':{'token':'original-review-token','source':scope.source}}
        parent=self.sessions._save(scope.operation_id,'running',node_receipt=receipt)
        pending={'account_id':1,'source':scope.source,'request_id':hashlib.sha256(scope.source.encode()).hexdigest(),
            'status':'waiting','attempts':0,'not_before':0}
        self.sessions.service.review_admission=Mock(return_value={'owner_refresh':pending})
        original_call=self.sessions._call
        def call(row,operation,payload):
            """只为原已核对401返回固定待办确认。:param row: 原行。:param operation: 固定动作。:param payload: 原输入。:return: 原回执。"""
            if operation=='run-owner-refresh-defer':
                return {'protocol':1,'scope':scope.model_dump(),'phase':'deferred','request_sha256':payload['request_sha256'],
                    'request_id':pending['request_id']}
            return original_call(row,operation,payload)
        self.sessions._call=call
        def stop(operation_id):
            """模拟已取得原Node实际停止证明。:param operation_id: 原评审。:return: 原关闭行。"""
            self.assertEqual(scope.operation_id,operation_id)
            active=ledger.active(1)
            self.assertEqual(2,len(active))
            self.assertEqual(1,len(self.sessions.activities))
            self.assertNotIn('credential-refresh-start',self.peer.calls)
            self.sessions._save(operation_id,'stopping',node_receipt={**receipt,'phase':'closed'})
            return self.sessions._save(operation_id,'closed',local_admission_released=True)
        self.sessions.stop=Mock(side_effect=stop)
        self.coordinator.defer_review(parent,'e'*64)
        deadline=time.monotonic()+5
        while self.coordinator.reviewing and time.monotonic()<deadline:
            time.sleep(.01)
        self.assertEqual(set(),self.coordinator.reviewing)
        rows=self._rows()
        self.assertEqual(2,len(rows))
        maintenance=next(item for item in rows if item['role']=='login')
        self.assertEqual('closed',maintenance['phase'])
        self.assertEqual(scope.model_dump(),maintenance['record']['work']['review_scope'])
        self.assertEqual(original.worker_env['CLAUDE_CODE_VERSION'],maintenance['record']['work']['version'])
        self.assertEqual(1,self.peer.calls.count('credential-refresh-start'))
        self.sessions.stop.assert_called_once_with(scope.operation_id)
        self.assertEqual('ready',self.owner.value['phase'])
