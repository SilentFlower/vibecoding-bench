"""用真实账号数据库验证 Pi 养号接入，模型与容器均由本地替身隔离。"""
import json
import os
import threading
import time
import unittest
from unittest.mock import Mock, patch

from fastapi import HTTPException

import main
import test_quota
from pi_owners import AccountPiOwners
from account_runtime import AccountRuntime
from warmup_pi import WarmupPiService


class WarmupPiIntegrationTests(unittest.TestCase):
    """核对旧调度、冻结题库、账号所有权与共同额度的真实接缝。"""

    _run = test_quota.QuotaGuardTests._run

    def setUp(self):
        """创建独立 SQLite、被动额度和可取消的 Pi 替身。:return: None。"""
        test_quota.QuotaGuardTests.setUp(self)
        self.owners = AccountPiOwners()
        environment = patch.dict(os.environ, {'V3_DEPLOYMENT_ID': 'warmup-integration',
            'V3_ACCOUNT_IMAGE': 'synthetic-account', 'V3_NETWORK': 'synthetic-network',
            'V3_MAX_ACTIVE_ACCOUNTS': '1', 'PER_ACCOUNT_CONCURRENCY': '2'})
        environment.start()
        self.addCleanup(environment.stop)
        self.runtime = AccountRuntime(Mock(), self.base, self.base, main.get_db, Mock(), Mock())
        self.addCleanup(self.runtime.heartbeat_pool.shutdown, wait=True)
        self.entered = threading.Event()
        self.pi = Mock()
        self.pi.available.return_value = True

        def run(configuration, tools, event, stop, timeout_sec):
            self.entered.set()
            stop.wait(5)
            return 'stopped'

        self.pi.run.side_effect = run
        self.terminal = Mock()
        self.terminal.usage.return_value = {}
        for name, value in (('account_runtime', self.runtime), ('pi_owners', self.owners),
                ('warmup_pi_service', None), ('warmup_scheduler', main.WarmupScheduler(self.scheduler))):
            patcher = patch.object(main, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.service = WarmupPiService(self.base, main.get_db, main._db_lock, self.terminal, main._projects_account,
            main._warmup_pi_admission, lambda: {'model': 'synthetic'}, main._warmup_pi_topic,
            main.warmup_scheduler._next_run_at, identity=main._quota_identity, owners=self.owners, pi=self.pi)
        patcher = patch.object(main, 'warmup_pi_service', self.service)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(self.service.close)

    def configure(self, enabled=True, threshold=55):
        """设置原账号养号计划，保持原随机间隔。:param enabled: 开关。:param threshold: 软阈值。:return: 最新账号。"""
        connection = main.get_db()
        try:
            with connection:
                connection.execute('UPDATE accounts SET warmup_enabled=?,warmup_next_run_at=?,'
                    'warmup_quota_5h_limit_percent=? WHERE id=1', (int(enabled), 0 if enabled else None, threshold))
            return dict(connection.execute('SELECT * FROM accounts WHERE id=1').fetchone())
        finally:
            connection.close()

    def observe(self, used=20, *, exhausted=False):
        """直接写入正常执行响应的被动事实。:param used: 已用量。:param exhausted: 真耗尽。:return: None。"""
        now = time.time()
        account = main._projects_account(1)
        self.guard._observe(account, main._quota_identity(account), {'observed_at': now, 'origin': 'cli',
            'allowed': not exhausted, 'windows': {'five_hour': {'observed_at': now, 'utilization': used,
                'reset_at': now + 3600, 'exhausted': exhausted, 'rejected': exhausted}}})

    def row(self):
        """读取当前原生养号轮。:return: 当前数据库快照。"""
        return self.service._round(self.service._one('SELECT * FROM warmup_pi_agents WHERE account_id=1'))

    def test_off_defaults_and_configure_recover_never_enable_or_start(self):
        """保存指南和进程恢复都保留关闭状态、空计划与原三至五小时。:return: None。"""
        original = main._projects_account(1)
        self.service.configure(1, 'Keep the exact user guide.', 1800)
        self.service.recover()
        main.warmup_scheduler._tick()
        current = main._projects_account(1)
        for name in ('warmup_enabled', 'warmup_next_run_at', 'warmup_interval_min_hours', 'warmup_interval_max_hours'):
            self.assertEqual(original[name], current[name])
        self.assertFalse(self.service.has_taken_over(1))
        with self.assertRaises(ValueError):
            self.service.start(1)
        self.pi.run.assert_not_called()
        self.terminal.start.assert_not_called()
        self.assertIsNone(self.owners.owner(1))

    def test_old_worker_finishes_before_takeover_and_late_callbacks_cannot_overwrite(self):
        """旧 worker 活跃时不选题；认领新轮后的所有旧回调只写旧历史。:return: None。"""
        self._run('legacy', 'warmup', status='running')
        self.configure()
        self.observe()
        with patch.object(self.service, 'prepare_topic', wraps=main._warmup_pi_topic) as prepare:
            result = main.warmup_scheduler.trigger_account(1)
            self.assertFalse(result['started'])
            prepare.assert_not_called()
            self.pi.run.assert_not_called()
            self.assertFalse(self.service.has_taken_over(1))
        connection = main.get_db()
        with connection:
            connection.execute("UPDATE runs SET status='success' WHERE id='legacy'")
        connection.close()
        main.warmup_scheduler.handle_run_terminal('legacy')
        result = main.run_account_warmup_now(1)
        self.assertTrue(result['started'])
        self.assertEqual('pi', result['engine'])
        self.assertTrue(self.entered.wait(1))
        before = main._projects_account(1)
        original_guard = self.service.has_taken_over
        with patch.object(self.service, 'has_taken_over', wraps=original_guard) as guard:
            connection = main.get_db()
            with connection:
                connection.execute("UPDATE runs SET status='running' WHERE id='legacy'")
            connection.close()
            main.warmup_scheduler.handle_run_started('legacy')
            main.warmup_scheduler.handle_run_sync_failure('legacy', before, ValueError('invalid_grant'))
            main.warmup_scheduler._pause_account(before, 'late worker error')
            connection = main.get_db()
            with connection:
                connection.execute("UPDATE runs SET status='auth_failed',error='invalid_grant' WHERE id='legacy'")
            connection.close()
            main.warmup_scheduler.handle_run_terminal('legacy')
            self.assertGreaterEqual(guard.call_count, 4)
            self.assertTrue(all(call.kwargs.get('connection') is not None for call in guard.call_args_list))
        after = main._projects_account(1)
        for name in ('warmup_enabled', 'warmup_next_run_at', 'warmup_last_status', 'warmup_last_error'):
            self.assertEqual(before[name], after[name])
        self.assertEqual('warmup', self.owners.owner(1)['kind'])

    def test_soft_threshold_blocks_new_round_but_started_round_continues(self):
        """软阈值只阻止新一轮，当前轮继续而共同耗尽仍然拦住。:return: None。"""
        account = self.configure()
        self.observe(60)
        self.assertFalse(main._warmup_pi_admission(account, None)['allowed'])
        work = {'started_at': time.time() - 20, 'status': 'paused', 'runtime_json': None,
            'account_identity': main._quota_identity(account)}
        self.assertTrue(main._warmup_pi_admission(account, work)['allowed'])
        self.observe(100, exhausted=True)
        gate = main._warmup_pi_admission(account, work)
        self.assertFalse(gate['allowed'])
        self.assertEqual('quota', gate['reason'])
        self.guard.record_auth_failure(account, 'invalid_grant')
        self.assertEqual('account_error', main._warmup_pi_admission(account, work)['reason'])
        work['account_identity'] = 'different-owner'
        self.assertEqual('identity', main._warmup_pi_admission(account, work)['reason'])
        self.runner.query_quota.assert_not_called()
        main.cc2api_client.refresh_usage.assert_not_called()

    def test_single_timer_defers_window_and_threshold_without_selecting_or_running(self):
        """原定时器到期扫描先检查时段和软阈值，未放行不选题也不调用模型。:return: None。"""
        self.configure()
        self.observe(60)
        with patch.object(self.service, 'prepare_topic', wraps=main._warmup_pi_topic) as choose:
            main.warmup_scheduler._tick()
            self.assertEqual('quota_wait', main._projects_account(1)['warmup_last_status'])
            self.pi.run.assert_not_called()
            choose.assert_not_called()
        self.configure()
        self.observe(20)
        opening = time.time() + 7200
        with patch.object(main, '_account_run_window', return_value={'allowed': False,
                'next_open_at': opening, 'timezone': 'UTC', 'message': '休息时段'}):
            result = main.warmup_scheduler.trigger_account(1)
        self.assertFalse(result['started'])
        self.assertEqual(opening, main._projects_account(1)['warmup_next_run_at'])
        self.assertIsNone(self.row())
        self.pi.run.assert_not_called()

    def test_native_resume_ignores_soft_threshold_and_retains_hard_admission(self):
        """恢复使用原轮次续聊准入，原生拒绝只接受精确来源、代次和身份。:return: None。"""
        self.configure()
        self.observe()
        self.service.start(1)
        self.assertTrue(self.entered.wait(1))
        row = self.row()
        source = 'warmup:' + row['id'] + ':' + str(row['generation'])
        root = self.base / 'native'
        self.observe(60)
        with self.assertRaises(main.RuntimeBusy):
            main._warmup_pi_quota_context(main._projects_account(1), source, root / 'flows', root / 'controls')
        started = time.time() - 10
        connection = main.get_db()
        with connection:
            connection.execute("UPDATE warmup_pi_rounds SET started_at=?,segment_started_at=?,status='running',runtime_json=? WHERE id=?",
                (started, started, json.dumps({'source': source}), row['id']))
        connection.close()
        env = main._warmup_pi_quota_context(main._projects_account(1), source, root / 'flows', root / 'controls')
        self.assertEqual(source, env['QUOTA_SOURCE'])
        facts = {'quota_limited': True, 'window': 'five_hour', 'observed_at': time.time()}
        main._warmup_pi_native_quota(main._projects_account(1), source[:-1] + '9', facts)
        self.assertFalse(self.guard.snapshot(main._projects_account(1))['blocked'])
        main._warmup_pi_native_quota(main._projects_account(1), source, facts)
        self.assertTrue(self.guard.snapshot(main._projects_account(1))['blocked'])
        with self.assertRaises(main.RuntimeBusy):
            main._warmup_pi_quota_context(main._projects_account(1), source, root / 'flows', root / 'controls')

    def test_topic_history_and_frozen_followups_use_original_topics(self):
        """新旧轮共同避重且保留原补充内容和时序，不借用工程目标。:return: None。"""
        self.configure()
        connection = main.get_db()
        with connection:
            connection.execute("INSERT INTO topics(id,no,title,description,followups_json) VALUES(2,2,'Second','Second topic',?)",
                (json.dumps(['Please add tests.', 'Please improve the interface.']),))
            connection.execute("INSERT INTO topics(id,no,title,description,followups_json) VALUES(3,3,'Third','Third topic',?)",
                (json.dumps(['Please add tests.', 'Please document how to run it.']),))
            connection.execute("INSERT INTO topics(id,no,title,description,enabled) VALUES(4,4,'Disabled','Do not use',0)")
        connection.close()
        self._run('old-topic', 'warmup', status='success')
        account = main._projects_account(1)
        first = main._warmup_pi_topic(account)
        self.assertIn(first['topic_id'], (2, 3))
        self.assertEqual({'claude_code_version', 'claude_effort_level', 'execution_model'}, set(first['settings']))
        self.assertEqual(len(first['followups']), len(first['timing']['offsets_sec']))
        self.assertTrue(all(isinstance(text, str) and text for text in first['followups']))
        self.service._ensure(1)
        connection = main.get_db()
        with connection:
            connection.execute('INSERT INTO warmup_pi_rounds(id,account_id,generation,topic_id,topic_no,title,topic_json,settings_json,'
                'account_identity,status,session_id,created_at) VALUES(?,1,1,?,?,?,?,?,?,?,?,?)',
                ('b' * 32, first['topic_id'], first['topic_no'], first['title'], json.dumps(first),
                    json.dumps(first['settings']), main._quota_identity(account), 'completed', 'native-original', time.time()))
        connection.close()
        second = main._warmup_pi_topic(account)
        self.assertEqual({1, 2, 3} - {1, first['topic_id']}, {second['topic_id']})

    def test_random_schedule_and_config_update_preserve_running_round(self):
        """保存间隔和关闭未来计划不改写当前轮，原三至五小时随机保持不变。:return: None。"""
        self.configure()
        self.observe()
        with patch.object(main.time, 'time', return_value=1000), patch.object(main.random, 'uniform', return_value=14400) as random:
            self.assertEqual(15400, main.warmup_scheduler._next_run_at(main._projects_account(1)))
            random.assert_called_once_with(10800, 18000)
        self.service.start(1)
        self.assertTrue(self.entered.wait(1))
        row = self.row()
        with patch.object(main, '_read_bench_profile_identity', return_value={'accountUuid': 'synthetic'}):
            result = main.update_account_warmup(1, main.WarmupConfigIn(enabled=False, interval_min_hours=4, interval_max_hours=6))
        self.assertIsNone(result['next_run_at'])
        account = main._projects_account(1)
        self.assertFalse(account['warmup_enabled'])
        self.assertEqual('running', account['warmup_last_status'])
        self.assertEqual(row['id'], self.row()['id'])
        self.assertTrue(self.service.view(1)['agents'][0]['controller_active'])
        self.assertIsNone(account['warmup_next_run_at'])
        self.assertEqual((4, 6), (account['warmup_interval_min_hours'], account['warmup_interval_max_hours']))

    def test_thinking_owner_blocks_oauth_changes_and_other_project_owner_defers(self):
        """没有原生终端时同样持有账号，凭据切换与其它 Pi 都不能抢占。:return: None。"""
        self.configure()
        self.observe()
        token = self.owners.claim(1, 'projects', 9)
        self.assertEqual('busy', main._warmup_pi_admission(main._projects_account(1), None)['reason'])
        self.assertFalse(main.warmup_scheduler.trigger_account(1)['started'])
        self.pi.run.assert_not_called()
        self.owners.release(1, token)
        self.service.start(1)
        self.assertTrue(self.entered.wait(1))
        self.terminal.start.assert_not_called()
        self.assertIn('warmup Pi', main._oauth_owner_transition_blocker(main._projects_account(1)))
        with self.assertRaises(HTTPException) as error:
            main.delete_account(1)
        self.assertEqual(409, error.exception.status_code)

    def test_existing_entrypoints_use_pi_round_and_real_resume(self):
        """旧启动入口分派新轮，人工暂停后的旧恢复入口接续同一原轮。:return: None。"""
        self.configure()
        self.observe()
        result = main.run_account_warmup_now(1)
        self.assertTrue(result['started'])
        self.assertNotIn('run_id', result)
        original = result['round_id']
        self.assertTrue(self.entered.wait(1))
        self.service.pause(1)
        for _ in range(100):
            if 1 not in self.service.controllers:
                break
            time.sleep(.01)
        self.assertIsNone(self.owners.owner(1))
        with patch.object(main, '_read_bench_profile_identity', return_value={'accountUuid': 'synthetic'}):
            resumed = main.resume_account_warmup(1)
        self.assertEqual('pi', resumed['engine'])
        self.assertEqual(original, self.row()['id'])
        self.assertTrue(main._projects_account(1)['warmup_enabled'])
        connection = main.get_db()
        self.assertEqual(0, connection.execute('SELECT COUNT(*) FROM runs').fetchone()[0])
        connection.close()
        with patch.object(main, '_read_account_oauth_status', return_value={}):
            self.assertEqual('pi', main.list_accounts()[0]['warmup_engine'])


if __name__ == '__main__':
    unittest.main()
