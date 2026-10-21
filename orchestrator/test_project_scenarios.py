"""场景任务输入消费和累计工作预算的持久回归。"""
import json
import sys
import threading
import time
import unittest
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from unittest.mock import Mock, patch

from project_iteration import ProjectIterationManager
from project_library import ProjectLibrary, snapshot_tree, write_document
from project_scenarios import initialize_scenario_schema, normalized_scenario_policy
from test_project_iterations import ProjectIterationFixture
from test_project_iterations import ROOT
from test_project_scenario_content import scenario_fixture


class ScenarioStateTests(ProjectIterationFixture):
    """使用真实 SQLite 验证跨 Run、额度代次和重启不增发预算。"""

    def setUp(self) -> None:
        """建立新内容批次，沿用测试专用调度器。@return None。"""
        super().setUp()
        library = ProjectLibrary(scenario_fixture(self.data / 'scenario-library'))
        self.scenario_manager = ProjectIterationManager(self.data, library, self.manager.database, self.manager.write_lock,
            self.manager.submit, self.manager.settings, self.manager.identity, self.manager.stop_run,
            self.manager.verifier, self.manager.is_executing)
        self.addCleanup(self.scenario_manager.stop)
        self.batch = self.scenario_manager.create_batch(1, '多类型测试', policy={})
        self.scenario_manager.transition(self.batch['id'], 'start')
        self.states = self.scenario_manager.scenarios
        self.tasks = self.sql('SELECT * FROM project_scenario_tasks ORDER BY id')
        self.controls = []
        self.scenario_manager.plans.control = lambda run,epoch,operation: self.control(run,epoch,operation)
        specification = spec_from_file_location('scenario_driver_fixture',ROOT/'images/account/project_plan.py')
        self.driver = module_from_spec(specification)
        with patch.dict(sys.modules,{'task_followups':self.scenario_manager.plans.dialogue}):
            specification.loader.exec_module(self.driver)

    def control(self, run: str, epoch: int, operation: str) -> dict:
        """只模拟定向内核证明，真正隔离另由Docker验证。@param run 运行。@param epoch 代次。@param operation 操作。@return 证明。"""
        self.controls.append((run,epoch,operation))
        return {'source':f'run:{run}:{epoch}','frozen':operation=='freeze','resumed':operation=='resume'}

    def configure_run(self, run_id: str, *, review: bool = False) -> dict:
        """按真实内容和driver初始化一次实际执行夹具。@param run_id 运行。@param review 独立评审。@return 本机配置。"""
        self.sql("UPDATE runs SET status='running',started_at=1 WHERE id=?",(run_id,))
        if review:
            native = self.data/'review-private'/run_id/'native'
            cwd = '/home/node/review'
        else:
            row = {'environment_id':'scenario-env','account_id':1}
            alias,_ = self.scenario_manager.prepare_workspace(row,run_id,self.data/'environments/scenario-env')
            cwd = '/home/node/projects/'+alias
            native = self.data/'environments/scenario-env/home/.claude/projects'/cwd.replace('/','-')
        native.mkdir(parents=True,exist_ok=True)
        runtime = self.data/'scenario-runtime'/run_id
        runtime.mkdir(parents=True)
        config = self.states.execution_configuration(run_id,f'run:{run_id}:0',0,native,
            runtime/'request.json',runtime/'decision.json',cwd)
        self.states.permit_start(run_id,f'run:{run_id}:0')
        config.update(native_directory=str(native),request_file=str(runtime/'request.json'),decision_file=str(runtime/'decision.json'),
            state_file=str(runtime/'project-plan-state.json'),work_file=str(runtime/'project-work.json'))
        self.driver.process('begin',config)
        return config

    def submit_reply(self, run_id: str, config: dict, answer: str, *, model: str = 'unit-fixture-model') -> int:
        """真实解析原生父链并封存候选，执行仍未释放。@param run_id 运行。@param config driver。@param answer 回答。@param model 实际模型。@return 作业ID。"""
        path = Path(config['native_directory'])/(config['session_id']+'.jsonl')
        user,assistant = 'user-'+run_id,'assistant-'+run_id
        records = [{'type':'user','uuid':user,'message':{'role':'user','content':config['prompt']}},
            {'type':'assistant','uuid':assistant,'parentUuid':user,'message':{'id':'response-'+run_id,'role':'assistant','model':model,
                'content':answer,'stop_reason':'end_turn','usage':{'input_tokens':7,'output_tokens':11,
                    'cache_read_input_tokens':0,'cache_creation_input_tokens':0}}}]
        with path.open('a') as stream:
            for record in records:
                stream.write(json.dumps(record)+'\n')
        results,errors = [],[]

        def advance() -> None:
            try:
                results.append(self.driver.process('advance',config,wait_seconds=4))
            except Exception as error:
                errors.append(error)

        thread = threading.Thread(target=advance)
        thread.start()
        deadline = time.monotonic()+3
        while not Path(config['request_file']).exists() and time.monotonic()<deadline:
            time.sleep(0.01)
        execution = self.sql('SELECT * FROM project_task_executions WHERE run_id=?',(run_id,))[0]
        source = self.sql('SELECT * FROM project_execution_sources WHERE execution_id=?',(execution['id'],))[0]
        if execution['role']=='candidate':
            self.states.capture_submission(execution,source)
        else:
            self.states._capture_review(execution,source)
        thread.join(timeout=5)
        self.assertFalse(thread.is_alive())
        if errors:
            raise errors[0]
        self.assertEqual('complete',results[0]['action'])
        return self.sql('SELECT id FROM project_evaluation_jobs WHERE task_id=? ORDER BY id DESC LIMIT 1',(execution['task_id'],))[0]['id']

    def release_run(self, run_id: str) -> None:
        """分别记录真实执行终态及严格释放。@param run_id 运行。@return None。"""
        self.sql("UPDATE runs SET status='success',ended_at=2 WHERE id=?",(run_id,))
        self.states.execution_released(run_id,0,None)
        execution = self.sql('SELECT e.*,r.status AS run_status,r.error AS run_error FROM project_task_executions e JOIN runs r ON r.id=e.run_id WHERE run_id=?',(run_id,))[0]
        source = self.sql('SELECT * FROM project_execution_sources WHERE execution_id=?',(execution['id'],))[0]
        batch = self.sql('SELECT * FROM project_iteration_batches WHERE id=?',(self.batch['id'],))[0]
        self.states._settle_execution(batch,execution,source)

    def execution(self, task_id: int, number: int, *, role: str = 'candidate', job_id=None,
                  review_attempt=None, reason='initial', delivery_id=None) -> tuple[int, int]:
        """建立实际表执行夹具。@param task_id 任务。@param number 执行序号。@return 执行和来源 ID。"""
        run_id = f'test{number}'
        generic = self.sql("INSERT INTO tasks(topic_no,title,prompt,account_id,timeout_sec) VALUES(1,'测试','问题',1,600) RETURNING id")[0]['id']
        self.sql("INSERT INTO runs(id,task_id,account_id,status,run_kind) VALUES(?,?,1,'running',?)",
            (run_id, generic, 'project_review' if role == 'review' else 'project_iteration'))
        if delivery_id is None:
            delivery_id = self.sql("INSERT INTO project_task_deliveries(task_id,phase_key,prompt,input_digest,created_at) VALUES(?,?,'问题','digest',1) RETURNING id",
                (task_id, f'phase{number}'))[0]['id']
        self.sql('UPDATE project_scenario_tasks SET next_reason=? WHERE id=?', (reason, task_id))
        execution_id = self.sql('INSERT INTO project_task_executions(task_id,run_id,role,evaluation_job_id,review_attempt,'
            'turn_no,generation,session_id,delivery_id,created_at) VALUES(?,?,?,?,?,1,1,?,?,1) RETURNING id',
            (task_id, run_id, role, job_id, review_attempt, 'session', delivery_id))[0]['id']
        source_id = self.sql('INSERT INTO project_execution_sources(execution_id,quota_attempt,source,created_at) VALUES(?,0,?,1) RETURNING id',
            (execution_id, f'run:{run_id}:0'))[0]['id']
        return execution_id, source_id

    def job(self, task_id: int, source_id: int) -> int:
        """建立有固定回答预算的评测作业。@param task_id 任务。@param source_id 来源。@return 作业 ID。"""
        return self.sql('INSERT INTO project_evaluation_jobs(task_id,source_id,turn_no,generation,response_key,response_digest,'
            'input_digest,basis_digest,candidate_digest,candidate_relative,answer_relative,evidence_json,version,response_budget_sec,created_at) '
            "VALUES(?,?,1,1,'response','r','i','b','c','candidate','answer','{}',1,360,1) RETURNING id", (task_id, source_id))[0]['id']

    def test_new_policy_defaults_and_explicit_values(self) -> None:
        """新内容默认600，旧字段和非法类型不静默覆盖。@return None。"""
        self.assertEqual(600, self.batch['policy']['timeout_sec'])
        self.assertEqual(3, self.batch['policy']['schema'])
        self.assertEqual(61, normalized_scenario_policy({'timeout_sec': 61}, 1, 2)['timeout_sec'])
        for value in (None, True, '600', 60.0, 59):
            with self.subTest(value=value), self.assertRaises(ValueError):
                normalized_scenario_policy({'timeout_sec': value}, 1, 2)

    def test_dependency_readiness_is_not_array_prefix(self) -> None:
        """第一和第二项独立就绪，第三项只依赖第一项。@return None。"""
        scenario_id = self.tasks[0]['scenario_instance_id']
        self.states.refresh_readiness(scenario_id)
        self.assertEqual(['ready', 'ready', 'pending'], [item['status'] for item in self.sql('SELECT status FROM project_scenario_tasks ORDER BY id')])
        self.sql("UPDATE project_scenario_tasks SET status='failed' WHERE task_key='Q1'")
        self.states.refresh_readiness(scenario_id)
        self.assertEqual(['failed', 'ready', 'blocked'], [item['status'] for item in self.sql('SELECT status FROM project_scenario_tasks ORDER BY id')])

    def test_attempt_claim_requires_consumption_and_clarification_reuses(self) -> None:
        """排队不扣次数，正常澄清及已消费重放不增业务尝试。@return None。"""
        task_id = self.tasks[0]['id']
        execution_id, source_id = self.execution(task_id, 1)
        self.assertEqual(0, self.states.task(task_id)['attempt_count'])
        attempt = self.states.consume_delivery(execution_id, source_id, 'user1')
        self.assertEqual(attempt, self.states.consume_delivery(execution_id, source_id, 'user1'))
        self.sql('UPDATE project_task_executions SET ended_at=1 WHERE id=?', (execution_id,))
        next_execution, next_source = self.execution(task_id, 2, reason='clarification')
        self.assertEqual(attempt, self.states.consume_delivery(next_execution, next_source, 'user2'))
        self.assertEqual(1, self.states.task(task_id)['attempt_count'])

    def test_three_consumed_business_attempts_are_hard_limit(self) -> None:
        """只容许首轮加两次修正，重启不重置计数。@return None。"""
        task_id = self.tasks[0]['id']
        for number in range(1, 5):
            execution_id, source_id = self.execution(task_id, number, reason='initial' if number == 1 else 'correction')
            if number < 4:
                self.states.consume_delivery(execution_id, source_id, f'user{number}')
            else:
                with self.assertRaises(ValueError):
                    self.states.consume_delivery(execution_id, source_id, 'user4')
            self.sql('UPDATE project_task_executions SET ended_at=1 WHERE id=?', (execution_id,))
        self.assertEqual(3, self.states.task(task_id)['attempt_count'])

    def test_budget_reservations_highwater_and_idempotent_settlement(self) -> None:
        """同一执行及quota新来源共用余额，结算重复不重复记账。@return None。"""
        task_id = self.tasks[0]['id']
        execution_id, source_id = self.execution(task_id, 1)
        segment = self.states.reserve_segment(source_id, 1, 'boot', 100.0)
        self.assertEqual(segment['id'], self.states.reserve_segment(source_id, 1, 'boot', 100.0)['id'])
        self.states.update_segment(segment['id'], 'boot', 55)
        self.states.update_segment(segment['id'], 'boot', 40)
        self.assertEqual(55, self.states.budget(task_id)['confirmed_sec'])
        self.states.update_segment(segment['id'], 'boot', 100, settled=True)
        self.states.update_segment(segment['id'], 'boot', 100, settled=True)
        self.assertEqual(1700, self.states.budget(task_id)['remaining_sec'])
        next_source = self.sql('INSERT INTO project_execution_sources(execution_id,quota_attempt,source,created_at) VALUES(?,1,?,1) RETURNING id',
            (execution_id, 'run:test1:1'))[0]['id']
        self.assertEqual(600, self.states.reserve_segment(next_source, 1, 'boot', 200)['reserved_sec'])
        self.assertEqual(1100, self.states.budget(task_id)['remaining_sec'])

    def test_uncertain_crash_tail_blocks_new_time(self) -> None:
        """未知尾段保留预留，跨boot不可清零并重领。@return None。"""
        task_id = self.tasks[0]['id']
        _, source_id = self.execution(task_id, 1)
        segment = self.states.reserve_segment(source_id, 1, 'old-boot', 100)
        self.states.update_segment(segment['id'], 'old-boot', 20, uncertain=True)
        budget = self.states.budget(task_id)
        self.assertEqual((20, 580, 1200, True), (budget['confirmed_sec'], budget['reserved_sec'], budget['remaining_sec'], budget['uncertain']))
        with self.assertRaises(ValueError):
            self.states.update_segment(segment['id'], 'new-boot', 21, settled=True)
        with self.assertRaises(ValueError):
            self.states.reserve_segment(source_id, 2, 'new-boot', 0)

    def test_review_attempt_response_and_task_three_layers(self) -> None:
        """逻辑评审跨Run共用180秒，同回答360秒，整任务720秒。@return None。"""
        task_id = self.tasks[0]['id']
        candidate_id, candidate_source = self.execution(task_id, 1)
        job_id = self.job(task_id, candidate_source)
        review_id, review_source = self.execution(task_id, 2, role='review', job_id=job_id, review_attempt=1)
        segment = self.states.reserve_segment(review_source, 1, 'boot', 100)
        self.states.update_segment(segment['id'], 'boot', 150, settled=True)
        resumed_source = self.sql('INSERT INTO project_execution_sources(execution_id,quota_attempt,source,created_at) VALUES(?,1,?,1) RETURNING id',
            (review_id, 'run:test2:1'))[0]['id']
        self.assertEqual(30, self.states.reserve_segment(resumed_source, 1, 'boot', 300)['reserved_sec'])
        self.assertEqual(0, self.states.budget(task_id, 'review', job_id=job_id, review_attempt=1)['slice_sec'])
        self.assertEqual(180, self.states.budget(task_id, 'review', job_id=job_id, review_attempt=2)['slice_sec'])
        self.assertEqual(1800, self.states.budget(task_id)['remaining_sec'])

    def test_repeat_schema_and_public_projection_keep_history(self) -> None:
        """重复建表不改变旧ID或内容，详情不含隐藏输入及会话身份。@return None。"""
        before = self.sql("SELECT name,seq FROM sqlite_sequence ORDER BY name")
        connection = self.manager.database()
        try:
            initialize_scenario_schema(connection)
            initialize_scenario_schema(connection)
        finally:
            connection.close()
        self.assertEqual(before, self.sql("SELECT name,seq FROM sqlite_sequence ORDER BY name"))
        detail = self.scenario_manager.instance(self.batch['instances'][0]['id'])
        serialized = json.dumps(detail)
        self.assertNotIn('rubric', serialized)
        self.assertNotIn('session_id', serialized)
        self.assertEqual(3, len(detail['scenarios'][0]['tasks']))

    def test_candidate_release_then_same_model_review_pass_without_code_checkpoint(self) -> None:
        """完整回答只续验收，释放双方后才通过，问答不接受代码。@return None。"""
        task_id = self.tasks[0]['id']
        self.states.refresh_readiness(self.tasks[0]['scenario_instance_id'])
        batch = self.sql('SELECT * FROM project_iteration_batches WHERE id=?',(self.batch['id'],))[0]
        account = self.sql('SELECT * FROM accounts WHERE id=1')[0]
        self.assertTrue(self.states._reserve_candidate(batch,account,task_id))
        run_id = self.launches[-1][0]
        config = self.configure_run(run_id)
        job_id = self.submit_reply(run_id,config,'这个模块的公开值为1。')
        self.assertEqual('waiting_release',self.sql('SELECT status FROM project_evaluation_jobs WHERE id=?',(job_id,))[0]['status'])
        self.assertEqual(1,len(self.launches))
        self.release_run(run_id)
        self.states._mechanical_job(job_id)
        job = self.sql('SELECT * FROM project_evaluation_jobs WHERE id=?',(job_id,))[0]
        self.assertEqual('review_ready',job['status'])
        self.assertTrue(self.states._reserve_review(batch,account,job))
        review_run = self.launches[-1][0]
        frozen = self.sql('SELECT claude_code_version,claude_effort_level,execution_model FROM runs WHERE id=?',(run_id,))[0]
        self.assertEqual(frozen,self.sql('SELECT claude_code_version,claude_effort_level,execution_model FROM runs WHERE id=?',(review_run,))[0])
        review_config = self.configure_run(review_run,review=True)
        package = json.loads(self.states._package_path(job_id).read_text())
        self.assertEqual('unit-fixture-model',package['resolved_model'])
        verdict = {key:package[key] for key in ('job_id','task_id','turn_no','response_digest','basis_digest')}
        verdict.update(decision='pass',outcome='resolved',branch_id=None,criteria=[{'id':'fact','status':'satisfied',
            'reason':'源码与回答吻合','evidence':['example.py:1']}],feedback_codes=[])
        self.submit_reply(review_run,review_config,json.dumps(verdict))
        self.assertEqual('evaluating',self.states.task(task_id)['status'])
        self.release_run(review_run)
        self.assertEqual('passed',self.states.task(task_id)['status'])
        self.assertIsNone(self.states.task(task_id)['accepted_checkpoint_digest'])
        self.assertEqual(1,self.states.task(task_id)['attempt_count'])
        attempt = self.sql('SELECT ended_at,result FROM project_task_attempts WHERE task_id=?',(task_id,))[0]
        self.assertIsNotNone(attempt['ended_at'])
        self.assertEqual('passed',attempt['result'])
        self.assertEqual(2,len(self.launches))
        usage = self.states.usage(self.batch['instances'][0]['id'])['tasks'][0]['roles']
        self.assertEqual((7,11,1),(usage['candidate']['input_tokens'],usage['candidate']['output_tokens'],usage['candidate']['requests']))
        self.assertEqual(1,usage['review']['requests'])
        self.assertTrue(usage['candidate']['complete'])
        artifact = self.states.artifacts(self.batch['instances'][0]['id'],task_id)
        self.assertEqual('这个模块的公开值为1。',artifact['answer'])
        self.assertFalse(artifact['code_accepted'])

    def test_complete_candidate_restart_only_evaluation_and_stale_result_ignored(self) -> None:
        """重启完整候选不重问，停止后迟到通过不能推进。@return None。"""
        task_id = self.tasks[0]['id']
        self.states.refresh_readiness(self.tasks[0]['scenario_instance_id'])
        batch = self.sql('SELECT * FROM project_iteration_batches WHERE id=?',(self.batch['id'],))[0]
        self.states._reserve_candidate(batch,self.sql('SELECT * FROM accounts WHERE id=1')[0],task_id)
        run_id = self.launches[-1][0]
        self.submit_reply(run_id,self.configure_run(run_id),'原版行为说明。')
        self.states.recover(lambda rid:None)
        execution = self.sql('SELECT e.*,r.status AS run_status,r.error AS run_error FROM project_task_executions e JOIN runs r ON r.id=e.run_id WHERE run_id=?',(run_id,))[0]
        source = self.sql('SELECT * FROM project_execution_sources WHERE execution_id=?',(execution['id'],))[0]
        self.states._settle_execution(batch,execution,source)
        job = self.sql('SELECT * FROM project_evaluation_jobs')[0]
        self.assertEqual('queued',job['status'])
        self.assertEqual(1,len(self.launches))
        self.scenario_manager.transition(self.batch['id'],'stop')
        self.states._apply_result(job,{'decision':'pass','outcome':'resolved','feedback_codes':[]})
        self.assertNotEqual('passed',self.states.task(task_id)['status'])

    def test_cross_instance_artifact_path_is_rejected(self) -> None:
        """nested任务、历史文件及评测版本都核对归属。@return None。"""
        with self.assertRaises(ValueError):
            self.states.artifacts(999,self.tasks[0]['id'])
        with self.assertRaises(ValueError):
            self.states.artifact_file(self.batch['instances'][0]['id'],self.tasks[0]['id'],'../../profiles/secret')

    def test_quota_after_capture_restart_finishes_release_and_only_evaluates(self) -> None:
        """额度等待写入后崩溃，重启补严格释放，不再发模型输入。@return None。"""
        task_id = self.tasks[0]['id']
        self.states.refresh_readiness(self.tasks[0]['scenario_instance_id'])
        batch = self.sql('SELECT * FROM project_iteration_batches WHERE id=?',(self.batch['id'],))[0]
        self.states._reserve_candidate(batch,self.sql('SELECT * FROM accounts WHERE id=1')[0],task_id)
        run_id = self.launches[-1][0]
        job_id = self.submit_reply(run_id,self.configure_run(run_id),'完整回答已生成。')
        self.sql("UPDATE runs SET status='quota_wait' WHERE id=?",(run_id,))
        cleanups = []
        self.states.recover(cleanups.append)
        self.assertEqual([run_id],cleanups)
        self.assertTrue(self.states.finish_captured_quota(run_id))
        execution = self.sql('SELECT e.*,r.status AS run_status,r.error AS run_error FROM project_task_executions e JOIN runs r ON r.id=e.run_id WHERE run_id=?',(run_id,))[0]
        source = self.sql('SELECT * FROM project_execution_sources WHERE execution_id=?',(execution['id'],))[0]
        self.states._settle_execution(batch,execution,source)
        self.states._mechanical_job(job_id)
        self.assertEqual('review_ready',self.sql('SELECT status FROM project_evaluation_jobs WHERE id=?',(job_id,))[0]['status'])
        self.assertEqual(1,len(self.launches))
        self.assertEqual(1,self.states.task(task_id)['attempt_count'])
        self.assertEqual(0,self.sql('SELECT quota_attempt FROM runs WHERE id=?',(run_id,))[0]['quota_attempt'])

    def test_incomplete_quota_strict_cleanup_error_blocks_parent(self) -> None:
        """尚未回答的额度来源清理失败时，也不能继续模型新代。@return None。"""
        task_id = self.tasks[0]['id']
        execution_id,source_id = self.execution(task_id,1)
        self.sql("UPDATE runs SET status='quota_wait' WHERE id='test1'")
        self.sql("UPDATE project_execution_sources SET execution_error='测试严格清理失败' WHERE id=?",(source_id,))
        self.assertTrue(self.states.finish_captured_quota('test1'))
        self.assertEqual('blocked',self.sql('SELECT status FROM project_iteration_batches WHERE id=?',(self.batch['id'],))[0]['status'])
        self.assertEqual('blocked',self.states.task(task_id)['status'])
        self.assertIsNotNone(self.sql('SELECT ended_at FROM project_task_executions WHERE id=?',(execution_id,))[0]['ended_at'])

    def test_disclosure_review_keeps_original_question_and_previous_answer(self) -> None:
        """补充材料后的冻结评审含首问、前答和材料，后续DB变化不改输入。@return None。"""
        task_id = self.tasks[0]['id']
        definition=json.loads(self.tasks[0]['definition_json'])
        definition['branches']=[{'id':'details','when':'必要信息不足','materials':['disclosure/details.txt'],
            'setup':[{'source':'disclosure/details.txt','target':'app/context.txt'}]}]
        self.sql('UPDATE project_scenario_tasks SET definition_json=? WHERE id=?',(json.dumps(definition),task_id))
        self.states.refresh_readiness(self.tasks[0]['scenario_instance_id'])
        batch=self.sql('SELECT * FROM project_iteration_batches WHERE id=?',(self.batch['id'],))[0]
        account=self.sql('SELECT * FROM accounts WHERE id=1')[0]
        self.states._reserve_candidate(batch,account,task_id)
        first=self.launches[-1][0]
        job_id=self.submit_reply(first,self.configure_run(first),'请补充实际调用材料。')
        self.release_run(first)
        self.states._mechanical_job(job_id)
        self.states._apply_result(self.sql('SELECT * FROM project_evaluation_jobs WHERE id=?',(job_id,))[0],
            {'decision':'disclose','branch_id':'details','outcome':None,'feedback_codes':[]})
        self.sql('UPDATE project_evaluation_jobs SET created_at=1e20 WHERE id=?',(job_id,))
        self.states._reserve_candidate(batch,account,task_id)
        second=self.launches[-1][0]
        configuration=self.configure_run(second)
        context_path=self.data/self.states.task(task_id)['workspace_relative']/'app/context.txt'
        self.assertEqual('隐藏材料',context_path.read_text())
        next_job=self.submit_reply(second,configuration,'补充材料说明当前行为正确。')
        self.release_run(second)
        self.states._mechanical_job(next_job)
        package=json.loads(self.states._package_path(next_job).read_text())
        self.assertEqual(['user','assistant','user'],[item['role'] for item in package['conversation']])
        self.assertEqual(definition['prompt'],package['question'])
        self.assertIn('隐藏材料',package['conversation'][-1]['content'])
        self.assertEqual(1,self.states.task(task_id)['attempt_count'])
        self.assertIsNone(self.sql('SELECT ended_at FROM project_task_attempts WHERE task_id=?',(task_id,))[0]['ended_at'])
        self.sql("UPDATE project_task_deliveries SET prompt='后来篡改' WHERE task_id=?",(task_id,))
        job=self.sql('SELECT * FROM project_evaluation_jobs WHERE id=?',(next_job,))[0]
        self.assertEqual(package['conversation'],self.states._package(job,self.states.task(task_id))['conversation'])
        self.states._block_evaluation(job,'合法uncertain，不自动重评')
        self.assertEqual('blocked',self.sql('SELECT result FROM project_task_attempts WHERE task_id=?',(task_id,))[0]['result'])
        context_path.write_text('后续半成品不能被重复投放覆盖')
        self.states._prepare_inputs(self.states.task(task_id))
        self.assertEqual('后续半成品不能被重复投放覆盖',context_path.read_text())

    def test_newly_activated_task_does_not_starve_current_plan_member(self) -> None:
        """分支激活较早任务后，仍先执行开放计划成员，不永久选错任务。@return None。"""
        first,activated,last=self.tasks
        self.sql('UPDATE project_scenario_tasks SET selected=0 WHERE id=?',(activated['id'],))
        self.states.refresh_readiness(first['scenario_instance_id'])
        batch=self.sql('SELECT * FROM project_iteration_batches WHERE id=?',(self.batch['id'],))[0]
        account=self.sql('SELECT * FROM accounts WHERE id=1')[0]
        self.states._reserve_candidate(batch,account,first['id'])
        run_id=self.launches[-1][0]
        self.sql('UPDATE project_task_executions SET ended_at=1 WHERE run_id=?',(run_id,))
        self.sql("UPDATE runs SET status='success',ended_at=1 WHERE id=?",(run_id,))
        self.sql("UPDATE project_scenario_tasks SET status='passed' WHERE id=?",(first['id'],))
        self.sql("UPDATE project_scenario_tasks SET selected=1,status='ready' WHERE id=?",(activated['id'],))
        self.states.drive(batch,account)
        self.assertEqual(last['id'],self.states.context(self.launches[-1][0])['scenario_task_id'])
        self.assertEqual('ready',self.states.task(activated['id'])['status'])

    def test_local_terminal_rotation_is_idempotent_and_keeps_independent_task_ready(self) -> None:
        """任务耗尽只阻塞真正后继，访问轮换不重复移到队尾。@return None。"""
        instance_id=self.batch['instances'][0]['id']
        self.sql('UPDATE project_instances SET in_pool=1 WHERE id=?',(instance_id,))
        self.states._task_status(self.tasks[0]['id'],'exhausted','累计时间已用尽')
        self.states.refresh_readiness(self.tasks[0]['scenario_instance_id'])
        instance=self.sql('SELECT in_pool,visit_order FROM project_instances WHERE id=?',(instance_id,))[0]
        self.assertEqual(0,instance['in_pool'])
        self.assertEqual(['exhausted','ready','blocked'],[row['status'] for row in self.sql('SELECT status FROM project_scenario_tasks ORDER BY id')])
        self.states._task_status(self.tasks[0]['id'],'exhausted','累计时间已用尽')
        self.assertEqual(instance,self.sql('SELECT in_pool,visit_order FROM project_instances WHERE id=?',(instance_id,))[0])

    def test_file_only_delivery_is_in_frozen_review_package(self) -> None:
        """回答仅指向已交付文件时，评审仍能读到实际代码及候选摘要。@return None。"""
        task_id=self.tasks[0]['id']
        definition=json.loads(self.tasks[0]['definition_json'])
        definition['allowed_paths']=['app']
        self.sql('UPDATE project_scenario_tasks SET definition_json=? WHERE id=?',(json.dumps(definition),task_id))
        self.states.refresh_readiness(self.tasks[0]['scenario_instance_id'])
        batch=self.sql('SELECT * FROM project_iteration_batches WHERE id=?',(self.batch['id'],))[0]
        self.states._reserve_candidate(batch,self.sql('SELECT * FROM accounts WHERE id=1')[0],task_id)
        run_id=self.launches[-1][0]
        configuration=self.configure_run(run_id)
        workspace=self.data/self.states.task(task_id)['workspace_relative']
        (workspace/'app').mkdir()
        (workspace/'app/example.py').write_text('VALUE = 1\n')
        job_id=self.submit_reply(run_id,configuration,'示例已放在app/example.py。')
        self.release_run(run_id)
        self.states._mechanical_job(job_id)
        package=json.loads(self.states._package_path(job_id).read_text())
        self.assertEqual('VALUE = 1\n',package['candidate_files']['app/example.py']['text'])
        self.assertFalse(package['candidate_files']['app/example.py']['binary'])
        self.assertEqual(self.sql('SELECT candidate_digest FROM project_evaluation_jobs WHERE id=?',(job_id,))[0]['candidate_digest'],package['candidate_digest'])

    def test_complete_review_quota_restart_applies_saved_verdict_without_repeating_model(self) -> None:
        """评审完整输出后遇quota并重启，只补释放和接受，不再重评。@return None。"""
        task_id=self.tasks[0]['id']
        self.states.refresh_readiness(self.tasks[0]['scenario_instance_id'])
        batch=self.sql('SELECT * FROM project_iteration_batches WHERE id=?',(self.batch['id'],))[0]
        account=self.sql('SELECT * FROM accounts WHERE id=1')[0]
        self.states._reserve_candidate(batch,account,task_id)
        candidate=self.launches[-1][0]
        job_id=self.submit_reply(candidate,self.configure_run(candidate),'实际公开值为1。')
        self.release_run(candidate)
        self.states._mechanical_job(job_id)
        self.states._reserve_review(batch,account,self.sql('SELECT * FROM project_evaluation_jobs WHERE id=?',(job_id,))[0])
        review=self.launches[-1][0]
        package=json.loads(self.states._package_path(job_id).read_text())
        verdict={key:package[key] for key in ('job_id','task_id','turn_no','response_digest','basis_digest')}
        verdict.update(decision='pass',outcome='resolved',branch_id=None,criteria=[{'id':'fact','status':'satisfied',
            'reason':'符合冻结事实','evidence':['example.py:1']}],feedback_codes=[])
        self.submit_reply(review,self.configure_run(review,review=True),json.dumps(verdict))
        self.sql("UPDATE runs SET status='quota_wait' WHERE id=?",(review,))
        cleanups=[]
        self.states.recover(cleanups.append)
        self.assertEqual([review],cleanups)
        self.assertTrue(self.states.finish_captured_quota(review))
        execution=self.sql('SELECT e.*,r.status AS run_status,r.error AS run_error FROM project_task_executions e JOIN runs r ON r.id=e.run_id WHERE run_id=?',(review,))[0]
        source=self.sql('SELECT * FROM project_execution_sources WHERE execution_id=?',(execution['id'],))[0]
        self.states._settle_execution(batch,execution,source)
        self.assertEqual('passed',self.states.task(task_id)['status'])
        self.assertEqual(2,len(self.launches))
        self.assertEqual((1,0),(self.states.task(task_id)['attempt_count'],self.sql('SELECT quota_attempt FROM runs WHERE id=?',(review,))[0]['quota_attempt']))

    def test_modify_with_delivery_review_accepts_code_only_after_review_release(self) -> None:
        """工程任务的必要语义交付未评完时，即使程序通过也不接受代码。@return None。"""
        task_id=self.tasks[0]['id']
        definition=json.loads(self.tasks[0]['definition_json'])
        definition.update(kind='modify',allowed_paths=['app'])
        definition['evaluation'].update(native='verification/native.json',semantic=True)
        self.sql("UPDATE project_scenario_tasks SET kind='modify',definition_json=? WHERE id=?",(json.dumps(definition),task_id))
        project=self.scenario_manager.library.projects['example']
        write_document(project.root/'verification/native.json',{'script':'verification/native.py','args':[],
            'python_paths':['app'],'expected':{'ok':True}})
        verifier=Mock()
        verifier.verify_native.return_value={'status':'passed'}
        self.scenario_manager.verifier=verifier
        self.states.refresh_readiness(self.tasks[0]['scenario_instance_id'])
        batch=self.sql('SELECT * FROM project_iteration_batches WHERE id=?',(self.batch['id'],))[0]
        account=self.sql('SELECT * FROM accounts WHERE id=1')[0]
        self.states._reserve_candidate(batch,account,task_id)
        candidate=self.launches[-1][0]
        configuration=self.configure_run(candidate)
        workspace=self.data/self.states.task(task_id)['workspace_relative']
        (workspace/'app').mkdir()
        (workspace/'app/output.txt').write_text('已交付业务代码')
        job_id=self.submit_reply(candidate,configuration,'已经实现并提供用户测试。')
        self.release_run(candidate)
        self.states._mechanical_job(job_id)
        self.assertEqual('evaluating',self.states.task(task_id)['status'])
        self.assertIsNone(self.states.task(task_id)['accepted_checkpoint_digest'])
        job=self.sql('SELECT * FROM project_evaluation_jobs WHERE id=?',(job_id,))[0]
        self.assertEqual('review_ready',job['status'])
        self.states._reserve_review(batch,account,job)
        review=self.launches[-1][0]
        package=json.loads(self.states._package_path(job_id).read_text())
        verdict={key:package[key] for key in ('job_id','task_id','turn_no','response_digest','basis_digest')}
        verdict.update(decision='pass',outcome='resolved',branch_id=None,criteria=[{'id':'fact','status':'satisfied',
            'reason':'交付与程序事实一致','evidence':['example.py:1']}],feedback_codes=[])
        self.submit_reply(review,self.configure_run(review,review=True),json.dumps(verdict))
        self.assertIsNone(self.states.task(task_id)['accepted_checkpoint_digest'])
        self.release_run(review)
        self.assertEqual(job['candidate_digest'],self.states.task(task_id)['accepted_checkpoint_digest'])

    def test_code_dependency_restores_accepted_input_and_preserves_failed_workspace(self) -> None:
        """代码依赖跳过失败半成品，封存现场且同任务接续不再重置。@return None。"""
        for task in self.tasks:
            definition=json.loads(task['definition_json'])
            definition.update(kind='modify',allowed_paths=['example.py'])
            definition['evaluation'].update(native='verification/native.json',semantic=False)
            if task['task_key']=='Q3':
                definition['requires']=[{'task_id':'Q1','artifact':'code'}]
            self.sql("UPDATE project_scenario_tasks SET kind='modify',definition_json=? WHERE id=?",(json.dumps(definition),task['id']))
        project=self.scenario_manager.library.projects['example']
        write_document(project.root/'verification/native.json',{'script':'verification/native.py','args':[],
            'python_paths':['.'],'expected':{'ok':True}})
        verifier=Mock()
        verifier.verify_native.side_effect=[{'status':'passed'},*({'status':'failed'} for _ in range(3))]
        self.scenario_manager.verifier=verifier
        batch=self.sql('SELECT * FROM project_iteration_batches WHERE id=?',(self.batch['id'],))[0]
        account=self.sql('SELECT * FROM accounts WHERE id=1')[0]
        for task_id,value in [(self.tasks[0]['id'],2),*((self.tasks[1]['id'],999) for _ in range(3))]:
            self.states.refresh_readiness(self.tasks[0]['scenario_instance_id'])
            self.assertTrue(self.states._reserve_candidate(batch,account,task_id))
            run_id=self.launches[-1][0]
            configuration=self.configure_run(run_id)
            workspace=self.data/self.states.task(task_id)['workspace_relative']
            (workspace/'example.py').write_text(f'VALUE = {value}\n')
            job_id=self.submit_reply(run_id,configuration,'已完成本次修改。')
            self.release_run(run_id)
            self.states._mechanical_job(job_id)
        self.assertEqual(('passed','failed'),tuple(self.states.task(task['id'])['status'] for task in self.tasks[:2]))
        self.assertEqual('VALUE = 999\n',(workspace/'example.py').read_text())
        task_id=self.tasks[2]['id']
        self.states.refresh_readiness(self.tasks[0]['scenario_instance_id'])
        self.states._close_finished(batch)
        self.assertTrue(self.states._reserve_candidate(batch,account,task_id))
        self.configure_run(self.launches[-1][0])
        self.assertEqual('VALUE = 2\n',(workspace/'example.py').read_text())
        marker=self.data/'project-artifacts/task-inputs'/str(task_id)/'code-dependency.json'
        binding=json.loads(marker.read_text())
        self.assertEqual(self.states.task(self.tasks[0]['id'])['accepted_checkpoint_digest'],binding['base_checkpoint_digest'])
        saved=self.data/binding['saved_relative']
        self.assertEqual('VALUE = 999\n',(saved/'example.py').read_text())
        (workspace/'example.py').write_text('VALUE = 3\n')
        self.states._prepare_inputs(self.states.task(task_id))
        self.assertEqual('VALUE = 3\n',(workspace/'example.py').read_text())
        binding['state']='replacing'
        write_document(marker,binding)
        with self.assertRaisesRegex(ValueError,'交接中断'):
            self.states._prepare_inputs(self.states.task(task_id))
        self.assertEqual('VALUE = 3\n',(workspace/'example.py').read_text())

    def test_incompatible_code_dependencies_do_not_guess_a_merge(self) -> None:
        """互不继承的已接受版本受阻，共同继承链才可准备输入。@return None。"""
        seed=self.data/'dependency-seed'
        seed.mkdir()
        snapshots=[]
        for value in (1,2):
            (seed/'example.py').write_text(f'VALUE = {value}\n')
            snapshot=snapshot_tree(seed,self.scenario_manager.objects)
            write_document(self.scenario_manager.manifests/(snapshot['digest']+'.json'),snapshot)
            snapshots.append(snapshot['digest'])
        jobs=[]
        for index,task in enumerate(self.tasks[:2]):
            _,source=self.execution(task['id'],index+1)
            job=self.job(task['id'],source)
            self.sql("UPDATE project_scenario_tasks SET kind='modify',status='passed',accepted_checkpoint_digest=? WHERE id=?",(snapshots[index],task['id']))
            self.sql("UPDATE project_evaluation_jobs SET status='passed',candidate_digest=?,evidence_json=? WHERE id=?",
                (snapshots[index],json.dumps({'parent_code_digest':None}),job))
            jobs.append(job)
        task=self.states.task(self.tasks[2]['id'])
        definition=json.loads(task['definition_json'])
        definition['requires']=[{'task_id':key,'artifact':'code'} for key in ('Q1','Q2')]
        with self.assertRaisesRegex(ValueError,'同一已接受继承链'):
            self.states._bind_code_dependencies(task,definition)
        workspace=self.data/'dependency-workspace'
        workspace.mkdir()
        (workspace/'example.py').write_text('VALUE = 999\n')
        self.sql('UPDATE project_scenario_instances SET workspace_relative=? WHERE id=?',
            (str(workspace.relative_to(self.data)),task['scenario_instance_id']))
        self.sql('UPDATE project_evaluation_jobs SET evidence_json=? WHERE id=?',
            (json.dumps({'parent_code_digest':snapshots[0],'parent_code_job_id':jobs[0]}),jobs[1]))
        self.states._bind_code_dependencies(self.states.task(task['id']),definition)
        self.assertEqual('VALUE = 2\n',(workspace/'example.py').read_text())

    def test_new_task_without_code_dependency_excludes_unaccepted_changes(self) -> None:
        """独立任务恢复确定基线与入口材料，不能夹带前任务未接受修改。@return None。"""
        scenario_id=self.tasks[0]['scenario_instance_id']
        scenario=self.sql('SELECT definition_json FROM project_scenario_instances WHERE id=?',(scenario_id,))[0]
        definition=json.loads(scenario['definition_json'])
        project=self.scenario_manager.library.projects['example']
        (project.root/'materials').mkdir()
        (project.root/'materials/entry.txt').write_text('入口材料')
        definition['entries'][0]['setup']=[{'source':'materials/entry.txt','target':'app/input.txt'}]
        self.sql('UPDATE project_scenario_instances SET definition_json=? WHERE id=?',(json.dumps(definition),scenario_id))
        self.states.refresh_readiness(scenario_id)
        batch=self.sql('SELECT * FROM project_iteration_batches WHERE id=?',(self.batch['id'],))[0]
        account=self.sql('SELECT * FROM accounts WHERE id=1')[0]
        self.assertTrue(self.states._reserve_candidate(batch,account,self.tasks[0]['id']))
        self.configure_run(self.launches[-1][0])
        workspace=self.data/self.states.task(self.tasks[0]['id'])['workspace_relative']
        (workspace/'example.py').write_text('VALUE = 999\n')
        (workspace/'app/unfinished.py').write_text('未接受半成品')
        self.states._prepare_inputs(self.states.task(self.tasks[1]['id']))
        self.assertEqual('VALUE = 1\n',(workspace/'example.py').read_text())
        self.assertEqual('入口材料',(workspace/'app/input.txt').read_text())
        self.assertFalse((workspace/'app/unfinished.py').exists())
        marker=self.data/'project-artifacts/task-inputs'/str(self.tasks[1]['id'])/'code-dependency.json'
        binding=json.loads(marker.read_text())
        saved=self.data/binding['saved_relative']
        self.assertEqual('VALUE = 999\n',(saved/'example.py').read_text())
        self.assertTrue((saved/'app/unfinished.py').is_file())
        (workspace/'app/input.txt').write_text('本任务半成品')
        self.states._prepare_inputs(self.states.task(self.tasks[1]['id']))
        self.assertEqual('本任务半成品',(workspace/'app/input.txt').read_text())

    def test_same_bytes_revert_does_not_join_distinct_code_branches(self) -> None:
        """后来的同字节回退不得篡改早期接受作业的父链。@return None。"""
        root_id=self.sql("INSERT INTO project_scenario_tasks(scenario_instance_id,task_key,kind,definition_json,selected,status,next_prompt,created_at,updated_at) "
            "VALUES(?,'ROOT','modify','{}',1,'passed','输入',1,1) RETURNING id",(self.tasks[0]['scenario_instance_id'],))[0]['id']
        jobs=[]
        # ROOT→A 与 ROOT→B 分叉，C 继承 A 后回退为与 ROOT 相同的内容。
        for number,(task_id,digest,parent) in enumerate([(root_id,'d0',None),(self.tasks[0]['id'],'d1',0),
                (self.tasks[1]['id'],'d2',0),(self.tasks[2]['id'],'d0',1)],1):
            _,source=self.execution(task_id,number)
            job=self.job(task_id,source)
            self.sql("UPDATE project_scenario_tasks SET kind='modify',status='passed',accepted_checkpoint_digest=? WHERE id=?",(digest,task_id))
            self.sql("UPDATE project_evaluation_jobs SET status='passed',candidate_digest=?,evidence_json=? WHERE id=?",
                (digest,json.dumps({'parent_code_digest':None if parent is None else ('d0' if parent==0 else 'd1'),
                    'parent_code_job_id':None if parent is None else jobs[parent]}),job))
            jobs.append(job)
        definition=json.loads(self.tasks[2]['definition_json'])
        definition['requires']=[{'task_id':key,'artifact':'code'} for key in ('Q1','Q2')]
        with self.assertRaisesRegex(ValueError,'同一已接受继承链'):
            self.states._bind_code_dependencies(self.states.task(self.tasks[2]['id']),definition)

    def test_review_model_drift_is_review_error_without_business_retry(self) -> None:
        """实际评审模型漂移时，即使结论JSON合法也不接受或惩罚候选。@return None。"""
        task_id=self.tasks[0]['id']
        self.states.refresh_readiness(self.tasks[0]['scenario_instance_id'])
        batch=self.sql('SELECT * FROM project_iteration_batches WHERE id=?',(self.batch['id'],))[0]
        account=self.sql('SELECT * FROM accounts WHERE id=1')[0]
        self.states._reserve_candidate(batch,account,task_id)
        candidate=self.launches[-1][0]
        job_id=self.submit_reply(candidate,self.configure_run(candidate),'实际值为1。')
        self.release_run(candidate)
        self.states._mechanical_job(job_id)
        self.states._reserve_review(batch,account,self.sql('SELECT * FROM project_evaluation_jobs WHERE id=?',(job_id,))[0])
        review=self.launches[-1][0]
        package=json.loads(self.states._package_path(job_id).read_text())
        verdict={key:package[key] for key in ('job_id','task_id','turn_no','response_digest','basis_digest')}
        verdict.update(decision='pass',outcome='resolved',branch_id=None,criteria=[{'id':'fact','status':'satisfied',
            'reason':'JSON合规但实际模型不同','evidence':['example.py:1']}],feedback_codes=[])
        self.submit_reply(review,self.configure_run(review,review=True),json.dumps(verdict),model='unexpected-model')
        self.release_run(review)
        job=self.sql('SELECT * FROM project_evaluation_jobs WHERE id=?',(job_id,))[0]
        self.assertEqual('review_ready',job['status'])
        self.assertIn('实际模型',json.loads(job['review_result_json'])['protocol_error'])
        self.assertEqual(('evaluating',1),(self.states.task(task_id)['status'],self.states.task(task_id)['attempt_count']))
