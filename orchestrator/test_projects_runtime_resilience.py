"""验证补丁兼容、启动故障持久化及两空间的安全恢复。"""
import json
import threading
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from project_runtime_policy import ProjectRuntimeError, check_python_runtime, python_versions_match
from project_library import digest_json, write_document
from projects import ProjectsService
from projects_runtime import ProjectsTerminal
from project_verifier import _NativeRegressionControlError, _native_python_adapter
import test_projects_agent as fixtures


class RuntimeCompatibilityTests(unittest.TestCase):
    """核对版本策略及明确的期望／实际事实。"""

    def test_patch_release_compatible_but_minor_exact_and_invalid_versions_rejected(self):
        """补丁可变不能意外放开主次版本或非正常版本。:return: None。"""
        self.assertTrue(python_versions_match('3.12.15', '3.12.16'))
        self.assertTrue(python_versions_match('3.12', '3.12.16'))
        for expected, actual, policy in [('3.12.15', '3.13.0', 'minor'), ('3.12.15', '3.12.16', 'exact'),
                ('3.12.15', '3.12.16rc1', 'minor'), ('3.12.15', '', 'minor'),
                ('3.12.15', '3.120.0', 'minor'), ('3.12.15', '3.12.15', 'unknown')]:
            with self.subTest(expected=expected, actual=actual, policy=policy):
                self.assertFalse(python_versions_match(expected, actual, policy))
        with self.assertRaises(ProjectRuntimeError) as raised:
            check_python_runtime({'python': '3.12.15'}, '3.13.0')
        self.assertEqual('python_incompatible', raised.exception.code)
        self.assertEqual('3.13.0', raised.exception.details['actual_python'])

    def test_frozen_runner_versions_use_only_known_sources_and_keep_original_assets(self):
        """真实冻结控制器都只适配版本前置条件，来源变化必须拒绝。:return: None。"""
        root = Path(__file__).resolve().parents[1] / 'project_library/projects'
        count = 0
        for path in root.glob('*/verification/*regression*.py'):
            before = path.read_bytes()
            if b"contract['python'] != sys.version.split()[0]" not in before:
                continue
            with self.subTest(path=str(path)):
                actual, facts = _native_python_adapter(before)
                compile(actual, str(path), 'exec')
                self.assertTrue(facts['preserves_frozen_contract'])
                self.assertIn(b"not python_versions_match(contract['python']", actual)
                self.assertEqual(before, path.read_bytes())
                with self.assertRaises(_NativeRegressionControlError):
                    _native_python_adapter(before + b'\n')
            count += 1
        self.assertGreater(count, 90)


class StartupFailureTests(unittest.TestCase):
    """使用真实 SQLite 和真实控制轮验证错误不被正常结束覆盖。"""

    setUp = fixtures.ProjectsAgentTests.setUp
    database = fixtures.ProjectsAgentTests.database
    activate = fixtures.ProjectsAgentTests.activate
    tool = fixtures.ProjectsAgentTests.tool
    start_work = fixtures.ProjectsAgentTests.start_work

    def test_cached_dependencies_still_check_runtime_and_upgrade_old_proof(self):
        """命中缓存仍核实际解释器，旧证明可在兼容时补齐。:return: None。"""
        profile = {'python': '3.12.15', 'artifacts': [], 'requirements': []}
        checksum = digest_json(profile)
        base = self.root / 'cli/projects-python' / checksum
        (base / 'site-packages').mkdir(parents=True)
        marker = self.root / 'runtime/projects-python' / (checksum + '.json')
        write_document(marker, {'profile_digest': checksum})
        runtime = SimpleNamespace(_root=lambda _: self.root, data=self.root)
        terminal = ProjectsTerminal(runtime, None, None, None)
        project = SimpleNamespace(manifest={'environment': 'example'})
        library = SimpleNamespace(environments={'example': profile})
        network = Mock()
        network.exec_run.return_value = SimpleNamespace(exit_code=0, output=b'3.12.16\n')
        with patch('projects_runtime.role_container', return_value=network):
            terminal._prepare_python({}, project, library)
            self.assertEqual('3.12.16', json.loads(marker.read_text())['actual_python'])
            before = marker.read_bytes()
            network.exec_run.return_value = SimpleNamespace(exit_code=0, output=b'3.13.0\n')
            with self.assertRaises(ProjectRuntimeError):
                terminal._prepare_python({}, project, library)
            self.assertEqual(before, marker.read_bytes())
        self.assertEqual(2, network.exec_run.call_count)

    def failing_round(self, namespace='projects', retryable=False):
        """通过真实服务线程执行一个确定失败后正常结束的 Pi。

        :param namespace: 固定工程空间。
        :param retryable: 是否为暂时故障。
        :return: 控制端保存的工作。
        """
        if namespace == 'warmup':
            self.service.close()
            original = self.service
            self.service = ProjectsService(self.root, self.database, threading.Lock(), self.catalog, self.terminal,
                original.account, original.admission, original.provider, original.verifier, self.pi, namespace='warmup')
            self.addCleanup(self.service.close)
        self.service.configure(1, ['example'])
        self.service.configure_schedule(1, True, 30)
        self.terminal.start = Mock(side_effect=ProjectRuntimeError('python_probe_failed' if retryable else 'python_incompatible',
            'Python 版本不兼容：验证版本 3.12.15，实际版本 3.13.0', retryable=retryable,
            details={'expected_python': '3.12.15', 'actual_python': '3.13.0', 'private_path': '/private/token'}))

        def execute(configuration, tools, event, stop, timeout):
            """模拟 SDK 正常收尾，故障事实仍必须由服务掌握。:return: settled。"""
            self.result = tools('claude_start', {'project_key': 'example', 'objective_id': 'feature'}, 'start-one')
            return 'settled'

        self.pi.run = Mock(side_effect=execute)
        self.service.start(1)
        controller = self.service.controllers.get(1)
        if controller:
            controller[0].join(3)
        self.assertFalse(self.service.controllers)
        agent = self.service.state(1)['agents'][0]
        return agent['work']

    def test_settled_failure_remains_visible_and_blocks_model_spinning_in_both_spaces(self):
        """正常轮次结束和定时到期不能吞掉故障，两个空间一致。:return: None。"""
        for namespace in ('projects', 'warmup'):
            with self.subTest(namespace=namespace):
                work = self.failing_round(namespace)
                self.assertTrue(self.result['controller_yield'])
                self.assertIsNone(work['started_at'])
                self.assertEqual(0, work['work_sec'])
                self.assertEqual('blocked', work['status'])
                self.assertEqual(1, work['failure']['attempt_count'])
                self.assertNotIn('/private/token', json.dumps(work))
                agent = self.service.state(1)['agents'][0]
                self.assertIn('版本不兼容', agent['message'])
                self.assertIsNone(agent['schedule']['next_run_at'])
                self.service.tick(time.time() + 100000)
                self.assertEqual(1, self.pi.run.call_count)
                self.assertEqual(work['failure'], self.service.work_page(1)['items'][0]['failure'])
                self.assertEqual(work['failure'], self.service.work_detail(work['id'])['work']['failure'])

    def test_restart_and_manual_retry_preserve_count_until_actual_start_succeeds(self):
        """重启不清零，手动恢复旧代工作再次失败计数，真正成功才解除。:return: None。"""
        work = self.failing_round()
        self.service.recover()
        current = self.service.state(1)['agents'][0]
        self.assertEqual(work['failure'], current['work']['failure'])
        self.assertIn('版本不兼容', current['message'])
        self.service.start(1)
        controller = self.service.controllers.get(1)
        if controller:
            controller[0].join(3)
        current = self.service.state(1)['agents'][0]
        self.assertEqual(2, current['work']['failure']['attempt_count'])
        self.assertEqual(work['id'], current['work']['id'])
        original = self.terminal.start

        def successful(account, row):
            """返回同一个工作区的实际可观察终端。:return: 原执行定位。"""
            self.terminal.start = original
            from test_projects_agent import TerminalFixture
            return TerminalFixture.start(self.terminal, account, row)

        self.terminal.start = successful
        self.service.start(1)
        controller = self.service.controllers.get(1)
        if controller:
            controller[0].join(3)
        current = self.service.state(1)['agents'][0]['work']
        self.assertEqual(work['id'], current['id'])
        self.assertIsNotNone(current['started_at'])
        self.assertIsNotNone(current['failure']['resolved_at'])
        self.assertEqual(2, current['failure']['attempt_count'])

    def test_retryable_failure_waits_without_model_and_keeps_deadline_through_restart(self):
        """未到恢复时间不请求模型，重启保留原截止。:return: None。"""
        work = self.failing_round(retryable=True)
        agent = self.service.state(1)['agents'][0]
        self.assertEqual('waiting', agent['status'])
        self.assertGreater(agent['schedule']['next_run_at'], time.time())
        deadline = agent['schedule']['next_run_at']
        self.service._write('UPDATE projects_agents SET schedule_next_at=? WHERE account_id=1', (time.time() - 1,))
        self.service.tick(deadline - 1)
        self.assertEqual(1, self.pi.run.call_count)
        self.assertEqual(deadline, self.service.state(1)['agents'][0]['schedule']['next_run_at'])
        self.service.recover()
        agent = self.service.state(1)['agents'][0]
        self.assertEqual(deadline, agent['schedule']['next_run_at'])
        self.assertEqual(work['failure'], agent['work']['failure'])

    def test_restart_preserves_new_model_block_instead_of_promoting_old_startup_failure(self):
        """重启保留较新的模型阻断，原启动问题仍可独立查看。:return: None。"""
        work = self.failing_round(retryable=True)
        self.service.pi = fixtures.ErrorPiFixture([{'type': 'error', 'reason': 'provider_content_filter', 'message': '本次模型过滤'}])
        self.service.start(1)
        controller = self.service.controllers.get(1)
        if controller:
            controller[0].join(3)
        self.service.recover()
        agent = self.service.state(1)['agents'][0]
        self.assertEqual('blocked', agent['status'])
        self.assertIn('内容过滤', agent['message'])
        self.assertEqual(work['failure'], agent['work']['failure'])

    def test_cancelled_generation_cannot_record_late_failure_or_rearm_schedule(self):
        """取消比准备结果优先，原线程不能复活计划。:return: None。"""
        generation = self.activate()

        def cancelled(account, work):
            """在真实启动边界插入用户暂停。:return: 不返回。"""
            self.service.pause(1)
            raise ProjectRuntimeError('python_probe_failed', '迟到故障', retryable=True)

        self.terminal.start = cancelled
        result = self.start_work()
        self.assertEqual('rejected', result['status'])
        agent = self.service.state(1)['agents'][0]
        self.assertGreater(agent['generation'], generation)
        self.assertIsNone(agent['work']['failure'])
        self.assertFalse(agent['schedule']['enabled'])

    def test_failure_after_terminal_creation_is_visible_and_does_not_leak_private_exception(self):
        """进程创建后基线失败同样留证，原执行收口且错误不泄露路径。:return: None。"""
        self.activate()
        with patch('projects.snapshot_tree', side_effect=OSError('/private/secret')):
            result = self.start_work()
        self.assertTrue(result['controller_yield'])
        self.assertEqual('startup_unknown', result['failure']['code'])
        self.assertEqual('starting', result['failure']['phase'])
        work = self.service.state(1)['agents'][0]['work']
        self.assertIn((work['id'], 'stop'), self.terminal.controls)
        self.assertNotIn('/private/secret', json.dumps(work))

    def test_enabling_schedule_during_failed_preparation_always_saves_a_retry_deadline(self):
        """失败发生时计划关闭，收尾时开启也不能丢失下次时间。:return: None。"""
        generation = self.activate()
        self.terminal.start = Mock(side_effect=ProjectRuntimeError('python_probe_failed', '版本暂不可读取', retryable=True))
        result = self.start_work()
        self.assertIsNone(result['failure']['retry_at'])
        self.service.configure_schedule(1, True, 30)
        agent = self.service._one('SELECT * FROM projects_agents WHERE account_id=1')
        work = self.service._one('SELECT * FROM projects_work WHERE id=?', (agent['current_work_id'],))
        self.assertTrue(self.service._finish_start_failure(agent, work, generation))
        value = self.service.state(1)['agents'][0]
        self.assertGreater(value['schedule']['next_run_at'], time.time())
        self.assertEqual(value['schedule']['next_run_at'], value['work']['failure']['retry_at'])

    def test_new_model_failure_cannot_be_hidden_by_old_retryable_startup_failure(self):
        """旧环境故障仍留档，新的模型过滤必须阻断并显示本次原因。:return: None。"""
        work = self.failing_round(retryable=True)
        self.service.pi = fixtures.ErrorPiFixture([{'type': 'error', 'reason': 'provider_content_filter', 'message': '本次模型过滤'}])
        self.service.start(1)
        controller = self.service.controllers.get(1)
        if controller:
            controller[0].join(3)
        agent = self.service.state(1)['agents'][0]
        self.assertEqual('blocked', agent['status'])
        self.assertIn('内容过滤', agent['message'])
        self.assertIsNone(agent['schedule']['next_run_at'])
        self.assertEqual(work['failure'], agent['work']['failure'])


if __name__ == '__main__':
    unittest.main()
