"""项目基线、真实 SQLite 生命周期与可信本地程序夹具的行为回归。"""
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from importlib.util import module_from_spec, spec_from_file_location
from unittest.mock import Mock, patch

from fastapi.testclient import TestClient
from requests.exceptions import ReadTimeout

import main
from project_iteration import ProjectIterationManager
from project_library import ProjectLibrary, materialize_snapshot, snapshot_tree
from project_verifier import ProjectVerifier


ROOT = Path(__file__).resolve().parents[1]


class LocalFixtureVerifier:
    """只执行测试作者写入的程序夹具；生产始终使用 Docker 验证器。"""

    def verify(self, candidate: Path, cases: list[dict]) -> dict:
        """检查受信任夹具的逐行结果。@param candidate 夹具副本。@param cases 断言。@return 判定。"""
        result = subprocess.run([sys.executable,str(candidate/'app.py')],
            input=''.join(json.dumps(case['input'])+'\n' for case in cases),capture_output=True,text=True,timeout=5)
        if result.returncode:
            return {'status':'failed','message':result.stderr[-1000:]}
        actual = [json.loads(line) for line in result.stdout.splitlines()]
        passed = actual==[case['expected'] for case in cases]
        return {'status':'passed' if passed else 'failed','case_count':len(cases)}


class ProjectIterationFixture(unittest.TestCase):
    """提供真实表和文件夹具，不发起模型请求。"""

    @classmethod
    def setUpClass(cls) -> None:
        """只读取一次完整内容契约。@return None。"""
        cls.library = ProjectLibrary(ROOT/'project_library')

    def setUp(self) -> None:
        """建立隔离数据库与可观测投放器。@return None。"""
        self.temporary = tempfile.TemporaryDirectory(prefix='project-mode-test-')
        self.data = Path(self.temporary.name)
        self.patches = [patch.object(main,'DB_PATH',self.data/'db.sqlite'),patch.object(main,'TOPICS_FILE',ROOT/'topics.md')]
        for item in self.patches:
            item.start()
        main.init_db()
        self.sql("INSERT INTO accounts(id,name,profile_path) VALUES(1,'first','first'),(2,'second','second')")
        self.launches = []
        self.manager = self.make_manager()

    def tearDown(self) -> None:
        """释放独立状态。@return None。"""
        self.manager.stop()
        for item in reversed(self.patches):
            item.stop()
        self.temporary.cleanup()

    def sql(self, statement: str, args=()) -> list[dict]:
        """对测试专属 SQLite 执行一次语句。@param statement SQL。@param args 参数。@return 行。"""
        connection = main.get_db()
        try:
            with connection:
                return [dict(row) for row in connection.execute(statement,args)]
        finally:
            connection.close()

    def make_manager(self) -> ProjectIterationManager:
        """构造不启动后台线程的推进器。@return 推进器。"""
        return ProjectIterationManager(self.data,self.library,main.get_db,main._db_lock,
            lambda rid,account,task:self.launches.append((rid,account,task)),
            lambda:{'claude_code_version':'2.1.293','claude_effort_level':'xhigh','execution_model':'opus'},
            lambda account:'identity-'+str(account['id']),self.stop_fixture,LocalFixtureVerifier(),lambda rid,attempt:False)

    def stop_fixture(self, run_id: str) -> None:
        """模拟已确认终止，保持真实停止字段。@param run_id 运行。@return None。"""
        self.sql("UPDATE runs SET status='stopped',stop_requested_at=1,ended_at=1 WHERE id=? AND status IN ('queued','running','quota_wait','stopping')",(run_id,))

    def begin(self, keys=None, account_id=1) -> dict:
        """建立并启动一个批次。@param keys 项目。@param account_id 账号。@return 批次。"""
        batch = self.manager.create_batch(account_id,'测试批次',keys)
        self.manager.transition(batch['id'],'start')
        self.manager.tick()
        return self.manager.batch(batch['id'])

    def materialize(self, run_id: str) -> Path:
        """模拟通过共同门禁后的目录发布。@param run_id 运行。@return 物理项目目录。"""
        context = self.manager.run_context(run_id)
        environment = {'environment_id':'environment-'+str(context['account_id']),'account_id':context['account_id']}
        self.sql("UPDATE runs SET status='running',started_at=1 WHERE id=?",(run_id,))
        return self.manager.prepare_workspace(environment,run_id,self.data/'environments'/environment['environment_id'])[1]

    def solve_fixture(self, run_id: str, workspace: Path | None = None) -> Path:
        """模拟当前业务动作。@param run_id 运行。@param workspace 在途时复用目录。@return 夹具目录。"""
        workspace = workspace or self.materialize(run_id)
        context = self.manager.run_context(run_id)
        project = self.library.projects[context['project_key']]
        reference = json.loads((project.root/'verification/reference.json').read_text())
        manifest = json.loads(context['manifest_json'])
        actions = {step['checks'][0]['input']['action']:reference['actions'][step['checks'][0]['input']['action']]
            for step in manifest['steps'][:context['next_step_index']+1]}
        shutil.copy2(ROOT/'project_library/reference_runtime.py',workspace/'fixture_behaviors.py')
        source = (project.root/'seed/app.py').read_text()
        source = source.replace('def handle(request):','def original_handle(request):')
        insertion = '\nfrom fixture_behaviors import evaluate\nACTIONS = '+repr(actions)+'\ndef handle(request):\n    action = request.get("action", "overview")\n    if action in ACTIONS:\n        return evaluate(ACTIONS[action],request,FIELDS)\n    return original_handle(request)\n\n'
        source = source.replace("if __name__ == '__main__':",insertion+"if __name__ == '__main__':")
        (workspace/'app.py').write_text(source)
        note = workspace/'accumulated.txt'
        previous = note.read_text() if note.exists() else ''
        note.write_text(previous+context['step_id']+'\n')
        return workspace

    def end_run(self, run_id: str, status='success', release=True) -> None:
        """模拟执行结束和独立释放证据。@param run_id 运行。@param status 状态。@param release 是否释放。@return None。"""
        self.sql('UPDATE runs SET status=?,ended_at=2 WHERE id=?',(status,run_id))
        if release:
            self.manager.execution_released(run_id,0)

class ProjectIterationTests(ProjectIterationFixture):
    """通过真实表和文件证明原单步批次的兼容性。"""

    def test_create_hundred_has_no_working_directories(self) -> None:
        """全量选择只写元数据；暂停和排队都不预先铺目录。@return None。"""
        batch = self.manager.create_batch(1,'全量')
        self.assertEqual(100,len(batch['instances']))
        self.assertTrue(all(item['workspace_path'] is None for item in batch['instances']))
        self.manager.tick()
        self.assertFalse((self.data/'environments').exists())
        self.assertFalse(self.launches)
        self.manager.transition(batch['id'],'start')
        self.manager.tick()
        self.assertFalse((self.data/'environments').exists())
        self.assertEqual(1,len({item[0] for item in self.launches}))

    def test_same_seed_isolated_between_accounts_and_batches(self) -> None:
        """同基线字节一致，一方修改不污染另一方，切换后目录保留。@return None。"""
        first = self.begin(['project-001'])
        first_run = self.launches[-1][0]
        a = self.materialize(first_run)
        self.manager.transition(first['id'],'stop')
        self.end_run(first_run,'stopped')
        for _ in range(3):
            self.manager.tick()
        self.begin(['project-001'],account_id=2)
        b = self.materialize(self.launches[-1][0])
        self.assertEqual(snapshot_tree(a)['digest'],snapshot_tree(b)['digest'])
        (a/'local.txt').write_text('first account')
        self.assertFalse((b/'local.txt').exists())
        self.assertTrue(a.exists())
        self.begin(['project-001'],account_id=1)
        c = self.materialize(self.launches[-1][0])
        self.assertNotEqual(a,c)
        self.assertEqual(snapshot_tree(b)['digest'],snapshot_tree(c)['digest'])
        self.assertFalse((c/'local.txt').exists())

    def test_two_steps_accumulate_and_replayed_tick_is_idempotent(self) -> None:
        """验收后接续下一步，重放不会重复接受，后一步保留前一步数据。@return None。"""
        batch = self.begin(['project-001'])
        for _ in range(2):
            run_id = self.launches[-1][0]
            workspace = self.solve_fixture(run_id)
            self.end_run(run_id)
            self.manager.tick()
        instance = self.manager.instance(batch['instances'][0]['id'])
        self.assertEqual(2,instance['next_step_index'])
        self.assertEqual('step-01\nstep-02\n',(workspace/'accumulated.txt').read_text())
        self.manager.tick()
        self.assertEqual(2,self.sql("SELECT COUNT(*) AS n FROM project_step_attempts WHERE validation_status='passed'")[0]['n'])

    def test_normal_exit_without_behavior_cannot_advance(self) -> None:
        """正常退出但尚未实现业务必须自动修复并在上限后切换。@return None。"""
        batch = self.begin(['project-001','project-002'])
        for _ in range(3):
            run_id = self.launches[-1][0]
            self.materialize(run_id)
            self.end_run(run_id)
            self.manager.tick()
        instance = self.manager.instance(batch['instances'][0]['id'])
        self.assertEqual(0,instance['next_step_index'])
        self.assertEqual('blocked',instance['status'])
        self.assertEqual('project-002',self.manager.run_context(self.launches[-1][0])['project_key'])
        self.assertEqual(3,len(instance['attempts']))

    def test_terminal_state_waits_for_strict_release(self) -> None:
        """终态已落库而旧执行未清理时，不验收也不投放下一步。@return None。"""
        batch = self.begin(['project-001'])
        run_id = self.launches[-1][0]
        self.solve_fixture(run_id)
        self.end_run(run_id,release=False)
        self.manager.tick()
        self.assertEqual(0,self.manager.instance(batch['instances'][0]['id'])['next_step_index'])
        self.manager.execution_released(run_id,0)
        self.manager.tick()
        self.assertEqual(1,self.manager.instance(batch['instances'][0]['id'])['next_step_index'])

    def test_repair_uses_existing_files_and_regresses_prior_capabilities(self) -> None:
        """失败后自动修复同一目录，后一步损坏旧能力时不得推进。@return None。"""
        batch = self.begin(['project-001'])
        original_run = self.launches[-1][0]
        workspace = self.materialize(original_run)
        (workspace/'user-data.txt').write_text('keep this data')
        self.end_run(original_run)
        self.manager.tick()
        repair_run = self.launches[-1][0]
        self.assertNotEqual(original_run,repair_run)
        self.assertEqual(2,self.manager.run_context(repair_run)['attempt_no'])
        self.assertEqual(workspace,self.solve_fixture(repair_run))
        self.end_run(repair_run)
        self.manager.tick()
        next_run = self.launches[-1][0]
        self.solve_fixture(next_run)
        action = self.library.projects['project-001'].manifest['steps'][0]['checks'][0]['input']['action']
        app = workspace/'app.py'
        app.write_text(app.read_text().replace(repr(action),repr('removed_prior_action')))
        self.end_run(next_run)
        self.manager.tick()
        instance = self.manager.instance(batch['instances'][0]['id'])
        self.assertEqual(1,instance['next_step_index'])
        self.assertEqual('failed',instance['attempts'][-2]['validation_status'])
        self.assertEqual('keep this data',(workspace/'user-data.txt').read_text())

    def test_authentication_and_cleanup_failures_block_batch(self) -> None:
        """账号认证失败及严格清理失败都停止该批次，不以切项目继续。@return None。"""
        for account_id,status,cleanup_error in ((1,'auth_failed',None),(2,'success','synthetic cleanup failure')):
            with self.subTest(status=status):
                batch = self.begin(['project-001','project-002'],account_id=account_id)
                run_id = self.launches[-1][0]
                workspace = self.materialize(run_id)
                self.end_run(run_id,status,release=False)
                self.manager.execution_released(run_id,0,cleanup_error)
                count = len(self.launches)
                with patch.object(self.manager.verifier,'verify') as verifier:
                    self.manager.tick()
                    self.manager.tick()
                    verifier.assert_not_called()
                self.assertEqual('blocked',self.manager.batch(batch['id'])['status'])
                self.assertEqual(count,len(self.launches))
                self.assertTrue(workspace.exists())

    def test_pause_then_resume_preserves_quota_wait_attempt(self) -> None:
        """额度等待期间暂停与恢复只延续原 run，不消耗业务修复次数。@return None。"""
        batch = self.begin(['project-001'])
        run_id = self.launches[-1][0]
        workspace = self.materialize(run_id)
        self.sql("UPDATE runs SET status='quota_wait',quota_attempt=1 WHERE id=?",(run_id,))
        self.manager.execution_released(run_id,0)
        self.manager.transition(batch['id'],'pause')
        self.manager.tick()
        self.assertEqual('paused',self.manager.batch(batch['id'])['status'])
        self.assertFalse(self.manager.execution_allowed(run_id))
        self.manager.transition(batch['id'],'start')
        self.manager.tick()
        self.assertTrue(self.manager.execution_allowed(run_id))
        attempts = self.manager.instance(batch['instances'][0]['id'])['attempts']
        self.assertEqual([run_id],[item['run_id'] for item in attempts])
        self.assertTrue(workspace.exists())

    def test_milestone_rotates_and_returns_without_reset(self) -> None:
        """三个活动项目按阶段轮换，返回时沿用原代码和目录。@return None。"""
        batch = self.begin(['project-001','project-002','project-003','project-004'])
        first_path = None
        for project_no in range(1,4):
            for _ in range(5):
                run_id = self.launches[-1][0]
                self.assertEqual(f'project-{project_no:03d}',self.manager.run_context(run_id)['project_key'])
                workspace = self.solve_fixture(run_id)
                if first_path is None:
                    first_path = workspace
                self.end_run(run_id)
                self.manager.tick()
        context = self.manager.run_context(self.launches[-1][0])
        self.assertEqual('project-001',context['project_key'])
        self.assertEqual(5,context['next_step_index'])
        self.assertEqual(5,len((first_path/'accumulated.txt').read_text().splitlines()))
        details = self.manager.batch(batch['id'])
        self.assertIsNone(details['instances'][3]['workspace_path'])

    def test_pause_and_stop_keep_unstarted_empty(self) -> None:
        """暂停不创建目录，立即停止的旧代次不能再次开始。@return None。"""
        batch = self.begin(['project-001'])
        run_id = self.launches[-1][0]
        self.manager.transition(batch['id'],'pause')
        self.manager.tick()
        self.assertFalse(self.manager.execution_allowed(run_id))
        self.assertIsNone(self.manager.instance(batch['instances'][0]['id'])['workspace_path'])
        self.manager.transition(batch['id'],'start')
        self.assertTrue(self.manager.execution_allowed(run_id))
        self.manager.transition(batch['id'],'stop')
        for _ in range(3):
            self.manager.tick()
        self.assertEqual('stopped',self.manager.batch(batch['id'])['status'])
        self.assertFalse((self.data/'environments').exists())
        with self.assertRaises(ValueError):
            self.manager.transition(batch['id'],'start')

    def test_stop_during_validation_cannot_accept_old_generation(self) -> None:
        """验收结束前的停止优先，旧结果不能推进进度。@return None。"""
        batch = self.begin(['project-001'])
        run_id = self.launches[-1][0]
        self.solve_fixture(run_id)
        self.end_run(run_id)
        original = self.manager.verifier.verify
        def stop_and_verify(candidate, cases):
            self.manager.transition(batch['id'],'stop')
            return original(candidate,cases)
        self.manager.verifier.verify = stop_and_verify
        self.manager.tick()
        self.assertEqual(0,self.manager.instance(batch['instances'][0]['id'])['next_step_index'])
        self.assertFalse(self.sql("SELECT id FROM project_step_attempts WHERE validation_status='passed'"))

    def test_native_usage_has_both_start_and_end_boundaries(self) -> None:
        """共享目录中的前后轮响应不计入当前轮，重复消息按完整用量去重。@return None。"""
        self.begin(['project-001'])
        run_id = self.launches[-1][0]
        workspace = self.materialize(run_id)
        directory = self.data/'native'
        directory.mkdir()
        session = directory/'session.jsonl'
        def line(identifier, output):
            return json.dumps({'type':'assistant','message':{'id':identifier,'role':'assistant','usage':{'input_tokens':10,'output_tokens':output}}})+'\n'
        session.write_text(line('before',100))
        self.manager.record_native_start('usage-run',directory)
        with session.open('a') as target:
            target.write(line('current',5)+line('current',20))
        self.sql("INSERT INTO tasks(id,topic_no,title,prompt,account_id) VALUES(999,1,'usage','usage',1)")
        self.sql("INSERT INTO runs(id,task_id,account_id,status) VALUES('usage-run',999,1,'success')")
        self.manager.record_native_end('usage-run',directory)
        with session.open('a') as target:
            target.write(line('after',1000))
        result = self.manager.native_usage('usage-run',directory,lambda usage:usage['input_tokens'])
        self.assertEqual(20,result['tokens_out'])
        self.assertEqual(1,result['requests'])
        self.assertTrue(workspace.exists())

    def test_post_preparation_gate_does_not_materialize(self) -> None:
        """环境准备后门禁关闭，不建立可见目录。@return None。"""
        self.begin(['project-001'])
        self.manager.admission = lambda account,rid:False
        with self.assertRaises(ValueError):
            self.materialize(self.launches[-1][0])
        self.assertFalse((self.data/'environments').exists())

    def test_account_disable_fences_and_stops_execution(self) -> None:
        """账号停用会撤销推进权并停止本账号工作，已有目录保留。@return None。"""
        batch = self.begin(['project-001'])
        run_id = self.launches[-1][0]
        workspace = self.materialize(run_id)
        self.sql('UPDATE accounts SET enabled=0 WHERE id=1')
        self.manager.tick()
        self.assertEqual('blocked',self.manager.batch(batch['id'])['status'])
        self.assertEqual('stopped',self.sql('SELECT status FROM runs WHERE id=?',(run_id,))[0]['status'])
        self.assertFalse(self.manager.execution_allowed(run_id))
        self.end_run(run_id,'stopped')
        self.manager.tick()
        self.assertTrue(workspace.exists())

    def test_verifier_infrastructure_errors_never_trigger_model_repairs(self) -> None:
        """验收环境失败只做有界本地重试，不让模型重复修复程序。@return None。"""
        batch = self.begin(['project-001','project-002'])
        run_id = self.launches[-1][0]
        self.solve_fixture(run_id)
        self.end_run(run_id)
        with patch.object(self.manager.verifier,'verify',return_value={'status':'error','message':'synthetic infrastructure failure'}):
            self.manager.tick()
            self.manager.tick()
        attempts = self.manager.instance(batch['instances'][0]['id'])['attempts']
        self.assertEqual(1,len(attempts))
        self.assertEqual('blocked',self.manager.instance(batch['instances'][0]['id'])['status'])

    def test_restart_retains_workspace_and_pending_step(self) -> None:
        """恢复推进器保留已验收文件并重投原排队步骤，实例不从头开始。@return None。"""
        batch = self.begin(['project-001'])
        run_id = self.launches[-1][0]
        workspace = self.solve_fixture(run_id)
        self.end_run(run_id)
        self.manager.tick()
        pending = self.launches[-1][0]
        self.manager.stop()
        self.manager = self.make_manager()
        self.manager.recover(lambda rid:None)
        self.manager.tick()
        self.assertEqual(pending,self.launches[-1][0])
        self.assertEqual(1,self.manager.instance(batch['instances'][0]['id'])['next_step_index'])
        self.assertEqual('step-01\n',(workspace/'accumulated.txt').read_text())

    def test_http_contract_authentication_and_old_run_entry_guard(self) -> None:
        """真实 ASGI 请求校验鉴权、数量、类型和旧入口拒绝，不启动真实模型。@return None。"""
        with patch.multiple(main,project_iterations=self.manager,V3_ENABLED=False,_AUTH_ENABLED=True,WEBUI_USER='fixture',WEBUI_PASS='fixture'):
            client = TestClient(main.app)
            self.assertEqual(401,client.get('/api/project-catalog').status_code)
            client.cookies.set(main._SESSION_COOKIE,main._make_session_token('fixture'))
            catalog = client.get('/api/project-catalog')
            self.assertEqual(200,catalog.status_code)
            self.assertEqual(100,len(catalog.json()['projects']))
            self.assertNotIn('reference.json',catalog.text)
            self.assertEqual(422,client.post('/api/project-iteration-batches',json={'account_id':True}).status_code)
            response = client.post('/api/project-iteration-batches',json={'account_id':1,'name':'HTTP 批次','project_keys':['project-001']})
            self.assertEqual(200,response.status_code,response.text)
            bid = response.json()['id']
            self.assertEqual(200,client.post(f'/api/project-iteration-batches/{bid}/start').status_code)
            self.manager.tick()
            task_id = self.launches[-1][2]['id']
            self.assertEqual(409,client.post(f'/api/tasks/{task_id}/run').status_code)
            self.assertFalse((self.data/'environments').exists())
            client.close()

    def test_historical_files_are_immutable_and_cannot_escape(self) -> None:
        """历史成果读取固定对象，后续修改和路径穿越都不能改变旧内容。@return None。"""
        self.begin(['project-001'])
        run_id = self.launches[-1][0]
        workspace = self.solve_fixture(run_id)
        self.end_run(run_id)
        self.manager.tick()
        attempt = self.sql('SELECT id FROM project_step_attempts WHERE run_id=?',(run_id,))[0]['id']
        original = self.manager.artifact_file(attempt,'accumulated.txt')['text']
        (workspace/'accumulated.txt').write_text('later changed')
        self.assertEqual(original,self.manager.artifact_file(attempt,'accumulated.txt')['text'])
        with self.assertRaises(ValueError):
            self.manager.artifact_file(attempt,'../../etc/passwd')

    def test_snapshot_rejects_links_instead_of_reading_external_data(self) -> None:
        """工作副本中的链接不能穿透到宿主其它目录。@return None。"""
        directory = self.data/'unsafe'
        directory.mkdir()
        (directory/'outside').symlink_to('/etc/passwd')
        with self.assertRaises((OSError,ValueError)):
            snapshot_tree(directory)

    def test_snapshot_can_be_verified_under_restrictive_umask(self) -> None:
        """控制端 umask 不得让无凭据验证用户读不到候选源码。@return None。"""
        source = self.data/'original'
        source.mkdir()
        (source/'module').mkdir()
        (source/'module/data.json').write_text('{"synthetic":true}')
        snapshot = snapshot_tree(source,self.manager.objects)
        old_mask = os.umask(0o077)
        try:
            restored = self.data/'restored'
            materialize_snapshot(snapshot,self.manager.objects,restored)
        finally:
            os.umask(old_mask)
        self.assertEqual(0o755,restored.stat().st_mode & 0o777)
        self.assertEqual(0o755,(restored/'module').stat().st_mode & 0o777)
        self.assertEqual(0o644,(restored/'module/data.json').stat().st_mode & 0o777)
        self.assertEqual(snapshot['digest'],snapshot_tree(restored)['digest'])

    def test_reference_behavior_matches_independent_business_examples(self) -> None:
        """手写业务结果校验参考器，避免只验证生成器与自身一致。@return None。"""
        spec = spec_from_file_location('project_reference_gold',ROOT/'project_library/reference_runtime.py')
        reference = module_from_spec(spec)
        spec.loader.exec_module(reference)
        fields = {'label':'name','metric':'amount','group':'team','state':'status','date':'date'}
        self.assertEqual([{'id':1,'html':'<h1>A &amp; B</h1>\n<p>&lt;unsafe&gt;</p>'}],
            reference.evaluate('render_documents',{'items':[{'id':1,'name':'# A & B\n<unsafe>'}]},fields))
        self.assertEqual([{'cycle':1,'phase':'focus','start':0,'end':10},
            {'cycle':1,'phase':'rest','start':10,'end':12},{'cycle':2,'phase':'focus','start':12,'end':22}],
            reference.evaluate('focus_schedule',{'options':{'cycles':2,'focus_minutes':10,'rest_minutes':2}},fields))
        self.assertEqual({'subtotal':30,'net':27,'tax':5.4,'total':32.4},
            reference.evaluate('quotation_tax',{'items':[{'amount':3,'unit_price':10}],
                'options':{'discount':0.1,'tax_rate':0.2}},fields))
        self.assertEqual([{'id':1,'text':'Hello Ada {missing}'}],
            reference.evaluate('snippet_expand',{'items':[{'id':1,'name':'Hello {user} {missing}'}],
                'options':{'values':{'user':'Ada'}}},fields))

    def test_candidate_timeout_is_a_business_failure(self) -> None:
        """候选超时触发有限业务修复，Docker 创建故障仍归类基础设施错误。@return None。"""
        candidate = self.data/'candidate'
        candidate.mkdir()
        client = Mock()
        client.containers.create.return_value.wait.side_effect = ReadTimeout('synthetic timeout')
        verifier = ProjectVerifier(client,self.data,self.data,'fixture-runtime')
        result = verifier.verify(candidate,[{'input':{},'expected':{}}],timeout=1)
        self.assertEqual('failed',result['status'])
        client.containers.create.return_value.remove.assert_called_once_with(force=True)
        self.assertEqual([],list((self.data/'project-verification-inputs').iterdir()))
        client.containers.create.side_effect = RuntimeError('synthetic daemon error')
        self.assertEqual('error',verifier.verify(candidate,[])['status'])


if __name__ == '__main__':
    unittest.main()
