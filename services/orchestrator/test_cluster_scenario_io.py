"""中央场景事务、节点实际文件及原Run具体协议的跨根目录回归。"""
from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

from account_runtime import AccountRuntime
from cluster_execution_grants import ExecutionGrant
from cluster_legacy_project_io import ClusterLegacyProjectIO
from cluster_quota import quota_scope_path
from cluster_runner import ClusterRunner
from cluster_runs import RunStart, RunTask
from cluster_scenario_project import NodeScenarioProject
from cluster_scenario_review import NodeScenarioReview
from cluster_workspace import NodeWorkspaceSnapshots, WorkspaceSnapshotRequest, WorkspaceSnapshotArchive, read_workspace_bundle
from project_review_runtime import ProjectReviewRuntime
from project_library import read_document
from project_test_content import create_project_fixture
from runtime_files import atomic_json
import test_project_scenarios as scenario_fixture
import test_cluster_runs as run_fixture


class ScenarioCentralIOTests(unittest.TestCase):
    """保留原中央SQLite及场景管理器，传输替身只复制实际源码包。"""

    @classmethod
    def setUpClass(cls) -> None:
        """准备类专用原内容夹具。:return: None。"""
        temporary=tempfile.TemporaryDirectory()
        cls.addClassCleanup(temporary.cleanup)
        cls.library=create_project_fixture(Path(temporary.name)/'classic-library')

    def setUp(self) -> None:
        """建立中央原场景候选与另一数据根的实际NodeRun。:return: None。"""
        central=scenario_fixture.ScenarioStateTests(methodName='runTest')
        central.library=self.library
        central.setUp()
        self.addCleanup(central.tearDown)
        self.addCleanup(central.doCleanups)
        self.central,self.manager,self.states=central,central.scenario_manager,central.states
        task=self.states.task(central.tasks[0]['id'])
        self.states.refresh_readiness(task['scenario_instance_id'])
        batch=central.sql('SELECT * FROM project_iteration_batches WHERE id=?',(central.batch['id'],))[0]
        account=central.sql('SELECT * FROM accounts WHERE id=1')[0]
        self.assertTrue(self.states._reserve_candidate(batch,account,task['id']))
        rid,account,generic=central.launches[-1]
        central.sql("UPDATE runs SET status='running',started_at=1 WHERE id=?",(rid,))
        self.rid,self.task_id=rid,task['id']
        node=run_fixture.NodeRunTests(methodName='runTest')
        node.setUp()
        self.addCleanup(node.doCleanups)
        self.node=node
        self.manager.library.install(node.fixture.root)
        self.scope=node.scope.model_copy(update={'operation_id':'f'*32,'source':f'run:{rid}:0'})
        original=node.grants.get(node.scope)['grant']
        grant=ExecutionGrant.model_validate({**original,**self.scope.model_dump(),
            'lease':{**original['lease'],'owner':self.scope.source}})
        node.grants.create(grant)
        atomic_json(quota_scope_path(node.fixture.root,self.scope),{'scope':self.scope.model_dump(),
            'state':{'identity':'synthetic-quota','remote_cli':{'source':self.scope.source,'sample_required':False}}})
        def call(row,operation,payload):
            return node.runs.dispatch(operation,json.dumps(payload).encode())
        sessions=SimpleNamespace(_call=call,_operation_lock=lambda _:threading.RLock())
        self.runner=ClusterRunner(sessions,lambda _: 'synthetic-quota')
        self.runner.for_run=lambda _:self.row
        self.io=ClusterLegacyProjectIO(self.runner,self.manager)
        project=self.io.binding(rid)
        work=node.work.model_copy(update={'id':rid,'task':RunTask(id=generic['id']),'project':project,
            'worker_env':dict(node.work.worker_env,RUN_ID=rid,QUOTA_SOURCE=self.scope.source)})
        self.request=RunStart(scope=self.scope,work=work)
        self.row={'operation_id':self.scope.operation_id,'environment_id':self.scope.environment_id,'source':self.scope.source,
            'phase':'starting','record':{'scope':self.scope.model_dump(),'work':work.model_dump()}}
        self.files=NodeScenarioProject(node.fixture.root,self.scope,rid,project,node.grants).files
        self.downloads=[]
        def copy(source,target,checksum,size):
            self.assertEqual(size,source.stat().st_size)
            self.assertEqual(checksum,hashlib.sha256(source.read_bytes()).hexdigest())
            shutil.copyfile(source,target)
            target.chmod(0o600)
            return {'sha256':checksum,'bytes':size}
        def upload(environment,operation,snapshot,source,checksum,size):
            self.assertEqual((self.scope.environment_id,self.scope.operation_id),(environment,operation))
            return copy(source,self.files.operation/'imports'/snapshot/'snapshot.tar',checksum,size)
        def download(environment,operation,snapshot,target,checksum,size):
            self.assertEqual((self.scope.environment_id,self.scope.operation_id),(environment,operation))
            self.downloads.append(snapshot)
            return copy(self.files.operation/'exports'/(snapshot+'.tar'),target,checksum,size)
        self.transfer=SimpleNamespace(upload_scenario_input=upload,download_scenario_input=download)
        sessions._archive_transfer=lambda _:self.transfer
        self.manager.execution_io=self.io

    def start_candidate(self) -> None:
        """准备Node实际作业替身，使用原产物解析和真实冻结候选包。

        :return: None；共享exec由替身登记，所有文件与driver均实际运行。
        """
        handle=hashlib.sha256(self.scope.source.encode()).hexdigest()[:20]
        proof={'source':self.scope.source,'pid':123}
        job={'source':self.scope.source,'run_id':self.rid,'account':{'id':1},'row':{
            'environment_id':self.scope.environment_id,'generation':1},'shared_cli':self.request.work.shared_cli,'handle':handle,'process':proof}
        if not self.request.work.shared_cli:
            job.update(execution_role='project-review',private_relative=str(self.files.private_root.relative_to(self.node.fixture.root)))
        runtime=self.node.host.runtime
        runtime.job_for_container=Mock(return_value=job)
        runtime.authorize_input=Mock()
        runtime.control_execution=Mock(return_value={'source':self.scope.source,'frozen':True})
        runtime.reviews=ProjectReviewRuntime(runtime)
        runtime.run_artifact_path=lambda rid,name:AccountRuntime.run_artifact_path(runtime,rid,name)
        def start(account,task,rid,environment,quota,*,project_manager,defer_permission):
            self.assertIsInstance(project_manager,NodeScenarioProject)
            self.assertTrue(defer_permission)
            project_manager.prepare_workspace({'account_id':1,'environment_id':self.scope.environment_id,'generation':1},
                rid,project_manager.root)
            connection=self.node.executor.database()
            try:
                with connection:
                    connection.execute('UPDATE runs SET environment_id=? WHERE id=?',(self.scope.environment_id,rid))
            finally:
                connection.close()
            return 'original-token','original-token'
        runtime.start_run.side_effect=start
        result=self.node.runs.start(self.request)
        self.assertEqual('ready',result['phase'])
        self.row['phase']='running'
        self.io.permit(self.row)
        self.assertEqual(proof,read_document(self.node.runs._project(self.scope).control_root()/handle/'start.json'))
        snapshots=NodeWorkspaceSnapshots(self.node.runs,source=self.node.runs.snapshot_workspace)
        def snapshot(operation,snapshot_id,objects):
            self.assertEqual(self.scope.operation_id,operation)
            request=WorkspaceSnapshotRequest(scope=self.scope,snapshot_id=snapshot_id,purpose='candidate')
            receipt=WorkspaceSnapshotArchive.model_validate(snapshots.create(request))
            path=self.files.operation.parent/'snapshots'/(snapshot_id+'.tar')
            return read_workspace_bundle(path,receipt,objects)
        self.runner.sessions.snapshot=snapshot

    def reserve_private_review(self) -> dict:
        """先用原本机夹具形成已释放回答，再将其独立评审分配到Node。

        :return: 原冻结评审包；候选执行由原测试夹具模拟。
        """
        self.manager.execution_io=None
        try:
            configuration=self.central.configure_run(self.rid)
            job_id=self.central.submit_reply(self.rid,configuration,'该项目公开常量的值为1。')
            self.central.release_run(self.rid)
            self.states._mechanical_job(job_id)
            job=self.manager._one('SELECT * FROM project_evaluation_jobs WHERE id=?',(job_id,))
            self.assertEqual('review_ready',job['status'])
            batch=self.manager._one('SELECT * FROM project_iteration_batches WHERE id=?',(self.central.batch['id'],))
            account=self.manager._one('SELECT * FROM accounts WHERE id=1')
            self.assertTrue(self.states._reserve_review(batch,account,job))
        finally:
            self.manager.execution_io=self.io
        rid,account,task=self.central.launches[-1]
        self.central.sql("UPDATE runs SET status='running',started_at=1 WHERE id=?",(rid,))
        scope=self.scope.model_copy(update={'operation_id':'a'*32,'source':f'run:{rid}:0'})
        original=self.node.grants.get(self.scope)['grant']
        grant=ExecutionGrant.model_validate({**original,**scope.model_dump(),
            'lease':{**original['lease'],'owner':scope.source,'shared_cli':False}})
        self.node.grants.create(grant)
        project=self.io.binding(rid)
        work=self.node.work.model_copy(update={'id':rid,'task':RunTask(id=task['id']),'project':project,
            'worker_env':dict(self.node.work.worker_env,RUN_ID=rid,QUOTA_SOURCE=scope.source)})
        self.rid,self.scope=rid,scope
        self.request=RunStart(scope=scope,work=work)
        self.row={'operation_id':scope.operation_id,'environment_id':scope.environment_id,'source':scope.source,
            'phase':'starting','record':{'scope':scope.model_dump(),'work':work.model_dump()}}
        self.files=NodeScenarioReview(self.node.fixture.root,scope,rid,project,self.node.grants).files
        atomic_json(quota_scope_path(self.node.fixture.root,scope),{'scope':scope.model_dump(),
            'state':{'identity':'synthetic-quota','remote_cli':{'source':scope.source,'sample_required':False}}})
        def upload(environment,operation,source,checksum,size):
            self.assertEqual((scope.environment_id,scope.operation_id),(environment,operation))
            self.assertEqual((checksum,size),(hashlib.sha256(source.read_bytes()).hexdigest(),source.stat().st_size))
            shutil.copyfile(source,self.files.package_path)
            self.files.package_path.chmod(0o600)
            return {'sha256':checksum,'bytes':size}
        self.transfer.upload_review_input=upload
        return read_document(self.states._package_path(job_id))

    def test_original_configuration_uses_verified_node_inputs_clock_and_private_native_mirror(self) -> None:
        """原中央source及工作预算绑定真实Node回执，逐阶段完整对象先于业务ready。:return: None。"""
        self.assertIsNone(self.states.task(self.task_id)['workspace_relative'])
        self.io.prepare(self.row)
        task=self.states.task(self.task_id)
        facts=self.files.facts()
        self.assertEqual(facts['workspace_relative'],task['workspace_relative'])
        self.assertEqual(facts['inputs']['input_checkpoint_digest'],task['input_checkpoint_digest'])
        self.assertFalse((self.manager.data/task['workspace_relative']).exists())
        source=self.central.sql('SELECT * FROM project_execution_sources')[0]
        segment=self.central.sql('SELECT * FROM project_work_segments')[0]
        self.assertEqual((facts['clock']['boot_id'],facts['clock']['start_mono']),(segment['boot_id'],segment['start_mono']))
        self.assertEqual(0,source['start_permitted'])
        native=self.manager.data/source['native_relative']
        self.assertEqual(0o700,native.stat().st_mode&0o777)
        self.assertEqual(0,native.stat().st_uid)
        saved=read_document(self.files.operation.parent/'project-plan.json')
        configuration=saved['configuration']
        self.assertEqual(3,configuration['workflow_schema'])
        self.assertEqual(segment['id'],configuration['segment_id'])
        self.assertEqual(segment['reserved_sec'],configuration['work_limit_sec'])
        self.start_candidate()
        self.assertEqual(1,self.central.sql('SELECT start_permitted FROM project_execution_sources')[0]['start_permitted'])
        self.assertIsNone(self.node.host.runtime.project_iterations)

    def test_original_scenario_driver_and_native_evidence_capture_node_candidate_and_publish_decision(self) -> None:
        """原driver真实通知、Node原生字节和候选包接回中央封存及具体完成决定。:return: None。"""
        self.io.prepare(self.row)
        self.start_candidate()
        provider=self.node.runs._project(self.scope)
        runtime=self.files.root/'runtime/runs'/self.rid
        runtime.mkdir(parents=True,exist_ok=True)
        provider.native.mkdir(parents=True,exist_ok=True)
        handle=hashlib.sha256(self.scope.source.encode()).hexdigest()[:20]
        configuration=read_document(self.files.operation.parent/'project-plan.json')['configuration']
        configuration.update(native_directory=str(provider.native),request_file=str(runtime/'project-plan-request.json'),
            state_file=str(runtime/'project-plan-state.json'),work_file=str(runtime/'project-work.json'),
            decision_file=str(self.files.root/'controls'/handle/'project-plan-decision.json'))
        self.central.driver.process('begin',configuration)
        job_id=self.central.submit_reply(self.rid,configuration,'该项目公开常量的值为1。')
        job=self.central.sql('SELECT * FROM project_evaluation_jobs WHERE id=?',(job_id,))[0]
        self.assertEqual('waiting_release',self.states.task(self.task_id)['phase'])
        self.assertIsNone(self.states.task(self.task_id)['accepted_checkpoint_digest'])
        candidate=self.manager.data/job['candidate_relative']
        self.assertEqual('VALUE = 1\n',(candidate/'example.py').read_text())
        source=self.central.sql('SELECT * FROM project_execution_sources')[0]
        mirror=self.manager.data/source['native_relative']
        self.assertTrue((mirror/(configuration['session_id']+'.jsonl')).exists())
        decision=read_document(Path(configuration['decision_file']))
        self.assertEqual(('complete',self.scope.source),(decision['action'],decision['source']))
        work=read_document(runtime/'project-work.json')
        self.assertEqual(self.scope.source,work['source'])
        self.assertEqual(configuration['segment_id'],work['segment_id'])

    def test_incomplete_stage_download_keeps_central_inputs_unpublished_then_same_scope_can_finish(self) -> None:
        """完整阶段对象缺失时中央保留原任务，原文件准备回执可核对后继续导入。:return: None。"""
        original=self.transfer.download_scenario_input
        self.transfer.download_scenario_input=Mock(side_effect=OSError('合成输入下载中断'))
        with self.assertRaisesRegex(OSError,'下载中断'):
            self.io.prepare(self.row)
        task=self.states.task(self.task_id)
        self.assertIsNone(task['workspace_relative'])
        self.assertIsNone(task['input_checkpoint_digest'])
        root=self.manager.data/'project-artifacts/task-inputs'/str(self.task_id)
        self.assertFalse((root/'code-dependency.json').exists())
        self.assertFalse((root/'prepared.json').exists())
        self.assertEqual([],self.central.sql('SELECT * FROM project_execution_sources'))
        self.assertTrue(self.files.workspace.exists())
        self.transfer.download_scenario_input=original
        self.io.prepare(self.row)
        self.assertIsNotNone(self.states.task(self.task_id)['input_checkpoint_digest'])

    def test_staging_failure_can_stop_and_restore_unsubmitted_evidence_without_publishing_workspace(self) -> None:
        """基线上传中断后定向收口，原未执行墓碑保留零投递事实和中央未物化状态。:return: None。"""
        self.transfer.upload_scenario_input=Mock(side_effect=OSError('合成上传中断'))
        with self.assertRaisesRegex(OSError,'上传中断'):
            self.io.prepare(self.row)
        self.assertEqual({'stopped':True},self.node.runs.recover_stop(self.scope))
        self.row['phase']='closed'
        native=self.io.native_directory(self.rid)
        self.assertEqual({'scope':self.scope.model_dump(),'unsubmitted':True},read_document(native/'unsubmitted.json'))
        self.io.sync_plan(self.rid)
        self.assertIsNone(self.states.task(self.task_id)['workspace_relative'])
        self.assertFalse(self.files.workspace.exists())
        self.assertEqual([],self.central.sql('SELECT * FROM project_execution_sources'))
        self.node.host.runtime.start_run.assert_not_called()

    def test_private_review_original_driver_uses_complete_package_native_model_and_waits_for_release(self) -> None:
        """原私有评审通知与精确模型经Node回传，完整结果封存后继续等待严格释放。:return: None。"""
        package=self.reserve_private_review()
        self.assertFalse(self.request.work.shared_cli)
        self.io.prepare(self.row)
        self.start_candidate()
        provider=self.node.runs._project(self.scope)
        self.assertIsInstance(provider,NodeScenarioReview)
        self.assertEqual(package,read_document(provider._package_path(package['job_id'])))
        runtime=provider.runtime_run_directory()
        runtime.mkdir(parents=True,exist_ok=True)
        provider.native.mkdir(parents=True,exist_ok=True)
        handle=hashlib.sha256(self.scope.source.encode()).hexdigest()[:20]
        configuration=read_document(provider.operation/'project-plan.json')['configuration']
        configuration.update(native_directory=str(provider.native),request_file=str(runtime/'project-plan-request.json'),
            state_file=str(runtime/'project-plan-state.json'),work_file=str(runtime/'project-work.json'),
            decision_file=str(provider.control_root()/handle/'project-plan-decision.json'))
        self.central.driver.process('begin',configuration)
        verdict={key:package[key] for key in ('job_id','task_id','turn_no','response_digest','basis_digest')}
        verdict.update(decision='pass',outcome='resolved',branch_id=None,
            criteria=[{'id':'fact','status':'satisfied','reason':'固定合成事实','evidence':['example.py:1']}],feedback_codes=[])
        self.central.submit_reply(self.rid,configuration,json.dumps(verdict))
        job=self.manager._one('SELECT * FROM project_evaluation_jobs WHERE id=?',(package['job_id'],))
        self.assertEqual('waiting_review_release',job['status'])
        result=json.loads(job['review_result_json'])
        self.assertEqual(package['resolved_model'],result['observed_model'])
        self.assertEqual('pass',result['decision']['decision'])
        self.assertIsNone(self.states.task(self.task_id)['accepted_checkpoint_digest'])
        self.assertEqual('complete',read_document(Path(configuration['decision_file']))['action'])
