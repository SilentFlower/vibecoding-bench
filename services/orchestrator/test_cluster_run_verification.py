"""已释放候选的独立程序许可、原冻结源码和持久占用回归。"""
from __future__ import annotations

import hashlib
import threading
import time
import unittest
import uuid
from unittest.mock import Mock

from cluster_environment import EnvironmentFence
from cluster_legacy_projects import LegacyProjectWork
from cluster_run_verification import NodeRunVerifications
from cluster_verification import RunVerificationStart, pending_run_programs
from cluster_workspace import NodeWorkspaceSnapshots, WorkspaceSnapshotRequest, write_workspace_bundle
from project_library import digest_json, read_document, snapshot_tree
from runtime_files import atomic_json
from verify_project_scenarios import create_scenario_fixture
import test_cluster_runs as run_fixture


class ReleasedRunProgramTests(unittest.TestCase):
    """保留真实节点投影、关闭证明和源码包，隔离程序接口使用可观察替身。"""

    def setUp(self) -> None:
        """准备已实际释放角色的原Scope及完整冻结候选。:return: None。"""
        node=run_fixture.NodeRunTests(methodName='runTest')
        node.setUp()
        self.addCleanup(node.doCleanups)
        self.node,self.scope=node,node.scope
        data=node.fixture.root
        library=create_scenario_fixture(data/'synthetic-library','3.12')
        library.install(data)
        project=library.projects['fixture-one']
        definition=project.manifest['scenarios'][0]['tasks'][3]
        objects=data/'program-fixture-objects'
        seed=snapshot_tree(project.root/'seed',objects)
        work=LegacyProjectWork(instance_id=1,attempt_id=None,batch_generation=1,library_digest=library.digest,
            project_key='fixture-one',seed_digest=seed['digest'],started=True,scenario={
                'catalog_release_id':1,'execution_id':1,'turn_no':1,'session_id':str(uuid.uuid4()),'files':{
                    'library_digest':library.digest,'project_key':'fixture-one','scenario_key':'S1','task_key':'Q4',
                    'seed_digest':seed['digest'],'started':True,'inputs':{'scenario_id':1,'task_id':1,'entry_key':'default',
                        'code':{'task_id':1,'dependencies':{},'base_checkpoint_digest':seed['digest'],
                            'base_checkpoint_job_id':None},'disclosures':[]}}})
        frozen=node.work.model_copy(update={'project':work})
        directory=node.runs._directory(self.scope,create=True)
        atomic_json(directory/'execution.json',{'protocol':1,'scope':self.scope.model_dump(),
            'work':frozen.model_dump(),'phase':'closed','result':None})
        node.grants.close(self.scope,'original_cli_closed')
        snapshots=NodeWorkspaceSnapshots(node.runs,source=node.runs.snapshot_workspace)
        snapshot_id=hashlib.sha256(('legacy-candidate:'+self.scope.operation_id).encode()).hexdigest()[:32]
        request=WorkspaceSnapshotRequest(scope=self.scope,snapshot_id=snapshot_id,purpose='candidate')
        receipt=write_workspace_bundle(snapshots._parent(self.scope,create=True)/(request.snapshot_id+'.tar'),
            request,seed,objects)
        atomic_json(snapshots._parent(self.scope)/(request.snapshot_id+'.json'),receipt.model_dump())
        self.verifier=Mock()
        self.verifier.verify_native.return_value={'status':'passed','actual':{'value':1}}
        node.executor.client.containers.list.return_value=[]
        node.host.runtime.image='synthetic-same-release'
        self.jobs=NodeRunVerifications(node.runs,snapshots,Mock(return_value=self.verifier))
        self.addCleanup(self.jobs.close)
        self.request=RunVerificationStart(scope=self.scope,attempt_id='9'*32,snapshot_id=request.snapshot_id,
            candidate_digest=seed['digest'],library_digest=library.digest,project_key='fixture-one',objective_id='Q4',
            definition_digest=digest_json(definition),not_after=int(time.time())+30,answer='原已释放候选回答')

    def wait(self) -> dict:
        """等待原后台程序收据。:return: 原持久程序状态。"""
        deadline=time.monotonic()+5
        while True:
            state=self.jobs.get(self.request)
            if state['phase'] not in ('starting','running'):
                return state
            self.assertLess(time.monotonic(),deadline)
            time.sleep(0.01)

    def test_closed_cli_scope_runs_only_original_program_and_keeps_grant_closed(self) -> None:
        """独立程序只读取原冻结候选，重复请求不创建CLI或第二程序。:return: None。"""
        self.jobs.start(self.request)
        state=self.wait()
        self.assertEqual('complete',state['phase'])
        self.assertEqual(state,self.jobs.start(self.request))
        self.verifier.verify_native.assert_called_once()
        self.assertEqual('VALUE = 1\n',(self.verifier.verify_native.call_args.args[0]/'library/example.py').read_text())
        self.assertEqual('原已释放候选回答',self.verifier.verify_native.call_args.kwargs['answer'])
        self.assertEqual('closed',self.node.grants.get(self.scope)['phase'])
        self.node.host.runtime.start_run.assert_not_called()
        self.assertEqual([],pending_run_programs(self.node.fixture.root,self.scope.environment_id))

    def test_expired_or_unreleased_program_permission_refuses_start(self) -> None:
        """过期程序许可和未释放候选均在持久启动意图前被拒绝。:return: None。"""
        with self.assertRaisesRegex(ValueError,'许可'):
            self.jobs.start(self.request.model_copy(update={'not_after':int(time.time())-1}))
        path=self.node.runs._directory(self.scope)/'execution.json'
        atomic_json(path,{**read_document(path),'phase':'ready'})
        with self.assertRaisesRegex(ValueError,'实际释放'):
            self.jobs.start(self.request)
        self.verifier.verify_native.assert_not_called()
        self.assertFalse((self.jobs._directory(self.request)/'intent.json').exists())

    def test_active_program_blocks_source_fence_until_actual_cancel(self) -> None:
        """独立程序占用参与源隔离，取消后核对原容器再撤销占用。:return: None。"""
        entered=threading.Event()
        def verify(*args,cancel,**kwargs):
            """模拟收到原取消信号后结束的隔离程序。:return: 原取消报告。"""
            entered.set()
            if not cancel.wait(5):
                raise ValueError('合成取消超时')
            return {'status':'cancelled'}
        self.verifier.verify_native.side_effect=verify
        self.jobs.start(self.request)
        self.assertTrue(entered.wait(3))
        self.assertEqual(1,len(pending_run_programs(self.node.fixture.root,self.scope.environment_id)))
        scope=self.scope.model_dump(include={'node_key','account_id','environment_id','assignment_revision','generation'})
        with self.assertRaisesRegex(ValueError,'未收口独立程序'):
            self.node.executor.fence(EnvironmentFence(operation_id='a'*32,**scope))
        state=self.jobs.cancel(self.request)
        self.assertIn(state['phase'],('complete','cancelled'))
        self.assertEqual([],pending_run_programs(self.node.fixture.root,self.scope.environment_id))

    def test_failed_container_cleanup_keeps_reconcile_and_pending_until_actual_stop(self) -> None:
        """验证器返回后实际容器仍在时保留活动，精确取消后才收口。:return: None。"""
        labels={**self.jobs._labels(self.request),'vibebench.project-verifier':'native',
            'vibebench.verifier-root':digest_json(str(self.node.executor.host_data))}
        child=Mock(labels=labels)
        child.remove.side_effect=OSError('合成实际停止失败')
        containers=[child]
        self.node.executor.client.containers.list.side_effect=lambda **_kwargs:list(containers)
        self.jobs.start(self.request)
        self.assertEqual('reconcile',self.wait()['phase'])
        self.assertEqual(1,len(pending_run_programs(self.node.fixture.root,self.scope.environment_id)))
        child.remove.side_effect=lambda **_kwargs:containers.clear()
        self.assertEqual('cancelled',self.jobs.cancel(self.request)['phase'])
        self.assertEqual([],pending_run_programs(self.node.fixture.root,self.scope.environment_id))
