"""以真实 SQLite 和共享额度门禁核对 Pi 准入与原生错误补证。"""
import json
import os
import time
import unittest
from unittest.mock import Mock, patch

import main
import test_quota
from account_runtime import AccountRuntime


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
