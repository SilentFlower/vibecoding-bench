"""节点私有评审文件、非共享证明及原driver路径的真实文件回归。"""
from __future__ import annotations

import hashlib
import base64
import unittest
from types import SimpleNamespace
from unittest.mock import Mock
from pathlib import Path

from cluster_execution_grants import ExecutionGrant
from cluster_legacy_projects import LegacyProjectWork
from cluster_project_plan import ProjectPlanDecision
from cluster_scenario_files import ScenarioConfiguration, ScenarioReviewWork
from cluster_scenario_review import NodeScenarioReview
from cluster_quota import NodeTerminalQuota, TerminalQuotaRead
from cluster_runs import RunOwnerRefresh, RunStart
from project_library import canonical_json, read_document
from runtime_files import atomic_json, private_directory
import test_cluster_scenario_files as scenario_fixture


class ScenarioNodeReviewTests(unittest.TestCase):
    """使用实际Scope、冻结包和私有文件，容器及模型执行另行验证。"""

    def setUp(self) -> None:
        """建立真实节点数据根及本次非共享评审证明。:return: None。"""
        fixture=scenario_fixture.ScenarioNodeFileTests(methodName='runTest')
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        self.fixture,self.node=fixture,fixture.node
        original=self.node.grants.get(fixture.scope)['grant']
        self.node.grants.close(fixture.scope,'previous_fixture_closed')
        grant=ExecutionGrant.model_validate({**original,'operation_id':'c'*32,'lease':{**original['lease'],'shared_cli':False}})
        self.scope=grant.scope()
        self.node.grants.create(grant)
        self.node.grants.activate(self.scope)
        self.package={'job_id':7,'task_id':5,'turn_no':1,'resolved_model':'offline-fixture',
            'response_digest':'d'*64,'basis_digest':'e'*64,'answer':'固定合成候选回答','rubric':{'criteria':[]}}
        self.raw=canonical_json(self.package)
        self.work=LegacyProjectWork(instance_id=2,attempt_id=None,batch_generation=1,library_digest=fixture.library.digest,
            project_key='example',seed_digest=fixture.work.seed_digest,started=False,scenario={
                'files':fixture.work.model_dump(),'catalog_release_id':1,'execution_id':9,'turn_no':1,
                'session_id':'11111111-1111-1111-1111-111111111111','review':{'job_id':7,'review_attempt':1,
                    'sha256':hashlib.sha256(self.raw).hexdigest(),'bytes':len(self.raw),'resolved_model':'offline-fixture'}})
        self.provider=NodeScenarioReview(fixture.data,self.scope,self.node.work.id,self.work,self.node.grants)
        self.node.runs._directory(self.scope,create=True)
        private_directory(self.provider.files.operation)
        self.provider.files.package_path.write_bytes(self.raw)
        self.provider.files.package_path.chmod(0o600)
        self.row={'account_id':1,'environment_id':self.scope.environment_id,'generation':self.scope.generation}

    def prepare(self) -> dict:
        """实际准备本次私有目录和原生字节起点。:return: 原文件回执。"""
        self.provider.prepare_workspace(self.row,self.node.work.id,self.provider.root)
        self.provider.record_native_start(self.node.work.id,self.provider.native)
        return self.provider.files.facts()

    def test_independent_owner_defer_checks_original_request_and_persists_once(self) -> None:
        """具体401请求与实际私有作业一致后创建待办，重复及变更摘要按原回执核对。:return: None。"""
        scope=self.scope.model_copy(update={'operation_id':'f'*32,'gateway_account_id':None})
        with self.node.executor.database() as connection:
            connection.execute('UPDATE accounts SET cc2api_account_id=NULL WHERE id=1')
        grant=ExecutionGrant(**scope.model_dump(),not_after=1020)
        self.node.grants.create(grant)
        self.node.grants.activate(scope)
        request=RunStart(scope=scope,work=self.node.work.model_copy(update={'project':self.work}))
        record={'protocol':1,'scope':scope.model_dump(),'work':request.work.model_dump(),'phase':'ready',
            'result':{'source':scope.source,'token':'original-review-token'},'pending_input':None,'shared_cli':False}
        atomic_json(self.node.runs._directory(scope,create=True)/'execution.json',record)
        source=self.fixture.data/'original-refresh-request.json'
        source.write_bytes(b'{"reason":"synthetic-401"}')
        runtime=self.node.host.runtime
        job={'source':scope.source,'execution_role':'project-review'}
        runtime.job_for_container=Mock(return_value=job)
        runtime.reviews=SimpleNamespace(defer_owner_refresh=Mock(),wait_owner_refresh_exit=Mock())
        self.node.runs._source_artifact=Mock(return_value=source)
        original=RunOwnerRefresh(scope=scope,request_sha256=hashlib.sha256(source.read_bytes()).hexdigest())
        receipt=self.node.runs.defer_owner_refresh(original)
        self.assertEqual('deferred',receipt['phase'])
        runtime.reviews.defer_owner_refresh.assert_called_once_with(job)
        runtime.reviews.wait_owner_refresh_exit.assert_called_once_with(job)
        self.assertEqual(receipt,self.node.runs.defer_owner_refresh(original))
        runtime.reviews.defer_owner_refresh.assert_called_once()
        with self.assertRaisesRegex(ValueError,'请求已变化'):
            self.node.runs.defer_owner_refresh(original.model_copy(update={'request_sha256':'a'*64}))

    def test_private_root_and_package_remain_outside_candidate_mounts_and_bind_frozen_job(self) -> None:
        """冻结包只在本次私有路径，候选HOME和项目根保持独立。:return: None。"""
        facts=self.prepare()
        root=self.provider.review_root(self.node.work.id)
        self.assertTrue(root.is_relative_to(self.fixture.data/'project-review-private'))
        self.assertFalse(root.is_relative_to(self.provider.root))
        self.assertEqual(0o700,root.stat().st_mode&0o777)
        self.assertEqual(0,root.stat().st_uid)
        self.assertEqual([],list(self.provider.workspace.iterdir()))
        context=self.provider.run_context(self.node.work.id)
        self.assertEqual('review',context['role'])
        self.assertEqual(7,context['scenario_execution']['evaluation_job_id'])
        self.assertEqual(self.package,read_document(self.provider._package_path(7)))
        self.assertEqual(facts,self.provider.files.prepare())
        self.assertEqual(str(self.provider.workspace.relative_to(self.fixture.data)),self.work.workspace_relative(self.scope.environment_id))
        with self.assertRaisesRegex(ValueError,'其他原评测'):
            self.provider._package_path(8)
        with self.assertRaisesRegex(ValueError,'本次Run'):
            self.provider.review_root('000000000000')

    def test_original_private_configuration_checks_clock_and_cleans_only_actual_private_notifications(self) -> None:
        """配置只命中原私有路径及Node时钟，旧输入状态保留供原driver接续。:return: None。"""
        facts=self.prepare()
        handle=hashlib.sha256(self.scope.source.encode()).hexdigest()[:20]
        run=self.provider.runtime_run_directory()
        run.mkdir(parents=True)
        for name in ('project-plan-request.json','project-work.json','project-plan-state.json'):
            (run/name).write_text('原私有通知')
        configuration=ScenarioConfiguration(schema=1,workflow_schema=3,plan_id=3,run_id=self.node.work.id,
            source=self.scope.source,generation=1,phase_seq=1,step_id='Q1',session_id=self.work.scenario.session_id,
            prompt='原评审固定输入',cwd='/home/node/review',resume=False,native_directory='/home/node/.claude/projects/-home-node-review',
            request_file=f'/run/v3/runs/{self.node.work.id}/project-plan-request.json',
            state_file=f'/run/v3/runs/{self.node.work.id}/project-plan-state.json',
            decision_file=f'/controls/{handle}/project-plan-decision.json',
            work_file=f'/run/v3/runs/{self.node.work.id}/project-work.json',segment_id=12,
            segment_boot_id=facts['clock']['boot_id'],work_limit_sec=12.5)
        self.provider.configure(configuration)
        self.assertFalse((run/'project-plan-request.json').exists())
        self.assertFalse((run/'project-work.json').exists())
        self.assertEqual('原私有通知',(run/'project-plan-state.json').read_text())
        actual=self.provider.execution_configuration(self.node.work.id,self.scope.source,0,self.provider.native,
            run/'project-plan-request.json',self.provider.control_root()/handle/'project-plan-decision.json','/home/node/review')
        self.assertEqual(configuration.model_dump(by_alias=True),actual)
        decision=ProjectPlanDecision(schema=1,plan_id=3,run_id=self.node.work.id,source=self.scope.source,generation=1,
            phase_seq=1,step_id='Q1',session_id=self.work.scenario.session_id,response_key='fixed-response',action='complete')
        self.provider.decision(decision)
        path=self.provider.control_root()/handle/'project-plan-decision.json'
        self.assertEqual('complete',read_document(path)['action'])
        self.assertFalse((self.provider.root/'controls'/handle/'project-plan-decision.json').exists())
        with self.assertRaisesRegex(ValueError,'实际准备不符'):
            self.provider.configure(configuration.model_copy(update={'segment_boot_id':'other-node-boot'}))

    def test_modified_package_and_oversized_descriptor_reject_before_private_workspace(self) -> None:
        """完整包变更和超过512KiB的包元信息均受阻，实际私有工作区保持未发布。:return: None。"""
        self.provider.files.package_path.write_bytes(self.raw+b' ')
        with self.assertRaisesRegex(ValueError,'摘要或大小'):
            self.prepare()
        self.assertFalse(self.provider.workspace.exists())
        with self.assertRaises(ValueError):
            ScenarioReviewWork.model_validate({**self.work.scenario.review.model_dump(),'bytes':512*1024+1})

    def test_review_original_run_stages_complete_package_and_reads_private_quota_before_unsubmitted_stop(self) -> None:
        """原非共享Run核对完整包和私有额度路径，exec前停止保留原私有现场。:return: None。"""
        original=self.node.grants.get(self.scope)['grant']
        self.node.grants.close(self.scope,'previous_review_fixture_closed')
        grant=ExecutionGrant.model_validate({**original,'operation_id':'f'*32})
        scope=grant.scope()
        self.node.grants.create(grant)
        request=RunStart(scope=scope,work=self.node.work.model_copy(update={'project':self.work}))
        self.assertFalse(request.work.shared_cli)
        staged=self.node.runs.stage_review_input(request)
        self.assertEqual({'scope':scope.model_dump(),'review':self.work.scenario.review.model_dump(),'staged':True},staged)
        self.assertEqual(staged,self.node.runs.stage_review_input(request))
        provider=self.node.runs._project(scope)
        self.assertIsInstance(provider,NodeScenarioReview)
        provider.files.package_path.write_bytes(self.raw)
        provider.files.package_path.chmod(0o600)
        self.assertTrue(self.node.runs.commit_review_input(scope)['ready'])
        self.assertTrue(self.node.runs.prepare_project(request)['prepared'])
        path=provider.files.private_root/'flows/cli/cli-quota.jsonl'
        path.parent.mkdir(parents=True)
        path.write_text('私有评审额度\n')
        read=NodeTerminalQuota(self.node.runs).read(TerminalQuotaRead(scope=scope,stream='cli'))
        self.assertEqual('私有评审额度\n',base64.b64decode(read['content']).decode())
        runtime=provider.runtime_run_directory()
        runtime.mkdir(parents=True)
        (runtime/'status.json').write_text('{"私有状态":true}')
        actual=self.node.runs._source_artifact(scope,self.node.runs._record(scope),self.node.host.runtime,'status.json')
        self.assertEqual(runtime/'status.json',actual)
        self.assertEqual({'stopped':True},self.node.runs.recover_stop(scope))
        self.assertEqual('closed',self.node.runs._record(scope)['phase'])
        self.assertEqual(self.raw,provider.files.package_path.read_bytes())
        self.node.host.runtime.start_run.assert_not_called()
