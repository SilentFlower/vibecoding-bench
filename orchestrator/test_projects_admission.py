"""以真实 SQLite 和共享额度门禁核对 Pi 准入与原生错误补证。"""
import json
import os
import time
import unittest
from unittest.mock import Mock, patch

import main
import test_quota
from account_runtime import AccountRuntime
from pi_owners import AccountPiOwners


class ProjectsAdmissionTests(unittest.TestCase):
    """新 Pi 使用共享被动事实，运行时段、额度和人工门禁具有不同的恢复语义。"""

    def setUp(self):
        """创建正式数据表、固定身份和禁止网络查询的隔离额度运行器。:return: None。"""
        test_quota.QuotaGuardTests.setUp(self)
        environment = patch.dict(os.environ, {'V3_DEPLOYMENT_ID': 'projects-quota-tests',
            'V3_ACCOUNT_IMAGE': 'synthetic-account', 'V3_NETWORK': 'synthetic-network',
            'V3_MAX_ACTIVE_ACCOUNTS': '1', 'PER_ACCOUNT_CONCURRENCY': '2'})
        environment.start()
        self.addCleanup(environment.stop)
        self.runtime = AccountRuntime(Mock(), self.base, self.base, main.get_db, Mock(), Mock())
        self.addCleanup(self.runtime.heartbeat_pool.shutdown, wait=True)
        runtime_patch = patch.object(main, 'account_runtime', self.runtime)
        runtime_patch.start()
        self.addCleanup(runtime_patch.stop)
        self.owners = AccountPiOwners()
        owner_patch = patch.object(main, 'pi_owners', self.owners)
        owner_patch.start()
        self.addCleanup(owner_patch.stop)
        self.identifier = 'a' * 32
        self.source = 'projects:' + self.identifier + ':1'
        self.started = time.time() - 60
        self.work = {'runtime_json': json.dumps({'source': self.source})}
        connection = main.get_db()
        try:
            with connection:
                connection.execute('UPDATE accounts SET warmup_quota_5h_limit_percent=30,'
                    'warmup_quota_7d_limit_percent=50 WHERE id=1')
                self.account = dict(connection.execute('SELECT * FROM accounts WHERE id=1').fetchone())
                connection.execute('INSERT INTO projects_agents(account_id,updated_at) VALUES(1,?)', (time.time(),))
                connection.execute('INSERT INTO projects_work(id,account_id,project_key,objective_id,goal,definition_json,'
                    'library_root,library_digest,settings_json,generation,status,session_id,runtime_json,account_identity,'
                    'segment_started_at,created_at) VALUES(?,1,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                    (self.identifier, 'example', 'feature', '合成工程目标', '{}', '/synthetic', 'frozen', '{}', 1,
                        'running', '00000000-0000-4000-8000-000000000001', self.work['runtime_json'],
                        main._quota_identity(self.account), self.started, self.started))
        finally:
            connection.close()

    def observe(self, used=10, observed_at=None, reset=None):
        """写入正式被动额度事实。:param used: 已用百分比。:param observed_at: 原观察时间。:param reset: 可信重置。:return: None。"""
        observed = observed_at or time.time()
        self.guard._observe(self.account, main._quota_identity(self.account), {'observed_at': observed,
            'origin': 'cli', 'allowed': True, 'windows': {'five_hour': {'observed_at': observed,
                'utilization': used, 'reset_at': reset or observed + 3600, 'exhausted': False, 'rejected': False}}})

    def facts(self, **fields):
        """提供终端已核对的结构化补证。:param fields: 覆盖字段。:return: 不含正文的补证。"""
        return {'account_error': None, 'quota_limited': True, 'window': 'five_hour',
            'retry_at': None, 'observed_at': time.time() - 1, 'evidence_key': 'e' * 64,
            'native_error': 'rate_limit', **fields}

    def claimed_start(self):
        """构造已认领但终端尚未返回、原工作仍保存旧代次的真实启动间隙。:return: 原工作、作业及所有权令牌。"""
        connection = main.get_db()
        try:
            with connection:
                connection.execute("UPDATE projects_agents SET generation=2,status='running',current_work_id=? WHERE account_id=1",
                    (self.identifier,))
                connection.execute("UPDATE projects_work SET status='paused',runtime_json=NULL WHERE id=?", (self.identifier,))
            work = dict(connection.execute('SELECT * FROM projects_work WHERE id=?', (self.identifier,)).fetchone())
        finally:
            connection.close()
        token = self.owners.claim(1, 'projects', 2)
        job = {'row': {'account_id': 1, 'environment_id': 'claimed-fixture'},
            'source': f'projects:{self.identifier}:2', 'shared_cli': True, 'claimed': True}
        with self.runtime.lock:
            self.runtime._register_job(job)
        return work, job, token

    def test_claimed_start_excludes_only_the_current_owner_despite_old_work_generation(self):
        """终端准备中的当前代次不能把自身租约当作其他执行，原工作旧代次保持可恢复。:return: None。"""
        work, job, _ = self.claimed_start()
        self.assertEqual(1, work['generation'])
        self.assertIsNone(work['runtime_json'])
        self.assertTrue(main._projects_admission(self.account, work)['allowed'])
        self.assertEqual(f'projects:{self.identifier}:2', job['source'])

    def test_claimed_start_requires_matching_account_pointer_generation_and_active_status(self):
        """相同来源文本不能代替当前账号、目标、代次和运行状态的完整绑定。:return: None。"""
        work, _, _ = self.claimed_start()
        connection = main.get_db()
        try:
            for field, value in (('current_work_id', 'other-work'), ('generation', 3), ('status', 'paused')):
                with self.subTest(field=field):
                    with connection:
                        connection.execute("UPDATE projects_agents SET generation=2,status='running',current_work_id=? WHERE account_id=1", (self.identifier,))
                        connection.execute('UPDATE projects_agents SET ' + field + '=? WHERE account_id=1', (value,))
                    self.assertEqual('busy', main._projects_admission(self.account, work)['reason'])
            with connection:
                connection.execute("UPDATE projects_agents SET generation=2,status='running',current_work_id=? WHERE account_id=1", (self.identifier,))
            self.assertEqual('busy', main._projects_admission(self.account, {**work, 'account_id': 2})['reason'])
        finally:
            connection.close()

    def test_claimed_start_keeps_other_work_generation_namespace_and_owner_busy(self):
        """只排除自己的精确来源，其他目标、旧代次、其他空间及失去所有权都继续互斥。:return: None。"""
        work, job, _ = self.claimed_start()
        for source in (f'projects:other-work:2', f'projects:{self.identifier}:1', f'warmup:{self.identifier}:2', 'run:other:1'):
            with self.subTest(source=source):
                job['source'] = source
                self.assertEqual('busy', main._projects_admission(self.account, work)['reason'])
        job['source'] = f'projects:{self.identifier}:2'
        for kind in (None, 'warmup'):
            with self.subTest(owner=kind):
                owners = AccountPiOwners()
                if kind:
                    owners.claim(1, kind, 2)
                with patch.object(main, 'pi_owners', owners):
                    self.assertEqual('busy', main._projects_admission(self.account, work)['reason'])

    def test_claimed_start_preserves_real_quota_auth_and_login_gates(self):
        """识别自身准备租约不能绕过实际登录、额度阈值和认证失败门禁。:return: None。"""
        work, _, _ = self.claimed_start()
        with patch.object(main, 'login_manager', Mock(has_active_name=Mock(return_value=True))):
            self.assertEqual('login', main._projects_admission(self.account, work)['reason'])
        self.observe(30)
        self.assertEqual('quota', main._projects_admission(self.account, work)['reason'])
        self.guard.record_auth_failure(self.account, 'invalid_grant')
        self.assertEqual('account_error', main._projects_admission(self.account, work)['reason'])

    def test_claimed_start_keeps_legacy_and_continuation_execution_busy(self):
        """自身准备租约不能掩盖旧普通任务或继续执行管理器的真实账号占用。:return: None。"""
        work, _, _ = self.claimed_start()
        test_quota.QuotaGuardTests._run(self, rid='legacy-claimed-start')
        self.assertEqual('busy', main._projects_admission(self.account, work)['reason'])
        connection = main.get_db()
        try:
            with connection:
                connection.execute("UPDATE runs SET status='completed' WHERE id='legacy-claimed-start'")
        finally:
            connection.close()
        with patch.object(main, 'continue_manager', Mock(has_active_account=Mock(return_value=True))):
            self.assertEqual('busy', main._projects_admission(self.account, work)['reason'])

    def test_only_real_matching_claim_may_reuse_its_expired_window_recovery_permission(self):
        """自己的真实认领可复用已登记许可，未认领作业或只有所有者时不能凭空借用。:return: None。"""
        work, job, _ = self.claimed_start()
        old = time.time() - 10
        self.guard._observe(self.account, main._quota_identity(self.account), {'observed_at': old,
            'allowed': False, 'windows': {'five_hour': {'observed_at': old,
                'exhausted': True, 'rejected': True, 'reset_at': old + 1}}})
        self.assertTrue(self.guard.admit(self.account, job['source'], warmup=True, workload='warmup'))
        self.assertTrue(main._projects_admission(self.account, work)['allowed'])
        self.assertIsNone(work['runtime_json'])
        job['claimed'] = False
        self.assertEqual('quota', main._projects_admission(self.account, work)['reason'])
        job['claimed'] = True
        job['source'] = f'projects:other-work:2'
        self.assertEqual('quota', main._projects_admission(self.account, work)['reason'])
        with self.runtime.lock:
            self.runtime._remove_job(job)
        self.assertEqual('quota', main._projects_admission(self.account, work)['reason'])

    def test_unknown_first_use_and_disabled_legacy_warmup_still_allow_pi(self):
        """首次未知不制造主动查询，旧定时养号关闭也不关闭 Pi 或它的额度策略。:return: None。"""
        self.assertFalse(self.account['warmup_enabled'])
        gate = main._projects_admission(self.account, None)
        self.assertTrue(gate['allowed'])
        self.assertEqual('allowed', gate['reason'])
        self.assertEqual({'five_hour': 30, 'seven_day': 50}, gate['quota']['limits'])
        self.runner.query_quota.assert_not_called()
        main.cc2api_client.refresh_usage.assert_not_called()

    def test_threshold_hit_retries_only_at_trusted_window_reset(self):
        """达到已用阈值后拒绝启动和输入，并提供可信的恢复时间。:return: None。"""
        reset = time.time() + 100
        self.observe(30, reset=reset)
        gate = main._projects_admission(self.account, self.work)
        self.assertFalse(gate['allowed'])
        self.assertEqual('quota', gate['reason'])
        self.assertTrue(gate['retryable'])
        self.assertEqual(reset, gate['retry_at'])
        self.runner.query_quota.assert_not_called()

    def test_threshold_without_reset_has_no_invented_retry_deadline(self):
        """缺少可信 reset 的阈值等待只能由新被动事实解除。:return: None。"""
        self.guard._observe(self.account, main._quota_identity(self.account), {'observed_at': time.time(),
            'allowed': False, 'windows': {'five_hour': {'utilization': 40}}})
        gate = main._projects_admission(self.account, self.work)
        self.assertEqual('quota', gate['reason'])
        self.assertIsNone(gate['retry_at'])

    def test_rest_window_keeps_known_quota_visible_without_starting_requests(self):
        """休息时段仍显示已有被动用量，不能把暂未执行误画成额度未知。:return: None。"""
        self.observe(12)
        with patch.object(main, '_account_run_window', return_value={'allowed': False,
                'next_open_at': time.time() + 300, 'message': '休息中', 'timezone': 'UTC'}):
            gate = main._projects_admission(self.account, self.work)
        self.assertEqual('window', gate['reason'])
        self.assertEqual(12, gate['quota']['windows']['five_hour']['utilization'])
        self.assertEqual(30, gate['quota']['limits']['five_hour'])
        self.runner.query_quota.assert_not_called()
        main.cc2api_client.refresh_usage.assert_not_called()
        self.assertTrue(gate['retryable'])

    def test_window_and_login_wait_are_retryable_but_environment_is_manual(self):
        """运行时段和登录属于可恢复等待，对账环境必须人工处理。:return: None。"""
        opening = time.time() + 3600
        with patch.object(main, '_account_run_window', return_value={'allowed': False,
                'next_open_at': opening, 'timezone': 'Asia/Shanghai', 'message': '休息中'}):
            gate = main._projects_admission(self.account, None)
        self.assertEqual(('window', True, opening), (gate['reason'], gate['retryable'], gate['retry_at']))
        with patch.object(main, 'login_manager', Mock(has_active_name=Mock(return_value=True))):
            gate = main._projects_admission(self.account, None)
        self.assertEqual(('login', True), (gate['reason'], gate['retryable']))
        connection = main.get_db()
        try:
            with connection:
                connection.execute("INSERT INTO account_environments(environment_id,name,account_id,fingerprint_json,state) "
                    "VALUES(?,'fixture',1,'{}','cli_reconcile')", ('b' * 32,))
        finally:
            connection.close()
        gate = main._projects_admission(self.account, None)
        self.assertEqual(('environment', False), (gate['reason'], gate['retryable']))

    def test_native_rejection_keeps_original_timestamp_and_reset(self):
        """原生限额按它实际发生时刻合并，不把重放赋予新时间。:return: None。"""
        observed = time.time() - 2
        reset = observed + 3600
        facts = self.facts(observed_at=observed, retry_at=reset)
        main._projects_native_quota(self.account, self.source, facts)
        state = self.guard.snapshot(self.account)
        self.assertTrue(state['blocked'])
        self.assertEqual(observed, state['windows']['five_hour']['observed_at'])
        self.assertEqual(reset, state['resume_at'])
        self.observe(5, observed_at=observed + 1, reset=reset)
        main._projects_native_quota(self.account, self.source, facts)
        self.assertFalse(self.guard.snapshot(self.account)['blocked'])

    def test_native_unknown_rejection_has_no_fake_reset(self):
        """只有原生拒绝而无窗口和恢复时间时保存 unknown 门禁，不伪造查询。:return: None。"""
        main._projects_native_quota(self.account, self.source, self.facts(window='unknown'))
        state = self.guard.snapshot(self.account)
        self.assertTrue(state['blocked'])
        self.assertEqual(['unknown'], state['exhausted'])
        self.assertIsNone(state['resume_at'])
        self.runner.query_quota.assert_not_called()
        main.cc2api_client.refresh_usage.assert_not_called()

    def test_auth_failure_requires_manual_recovery_and_old_auth_is_ignored(self):
        """较旧认证错误不能覆盖更新允许事实，新的认证错误明确要求人工介入。:return: None。"""
        now = time.time()
        self.observe(1, observed_at=now - 2)
        main._projects_native_quota(self.account, self.source, self.facts(account_error='invalid_grant',
            quota_limited=False, observed_at=now - 3))
        self.assertNotIn('account_error', self.guard.snapshot(self.account))
        main._projects_native_quota(self.account, self.source, self.facts(account_error='invalid_grant',
            quota_limited=False, observed_at=now - 1))
        gate = main._projects_admission(self.account, self.work)
        self.assertEqual(('account_error', False, None), (gate['reason'], gate['retryable'], gate['retry_at']))

    def test_old_binding_source_generation_or_pre_segment_observation_is_ignored(self):
        """原绑定、旧控制代次及启动前错误不能污染当前账号。:return: None。"""
        main._projects_native_quota(self.account, self.source[:-1] + '2', self.facts())
        main._projects_native_quota(self.account, self.source, self.facts(observed_at=self.started - 1))
        changed = {**self.account, 'cc2api_account_id': 7}
        main._projects_native_quota(changed, self.source, self.facts())
        self.assertFalse(self.guard.snapshot(self.account)['blocked'])
        connection = main.get_db()
        try:
            with connection:
                connection.execute('UPDATE accounts SET cc2api_account_id=7 WHERE id=1')
        finally:
            connection.close()
        main._projects_native_quota(self.account, self.source, self.facts())
        self.assertFalse(self.guard.snapshot(changed)['blocked'])

    def test_expired_common_window_uses_one_persistent_recovery_execution(self):
        """到期后只准一个真实来源更新额度，重启和释放不会重复发放机会。:return: None。"""
        old = time.time() - 10
        self.guard._observe(self.account, main._quota_identity(self.account), {'observed_at': old,
            'allowed': False, 'windows': {'five_hour': {'observed_at': old,
                'exhausted': True, 'rejected': True, 'reset_at': old + 1}}})
        self.assertTrue(main._projects_admission(self.account, None)['allowed'])
        self.assertTrue(self.guard.admit(self.account, self.source, warmup=True, workload='warmup'))
        self.assertTrue(main._projects_admission(self.account, self.work)['allowed'])
        self.guard.release(self.account, self.source)
        self.assertFalse(main._projects_admission(self.account, None)['allowed'])
        restarted = main.QuotaGuard(self.runner)
        self.assertFalse(restarted.admit(self.account, self.source[:-1] + '2', warmup=True, workload='warmup'))
        self.runner.query_quota.assert_not_called()
        main.cc2api_client.refresh_usage.assert_not_called()


if __name__ == '__main__':
    unittest.main()
