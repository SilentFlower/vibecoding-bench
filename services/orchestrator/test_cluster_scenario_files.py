"""场景节点文件的真实基线传输、冻结材料、回执及未知恢复回归。"""
from __future__ import annotations

import tempfile
import hashlib
import shutil
import unittest
from pathlib import Path
from unittest.mock import patch

from cluster_scenario_files import NodeScenarioFiles, ScenarioFileWork, ScenarioInputSelection
from cluster_execution_grants import ExecutionGrant
from cluster_legacy_projects import LegacyProjectWork
from cluster_runs import RunScenarioInput, RunStart
from cluster_scenario_project import NodeScenarioProject
from cluster_workspace import WorkspaceSnapshotArchive, WorkspaceSnapshotRequest, read_workspace_bundle, write_workspace_bundle
from project_library import ProjectLibrary, materialize_snapshot, read_document, snapshot_tree, write_document
from runtime_files import atomic_json
from unittest.mock import Mock
from test_project_scenario_content import scenario_fixture
import test_cluster_runs as run_fixture


class ScenarioNodeFileTests(unittest.TestCase):
    """中央和节点采用独立临时数据根，所有源码包均实际写入及读取。"""

    def setUp(self) -> None:
        """准备真实节点有限证明和冻结场景内容。:return: None。"""
        temporary=tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.central=Path(temporary.name)
        root=scenario_fixture(self.central/'library')
        project=root/'projects/example'
        (project/'disclosure/entry.txt').write_text('入口业务材料')
        (project/'materials').mkdir()
        (project/'materials/task.txt').write_text('任务业务材料')
        definition=read_document(project/'project.json')
        scenario=definition['scenarios'][0]
        scenario['entries'][0]['setup']=[{'source':'disclosure/entry.txt','target':'app/entry.txt'}]
        scenario['tasks'][0]['setup']=[{'source':'materials/task.txt','target':'app/task.txt'}]
        scenario['tasks'][0]['branches']=[{'id':'details','when':'请求详细材料',
            'setup':[{'source':'disclosure/details.txt','target':'app/details.txt'}],
            'materials':['disclosure/details.txt'],'activate_tasks':[]}]
        write_document(project/'project.json',definition)
        self.library=ProjectLibrary(root)
        node=run_fixture.NodeRunTests(methodName='runTest')
        node.setUp()
        self.addCleanup(node.doCleanups)
        self.node,self.scope,self.data=node,node.scope,node.fixture.root
        self.library.install(self.data)
        node.grants.activate(self.scope)
        baseline=snapshot_tree(project/'seed',self.central/'objects')
        self.work=ScenarioFileWork(library_digest=self.library.digest,project_key='example',scenario_key='SC1',task_key='Q1',
            seed_digest=baseline['digest'],started=False,inputs={'scenario_id':3,'task_id':5,'entry_key':'normal',
                'code':{'task_id':5,'dependencies':{},'base_checkpoint_digest':baseline['digest'],'base_checkpoint_job_id':None},
                'disclosures':['details']})
        self.files=NodeScenarioFiles(self.data,self.scope,node.work.id,self.work,node.grants)
        self.bundle=self.central/'transfer/base.tar'
        self.receipt=write_workspace_bundle(self.bundle,WorkspaceSnapshotRequest(scope=self.scope,
            snapshot_id='1'*32,purpose='candidate'),baseline,self.central/'objects')

    def test_real_base_import_and_preparation_publish_all_stage_objects_without_hidden_files(self) -> None:
        """真实包导入后准备原场景，中央逐阶段下载可还原原材料且同意图幂等。:return: None。"""
        self.files.import_base(self.bundle,self.receipt)
        facts=self.files.prepare()
        self.assertEqual(self.scope.model_dump(),facts['scope'])
        self.assertEqual(['entry','task','branch:details'],list(facts['inputs']['stages']))
        self.assertEqual('隐藏材料',(self.files.workspace/'app/details.txt').read_text())
        self.assertFalse((self.files.workspace/'verification').exists())
        self.assertTrue(facts['clock']['start_mono']>0)
        self.assertEqual(Path('/proc/sys/kernel/random/boot_id').read_text().strip(),facts['clock']['boot_id'])
        for stage in facts['inputs']['stages']:
            receipt=WorkspaceSnapshotArchive.model_validate(self.files.archive(stage))
            bundle=self.files.operation/'exports'/(receipt.snapshot_id+'.tar')
            manifest=read_workspace_bundle(bundle,receipt,self.central/'received-objects')
            destination=self.central/('received-'+stage.replace(':','-'))
            materialize_snapshot(manifest,self.central/'received-objects',destination)
            self.assertEqual(facts['inputs']['stages'][stage]['input_checkpoint_digest'],manifest['digest'])
            self.assertEqual('入口业务材料',(destination/'app/entry.txt').read_text())
            self.assertEqual(receipt.model_dump(),self.files.archive(stage))
        (self.files.workspace/'partial.txt').write_text('本任务新半成品')
        self.assertEqual(facts,self.files.prepare())
        self.assertEqual('本任务新半成品',(self.files.workspace/'partial.txt').read_text())
        self.node.grants.close(self.scope,'synthetic_scope_closed')
        self.assertEqual(facts,self.files.facts())
        with self.assertRaises(ValueError):
            self.files.prepare()

    def test_base_scope_and_digest_conflicts_reject_before_objects_or_workspace_are_published(self) -> None:
        """跨账号Scope与替代树受阻，文件准备必须先有完整的原基线。:return: None。"""
        for bad in (self.receipt.model_copy(update={'scope':self.scope.model_copy(update={'account_id':2})}),
                self.receipt.model_copy(update={'tree_digest':'0'*64})):
            with self.assertRaisesRegex(ValueError,'原Scope或已接受输入'):
                self.files.import_base(self.bundle,bad)
        self.assertFalse(self.files.objects.exists())
        with self.assertRaises((ValueError,OSError)):
            self.files.prepare()
        self.assertFalse(self.files.workspace.exists())
        self.assertFalse((self.files.operation/'intent.json').exists())

    def test_unknown_after_file_writes_preserves_intent_and_refuses_repeating_preparation(self) -> None:
        """实际写入后回执丢失时保留原意图及现场，重复调用进入核对。:return: None。"""
        self.files.import_base(self.bundle,self.receipt)
        def publish(path,value):
            if path.name=='prepared.json':
                raise OSError('合成回执发布失败')
            return atomic_json(path,value)
        with patch('cluster_scenario_files.atomic_json',side_effect=publish):
            with self.assertRaisesRegex(OSError,'合成回执'):
                self.files.prepare()
        self.assertTrue((self.files.operation/'intent.json').exists())
        self.assertEqual('隐藏材料',(self.files.workspace/'app/details.txt').read_text())
        with self.assertRaisesRegex(ValueError,'结果未知'):
            self.files.prepare()

    def test_strict_input_identity_and_unknown_disclosure_are_rejected(self) -> None:
        """任务身份、披露路径及跨Run定位均按固定原上下文核对。:return: None。"""
        selection=self.work.inputs.model_dump()
        for values in ({'task_id':True},{'disclosures':['../../verification']},{'disclosures':['details','details']}):
            with self.assertRaises(ValueError):
                ScenarioInputSelection.model_validate({**selection,**values})
        with self.assertRaisesRegex(ValueError,'其他Run'):
            NodeScenarioFiles(self.data,self.scope,'000000000000',self.work,self.node.grants)
        self.files.import_base(self.bundle,self.receipt)
        changed=self.work.model_copy(update={'inputs':self.work.inputs.model_copy(update={'disclosures':['missing']})})
        files=NodeScenarioFiles(self.data,self.scope,self.node.work.id,changed,self.node.grants)
        with self.assertRaisesRegex(ValueError,'披露选择'):
            files.prepare()
        self.assertFalse((files.workspace/'app/details.txt').exists())

    def scenario_run(self) -> tuple[RunStart,RunScenarioInput,Path]:
        """登记全新原场景操作，保持实际文件与中央数据根隔离。

        :return: 原启动、基线意图及实际中央包路径。
        """
        original=self.node.grants.get(self.scope)['grant']
        self.node.grants.close(self.scope,'synthetic_previous_closed')
        grant=ExecutionGrant.model_validate({**original,'operation_id':'b'*32})
        scope=grant.scope()
        self.node.grants.create(grant)
        project=LegacyProjectWork(instance_id=2,attempt_id=None,batch_generation=1,library_digest=self.library.digest,
            project_key='example',seed_digest=self.work.seed_digest,started=False,scenario={'files':self.work.model_dump(),
                'catalog_release_id':1,'execution_id':9,'turn_no':1,'session_id':'11111111-1111-1111-1111-111111111111'})
        work=self.node.work.model_copy(update={'project':project})
        request=RunStart(scope=scope,work=work)
        path=self.central/'transfer/run-base.tar'
        receipt=write_workspace_bundle(path,WorkspaceSnapshotRequest(scope=scope,snapshot_id='2'*32,purpose='candidate'),
            snapshot_tree(self.library.projects['example'].root/'seed'),self.central/'objects')
        return request,RunScenarioInput(**request.model_dump(),archive=receipt),path

    def test_original_run_protocol_stages_base_prepares_files_and_stops_before_exec(self) -> None:
        """原Run先核对真实基线和场景文件，实际exec前可定向收口原意图。:return: None。"""
        request,stage,bundle=self.scenario_run()
        runs=self.node.runs
        expected={'scope':request.scope.model_dump(),'archive':stage.archive.model_dump(),'staged':True}
        self.assertEqual(expected,runs.stage_scenario_input(stage))
        self.assertEqual(expected,runs.stage_scenario_input(stage))
        files=NodeScenarioProject(self.data,request.scope,request.work.id,request.work.project,self.node.grants).files
        target=files.operation/'imports'/stage.archive.snapshot_id/'snapshot.tar'
        shutil.copyfile(bundle,target)
        target.chmod(0o600)
        committed=runs.commit_scenario_input(request.scope)
        self.assertTrue(committed['ready'])
        self.assertEqual(committed,runs.commit_scenario_input(request.scope))
        self.assertEqual({'scope':request.scope.model_dump(),'prepared':True},runs.prepare_project(request))
        self.assertEqual('隐藏材料',(files.workspace/'app/details.txt').read_text())
        provider=runs._project(request.scope)
        self.assertIsInstance(provider,NodeScenarioProject)
        self.assertEqual(9,provider.run_context(request.work.id)['scenario_execution']['id'])
        self.assertEqual(self.library.digest,provider._release(1).digest)
        result=runs.recover_stop(request.scope)
        self.assertEqual({'stopped':True},result)
        self.assertEqual('closed',runs._record(request.scope)['phase'])
        self.node.host.runtime.start_run.assert_not_called()
        self.assertEqual('隐藏材料',(files.workspace/'app/details.txt').read_text())

    def test_original_run_stage_unknown_preparation_is_not_repeated(self) -> None:
        """实际输入准备中断后原Run保留reconcile，重复准备拒绝重新替换现场。:return: None。"""
        request,stage,bundle=self.scenario_run()
        runs=self.node.runs
        runs.stage_scenario_input(stage)
        files=NodeScenarioProject(self.data,request.scope,request.work.id,request.work.project,self.node.grants).files
        target=files.operation/'imports'/stage.archive.snapshot_id/'snapshot.tar'
        shutil.copyfile(bundle,target)
        target.chmod(0o600)
        runs.commit_scenario_input(request.scope)
        with patch('cluster_scenario_files.atomic_json',side_effect=OSError('合成准备落盘失败')):
            with self.assertRaisesRegex(OSError,'合成准备'):
                runs.prepare_project(request)
        record=runs._record(request.scope)
        self.assertEqual('reconcile',record['phase'])
        self.assertTrue(record['project_prepare_intent'])
        with self.assertRaisesRegex(ValueError,'准备需要核对'):
            runs.prepare_project(request)
