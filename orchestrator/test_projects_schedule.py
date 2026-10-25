"""验证真实 SQLite 上的计划认领、门禁暂停、预算和重启恢复，不调用真实模型。"""
import threading
import time
import unittest
from unittest.mock import Mock, patch

from projects import ProjectsService
import test_projects_agent as fixtures


class ProjectsScheduleTests(unittest.TestCase):
    """检查人工控制优先、自动计划持久化和额度等待的执行事实。"""

    setUp = fixtures.ProjectsAgentTests.setUp
    database = fixtures.ProjectsAgentTests.database
    activate = fixtures.ProjectsAgentTests.activate
    tool = fixtures.ProjectsAgentTests.tool
    start_work = fixtures.ProjectsAgentTests.start_work

    def test_default_off_and_concurrent_due_ticks_only_start_one_controller(self):
        """并发到点扫描只能认领同账号一次，未开启计划不会自动执行。:return: None。"""
        self.service.configure(1, ['example'])
        self.assertFalse(self.service.state(1)['agents'][0]['schedule']['enabled'])
        self.service.tick()
        self.assertFalse(self.pi.entered.is_set())
        self.service.configure_schedule(1, True, 60)
        threads = [threading.Thread(target=self.service.tick) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(2)
        self.assertTrue(self.pi.entered.wait(1))
        self.assertEqual(1, self.service.state(1)['agents'][0]['generation'])
        self.assertEqual(1, len(self.service.controllers))

    def test_quota_wait_does_not_call_model_and_rechecks_at_actual_reset(self):
        """额度未恢复只扫描本地状态，不启动Pi或消耗模型调用。:return: None。"""
        self.service.configure(1, ['example'])
        provider = Mock(wraps=self.service.provider)
        self.service.provider = provider
        now = time.time()
        self.service.admission = lambda *_: {'allowed': False, 'retryable': True,
            'reason': 'quota', 'retry_at': now + 300, 'message': '额度等待'}
        self.service.configure_schedule(1, True, 1)
        self.service.tick(now + 1)
        agent = self.service.state(1)['agents'][0]
        self.assertEqual('waiting', agent['schedule']['state'])
        self.assertEqual(now + 300, agent['schedule']['next_run_at'])
        self.assertFalse(self.pi.entered.is_set())
        provider.assert_not_called()
        self.service.admission = lambda *_: {'allowed': True}
        self.service.tick(now + 299)
        provider.assert_not_called()
        self.service.tick(now + 301)
        self.assertTrue(self.pi.entered.wait(1))
        provider.assert_called_once()

    def test_manual_pause_disables_due_plan_and_late_controller_cannot_rearm(self):
        """人工暂停同时撤销计划，迟到收尾不能重新排程。:return: None。"""
        self.service.configure(1, ['example'])
        self.service.configure_schedule(1, True, 1)
        self.service.tick()
        self.assertTrue(self.pi.entered.wait(1))
        controller = self.service.controllers[1][0]
        paused = self.service.pause(1)['agents'][0]
        controller.join(2)
        self.service.tick(time.time() + 10000)
        agent = self.service.state(1)['agents'][0]
        self.assertFalse(agent['schedule']['enabled'])
        self.assertIsNone(agent['schedule']['next_run_at'])
        self.assertEqual(paused['generation'], agent['generation'])
        self.assertFalse(agent['controller_active'])

    def test_disabling_schedule_keeps_current_controller_and_generation(self):
        """关闭未来自动运行不等于中断当前轮。:return: None。"""
        self.service.configure(1, ['example'])
        self.service.start(1)
        self.assertTrue(self.pi.entered.wait(1))
        controller = self.service.controllers[1]
        generation = self.service.state(1)['agents'][0]['generation']
        self.service.configure_schedule(1, True, 15)
        self.service.configure_schedule(1, False, 15)
        self.assertIs(controller, self.service.controllers[1])
        self.assertFalse(controller[1].is_set())
        self.assertEqual(generation, self.service.state(1)['agents'][0]['generation'])

    def test_reenabling_while_old_controller_is_stopping_keeps_a_due_plan(self):
        """已取消但尚在收尾的旧线程不能让重新开启的计划永久失去下次时间。:return: None。"""
        self.service.configure(1, ['example'])
        stopped = threading.Event()
        stopped.set()
        self.service.controllers[1] = (threading.Thread(), stopped)
        agent = self.service.configure_schedule(1, True, 5)['agents'][0]
        self.assertEqual('scheduled', agent['schedule']['state'])
        self.assertIsNotNone(agent['schedule']['next_run_at'])
        self.service.controllers.pop(1)
        self.service.tick()
        self.assertTrue(self.pi.entered.wait(1))

    def test_view_exposes_actual_progress_and_only_public_quota_fields(self):
        """页面得到真实进度与门禁原因，内部身份和原始来源始终不进入公开视图。:return: None。"""
        self.activate(keys=['example', 'other'])
        result = self.start_work()
        self.service._write('UPDATE projects_work SET segment_started_at=? WHERE id=?',
            (time.time() - 12, result['work_id']))
        self.service.admission = lambda *_: {'allowed': False, 'reason': 'quota', 'retryable': True,
            'retry_at': time.time() + 300, 'message': '达到阈值', 'identity': 'PRIVATE_IDENTITY',
            'quota': {'known': True, 'identity': 'PRIVATE_IDENTITY', 'source': 'cli', 'limits': {'five_hour': 30},
                'windows': {'five_hour': {'utilization': 31, 'identity': 'PRIVATE_IDENTITY', 'reset_at': time.time() + 300}}, 'hit': ['five_hour']},
            'window': {'allowed': True, 'timezone': 'Asia/Shanghai', 'secret': 'PRIVATE_IDENTITY'}}
        agent = self.service.view(1)['agents'][0]
        self.assertNotIn('PRIVATE_IDENTITY', str(agent))
        self.assertEqual({'completed': 0, 'remaining': 2, 'total': 2},
            {key: agent['progress'][key] for key in ('completed', 'remaining', 'total')})
        self.assertGreaterEqual(agent['progress']['elapsed_work_sec'], 12)
        self.assertEqual(31, agent['admission']['quota']['windows']['five_hour']['utilization'])
        self.assertEqual(30, agent['admission']['quota']['limits']['five_hour'])
        self.assertEqual('quota', agent['admission']['reason'])

    def test_gate_watcher_stops_manual_run_even_when_schedule_disabled(self):
        """在途门禁监控独立于定时开关，守住未调用新工具期间的Claude执行。:return: None。"""
        self.service.configure(1, ['example'])
        self.service.start(1)
        self.assertTrue(self.pi.entered.wait(1))
        original = self.start_work()
        self.allowed = False
        self.service.tick()
        agent = self.service.state(1)['agents'][0]
        work = self.service._one('SELECT * FROM projects_work WHERE id=?', (original['work_id'],))
        self.assertEqual('waiting', work['status'])
        self.assertIsNone(work['runtime_json'])
        self.assertIn((work['id'], 'stop'), self.terminal.controls)
        self.assertFalse(agent['schedule']['enabled'])
        self.assertEqual('paused', agent['status'])

    def test_finished_round_schedules_after_interval_and_survives_service_restart(self):
        """下一轮时间写入数据库，重建服务后按原到期点启动。:return: None。"""
        self.service.configure(1, ['example'])
        self.service.configure_schedule(1, True, 7)
        self.pi.run = Mock(return_value='settled')
        started = time.time()
        self.service.tick()
        controller = self.service.controllers.get(1)
        if controller:
            controller[0].join(2)
        planned = self.service.state(1)['agents'][0]['schedule']['next_run_at']
        self.assertGreaterEqual(planned, started + 420)
        self.service.close()
        pi = fixtures.PiFixture()
        original = self.service
        self.service = ProjectsService(self.root, self.database, threading.Lock(), self.catalog, self.terminal,
            original.account, original.admission, original.provider, original.verifier, pi)
        self.addCleanup(self.service.close)
        self.service.recover()
        self.assertEqual(planned, self.service.state(1)['agents'][0]['schedule']['next_run_at'])
        self.service.tick(planned - 1)
        self.assertFalse(pi.entered.is_set())
        self.service.tick(planned + 1)
        self.assertTrue(pi.entered.wait(1))

    def test_cumulative_time_beyond_one_turn_resumes_original_sessions(self):
        """累计超过三十分钟仍按轮接续原工作和两个会话，不需要清零累计值。:return: None。"""
        self.activate()
        self.service.configure(1, ['example'], budget_sec=1800)
        original = self.start_work()
        session_file = self.root / 'projects/agents/1/original.jsonl'
        session_file.parent.mkdir(parents=True)
        session_file.write_text('{}\n')
        self.service._pi_event(1, 1, {'type': 'ready', 'session_file': str(session_file)})
        self.service.pause(1)
        self.service._write('UPDATE projects_work SET work_sec=1804.6653017997742 WHERE id=?', (original['work_id'],))
        calls = []

        def run(configuration, tools, event, stop, timeout_sec):
            """恢复同一个目标并模拟本轮到时。:param configuration: 配置。:param tools: 工具。:param event: 事件。:param stop: 取消。:param timeout_sec: 单轮剩余秒数。:return: timeout。"""
            calls.append((configuration, timeout_sec, tools('claude_start',
                {'project_key': 'example', 'objective_id': 'feature'}, 'continue')))
            return 'timeout'

        self.pi.run = run
        self.service.configure_schedule(1, True, 1)
        self.service.tick()
        self.join_controller()
        agent = self.service.state(1)['agents'][0]
        self.assertEqual(('paused', 'scheduled'), (agent['status'], agent['schedule']['state']))
        self.assertIn('累计耗时保留', agent['schedule']['message'])
        self.assertEqual(original['work_id'], calls[0][2]['work_id'])
        self.assertEqual(original['session_id'], calls[0][2]['session_id'])
        self.assertEqual(str(session_file), calls[0][0]['session_file'])
        self.assertGreaterEqual(agent['work']['work_sec'], 1804.6653017997742)
        self.assertGreaterEqual(calls[0][1], 1798)
        self.assertGreaterEqual(self.terminal.started[-1][1]['remaining_sec'], 1798)
        self.assertEqual({'turn_active': False, 'turn_elapsed_sec': 0, 'turn_budget_sec': 1800, 'remaining_work_sec': 1800},
            {key: self.service.view(1)['agents'][0]['progress'][key]
                for key in ('turn_active', 'turn_elapsed_sec', 'turn_budget_sec', 'remaining_work_sec')})
        self.service.tick(agent['schedule']['next_run_at'] + 1)
        self.join_controller()
        self.assertEqual(2, len(calls))
        self.assertGreaterEqual(calls[1][1], 1798)
        self.assertEqual(original['session_id'], calls[1][2]['session_id'])

    def test_changed_identity_still_prevents_scheduled_models(self):
        """分轮续跑不能将计划转交到新的账号绑定。:return: None。"""
        self.service.configure(2, ['other'])
        self.service.configure_schedule(2, True, 1)
        self.service.account = lambda aid: {'id': aid, 'name': str(aid), 'cc2api_account_id': 99}
        self.service.tick()
        self.assertEqual('blocked', self.service.state(2)['agents'][0]['schedule']['state'])
        self.assertFalse(self.pi.entered.is_set())

    join_controller = fixtures.ProjectsAgentTests.join_controller

    def test_completed_objective_ends_round_and_next_turn_gets_full_time(self):
        """完成首目标后拒绝本轮第二项，下一轮启动新目标时获得完整时限。:return: None。"""
        self.service.configure(1, ['example', 'other'], budget_sec=1800)
        clock = [1000.0]
        snapshots = []
        opened = []
        self.verification = {'status': 'passed', 'feedback': []}

        def run(configuration, tools, event, stop, timeout_sec):
            """在两个指挥轮次使用可控时钟。:param configuration: 配置。:param tools: 工具。:param event: 事件。:param stop: 取消。:param timeout_sec: 单轮剩余。:return: 正常完成或超时。"""
            if not snapshots:
                opened.append(tools('claude_start', {'project_key': 'example', 'objective_id': 'feature'}, 'first'))
                self.assertIs(tools('project_submit', {'summary': '首目标已独立通过'}, 'submit')['round_complete'], True)
                clock[0] += 1200
            result = tools('claude_start', {'project_key': 'other', 'objective_id': 'feature'}, 'next')
            if result['status'] == 'running':
                opened.append(result)
            snapshots.append((result, self.service.view(1)['agents'][0]['progress'], timeout_sec))
            return 'settled' if len(snapshots) == 1 else 'timeout'

        self.pi.run = run
        with patch('projects.time.monotonic', side_effect=lambda: clock[0]):
            self.service.start(1)
            self.join_controller()
            self.assertEqual('rejected', snapshots[0][0]['status'])
            self.assertEqual(1, len(self.terminal.started))
            self.assertEqual((True, 1200, 600), tuple(snapshots[0][1][key]
                for key in ('turn_active', 'turn_elapsed_sec', 'remaining_work_sec')))
            self.assertFalse(self.service.state(1)['agents'][0]['schedule']['enabled'])
            self.service.tick(time.time() + 86400)
            self.assertEqual(1, len(snapshots))
            clock[0] += 60
            self.service.start(1)
            self.join_controller()
        self.assertEqual(1800, snapshots[1][2])
        self.assertEqual(1800, self.terminal.started[-1][1]['remaining_sec'])
        self.assertNotEqual(opened[0]['work_id'], opened[1]['work_id'])

    def prepare_legacy_budget_block(self):
        """构造旧版本累计时限导致的精确阻塞，不调用真实模型。:return: 原工作。"""
        self.activate()
        self.service.configure(1, ['example'], budget_sec=1800)
        result = self.start_work()
        self.service.pause(1)
        self.service.configure_schedule(1, True, 2)
        self.service._write('UPDATE projects_work SET work_sec=1804.6653017997742 WHERE id=?', (result['work_id'],))
        self.service._write("UPDATE projects_agents SET schedule_state='blocked',schedule_next_at=NULL,schedule_message=? WHERE account_id=1",
            ('原任务累计预算已用尽，请调整预算或停止目标；定时运行不会重置预算',))
        return self.service._one('SELECT * FROM projects_work WHERE id=?', (result['work_id'],))

    def test_legacy_budget_block_requeues_once_at_original_interval(self):
        """仅精确旧故障在核对后重排原计划，审计不重复且现场不变。:return: None。"""
        original = self.prepare_legacy_budget_block()
        now = time.time()
        self.service.tick(now)
        agent = self.service.state(1)['agents'][0]
        self.assertEqual(('paused', 'scheduled', now + 120),
            (agent['status'], agent['schedule']['state'], agent['schedule']['next_run_at']))
        self.assertEqual(original, self.service._one('SELECT * FROM projects_work WHERE id=?', (original['id'],)))
        self.service.tick(now + 1)
        self.assertEqual(1, len([item for item in self.service.events(1) if item['kind'] == 'budget_policy']))
        self.assertFalse(self.pi.entered.is_set())

    def test_service_recovery_also_migrates_legacy_budget_block(self):
        """部署重启能修复旧预算阻塞，并保留原目标、Claude 会话和累计耗时。:return: None。"""
        original = self.prepare_legacy_budget_block()
        self.service.recover()
        agent = self.service.state(1)['agents'][0]
        self.assertEqual('scheduled', agent['schedule']['state'])
        self.assertIsNotNone(agent['schedule']['next_run_at'])
        self.assertEqual((original['id'], original['session_id'], original['work_sec']),
            tuple(agent['work'][key] for key in ('id', 'session_id', 'work_sec')))
        self.assertFalse(self.pi.entered.is_set())

    def test_legacy_budget_migration_preserves_all_other_holds(self):
        """旧预算迁移不解除关闭计划、人工阻塞、身份变化、未知输入或认证错误。:return: None。"""
        original = self.prepare_legacy_budget_block()
        saved_agent = self.service._one('SELECT * FROM projects_agents WHERE account_id=1')
        account, admission = self.service.account, self.service.admission
        for condition in ('disabled', 'other_reason', 'manual', 'identity', 'unknown', 'authentication', 'quota'):
            with self.subTest(condition=condition):
                if condition == 'disabled':
                    self.service._write('UPDATE projects_agents SET schedule_enabled=0 WHERE account_id=1')
                elif condition == 'other_reason':
                    self.service._write("UPDATE projects_agents SET schedule_message='执行收口未确认' WHERE account_id=1")
                elif condition == 'manual':
                    self.service._write("UPDATE projects_work SET status='blocked' WHERE id=?", (original['id'],))
                elif condition == 'identity':
                    self.service.account = lambda aid: {'id': aid, 'cc2api_account_id': 99}
                elif condition == 'unknown':
                    self.service._write("INSERT INTO projects_actions(id,work_id,generation,request_json,status,created_at) VALUES(?,?,?,?,?,?)",
                        ('uncertain', original['id'], original['generation'], '{}', 'unknown', time.time()))
                else:
                    self.service.admission = lambda *_: {'allowed': False, 'retryable': condition == 'quota',
                        'reason': condition, 'retry_at': time.time() + 600, 'message': condition}
                self.service.tick()
                agent = self.service.state(1)['agents'][0]
                self.assertEqual('waiting' if condition == 'quota' else 'blocked', agent['schedule']['state'])
                self.assertEqual(original['session_id'], agent['work']['session_id'])
                self.assertFalse(self.pi.entered.is_set())
                self.service.account, self.service.admission = account, admission
                self.service._write('DELETE FROM projects_actions WHERE id=?', ('uncertain',))
                self.service._write("UPDATE projects_work SET status='paused' WHERE id=?", (original['id'],))
                self.service._write('UPDATE projects_agents SET status=?,schedule_enabled=1,schedule_state=?,schedule_message=?,schedule_next_at=NULL WHERE account_id=1',
                    (saved_agent['status'], saved_agent['schedule_state'], saved_agent['schedule_message']))

    def test_all_objectives_completed_is_idle_until_pool_is_updated(self):
        """已完成项目池不会反复唤醒模型，用户扩充项目池后才重新排程。:return: None。"""
        self.activate()
        self.start_work()
        self.verification = {'status': 'passed', 'feedback': []}
        self.tool('project_submit', {'summary': '原池已完成'})
        self.service.configure_schedule(1, True, 1)
        self.service.tick()
        agent = self.service.state(1)['agents'][0]
        self.assertEqual('completed', agent['schedule']['state'])
        self.assertIsNone(agent['schedule']['next_run_at'])
        self.assertFalse(self.pi.entered.is_set())
        self.service.configure(1, ['example', 'other'])
        self.service.tick()
        self.assertTrue(self.pi.entered.wait(1))

    def test_completed_enabled_plan_rechecks_new_content_after_service_recovery(self):
        """内容扩充后，已开启且因目标完成休眠的计划能识别新目标。:return: None。"""
        self.activate()
        self.start_work()
        self.verification = {'status': 'passed', 'feedback': []}
        self.tool('project_submit', {'summary': '原版本全部完成'})
        self.service._write("UPDATE projects_agents SET status='paused' WHERE account_id=1")
        self.service.configure_schedule(1, True, 1)
        self.service.tick()
        self.assertEqual('completed', self.service.state(1)['agents'][0]['schedule']['state'])
        old = self.catalog.project

        def expanded(key, detail=True):
            """模拟新增公开工程目标。:param key: 项目。:param detail: 是否详细。:return: 新目标目录。"""
            value = old(key, detail)
            value['objectives'].append({'id': 'later-feature', 'goal': '新版本目标'})
            return value

        self.catalog.project = expanded
        self.service.recover()
        self.assertEqual('scheduled', self.service.state(1)['agents'][0]['schedule']['state'])
        self.service.tick()
        self.assertTrue(self.pi.entered.wait(1))


if __name__ == '__main__':
    unittest.main()
