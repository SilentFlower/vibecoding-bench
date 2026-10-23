"""以真实 SQLite 和确定性交接验证自动计划的收尾、等待与迟到验收边界。"""
import threading
import time
import unittest
from unittest.mock import patch

import test_projects_agent as fixtures


class ProjectsScheduleEdgeTests(unittest.TestCase):
    """不调用真实模型，通过同步信号覆盖计划与控制代次交接。"""

    setUp = fixtures.ProjectsAgentTests.setUp
    database = fixtures.ProjectsAgentTests.database
    tool = fixtures.ProjectsAgentTests.tool
    start_work = fixtures.ProjectsAgentTests.start_work

    def test_tool_gate_keeps_actual_reset_after_pi_immediately_settles(self):
        """工具发现门禁后即撤销控制代次，Pi 随即结束也不能改写可信恢复时间。

        :return: None。
        """
        proceed = threading.Event()
        self.addCleanup(proceed.set)
        responses = []

        def run(configuration, tools, event, stop, timeout_sec):
            self.pi.entered.set()
            if not proceed.wait(2):
                return 'stopped'
            responses.append(tools('claude_observe', {}, 'gate-observation'))
            return 'settled'

        self.pi.run = run
        self.service.configure(1, ['example'])
        self.service.configure_schedule(1, True, 60)
        self.service.start(1)
        self.assertTrue(self.pi.entered.wait(1))
        controller = self.service.controllers[1][0]
        work = self.start_work()
        reset = time.time() + 120
        self.service.admission = lambda *_: {'allowed': False, 'reason': 'quota',
            'retryable': True, 'retry_at': reset, 'message': '等待真实额度重置'}
        proceed.set()
        controller.join(2)
        self.assertFalse(controller.is_alive())
        agent = self.service.state(1)['agents'][0]
        current = self.service._one('SELECT * FROM projects_work WHERE id=?', (work['work_id'],))
        self.assertEqual('waiting', responses[0]['status'])
        self.assertEqual('waiting', agent['schedule']['state'])
        self.assertEqual(reset, agent['schedule']['next_run_at'])
        self.assertEqual('waiting', current['status'])
        self.assertIsNone(current['runtime_json'])
        self.assertFalse(agent['controller_active'])

    def test_old_tick_exception_cannot_block_a_newly_saved_plan(self):
        """旧扫描在抛错前交接给新配置，错误收口必须保留新配置的待检查时间。

        :return: None。
        """
        self.service.configure(1, ['example'])
        self.service.configure_schedule(1, True, 60)
        original = self.service.provider
        now = time.time()

        def failing_provider():
            # 同步回调精确重现“用户已保存新计划，旧检查稍后才收口”的先后关系。
            with patch('projects.time.time', return_value=now + 7):
                self.service.configure_schedule(1, True, 23)
            raise ValueError('旧模型配置检查失败')

        self.service.provider = failing_provider
        self.service.tick(now + 1)
        agent = self.service.state(1)['agents'][0]
        self.assertEqual('scheduled', agent['schedule']['state'])
        self.assertEqual(23, agent['schedule']['interval_minutes'])
        self.assertEqual(now + 7, agent['schedule']['next_run_at'])
        self.assertFalse(self.pi.entered.is_set())
        self.service.provider = original
        self.service.tick(now + 8)
        self.assertTrue(self.pi.entered.wait(1))

    def test_quota_during_verification_rejects_late_result_without_resume(self):
        """独立验收期间额度门禁先暂停执行，迟到失败不能恢复终端或接受旧代次交付。

        :return: None。
        """
        entered, release = threading.Event(), threading.Event()
        replies = []

        def verify(*arguments):
            entered.set()
            if not release.wait(2):
                raise ValueError('合成验收未及时结束')
            return {'status': 'failed', 'feedback': ['迟到的合成返工意见']}

        self.service.verifier = verify
        self.service.configure(1, ['example'])
        self.service.configure_schedule(1, True, 60)
        self.service.start(1)
        self.assertTrue(self.pi.entered.wait(1))
        controller = self.service.controllers[1][0]
        work = self.start_work()
        worker = threading.Thread(target=lambda: replies.append(
            self.tool('project_submit', {'summary': '核对验收时的额度暂停'})))

        def finish_verification():
            release.set()
            worker.join(2)

        self.addCleanup(finish_verification)
        worker.start()
        self.assertTrue(entered.wait(1))
        self.assertEqual('verifying', self.service._one('SELECT status FROM projects_work WHERE id=?', (work['work_id'],))['status'])
        reset = time.time() + 120
        self.service.admission = lambda *_: {'allowed': False, 'retryable': True,
            'reason': 'quota', 'retry_at': reset, 'message': '验收期间额度已耗尽'}
        self.service.tick()
        controller.join(2)
        release.set()
        worker.join(2)
        self.assertFalse(worker.is_alive())
        self.assertNotIn((work['work_id'], 'resume'), self.terminal.controls)
        self.assertIn((work['work_id'], 'stop'), self.terminal.controls)
        current = self.service._one('SELECT * FROM projects_work WHERE id=?', (work['work_id'],))
        self.assertEqual('waiting', current['status'])
        self.assertIsNone(current['runtime_json'])
        self.assertEqual('cancelled', self.service._one('SELECT status FROM projects_submissions WHERE work_id=?', (work['work_id'],))['status'])
        self.assertEqual('rejected', replies[0]['status'])
        self.assertEqual(reset, self.service.state(1)['agents'][0]['schedule']['next_run_at'])

    def test_finalization_gate_error_releases_controller_registration(self):
        """收尾门禁读取失败仍须回收控制者登记，避免死线程永久阻止后续人工启动。

        :return: None。
        """
        finish = threading.Event()
        self.addCleanup(finish.set)
        errors = []

        def run(configuration, tools, event, stop, timeout_sec):
            self.pi.entered.set()
            finish.wait(2)
            return 'settled'

        def gate(*arguments):
            if finish.is_set():
                raise ValueError('合成门禁读取失败')
            return {'allowed': True}

        self.pi.run, self.service.admission = run, gate
        self.service.configure(1, ['example'])
        self.service.configure_schedule(1, True, 60)
        with patch.object(threading, 'excepthook', lambda value: errors.append(value.exc_type.__name__)):
            self.service.start(1)
            self.assertTrue(self.pi.entered.wait(1))
            controller = self.service.controllers[1][0]
            finish.set()
            controller.join(2)
        self.assertFalse(controller.is_alive())
        self.assertNotIn(1, self.service.controllers)
        self.assertNotIn(1, self.service.controller_identities)
        self.assertFalse(errors)
        agent = self.service.state(1)['agents'][0]
        self.assertEqual('blocked', agent['schedule']['state'])
        self.assertIsNone(agent['schedule']['next_run_at'])

    def test_passive_evidence_error_does_not_hide_closed_window(self):
        """原生补证文件损坏不能让已关闭的运行窗口失去持续门禁。

        :return: None。
        """
        self.service.configure(1, ['example'])
        self.service.start(1)
        self.assertTrue(self.pi.entered.wait(1))
        controller = self.service.controllers[1]
        work = self.start_work()
        generation = self.service.state(1)['agents'][0]['generation']

        def broken_evidence(current):
            raise ValueError('合成原生额度游标损坏')

        self.terminal.passive_status = broken_evidence
        self.service.admission = lambda *_: {'allowed': False, 'retryable': True,
            'reason': 'window', 'retry_at': time.time() + 120, 'message': '运行窗口已关闭'}
        self.service.tick()
        self.assertTrue(controller[1].is_set())
        controller[0].join(2)
        current = self.service._one('SELECT * FROM projects_work WHERE id=?', (work['work_id'],))
        self.assertNotEqual('running', current['status'])
        self.assertIsNone(current['runtime_json'])
        self.assertGreater(self.service.state(1)['agents'][0]['generation'], generation)
        self.assertIn((work['work_id'], 'stop'), self.terminal.controls)


if __name__ == '__main__':
    unittest.main()
