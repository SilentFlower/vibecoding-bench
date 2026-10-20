"""同会话计划的真实 SQLite、文件、独立行为验收及驱动握手回归。"""
import json
import os
import sqlite3
import threading
import time
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from unittest.mock import patch
from unittest.mock import Mock

import main
from project_iteration import PROJECT_SCHEMA
from project_plans import initialize_plan_schema
from test_project_iterations import ProjectIterationFixture, ROOT


class ProjectPlanTests(ProjectIterationFixture):
    """用冻结会话字节证据核对计划进度，不以模型自述冒充独立验收。"""

    def setUp(self) -> None:
        """启用可观测的定向控制替身；真实进程树另由 Docker 场景验证。@return None。"""
        super().setUp()
        self.controls = []
        self.gate = {'allowed':True}
        self.manager.plans.control = lambda run,epoch,op:self.control_fixture(run,epoch,op)
        self.manager.plans.admission = lambda account:self.gate
        specification = spec_from_file_location('plan_driver_fixture',ROOT/'images/account/project_plan.py')
        self.driver = module_from_spec(specification)
        import sys
        with patch.dict(sys.modules,{'task_followups':self.manager.plans.dialogue}):
            specification.loader.exec_module(self.driver)

    def control_fixture(self, run: str, epoch: int, operation: str) -> dict:
        """记录定向控制的归属。@param run 运行。@param epoch 代次。@param operation 操作。@return 暂停证明。"""
        self.controls.append((run,epoch,operation))
        return {'source':f'run:{run}:{epoch}','frozen':operation=='freeze','resumed':operation=='resume'}

    def begin_plan(self, keys=None, **policy) -> dict:
        """创建真实 schema 2 批次。@param keys 项目。@param policy 策略。@return 批次。"""
        batch = self.manager.create_batch(1,'多步计划',keys or ['project-001'],policy)
        self.manager.transition(batch['id'],'start')
        self.manager.tick()
        return self.manager.batch(batch['id'])

    def configure(self, run_id: str, epoch: int = 0) -> dict:
        """在实际发布目录后冻结驱动配置。@param run_id 运行。@param epoch 额度代次。@return 本机测试路径配置。"""
        workspace = self.materialize(run_id)
        context = self.manager.run_context(run_id)
        native = self.data/'environments/environment-1/home/.claude/projects'/context['workspace_relative'].replace('/','-')
        native.mkdir(parents=True,exist_ok=True)
        runtime = self.data/'runtime'/run_id
        controls = self.data/'controls'/f'{run_id}-{epoch}'
        runtime.mkdir(parents=True,exist_ok=True)
        controls.mkdir(parents=True,exist_ok=True)
        cwd = '/home/node/projects/'+workspace.name
        config = self.manager.plans.execution_configuration(run_id,f'run:{run_id}:{epoch}',epoch,native,
            runtime/'request.json',controls/'decision.json',cwd)
        config.update(native_directory=str(native),request_file=str(runtime/'request.json'),
            decision_file=str(controls/'decision.json'),state_file=str(runtime/'project-plan-state.json'))
        self.driver.process('begin',config)
        return config

    def reply(self, run_id: str, config: dict, *, solve: bool = True, tokens: int = 11) -> None:
        """模拟原生输入与最终回复；可选择实现或失败候选。@param run_id 运行。@param config 会话。@param solve 实现业务。@param tokens 输出量。@return None。"""
        if solve:
            context = self.manager.run_context(run_id)
            self.solve_fixture(run_id,self.data/context['workspace_relative'])
        execution = self.sql('SELECT * FROM project_plan_executions WHERE run_id=?',(run_id,))[0]
        attempt = self.sql('SELECT * FROM project_step_attempts WHERE id=?',(execution['current_attempt_id'],))[0]
        path = Path(config['native_directory'])/(config['session_id']+'.jsonl')
        sequence = execution['phase_seq']
        records = [
            {'type':'user','uuid':f'u-{run_id}-{sequence}','message':{'role':'user','content':attempt['expected_prompt']}},
            {'type':'assistant','uuid':f'a-{run_id}-{sequence}','parentUuid':f'u-{run_id}-{sequence}',
                'message':{'id':f'response-{run_id}-{sequence}','role':'assistant','content':'Completed the current step.',
                    'stop_reason':'end_turn','usage':{'input_tokens':7,'output_tokens':tokens}}},
        ]
        with path.open('a') as stream:
            for record in records:
                stream.write(json.dumps(record)+'\n')

    def verify_step(self, run_id: str, config: dict, *, solve: bool = True, tokens: int = 11) -> dict:
        """让真实驱动等待与独立推进器并行交接。@param run_id 运行。@param config 会话。@param solve 实现业务。@param tokens 输出量。@return 决定。"""
        self.reply(run_id,config,solve=solve,tokens=tokens)
        results,errors = [],[]

        def advance():
            try:
                results.append(self.driver.process('advance',config,wait_seconds=8))
            except Exception as error:
                errors.append(error)

        thread = threading.Thread(target=advance)
        thread.start()
        deadline = time.monotonic()+5
        while not Path(config['request_file']).exists() and time.monotonic()<deadline:
            time.sleep(0.01)
        self.manager.tick()
        thread.join(timeout=9)
        self.assertFalse(thread.is_alive())
        if errors:
            raise errors[0]
        self.assertEqual(1,len(results))
        if results[0]['action']=='send':
            self.driver.process('sent',config)
            Path(config['request_file']).unlink(missing_ok=True)
        return results[0]

    def partial_input(self, run_id: str, config: dict) -> None:
        """记录已消费但尚无最终回复的当前步骤。@param run_id 运行。@param config 会话。@return None。"""
        execution = self.sql('SELECT * FROM project_plan_executions WHERE run_id=?',(run_id,))[0]
        attempt = self.sql('SELECT * FROM project_step_attempts WHERE id=?',(execution['current_attempt_id'],))[0]
        path = Path(config['native_directory'])/(config['session_id']+'.jsonl')
        previous = self.manager.plans.dialogue.read_dialogue(path)[-1]['id']
        with path.open('a') as stream:
            stream.write(json.dumps({'type':'user','uuid':f"partial-{run_id}-{execution['phase_seq']}",
                'parentUuid':previous,'message':{'role':'user','content':attempt['expected_prompt']}})+'\n')

    def test_same_run_two_steps_and_usage_boundaries(self) -> None:
        """同 Run／session 通过两步，中间单独检查点，输出统计不重复。@return None。"""
        batch = self.begin_plan()
        run_id = self.launches[-1][0]
        config = self.configure(run_id)
        first = self.verify_step(run_id,config,tokens=11)
        self.assertEqual('send',first['action'])
        instance = self.manager.instance(batch['instances'][0]['id'])
        self.assertEqual(1,instance['next_step_index'])
        self.assertEqual(1,instance['plans'][0]['completed_steps'])
        self.assertEqual({run_id},{attempt['run_id'] for attempt in instance['attempts']})
        self.assertEqual('complete',self.verify_step(run_id,config,tokens=29)['action'])
        self.end_run(run_id)
        self.manager.transition(batch['id'],'pause')
        self.manager.tick()
        instance = self.manager.instance(instance['id'])
        usages = [self.manager.step_usage(attempt['id'],lambda usage:usage['input_tokens']) for attempt in instance['attempts']]
        self.assertEqual([11,29],[usage['tokens_out'] for usage in usages])
        self.assertEqual(40,sum(usage['tokens_out'] for usage in usages))
        self.assertEqual(2,instance['next_step_index'])
        self.assertEqual('completed',instance['plans'][0]['status'])
        self.assertEqual([(run_id,0,'freeze'),(run_id,0,'resume')]*2,self.controls)

    def test_strict_policy_and_api_defaults_without_side_effects(self) -> None:
        """非法参数不创建批次，API 省略并发按真实容量默认而非保留旧单步模式。@return None。"""
        invalid = [
            {'concurrency':True},{'concurrency':'2'},{'concurrency':1.5},{'concurrency':3},
            {'concurrency':2,'active_projects':1},{'active_projects':0},{'steps_per_plan':0},
            {'rotation_steps':999},{'timeout_sec':59},{'interval_min_sec':30,'interval_max_sec':10},
        ]
        for policy in invalid:
            with self.subTest(policy=policy),self.assertRaises(ValueError):
                self.manager.create_batch(1,'invalid',['project-001','project-002'],policy)
        self.assertEqual(0,self.sql('SELECT COUNT(*) AS n FROM project_iteration_batches')[0]['n'])
        from fastapi.testclient import TestClient
        with patch.object(main,'project_iterations',self.manager):
            client = TestClient(main.app)
            self.assertEqual(422,client.post('/api/project-iteration-batches',json={
                'account_id':1,'project_keys':['project-001'],'steps_per_plan':True}).status_code)
            response = client.post('/api/project-iteration-batches',json={'account_id':1,'project_keys':['project-001']})
        self.assertEqual(200,response.status_code)
        self.assertEqual(2,response.json()['policy']['schema'])
        self.assertEqual(1,response.json()['policy']['concurrency'])
        self.assertEqual(2,response.json()['policy']['steps_per_plan'])
        self.assertFalse((self.data/'environments').exists())

    def test_candidate_fifo_does_not_block_other_projects(self) -> None:
        """CLI 可写通知被替换成 FIFO 时立即拒绝，不阻塞兄弟项目调度。@return None。"""
        path = self.data/'candidate-fifo'
        os.mkfifo(path)
        started = time.monotonic()
        with self.assertRaisesRegex(ValueError,'候选通知类型'):
            self.manager.plans._request(path)
        self.assertLess(time.monotonic()-started,1)

    def test_tasks_also_respect_explicit_account_capacity_one(self) -> None:
        """Tasks 的页面来源、保存默认与显式参数也遵守真实账号容量。@return None。"""
        topic = self.sql('SELECT id FROM topics LIMIT 1')[0]['id']
        with patch.object(main,'PER_ACCOUNT_CONCURRENCY',1),patch.object(main,'scheduler',Mock()):
            result = main.create_task_batch(main.BatchIn(account_id=1,topic_ids=[topic]))
            batch = next(item for item in main.list_task_batches() if item['id']==result['id'])
            self.assertEqual(1,batch['concurrency'])
            self.assertEqual(1,batch['effective_concurrency'])
            self.assertEqual(1,batch['account_concurrency_limit'])
            with self.assertRaises(main.HTTPException) as failure:
                main.create_task_batch(main.BatchIn(account_id=1,topic_ids=[topic],concurrency=2))
            self.assertEqual(400,failure.exception.status_code)

    def test_timeout_one_of_two_preserves_partial_and_resume_range(self) -> None:
        """超时保留 1／2、旧 Run 和半成品，新 Run 只补原计划剩余一步。@return None。"""
        batch = self.begin_plan()
        run_id = self.launches[-1][0]
        config = self.configure(run_id)
        self.verify_step(run_id,config)
        self.partial_input(run_id,config)
        workspace = self.data/self.manager.run_context(run_id)['workspace_relative']
        (workspace/'partial.txt').write_text('half of step two')
        self.end_run(run_id,'timeout')
        self.manager.tick()
        resumed = self.launches[-1][0]
        self.assertNotEqual(run_id,resumed)
        self.assertEqual('timeout',self.sql('SELECT status FROM runs WHERE id=?',(run_id,))[0]['status'])
        second = self.configure(resumed)
        self.assertTrue(second['resume'])
        self.assertEqual(config['session_id'],second['session_id'])
        self.assertEqual('step-02',second['step_id'])
        self.assertEqual('half of step two',(workspace/'partial.txt').read_text())
        self.assertEqual('complete',self.verify_step(resumed,second)['action'])
        self.manager.transition(batch['id'],'pause')
        self.end_run(resumed)
        self.manager.tick()
        plan = self.manager.instance(batch['instances'][0]['id'])['plans'][0]
        self.assertEqual(2,plan['completed_steps'])
        self.assertEqual(2,len(plan['runs']))

    def test_real_quota_wait_keeps_run_step_attempt_and_native_session(self) -> None:
        """真实耗尽恢复沿原 Run 与当前尝试，只更换额度执行代次。@return None。"""
        batch = self.begin_plan()
        run_id = self.launches[-1][0]
        config = self.configure(run_id)
        self.verify_step(run_id,config)
        before = self.manager.run_context(run_id)
        self.sql("UPDATE runs SET status='quota_wait' WHERE id=?",(run_id,))
        self.manager.execution_released(run_id,0)
        self.manager.tick()
        self.assertEqual('quota_wait',self.manager.run_context(run_id)['plan_status'])
        self.sql("UPDATE runs SET status='queued',quota_attempt=1 WHERE id=?",(run_id,))
        resumed = self.configure(run_id,1)
        self.assertTrue(resumed['resume'])
        self.assertEqual(config['session_id'],resumed['session_id'])
        self.assertEqual(before['attempt_id'],self.manager.run_context(run_id)['attempt_id'])
        self.assertEqual(1,self.manager.run_context(run_id)['attempt_no'])
        self.assertEqual('complete',self.verify_step(run_id,resumed)['action'])
        self.assertEqual(1,len(self.manager.instance(batch['instances'][0]['id'])['plans'][0]['runs']))

    def test_rotation_two_two_one_and_preserved_queue(self) -> None:
        """固定初始队列，默认范围 2＋2＋1 后轮换且不提前创建目录。@return None。"""
        with patch('project_iteration.random.shuffle',side_effect=lambda keys:keys.reverse()) as shuffled:
            batch = self.begin_plan(['project-001','project-002','project-003','project-004'],concurrency=1)
        shuffled.assert_called_once()
        initial = self.sql('SELECT project_key FROM project_instances ORDER BY initial_order')
        self.assertEqual('project-004',initial[0]['project_key'])
        original = self.manager.run_context(self.launches[-1][0])['id']
        ranges = []
        for count in (2,2,1):
            run_id = self.launches[-1][0]
            config = self.configure(run_id)
            context = self.manager.run_context(run_id)
            ranges.append((context['start_index'],context['target_index']))
            for _ in range(count):
                self.verify_step(run_id,config)
            self.end_run(run_id)
            self.manager.tick()
        self.assertEqual([(0,2),(2,4),(4,5)],ranges)
        self.assertNotEqual(original,self.manager.run_context(self.launches[-1][0])['id'])
        self.assertEqual(initial,self.sql('SELECT project_key FROM project_instances ORDER BY initial_order'))
        self.assertEqual(3,self.sql('SELECT COUNT(*) AS n FROM project_instances WHERE in_pool=1')[0]['n'])
        self.assertEqual(1,self.sql('SELECT COUNT(*) AS n FROM project_instances WHERE workspace_relative IS NOT NULL')[0]['n'])

    def test_accepted_decision_replay_and_gate_do_not_interrupt_plan(self) -> None:
        """已接受决定可重放；阈值只挡新计划，暂停允许原两步完成。@return None。"""
        batch = self.begin_plan()
        run_id = self.launches[-1][0]
        config = self.configure(run_id)
        self.verify_step(run_id,config)
        self.gate = {'allowed':False,'message':'5h 已用达到阈值'}
        self.manager.transition(batch['id'],'pause')
        self.verify_step(run_id,config)
        execution = self.sql('SELECT * FROM project_plan_executions WHERE run_id=?',(run_id,))[0]
        Path(config['decision_file']).unlink()
        self.manager.plans._decision(execution)
        self.assertEqual('complete',json.loads(Path(config['decision_file']).read_text())['action'])
        self.end_run(run_id)
        self.manager.tick()
        self.assertEqual(2,self.manager.instance(batch['instances'][0]['id'])['next_step_index'])
        self.manager.transition(batch['id'],'start')
        self.manager.tick()
        self.assertEqual(1,len({item[0] for item in self.launches}))

    def test_persistent_interval_and_shared_account_capacity(self) -> None:
        """两个批次共用容量，补位截止只抽一次且跨恢复保留。@return None。"""
        batch = self.begin_plan(['project-001','project-002','project-003'],interval_min_sec=30,interval_max_sec=30)
        runs = {item[0] for item in self.launches}
        self.assertEqual(2,len(runs))
        self.begin_plan(['project-004','project-005'])
        self.assertEqual(2,len({item[0] for item in self.launches}))
        self.manager.transition(batch['id'],'pause')
        for run_id in runs:
            self.end_run(run_id,'failed')
        self.manager.tick()
        self.manager.tick()
        deadline = self.manager.batch(batch['id'])['next_launch_at']
        self.assertIsNotNone(deadline)
        self.manager.transition(batch['id'],'start')
        for _ in range(3):
            self.manager.tick()
        self.assertEqual(deadline,self.manager.batch(batch['id'])['next_launch_at'])
        self.assertLessEqual(self.sql('SELECT COUNT(*) AS n FROM project_plan_executions WHERE ended_at IS NULL')[0]['n'],2)

    def test_failed_repairs_only_block_one_project(self) -> None:
        """首轮加两次修复耗尽只阻塞该项目，同 Run 不重复计步。@return None。"""
        batch = self.begin_plan(['project-001','project-002'])
        run_id = self.launches[0][0]
        config = self.configure(run_id)
        for expected in ('send','send','failed'):
            self.assertEqual(expected,self.verify_step(run_id,config,solve=False)['action'])
        instance = self.manager.instance(self.manager.run_context(run_id)['id'])
        self.assertEqual(0,instance['next_step_index'])
        self.assertEqual('blocked',instance['status'])
        self.assertEqual(3,len(instance['attempts']))
        self.assertEqual('active',self.manager.batch(batch['id'])['status'])

    def test_missing_session_and_stale_generation_never_accept(self) -> None:
        """缺失会话拒绝接续，旧代次通知不能推进检查点。@return None。"""
        batch = self.begin_plan()
        run_id = self.launches[-1][0]
        config = self.configure(run_id)
        self.reply(run_id,config)
        native = Path(config['native_directory'])/(config['session_id']+'.jsonl')
        dialogue = self.manager.plans.dialogue.read_dialogue(native)
        request = {key:config[key] for key in ('schema','plan_id','run_id','source','generation','phase_seq','step_id','session_id')}
        request.update(input_key=dialogue[0]['key'],response_key=dialogue[-1]['key'],response_end=dialogue[-1]['end'])
        Path(config['request_file']).write_text(json.dumps(request))
        self.manager.transition(batch['id'],'stop')
        self.manager.tick()
        self.assertEqual(0,self.manager.instance(batch['instances'][0]['id'])['next_step_index'])
        self.assertFalse(self.controls)

    def test_missing_resume_session_blocks_and_keeps_partial(self) -> None:
        """缺失原会话时禁止偷偷新开会话或重铺初始代码。@return None。"""
        self.begin_plan()
        run_id = self.launches[-1][0]
        config = self.configure(run_id)
        self.verify_step(run_id,config)
        self.partial_input(run_id,config)
        workspace = self.data/self.manager.run_context(run_id)['workspace_relative']
        (workspace/'partial.txt').write_text('keep')
        self.end_run(run_id,'timeout')
        self.manager.tick()
        resumed = self.launches[-1][0]
        (Path(config['native_directory'])/(config['session_id']+'.jsonl')).unlink()
        with self.assertRaisesRegex(ValueError,'会话缺失'):
            self.configure(resumed)
        self.assertEqual('keep',(workspace/'partial.txt').read_text())
        self.assertEqual('blocked',self.manager.run_context(resumed)['plan_status'])

    def test_missing_checkpoint_blocks_without_rebuilding_seed(self) -> None:
        """会话仍在但检查点对象缺失时也立即阻塞，不把当前目录冒充历史证明。@return None。"""
        self.begin_plan()
        run_id = self.launches[-1][0]
        config = self.configure(run_id)
        self.verify_step(run_id,config)
        self.partial_input(run_id,config)
        context = self.manager.run_context(run_id)
        workspace = self.data/context['workspace_relative']
        (workspace/'partial.txt').write_text('keep')
        self.end_run(run_id,'timeout')
        self.manager.tick()
        resumed = self.launches[-1][0]
        (self.manager.manifests/(context['checkpoint_digest']+'.json')).unlink()
        with self.assertRaisesRegex(ValueError,'接续证明缺失或损坏'):
            self.configure(resumed)
        self.assertEqual('blocked',self.manager.run_context(resumed)['plan_status'])
        self.assertEqual('keep',(workspace/'partial.txt').read_text())

    def test_truncated_original_session_cannot_reset_byte_evidence(self) -> None:
        """原会话存在但短于已保存边界时，恢复不能重新采零起点绕过证明。@return None。"""
        self.begin_plan()
        run_id = self.launches[-1][0]
        config = self.configure(run_id)
        self.verify_step(run_id,config)
        self.partial_input(run_id,config)
        self.end_run(run_id,'timeout')
        self.manager.tick()
        resumed = self.launches[-1][0]
        native = Path(config['native_directory'])/(config['session_id']+'.jsonl')
        native.write_bytes(native.read_bytes()[:40])
        with self.assertRaisesRegex(ValueError,'会话被截断'):
            self.configure(resumed)
        self.assertEqual('blocked',self.manager.run_context(resumed)['plan_status'])

    def test_quota_partial_dialogue_cannot_be_truncated_to_last_checkpoint(self) -> None:
        """真实耗尽也封存未完成步骤边界，不能只校验最后一次已通过回复。@return None。"""
        self.begin_plan()
        run_id = self.launches[-1][0]
        config = self.configure(run_id)
        self.verify_step(run_id,config)
        native = Path(config['native_directory'])/(config['session_id']+'.jsonl')
        accepted = native.read_bytes()
        with native.open('a') as stream:
            stream.write(json.dumps({'type':'user','uuid':'quota-partial-input','message':{'role':'user','content':'partial current step'}})+'\n')
        self.sql("UPDATE runs SET status='quota_wait' WHERE id=?",(run_id,))
        self.manager.execution_released(run_id,0)
        native.write_bytes(accepted)
        self.sql("UPDATE runs SET status='queued',quota_attempt=1 WHERE id=?",(run_id,))
        with self.assertRaisesRegex(ValueError,'会话被截断'):
            self.configure(run_id,1)
        self.assertEqual('blocked',self.manager.run_context(run_id)['plan_status'])

    def test_out_of_order_native_writes_use_parent_chain(self) -> None:
        """回复先于输入落盘仍按真实父链验收；孤立回复不得通过。@return None。"""
        self.begin_plan()
        run_id = self.launches[-1][0]
        config = self.configure(run_id)
        self.reply(run_id,config)
        native = Path(config['native_directory'])/(config['session_id']+'.jsonl')
        lines = native.read_text().splitlines()
        native.write_text(lines[1]+'\n'+lines[0]+'\n')
        result = []
        thread = threading.Thread(target=lambda:result.append(self.driver.process('advance',config,wait_seconds=6)))
        thread.start()
        deadline = time.monotonic()+3
        while not Path(config['request_file']).exists() and time.monotonic()<deadline:
            time.sleep(0.01)
        self.manager.tick()
        thread.join(timeout=7)
        self.assertEqual('send',result[0]['action'])
        with self.assertRaisesRegex(ValueError,'投递结果不确定'):
            self.driver.process('advance',config,wait_seconds=0)

    def test_stop_during_verification_and_duplicate_decision(self) -> None:
        """停止在验收提交前获胜；正常重放同一候选不会重复增加通过数。@return None。"""
        batch = self.begin_plan()
        run_id = self.launches[-1][0]
        config = self.configure(run_id)
        self.verify_step(run_id,config)
        self.manager.tick()
        self.manager.tick()
        self.assertEqual(1,self.manager.instance(batch['instances'][0]['id'])['next_step_index'])
        self.reply(run_id,config)
        path = Path(config['native_directory'])/(config['session_id']+'.jsonl')
        records = self.manager.plans.dialogue.read_dialogue(path)
        execution = self.sql('SELECT * FROM project_plan_executions WHERE run_id=?',(run_id,))[0]
        attempt = self.sql('SELECT * FROM project_step_attempts WHERE id=?',(execution['current_attempt_id'],))[0]
        request = {key:config[key] for key in ('schema','plan_id','run_id','source','generation','session_id')}
        request.update(phase_seq=execution['phase_seq'],step_id=attempt['step_id'],
            input_key=records[-2]['key'],response_key=records[-1]['key'],response_end=records[-1]['end'])
        Path(config['request_file']).write_text(json.dumps(request))
        verify = self.manager.verifier.verify

        def stopped(candidate,cases):
            self.manager.transition(batch['id'],'stop')
            return verify(candidate,cases)

        with patch.object(self.manager.verifier,'verify',side_effect=stopped):
            self.manager.tick()
        self.assertEqual(1,self.manager.instance(batch['instances'][0]['id'])['next_step_index'])
        self.assertEqual('resume',self.controls[-1][2])

    def test_consumed_input_recovers_lost_send_ack_without_resending(self) -> None:
        """发送确认丢失但原生输入已消费时，只继续观察并验收，不重复注入。@return None。"""
        batch = self.begin_plan()
        run_id = self.launches[-1][0]
        config = self.configure(run_id)
        self.verify_step(run_id,config)
        path = Path(config['state_file'])
        state = json.loads(path.read_text())
        state['delivery'] = 'sending'
        path.write_text(json.dumps(state))
        self.assertEqual('complete',self.verify_step(run_id,config)['action'])
        self.assertEqual(2,self.manager.instance(batch['instances'][0]['id'])['next_step_index'])

    def test_uncertain_input_without_native_consumption_blocks_recovery(self) -> None:
        """仅有发送意图而无消费证据时不创建恢复 Run 自动重发。@return None。"""
        batch = self.begin_plan()
        run_id = self.launches[-1][0]
        config = self.configure(run_id)
        self.verify_step(run_id,config)
        self.end_run(run_id,'failed')
        self.manager.tick()
        instance = self.manager.instance(batch['instances'][0]['id'])
        self.assertEqual(1,instance['next_step_index'])
        self.assertEqual('blocked',instance['status'])
        self.assertIn('缺少原生消费证据',instance['error'])
        self.assertEqual(1,len(instance['plans'][0]['runs']))

    def test_accepted_checkpoint_before_next_send_resumes_remaining_step(self) -> None:
        """接受后、发送下一步前中断，有明确未发送证据时自动接续剩余范围。@return None。"""
        self.begin_plan()
        run_id = self.launches[-1][0]
        config = self.configure(run_id)
        self.verify_step(run_id,config)
        path = Path(config['state_file'])
        state = json.loads(path.read_text())
        state.update(phase_seq=0,step_id='step-01',prompt=config['prompt'],delivery='sent',offset=0)
        path.write_text(json.dumps(state))
        self.end_run(run_id,'failed')
        self.manager.tick()
        resumed_id = self.launches[-1][0]
        self.assertNotEqual(run_id,resumed_id)
        resumed = self.configure(resumed_id)
        self.assertEqual('step-02',resumed['step_id'])
        self.assertEqual(config['session_id'],resumed['session_id'])
        self.assertEqual('complete',self.verify_step(resumed_id,resumed)['action'])


class ProjectPlanMigrationTests(ProjectIterationFixture):
    """以未迁移的历史表证明兼容升级而非只测试新建库。"""

    def test_old_attempt_ids_indexes_sequence_and_repeat_upgrade(self) -> None:
        """解除 Run 唯一限制时保留主键、内容与序列，重复初始化不改旧记录。@return None。"""
        connection = sqlite3.connect(self.data/'legacy.sqlite')
        connection.row_factory = sqlite3.Row
        connection.executescript('CREATE TABLE accounts(id INTEGER PRIMARY KEY); CREATE TABLE runs(id TEXT PRIMARY KEY);'+PROJECT_SCHEMA)
        connection.execute('INSERT INTO project_catalog_releases VALUES(1,?,?,?,?)',('legacy','digest','catalog',1))
        connection.execute("INSERT INTO project_iteration_batches(id,account_id,account_identity,name,catalog_release_id,policy_json,created_at,updated_at) VALUES(1,1,'original','legacy',1,'{}',1,1)")
        for index,status in enumerate(('passed','failed','pending','cancelled'),start=1):
            connection.execute("INSERT INTO project_instances(id,batch_id,project_key,manifest_json,seed_digest,roadmap_digest,checkpoint_digest,created_at,updated_at) VALUES(?,1,?,'{}','seed','route','checkpoint',1,1)",(index,str(index)))
            connection.execute('INSERT INTO runs VALUES(?)',(f'legacy-{index}',))
            connection.execute('INSERT INTO project_step_attempts(id,instance_id,step_id,attempt_no,generation,run_id,expected_checkpoint_digest,validation_status,created_at) '
                'VALUES(?,?,?,1,1,?,?,?,1)',(index*10,index,'step-01',f'legacy-{index}','original-checkpoint',status))
        connection.execute("UPDATE sqlite_sequence SET seq=123 WHERE name='project_step_attempts'")
        connection.commit()
        before = [tuple(row) for row in connection.execute('SELECT id,run_id,validation_status,expected_checkpoint_digest FROM project_step_attempts')]
        initialize_plan_schema(connection)
        initialize_plan_schema(connection)
        self.assertEqual(before,[tuple(row) for row in connection.execute('SELECT id,run_id,validation_status,expected_checkpoint_digest FROM project_step_attempts')])
        cursor = connection.execute("INSERT INTO project_step_attempts(instance_id,step_id,attempt_no,generation,run_id,expected_checkpoint_digest,created_at) VALUES(1,'step-02',1,1,'legacy-1','original-checkpoint',1)")
        self.assertEqual(124,cursor.lastrowid)
        indexes = {row['name'] for row in connection.execute('PRAGMA index_list(project_step_attempts)')}
        self.assertIn('idx_project_step_accepted',indexes)
        self.assertIn('idx_project_attempts_instance',indexes)
        connection.close()
