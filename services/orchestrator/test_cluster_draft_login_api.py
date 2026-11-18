"""新账号节点草稿的原管理HTTP、双端SQLite与提交恢复验证。"""
from __future__ import annotations

import json
import time
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from fastapi.testclient import TestClient

import main
from account_runtime import AccountRuntime, RuntimeBusy
from cluster_service import ClusterService
from cluster_draft_login_contract import DraftLoginGrant, DraftLoginScope
import test_cluster_draft_login_runner as runner_fixture
from test_cluster_draft_login import _DraftRuntime


class ClusterDraftLoginApiTests(unittest.TestCase):
    """复用实际Node协议，中央使用原LoginManager与草稿管理入口。"""

    def setUp(self) -> None:
        """准备原中央运行时与管理入口，Node保留独立数据库。:return: None。"""
        fixture=runner_fixture.ClusterDraftLoginRunnerTests(methodName='runTest')
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        self.fixture,self.coordinator=fixture,fixture.coordinator
        environment=patch.dict('os.environ',{'V3_DEPLOYMENT_ID':'synthetic','V3_ACCOUNT_IMAGE':'synthetic',
            'V3_NETWORK':'synthetic','V3_RELEASE':'synthetic-release'})
        environment.start()
        self.addCleanup(environment.stop)
        self.runtime=AccountRuntime(Mock(),fixture.runtime.data,fixture.runtime.data,fixture.central.database,
            lambda timezone:{'tz':timezone or 'UTC','mem':'4g','swap':'0'},Mock())
        self.addCleanup(self.runtime.heartbeat_pool.shutdown)
        self.coordinator.runtime=self.runtime
        self.coordinator.profile_lock=main._profile_lock
        self.coordinator.prepare_admission=main._mark_remote_draft_node_prepare
        self.coordinator.owner_lock=main._oauth_owner_lock
        self.coordinator.save_profile=main._save_remote_draft_profile
        self.manager=main.LoginManager(Mock())
        self.placement=ClusterService(fixture.central.store,self.runtime.data,Mock(),self.runtime.data/'transports')
        self.addCleanup(self.placement.close)
        for name,value in {'get_db':fixture.central.database,'BENCH_DATA':self.runtime.data,
                'PROFILES_DIR':self.runtime.data/'profiles','account_runtime':self.runtime,
                'cluster_service':self.placement,'cluster_draft_logins':self.coordinator,
                'cluster_logins':None,'cluster_bound_logins':None,'login_manager':self.manager,
                '_resolve_account_cli_version':lambda account,version=None:(version or '2.1.293','synthetic')}.items():
            guard=patch.object(main,name,value)
            guard.start()
            self.addCleanup(guard.stop)
        self.runtime.locality=self.placement.owns_local
        self.runtime.placement=self.placement.admit_local
        with fixture.central.connection:
            fixture.central.connection.execute('DELETE FROM account_environments')
        self.client=TestClient(main.app)
        self.addCleanup(self.client.close)

    def start(self) -> dict:
        """通过原产品入口选择SSH节点并等待原Node登录就绪。:return: 原会话公开字段。"""
        response=self.client.post('/api/accounts/login/start',json={'name':'draft_only',
            'node_id':self.fixture.central.node_id,'upstream_socks5_host':'synthetic.proxy.invalid',
            'upstream_socks5_user':'synthetic-user','upstream_socks5_pass':'synthetic-secret'})
        self.assertEqual(200,response.status_code,response.text)
        value=response.json()
        deadline=time.monotonic()+5
        while True:
            status=self.client.get('/api/accounts/login/'+value['session_id']+'/status')
            self.assertEqual(200,status.status_code,status.text)
            if status.json()['phase']!='preparing':
                break
            self.assertLess(time.monotonic(),deadline,status.text)
            time.sleep(.01)
        self.manager.client.containers.run.assert_not_called()
        return value

    def test_product_start_list_original_session_and_complete_commit(self) -> None:
        """首次账号保持NULL，节点列表无代理秘密；原SID提交完整账号与远程归属。:return: None。"""
        first=self.start()
        self.assertEqual(self.fixture.central.node_id,first['node_id'])
        with main.get_db() as connection:
            self.assertEqual(0,connection.execute('SELECT count(*) FROM accounts').fetchone()[0])
        forbidden=self.client.post('/api/accounts',json={'name':'draft_only'})
        self.assertEqual(409,forbidden.status_code,forbidden.text)
        listing=self.client.get('/api/accounts/login-drafts')
        self.assertEqual(200,listing.status_code,listing.text)
        draft=listing.json()[0]
        self.assertEqual(first['node_id'],draft['node_id'])
        self.assertTrue(draft['credentials_present'])
        self.assertNotIn('synthetic-secret',listing.text)
        self.assertNotIn('synthetic-user',listing.text)
        resumed=self.client.post('/api/accounts/login-drafts/'+first['environment_id']+'/resume',
            json={'generation':draft['generation']})
        self.assertEqual(200,resumed.status_code,resumed.text)
        self.assertEqual(first['session_id'],resumed.json()['session_id'])
        response=self.client.post('/api/accounts/login/'+first['session_id']+'/commit',json={'name':'draft_only'})
        self.assertEqual(200,response.status_code,response.text)
        self.assertGreater(response.json()['id'],0)
        self.assertEqual([],self.client.get('/api/accounts/login-drafts').json())
        self.assertEqual(first['node_id'],self.fixture.central.store.assignment(response.json()['id'])['node_id'])
        profile=json.loads((self.runtime.data/'profiles/draft_only/.credentials.json').read_text())
        self.assertTrue(profile['unknown_credentials']['preserved'])
        self.assertEqual(1,self.fixture.host.runtime.begin_calls)

    def test_registration_failure_can_delete_only_central_owned_draft(self) -> None:
        """账本登记失败时，明确未准备标记允许原页面清理中央残留。:return: None。"""
        with patch.object(self.coordinator.ledger,'begin',side_effect=ValueError('synthetic registration failure')):
            response=self.client.post('/api/accounts/login/start',json={'name':'draft_only',
                'node_id':self.fixture.central.node_id})
        self.assertGreaterEqual(response.status_code,400,response.text)
        self.assertEqual([],self.fixture.calls)
        draft=self.client.get('/api/accounts/login-drafts').json()[0]
        self.assertTrue(draft['can_delete'])
        self.assertFalse(draft['can_resume'])
        self.assertNotEqual('unverified',draft['generation'])
        row=main._login_drafts().row(draft['environment_id'])
        self.assertIs(main._login_drafts().record(row)['node_prepare_intent'],False)
        self.assertEqual(409,self.client.post('/api/accounts',json={'name':'draft_only'}).status_code)
        url='/api/accounts/login-drafts/'+draft['environment_id']+'?generation='+draft['generation']
        with patch.object(self.runtime,'_root',side_effect=AssertionError('禁止中央HOME定位')):
            response=self.client.delete(url)
        self.assertEqual(200,response.status_code,response.text)
        self.assertEqual([],self.fixture.calls)
        self.runtime.client.containers.run.assert_not_called()
        self.assertFalse((self.runtime.data/'profiles/draft_only').exists())
        self.assertEqual([],self.client.get('/api/accounts/login-drafts').json())

    def test_registration_cleanup_marker_retry_preserves_later_reused_profile(self) -> None:
        """登记残留清理的最后标记失败后，重复尾段保护后来同名资料。:return: None。"""
        with patch.object(self.coordinator.ledger,'begin',side_effect=ValueError('synthetic registration failure')):
            self.client.post('/api/accounts/login/start',json={'name':'draft_only','node_id':self.fixture.central.node_id})
        draft=self.client.get('/api/accounts/login-drafts').json()[0]
        marker=self.runtime.data/'login-drafts'/(draft['environment_id']+'.json')
        original=Path.unlink
        def unlink(path,*args,**kwargs):
            """注入原中央标记删除失败。:return: 原删除结果。"""
            if path==marker:
                raise PermissionError('synthetic final marker failure')
            return original(path,*args,**kwargs)
        url='/api/accounts/login-drafts/'+draft['environment_id']+'?generation='+draft['generation']
        with patch.object(Path,'unlink',unlink):
            response=self.client.delete(url)
        self.assertEqual(503,response.status_code,response.text)
        profile=self.runtime.data/'profiles/draft_only'
        profile.mkdir(parents=True)
        sentinel=profile/'later.json'
        sentinel.write_text('synthetic later profile')
        self.assertTrue(self.client.get('/api/accounts/login-drafts').json()[0]['can_delete'])
        response=self.client.delete(url)
        self.assertEqual(200,response.status_code,response.text)
        self.assertEqual('synthetic later profile',sentinel.read_text())
        self.assertEqual([],self.fixture.calls)

    def test_unregistered_unknown_intent_keeps_cleanup_closed(self) -> None:
        """缺失或已进入节点准备的意图继续保护未登记草稿。:return: None。"""
        with patch.object(self.coordinator.ledger,'begin',side_effect=ValueError('synthetic registration failure')):
            self.client.post('/api/accounts/login/start',json={'name':'draft_only','node_id':self.fixture.central.node_id})
        draft=self.client.get('/api/accounts/login-drafts').json()[0]
        drafts=main._login_drafts()
        row=drafts.row(draft['environment_id'])
        for intent in (None,True):
            drafts.save(row,node_prepare_intent=intent)
            self.assertFalse(self.client.get('/api/accounts/login-drafts').json()[0]['can_delete'])
            response=self.client.delete('/api/accounts/login-drafts/'+draft['environment_id']+'?generation='+draft['generation'])
            self.assertEqual(409,response.status_code,response.text)
        self.assertTrue((self.runtime.data/'profiles/draft_only').exists())
        self.assertEqual([],self.fixture.calls)

    def test_prepare_intent_is_durable_before_rpc_and_survives_new_generation(self) -> None:
        """原节点准备之前持久意图，后续重登继续保留已进入节点的事实。:return: None。"""
        original=self.fixture.peer.execution_environment
        observed=[]
        def execution(container,payload,operation):
            """在真实Node协议入口观察中央原子标记。:return: 原节点回执。"""
            if operation in ('draft-login-prepare','draft-login-recover-preparation'):
                marker=json.loads((self.runtime.data/'login-drafts'/(payload['work']['environment_id']+'.json')).read_text())
                self.assertIs(marker['node_prepare_intent'],True)
                observed.append(marker['generation'])
            return original(container,payload,operation)
        with patch.object(self.fixture.peer,'execution_environment',side_effect=execution):
            first=self.start()
            response=self.client.post('/api/accounts/login-drafts/'+first['environment_id']+'/restart',
                json={'generation':first['draft_generation']})
            self.assertEqual(200,response.status_code,response.text)
        self.assertEqual([first['draft_generation'],response.json()['draft_generation']],observed)

    def test_prepare_intent_write_failure_uses_registered_zero_generation_cleanup(self) -> None:
        """意图写失败阻止Node准备，已登记账本继续走原零代清理协议。:return: None。"""
        original=main.LoginDraftStore.save
        def save(store,row,**fields):
            """只阻止原准备意图原子写入。:return: 原标记。"""
            if fields.get('node_prepare_intent') is True:
                raise PermissionError('synthetic intent write failure')
            return original(store,row,**fields)
        with patch.object(main.LoginDraftStore,'save',save):
            response=self.client.post('/api/accounts/login/start',json={'name':'draft_only',
                'node_id':self.fixture.central.node_id})
        self.assertEqual(503,response.status_code,response.text)
        self.assertEqual([],self.fixture.calls)
        draft=self.client.get('/api/accounts/login-drafts').json()[0]
        self.assertIsNotNone(self.coordinator.ledger.find(draft['environment_id']))
        self.assertFalse(main._login_drafts().unregistered(main._login_drafts().row(draft['environment_id'])))
        response=self.client.delete('/api/accounts/login-drafts/'+draft['environment_id']+'?generation='+draft['generation'])
        self.assertEqual(200,response.status_code,response.text)
        self.assertEqual(['draft-login-delete-preparation'],self.fixture.calls)

    def test_cancel_resume_checks_retained_material_on_same_node_then_restart_changes_generation(self) -> None:
        """取消保留产物，继续只检查旧HOME；重登新代次保持原节点、代理与画像。:return: None。"""
        first=self.start()
        response=self.client.delete('/api/accounts/login/'+first['session_id'])
        self.assertEqual(200,response.status_code,response.text)
        draft=self.client.get('/api/accounts/login-drafts').json()[0]
        self.assertEqual('cancelled',draft['state'])
        self.assertTrue(draft['can_resume'])
        response=self.client.post('/api/accounts/login-drafts/'+first['environment_id']+'/resume',
            json={'generation':draft['generation']})
        self.assertEqual(200,response.status_code,response.text)
        resumed=response.json()
        self.assertNotEqual(first['session_id'],resumed['session_id'])
        deadline=time.monotonic()+5
        while self.fixture.host.runtime.recover_calls==0:
            self.assertLess(time.monotonic(),deadline)
            time.sleep(.01)
        self.assertEqual(1,self.fixture.host.runtime.begin_calls)
        stale=self.client.post('/api/accounts/login-drafts/'+first['environment_id']+'/restart',
            json={'generation':first['draft_generation']})
        self.assertEqual(409,stale.status_code,stale.text)
        response=self.client.post('/api/accounts/login-drafts/'+first['environment_id']+'/restart',
            json={'generation':resumed['draft_generation']})
        self.assertEqual(200,response.status_code,response.text)
        self.assertNotEqual(resumed['session_id'],response.json()['session_id'])
        self.assertEqual(first['node_id'],response.json()['node_id'])
        current=self.coordinator.ledger.find(first['environment_id'])
        self.assertEqual('synthetic-secret',self.coordinator.preparation(current).settings.upstream_socks5_pass)

    def test_half_saved_account_stays_in_drafts_and_original_submit_recovers(self) -> None:
        """激活响应丢失后半保存账号继续可见，原SID重建后只接续原提交。:return: None。"""
        first=self.start()
        self.fixture.loss='draft-login-activate'
        response=self.client.post('/api/accounts/login/'+first['session_id']+'/commit',json={'name':'draft_only'})
        self.assertEqual(503,response.status_code,response.text)
        with main.get_db() as connection:
            self.assertEqual(0,connection.execute('SELECT enabled FROM accounts').fetchone()[0])
        draft=self.client.get('/api/accounts/login-drafts').json()[0]
        self.assertEqual('submitting',draft['state'])
        self.assertTrue(draft['can_resume'])
        self.assertFalse(draft['can_delete'])
        self.assertFalse(draft['can_restart'])
        self.coordinator.close()
        self.coordinator=self.fixture.new_coordinator()
        self.coordinator.runtime=self.runtime
        self.coordinator.owner_lock=main._oauth_owner_lock
        self.coordinator.save_profile=main._save_remote_draft_profile
        with patch.object(main,'cluster_draft_logins',self.coordinator),patch.object(main,'login_manager',main.LoginManager(Mock())):
            response=self.client.post('/api/accounts/login/'+first['session_id']+'/commit',json={'name':'draft_only'})
            self.assertEqual(200,response.status_code,response.text)
        self.assertEqual(1,self.fixture.host.runtime.begin_calls)
        self.assertEqual([],self.client.get('/api/accounts/login-drafts').json())

    def test_complete_delete_response_lost_keeps_retryable_external_receipt(self) -> None:
        """Node实际删除后响应丢失，中央保留deleting并按原回执完成清理。:return: None。"""
        first=self.start()
        self.fixture.loss='draft-login-delete'
        url='/api/accounts/login-drafts/'+first['environment_id']+'?generation='+first['draft_generation']
        response=self.client.delete(url)
        self.assertEqual(503,response.status_code,response.text)
        self.assertTrue((self.runtime.data/'profiles/draft_only').exists())
        self.assertFalse((self.fixture.node.root/'profiles/draft_only').exists())
        draft=self.client.get('/api/accounts/login-drafts').json()[0]
        self.assertEqual('deleting',draft['state'])
        self.assertTrue(draft['can_delete'])
        response=self.client.delete(url)
        self.assertEqual(200,response.status_code,response.text)
        self.assertFalse((self.runtime.data/'profiles/draft_only').exists())
        self.assertEqual([],self.client.get('/api/accounts/login-drafts').json())
        self.assertEqual({'ok':True},self.client.delete(url).json())
        with main.get_db() as connection:
            self.assertEqual(0,connection.execute('SELECT count(*) FROM node_login_drafts').fetchone()[0])
            self.assertEqual(0,connection.execute('SELECT count(*) FROM account_environments').fetchone()[0])
        self.assertIsNotNone(self.coordinator.deletion(first['environment_id']))
        self.assertEqual({},self.coordinator.activities)

    def test_final_marker_failure_remains_visible_after_both_databases_are_clean(self) -> None:
        """最后标记删除失败时，环境外回执支持列表展示和重复收口。:return: None。"""
        first=self.start()
        marker=self.runtime.data/'login-drafts'/(first['environment_id']+'.json')
        original=Path.unlink
        def unlink(path,*args,**kwargs):
            """只在本次中央草稿标记注入文件故障。:return: 原删除结果。"""
            if path==marker:
                raise PermissionError('synthetic final marker failure')
            return original(path,*args,**kwargs)
        url='/api/accounts/login-drafts/'+first['environment_id']+'?generation='+first['draft_generation']
        with patch.object(Path,'unlink',unlink):
            response=self.client.delete(url)
        self.assertEqual(503,response.status_code,response.text)
        self.assertIsNone(self.coordinator.ledger.find(first['environment_id']))
        draft=self.client.get('/api/accounts/login-drafts').json()[0]
        self.assertEqual('deleting',draft['state'])
        self.assertTrue(draft['can_delete'])
        response=self.client.delete(url)
        self.assertEqual(200,response.status_code,response.text)
        self.assertFalse(marker.exists())
        self.assertEqual([],self.client.get('/api/accounts/login-drafts').json())

    def test_unknown_preparation_is_visible_and_original_reconcile_only_stops(self) -> None:
        """原准备响应丢失时保留可见草稿，原代次恢复检查后可完整删除。:return: None。"""
        self.fixture.loss='draft-login-prepare'
        response=self.client.post('/api/accounts/login/start',json={'name':'draft_only','node_id':self.fixture.central.node_id})
        self.assertEqual(503,response.status_code,response.text)
        draft=self.client.get('/api/accounts/login-drafts').json()[0]
        self.assertTrue(draft['can_reconcile'])
        self.assertEqual('reconcile',draft['state'])
        response=self.client.post('/api/accounts/login-drafts/'+draft['environment_id']+'/reconcile',
            json={'generation':draft['generation']})
        self.assertEqual(200,response.status_code,response.text)
        self.assertEqual(0,self.fixture.host.runtime.begin_calls)
        response=self.client.delete('/api/accounts/login-drafts/'+draft['environment_id']+'?generation='+draft['generation'])
        self.assertEqual(200,response.status_code,response.text)
        self.assertEqual([],self.client.get('/api/accounts/login-drafts').json())

    def test_committed_node_keeps_submit_control_until_final_marker_cleanup(self) -> None:
        """正式保存完成而最后标记失败时，页面仍能沿同SID重试收口。:return: None。"""
        first=self.start()
        marker=self.runtime.data/'login-drafts'/(first['environment_id']+'.json')
        original=Path.unlink
        def unlink(path,*args,**kwargs):
            """只中断原提交的最后草稿标记清理。:return: 原删除结果。"""
            if path==marker:
                raise PermissionError('synthetic commit marker failure')
            return original(path,*args,**kwargs)
        url='/api/accounts/login/'+first['session_id']+'/commit'
        with patch.object(Path,'unlink',unlink):
            response=self.client.post(url,json={'name':'draft_only'})
        self.assertEqual(503,response.status_code,response.text)
        status=self.client.get('/api/accounts/login/'+first['session_id']+'/status')
        self.assertEqual(200,status.status_code,status.text)
        self.assertEqual('submitting',status.json()['phase'])
        self.assertTrue(status.json()['credentials_ready'])
        response=self.client.post(url,json={'name':'draft_only'})
        self.assertEqual(200,response.status_code,response.text)
        self.assertFalse(marker.exists())
        self.assertEqual([],self.client.get('/api/accounts/login-drafts').json())

    def test_new_generation_marker_failure_recovers_only_from_exact_previous_scope(self) -> None:
        """新代次标记失败阻止Node准备，原前代证明支持同操作恢复检查。:return: None。"""
        first=self.start()
        response=self.client.delete('/api/accounts/login/'+first['session_id'])
        self.assertEqual(200,response.status_code,response.text)
        original=main.LoginDraftStore.save
        def save(store,row,**fields):
            """只中断新代次标记，保留真实Node与中央账本。:return: 原保存结果。"""
            if fields.get('generation') and fields['generation']!=first['draft_generation']:
                raise OSError('synthetic generation marker failure')
            return original(store,row,**fields)
        endpoint='/api/accounts/login-drafts/'+first['environment_id']
        with patch.object(main.LoginDraftStore,'save',save):
            response=self.client.post(endpoint+'/restart',json={'generation':first['draft_generation']})
        self.assertEqual(503,response.status_code,response.text)
        current=self.coordinator.ledger.find(first['environment_id'])
        self.assertNotEqual(first['draft_generation'],current['generation'])
        self.assertIsNone(current['record']['scope'])
        response=self.client.post(endpoint+'/reconcile',json={'generation':current['generation']})
        self.assertEqual(200,response.status_code,response.text)
        self.assertEqual('closed',self.coordinator.ledger.find(first['environment_id'])['phase'])
        self.assertEqual(current['generation'],main._login_drafts().record(main._login_drafts().row(first['environment_id']))['generation'])
        response=self.client.post(endpoint+'/restart',json={'generation':current['generation']})
        self.assertEqual(200,response.status_code,response.text)
        self.assertNotEqual(current['sid'],response.json()['session_id'])

    def test_failed_resource_preparation_deletes_at_generation_zero_without_repreparing(self) -> None:
        """准备本身失败且中央私有副本缺失时，独立清理身份直接收口零代资源。:return: None。"""
        with patch.object(_DraftRuntime,'ensure',side_effect=ValueError('synthetic preparation capacity failure')) as ensure:
            response=self.client.post('/api/accounts/login/start',json={'name':'draft_only','node_id':self.fixture.central.node_id})
            self.assertEqual(400,response.status_code,response.text)
            draft=self.client.get('/api/accounts/login-drafts').json()[0]
            self.assertTrue(draft['can_delete'])
            row=self.coordinator.ledger.find(draft['environment_id'])
            self.assertIsNone(row['record']['scope'])
            self.coordinator._preparation_path(row).unlink()
            self.fixture.loss='draft-login-delete-preparation'
            url='/api/accounts/login-drafts/'+draft['environment_id']+'?generation='+draft['generation']
            response=self.client.delete(url)
            self.assertEqual(503,response.status_code,response.text)
            self.assertEqual('deleting',self.client.get('/api/accounts/login-drafts').json()[0]['state'])
            response=self.client.delete(url)
            self.assertEqual(200,response.status_code,response.text)
            self.assertEqual(1,ensure.call_count)
        receipt=self.coordinator.deletion(draft['environment_id'])
        self.assertEqual('login-draft-preparation',receipt.scope.role)
        self.assertEqual(0,receipt.scope.generation)
        self.assertNotIn('account_id',receipt.scope.model_dump())
        with self.assertRaises(ValueError):
            DraftLoginScope.model_validate(receipt.scope.model_dump())
        with self.assertRaises(ValueError):
            DraftLoginGrant.model_validate({**receipt.scope.model_dump(),'not_after':int(time.time())+30})
        self.assertEqual([],self.client.get('/api/accounts/login-drafts').json())
        with main.get_db() as connection:
            self.assertEqual(0,connection.execute('SELECT count(*) FROM accounts').fetchone()[0])

    def test_draft_locality_and_environment_projection_never_read_central_home_or_docker(self) -> None:
        """中央启动和环境页按冻结节点识别NULL草稿，位置只读且拒绝本机执行。:return: None。"""
        first=self.start()
        row=main._login_drafts().row(first['environment_id'])
        self.assertFalse(self.placement.owns_local(row))
        with self.assertRaises(RuntimeBusy):
            self.placement.admit_local({'name':'draft_only','id':None})
        with patch.object(self.runtime,'role_status',side_effect=AssertionError('unexpected central Docker read')), \
                patch.object(self.runtime,'_root',side_effect=AssertionError('unexpected central HOME read')), \
                patch.object(self.runtime,'native_preparation_snapshots',return_value=({},None)), \
                patch.object(main,'credential_ownership',None):
            response=self.client.get('/api/environments')
        self.assertEqual(200,response.status_code,response.text)
        projected=response.json()[0]
        self.assertTrue(projected['login_draft'])
        self.assertEqual(first['node_id'],projected['node']['node_id'])
        self.assertNotIn('account_id',projected['node'])
        self.assertFalse(projected['can_reprofile'])
        self.assertFalse(self.placement.owns_local({**row,'generation':0}))

    def test_proxy_references_use_frozen_node_configuration_without_central_sender(self) -> None:
        """代理目录读取原私有准备的引用摘要，状态未知保留保护，中央sender始终独立。:return: None。"""
        first=self.start()
        with patch.object(main,'V3_ENABLED',True), \
                patch.object(self.runtime,'_sender_config',side_effect=AssertionError('unexpected central sender read')):
            snapshot=main.v3_proxy_references()
        self.assertTrue(snapshot['complete'])
        reference=next(item for item in snapshot['references'] if item['id']==first['environment_id'])
        self.assertEqual('draft',reference['kind'])
        self.assertNotIn('synthetic-user',json.dumps(snapshot))
        self.assertNotIn('synthetic-secret',json.dumps(snapshot))

    def test_repeated_final_marker_cleanup_preserves_reused_name_profile(self) -> None:
        """原数据库已收口而标记失败时，重试只清旧标记并保留后来复用名称的资料。:return: None。"""
        first=self.start()
        marker=self.runtime.data/'login-drafts'/(first['environment_id']+'.json')
        original=Path.unlink
        def unlink(path,*args,**kwargs):
            """只中断原草稿最终标记。:return: 原删除结果。"""
            if path==marker:
                raise PermissionError('synthetic old marker failure')
            return original(path,*args,**kwargs)
        url='/api/accounts/login-drafts/'+first['environment_id']+'?generation='+first['draft_generation']
        with patch.object(Path,'unlink',unlink):
            self.assertEqual(503,self.client.delete(url).status_code)
        replacement=self.runtime._row('draft_only')
        profile=self.runtime.data/'profiles/draft_only/settings.json'
        profile.parent.mkdir(parents=True)
        profile.write_text('{"new_draft":true}')
        self.assertNotEqual(first['environment_id'],replacement['environment_id'])
        self.assertEqual(200,self.client.delete(url).status_code)
        self.assertEqual('{"new_draft":true}',profile.read_text())


if __name__=='__main__':
    unittest.main()
