"""经典项目实际文件、中央事务、监督放行和原生证据区间回归。"""
from __future__ import annotations

import hashlib
import base64
import json
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import main

from account_runtime import RuntimeBusy
from cluster_execution_grants import ExecutionGrant
from cluster_legacy_project_io import ClusterLegacyProjectIO
from cluster_legacy_projects import NodeLegacyProject, ProjectNativeRead
from cluster_quota import quota_scope_path
from cluster_project_plan import ProjectPlanConfiguration
from cluster_runs import RunStart, RunTask
from cluster_workspace import NodeWorkspaceSnapshots, WorkspaceSnapshotRequest, WorkspaceSnapshotArchive, read_workspace_bundle
from project_library import snapshot_tree
from project_test_content import create_project_fixture
from run_usage import usage_input_tokens
from runtime_files import atomic_json
import test_cluster_runs as run_fixture
import test_project_iterations as project_fixture


class LegacyNodeProjectTests(unittest.TestCase):
    """用真实中央SQLite、节点文件与源码包验证原经典项目所有权。"""

    @classmethod
    def setUpClass(cls) -> None:
        """创建类专用原schema1内容。:return: None。"""
        temporary=tempfile.TemporaryDirectory()
        cls.addClassCleanup(temporary.cleanup)
        cls.library=create_project_fixture(Path(temporary.name)/'library')

    def setUp(self) -> None:
        """建立实际中央业务记录和原节点Scope。:return: None。"""
        central=project_fixture.ProjectIterationFixture(methodName='runTest')
        central.library=self.library
        central.setUp()
        self.addCleanup(central.tearDown)
        if getattr(self,'plan_mode',False):
            batch=central.manager.create_batch(1,'原计划',['project-001'],policy={'concurrency':1,'active_projects':1,'steps_per_plan':2})
            central.manager.transition(batch['id'],'start')
            central.manager.tick()
        else:
            central.begin(['project-001'])
        rid,account,task=central.launches[0]
        central.sql("UPDATE runs SET status='running',started_at=1 WHERE id=?",(rid,))
        self.central,self.manager,self.rid=central,central.manager,rid
        node=run_fixture.NodeRunTests(methodName='runTest')
        node.setUp()
        self.addCleanup(node.doCleanups)
        self.node=node
        self.library.install(node.fixture.root)
        work=node.work.model_copy(update={'id':rid,'task':RunTask(**{**node.work.task.model_dump(),'id':task['id']})})
        work.worker_env=dict(work.worker_env,RUN_ID=rid,QUOTA_SOURCE=f'run:{rid}:0')
        self.scope=node.scope.model_copy(update={'operation_id':'f'*32,'source':f'run:{rid}:0'})
        original=node.grants.get(node.scope)['grant']
        grant=ExecutionGrant.model_validate({**original,**self.scope.model_dump(),
            'lease':{**original['lease'],'owner':self.scope.source}})
        node.grants.create(grant)
        atomic_json(quota_scope_path(node.fixture.root,self.scope),{'scope':self.scope.model_dump(),
            'state':{'identity':'synthetic-quota','remote_cli':{'source':self.scope.source,'sample_required':False}}})
        self.runner=SimpleNamespace(for_run=lambda _rid:self.row,
            _read=lambda row,operation,payload:node.runs.dispatch(operation,json.dumps(payload).encode()))
        self.runner.sessions=SimpleNamespace(_call=self.runner._read,_operation_lock=lambda _:threading.RLock())
        self.io=ClusterLegacyProjectIO(self.runner,self.manager)
        self.work=work.model_copy(update={'project':self.io.binding(rid)})
        self.request=RunStart(scope=self.scope,work=self.work)
        self.project=NodeLegacyProject(node.fixture.root,self.scope,rid,self.work.project,node.grants)
        self.project.native.mkdir(parents=True)
        self.session=self.project.native/'original-session.jsonl'
        self.session.write_text(self.message('old',100))
        self.job={'token':'original-token','source':self.scope.source,'run_id':rid,'account':{'id':1},'row':{'generation':1,'environment_id':self.scope.environment_id},
            'shared_cli':True,'handle':hashlib.sha256(self.scope.source.encode()).hexdigest()[:20],
            'process':{'source':self.scope.source,'pid':123}}
        def prepare(_account,_task,_rid,_env,_quota,*,project_manager,defer_permission):
            self.assertTrue(defer_permission)
            project_manager.prepare_workspace({'account_id':1,'environment_id':self.scope.environment_id,'generation':1},rid,self.project.root)
            project_manager.record_native_start(rid,self.project.native)
            return 'original-token','original-token'
        node.host.runtime.start_run.side_effect=prepare
        node.host.runtime.job_for_container=Mock(return_value=self.job)
        node.host.runtime.authorize_input=Mock()
        self.permit=self.project.root/'controls'/self.job['handle']/'start.json'
        self.row={'operation_id':self.scope.operation_id,'phase':'running','source':self.scope.source,'environment_id':self.scope.environment_id,'record':{'scope':self.scope.model_dump(),'work':self.work.model_dump()}}
        self.manager.execution_io=self.io

    @staticmethod
    def message(identity: str, tokens: int) -> str:
        """构造原Claude主会话usage。:param identity: 原响应。:param tokens: 输出。:return: 原JSONL行。"""
        return json.dumps({'type':'assistant','message':{'id':identity,'role':'assistant',
            'usage':{'input_tokens':2,'output_tokens':tokens}}})+'\n'

    def start(self) -> None:
        """调用实际节点启动协议。:return: None。"""
        self.assertEqual('ready',self.node.runs.start(self.request)['phase'])

    def test_original_workspace_waits_for_central_parent_then_permits_once(self) -> None:
        """实际物化与中央CAS在放行前，暂停父批次拒绝监督放行。:return: None。"""
        self.start()
        self.assertFalse(self.permit.exists())
        self.assertEqual(self.work.project.seed_digest,snapshot_tree(self.project.workspace)['digest'])
        self.io.permit(self.row)
        self.assertEqual(self.job['process'],json.loads(self.permit.read_text()))
        self.io.permit(self.row)
        self.node.host.runtime.start_run.assert_called_once()
        context=self.manager.run_context(self.rid)
        self.assertEqual(str(self.project.workspace.relative_to(self.node.fixture.root)),context['workspace_relative'])
        self.central.sql("UPDATE project_iteration_batches SET status='paused'")
        self.permit.unlink()
        with self.assertRaisesRegex(RuntimeBusy,'暂停'):
            self.io.permit(self.row)
        self.assertFalse(self.permit.exists())

    def test_native_mirror_keeps_original_start_end_and_excludes_later_steps(self) -> None:
        """中央原聚合器只读取该Run真实字节，后续追加不污染旧终点。:return: None。"""
        self.start()
        self.io.permit(self.row)
        with self.session.open('a') as output:
            output.write(self.message('this',7))
        self.project.finish()
        self.central.sql("UPDATE runs SET status='success' WHERE id=?",(self.rid,))
        with self.session.open('a') as output:
            output.write(self.message('future',900))
        self.manager.record_native_end(self.rid,Path('/missing'))
        mirror=self.io.native_directory(self.rid)
        self.assertNotIn('future',(mirror/self.session.name).read_text())
        usage=self.manager.native_usage(self.rid,Path('/missing'),usage_input_tokens)
        self.assertEqual(7,usage['tokens_out'])
        self.assertEqual(1,usage['requests'])
        self.assertEqual('original-session',self.manager.latest_native_session(self.rid,Path('/missing')))
        self.session.unlink()
        self.session.symlink_to(self.node.fixture.root/'cluster-node.json')
        with self.assertRaises(ValueError):
            self.io.native_directory(self.rid)

    def test_frozen_candidate_uses_original_bundle_and_rejects_later_workspace_owner(self) -> None:
        """原停止候选经真实受限包回中央，后续执行只可读已冻结包。:return: None。"""
        self.start()
        self.io.permit(self.row)
        record=self.node.runs._record(self.scope)
        record['phase']='closed'
        atomic_json(self.node.runs._directory(self.scope)/'execution.json',record)
        snapshots=NodeWorkspaceSnapshots(self.node.runs,source=self.node.runs.snapshot_workspace)
        request=WorkspaceSnapshotRequest(scope=self.scope,snapshot_id='a'*32,purpose='candidate')
        receipt=WorkspaceSnapshotArchive.model_validate(snapshots.create(request))
        bundle=self.node.runs._directory(self.scope)/'snapshots'/('a'*32+'.tar')
        manifest=read_workspace_bundle(bundle,receipt,self.manager.objects)
        self.runner.sessions.snapshot=Mock(return_value=manifest)
        instance=self.manager.run_context(self.rid)
        captured,candidate=self.manager._capture(instance)
        self.assertEqual(self.work.project.seed_digest,captured['digest'])
        self.assertEqual(captured['digest'],snapshot_tree(candidate)['digest'])
        atomic_json(self.project.owner/'execution.json',{'scope':{**self.scope.model_dump(),'source':'later'},'run_id':'later'})
        self.assertEqual(receipt.model_dump(),snapshots.create(request))
        with self.assertRaisesRegex(ValueError,'后续执行'):
            snapshots.create(request.model_copy(update={'snapshot_id':'b'*32}))

    def test_unknown_directory_and_cross_scope_native_reads_remain_blocked(self) -> None:
        """未知现场不会重建seed，错误Scope在实际读取前拒绝。:return: None。"""
        self.project.workspace.mkdir(parents=True)
        (self.project.workspace/'user.txt').write_text('用户现场')
        self.assertEqual('reconcile',self.node.runs.start(self.request)['phase'])
        self.assertEqual('用户现场',(self.project.workspace/'user.txt').read_text())
        with self.assertRaises(ValueError):
            self.project.read(ProjectNativeRead(scope=self.scope.model_copy(update={'account_id':2}),name='original-session.jsonl'))

    def test_large_unrelated_history_keeps_metadata_without_body_transfer(self) -> None:
        """旧会话128MiB只保留起止尺寸，本轮原生字节与用量仍准确。:return: None。"""
        old=self.project.native/'unrelated-old.jsonl'
        with old.open('wb') as output:
            output.truncate(128*1024*1024)
        self.start()
        self.io.permit(self.row)
        with self.session.open('a') as output:
            output.write(self.message('current',7))
        self.project.finish()
        future=self.project.native/'future-unrelated.jsonl'
        with future.open('wb') as output:
            output.truncate(128*1024*1024)
        self.central.sql("UPDATE runs SET status='success' WHERE id=?",(self.rid,))
        mirror=self.io.native_directory(self.rid)
        self.assertFalse((mirror/old.name).exists())
        self.assertFalse((mirror/future.name).exists())
        usage=self.manager.native_usage(self.rid,Path('/missing'),usage_input_tokens)
        self.assertEqual((7,1),(usage['tokens_out'],usage['requests']))
        self.assertEqual(128*1024*1024,self.project.facts()['start'][old.name])
        chunk=self.project.read(ProjectNativeRead(scope=self.scope,name=self.session.name,limit=3))
        self.assertEqual(3,len(base64.b64decode(chunk['content'])))


class ProjectPlanNodeTests(unittest.TestCase):
    """实际中央计划事务、节点文件准备与逐步决定的边界回归。"""

    plan_mode=True
    setUpClass=classmethod(LegacyNodeProjectTests.setUpClass.__func__)
    setUp=LegacyNodeProjectTests.setUp
    message=staticmethod(LegacyNodeProjectTests.message)

    def test_original_configuration_is_committed_before_single_actual_start_and_decisions(self) -> None:
        """原中央保存source/证据后配置Node，实际启动一次，决定按原阶段推进。:return: None。"""
        original=self.project.root/'runtime/runs'/self.rid
        original.mkdir(parents=True)
        (original/'project-plan-request.json').write_text('旧候选通知')
        (original/'project-plan-state.json').write_text('保留原输入状态')
        self.io.prepare(self.row)
        self.assertFalse((original/'project-plan-request.json').exists())
        self.assertEqual('保留原输入状态',(original/'project-plan-state.json').read_text())
        self.assertFalse(self.permit.exists())
        execution=self.manager._one('SELECT * FROM project_plan_executions WHERE run_id=?',(self.rid,))
        self.assertEqual(self.scope.source,execution['source'])
        self.assertEqual('starting',self.node.runs.get(self.scope)['phase'])
        self.assertEqual('ready',self.node.runs.start(self.request)['phase'])
        self.io.permit(self.row)
        self.assertEqual('ready',self.node.runs.start(self.request)['phase'])
        self.node.host.runtime.start_run.assert_called_once()
        config=self.project.execution_configuration(self.rid,self.scope.source,0,self.project.native,
            self.project.root/'runtime/runs'/self.rid/'project-plan-request.json',self.permit.with_name('project-plan-decision.json'),
            '/home/node/projects/'+self.project.workspace.name)
        self.assertEqual(self.work.project.plan.session_id,config['session_id'])
        self.assertFalse(config['resume'])
        plan=self.work.project.plan
        document={'schema':1,'plan_id':plan.id,'run_id':self.rid,'source':self.scope.source,
            'generation':self.work.project.batch_generation,'phase_seq':plan.phase_seq,'step_id':plan.step_id,
            'session_id':plan.session_id,'response_key':'first-answer','action':'send',
            'next_phase_seq':plan.phase_seq+1,'next_step_id':'step-02','prompt':'原下一步'}
        self.central.sql('UPDATE project_plan_executions SET decision_json=? WHERE run_id=?',(json.dumps(document),self.rid))
        execution=self.manager._one('SELECT * FROM project_plan_executions WHERE run_id=?',(self.rid,))
        self.manager.plans._decision(execution)
        destination=self.permit.with_name('project-plan-decision.json')
        self.assertEqual(document,json.loads(destination.read_text()))
        self.manager.plans._decision(execution)
        changed={**document,'prompt':'同阶段改变输入'}
        with self.assertRaisesRegex(ValueError,'同阶段'):
            self.io.publish_decision(execution,changed)
        second={key:value for key,value in document.items() if key not in ('next_phase_seq','next_step_id','prompt')}
        second.update(phase_seq=plan.phase_seq+1,step_id='step-02',response_key='second-answer',action='complete')
        self.io.publish_decision(execution,second)
        with self.assertRaisesRegex(ValueError,'回退'):
            self.io.publish_decision(execution,document)

    def test_file_preparation_cancels_without_touching_other_actual_jobs(self) -> None:
        """尚未进入exec意图的准备可收口，另一个原作业保持原身份。:return: None。"""
        self.io.prepare(self.row)
        self.node.host.runtime.restore_execution=Mock(side_effect=AssertionError('准备阶段误恢复实际进程'))
        self.node.host.runtime.jobs={'other-original':object()}
        self.assertEqual({'stopped':True},self.node.runs.recover_stop(self.scope))
        self.assertEqual('closed',self.node.runs.get(self.scope)['phase'])
        self.assertIn('other-original',self.node.host.runtime.jobs)
        self.assertEqual('closed',self.node.runs.start(self.request)['phase'])
        self.node.host.runtime.start_run.assert_not_called()
        self.node.host.runtime.restore_execution.assert_not_called()

    def test_configuration_rejects_wrong_service_paths_and_altered_frozen_phase(self) -> None:
        """固定路径和初始阶段在实际exec之前核对。:return: None。"""
        self.io.prepare(self.row)
        saved=json.loads((self.project.operation/'project-plan.json').read_text())
        original=ProjectPlanConfiguration.model_validate(saved['configuration'])
        for changes in ({'cwd':'/tmp/other'},{'source':'other'},{'phase_seq':original.phase_seq+1}):
            with self.assertRaises(ValueError):
                self.project.configure(original.model_copy(update=changes))
        with self.assertRaises(ValueError):
            ProjectPlanConfiguration.model_validate({**saved['configuration'],'schema':True})
        self.node.host.runtime.start_run.assert_not_called()

    def test_unknown_actual_start_remains_single_intent_across_actor_queries(self) -> None:
        """进入exec意图后未知只查询同一记录，文件准备回执不会触发重启。:return: None。"""
        self.io.prepare(self.row)
        self.node.host.runtime.start_run.side_effect=RuntimeError('合成私有启动错误')
        first=self.node.runs.start(self.request)
        self.assertEqual('reconcile',first['phase'])
        self.assertEqual(first,self.node.runs.start(self.request))
        self.assertTrue(self.node.runs._record(self.scope)['start_intent'])
        self.assertNotIn('合成私有启动错误',str(first))
        self.node.host.runtime.start_run.assert_called_once()

    def test_original_control_routes_to_scope_and_rejects_old_attempt(self) -> None:
        """精确run/attempt控制原Scope，旧代次在发送前拒绝。:return: None。"""
        control=Mock(return_value={'source':self.scope.source,'frozen':True})
        self.runner.sessions.control=control
        local=Mock()
        with patch.multiple(main,cluster_runner=self.runner,account_runtime=local):
            self.assertEqual({'source':self.scope.source,'frozen':True},main._project_execution_control(self.rid,0,'freeze'))
            with self.assertRaisesRegex(ValueError,'代次'):
                main._project_execution_control(self.rid,1,'freeze')
        control.assert_called_once_with(self.scope.operation_id,'freeze')
        local.control_execution.assert_not_called()

    def test_preparing_source_defers_reads_and_only_prior_attempt_state_is_ignored(self) -> None:
        """准备窗口等待精确启动，旧同Run输入状态保留，跨Run通知明确拒绝。:return: None。"""
        self.io.prepare(self.row)
        execution=self.manager._one('SELECT * FROM project_plan_executions WHERE run_id=?',(self.rid,))
        execution['run_status']='running'
        self.row['phase']='starting'
        with patch.object(self.io,'sync_plan') as sync:
            self.manager.plans._inspect({},None,execution)
        sync.assert_not_called()
        self.row['phase']='running'
        self.assertTrue(self.io.plan_running(execution))
        self.assertFalse(self.io.plan_running({**execution,'source':f'run:{self.rid}:1'}))
        source=f'run:{self.rid}:1'
        work=self.work.model_dump()
        work['task']['quota_attempt']=1
        work['worker_env']['QUOTA_SOURCE']=source
        self.row={**self.row,'operation_id':'c'*32,'source':source,'record':{'scope':self.scope.model_copy(
            update={'operation_id':'c'*32,'source':source}).model_dump(),'work':work}}
        previous={'source':self.scope.source,'phase_seq':0,'delivery':'sent'}
        self.runner.artifact=Mock(side_effect=lambda _rid,name:json.dumps(previous).encode() if name=='project-plan-state.json' else None)
        with patch.object(self.io,'native_directory',return_value=Path('/unused')):
            self.io.sync_plan(self.rid)
            request,state,decision=self.io._plan_paths(self.row)
            self.assertFalse(state.exists())
            previous['source']='run:'+'a'*12+':0'
            with self.assertRaisesRegex(ValueError,'其他source'):
                self.io.sync_plan(self.rid)
