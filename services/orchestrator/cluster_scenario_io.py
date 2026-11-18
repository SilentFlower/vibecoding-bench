"""场景节点输入的中央协调，先核对完整真实文件再保存原业务事实。"""
from __future__ import annotations

import hashlib
import math
import re
import time

from cluster_scenario_files import ScenarioFileWork, ScenarioProjectWork, ScenarioConfiguration, ScenarioReviewWork
from cluster_workspace import WorkspaceSnapshotArchive, WorkspaceSnapshotRequest, read_workspace_bundle, write_workspace_bundle
from project_library import digest_json, read_checkpoint, read_document, safe_relative, snapshot_tree, write_document
from runtime_files import atomic_json, private_directory
from system_update_contract import safe_read, strict_json


class ClusterScenarioIO:
    """沿原Run有限证明准备节点场景输入及原中央driver配置。

    :param owner: 原ClusterLegacyProjectIO，复用Run、原生证据和路径消费者。
    """

    def __init__(self, owner) -> None:
        """登记已有所有者。:param owner: 原中央文件所有者。:return: None。"""
        self.owner,self.runner,self.manager=owner,owner.runner,owner.manager

    def binding(self, context: dict) -> ScenarioProjectWork:
        """冻结原中央场景候选及已接受输入来源。

        :param context: 原ProjectScenarios执行视图。
        :return: 原节点场景定位。
        """
        task=self.manager.scenarios.task(context['scenario_task_id'])
        library=self.manager._release(context['catalog_release_id'])
        if library.schema not in (2,3):
            raise ValueError('节点场景内容版本不符')
        files=ScenarioFileWork(library_digest=library.digest,project_key=context['project_key'],
            scenario_key=context['scenario_key'],task_key=context['task_key'],seed_digest=context['seed_digest'],
            started=bool(context['workspace_relative']),inputs=self.manager.scenarios.input_selection(task))
        # 原checkpoint仍由中央核对，节点再按同一Scope验证整包及所有对象。
        review=None
        if context['role']=='review':
            execution=context['scenario_execution']
            raw=safe_read(self.manager.scenarios._package_path(execution['evaluation_job_id']),512*1024,private=True)
            package=strict_json(raw,512*1024)
            if (package.get('job_id')!=execution['evaluation_job_id'] or package.get('task_id')!=context['scenario_task_id']
                    or package.get('turn_no')!=execution['turn_no']):
                raise ValueError('原中央私有评审包与冻结回答不一致')
            review=ScenarioReviewWork(job_id=execution['evaluation_job_id'],review_attempt=execution['review_attempt'],
                sha256=hashlib.sha256(raw).hexdigest(),bytes=len(raw),resolved_model=package['resolved_model'])
        else:
            checksum=files.inputs.code.base_checkpoint_digest
            path=self.manager.manifests/(checksum+'.json')
            if checksum==files.seed_digest and not path.exists() and not path.is_symlink():
                seed=snapshot_tree(library.projects[files.project_key].root/'seed',self.manager.objects)
                if seed['digest']!=checksum:
                    raise ValueError('原中央场景seed与冻结基线不一致')
                write_document(path,seed)
            read_checkpoint(self.manager.objects,self.manager.manifests,checksum)
        return ScenarioProjectWork(files=files,catalog_release_id=context['catalog_release_id'],
            execution_id=context['execution_id'],turn_no=context['scenario_execution']['turn_no'],session_id=context['session_id'],review=review)

    def prepare(self, row: dict, project) -> None:
        """导入原已接受基线，取得实际输入回执，再生成原中央场景配置。

        :param row: 已持有原CLI许可并持续续约的执行。
        :param project: 原冻结场景定位。
        :return: None；失败沿原Run账本停止恢复。
        """
        scope=row['record']['scope']
        work=row['record']['work']
        if project.scenario.review is not None:
            self.prepare_review(row,project)
            return
        files=project.scenario.files
        directory=self.manager.data/'cluster-scenario-inputs'/row['operation_id']
        private_directory(directory)
        metadata=directory/'base.json'
        bundle=directory/'base.tar'
        checksum=files.inputs.code.base_checkpoint_digest
        snapshot_id=hashlib.sha256(('scenario-base:'+checksum).encode()).hexdigest()[:32]
        request=WorkspaceSnapshotRequest(scope=scope,snapshot_id=snapshot_id,purpose='candidate')
        if metadata.exists() or metadata.is_symlink():
            receipt=WorkspaceSnapshotArchive.model_validate(strict_json(safe_read(metadata,16384,private=True),16384))
            if receipt.scope!=request.scope or receipt.snapshot_id!=snapshot_id or receipt.tree_digest!=checksum:
                raise ValueError('原场景中央基线包身份已经变化')
        else:
            snapshot=read_checkpoint(self.manager.objects,self.manager.manifests,checksum)
            receipt=write_workspace_bundle(bundle,request,snapshot,self.manager.objects)
            atomic_json(metadata,receipt.model_dump())
        payload={'scope':scope,'work':work,'archive':receipt.model_dump()}
        result=self.runner.sessions._call(row,'run-scenario-input-stage',payload)
        if result!={'scope':scope,'archive':receipt.model_dump(),'staged':True}:
            raise ValueError('节点场景基线暂存意图回执无效')
        transfer=self.runner.sessions._archive_transfer(row)
        transfer.upload_scenario_input(row['environment_id'],row['operation_id'],snapshot_id,bundle,receipt.sha256,receipt.bytes)
        result=self.runner.sessions._call(row,'run-scenario-input-commit',scope)
        if result!={'scope':scope,'tree_digest':checksum,'ready':True}:
            raise ValueError('节点场景完整基线导入回执无效')
        result=self.runner.sessions._call(row,'run-project-prepare',{'scope':scope,'work':work})
        if result!={'scope':scope,'prepared':True}:
            raise ValueError('节点场景文件准备回执无效')
        facts=self.runner._read(row,'run-scenario-input-facts',scope)
        self.accept_files(row,project,facts,transfer,directory)
        native=self.owner.native_directory(work['id'])
        request_path,state_path,decision_path=self.owner._plan_paths(row)
        configuration=self.manager.scenarios.execution_configuration(work['id'],row['source'],work['task']['quota_attempt'],
            native,request_path,decision_path,'/home/node/projects/'+project.alias(row['environment_id']),execution_files=facts)
        value=ScenarioConfiguration.model_validate(configuration)
        result=self.runner.sessions._call(row,'run-project-configure',{'scope':scope,'configuration':value.model_dump(by_alias=True)})
        if result!={'scope':scope,'configured':True}:
            raise ValueError('节点场景原driver配置回执无效')

    def _stage_markers(self, files: ScenarioFileWork, release_id: int) -> dict:
        project=self.manager._release(release_id).projects[files.project_key]
        scenario=next(item for item in project.manifest['scenarios'] if item['id']==files.scenario_key)
        task=next(item for item in scenario['tasks'] if item['id']==files.task_key)
        selection=files.inputs
        entry=next(item for item in scenario['entries'] if item['id']==selection.entry_key)
        root=self.manager.data/'project-artifacts'
        task_root=root/'task-inputs'/str(selection.task_id)
        stages={'entry':(root/'scenarios'/str(selection.scenario_id)/'entry-inputs.json',
            {'scenario_id':selection.scenario_id,'entry_key':selection.entry_key,'setup_digest':digest_json(entry.get('setup',[]))}),
            'task':(task_root/'prepared.json',{'task_id':selection.task_id,'setup_digest':digest_json(task.get('setup',[]))})}
        for key in selection.disclosures:
            branch=next(item for item in task.get('branches',[]) if item['id']==key)
            if branch.get('setup'):
                stages['branch:'+key]=(task_root/('branch-'+key+'.json'),{'task_id':selection.task_id,
                    'branch_id':key,'setup_digest':digest_json(branch['setup'])})
        return stages

    def _check_clock(self, clock: dict) -> None:
        if (not isinstance(clock,dict) or set(clock)!={'boot_id','start_mono'}
                or not isinstance(clock['boot_id'],str) or not 1<=len(clock['boot_id'])<=128
                or type(clock['start_mono']) not in (int,float) or not math.isfinite(clock['start_mono']) or clock['start_mono']<0):
            raise ValueError('节点场景实际启动时钟回执无效')

    def prepare_review(self, row: dict, project) -> None:
        """传输本次完整冻结评审包，保留原中央评审source及预算事务。

        :param row: 原非共享CLI执行。
        :param project: 原冻结评审定位。
        :return: None；候选输入事实保持原先已核对的状态。
        """
        scope,work=row['record']['scope'],row['record']['work']
        review=project.scenario.review
        package=self.manager.scenarios._package_path(review.job_id)
        raw=safe_read(package,512*1024,private=True)
        if len(raw)!=review.bytes or hashlib.sha256(raw).hexdigest()!=review.sha256:
            raise ValueError('原中央冻结评审包在投递前发生变化')
        result=self.runner.sessions._call(row,'run-review-input-stage',{'scope':scope,'work':work})
        if result!={'scope':scope,'review':review.model_dump(),'staged':True}:
            raise ValueError('节点私有评审包暂存回执无效')
        self.runner.sessions._archive_transfer(row).upload_review_input(row['environment_id'],row['operation_id'],
            package,review.sha256,review.bytes)
        result=self.runner.sessions._call(row,'run-review-input-commit',scope)
        if result!={'scope':scope,'sha256':review.sha256,'ready':True}:
            raise ValueError('节点私有评审完整包核对回执无效')
        result=self.runner.sessions._call(row,'run-project-prepare',{'scope':scope,'work':work})
        if result!={'scope':scope,'prepared':True}:
            raise ValueError('节点私有评审文件准备回执无效')
        facts=self.runner._read(row,'run-review-input-facts',scope)
        if (set(facts)!={'scope','run_id','work','review','workspace_relative','clock'} or facts['scope']!=scope
                or facts['run_id']!=work['id'] or facts['work']!=project.scenario.files.model_dump()
                or facts['review']!=review.model_dump() or facts['workspace_relative']!=project.workspace_relative(row['environment_id'])):
            raise ValueError('节点私有评审文件事实与原执行不一致')
        self._check_clock(facts['clock'])
        directory=self.manager.data/'cluster-scenario-inputs'/row['operation_id']
        private_directory(directory)
        atomic_json(directory/'prepared.json',facts)
        native=self.owner.native_directory(work['id'])
        request_path,state_path,decision_path=self.owner._plan_paths(row)
        configuration=self.manager.scenarios.execution_configuration(work['id'],row['source'],work['task']['quota_attempt'],
            native,request_path,decision_path,'/home/node/review',execution_files=facts)
        value=ScenarioConfiguration.model_validate(configuration)
        result=self.runner.sessions._call(row,'run-project-configure',{'scope':scope,'configuration':value.model_dump(by_alias=True)})
        if result!={'scope':scope,'configured':True}:
            raise ValueError('节点私有评审原driver配置回执无效')

    def accept_files(self, row: dict, project, facts: dict, transfer, directory) -> None:
        """核对原事实和每阶段完整对象，再保存原物化标记及中央任务状态。

        :param row: 原节点操作。
        :param project: 原冻结场景。
        :param facts: 节点真实文件回执。
        :param transfer: 已核对原SSH配置的固定归档传输器。
        :param directory: 本操作中央私有暂存目录。
        :return: None。
        """
        scope=row['record']['scope']
        files=project.scenario.files
        relative=f"environments/{row['environment_id']}/projects/{files.alias(row['environment_id'])}"
        if (set(facts)!={'scope','run_id','work','workspace_relative','inputs','clock'} or facts['scope']!=scope
                or facts['run_id']!=row['record']['work']['id'] or facts['work']!=files.model_dump()
                or facts['workspace_relative']!=relative):
            raise ValueError('节点场景实际文件回执与冻结原执行不一致')
        self._check_clock(facts['clock'])
        inputs=facts['inputs']
        code=inputs['code']
        expected={**files.inputs.code.model_dump(),'state':'ready'}
        if any(code.get(key)!=value for key,value in expected.items()) or set(code)-set(expected)-{'previous_digest','saved_relative'}:
            raise ValueError('节点场景代码来源回执不符')
        if set(code)-set(expected):
            prefix=f"environments/{row['environment_id']}/runtime/scenario-inputs/{files.inputs.scenario_id}/staging/"
            if (set(code)-set(expected)!={'previous_digest','saved_relative'}
                    or re.fullmatch('[a-f0-9]{64}',str(code['previous_digest'])) is None
                    or not safe_relative(code['saved_relative']).startswith(prefix)):
                raise ValueError('节点场景原现场保留定位无效')
        stages=self._stage_markers(files,project.scenario.catalog_release_id)
        if set(inputs)!={'code','stages','input_checkpoint_digest'} or set(inputs['stages'])!=set(stages):
            raise ValueError('节点场景准备阶段集合不符')
        for stage,(path,identity) in stages.items():
            record=inputs['stages'][stage]
            if set(record)!=set(identity)|{'input_checkpoint_digest'} or any(record.get(key)!=value for key,value in identity.items()):
                raise ValueError('节点场景准备阶段身份不符')
            receipt=WorkspaceSnapshotArchive.model_validate(self.runner._read(row,'run-scenario-input-archive',{'scope':scope,'stage':stage}))
            if receipt.scope.model_dump()!=scope or receipt.purpose!='candidate' or receipt.tree_digest!=record['input_checkpoint_digest']:
                raise ValueError('节点场景输入源码包与原阶段不一致')
            bundle=directory/(receipt.snapshot_id+'.tar')
            if not bundle.exists() and not bundle.is_symlink():
                transfer.download_scenario_input(row['environment_id'],row['operation_id'],receipt.snapshot_id,
                    bundle,receipt.sha256,receipt.bytes)
            snapshot=read_workspace_bundle(bundle,receipt,self.manager.objects)
            write_document(self.manager.manifests/(snapshot['digest']+'.json'),snapshot)
        if inputs['input_checkpoint_digest']!=inputs['stages'][next(reversed(stages))]['input_checkpoint_digest']:
            raise ValueError('节点场景最终输入摘要与最后阶段不符')
        task=self.manager.scenarios.task(files.inputs.task_id)
        if (task['instance_id']!=project.instance_id or task['generation']!=project.batch_generation
                or task['account_id']!=scope['account_id'] or task['workspace_relative'] not in (None,relative)):
            raise ValueError('原中央场景归属在文件准备期间发生变化')
        records={path:inputs['stages'][stage] for stage,(path,_) in stages.items()}
        root=self.manager.data/'project-artifacts'
        records[root/'task-inputs'/str(files.inputs.task_id)/'code-dependency.json']=code
        records[root/'scenarios'/str(files.inputs.scenario_id)/'materialized.json']={
            'scenario_id':files.inputs.scenario_id,'seed_digest':project.seed_digest,'workspace_relative':relative}
        for path,value in records.items():
            if path.exists() or path.is_symlink():
                if read_document(path)!=value:
                    raise ValueError('原中央场景输入标记与节点实际事实冲突')
            else:
                write_document(path,value)
        with self.manager.write_lock:
            connection=self.manager.database()
            try:
                with connection:
                    cursor=connection.execute('UPDATE project_scenario_instances SET workspace_relative=?,updated_at=? WHERE id=? '
                        'AND (workspace_relative IS NULL OR workspace_relative=?) AND instance_id=? '
                        'AND EXISTS(SELECT 1 FROM project_instances i JOIN project_iteration_batches b ON b.id=i.batch_id '
                        'WHERE i.id=project_scenario_instances.instance_id AND b.generation=? AND b.account_id=?)',
                        (relative,time.time(),files.inputs.scenario_id,relative,project.instance_id,project.batch_generation,scope['account_id']))
                    if cursor.rowcount!=1:
                        raise ValueError('原中央场景工作区CAS失败')
                    connection.execute('UPDATE project_scenario_tasks SET input_checkpoint_digest=? WHERE id=? AND scenario_instance_id=?',
                        (inputs['input_checkpoint_digest'],files.inputs.task_id,files.inputs.scenario_id))
            finally:
                connection.close()
        atomic_json(directory/'prepared.json',facts)
