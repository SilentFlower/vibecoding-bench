"""验证项目与工程养号的单目标指挥边界及正常收尾，不调用真实模型。"""
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import Mock

from project_requester_settings import ProjectRequesterSettings
import test_projects_engine_cycles as fixtures


class SingleObjectiveRoundTests(unittest.TestCase):
    """两空间复用真实 SQLite 和共享引擎，模型工具无法跨目标扩大本轮。"""

    setUp = fixtures.ProjectsEngineCycleTests.setUp
    database = fixtures.ProjectsEngineCycleTests.database
    create = fixtures.ProjectsEngineCycleTests.create
    agent = fixtures.ProjectsEngineCycleTests.agent
    complete = fixtures.ProjectsEngineCycleTests.complete

    def test_saved_compaction_threshold_reaches_both_spaces_without_mutating_prior_configuration(self):
        """页面私有配置进入两空间启动快照，后续保存不改变已交接的配置。:return: None。"""
        settings = ProjectRequesterSettings(self.root / 'settings/requester.json', {
            'PROJECT_REQUESTER_BASE_URL': 'https://synthetic.example/v1',
            'PROJECT_REQUESTER_API_KEY': 'synthetic-private-key', 'PROJECT_REQUESTER_MODEL': 'local-test'})
        captured = []
        for index, service in enumerate((self.primary, self.service)):
            settings.save('https://synthetic.example/v1', ['local-test'], compaction_threshold_tokens=410000 + index * 10000)
            service.provider = settings.agent_configuration

            def run(configuration, tools, event, stop, timeout_sec):
                """只记录本地启动快照，不请求任何模型。:return: timeout。"""
                captured.append(configuration)
                return 'timeout'

            service.pi.run = run
            service.start(1)
            self.finish(service)
        self.assertEqual([410000, 420000], [value['compaction_threshold_tokens'] for value in captured])

    def finish(self, service):
        """等待当前控制者退出，拒绝用尚在运行的状态断言完成。

        :param service: 当前空间的工程服务。
        :return: 最新公开账号状态。
        """
        controller = service.controllers.get(1)
        if controller:
            controller[0].join(5)
            self.assertFalse(controller[0].is_alive())
        self.assertNotIn(1, service.controllers)
        return service.view(1)['agents'][0]

    def test_success_blocks_second_objective_and_next_tick_uses_original_interval(self):
        """本轮通过后拒绝第二目标，下一次到期认领才可正常开始它。:return: None。"""
        for service in (self.primary, self.service):
            with self.subTest(namespace=service.namespace):
                calls = []
                service.configure_schedule(1, True, 7)

                def run(configuration, tools, event, stop, timeout_sec):
                    """模拟忽略指南仍尝试开启第二目标的旧 Pi。:return: 正常结束。"""
                    index = len(calls)
                    first = tools('claude_start', {'project_key': self.catalog.keys[0], 'objective_id': f'F-{index}'}, 'start')
                    accepted = tools('project_submit', {'summary': '交付本轮完整目标'}, 'submit')
                    second = tools('claude_start', {'project_key': self.catalog.keys[0], 'objective_id': f'F-{index + 1}'}, 'next')
                    calls.append((first, accepted, second, configuration['context_mode']))
                    return 'settled'

                service.pi.run = run
                started = time.time()
                service.start(1)
                first = self.finish(service)
                self.assertEqual('paused', first['status'])
                self.assertEqual('passed', first['work']['status'])
                self.assertEqual('scheduled', first['schedule']['state'])
                self.assertGreaterEqual(first['schedule']['next_run_at'], started + 420)
                self.assertIs(calls[0][1]['round_complete'], True)
                self.assertEqual('fresh', calls[0][3])
                self.assertEqual('rejected', calls[0][2]['status'])
                self.assertEqual(1, len(service.terminal.started))
                self.assertEqual(1, service._one('SELECT count(*) AS total FROM projects_work')['total'])
                due = first['schedule']['next_run_at']
                service.tick(due - 1)
                self.assertEqual(1, len(calls))
                service.tick(due + 1)
                following = self.finish(service)
                self.assertEqual(2, len(calls))
                self.assertEqual('fresh', calls[1][3])
                self.assertNotEqual(calls[0][0]['work_id'], calls[1][0]['work_id'])
                self.assertEqual('F-1', following['work']['objective_id'])
                self.assertEqual(2, following['progress']['completed'])
                self.assertIsNone(self.owners.owner(1))
                if service.auto_cycle:
                    self.assertEqual(1, following['cycle']['number'])
                    self.terminal.cleanup_cycle.assert_not_called()

    def test_failed_verification_keeps_same_work_until_real_success(self):
        """业务失败不结束目标，原会话可继续返工和提交。:return: None。"""
        for service in (self.primary, self.service):
            with self.subTest(namespace=service.namespace):
                service.verifier = Mock(side_effect=[{'status': 'failed'}, {'status': 'passed'}])
                results = []

                def run(configuration, tools, event, stop, timeout_sec):
                    """先失败再在同一工作重验通过。:return: 正常结束。"""
                    first = tools('claude_start', {'project_key': self.catalog.keys[0], 'objective_id': 'F-0'}, 'start')
                    failed = tools('project_submit', {'summary': '第一次交付'}, 'failed')
                    resumed = tools('claude_start', {'project_key': self.catalog.keys[0], 'objective_id': 'F-0'}, 'resume')
                    accepted = tools('project_submit', {'summary': '根据失败事实返工'}, 'accepted')
                    results.append((first, failed, resumed, accepted))
                    return 'settled'

                service.pi.run = run
                service.start(1)
                state = self.finish(service)
                first, failed, resumed, accepted = results[0]
                self.assertNotIn('round_complete', failed)
                self.assertEqual(first['work_id'], resumed['id'])
                self.assertEqual(first['session_id'], resumed['session_id'])
                self.assertIs(accepted['round_complete'], True)
                self.assertEqual(1, len(service.terminal.started))
                self.assertEqual(1, state['progress']['completed'])
                self.assertFalse(state['schedule']['enabled'])
                self.assertIsNone(state['schedule']['next_run_at'])

    def test_manual_pause_during_verification_wins_over_success(self):
        """人工暂停后迟到的通过结果不能结束为成功或重开计划。:return: None。"""
        for service in (self.primary, self.service):
            with self.subTest(namespace=service.namespace):
                entered, released = threading.Event(), threading.Event()
                results = []

                def verify(*args):
                    """保留真实验收竞争窗口。:return: 合成通过。"""
                    entered.set()
                    if not released.wait(5):
                        raise ValueError('测试没有释放验收')
                    return {'status': 'passed'}

                def run(configuration, tools, event, stop, timeout_sec):
                    """等待人工暂停后处理迟到结果。:return: 结束状态。"""
                    tools('claude_start', {'project_key': self.catalog.keys[0], 'objective_id': 'F-0'}, 'start')
                    results.append(tools('project_submit', {'summary': '等待验收'}, 'submit'))
                    return 'settled'

                service.verifier, service.pi.run = verify, run
                service.configure_schedule(1, True, 7)
                try:
                    service.start(1)
                    self.assertTrue(entered.wait(3))
                    service.pause(1)
                finally:
                    released.set()
                state = self.finish(service)
                self.assertNotIn('round_complete', results[0])
                self.assertEqual('paused', state['status'])
                self.assertFalse(state['schedule']['enabled'])
                self.assertIsNone(state['schedule']['next_run_at'])
                self.assertEqual(0, state['progress']['completed'])

    def test_timeout_resumes_original_goal_and_both_sessions_next_round(self):
        """首轮超时接续原目标，连续两轮后待复验，累计耗时和会话不清零。:return: None。"""
        for service in (self.primary, self.service):
            with self.subTest(namespace=service.namespace):
                calls = []

                def run(configuration, tools, event, stop, timeout_sec):
                    """保存原 Pi 会话并模拟真实目标片段超时。:return: timeout。"""
                    session = Path(configuration['session_dir']) / 'original.jsonl'
                    if not session.exists():
                        session.write_text('{}\n')
                    event({'type': 'ready', 'session_file': str(session)})
                    started = tools('claude_start', {'project_key': self.catalog.keys[0], 'objective_id': 'F-0'}, 'resume')
                    calls.append((configuration.get('session_file'), started, str(session), configuration['context_mode']))
                    return 'timeout'

                service.pi.run = run
                service.configure_schedule(1, True, 7)
                service.start(1)
                first = self.finish(service)
                work_id = calls[0][1]['work_id']
                service._write('UPDATE projects_work SET work_sec=1804.5 WHERE id=?', (work_id,))
                service.tick(first['schedule']['next_run_at'] + 1)
                resumed = self.finish(service)
                self.assertEqual(2, len(calls))
                self.assertEqual(['fresh', 'resume'], [call[3] for call in calls])
                self.assertEqual(calls[0][1]['work_id'], calls[1][1]['work_id'])
                self.assertEqual(calls[0][1]['session_id'], calls[1][1]['session_id'])
                self.assertEqual(calls[0][2], calls[1][0])
                self.assertGreaterEqual(resumed['work']['work_sec'], 1804.5)
                self.assertEqual('deferred', resumed['work']['status'])
                self.assertEqual(1, service._one('SELECT count(*) AS total FROM projects_work')['total'])

    def test_failed_terminal_release_never_emits_round_completion(self):
        """验收通过但原执行未能收口时，不能发出正常完成信号。:return: None。"""
        for service in (self.primary, self.service):
            with self.subTest(namespace=service.namespace):
                original = service.terminal.control
                results = []

                def control(work, operation):
                    """仅模拟执行收口失败。:param work: 原工作。:param operation: 动作。:return: 原结果。"""
                    if operation == 'stop':
                        raise ValueError('合成执行收口未确认')
                    return original(work, operation)

                def run(configuration, tools, event, stop, timeout_sec):
                    """接收收口失败后的真实工具拒绝。:return: 结束状态。"""
                    tools('claude_start', {'project_key': self.catalog.keys[0], 'objective_id': 'F-0'}, 'start')
                    results.append(tools('project_submit', {'summary': '尚未收口'}, 'submit'))
                    return 'settled'

                service.terminal.control, service.pi.run = control, run
                try:
                    service.start(1)
                    state = self.finish(service)
                    self.assertNotIn('round_complete', results[0])
                    self.assertEqual('blocked', state['status'])
                    self.assertEqual(0, state['progress']['completed'])
                    self.assertIsNone(state['schedule']['next_run_at'])
                finally:
                    service.terminal.control = original

    def test_same_generation_cannot_bypass_bound_target_by_clearing_current_pointer(self):
        """持久工作代次保护不依赖可变的当前目标指针。:return: None。"""
        for service in (self.primary, self.service):
            with self.subTest(namespace=service.namespace):
                service._write("UPDATE projects_agents SET generation=1,status='running' WHERE account_id=1")
                first = service.tool(1, 1, 'claude_start', {'project_key': self.catalog.keys[0], 'objective_id': 'F-0'}, 'first')
                work = service._one('SELECT * FROM projects_work WHERE id=?', (first['work_id'],))
                service._release(work, 'stopped')
                service._write('UPDATE projects_agents SET current_work_id=NULL WHERE account_id=1')
                second = service.tool(1, 1, 'claude_start', {'project_key': self.catalog.keys[1], 'objective_id': 'F-0'}, 'second')
                self.assertEqual('rejected', second['status'])
                self.assertEqual(1, len(service.terminal.started))
                self.assertEqual(1, service._one('SELECT count(*) AS total FROM projects_work')['total'])

    def test_warmup_new_engine_cycle_still_stops_after_its_first_goal(self):
        """全池通过后的新工程轮次仍遵守一次指挥只交付一个目标。:return: None。"""
        self.complete()
        results = []

        def run(configuration, tools, event, stop, timeout_sec):
            """只完成新工程轮次第一项，再探测第二项门禁。:return: 正常完成。"""
            tools('claude_start', {'project_key': self.catalog.keys[0], 'objective_id': 'F-0'}, 'first-new-cycle')
            accepted = tools('project_submit', {'summary': '新工程轮次首目标'}, 'submit')
            next_goal = tools('claude_start', {'project_key': self.catalog.keys[0], 'objective_id': 'F-1'}, 'second-new-cycle')
            results.append((accepted, next_goal))
            return 'settled'

        self.service.pi.run = run
        self.service.configure_schedule(1, True, 7)
        self.service.start(1)
        state = self.finish(self.service)
        self.assertEqual(2, state['cycle']['number'])
        self.assertEqual(1, state['cycle']['completed'])
        self.assertIs(results[0][0]['round_complete'], True)
        self.assertEqual('rejected', results[0][1]['status'])
        self.terminal.cleanup_cycle.assert_called_once_with({'id': 1, 'name': '1'}, 1)
        self.assertEqual(601, self.service._one('SELECT count(*) AS total FROM projects_submissions')['total'])

    def test_concurrent_first_selection_publishes_only_one_target(self):
        """两个并发选目标调用都读到空现场时，发布前校验仍只放行一个。:return: None。"""
        for service in (self.primary, self.service):
            with self.subTest(namespace=service.namespace):
                service._write("UPDATE projects_agents SET generation=1,status='running' WHERE account_id=1")
                original, barrier = service.terminal.settings, threading.Barrier(2)

                def settings(account):
                    """在目标发布前同步两个调用。:return: 原配置。"""
                    barrier.wait(3)
                    return original(account)

                service.terminal.settings = settings
                results, failures = [], []

                def start(index):
                    """请求一个不同的工程目标。:param index: 目标编号。:return: None。"""
                    try:
                        results.append(service.tool(1, 1, 'claude_start',
                            {'project_key': self.catalog.keys[0], 'objective_id': f'F-{index}'}, str(index)))
                    except Exception as error:
                        failures.append(error)

                workers = [threading.Thread(target=start, args=(index,)) for index in range(2)]
                for worker in workers:
                    worker.start()
                for worker in workers:
                    worker.join(5)
                    self.assertFalse(worker.is_alive())
                self.assertEqual([], failures)
                self.assertEqual(['rejected', 'running'], sorted(row['status'] for row in results))
                self.assertEqual(1, len(service.terminal.started))
                self.assertEqual(1, service._one('SELECT count(*) AS total FROM projects_work')['total'])
                service.terminal.settings = original


if __name__ == '__main__':
    unittest.main()
