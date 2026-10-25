"""验证验收自动收敛、双空间持久冷却和原会话恢复。"""
import json
import threading
import time
from unittest.mock import Mock

from projects import ProjectsService
from test_projects_agent import ProjectsAgentTests


class VerificationRecoveryTests(ProjectsAgentTests):
    """在真实 SQLite 和工程工具上验证重复反馈不能无限消耗原会话。"""

    def submit(self, generation=1):
        """提交当前真实候选。:param generation: 控制代次。:return: 工具结果。"""
        return self.tool('project_submit', {'summary': '验证当前实现'}, generation=generation)

    def test_changed_candidates_have_three_attempts_then_defer_without_acceptance(self):
        """不同候选也有总返工上限，暂存保留原会话且不能当作通过。:return: None。"""
        self.activate()
        self.start_work()
        work = self.service._one('SELECT * FROM projects_work')
        for attempt in range(3):
            (self.terminal.workspace(work) / 'library/app.py').write_text(f'VALUE = {attempt + 3}\n')
            result = self.submit()
            self.assertEqual('deferred' if attempt == 2 else 'failed', result['status'])
        self.assertTrue(result['round_complete'])
        saved = self.service._one('SELECT * FROM projects_work')
        self.assertEqual(work['session_id'], saved['session_id'])
        self.assertEqual(work['id'], saved['id'])
        self.assertIsNone(saved['runtime_json'])
        state = self.service.state(1)['agents'][0]
        self.assertEqual([], state['passed'])
        self.assertEqual([], state['available_objectives'])
        self.assertEqual(1, len(state['deferred_objectives']))
        self.assertEqual('verification_wait', self.service._eligibility(self.service._one('SELECT * FROM projects_agents'), saved)[0])

    def test_same_candidate_repeats_are_bounded_and_another_project_can_run(self):
        """同一冻结候选第二次失败后让出活动槽位，下一轮可处理其他项目。:return: None。"""
        self.activate(keys=['example', 'other'])
        self.start_work()
        self.assertEqual('failed', self.submit()['status'])
        self.assertEqual('deferred', self.submit()['status'])
        self.service._write("UPDATE projects_agents SET generation=2,status='running'")
        result = self.tool('claude_start', {'project_key': 'other', 'objective_id': 'feature'}, generation=2)
        self.assertEqual('running', result['status'])
        self.assertEqual(2, len(self.service._rows('SELECT * FROM projects_work')))
        self.assertEqual('rejected', self.tool('claude_start', {'project_key': 'example', 'objective_id': 'feature'}, generation=2)['status'])

    def test_cooldown_resumes_exact_work_and_session_after_service_restart(self):
        """重启保留待复验事实，复验沿用原work/session和修改而不复制seed。:return: None。"""
        self.activate()
        self.start_work()
        work = self.service._one('SELECT * FROM projects_work')
        self.submit()
        self.submit()
        self.service.close()
        old = self.service
        self.service = ProjectsService(self.root, self.database, threading.Lock(), self.catalog, self.terminal,
            old.account, old.admission, old.provider, old.verifier, self.pi)
        self.addCleanup(self.service.close)
        self.service._write('UPDATE projects_verification_holds SET retry_at=?', (time.time() - 1,))
        self.service._write("UPDATE projects_agents SET generation=generation+1,status='running'")
        generation = self.service._one('SELECT generation FROM projects_agents')['generation']
        result = self.tool('claude_start', {'project_key': 'example', 'objective_id': 'feature'}, generation=generation)
        self.assertEqual('running', result['status'])
        self.assertEqual(work['id'], result['work_id'])
        self.assertEqual(work['session_id'], result['session_id'])
        self.assertEqual(1, len(self.service._rows('SELECT * FROM projects_work')))

    def test_infrastructure_error_defers_and_does_not_request_business_repair(self):
        """已在本地重验的环境错误直接暂存，不交给模型无限改源码。:return: None。"""
        self.activate()
        self.start_work()
        self.verification = {'status': 'error', 'feedback': ['验证环境不可用']}
        result = self.submit()
        self.assertEqual('deferred', result['status'])
        self.assertEqual('error', result['verification']['status'])
        self.assertNotEqual('resume', self.terminal.controls[-1][1])

    def test_verifier_exception_also_yields_after_confirmed_release(self):
        """验证器抛错也自动冷却，不能变成人工确认或恢复被冻住的CLI。:return: None。"""
        self.activate()
        self.start_work()
        self.service.verifier = Mock(side_effect=RuntimeError('合成验证服务故障'))
        result = self.submit()
        self.assertEqual('deferred', result['status'])
        self.assertIsNone(self.service._one('SELECT runtime_json FROM projects_work')['runtime_json'])

    def test_correction_is_applied_once_without_discarding_native_session(self):
        """新纠错首次隔离Pi上下文，后续恢复同一检查点且Claude会话保持。:return: None。"""
        self.activate()
        self.start_work()
        work = self.service._one('SELECT * FROM projects_work')
        note = '已确认旧验收只统计错误，覆盖率已通过；按公开合同复验原候选。'
        self.service._event(1, 'verification_correction', {'message': note}, work['id'])
        calls = []
        self.pi.run = lambda config, *args: calls.append(config) or 'settled'
        self.service._run(1, 1, self.service.provider(), threading.Event())
        self.assertEqual('fresh', calls[-1]['context_mode'])
        self.assertIn(note, calls[-1]['prompt'])
        self.service._write("UPDATE projects_agents SET generation=2,status='running'")
        self.service._run(1, 2, self.service.provider(), threading.Event())
        self.assertEqual('resume', calls[-1]['context_mode'])
        self.assertEqual(work['session_id'], self.service._one('SELECT session_id FROM projects_work')['session_id'])

    def test_user_stop_cancels_deferred_resume_without_deleting_evidence(self):
        """人工停止仍优先于自动复验，代码和原始工作记录不删除。:return: None。"""
        self.activate()
        self.start_work()
        self.submit()
        self.submit()
        work = self.service._one('SELECT * FROM projects_work')
        self.service.pause(1, stop_work=True)
        state = self.service.state(1)['agents'][0]
        self.assertEqual('stopped', state['work']['status'])
        self.assertEqual([], state['deferred_objectives'])
        self.assertEqual(work['session_id'], state['work']['session_id'])

    def test_repeated_timeout_yields_without_blocking_schedule_or_resetting_budget(self):
        """连续两轮耗尽时限会自动暂存，计划等待复验而非人工解锁。:return: None。"""
        self.activate()
        self.start_work()
        self.service.configure_schedule(1, True, 1)
        self.pi.run = Mock(return_value='timeout')
        self.service._run(1, 1, self.service.provider(), threading.Event())
        self.service._write("UPDATE projects_agents SET generation=2,status='running'")
        self.tool('claude_start', {'project_key': 'example', 'objective_id': 'feature'}, generation=2)
        self.service._run(1, 2, self.service.provider(), threading.Event())
        state = self.service.state(1)['agents'][0]
        self.assertEqual('deferred', state['work']['status'])
        self.assertEqual('waiting', state['schedule']['state'])
        self.assertGreater(state['schedule']['next_run_at'], time.time())
        self.assertTrue(state['schedule']['enabled'])

    def test_cancellation_during_release_cannot_publish_round_complete(self):
        """长IO后取消仍优先，不能把迟到暂存作为下一目标的入场证明。:return: None。"""
        self.activate()
        self.start_work()
        work = self.service._one('SELECT * FROM projects_work')
        stop = threading.Event()
        original = self.terminal.control

        def control(value, operation):
            """在停止确认时模拟用户取消。:param value: 原目标。:param operation: 操作。:return: 收口结果。"""
            if operation == 'stop':
                stop.set()
            return original(value, operation)

        self.terminal.control = control
        with self.assertRaisesRegex(ValueError, '取消'):
            self.service._defer_work(work, 1, '有限返工', stop)
        self.assertIsNone(self.service._one('SELECT * FROM projects_verification_holds'))

    def test_warmup_namespace_has_own_holds_and_activity_index(self):
        """养号空间拥有独立索引和复验表，不能被项目空间结果串用。:return: None。"""
        old = self.service
        warmup = ProjectsService(self.root, self.database, threading.Lock(), self.catalog, self.terminal,
            old.account, old.admission, old.provider, old.verifier, self.pi, namespace='warmup')
        self.addCleanup(warmup.close)
        self.service = warmup
        self.activate(keys=['example', 'other'])
        self.start_work()
        self.submit()
        self.assertEqual('deferred', self.submit()['status'])
        self.assertEqual([], old._rows('SELECT * FROM projects_verification_holds'))
        self.assertEqual(1, len(warmup._rows('SELECT * FROM projects_verification_holds')))
