"""中央经典项目文件消费者，节点负责实际目录，原管理器负责业务事务。"""
from __future__ import annotations

import base64
import hashlib
import os
import re
import time
from pathlib import Path
from uuid import uuid4

from account_runtime import RuntimeBusy
from cluster_legacy_projects import LegacyProjectWork
from cluster_project_plan import LegacyProjectPlan, ProjectPlanConfiguration, ProjectPlanDecision
from cluster_quota import QuotaFileChunk
from cluster_scenario_io import ClusterScenarioIO
from project_library import snapshot_tree, write_document
from runtime_files import atomic_json, private_directory
from system_update_contract import safe_read, strict_json


class ClusterLegacyProjectIO:
    """将原经典项目文件事实接回中央管理器。

    :param runner: 原远程Run协调器。
    :param manager: 原中央项目管理器。
    """

    def __init__(self, runner, manager) -> None:
        """登记原中央所有者。参数见类说明。:return: None。"""
        self.runner,self.manager = runner,manager
        self.scenarios=ClusterScenarioIO(self)
        self.programs=None

    def verify_scenario(self,job:dict,task:dict,source:dict,execution:dict,*,regression:bool=False,retry:bool=False) -> dict | None:
        """将原已释放场景的机械验收交给具体独立程序协调器。

        :param job: 原冻结候选作业。
        :param task: 原场景任务。
        :param source: 原已释放来源。
        :param execution: 原候选执行。
        :param regression: 是否执行原完整回归。
        :param retry: 原已知环境错误的有限复验。
        :return: 原节点完整报告；本机执行返回None。
        """
        if self.programs is None:
            if self.runner.for_run(execution['run_id']) is not None:
                raise ValueError('原远程场景独立程序协调器尚未准备')
            return None
        return self.programs.verify(job,task,source,execution,regression=regression,retry=retry)

    def binding(self, run_id: str) -> LegacyProjectWork | None:
        """冻结本次原实例，未接通的工作流保留明确门禁。

        :param run_id: 原运行。
        :return: 经典实例定位；普通运行返回None。
        """
        context = self.manager.run_context(run_id)
        if context is None:
            return None
        if not self.manager.can_start(run_id):
            raise RuntimeBusy('原经典项目需要等待批次、窗口或额度门禁')
        library = self.manager._release(context['catalog_release_id'])
        if context.get('scenario_execution'):
            return LegacyProjectWork(instance_id=context['id'],attempt_id=context['attempt_id'],
                batch_generation=context['attempt_generation'],library_digest=library.digest,project_key=context['project_key'],
                seed_digest=context['seed_digest'],started=bool(context['workspace_relative']),scenario=self.scenarios.binding(context))
        if library.schema!=1:
            raise ValueError('原经典项目内容合同需要核对')
        return LegacyProjectWork(instance_id=context['id'],attempt_id=context['attempt_id'],
            batch_generation=context['attempt_generation'],library_digest=library.digest,
            project_key=context['project_key'],seed_digest=context['seed_digest'],started=bool(context['workspace_relative']),
            plan=LegacyProjectPlan(id=context['plan_id'],execution_id=context['plan_execution_id'],phase_seq=context['phase_seq'],
                step_id=context['step_id'],session_id=context['session_id']) if context.get('plan_id') else None)

    def accept(self, row: dict) -> dict:
        """核对原节点物化事实并CAS保存中央实例归属。

        :param row: 原冻结节点执行。
        :return: 原事实，供后续原生镜像读取。
        """
        work = row['record']['work']
        project = LegacyProjectWork.model_validate(work['project'])
        scope = row['record']['scope']
        facts = self.runner._read(row,'run-project-facts',scope)
        if facts=={'scope':scope,'unsubmitted':True}:
            return facts
        relative = project.workspace_relative(scope['environment_id'])
        if (set(facts)!={'scope','project','workspace_relative','start','end','files'}
                or facts['scope']!=scope or facts['project']!=project.model_dump() or facts['workspace_relative']!=relative):
            raise ValueError('原经典项目物化事实与冻结范围不符')
        for field in ('start','end','files'):
            values=facts[field]
            if field=='end' and values is None:
                continue
            if (not isinstance(values,dict) or len(values)>512 or any(not isinstance(name,str)
                    or re.fullmatch(r'[A-Za-z0-9_-]{1,128}\.jsonl',name) is None
                    or type(size) is not int or not 0<=size<=64*1024*1024*1024 for name,size in values.items())):
                raise ValueError('原经典项目原生边界超过受限合同')
        if project.scenario is not None:
            context=self.manager.scenarios.context(work['id'])
            review=project.scenario.review is not None
            if (not context or context['role']!=('review' if review else 'candidate') or context['execution_id']!=project.scenario.execution_id
                    or context['scenario_task_id']!=project.scenario.files.inputs.task_id or context['account_id']!=scope['account_id']
                    or context['id']!=project.instance_id or not review and context['workspace_relative']!=relative):
                raise ValueError('原中央场景与实际节点原生文件不一致')
            self._record_start(work['id'],facts['start'])
            return facts
        with self.manager.write_lock:
            connection = self.manager.database()
            try:
                with connection:
                    current = connection.execute('SELECT i.*,a.run_id,b.account_id,b.catalog_release_id FROM project_instances i '
                        'JOIN project_step_attempts a ON a.instance_id=i.id JOIN project_iteration_batches b ON b.id=i.batch_id '
                        'WHERE i.id=? AND a.id=?',(project.instance_id,project.attempt_id)).fetchone()
                    if (current is None or current['run_id']!=work['id'] or current['account_id']!=scope['account_id']
                            or current['seed_digest']!=project.seed_digest or current['project_key']!=project.project_key
                            or current['workspace_relative'] not in (None,relative)):
                        raise ValueError('原中央经典实例与节点物化事实不一致')
                    now=time.time()
                    connection.execute('UPDATE project_instances SET workspace_relative=?,started_at=COALESCE(started_at,?),updated_at=? '
                        'WHERE id=? AND (workspace_relative IS NULL OR started_at IS NULL)',(relative,now,now,project.instance_id))
            finally:
                connection.close()
        seed_path=self.manager.manifests/(project.seed_digest+'.json')
        if seed_path.is_symlink():
            raise ValueError('原中央项目seed清单不能为链接')
        if not seed_path.exists():
            # 实际工作区已在Node物化；中央仍须保留原seed对象供原checkpoint合同核对。
            library=self.manager._release(current['catalog_release_id'])
            if library.digest!=project.library_digest:
                raise ValueError('原中央项目内容摘要发生变化')
            seed=snapshot_tree(library.projects[project.project_key].root/'seed',self.manager.objects)
            if seed['digest']!=project.seed_digest:
                raise ValueError('原中央项目seed与冻结事实不符')
            write_document(seed_path,seed)
        self._record_start(work['id'],facts['start'])
        return facts

    def _record_start(self, run_id: str, sizes: dict) -> None:
        root=self.manager.data/'project-artifacts/runs'/run_id
        start=root/'native-start.json'
        if start.exists() or start.is_symlink():
            if strict_json(safe_read(start,96*1024,private=True),96*1024)!=sizes:
                raise ValueError('原经典项目首次原生字节起点已变化')
        else:
            write_document(start,sizes)

    def permit(self, row: dict) -> None:
        """保存物化后复核原批次，放行本次实际监督器。

        :param row: 原节点已准备执行。
        :return: None；未知放行仍由原执行账本收口。
        """
        if self.accept(row).get('unsubmitted') is True:
            raise RuntimeBusy('原节点项目已确认尚未实际执行并已关闭')
        work=row['record']['work']
        if not self.manager.can_start(work['id']):
            raise RuntimeBusy('原经典项目在实际放行前已暂停或停止')
        if work['project'].get('scenario') is not None:
            self.manager.scenarios.permit_start(work['id'],row['source'])
        result=self.runner.sessions._call(row,'run-project-permit',row['record']['scope'])
        if result!={'scope':row['record']['scope'],'permitted':True}:
            raise ValueError('原经典项目监督放行回执无效')

    def native_directory(self, run_id: str) -> Path | None:
        """同步原Scope具体会话的有界字节，供原中央证据解析器使用。

        :param run_id: 原运行。
        :return: root私有镜像；本机项目返回None。
        """
        row=self.runner.for_run(run_id)
        if row is None or row['record']['work'].get('project') is None:
            return None
        with self.runner.sessions._operation_lock('legacy-native:'+run_id):
            facts=self.accept(row)
            root=self.manager.data/'cluster-project-native'/row['operation_id']
            private_directory(root)
            if facts.get('unsubmitted') is True:
                atomic_json(root/'unsubmitted.json',{'scope':row['record']['scope'],'unsubmitted':True})
                return root
            project=LegacyProjectWork.model_validate(row['record']['work']['project'])
            plan=project.execution_plan()
            fixed=plan.session_id+'.jsonl' if plan else None
            boundaries=facts['end'] if facts['end'] is not None else facts['files']
            selected_files={name:size for name,size in boundaries.items()
                if size!=facts['start'].get(name,0) or name==fixed}
            if sum(selected_files.values())>64*1024*1024:
                raise ValueError('本轮经典项目会话传输超过64MiB受限范围')
            for name,size in selected_files.items():
                temporary=root/('.'+uuid4().hex)
                identity=None
                try:
                    with temporary.open('xb') as output:
                        temporary.chmod(0o600)
                        offset=0
                        while offset<size:
                            limit=min(128*1024,size-offset)
                            result=self.runner._read(row,'run-project-native',{'scope':row['record']['scope'],
                                'name':name,'offset':offset,'limit':limit})
                            if result.get('scope')!=row['record']['scope'] or result.get('name')!=name:
                                raise ValueError('原经典项目会话字节来自其他执行')
                            chunk=QuotaFileChunk.model_validate({key:value for key,value in result.items() if key not in ('scope','name')})
                            content=base64.b64decode(chunk.content,validate=True)
                            if (chunk.offset!=offset or chunk.size<size or not content or len(content)>limit
                                    or chunk.file_identity is None or identity is not None and identity!=chunk.file_identity):
                                raise ValueError('原经典项目会话在读取时被替换或截断')
                            identity=chunk.file_identity
                            selected=content[:size-offset]
                            output.write(selected)
                            offset+=len(selected)
                        output.flush()
                        os.fsync(output.fileno())
                    os.replace(temporary,root/name)
                finally:
                    temporary.unlink(missing_ok=True)
            # 只读镜像的文件集由本次节点清单决定，旧镜像文件不能成为新的会话证据。
            for path in root.glob('*.jsonl'):
                if path.name not in selected_files:
                    path.unlink()
            if facts['end'] is not None:
                write_document(self.manager.data/'project-artifacts/runs'/run_id/'native-end.json',facts['end'])
            return root

    def capture(self, instance: dict) -> dict | None:
        """取得原当前步骤的冻结源码包，沿原对象存储验收。

        :param instance: 原中央实例。
        :return: 原snapshot_tree清单；本机项目返回None。
        """
        if 'scenario_instance_id' in instance:
            attempt=self.manager._one("SELECT run_id FROM project_task_executions WHERE task_id=? AND role='candidate' ORDER BY id DESC LIMIT 1",(instance['id'],))
        else:
            attempt=self.manager._one('SELECT run_id FROM project_step_attempts WHERE instance_id=? ORDER BY id DESC LIMIT 1',(instance['id'],))
        row=self.runner.for_run(attempt['run_id']) if attempt else None
        if row is None or row['record']['work'].get('project') is None:
            return None
        project=LegacyProjectWork.model_validate(row['record']['work']['project'])
        expected_id=instance['instance_id'] if project.scenario is not None else instance['id']
        if project.instance_id!=expected_id or (project.scenario is not None and project.scenario.files.inputs.task_id!=instance['id']):
            raise ValueError('原经典项目候选属于其他实例')
        phase=''
        if project.plan is not None:
            execution=self.manager._one('SELECT phase_seq FROM project_plan_executions WHERE run_id=?',(attempt['run_id'],))
            if execution is None:
                raise ValueError('原计划候选阶段缺失')
            phase=':'+str(execution['phase_seq'])
        snapshot_id=hashlib.sha256(('legacy-candidate:'+row['operation_id']+phase).encode()).hexdigest()[:32]
        return self.runner.sessions.snapshot(row['operation_id'],snapshot_id,self.manager.objects)

    def _plan_paths(self, row: dict) -> tuple[Path,Path,Path]:
        root=self.manager.data/'cluster-project-control'/row['operation_id']
        private_directory(root)
        handle=hashlib.sha256(row['source'].encode()).hexdigest()[:20]
        controls=root/handle
        private_directory(controls)
        return root/'project-plan-request.json',root/'project-plan-state.json',controls/'project-plan-decision.json'

    def prepare(self, row: dict) -> None:
        """实际exec前准备原文件，并让原中央管理器保存计划事务。

        :param row: 已取得真实许可并开始心跳的原操作。
        :return: None；失败由原账本恢复收口。
        """
        work=row['record']['work']
        project=LegacyProjectWork.model_validate(work['project'])
        if project.scenario is not None:
            self.scenarios.prepare(row,project)
            return
        if project.plan is None:
            return
        request={'scope':row['record']['scope'],'work':work}
        result=self.runner.sessions._call(row,'run-project-prepare',request)
        if result!={'scope':row['record']['scope'],'prepared':True}:
            raise ValueError('原同会话计划文件准备回执无效')
        native=self.native_directory(work['id'])
        request_path,state_path,decision_path=self._plan_paths(row)
        configuration=self.manager.plans.execution_configuration(work['id'],row['source'],work['task']['quota_attempt'],
            native,request_path,decision_path,'/home/node/projects/'+project.alias(row['environment_id']))
        value=ProjectPlanConfiguration.model_validate(configuration)
        result=self.runner.sessions._call(row,'run-project-configure',{'scope':row['record']['scope'],
            'configuration':value.model_dump(by_alias=True)})
        if result!={'scope':row['record']['scope'],'configured':True}:
            raise ValueError('原同会话计划配置发布回执无效')

    def sync_plan(self, run_id: str) -> None:
        """在原证据解析前镜像具体driver通知、输入状态及原生字节。

        :param run_id: 原计划Run。
        :return: None；本机原计划保持原路径。
        """
        row=self.runner.for_run(run_id)
        if row is None or not row['record']['work'].get('project'):
            return
        if LegacyProjectWork.model_validate(row['record']['work']['project']).execution_plan() is None:
            return
        native=self.native_directory(run_id)
        if native is not None and (native/'unsubmitted.json').exists():
            proof=strict_json(safe_read(native/'unsubmitted.json',16384,private=True),16384)
            if proof!={'scope':row['record']['scope'],'unsubmitted':True}:
                raise ValueError('原节点未执行回执属于其他Scope')
            return
        request_path,state_path,decision_path=self._plan_paths(row)
        artifacts=[('project-plan-request.json',request_path),('project-plan-state.json',state_path)]
        if row['record']['work']['project'].get('scenario') is not None:
            artifacts.append(('project-work.json',request_path.with_name('project-work.json')))
        for name,path in artifacts:
            raw=self.runner.artifact(run_id,name)
            if raw is None:
                path.unlink(missing_ok=True)
                continue
            document=strict_json(raw,65536)
            if document.get('source')!=row['source']:
                source=document.get('source')
                previous=re.fullmatch(r'run:([a-f0-9]{12}):([0-9]+)',source) if isinstance(source,str) else None
                if (previous and previous[1]==run_id
                        and int(previous[2])<row['record']['work']['task']['quota_attempt']):
                    # 原driver复用上一额度尝试的输入状态；中央当前尝试只消费自己的新通知。
                    path.unlink(missing_ok=True)
                    continue
                raise ValueError('原同会话计划通知来自其他source')
            write_document(path,document)

    def plan_running(self, execution: dict) -> bool:
        """确认原计划正在本次实际节点执行，准备窗口保留原现场。

        :param execution: 原中央计划执行行。
        :return: 当前source已取得实际启动回执，本机执行沿原路径。
        """
        row=self.runner.for_run(execution['run_id'])
        return row is None or row['phase']=='running' and row['source']==execution['source']

    def publish_decision(self, execution: dict, document: dict) -> None:
        """原中央事务落盘后发布具体阶段决定。

        :param execution: 原计划执行行。
        :param document: 原持久决定。
        :return: None；本机项目沿原控制文件。
        """
        row=self.runner.for_run(document['run_id'])
        if row is None:
            return
        value=ProjectPlanDecision.model_validate(document)
        if row['source']!=execution['source'] or value.source!=row['source']:
            raise ValueError('原计划决定与原执行来源不一致')
        result=self.runner.sessions._call(row,'run-project-decision',{'scope':row['record']['scope'],
            'decision':value.model_dump(by_alias=True,exclude_none=True)})
        expected={'scope':row['record']['scope'],'phase_seq':value.phase_seq,
            'sha256':hashlib.sha256(value.model_dump_json(by_alias=True,exclude_none=True).encode()).hexdigest()}
        if result!=expected:
            raise ValueError('原计划决定发布回执无效')
