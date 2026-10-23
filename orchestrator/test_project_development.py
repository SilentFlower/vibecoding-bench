"""完整开发周期的真实 SQLite、会话交接和有限恢复回归。"""
import json
import sys
import time
import unittest
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from unittest.mock import Mock, patch

import test_project_scenarios as scenario_tests
from project_iteration import ProjectIterationManager
from project_library import ProjectLibrary, safe_relative, snapshot_tree, write_document
from project_development import ProjectDevelopment
from test_project_iterations import ProjectIterationFixture, ROOT
from test_project_scenario_content import scenario_fixture


def development_fixture(root: Path) -> Path:
    """构造单项完整开发任务，只用于隔离回归。

    :param root: 临时内容根。
    :return: 已写入 schema 3 的夹具根目录。
    """
    scenario_fixture(root)
    project = root / 'projects/example'
    (project / 'seed/library').mkdir()
    (project / 'seed/example.py').rename(project / 'seed/library/example.py')
    manifest = json.loads((project / 'project.json').read_text())
    task = manifest['scenarios'][0]['tasks'][0]
    task.update(kind='modify', development_cycle='feature', allowed_paths=['library/example.py'],
        prompt='We need VALUE to become 2. First explain the current code, then agree a plan before implementation.',
        owner_materials=['disclosure/details.txt'], outcomes=['implemented'])
    task['evaluation']['native'] = 'verification/native.json'
    rubric_path = project / task['evaluation']['rubric']
    rubric_path.write_text(rubric_path.read_text().replace('example.py:1', 'library/example.py:1'))
    (project / 'verification/native.py').write_text('raise SystemExit("isolated fixture only")\n')
    (project / 'verification/private-secret.txt').write_text('PRIVATE_VERIFICATION_SENTINEL')
    write_document(project / 'verification/native.json', {'script': 'verification/native.py', 'args': [],
        'python_paths': ['library'], 'expected': {'VALUE': 2}})
    manifest.update(schema=3, seed_digest=snapshot_tree(project / 'seed')['digest'])
    manifest['scenarios'][0]['tasks'] = [task]
    manifest['scenarios'][0]['entries'][0]['task_ids'] = [task['id']]
    write_document(project / 'project.json', manifest)
    write_document(root / 'catalog.json', {'schema': 3, 'version': 'test-only-development', 'projects': ['example']})
    return root


class DevelopmentStateTests(ProjectIterationFixture):
    """完整任务共享原会话，普通交流与业务交付分别推进。"""

    configure_run = scenario_tests.ScenarioStateTests.configure_run
    submit_reply = scenario_tests.ScenarioStateTests.submit_reply
    release_run = scenario_tests.ScenarioStateTests.release_run
    control = scenario_tests.ScenarioStateTests.control

    def setUp(self) -> None:
        """准备实际表、原生消息驱动和受控外部模型。@return None。"""
        super().setUp()
        self.client = Mock()
        self.client.model, self.client.fallback_model = 'primary', 'secondary'
        self.client.models, self.client.revision = ('primary', 'secondary'), 'environment'
        self.native = Mock()
        self.native.verify_native.side_effect = self.verify_native
        library = ProjectLibrary(development_fixture(self.data / 'development-library'))
        self.scenario_manager = ProjectIterationManager(self.data, library, self.manager.database, self.manager.write_lock,
            self.manager.submit, self.manager.settings, self.manager.identity, self.manager.stop_run,
            self.native, self.manager.is_executing, dialogue=self.client)
        self.addCleanup(self.scenario_manager.stop)
        self.batch = self.scenario_manager.create_batch(1, '完整周期', policy={})
        self.scenario_manager.transition(self.batch['id'], 'start')
        self.states = self.scenario_manager.scenarios
        self.tasks = self.sql('SELECT * FROM project_scenario_tasks ORDER BY id')
        self.task_id = self.tasks[0]['id']
        self.controls = []
        self.scenario_manager.plans.control = lambda run, epoch, operation: self.control(run, epoch, operation)
        specification = spec_from_file_location('development_driver_fixture', ROOT / 'images/account/project_plan.py')
        self.driver = module_from_spec(specification)
        with patch.dict(sys.modules, {'task_followups': self.scenario_manager.plans.dialogue}):
            specification.loader.exec_module(self.driver)

    def verify_native(self, candidate, *args, **kwargs) -> dict:
        """只检查可信测试夹具值，实际 Docker 行为另行验证。

        :param candidate: 冻结候选目录。
        :param args: 原验证接口参数。
        :param kwargs: 原验证接口选项。
        :return: 夹具业务结果。
        """
        actual = int((candidate / 'library/example.py').read_text().split('=')[1].strip())
        return {'status': 'passed' if actual == 2 else 'failed', 'actual': {'VALUE': actual},
            'expected': {'VALUE': 2}, 'feedback_codes': [] if actual == 2 else ['behavior_mismatch']}

    def model_result(self, action='reply', message='Please explain the error path.', *, model='primary') -> dict:
        """构造已经通过客户端校验的受控回复。

        :param action: 业务动作。
        :param message: 下一条自然用户消息。
        :param model: 实际请求的模型。
        :return: 客户端结果。
        """
        return {'status': 'ready', 'category': None, 'action': action, 'message': message, 'model': model,
            'configuration_revision': self.client.revision,
            'elapsed_sec': 0.25, 'fallback_reason': 'quota' if model == 'secondary' else None,
            'attempts': [{'status': 'ready', 'model': model, 'usage': {'prompt_tokens': 10, 'completion_tokens': 4}}]}

    def launch(self) -> tuple[str, dict]:
        """通过正式预留与 driver 创建一个开发者执行片段。

        :return: 实际 Run 与原生驱动配置。
        """
        task = self.states.task(self.task_id)
        batch = self.sql('SELECT * FROM project_iteration_batches WHERE id=?', (self.batch['id'],))[0]
        account = self.sql('SELECT * FROM accounts WHERE id=1')[0]
        self.states.refresh_readiness(task['scenario_instance_id'])
        self.assertTrue(self.states._reserve_candidate(batch, account, self.task_id))
        run = self.launches[-1][0]
        return run, self.configure_run(run)

    def turn(self, action, answer='The actual code and plan are explained.', *, value=None, model='primary') -> int:
        """通过真实输入与回答证据推进一轮。

        :param action: 外部需求方选择。
        :param answer: 开发者实际回复。
        :param value: 可选模拟代码交付。
        :param model: 请求使用的主备模型。
        :return: 本轮冻结回答作业 ID。
        """
        run, config = self.launch()
        if value is not None:
            workspace = self.data / safe_relative(self.states.task(self.task_id)['workspace_relative'])
            (workspace / 'library/example.py').write_text(f'VALUE = {value}\n')
        self.client.generate.return_value = self.model_result(action, 'Please continue the agreed task.', model=model)
        job_id = self.submit_reply(run, config, answer)
        self.release_run(run)
        self.states._mechanical_job(job_id)
        return job_id

    def test_more_than_eight_questions_keep_one_attempt_and_no_review(self) -> None:
        """深入追问不被旧短题轮数切断，不启动原生或模型验收。@return None。"""
        for number in range(10):
            self.turn('reply', f'Actual detail {number} is explained.')
        task = self.states.task(self.task_id)
        self.assertEqual(('ready', 11, 1), (task['status'], task['turn_no'], task['attempt_count']))
        self.native.verify_native.assert_not_called()
        self.assertEqual(1, self.sql('SELECT COUNT(DISTINCT session_id) AS count FROM project_task_executions')[0]['count'])
        self.assertFalse(self.sql("SELECT id FROM project_task_executions WHERE role='review'"))
        conversation = self.states.attempts(task['instance_id'], task['id'])['conversation']
        self.assertEqual(20, len(conversation))
        context = self.client.generate.call_args.args[0]
        self.assertNotIn('PRIVATE_VERIFICATION_SENTINEL', json.dumps(context))
        self.assertIn('隐藏材料', json.dumps(context, ensure_ascii=False))

    def test_plan_approval_then_delivery_completes_one_task(self) -> None:
        """确认方案后在原会话交付，独立验证只在交付触发。@return None。"""
        self.turn('implement')
        self.assertEqual('implementing', self.states.development.phase(self.task_id))
        job_id = self.turn('verify', 'The agreed change is implemented and tested.', value=2)
        self.assertEqual('passed', self.states.task(self.task_id)['status'])
        self.assertEqual('passed', self.sql('SELECT status FROM project_evaluation_jobs WHERE id=?', (job_id,))[0]['status'])
        self.assertEqual(1, self.native.verify_native.call_count)
        self.assertEqual(1, self.sql('SELECT visit_completed FROM project_instances WHERE id=?',
            (self.states.task(self.task_id)['instance_id'],))[0]['visit_completed'])
        self.assertIsNotNone(self.client.generate.call_args.args[0]['approved_plan'])
        self.assertEqual({'passed': 1}, self.scenario_manager.batch(self.batch['id'])['task_counts'])

    def test_failed_delivery_returns_concrete_feedback_then_repairs_same_session(self) -> None:
        """程序失败反馈实际差异，修复后仅接受一次业务成果。@return None。"""
        self.turn('implement')
        self.turn('verify', 'The implementation is ready.')
        task = self.states.task(self.task_id)
        self.assertEqual(('ready', 'repairing'), (task['status'], task['phase']))
        self.assertEqual(0, self.scenario_manager.batch(self.batch['id'])['task_counts'].get('passed', 0))
        self.assertIn('"VALUE":1', task['next_prompt'])
        self.assertIn('"VALUE":2', task['next_prompt'])
        self.turn('verify', 'The demonstrated issue is repaired.', value=2)
        self.assertEqual(('passed', 2), (self.states.task(self.task_id)['status'], self.states.task(self.task_id)['attempt_count']))
        self.assertEqual(1, self.sql('SELECT COUNT(DISTINCT session_id) AS count FROM project_task_executions')[0]['count'])
        self.assertEqual(1, self.states.development.revisions(self.task_id)['business_repairs'])
        self.assertEqual(0, self.states.development.revisions(self.task_id)['review_appeals'])

    def test_timeout_resumes_partial_code_without_spending_repair_attempt(self) -> None:
        """工作切片超时保留方案、原会话和半成品，不扣业务修复次数。@return None。"""
        self.turn('implement')
        run, config = self.launch()
        workspace = self.data / safe_relative(self.states.task(self.task_id)['workspace_relative'])
        (workspace / 'library/example.py').write_text('VALUE = 2\n')
        native = Path(config['native_directory']) / (config['session_id'] + '.jsonl')
        with native.open('a') as stream:
            stream.write(json.dumps({'type': 'user', 'uuid': 'unfinished-input',
                'message': {'role': 'user', 'content': config['prompt']}}) + '\n')
        self.driver.process('tick', config)
        self.driver.process('finish', config)
        self.sql("UPDATE runs SET status='timeout',ended_at=2 WHERE id=?", (run,))
        self.states.execution_released(run, 0, None)
        execution = self.sql('SELECT e.*,r.status AS run_status FROM project_task_executions e JOIN runs r ON r.id=e.run_id WHERE run_id=?', (run,))[0]
        source = self.sql('SELECT * FROM project_execution_sources WHERE execution_id=?', (execution['id'],))[0]
        batch = self.sql('SELECT * FROM project_iteration_batches WHERE id=?', (self.batch['id'],))[0]
        self.states._settle_execution(batch, execution, source)
        self.assertEqual(('ready', 'timeout_resume', 1), tuple(self.states.task(self.task_id)[key]
            for key in ('status', 'phase', 'attempt_count')))
        resumed, resumed_config = self.launch()
        self.assertTrue(resumed_config['resume'])
        self.assertEqual(config['session_id'], resumed_config['session_id'])
        self.assertEqual('VALUE = 2\n', (workspace / 'library/example.py').read_text())
        self.assertEqual('timeout', self.sql('SELECT status FROM runs WHERE id=?', (run,))[0]['status'])
        self.assertNotEqual(run, resumed)

    def test_saved_fallback_reply_is_replayed_without_new_generation(self) -> None:
        """生成结果先落盘，重复收口不调用模型或追加同一句话。@return None。"""
        job_id = self.turn('reply', model='secondary')
        count, turn = self.client.generate.call_count, self.states.task(self.task_id)['turn_no']
        self.states._mechanical_job(job_id)
        self.assertEqual((count, turn), (self.client.generate.call_count, self.states.task(self.task_id)['turn_no']))
        self.turn('reply', model='secondary')
        self.assertEqual('secondary', self.client.generate.call_args.kwargs['preferred_model'])
        usage = self.states.usage(self.states.task(self.task_id)['instance_id'])['tasks'][0]['roles']['requester']
        self.assertEqual((2, 20, 8), (usage['requests'], usage['input_tokens'], usage['output_tokens']))

    def test_changed_model_configuration_reselects_without_replacing_developer_session(self) -> None:
        """配置变更或旧模型移除后重新选择，原开发者会话和有效消息保持。@return None。"""
        self.turn('reply', model='secondary')
        self.client.models, self.client.revision = ('new-primary', 'new-secondary'), 'page-new-revision'
        self.turn('reply', model='new-primary')
        self.assertIsNone(self.client.generate.call_args.kwargs['preferred_model'])
        self.assertEqual(1, self.sql('SELECT COUNT(DISTINCT session_id) AS count FROM project_task_executions')[0]['count'])

    def test_pause_keeps_generated_reply_until_same_task_resumes(self) -> None:
        """请求期间暂停只保存消息，恢复后发送原消息而非重新生成。@return None。"""
        run, config = self.launch()
        job_id = self.submit_reply(run, config, 'A concrete code question has been answered.')
        self.release_run(run)
        def generate(*args, **kwargs):
            self.sql("UPDATE project_iteration_batches SET status='paused' WHERE id=?", (self.batch['id'],))
            return self.model_result('reply', 'Ask the next detail exactly once.')
        self.client.generate.side_effect = generate
        self.states._mechanical_job(job_id)
        self.assertEqual('evaluating', self.states.task(self.task_id)['status'])
        self.client.models, self.client.revision = ('replacement-only',), 'changed-while-paused'
        self.sql("UPDATE project_iteration_batches SET status='active' WHERE id=?", (self.batch['id'],))
        self.scenario_manager.stop()
        self.scenario_manager = ProjectIterationManager(self.data, self.scenario_manager.library,
            self.manager.database, self.manager.write_lock, self.manager.submit, self.manager.settings,
            self.manager.identity, self.manager.stop_run, self.native, self.manager.is_executing, dialogue=self.client)
        self.addCleanup(self.scenario_manager.stop)
        self.states = self.scenario_manager.scenarios
        self.states._mechanical_job(job_id)
        self.assertEqual(1, self.client.generate.call_count)
        self.assertEqual('Ask the next detail exactly once.', self.states.task(self.task_id)['next_prompt'])

    def test_unfinished_external_request_retains_reservation_and_blocks_blind_retry(self) -> None:
        """重启遇已发送但未收回的请求时保留不确定状态。@return None。"""
        run, config = self.launch()
        job_id = self.submit_reply(run, config, 'The plan is partially explained.')
        self.release_run(run)
        job = self.sql('SELECT * FROM project_evaluation_jobs WHERE id=?', (job_id,))[0]
        self.sql('INSERT INTO project_dialogue_jobs(task_id,evaluation_job_id,generation,status,phase,request_json,reserved_sec,created_at) '
            "VALUES(?,?,1,'requesting','investigating','{}',30,1)", (self.task_id, job_id))
        self.states._mechanical_job(job_id)
        self.client.generate.assert_not_called()
        self.assertEqual('blocked', self.states.task(self.task_id)['status'])
        budget = self.states.budget(self.task_id)
        self.assertTrue(budget['uncertain'])
        self.assertGreaterEqual(budget['reserved_sec'], 30)

    def test_verification_before_plan_approval_does_not_accept_code(self) -> None:
        """需求方不能提前提交验收或自行声明完成。@return None。"""
        self.turn('verify', 'There is no approved plan yet.', value=2)
        self.assertEqual('blocked', self.states.task(self.task_id)['status'])
        self.native.verify_native.assert_not_called()

    def test_transient_request_failure_resumes_saved_delivery_verification(self) -> None:
        """外部故障恢复后验证原交付，不重复实现或损失业务修复机会。@return None。"""
        self.turn('implement')
        run, config = self.launch()
        workspace = self.data / safe_relative(self.states.task(self.task_id)['workspace_relative'])
        (workspace / 'library/example.py').write_text('VALUE = 2\n')
        job_id = self.submit_reply(run, config, 'The approved implementation is ready.')
        self.release_run(run)
        self.client.generate.return_value = {'status': 'error', 'category': 'rate_limit',
            'attempts': [{'model': 'primary', 'category': 'rate_limit'}], 'elapsed_sec': 0.5,
            'error': '需求方服务限流'}
        self.states._mechanical_job(job_id)
        task = self.states.task(self.task_id)
        self.assertEqual(('evaluating', 1), (task['status'], task['attempt_count']))
        self.assertEqual('dialogue_wait', self.sql('SELECT status FROM project_evaluation_jobs WHERE id=?', (job_id,))[0]['status'])
        calls = self.client.generate.call_count
        self.states._mechanical_job(job_id)
        self.assertEqual(calls, self.client.generate.call_count)
        self.sql('UPDATE project_dialogue_jobs SET retry_at=0 WHERE evaluation_job_id=?', (job_id,))
        self.client.generate.return_value = self.model_result('verify', '')
        self.states._mechanical_job(job_id)
        self.assertEqual('passed', self.states.task(self.task_id)['status'])
        self.assertEqual(1, self.native.verify_native.call_count)
        self.states._mechanical_job(job_id)
        self.assertEqual(1, self.native.verify_native.call_count)
        self.assertEqual(1, self.sql('SELECT visit_completed FROM project_instances WHERE id=?', (task['instance_id'],))[0]['visit_completed'])
        usage = self.states.development.summary(self.task_id)
        self.assertEqual(3, usage['requests'])
        self.assertFalse(usage['complete'])

    def test_stopped_parent_never_receives_late_generated_message(self) -> None:
        """停止与外部响应竞争时保存调用事实，禁止恢复或投递迟到消息。@return None。"""
        run, config = self.launch()
        job_id = self.submit_reply(run, config, 'The original investigation is explained.')
        self.release_run(run)
        def generate(*args, **kwargs):
            self.scenario_manager.transition(self.batch['id'], 'stop')
            return self.model_result('implement', 'Implement the plan now.')
        self.client.generate.side_effect = generate
        self.states._mechanical_job(job_id)
        task = self.states.task(self.task_id)
        self.assertNotEqual('ready', task['status'])
        self.assertEqual(1, task['turn_no'])
        self.assertEqual('cancelled', self.sql('SELECT status FROM project_dialogue_jobs WHERE evaluation_job_id=?', (job_id,))[0]['status'])

    def test_verified_delivery_resumes_only_result_application_after_interruption(self) -> None:
        """验证已完成但尚未收口时复用原证据，只接受一次交付。@return None。"""
        self.turn('implement')
        with patch.object(self.states, '_apply_result'):
            job_id = self.turn('verify', 'The approved delivery is implemented.', value=2)
        job = self.sql('SELECT * FROM project_evaluation_jobs WHERE id=?', (job_id,))[0]
        self.assertEqual('mechanical_running', job['status'])
        self.assertEqual('passed', json.loads(job['native_result_json'])['status'])
        self.assertEqual('evaluating', self.states.task(self.task_id)['status'])
        self.states._mechanical_job(job_id)
        self.assertEqual('passed', self.states.task(self.task_id)['status'])
        self.assertEqual(1, self.native.verify_native.call_count)
        self.assertEqual(2, self.client.generate.call_count)

    def test_eligible_continuation_precedes_fresh_task_without_blocking_on_service_wait(self) -> None:
        """同账号先续原任务，服务等待时其它完整任务仍可使用空闲容量。@return None。"""
        self.turn('reply')
        other = self.scenario_manager.create_batch(1, '另一个完整任务', policy={})
        self.scenario_manager.transition(other['id'], 'start')
        fresh = self.sql('SELECT t.id FROM project_scenario_tasks t JOIN project_scenario_instances s '
            'ON s.id=t.scenario_instance_id JOIN project_instances i ON i.id=s.instance_id WHERE i.batch_id=?', (other['id'],))[0]['id']
        batch = self.sql('SELECT * FROM project_iteration_batches WHERE id=?', (other['id'],))[0]
        account = self.sql('SELECT * FROM accounts WHERE id=1')[0]
        self.states.refresh_readiness(self.states.task(fresh)['scenario_instance_id'])
        self.assertFalse(self.states._reserve_candidate(batch, account, fresh))
        # 待生成的外部消息尚不具备执行条件，不持有 Claude 执行名额。
        self.sql("UPDATE project_scenario_tasks SET status='evaluating' WHERE id=?", (self.task_id,))
        self.assertTrue(self.states._reserve_candidate(batch, account, fresh))

    def test_same_code_semantic_appeal_is_bounded_and_program_failure_cannot_be_overridden(self) -> None:
        """同版本只允许一次语义复核，不能不断重抽得到通过。@return None。"""
        definition = json.loads(self.states.task(self.task_id)['definition_json'])
        definition['evaluation']['semantic'] = True
        self.sql('UPDATE project_scenario_tasks SET definition_json=? WHERE id=?', (json.dumps(definition), self.task_id))
        self.turn('implement')
        failed = self.turn('verify', 'The delivered code implements the agreed behavior.', value=2)
        semantic_failure = {'decision': 'fail', 'outcome': None, 'feedback_codes': ['missing_evidence'],
            'criteria': [{'status': 'violated', 'reason': 'Explain the preserved boundary.', 'evidence': ['library/example.py']}]}
        self.states._apply_result(self.sql('SELECT * FROM project_evaluation_jobs WHERE id=?', (failed,))[0], semantic_failure)
        appealed = self.turn('verify', 'The exact unchanged source and behavior demonstrate that the review misunderstood the boundary.')
        self.assertEqual('review_ready', self.sql('SELECT status FROM project_evaluation_jobs WHERE id=?', (appealed,))[0]['status'])
        self.states._apply_result(self.sql('SELECT * FROM project_evaluation_jobs WHERE id=?', (appealed,))[0], semantic_failure)
        self.turn('verify', 'Please review the same code again.')
        self.assertEqual('blocked', self.states.task(self.task_id)['status'])
        self.assertEqual(2, self.native.verify_native.call_count)
        self.assertEqual(1, self.states.development.revisions(self.task_id)['review_appeals'])

    def test_unchanged_program_failure_cannot_enter_semantic_appeal(self) -> None:
        """程序明确失败时不能靠同版本模型重评覆盖事实。@return None。"""
        self.turn('implement')
        self.turn('verify', 'The implementation is ready.')
        self.turn('verify', 'The program must pass; review the unchanged code again.')
        self.assertEqual('blocked', self.states.task(self.task_id)['status'])
        self.assertEqual(1, self.native.verify_native.call_count)


class DevelopmentContentTests(unittest.TestCase):
    """新内容明确任务颗粒度，旧服务不会静默解释成短问答。"""

    def test_new_schema_has_one_complete_task_and_rejects_legacy_turn_cap(self) -> None:
        """单需求计数和版本一致，旧四轮限制不进入新周期。@return None。"""
        from tempfile import TemporaryDirectory
        with TemporaryDirectory() as temporary:
            root = development_fixture(Path(temporary) / 'library')
            library = ProjectLibrary(root)
            summary = library.projects['example'].summary(include_steps=True)
            self.assertEqual((3, 1, 'feature'), (summary['content_schema'], summary['task_count'],
                summary['scenarios'][0]['tasks'][0]['development_cycle']))
            path = root / 'projects/example/project.json'
            manifest = json.loads(path.read_text())
            manifest['scenarios'][0]['tasks'][0]['max_turns'] = 4
            write_document(path, manifest)
            with self.assertRaises(ValueError):
                ProjectLibrary(root)

    def test_large_regression_feedback_keeps_concrete_failure(self) -> None:
        """完整回归报告很大时仍保留失败位置和预期／实际差异。@return None。"""
        report = {'status': 'failed', 'native': {'status': 'failed', 'regression': {'status': 'failed',
            'nodes': [{'id': 'frozen-node-' + str(number)} for number in range(3000)],
            'stdout_tail': 'tests/test_api.py::test_boundary: expected VALUE=2, got VALUE=1',
            'counts': {'passed': 2999, 'failed': 1}, 'returncode': 1}}}
        prompt = ProjectDevelopment.failure_feedback({'native_result_json': json.dumps(report)},
            {'feedback_codes': ['behavior_mismatch'], 'criteria': []})
        self.assertIn('tests/test_api.py::test_boundary', prompt)
        self.assertIn('expected VALUE=2, got VALUE=1', prompt)
        self.assertLess(len(prompt.encode()), 13000)
        criteria = [{'status': 'violated', 'reason': '失败原因' * 150,
            'evidence': ['library/' + '说明' * 80 + '.py'] * 4} for _ in range(4)]
        unicode_prompt = ProjectDevelopment.failure_feedback({'native_result_json': json.dumps(report)},
            {'feedback_codes': ['behavior_mismatch'], 'criteria': criteria})
        self.assertLess(len(unicode_prompt.encode()), 13000)
        self.assertIn('tests/test_api.py::test_boundary', unicode_prompt)

    def test_development_manifest_and_historical_catalog_have_separate_semantics(self) -> None:
        """新定义入口不改写旧题目，待准入项目也不能混进可执行计数。@return None。"""
        from tempfile import TemporaryDirectory
        with TemporaryDirectory() as temporary:
            root = development_fixture(Path(temporary) / 'library')
            project = root / 'projects/example'
            manifest = json.loads((project / 'project.json').read_text())
            write_document(project / 'development.json', manifest)
            manifest['schema'] = 2
            manifest['scenarios'][0]['tasks'][0].pop('development_cycle')
            manifest['scenarios'][0]['tasks'][0].pop('owner_materials')
            write_document(project / 'project.json', manifest)
            catalog = {'schema': 3, 'version': 'test-new', 'projects': ['example'], 'project_manifest': 'development.json',
                'admission': [{'project_key': 'example', 'status': 'ready'},
                    {'project_key': 'pending-project', 'status': 'blocked', 'reason': '缺少真实工程合同'}]}
            write_document(root / 'catalog.json', catalog)
            write_document(root / 'catalog-legacy.json', {'schema': 2, 'version': 'test-old', 'projects': ['example']})
            self.assertEqual(3, ProjectLibrary(root).schema)
            self.assertEqual(2, ProjectLibrary(root, catalog_name='catalog-legacy.json').schema)
            catalog['admission'][1]['status'] = 'ready'
            write_document(root / 'catalog.json', catalog)
            with self.assertRaises(ValueError):
                ProjectLibrary(root)


if __name__ == '__main__':
    unittest.main()
