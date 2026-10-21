"""私有评审的冻结身份、待办换代与真实角色归属回归。"""
import json
import os
import sqlite3
import tempfile
import threading
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from account_isolation import ISOLATION_VERSION
from account_runtime import AccountRuntime
from project_library import read_document, write_document
from resource_budget import scenario_account_limits
import main


class PrivateReviewTests(unittest.TestCase):
    """不访问网络或真实账号，使用真实SQLite和持久待办验证门禁。"""

    def setUp(self) -> None:
        """准备隔离账号、环境及有限的Docker接口替身。@return None。"""
        temporary=tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root=Path(temporary.name)

        def database():
            connection=sqlite3.connect(self.root/'state.sqlite')
            connection.row_factory=sqlite3.Row
            return connection

        self.database=database
        with database() as connection:
            connection.execute('CREATE TABLE accounts(id INTEGER PRIMARY KEY,name TEXT,cc2api_account_id INTEGER,enabled INTEGER DEFAULT 1,deleted_at REAL)')
            connection.execute('CREATE TABLE app_settings(key TEXT PRIMARY KEY,value TEXT)')
            connection.execute('CREATE TABLE runs(id TEXT PRIMARY KEY,quota_identity TEXT)')
            connection.execute("INSERT INTO accounts(id,name) VALUES(1,'synthetic')")
            connection.execute("INSERT INTO runs VALUES('review','identity-None')")
        environment=patch.dict(os.environ,{'V3_DEPLOYMENT_ID':'private-test','V3_ACCOUNT_IMAGE':'private-test',
            'V3_NETWORK':'private-test','V3_ACCOUNT_MEMORY':'4g','V3_ACCOUNT_SWAP':'0'})
        environment.start()
        self.addCleanup(environment.stop)
        client=Mock()
        client.containers.list.return_value=[]
        fingerprint=Mock(return_value={'profile_version':2,'hostname':'fixed','machine_id':'a'*32,
            'mac':'02:00:00:00:00:01','tz':'UTC','lang':'en_US.UTF-8'})
        self.runtime=AccountRuntime(client,self.root,self.root,database,fingerprint,None,
            lambda account:'identity-'+str(account.get('cc2api_account_id')))
        self.addCleanup(self.runtime.heartbeat_pool.shutdown)
        self.review=self.runtime.reviews
        self.row=self.runtime._row('synthetic',1)
        self.account={'id':1,'name':'synthetic','cc2api_account_id':None}
        self.job={'row':self.row,'account':self.account,'run_id':'review','source':'run:review:0',
            'private_relative':'project-review-private/test'}
        self.credentials={'claudeAiOauth':{'accessToken':'synthetic-at','refreshToken':'synthetic-rt','expiresAt':time.time()*1000+3600000}}
        write_document(self.root/'profiles/synthetic/.credentials.json',self.credentials)
        write_document(self.root/'project-review-private/test/access/.credentials.json',self.credentials)
        self.path=self.root/'project-review-owner-refresh/1.json'

    def test_defer_uses_frozen_run_and_complete_old_identity_does_not_block(self) -> None:
        """当前身份不能替换旧Run；完成的历史待办不阻塞合法新身份。@return None。"""
        self.review.defer_owner_refresh(self.job)
        self.assertEqual('identity-None',read_document(self.path)['identity'])
        changed={**self.account,'cc2api_account_id':7}
        self.assertIsNone(self.review.owner_refresh_state(changed))
        self.assertEqual('identity-None',read_document(self.path)['identity'])
        state=read_document(self.path)
        write_document(self.path,{**state,'status':'complete'})
        self.assertIsNone(self.review.owner_refresh_state(changed))

    def test_completed_request_between_snapshot_and_claim_is_not_refreshed_again(self) -> None:
        """同请求完成与新retry交错，锁内重读阻止第二次强制刷新。@return None。"""
        self.review.defer_owner_refresh(self.job)
        state=read_document(self.path)
        callback=Mock()
        with patch.object(self.review,'owner_refresh_state',side_effect=[state,None]):
            self.assertFalse(self.review.retry_owner_refresh(self.account,callback))
        callback.assert_not_called()
        self.assertEqual('waiting',read_document(self.path)['status'])

    def test_binding_change_while_waiting_rejects_stale_refresh(self) -> None:
        """待办线程必须重读完整账号，改绑后不能刷新原本地RT。@return None。"""
        self.review.defer_owner_refresh(self.job)
        with self.database() as connection:
            connection.execute('UPDATE accounts SET cc2api_account_id=7 WHERE id=1')
        done=threading.Event()
        original=write_document

        def observe(path,value,*args,**kwargs):
            original(path,value,*args,**kwargs)
            if path==self.path and value.get('status')=='error':
                done.set()

        callback=Mock()
        with patch('project_review_runtime.write_document',side_effect=observe):
            self.assertTrue(self.review.retry_owner_refresh(self.account,callback))
            self.assertTrue(done.wait(3))
        callback.assert_not_called()
        self.assertEqual('error',read_document(self.path)['status'])

    def test_actual_orphan_blocks_running_pool_and_only_stopped_instance_is_removed(self) -> None:
        """没有登记的运行评审不能当空池，已停止实例才可清理。@return None。"""
        labels={**self.runtime._labels(self.row),'vibebench.role':'project-review',
            'vibebench.review-intent':'a'*64,'vibebench.isolation-version':str(ISOLATION_VERSION)}
        child=Mock(labels=labels,status='running')
        self.runtime.client.containers.list.return_value=[child]
        with self.assertRaisesRegex(ValueError,'缺少执行登记'):
            self.review.check_orphans(self.row)
        child.remove.assert_not_called()
        child.status='exited'
        self.review.check_orphans(self.row)
        child.remove.assert_called_once_with()

    def test_new_layout_metrics_use_fixed_cli_remaining_budget(self) -> None:
        """预留512MiB后的CLI指标按实际布局核对，旧限额不能冒充。@return None。"""
        self.runtime._update(self.row,isolation_version=ISOLATION_VERSION)
        limits=scenario_account_limits('4g')
        layout={'schema':1,'review_capacity':1,'limits':{key:list(value) for key,value in limits.items()},'cli_nano_cpus':500000000}
        write_document(self.runtime._root(self.row)/'runtime/project-review-layout.json',layout)
        child=Mock(attrs={'HostConfig':{'Memory':limits['cli'][0],'MemorySwap':limits['cli'][1],
            'NanoCpus':500000000,'PidsLimit':384}})
        child.exec_run.return_value=SimpleNamespace(exit_code=0,output=json.dumps({'memory':limits['cli'][0],'samples':[]}).encode())
        self.assertEqual(limits['cli'][0],self.runtime._sample_cli_metrics(self.row,child)['constrained_memory'])
        child.exec_run.return_value=SimpleNamespace(exit_code=0,output=json.dumps({'memory':limits['cli'][0]+512*1024**2,'samples':[]}).encode())
        with self.assertRaisesRegex(ValueError,'角色预算不符'):
            self.runtime._sample_cli_metrics(self.row,child)

    def test_stopped_or_missing_private_container_skips_exec_and_releases_record(self) -> None:
        """退出或缺失子容器不再exec清理，释放不改固定CLI和原凭据。@return None。"""
        for state in ('exited','missing'):
            with self.subTest(state=state):
                job=self.runtime.claim(self.row,self.account,'run:review:'+state,shared_cli=True)
                job.update(execution_role='project-review',private_relative='project-review-private/test',review_intent='a'*64,
                    exec='old-exec',handle='test')
                self.runtime._save_execution(job)
                child=Mock(status='exited') if state=='exited' else None
                with patch.object(self.review,'container',return_value=child),patch.object(self.runtime,'_cleanup_shared_job') as cleanup:
                    self.runtime.cleanup(job['token'])
                cleanup.assert_not_called()
                if child:
                    child.exec_run.assert_not_called()
                    child.stop.assert_not_called()
                    child.remove.assert_called_once_with()
                self.assertFalse(self.runtime.environment_jobs(self.row['environment_id']))
                self.assertFalse(self.runtime._execution_path(job).exists())

    def test_release_failure_retains_private_holder_and_persistent_intent(self) -> None:
        """无法停止真实子容器或退租失败，名额和创建意图都不假报释放。@return None。"""
        job=self.runtime.claim(self.row,self.account,'run:review:failure',shared_cli=True)
        job.update(execution_role='project-review',private_relative='project-review-private/test',review_intent='a'*64)
        self.runtime._save_execution(job)
        child=Mock(status='running')
        child.stop.side_effect=RuntimeError('模拟Docker停止失败')
        with patch.object(self.review,'container',return_value=child),patch.object(self.runtime,'_cleanup_shared_job'):
            with self.assertRaises(RuntimeError):
                self.runtime.cleanup(job['token'])
        self.assertEqual([job],self.runtime.environment_jobs(self.row['environment_id']))
        self.assertTrue(self.runtime._execution_path(job).exists())
        child.status='exited'
        with patch.object(self.review,'container',return_value=child),patch.object(self.runtime,'_lease',side_effect=RuntimeError('模拟退租失败')):
            with self.assertRaises(RuntimeError):
                self.runtime.cleanup(job['token'])
        self.assertEqual([job],self.runtime.environment_jobs(self.row['environment_id']))
        self.assertTrue(self.runtime._execution_path(job).exists())

    def test_rebuilt_environment_supersedes_old_request_without_forging_completion(self) -> None:
        """重建后新代可准入，旧待办归档为失效而非刷新成功。@return None。"""
        self.review.defer_owner_refresh(self.job)
        old=read_document(self.path)
        self.runtime._update(self.row,generation=self.row['generation']+1)
        current=self.runtime._row('synthetic',1)
        self.assertIsNone(self.review.owner_refresh_state(self.account))
        callback=Mock()
        self.assertFalse(self.review.retry_owner_refresh(self.account,callback))
        callback.assert_not_called()
        self.review.defer_owner_refresh({**self.job,'row':current,'source':'run:new-generation:0'})
        new=read_document(self.path)
        self.assertEqual(current['generation'],new['environment_generation'])
        archived=read_document(self.path.parent/'archive'/(old['request_id']+'.json'))
        self.assertEqual(('superseded','waiting'),(archived['status'],archived['previous_status']))
        self.assertNotEqual(old['request_id'],new['request_id'])

    def test_owner_replaced_rejected_token_allows_new_request_but_same_token_stays_blocked(self) -> None:
        """原所有者发布新AT后旧失败不阻塞；未更换凭据时仍保留失败上限。@return None。"""
        self.review.defer_owner_refresh(self.job)
        state=read_document(self.path)
        write_document(self.path,{**state,'status':'error','attempts':2})
        self.assertEqual('error',self.review.owner_refresh_state(self.account)['status'])
        changed={'claudeAiOauth':{**self.credentials['claudeAiOauth'],'accessToken':'synthetic-restored-at'}}
        write_document(self.root/'profiles/synthetic/.credentials.json',changed)
        self.assertIsNone(self.review.owner_refresh_state(self.account))
        write_document(self.root/'project-review-private/test/access/.credentials.json',changed)
        self.review.defer_owner_refresh({**self.job,'source':'run:restored-token:0'})
        self.assertEqual('waiting',self.review.owner_refresh_state(self.account)['status'])
        self.assertEqual('superseded',read_document(self.path.parent/'archive'/(state['request_id']+'.json'))['status'])

    def test_late_callback_cannot_force_refresh_for_new_request(self) -> None:
        """旧线程即使拿到owner锁，也不能替新request刷新或覆盖凭据。@return None。"""
        self.review.defer_owner_refresh(self.job)
        request={**read_document(self.path),'request_id':'b'*64}
        runner=Mock()
        with patch.multiple(main,get_db=self.database,account_runtime=self.runtime,runner=runner):
            with self.assertRaisesRegex(ValueError,'代次已经变化'):
                main._refresh_project_review_owner(self.account,request)
        runner.refresh_account_oauth_token.assert_not_called()

    def test_current_request_forces_original_owner_with_frozen_scope(self) -> None:
        """同一有效请求复用原owner并明确强制刷新，不在评审中引入RT所有者。@return None。"""
        self.review.defer_owner_refresh(self.job)
        request=read_document(self.path)
        runner=Mock()
        runner.refresh_account_oauth_token.return_value=True
        with patch.multiple(main,get_db=self.database,account_runtime=self.runtime,runner=runner):
            main._refresh_project_review_owner(self.account,request)
        self.assertEqual(1,runner.refresh_account_oauth_token.call_count)
        call=runner.refresh_account_oauth_token.call_args
        self.assertEqual(1,call.args[0]['id'])
        self.assertEqual({'force_refresh':True},call.kwargs)
