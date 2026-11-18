"""中央场景独立程序账本，原CLI已释放后单独保护启动、收口与完整报告。"""
from __future__ import annotations

import hashlib
import threading
import time
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictInt, StrictStr

from cluster_program_verification import RemoteProgramVerification
from cluster_runs import RunWork
from cluster_ssh import NodeSshError
from cluster_verification import RunVerificationStart, VerificationReference, VerificationState
from project_library import digest_json, safe_relative
from runtime_files import atomic_json, private_directory
from system_update_contract import safe_read, strict_json


class RunProgramRecord(BaseModel):
    """原具体机械验收的持久中央记录。

    :param job_id: 原中央候选评测作业。
    :param node_id: 原实际节点。
    :param node_config_sha256: 本次冻结SSH配置。
    :param request: 原独立程序有限启动许可。
    :param phase: 已登记、待核对或实际收口阶段。
    :param state: 原Node回执。
    :param error_reason: 原环境故障且已确认停止的中央事实，用于原一次有限复验。
    """

    model_config=ConfigDict(extra='forbid')
    job_id: StrictInt=Field(ge=1)
    node_id: StrictInt=Field(ge=1)
    node_config_sha256: StrictStr=Field(pattern='^[a-f0-9]{64}$')
    request: RunVerificationStart
    phase: Literal['registered','reconcile','complete','cancelled']='registered'
    state: VerificationState | None=None
    error_reason: Literal['timeout','node_restart','preparation_failed','control_restart'] | None=None


class RemoteRunPrograms(RemoteProgramVerification):
    """持久保护原候选的机械验收，更新及迁移门禁复用同一活动事实。

    :param io: 原ClusterLegacyProjectIO。
    :param owner_lock: 原账号owner锁提供器，和迁移/凭据交接共用。
    :param observation_grace: 传输中断后仅查询原尝试的最长恢复窗口。
    """

    def __init__(self,io,owner_lock,*,observation_grace:float=30.0) -> None:
        """保存原依赖并恢复持久活动。参数见类说明。:return: None。"""
        self.io,self.sessions,self.owner_lock=io,io.runner.sessions,owner_lock
        if not 0<observation_grace<=30:
            raise ValueError('独立程序观察恢复窗口无效')
        self.observation_grace=observation_grace
        self.root=io.manager.data/'cluster-run-programs'
        private_directory(self.root)
        self.lock,self.activities=threading.RLock(),{}
        self.executing={}
        self.closing=False
        for path in self.root.glob('*/record.json'):
            try:
                record=self._read(path)
            except (OSError,ValueError):
                # 损坏记录仍占更新名额；只读账号门禁报告需要核对，管理入口继续启动。
                self.activities[path.parent.name]=self.sessions.activity_gate.restore_reserved('remote-program:'+path.parent.name)
                continue
            if record.phase not in ('complete','cancelled'):
                self.activities[record.request.attempt_id]=self.sessions.activity_gate.restore_reserved(
                    'remote-program:'+record.request.attempt_id)

    def _read(self,path:Path) -> RunProgramRecord:
        record=RunProgramRecord.model_validate(strict_json(safe_read(path,2*1024*1024,private=True),2*1024*1024))
        if path.parent.name!=record.request.attempt_id:
            raise ValueError('中央独立程序记录与原尝试不一致')
        if record.state is not None:
            self._receipt(record.request,record.state.model_dump())
        if record.phase in ('complete','cancelled') and (record.state is None or record.state.phase!=record.phase):
            raise ValueError('中央独立程序终态缺少原停止回执')
        return record

    def active(self,account_id:int | None=None) -> list[RunProgramRecord]:
        """读取尚未实际收口的程序，用于原账号迁移和更新排空。

        :param account_id: 需要检查的原账号，省略时读取全部。
        :return: 原持久活动列表，坏记录抛错保留门禁。
        """
        with self.lock:
            return [record for path in self.root.glob('*/record.json')
                if (record:=self._read(path)).phase not in ('complete','cancelled')
                and (account_id is None or record.request.scope.account_id==account_id)]

    def _row(self,record:RunProgramRecord) -> dict:
        row=self.sessions.ledger.get(record.request.scope.operation_id)
        if (row['record']['scope']!=record.request.scope.model_dump() or row['node_id']!=record.node_id
                or row['record']['node_config_sha256']!=record.node_config_sha256 or row['phase']!='closed'):
            raise ValueError('原独立程序的候选Scope或实际释放事实已变化')
        return row

    def _save(self,record:RunProgramRecord) -> None:
        atomic_json(self.root/record.request.attempt_id/'record.json',record.model_dump())

    def _finish(self,record:RunProgramRecord,state:VerificationState) -> None:
        if state.phase not in ('complete','cancelled'):
            raise ValueError('原独立程序尚未实际停止')
        record.phase=state.phase
        record.state=state
        latest=self._read(self.root/record.request.attempt_id/'record.json')
        record.error_reason=record.error_reason or latest.error_reason
        self._save(record)
        self.sessions.activity_gate.release_reserved(self.activities.pop(record.request.attempt_id,None))

    def cancel(self,record:RunProgramRecord) -> None:
        """沿原节点和尝试确认实际取消，未知状态保留原活动。

        :param record: 原持久记录。
        :return: None；失败保留更新与账号排空占用。
        """
        with self.lock:
            row=self._row(record)
            state=self._receipt(record.request,self.sessions._call(row,'run-verification-cancel',record.request.model_dump()))
            self._finish(record,state)

    def recover(self) -> list[str]:
        """重启先收口原独立程序，失败活动继续保持待核对。

        :return: 仍需核对的具体尝试ID。
        """
        pending=[]
        for path in self.root.glob('*/record.json'):
            try:
                record=self._read(path)
            except (OSError,ValueError):
                pending.append(path.parent.name)
                continue
            if record.phase in ('complete','cancelled'):
                continue
            try:
                self.cancel(record)
                if record.phase=='cancelled' or record.state.report and record.state.report.status=='cancelled':
                    record.error_reason='control_restart'
                    self._save(record)
            except Exception:
                record.phase='reconcile'
                self._save(record)
                pending.append(record.request.attempt_id)
        return pending

    def close(self) -> list[str]:
        """关闭新独立程序并沿原尝试实际收口。:return: 仍待核对的尝试ID。"""
        with self.lock:
            self.closing=True
        return self.recover()

    def recover_pending(self) -> list[str]:
        """由原Run恢复线程收口已结束前台观察的未决程序。

        :return: 本轮仍待核对的具体尝试。
        """
        pending=[]
        with self.lock:
            attempts=list(self.activities)
        for attempt in attempts:
            with self.lock:
                if self.executing.get(attempt,0):
                    continue
                try:
                    record=self._read(self.root/attempt/'record.json')
                    if record.phase!='reconcile':
                        continue
                    self.cancel(record)
                    if record.phase=='cancelled' or record.state.report and record.state.report.status=='cancelled':
                        record.error_reason='control_restart'
                        self._save(record)
                except Exception:
                    pending.append(attempt)
        return pending

    def _cancelled(self,job:dict) -> bool:
        parent=self.io.manager._one('SELECT b.status,b.generation FROM project_evaluation_jobs j '
            'JOIN project_scenario_tasks t ON t.id=j.task_id JOIN project_scenario_instances s ON s.id=t.scenario_instance_id '
            'JOIN project_instances i ON i.id=s.instance_id JOIN project_iteration_batches b ON b.id=i.batch_id WHERE j.id=?',(job['id'],))
        return (self.closing or parent is None or parent['generation']!=job['generation']
            or parent['status'] not in ('active','pausing','paused'))

    def _query(self,record:RunProgramRecord,deadline:float) -> VerificationState:
        until=min(deadline,time.monotonic()+self.observation_grace)
        reference=VerificationReference(scope=record.request.scope,attempt_id=record.request.attempt_id).model_dump()
        while True:
            try:
                value=self.sessions._call(self._row(record),'run-verification-get',reference)
            except (NodeSshError,OSError,ValueError) as error:
                transient=(isinstance(error,NodeSshError) and error.reason in ('timeout','connection_failed','remote_command_failed')
                    or isinstance(error,OSError) or type(error) is ValueError
                    and str(error)=='节点环境准备失败，请检查执行组件、环境归属与资源')
                if not transient or time.monotonic()>=until:
                    raise
                with self.lock:
                    current=self._read(self.root/record.request.attempt_id/'record.json')
                    if current.phase not in ('complete','cancelled'):
                        record.phase='reconcile'
                        self._save(record)
                # 仅恢复同一程序的只读观察，不提交启动、模型输入或新的RT刷新。
                time.sleep(min(0.5,max(0,until-time.monotonic())))
            else:
                return self._receipt(record.request,value)

    def verify(self,job:dict,task:dict,source:dict,execution:dict,*,regression:bool=False,retry:bool=False) -> dict | None:
        """执行原场景冻结合同，启动响应未知只查询同一原尝试。

        :param job: 原中央候选评测作业。
        :param task: 原冻结场景任务。
        :param source: 已严格释放的原执行来源。
        :param execution: 原候选执行。
        :param regression: 是否执行冻结完整回归。
        :param retry: 原管理器明确要求的第二次已知环境错误复验。
        :return: 原完整报告；原本机执行返回None。
        """
        attempt=hashlib.sha256(f"scenario-native:{job['id']}:{int(regression)}:{int(retry)}".encode()).hexdigest()[:32]
        with self.lock:
            self.executing[attempt]=self.executing.get(attempt,0)+1
        try:
            return self._verify(job,task,source,execution,attempt,regression=regression,retry=retry)
        finally:
            with self.lock:
                count=self.executing[attempt]-1
                if count:
                    self.executing[attempt]=count
                else:
                    self.executing.pop(attempt)

    def _verify(self,job:dict,task:dict,source:dict,execution:dict,attempt:str,*,regression:bool,retry:bool) -> dict | None:
        account=self.io.manager._one('SELECT * FROM accounts WHERE id=(SELECT account_id FROM runs WHERE id=?)',(execution['run_id'],))
        if account is None:
            raise ValueError('原机械验收账号缺失')
        row=self.sessions.ledger.by_source(account['id'],source['source'],active_only=False)
        if row is None:
            return None
        if (row['phase']!='closed' or not source['released_at'] or source['execution_error'] or execution['ended_at'] is None):
            raise ValueError('机械验收需要原候选及CLI已严格释放')
        work=RunWork.model_validate(row['record']['work'])
        project=work.project
        if (project is None or project.scenario is None or project.scenario.review is not None
                or project.scenario.files.inputs.task_id!=task['id'] or work.id!=execution['run_id']):
            raise ValueError('机械验收与原候选任务不一致')
        scenario=project.scenario
        library=self.io.manager._release(task['catalog_release_id'])
        answer=strict_json(safe_read(self.io.manager.data/safe_relative(job['answer_relative']),512*1024,private=True),512*1024)['text']
        request=RunVerificationStart(scope=row['record']['scope'],attempt_id=attempt,
            snapshot_id=hashlib.sha256(('legacy-candidate:'+row['operation_id']).encode()).hexdigest()[:32],
            candidate_digest=job['candidate_digest'],library_digest=library.digest,project_key=task['project_key'],
            objective_id=scenario.files.task_key,definition_digest=digest_json(strict_json(task['definition_json'].encode(),4*1024*1024)),
            answer=answer,regression=regression,not_after=int(time.time())+30)
        directory=self.root/attempt
        with self.owner_lock(account['name']),self.lock:
            if self.closing:
                raise ValueError('原独立程序协调器正在关闭')
            path=directory/'record.json'
            existing=path.exists() or path.is_symlink()
            if existing:
                record=self._read(path)
                if (record.job_id!=job['id'] or record.node_id!=row['node_id']
                        or record.request.model_dump(exclude={'not_after'})!=request.model_dump(exclude={'not_after'})):
                    raise ValueError('原独立程序冻结输入已变化')
                request=record.request
            else:
                account=self.io.manager._one('SELECT * FROM accounts WHERE id=?',(account['id'],))
                if account is None:
                    raise ValueError('原独立程序账号已删除')
                assignment=self.sessions.service.store.assignment(account['id'])
                if (not account['enabled'] or account['deleted_at'] is not None or assignment['phase']!='ready'
                        or account['cc2api_account_id']!=request.scope.gateway_account_id
                        or assignment['node_id']!=row['node_id'] or assignment['revision']!=request.scope.assignment_revision):
                    raise ValueError('独立程序启动前原账号归属已变化')
                if retry:
                    previous=hashlib.sha256(f"scenario-native:{job['id']}:{int(regression)}:0".encode()).hexdigest()[:32]
                    original=self._read(self.root/previous/'record.json')
                    known_error=(original.phase=='complete' and original.state.report is not None
                        and original.state.report.status=='error')
                    if not known_error and not (original.phase in ('complete','cancelled') and original.error_reason is not None):
                        raise ValueError('第二次程序复验需要原已知环境错误完整回执')
                private_directory(directory)
                activity=self.sessions.activity_gate.reserve('remote-program:'+attempt)
                record=RunProgramRecord(job_id=job['id'],node_id=row['node_id'],
                    node_config_sha256=row['record']['node_config_sha256'],request=request)
                try:
                    self._save(record)
                except Exception:
                    self.sessions.activity_gate.release_reserved(activity)
                    raise
                self.activities[attempt]=activity
        if record.phase=='cancelled':
            if record.error_reason is not None:
                return {'status':'error','message':'原节点独立程序环境中断并已确认停止'}
            raise ValueError('原独立程序已取消，保留具体恢复记录')
        try:
            if record.phase=='complete':
                report=self._download_report(row,request,record.state,directory,run=True)
                if report['status']=='cancelled':
                    if record.error_reason is not None:
                        return {'status':'error','message':'原节点独立程序环境中断并已确认停止'}
                    raise ValueError('原独立程序已取消，保留原报告')
                return report
            profile=library.environments[library.projects[task['project_key']].manifest['environment']]
            deadline=time.monotonic()+profile['regression' if regression else 'business']['timeout_sec']+120
            if self._cancelled(job):
                self.cancel(record)
                raise ValueError('原批次已停止或变化，独立程序已确认取消')
            if existing:
                state=self._query(record,deadline)
            else:
                try:
                    value=self.sessions._call(row,'run-verification-start',request.model_dump())
                except Exception:
                    state=self._query(record,deadline)
                else:
                    state=self._receipt(request,value)
            while state.phase in ('starting','running'):
                if self._cancelled(job):
                    self.cancel(record)
                    raise ValueError('原批次已停止或变化，独立程序已确认取消')
                if time.monotonic()>=deadline:
                    self.cancel(record)
                    record.error_reason='timeout'
                    self._save(record)
                    return {'status':'error','message':'原节点独立程序超时并已确认停止'}
                time.sleep(0.25)
                state=self._query(record,deadline)
            if state.phase!='complete':
                self.cancel(record)
                record.error_reason='node_restart' if state.failure_type=='NodeRestart' else 'preparation_failed'
                self._save(record)
                return {'status':'error','message':'原节点独立程序环境中断并已确认停止'}
            report=self._download_report(row,request,state,directory,run=True)
            with self.lock:
                self._finish(record,state)
            if report['status']=='cancelled':
                raise ValueError('原独立程序已取消，保留原报告')
            return report
        except Exception:
            with self.lock:
                latest=self._read(directory/'record.json')
                if latest.phase not in ('complete','cancelled'):
                    record.phase='reconcile'
                    self._save(record)
            raise
