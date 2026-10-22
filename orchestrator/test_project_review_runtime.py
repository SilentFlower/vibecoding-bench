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

from docker.errors import APIError

from account_isolation import ISOLATION_VERSION, role_labels
from account_runtime import AccountRuntime, RuntimeBusy
from project_library import read_document, write_document
from project_review_runtime import SERIAL_MODE
from resource_budget import isolated_account_limits, scenario_account_limits, serial_review_limits
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

    def _serial_fixture(self, legacy: bool = False) -> SimpleNamespace:
        """创建带状态变化的容器替身，核真实持久交接和恢复。@param legacy 旧布局。@return 夹具。"""
        fingerprint={**json.loads(self.row['fingerprint_json']),'mem':'1536m','swap':'2048m'}
        self.runtime._update(self.row,fingerprint_json=json.dumps(fingerprint),generation=1,
            isolation_version=ISOLATION_VERSION,container_id='fixed-cli',network_container_id='network',
            sender_container_id='sender',state='ready')
        limits=isolated_account_limits('1536m','2048m')
        if legacy:
            limits=scenario_account_limits('1536m','2048m')
            write_document(self.runtime._root(self.row)/'runtime/project-review-layout.json',
                {'schema':1,'review_capacity':1,'limits':{key:list(value) for key,value in limits.items()},
                 'cli_nano_cpus':1000000000,'review_nano_cpus':500000000})
        events=[]
        roles={role:Mock(id=self.row[column],labels=role_labels(self.runtime,self.row,role),status='running',
            attrs={'HostConfig':{'Memory':limits[role][0],'MemorySwap':limits[role][1],
                'NanoCpus':(1000000000 if legacy else 1500000000) if role=='cli' else 250000000,
                'PidsLimit':(384 if legacy else 512) if role=='cli' else 128}})
            for role,column in (('cli','container_id'),('network','network_container_id'),('sender','sender_container_id'))}
        cli=roles['cli']

        def stop(timeout):
            """模拟已确认的原容器退出。@param timeout 停止截止。@return None。"""
            events.append('cli-stopped')
            cli.status='exited'

        def start():
            """模拟恢复同一个容器。@return None。"""
            events.append('cli-started')
            cli.status='running'

        cli.stop.side_effect=stop
        cli.start.side_effect=start
        cli.exec_run.return_value=SimpleNamespace(exit_code=0,output=b'{"orphans":[]}')
        containers={role.id:role for role in roles.values()}
        self.runtime.client.containers.get.side_effect=lambda identifier:containers[identifier]
        for name in ('_wait_network','_sender_active','check_system_profile'):
            self.enterContext(patch.object(self.runtime,name))
        job=self.runtime.claim(self.row,self.account,'run:review:0')
        job.update(execution_role='project-review',private_relative='project-review-private/test',
            review_intent='a'*64,run_id='review',resource_mode=SERIAL_MODE)
        self.runtime._save_execution(job)
        return SimpleNamespace(cli=cli,roles=roles,containers=containers,events=events,job=job,
            layout=self.review.serial_layout(self.row,cli))

    def _private_child(self, fixture: SimpleNamespace) -> Mock:
        """登记只包含本评审的独立容器。@param fixture 交接夹具。@return 私有容器。"""
        child=Mock(id='private-review',labels=self.review.labels(fixture.job),status='running')

        def stop(timeout):
            """记录私有进程空间已退出。@param timeout 停止截止。@return None。"""
            fixture.events.append('review-stopped')
            child.status='exited'

        child.stop.side_effect=stop
        fixture.containers[child.id]=child
        fixture.job['review_container_id']=child.id
        self.runtime._save_execution(fixture.job)
        self.runtime.client.containers.list.return_value=[child]
        return child

    def test_serial_budget_needs_no_reservation_and_preserves_existing_limits(self) -> None:
        """普通和旧预留布局都能串行复用，固定配额不被改写。@return None。"""
        fixture=self._serial_fixture()
        self.assertEqual((1152*1024**2,1152*1024**2),serial_review_limits('1536m','2048m'))
        self.assertEqual([1152*1024**2]*2,fixture.layout['limits']['review'])
        self.assertFalse((self.runtime._root(self.row)/'runtime/project-review-layout.json').exists())
        self.assertEqual([1152*1024**2,3200*1024**2],fixture.layout['limits']['cli'])
        self.assertEqual((512*1024**2,)*2,serial_review_limits('896m'))
        with self.assertRaises(ValueError):
            serial_review_limits('895m')

    def test_serial_cleanup_stops_review_before_restoring_same_cli(self) -> None:
        """非共享评审完整清理后恢复原 CLI，网络与发送器不停止。@return None。"""
        fixture=self._serial_fixture()
        original=dict(fixture.cli.attrs['HostConfig'])
        self.review.prepare_serial(fixture.job,fixture.cli,fixture.layout)
        self.assertEqual('exited',fixture.cli.status)
        child=self._private_child(fixture)
        self.review._serial_phase(fixture.job,'review_running',review_container_id=child.id)
        with self.assertRaises(RuntimeBusy):
            self.runtime.claim(self.row,self.account,'run:other:0',shared_cli=True)
        self.runtime.cleanup(fixture.job['token'])
        self.assertEqual(['cli-stopped','review-stopped','cli-started'],fixture.events)
        self.assertEqual(original,fixture.cli.attrs['HostConfig'])
        self.assertIsNone(self.review.serial_state(self.row))
        self.assertFalse(self.runtime.environment_jobs(self.row['environment_id']))
        for role in ('network','sender'):
            fixture.roles[role].stop.assert_not_called()
            fixture.roles[role].start.assert_not_called()

    def test_serial_unconfirmed_stop_keeps_gate_and_never_starts_review(self) -> None:
        """暂停或停止结果未知时，交接记录阻止后续执行。@return None。"""
        fixture=self._serial_fixture()
        fixture.cli.stop.side_effect=lambda **kwargs:None
        with self.assertRaisesRegex(ValueError,'尚未停止'):
            self.review.prepare_serial(fixture.job,fixture.cli,fixture.layout)
        self.assertEqual('cli_stopping',self.review.serial_state(self.row)['phase'])
        self.runtime.client.containers.run.assert_not_called()
        with self.assertRaises(RuntimeBusy):
            self.runtime.claim(self.row,self.account,'run:other:0')

    def test_serial_orphan_process_is_not_killed_to_make_room(self) -> None:
        """未知进程需要对账，不能为了评审主动终止旧任务。@return None。"""
        fixture=self._serial_fixture()
        fixture.cli.exec_run.return_value=SimpleNamespace(exit_code=0,output=b'{"orphans":[{"pid":123}]}')
        with self.assertRaisesRegex(ValueError,'未登记进程'):
            self.review.prepare_serial(fixture.job,fixture.cli,fixture.layout)
        fixture.cli.stop.assert_not_called()
        self.assertIsNone(self.review.serial_state(self.row))

    def test_serial_private_stop_failure_cannot_restore_primary_or_release(self) -> None:
        """评审停止失败时保持原 CLI 停止并保留占用。@return None。"""
        fixture=self._serial_fixture()
        self.review.prepare_serial(fixture.job,fixture.cli,fixture.layout)
        child=self._private_child(fixture)
        child.stop.side_effect=RuntimeError('模拟私有容器停止失败')
        with self.assertRaises(RuntimeError):
            self.runtime.cleanup(fixture.job['token'])
        fixture.cli.start.assert_not_called()
        self.assertEqual('exited',fixture.cli.status)
        self.assertTrue(self.runtime._execution_path(fixture.job).exists())
        self.assertEqual([fixture.job],self.runtime.environment_jobs(self.row['environment_id']))

    def test_serial_restore_failure_retains_record_then_retries(self) -> None:
        """恢复失败后原记录可重试，不能提前释放资源占用。@return None。"""
        fixture=self._serial_fixture()
        self.review.prepare_serial(fixture.job,fixture.cli,fixture.layout)
        child=self._private_child(fixture)
        fixture.cli.start.side_effect=RuntimeError('模拟恢复失败')
        with self.assertRaises(RuntimeError):
            self.runtime.cleanup(fixture.job['token'])
        self.assertEqual('exited',child.status)
        self.assertEqual('cli_restoring',self.review.serial_state(self.row)['phase'])
        self.assertTrue(self.runtime._execution_path(fixture.job).exists())
        fixture.cli.start.side_effect=lambda:setattr(fixture.cli,'status','running')
        self.runtime.cleanup(fixture.job['token'])
        self.assertIsNone(self.review.serial_state(self.row))
        self.assertFalse(self.runtime.environment_jobs(self.row['environment_id']))

    def test_serial_restart_recovers_persisted_nonshared_review(self) -> None:
        """管理服务丢失内存登记后，从单作业记录收口评审再恢复。@return None。"""
        fixture=self._serial_fixture()
        self.review.prepare_serial(fixture.job,fixture.cli,fixture.layout)
        self._private_child(fixture)
        self.runtime.jobs.clear()
        self.runtime.reconcile(self.row['environment_id'])
        self.assertEqual(['cli-stopped','review-stopped','cli-started'],fixture.events)
        self.assertFalse(self.runtime._execution_path(fixture.job).exists())
        self.assertIsNone(self.review.serial_state(self.row))
        self.assertEqual('ready',self.runtime._row('synthetic',1)['state'])

    def test_serial_wrong_generation_and_changed_limits_refuse_restore(self) -> None:
        """迟到代次或被改写的容器限额不得自动恢复。@return None。"""
        fixture=self._serial_fixture()
        self.review.prepare_serial(fixture.job,fixture.cli,fixture.layout)
        with self.assertRaisesRegex(ValueError,'代次不符'):
            self.review.serial_state({**self.row,'generation':self.row['generation']+1})
        fixture.cli.attrs['HostConfig']['Memory']+=1
        with self.assertRaisesRegex(ValueError,'配额发生变化'):
            self.runtime.cleanup(fixture.job['token'])
        fixture.cli.start.assert_not_called()

    def test_serial_legacy_layout_keeps_original_cli_budget(self) -> None:
        """旧环境的 CLI 仍为原配额，评审只在停止后借原总预算。@return None。"""
        fixture=self._serial_fixture(legacy=True)
        self.assertEqual(640*1024**2,fixture.cli.attrs['HostConfig']['Memory'])
        self.assertEqual([1152*1024**2]*2,fixture.layout['limits']['review'])
        self.review.prepare_serial(fixture.job,fixture.cli,fixture.layout)
        self.runtime.cleanup(fixture.job['token'])
        self.assertEqual(640*1024**2,fixture.cli.attrs['HostConfig']['Memory'])

    def test_serial_public_cpu_overbudget_is_rejected_before_switch(self) -> None:
        """公共角色也计入有限 CPU 预算，不能额外叠加评审份额。@return None。"""
        fixture=self._serial_fixture()
        fixture.roles['network'].attrs['HostConfig']['NanoCpus']+=1
        with self.assertRaisesRegex(ValueError,'CPU 限额超过'):
            self.review.serial_layout(self.row,fixture.cli)
        fixture.cli.stop.assert_not_called()

    def test_serial_record_without_execution_remains_blocked(self) -> None:
        """不能只凭孤立切换记录伪造退租和恢复成功。@return None。"""
        fixture=self._serial_fixture()
        self.review.prepare_serial(fixture.job,fixture.cli,fixture.layout)
        self.runtime._execution_path(fixture.job).unlink()
        self.runtime.jobs.clear()
        self.runtime.reconcile(self.row['environment_id'])
        fixture.cli.start.assert_not_called()
        self.assertIsNotNone(self.review.serial_state(self.row))
        self.assertIn(self.runtime._row('synthetic',1)['state'],('reconcile','cli_reconcile'))
        with self.assertRaisesRegex(ValueError,'交接未确认收口'):
            self.runtime._recover_cli(self.row)
        fixture.cli.start.assert_not_called()

    def test_missing_switch_record_cannot_release_a_stopped_primary(self) -> None:
        """交接记录丢失且原 CLI 仍停止时，不能假报已经恢复并清执行记录。@return None。"""
        fixture=self._serial_fixture()
        self.review.prepare_serial(fixture.job,fixture.cli,fixture.layout)
        self._private_child(fixture)
        self.review.serial_path(self.row).unlink()
        with self.assertRaisesRegex(ValueError,'无法确认固定 CLI 已恢复'):
            self.runtime.cleanup(fixture.job['token'])
        self.assertTrue(self.runtime._execution_path(fixture.job).exists())
        self.assertEqual('exited',fixture.cli.status)
        self.assertIn(self.runtime._row('synthetic',1)['state'],('reconcile','cli_reconcile'))
        fixture.cli.start.assert_not_called()

    def test_api_ensure_does_not_wake_cli_during_serial_review(self) -> None:
        """API 准备允许访问发送器，但不唤醒已让出资源的固定 CLI。@return None。"""
        fixture=self._serial_fixture()
        self.review.prepare_serial(fixture.job,fixture.cli,fixture.layout)
        self.runtime.release_id='serial-test'
        self.runtime.client.images.get.return_value.attrs={'Config':{'Labels':{
            'vibebench.product':'v3','vibebench.role':'account','vibebench.release':'serial-test'}}}
        with patch.object(self.runtime,'_container',return_value=fixture.cli):
            row,container=self.runtime.ensure(self.account)
            self.assertEqual(self.row['container_id'],row['container_id'])
            self.assertIs(fixture.cli,container)
            with self.assertRaises(RuntimeBusy):
                self.runtime.ensure(self.account,'9.9.9')
        fixture.cli.start.assert_not_called()
        self.assertEqual('exited',fixture.cli.status)

    def test_busy_account_waits_for_review_without_blocking_business(self) -> None:
        """尚有 CLI 占用是可重试等待，不能误报评审环境损坏。@return None。"""
        fixture=self._serial_fixture()
        result=self.review.admission(self.account)
        self.assertFalse(result['allowed'])
        self.assertFalse(result['blocked'])
        fixture.cli.stop.assert_not_called()

    def test_review_cannot_stop_cli_between_profile_check_and_claim(self) -> None:
        """评审在普通任务检查时竞争，必须等待并返回可重试忙碌，不能制造409。@return None。"""
        fixture=self._serial_fixture()
        self.runtime.release(fixture.job)
        attempted,finished=threading.Event(),threading.Event()
        outcomes=[]
        immediate=[]
        environment_lock=self.runtime.environment_lock(self.row['environment_id'])

        def compete() -> None:
            """在画像检查窗口竞争真实认领边界，有界等待避免残留线程。@return None。"""
            acquired=environment_lock.acquire(blocking=False)
            immediate.append(acquired)
            attempted.set()
            try:
                if not acquired:
                    acquired=environment_lock.acquire(timeout=5)
                    if not acquired:
                        raise TimeoutError('等待普通任务完成认领超时')
                job=self.runtime.claim(self.row,self.account,'run:review:0')
                job.update(execution_role='project-review',private_relative='project-review-private/test',
                    review_intent='a'*64,run_id='review',resource_mode=SERIAL_MODE)
                self.runtime._save_execution(job)
                self.review.prepare_serial(job,fixture.cli,fixture.layout)
                outcomes.append('review-started')
            except Exception as error:
                outcomes.append(error)
            finally:
                if acquired:
                    environment_lock.release()
                finished.set()

        contender=threading.Thread(target=compete,daemon=True)

        def profile_check(row: dict, container) -> None:
            """让竞争恰好发生在画像exec之前，旧实现会先停止固定CLI。@param row 环境。@param container CLI。@return None。"""
            contender.start()
            self.assertTrue(attempted.wait(5))
            # 旧实现允许评审直接拿锁并停机，等其动作完成后再观察，避免概率竞态。
            if immediate[0]:
                self.assertTrue(finished.wait(5))
            if container.status != 'running':
                raise APIError('409: 固定 CLI 已停止，画像exec失败')

        def version_ready(container, version: str) -> None:
            """版本安装期间竞争方可拿环境锁，仍被已认领作业挡住。@param container CLI。@param version 版本。@return None。"""
            self.assertTrue(finished.wait(5),'版本安装不应持有环境生命周期锁')

        self.runtime.check_system_profile.side_effect=profile_check
        try:
            with patch.object(self.runtime,'ensure',return_value=(self.row,fixture.cli)), \
                    patch.object(self.runtime,'_ensure_version',side_effect=version_ready):
                with self.runtime._cli_setup(self.account,'run:ordinary:0','2.1.293',shared_cli=True) as (_,_,job):
                    self.assertEqual('running',fixture.cli.status)
                    self.assertTrue(job['claimed'])
                self.assertTrue(finished.wait(5))
            self.assertEqual(1,len(outcomes))
            self.assertIsInstance(outcomes[0],RuntimeBusy)
            fixture.cli.stop.assert_not_called()
            self.assertIsNone(self.review.serial_state(self.row))
        finally:
            self.runtime.check_system_profile.side_effect=None
            for current in self.runtime.environment_jobs(self.row['environment_id']):
                self.runtime.release(current)
            if contender.ident is not None:
                contender.join(timeout=5)
        self.assertFalse(contender.is_alive())

    def test_serial_release_failure_keeps_gate_after_cli_restored(self) -> None:
        """原 CLI 恢复后退租失败，仍保留本执行记录直到成功重试。@return None。"""
        fixture=self._serial_fixture()
        self.review.prepare_serial(fixture.job,fixture.cli,fixture.layout)
        self._private_child(fixture)
        with patch.object(self.runtime,'_lease',side_effect=RuntimeError('模拟退租失败')):
            with self.assertRaises(RuntimeError):
                self.runtime.cleanup(fixture.job['token'])
        self.assertEqual('running',fixture.cli.status)
        self.assertEqual('cli_restoring',self.review.serial_state(self.row)['phase'])
        self.assertTrue(self.runtime._execution_path(fixture.job).exists())
        with self.assertRaises(RuntimeBusy):
            self.runtime.claim(self.row,self.account,'run:other:0',shared_cli=True)
        self.runtime.cleanup(fixture.job['token'])
        self.assertIsNone(self.review.serial_state(self.row))

    def test_serial_ownership_on_one_account_does_not_lock_another(self) -> None:
        """切换记录和占用均按环境隔离，其他账号仍可认领 CLI。@return None。"""
        fixture=self._serial_fixture()
        self.review.prepare_serial(fixture.job,fixture.cli,fixture.layout)
        other_row=self.runtime._row('synthetic-other',2)
        other=self.runtime.claim(other_row,{'id':2,'name':'synthetic-other'},'run:other:0',shared_cli=True)
        self.assertTrue(other['claimed'])
        self.assertEqual([fixture.job],self.runtime.environment_jobs(self.row['environment_id']))
        self.runtime.release(other)

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
