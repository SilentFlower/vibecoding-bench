"""验证真实 SQLite 上的计划认领、门禁暂停、预算和重启恢复，不调用真实模型。"""
import threading
import time
import unittest
from unittest.mock import Mock

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

    def test_exhausted_work_budget_and_changed_identity_do_not_start_models(self):
        """定时不重置累计预算，也不将计划转交新绑定账号。:return: None。"""
        self.activate()
        original = self.start_work()
        self.service.pause(1)
        self.service._write('UPDATE projects_work SET work_sec=3600 WHERE id=?', (original['work_id'],))
        self.service.configure_schedule(1, True, 1)
        self.service.tick()
        agent = self.service.state(1)['agents'][0]
        self.assertEqual('blocked', agent['schedule']['state'])
        self.assertIn('累计预算', agent['schedule']['message'])
        self.assertFalse(self.pi.entered.is_set())
        self.service.configure(2, ['other'])
        self.service.configure_schedule(2, True, 1)
        self.service.account = lambda aid: {'id': aid, 'name': str(aid), 'cc2api_account_id': 99}
        self.service.tick()
        self.assertEqual('blocked', self.service.state(2)['agents'][0]['schedule']['state'])
        self.assertFalse(self.pi.entered.is_set())

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


if __name__ == '__main__':
    unittest.main()
