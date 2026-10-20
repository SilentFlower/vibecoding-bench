"""同一次 CLI 的持久多步计划、逐步验收及中断接续。"""
from __future__ import annotations

import json
import hashlib
import os
import random
import re
import time
import uuid
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from stat import S_ISREG
from typing import TYPE_CHECKING, Callable

from project_library import canonical_json, digest_json, read_document, safe_relative, write_document

if TYPE_CHECKING:
    from project_iteration import ProjectIterationManager


PLAN_SCHEMA = '''
CREATE TABLE IF NOT EXISTS project_execution_plans (
  id INTEGER PRIMARY KEY AUTOINCREMENT, instance_id INTEGER NOT NULL,
  generation INTEGER NOT NULL, start_index INTEGER NOT NULL, target_index INTEGER NOT NULL,
  completed_steps INTEGER NOT NULL DEFAULT 0, session_id TEXT NOT NULL,
  execution_json TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'ready', error TEXT,
  created_at REAL NOT NULL, updated_at REAL NOT NULL, ended_at REAL,
  FOREIGN KEY(instance_id) REFERENCES project_instances(id)
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_project_plan_open_instance
  ON project_execution_plans(instance_id) WHERE status IN ('ready','running','finalizing','quota_wait');
CREATE TABLE IF NOT EXISTS project_plan_executions (
  id INTEGER PRIMARY KEY AUTOINCREMENT, plan_id INTEGER NOT NULL, run_id TEXT NOT NULL UNIQUE,
  quota_attempt INTEGER NOT NULL DEFAULT 0, source TEXT, phase_seq INTEGER NOT NULL DEFAULT 0,
  current_attempt_id INTEGER, request_relative TEXT, decision_relative TEXT, native_relative TEXT,
  cwd TEXT, evidence_start_json TEXT, decision_json TEXT,
  not_before REAL NOT NULL DEFAULT 0, released_at REAL, released_quota_attempt INTEGER,
  execution_error TEXT, created_at REAL NOT NULL, ended_at REAL,
  FOREIGN KEY(plan_id) REFERENCES project_execution_plans(id), FOREIGN KEY(run_id) REFERENCES runs(id)
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_project_plan_open_execution
  ON project_plan_executions(plan_id) WHERE ended_at IS NULL;
'''

PLAN_DEFAULTS = {'schema':2, 'concurrency':2, 'active_projects':3, 'rotation_steps':5,
    'steps_per_plan':2, 'timeout_sec':1800, 'interval_min_sec':0, 'interval_max_sec':0, 'repair_limit':2}
RUN_TERMINAL = {'success','failed','timeout','stopped','auth_failed'}


def initialize_plan_schema(connection) -> None:
    """幂等增加计划结构并保留旧尝试主键，移除单 Run 唯一限制。

    :param connection: 已初始化基础项目表的 SQLite 连接。
    :return: None；迁移异常回滚尝试表，不删除历史成果。
    """
    connection.executescript(PLAN_SCHEMA)
    try:
        connection.execute('BEGIN IMMEDIATE')
        indexes = connection.execute("SELECT sql FROM sqlite_master WHERE type='index' AND tbl_name='project_step_attempts' AND sql IS NOT NULL").fetchall()
        unique_run = False
        for index in connection.execute('PRAGMA index_list(project_step_attempts)'):
            if index['unique'] and [item['name'] for item in connection.execute('PRAGMA index_info("'+index['name'].replace('"','""')+'")')]==['run_id']:
                unique_run = True
        if unique_run:
            original = connection.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='project_step_attempts'").fetchone()['sql']
            replacement, count = re.subn(r'\brun_id\s+TEXT\s+NOT\s+NULL\s+UNIQUE\b', 'run_id TEXT NOT NULL', original, flags=re.I)
            if count!=1:
                raise ValueError('旧项目尝试表结构未知，不能猜测重建')
            replacement = re.sub(r'CREATE TABLE\s+(?:IF NOT EXISTS\s+)?["`\[]?project_step_attempts["`\]]?',
                'CREATE TABLE project_step_attempts_upgrade', replacement, count=1, flags=re.I)
            columns = [item['name'] for item in connection.execute('PRAGMA table_info(project_step_attempts)')]
            quoted = ','.join('"'+name.replace('"','""')+'"' for name in columns)
            sequence = None
            if connection.execute("SELECT 1 FROM sqlite_master WHERE name='sqlite_sequence'").fetchone():
                sequence = connection.execute("SELECT seq FROM sqlite_sequence WHERE name='project_step_attempts'").fetchone()
            connection.execute(replacement)
            connection.execute(f'INSERT INTO project_step_attempts_upgrade({quoted}) SELECT {quoted} FROM project_step_attempts')
            connection.execute('DROP TABLE project_step_attempts')
            connection.execute('ALTER TABLE project_step_attempts_upgrade RENAME TO project_step_attempts')
            for index in indexes:
                connection.execute(index['sql'])
            if sequence:
                connection.execute("UPDATE sqlite_sequence SET seq=MAX(seq,?) WHERE name='project_step_attempts'",(sequence['seq'],))
        additions = {
            'project_step_attempts': {'plan_id':'INTEGER', 'phase_seq':'INTEGER', 'expected_prompt':'TEXT',
                'native_start_json':'TEXT', 'native_end_json':'TEXT', 'fenced_at':'REAL', 'fenced_source':'TEXT'},
            'project_instances': {'initial_order':'INTEGER', 'in_pool':'INTEGER NOT NULL DEFAULT 0',
                'visit_completed':'INTEGER NOT NULL DEFAULT 0'},
            'project_iteration_batches': {'launches_started':'INTEGER NOT NULL DEFAULT 0', 'last_launch_at':'REAL', 'wait_reason':'TEXT'},
            'project_plan_executions': {'native_relative':'TEXT','cwd':'TEXT','evidence_start_json':'TEXT','decision_json':'TEXT'},
        }
        for table, fields in additions.items():
            present = {item['name'] for item in connection.execute(f'PRAGMA table_info({table})')}
            for name, kind in fields.items():
                if name not in present:
                    connection.execute(f'ALTER TABLE {table} ADD COLUMN {name} {kind}')
        connection.execute('CREATE INDEX IF NOT EXISTS idx_project_attempts_run ON project_step_attempts(run_id,id)')
        connection.commit()
    except Exception:
        connection.rollback()
        raise


def normalized_policy(values: dict, project_count: int, maximum_steps: int, account_limit: int) -> dict:
    """校验新策略并解析省略的默认并发，不静默夹取显式输入。

    :param values: 创建请求中提供的策略。
    :param project_count: 选中项目数量。
    :param maximum_steps: 冻结路线的最大步数。
    :param account_limit: 真实账号 CLI 上限。
    :return: 可持久化的完整 schema 2 策略。
    """
    allowed = set(PLAN_DEFAULTS)-{'schema','repair_limit'}
    if set(values)-allowed:
        raise ValueError('项目调度参数包含未知字段')
    policy = {**PLAN_DEFAULTS, **values}
    if any(type(value) is not int for value in policy.values()):
        raise ValueError('项目调度参数必须为整数')
    if not 1<=policy['active_projects']<=100:
        raise ValueError('活动项目池须为 1～100')
    capacity = min(2, account_limit, project_count, policy['active_projects'])
    if 'concurrency' not in values:
        policy['concurrency'] = capacity
    if not 1<=policy['concurrency']<=capacity:
        raise ValueError('并发超过账号或活动项目的真实容量')
    for field in ('rotation_steps','steps_per_plan'):
        if not 1<=policy[field]<=maximum_steps:
            raise ValueError('推进步数须为正数且不超过所选路线最大步数')
    if not 60<=policy['timeout_sec']<=86400:
        raise ValueError('单次执行超时须为 60～86400 秒')
    if not 0<=policy['interval_min_sec']<=policy['interval_max_sec']<=86400:
        raise ValueError('计划随机间隔须为 0～86400 秒且上限不小于下限')
    return policy


def _dialogue_module():
    path = Path(__file__).with_name('task_followups.py')
    if not path.is_file():
        path = Path(__file__).resolve().parents[1]/'images/worker/task_followups.py'
    specification = spec_from_file_location('_project_plan_dialogue',path)
    if specification is None or specification.loader is None:
        raise ValueError('原生会话解析器不可用')
    module = module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


class ProjectPlans:
    """管理同一次 CLI 的固定目标范围及逐步验收。

    :param owner: 已初始化的项目实例管理器。
    :param control: 按运行和额度代次操作真实执行的回调。
    :param admission: 创建新执行前的只读账号门禁。
    :param concurrency_limit: 同账号真实 CLI 上限。
    """

    def __init__(self, owner: ProjectIterationManager, control: Callable | None = None,
                 admission: Callable | None = None, concurrency_limit: int = 2) -> None:
        """登记已有能力，不启动线程。@return None。"""
        self.owner, self.control, self.admission = owner, control, admission
        self.limit = min(2,concurrency_limit)
        self.dialogue = _dialogue_module()

    def context(self, run_id: str) -> dict | None:
        """读取计划当前步骤，同时保留原运行器所需的实例字段。@param run_id 运行。@return 内部联合视图。"""
        return self.owner._one('SELECT i.*,b.account_id,b.account_identity,b.catalog_release_id,'
            'b.status AS batch_status,b.generation AS batch_generation,p.generation AS attempt_generation,'
            'p.id AS plan_id,p.session_id,p.start_index,p.target_index,p.completed_steps,p.status AS plan_status,'
            'e.id AS plan_execution_id,e.phase_seq,e.source,e.not_before,a.id AS attempt_id,a.step_id,a.attempt_no '
            'FROM project_plan_executions e JOIN project_execution_plans p ON p.id=e.plan_id '
            'JOIN project_instances i ON i.id=p.instance_id JOIN project_iteration_batches b ON b.id=i.batch_id '
            'LEFT JOIN project_step_attempts a ON a.id=e.current_attempt_id WHERE e.run_id=?',(run_id,))

    def summaries(self, instance_id: int) -> list[dict]:
        """返回不含内部会话和进程证明的计划进度。@param instance_id 实例。@return 计划及 Run 关联。"""
        plans = self.owner._rows('SELECT id,start_index,target_index,completed_steps,status,error,created_at,ended_at '
            'FROM project_execution_plans WHERE instance_id=? ORDER BY id',(instance_id,))
        for plan in plans:
            plan['step_count'] = plan['target_index']-plan['start_index']
            plan['runs'] = self.owner._rows('SELECT r.id,r.status,r.error,r.created_at,r.ended_at FROM runs r '
                'JOIN project_plan_executions e ON e.run_id=r.id WHERE e.plan_id=? ORDER BY e.id',(plan['id'],))
        return plans

    def _write(self, sql: str, parameters=()) -> None:
        with self.owner.write_lock:
            connection = self.owner.database()
            try:
                with connection:
                    connection.execute(sql,parameters)
            finally:
                connection.close()

    def batch_summary(self, batch: dict) -> dict:
        """返回实际容量和投放等待原因，不创建环境或查询上游。@param batch 批次。@return 调度摘要。"""
        policy = batch.get('policy') or json.loads(batch['policy_json'])
        account = self.owner._one('SELECT * FROM accounts WHERE id=?',(batch['account_id'],))
        admission = self.admission(account) if self.admission and account else {'allowed':True}
        active = self.owner._rows('SELECT r.id,r.status,p.instance_id FROM project_plan_executions e '
            'JOIN project_execution_plans p ON p.id=e.plan_id JOIN project_instances i ON i.id=p.instance_id '
            'JOIN runs r ON r.id=e.run_id WHERE i.batch_id=? AND e.ended_at IS NULL',(batch['id'],))
        reasons = []
        if not admission.get('allowed',False):
            reasons.append(admission.get('message') or '等待账号门禁')
        if batch.get('next_launch_at') and batch['next_launch_at']>time.time():
            reasons.append('等待计划随机间隔')
        if len(active)>=policy['concurrency']:
            reasons.append('等待在途计划收口')
        return {'account_concurrency_limit':self.limit,'configured_concurrency':policy['concurrency'],
            'active_runs':active,'running_count':sum(item['status'] in ('running','stopping') for item in active),
            'wait_reasons':reasons,'admission':admission,'next_launch_at':batch.get('next_launch_at')}

    def _relative(self, path: Path) -> str:
        relative = str(path.relative_to(self.owner.data))
        safe_relative(relative)
        current = path
        while current!=self.owner.data:
            if current.is_symlink():
                raise ValueError('计划控制或会话路径包含链接')
            current = current.parent
        return relative

    def _sizes(self, directory: Path) -> dict:
        self._relative(directory)
        result = {}
        for path in directory.glob('*.jsonl'):
            metadata = path.lstat()
            if not S_ISREG(metadata.st_mode) or metadata.st_nlink!=1:
                raise ValueError('原生会话不能为链接或特殊文件')
            result[path.name] = metadata.st_size
        return result

    def _request(self, path: Path, maximum: int = 16384) -> dict:
        descriptor = os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
        try:
            metadata = os.fstat(descriptor)
            if not S_ISREG(metadata.st_mode) or metadata.st_nlink!=1 or metadata.st_size>maximum:
                raise ValueError('候选通知类型、链接或大小无效')
            with os.fdopen(descriptor,'rb',closefd=False) as stream:
                value = json.loads(stream.read(maximum+1))
            if not isinstance(value,dict):
                raise ValueError('候选通知必须为对象')
            return value
        finally:
            os.close(descriptor)

    def _checkpoint(self, context: dict) -> None:
        checksum = context['checkpoint_digest']
        if not re.fullmatch(r'[a-f0-9]{64}',checksum):
            raise ValueError('原计划检查点摘要无效')
        path = self.owner.manifests/(checksum+'.json')
        self._relative(path)
        manifest = read_document(path)
        if (not isinstance(manifest,dict) or manifest.get('schema')!=1 or manifest.get('digest')!=checksum
                or not isinstance(manifest.get('files'),dict) or digest_json(manifest['files'])!=checksum):
            raise ValueError('原计划检查点清单缺失或损坏')
        for name,item in manifest['files'].items():
            safe_relative(name)
            if (not isinstance(item,dict) or not isinstance(item.get('digest'),str)
                    or not re.fullmatch(r'[a-f0-9]{64}',item['digest'])
                    or type(item.get('size')) is not int or not 0<=item['size']<=128*1024*1024):
                raise ValueError('原计划检查点对象清单无效')
            source = self.owner.objects/item['digest'][:2]/item['digest']
            self._relative(source)
            descriptor = os.open(source,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
            try:
                metadata = os.fstat(descriptor)
                if not S_ISREG(metadata.st_mode) or metadata.st_size!=item['size']:
                    raise ValueError('原计划检查点对象类型或大小无效')
                with os.fdopen(descriptor,'rb',closefd=False) as stream:
                    content = stream.read(item['size']+1)
                if hashlib.sha256(content).hexdigest()!=item['digest']:
                    raise ValueError('原计划检查点对象已损坏')
            finally:
                os.close(descriptor)

    def execution_configuration(self, run_id: str, source: str, quota_attempt: int,
                                native_directory: Path, request_path: Path, decision_path: Path, cwd: str) -> dict | None:
        """在真实启动前绑定本执行来源和会话证据，供 driver 使用。

        :param run_id: 原 Run。
        :param source: 本次额度代次的真实执行来源。
        :param quota_attempt: 原运行器额度代次。
        :param native_directory: 固定 HOME 内的项目会话目录。
        :param request_path: 本 Run 的候选通知路径。
        :param decision_path: 本 source 的只读验收决定。
        :param cwd: 已发布的物理项目目录。
        :return: 有界公开计划配置；历史单步 Run 返回 None。
        """
        context = self.context(run_id)
        if context is None:
            return None
        if (cwd!='/home/node/projects/'+Path(context['workspace_relative']).name
                or context['attempt_generation']!=context['batch_generation']):
            raise ValueError('计划会话与项目归属或批次代次不符')
        execution = self.owner._one('SELECT * FROM project_plan_executions WHERE run_id=?',(run_id,))
        attempt = self.owner._one('SELECT * FROM project_step_attempts WHERE id=?',(execution['current_attempt_id'],))
        if execution['ended_at'] is not None or attempt['ended_at'] is not None:
            raise ValueError('已收口计划步骤不能重新启动')
        previous = self.owner._one('SELECT id FROM project_plan_executions WHERE plan_id=? AND id<? LIMIT 1',
            (context['plan_id'],execution['id']))
        resume = bool(previous or quota_attempt>0)
        session_path = native_directory/(context['session_id']+'.jsonl')
        try:
            self._checkpoint(context)
            if resume and (not session_path.is_file() or session_path.is_symlink()):
                raise ValueError('原计划会话缺失，保留现场等待对账')
            if resume:
                # 新代次不能把已截断文件重新记为零起点；先核对原计划已经持久化的字节证据。
                required = 0
                for previous_attempt in self.owner._rows('SELECT native_start_json,native_end_json FROM project_step_attempts WHERE plan_id=?',
                        (context['plan_id'],)):
                    for field in ('native_start_json','native_end_json'):
                        boundaries = json.loads(previous_attempt[field]) if previous_attempt[field] else {}
                        position = boundaries.get(session_path.name,0)
                        if type(position) is not int or position<0:
                            raise ValueError('原计划会话字节证据无效')
                        required = max(required,position)
                if session_path.stat().st_size<required:
                    raise ValueError('原计划会话被截断，保留现场等待对账')
                if not self.dialogue.read_dialogue(session_path):
                    raise ValueError('原计划会话没有可核对的原生对话')
            if not resume and session_path.exists():
                raise ValueError('新计划的会话 ID 已被其他记录占用')
        except (OSError,ValueError) as error:
            message = '原计划接续证明缺失或损坏：'+str(error)[:240]
            self._write("UPDATE project_execution_plans SET status='blocked',error=? WHERE id=?",(message,context['plan_id']))
            self.owner._set_instance(context['id'],status='blocked',error=message,switch_reason='项目证明缺失后切换')
            raise ValueError(message) from error
        snapshot = self._sizes(native_directory)
        relative = {key:self._relative(path) for key,path in
            (('request_relative',request_path),('decision_relative',decision_path),('native_relative',native_directory))}
        with self.owner.write_lock:
            connection = self.owner.database()
            try:
                with connection:
                    run = connection.execute('SELECT quota_attempt,status FROM runs WHERE id=?',(run_id,)).fetchone()
                    parent = connection.execute('SELECT generation,status FROM project_iteration_batches WHERE id=?',(context['batch_id'],)).fetchone()
                    if (not run or run['quota_attempt']!=quota_attempt or run['status']!='running'
                            or parent['generation']!=context['attempt_generation'] or parent['status']!='active'):
                        raise ValueError('计划真实启动前状态或额度代次已经改变')
                    connection.execute('UPDATE project_plan_executions SET source=?,quota_attempt=?,request_relative=?,decision_relative=?,'
                        'native_relative=?,cwd=?,evidence_start_json=?,released_at=NULL,released_quota_attempt=NULL,execution_error=NULL WHERE id=?',
                        (source,quota_attempt,relative['request_relative'],relative['decision_relative'],relative['native_relative'],
                            cwd,canonical_json(snapshot).decode(),execution['id']))
                    connection.execute('UPDATE project_step_attempts SET native_start_json=COALESCE(native_start_json,?),native_end_json=NULL WHERE id=?',
                        (canonical_json(snapshot).decode(),attempt['id']))
            finally:
                connection.close()
        request_path.unlink(missing_ok=True)
        payload = {'schema':1,'plan_id':context['plan_id'],'run_id':run_id,'source':source,
            'generation':context['attempt_generation'],'phase_seq':execution['phase_seq'],'step_id':attempt['step_id'],
            'session_id':context['session_id'],'prompt':attempt['expected_prompt'],'cwd':cwd,'resume':resume,
            'native_directory':'/home/node/.claude/projects/'+cwd.replace('/','-'),
            'request_file':f'/run/v3/runs/{run_id}/project-plan-request.json',
            'state_file':f'/run/v3/runs/{run_id}/project-plan-state.json',
            'decision_file':'/controls/'+decision_path.parent.name+'/project-plan-decision.json'}
        if len(canonical_json(payload))>65536:
            raise ValueError('单次计划提示和控制配置超过大小限制')
        return payload

    def execution_released(self, run_id: str, quota_attempt: int, error: str | None) -> None:
        """记录最终释放，与会话内的逐步暂停证明区分。@param run_id 运行。@param quota_attempt 额度代次。@param error 清理错误。@return None。"""
        execution = self.owner._one('SELECT e.native_relative,r.quota_attempt FROM project_plan_executions e JOIN runs r ON r.id=e.run_id WHERE e.run_id=?',(run_id,))
        if execution is None or execution['quota_attempt']!=quota_attempt:
            return
        boundaries = None
        if not error and execution['native_relative']:
            try:
                boundaries = canonical_json(self._sizes(self.owner.data/safe_relative(execution['native_relative']))).decode()
            except (OSError,ValueError) as failure:
                error = '原生会话封存失败：'+type(failure).__name__
        self._write('UPDATE project_plan_executions SET released_at=?,released_quota_attempt=?,execution_error=? '
            'WHERE run_id=? AND EXISTS(SELECT 1 FROM runs WHERE id=? AND quota_attempt=?)',
            (None if error else time.time(),quota_attempt,error,run_id,run_id,quota_attempt))
        self._write('UPDATE project_step_attempts SET execution_released_at=?,released_quota_attempt=?,execution_error=?,native_end_json=COALESCE(native_end_json,?) '
            'WHERE run_id=? AND EXISTS(SELECT 1 FROM runs WHERE id=? AND quota_attempt=?)',
            (None if error else time.time(),quota_attempt,error,boundaries,run_id,run_id,quota_attempt))

    def recover(self, cleanup: Callable) -> None:
        """重启后收口计划的旧执行，保留已接受检查点和待完成范围。@param cleanup 原 Runner 清理入口。@return None。"""
        executions = self.owner._rows('SELECT e.run_id,r.status,r.started_at,r.worker_container,r.quota_attempt '
            'FROM project_plan_executions e JOIN runs r ON r.id=e.run_id WHERE e.ended_at IS NULL')
        for execution in executions:
            if (execution['status']=='quota_wait' or execution['status']=='queued'
                    and not execution['started_at'] and not execution['worker_container']):
                continue
            try:
                cleanup(execution['run_id'])
                self.execution_released(execution['run_id'],execution['quota_attempt'],None)
                if execution['status'] not in RUN_TERMINAL:
                    self._write("UPDATE runs SET status='failed',error='服务重启中断，保留计划检查点与未完成现场',ended_at=? "
                        "WHERE id=? AND status IN ('running','stopping')",(time.time(),execution['run_id']))
            except Exception as error:
                self.execution_released(execution['run_id'],execution['quota_attempt'],type(error).__name__)

    def _prompt(self, instance: dict, plan: dict, step: dict, report: dict | None = None) -> str:
        manifest = json.loads(instance['manifest_json'])
        sample = step['checks'][0]
        prompt = (f"Continue developing the existing project: {manifest['title']}.\n"
            f"This session's fixed plan covers roadmap steps {plan['start_index']+1} through {plan['target_index']}.\n"
            f"Current step: {step['id']}\nGoal: {step['goal']}\n"
            'Preserve existing code and data. Complete only the current step, perform necessary checks, '
            'and give a brief final reply. Wait for independent verification before starting the next step.\n'
            'Runtime contract: python3 app.py reads one JSON request per line and writes one JSON result per line. '
            'Use the existing runtime and standard library.\nExample input: '
            +canonical_json(sample['input']).decode()+'\nExpected example result: '
            +canonical_json(sample['expected']).decode())
        if report:
            prompt += '\nContinue from the current files. Previous attempt evidence: '+canonical_json(report).decode()[:12000]
        return prompt

    def _failure_report(self, instance: dict) -> dict | None:
        manifest = json.loads(instance['manifest_json'])
        if instance['next_step_index']>=len(manifest['steps']):
            return None
        step = manifest['steps'][instance['next_step_index']]
        previous = self.owner._one('SELECT report_relative FROM project_step_attempts WHERE instance_id=? AND step_id=? '
            'ORDER BY attempt_no DESC LIMIT 1',(instance['id'],step['id']))
        return read_document(self.owner.data/safe_relative(previous['report_relative'])) if previous and previous['report_relative'] else None

    def _attempt(self, connection, instance: dict, plan: dict, run_id: str, phase_seq: int, now: float,
                 report: dict | None = None) -> tuple[int,str]:
        manifest = json.loads(instance['manifest_json'])
        step = manifest['steps'][instance['next_step_index']]
        previous = connection.execute('SELECT attempt_no,report_relative FROM project_step_attempts '
            'WHERE instance_id=? AND step_id=? ORDER BY attempt_no DESC LIMIT 1',(instance['id'],step['id'])).fetchone()
        attempt_no = previous['attempt_no']+1 if previous else 1
        if attempt_no>3:
            raise ValueError('当前步骤的修复次数已经用尽')
        prompt = self._prompt(instance,plan,step,report)
        attempt = connection.execute('INSERT INTO project_step_attempts(instance_id,step_id,attempt_no,generation,run_id,'
            'expected_checkpoint_digest,created_at,plan_id,phase_seq,expected_prompt) VALUES(?,?,?,?,?,?,?,?,?,?)',
            (instance['id'],step['id'],attempt_no,plan['generation'],run_id,instance['checkpoint_digest'],now,plan['id'],phase_seq,prompt))
        return attempt.lastrowid,prompt

    def reserve(self, batch: dict, instance: dict, account: dict) -> None:
        """为固定计划建立一个新的 CLI Run，恢复时不扩大目标范围。@param batch 批次。@param instance 实例。@param account 账号。@return None。"""
        policy = json.loads(batch['policy_json'])
        frozen = self.owner.settings()
        report = self._failure_report(instance)
        now, run_id = time.time(),uuid.uuid4().hex[:12]
        with self.owner.write_lock:
            connection = self.owner.database()
            try:
                with connection:
                    parent = connection.execute('SELECT * FROM project_iteration_batches WHERE id=?',(batch['id'],)).fetchone()
                    current = connection.execute('SELECT * FROM project_instances WHERE id=?',(instance['id'],)).fetchone()
                    if (not parent or parent['status']!='active' or parent['generation']!=batch['generation']
                            or current['status'] not in ('ready','not_started')):
                        return
                    occupied = connection.execute('SELECT COUNT(*) FROM project_plan_executions e '
                        'JOIN project_execution_plans p ON p.id=e.plan_id JOIN project_instances i ON i.id=p.instance_id '
                        'JOIN project_iteration_batches b ON b.id=i.batch_id WHERE b.account_id=? AND e.ended_at IS NULL',
                        (batch['account_id'],)).fetchone()[0]
                    batch_occupied = connection.execute('SELECT COUNT(*) FROM project_plan_executions e '
                        'JOIN project_execution_plans p ON p.id=e.plan_id JOIN project_instances i ON i.id=p.instance_id '
                        'WHERE i.batch_id=? AND e.ended_at IS NULL',(batch['id'],)).fetchone()[0]
                    if (occupied>=self.limit or batch_occupied>=policy['concurrency']
                            or float(parent['next_launch_at'] or 0)>now):
                        return
                    if connection.execute('SELECT 1 FROM project_plan_executions e JOIN project_execution_plans p ON p.id=e.plan_id '
                            'WHERE p.instance_id=? AND e.ended_at IS NULL',(instance['id'],)).fetchone():
                        return
                    current = dict(current)
                    plan = connection.execute("SELECT * FROM project_execution_plans WHERE instance_id=? AND status='ready' ORDER BY id DESC LIMIT 1",
                        (instance['id'],)).fetchone()
                    if plan:
                        plan = dict(plan)
                        frozen = json.loads(plan['execution_json'])
                    else:
                        total = len(json.loads(current['manifest_json'])['steps'])
                        remaining = policy['rotation_steps']-current['visit_completed']
                        target = min(total,current['next_step_index']+min(policy['steps_per_plan'],remaining))
                        if target<=current['next_step_index']:
                            raise ValueError('计划范围为空，轮换计数需要对账')
                        cursor = connection.execute('INSERT INTO project_execution_plans(instance_id,generation,start_index,target_index,'
                            'session_id,execution_json,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)',
                            (instance['id'],batch['generation'],current['next_step_index'],target,str(uuid.uuid4()),
                                canonical_json(frozen).decode(),now,now))
                        plan = dict(connection.execute('SELECT * FROM project_execution_plans WHERE id=?',(cursor.lastrowid,)).fetchone())
                    if current['next_step_index']!=plan['start_index']+plan['completed_steps']:
                        raise ValueError('原计划与项目已接受进度不一致')
                    title = json.loads(current['manifest_json'])
                    task = connection.execute('INSERT INTO tasks(topic_no,title,prompt,account_id,timeout_sec,repeat_n) VALUES(?,?,?,?,?,1)',
                        (title['source_topic_no'],f"[Project iteration] {title['title']} / steps {plan['start_index']+1}-{plan['target_index']}",
                            '',batch['account_id'],policy['timeout_sec']))
                    task_id = task.lastrowid
                    connection.execute('INSERT INTO runs(id,task_id,account_id,status,run_kind,claude_code_version,claude_effort_level,execution_model,quota_identity) '
                        'VALUES(?,?,?,?,?,?,?,?,?)',(run_id,task_id,batch['account_id'],'queued','project_iteration',
                            frozen['claude_code_version'],frozen['claude_effort_level'],frozen['execution_model'],batch['account_identity']))
                    attempt_id,prompt = self._attempt(connection,current,plan,run_id,0,now,report)
                    connection.execute('UPDATE tasks SET prompt=? WHERE id=?',(prompt,task_id))
                    connection.execute('INSERT INTO project_plan_executions(plan_id,run_id,current_attempt_id,not_before,created_at) VALUES(?,?,?,?,?)',
                        (plan['id'],run_id,attempt_id,float(parent['next_launch_at'] or 0),now))
                    connection.execute("UPDATE project_execution_plans SET status='running',updated_at=? WHERE id=?",(now,plan['id']))
                    connection.execute("UPDATE project_instances SET status='ready',error=NULL,updated_at=? WHERE id=?",(now,instance['id']))
                    connection.execute('UPDATE project_iteration_batches SET launches_started=launches_started+1,last_launch_at=?,next_launch_at=NULL,wait_reason=NULL,updated_at=? WHERE id=?',
                        (now,now,batch['id']))
            finally:
                connection.close()
        payload = {'id':task_id,'prompt':prompt,'timeout_sec':policy['timeout_sec'],**frozen,'model_override':frozen['execution_model']}
        if plan['completed_steps'] or self.owner._one('SELECT 1 FROM project_plan_executions WHERE plan_id=? AND run_id!=?',(plan['id'],run_id)):
            payload['resume_session_id'] = plan['session_id']
        self.owner.submit(run_id,account,payload)

    def _decision(self, execution: dict) -> None:
        if not execution.get('decision_json') or not execution.get('decision_relative'):
            return
        document = json.loads(execution['decision_json'])
        if document['source']!=execution['source']:
            return
        path = self.owner.data/safe_relative(execution['decision_relative'])
        self._relative(path)
        write_document(path,document)
        # 控制目录以只读方式挂载给 CLI，只允许该普通用户读取决定。
        os.chown(path,0,1000,follow_symlinks=False)
        path.chmod(0o640)

    def _evidence(self, execution: dict, attempt: dict, plan: dict, request: dict) -> dict:
        expected = {'schema':1,'plan_id':plan['id'],'run_id':execution['run_id'],
            'source':execution['source'],'generation':plan['generation'],'phase_seq':execution['phase_seq'],
            'step_id':attempt['step_id'],'session_id':plan['session_id']}
        if any(type(request.get(key)) is not type(value) or request.get(key)!=value for key,value in expected.items()):
            raise ValueError('候选通知与当前计划阶段或执行代次不符')
        directory = self.owner.data/safe_relative(execution['native_relative'])
        self._relative(directory)
        path = directory/(plan['session_id']+'.jsonl')
        if path.is_symlink() or not path.is_file():
            raise ValueError('原计划会话证明缺失')
        start = json.loads(execution['evidence_start_json'])
        offset = start.get(path.name,0)
        if type(offset) is not int or offset<0 or path.stat().st_size<offset:
            raise ValueError('原计划会话被截断')
        dialogue = self.dialogue.read_dialogue(path,offset=offset)
        user = next((item for item in reversed(dialogue) if item['role']=='user'
            and item['normal'] and isinstance(item['text'],str)
            and self.dialogue._matches_input(item['text'],attempt['expected_prompt'])),None)
        if user is None:
            raise ValueError('当前步骤指令没有实际进入固定会话')
        following = dialogue[dialogue.index(user)+1:]
        response = next((item for item in reversed(following) if item['role']=='assistant' and item['normal']),None)
        if response is None or any(request.get(key)!=value for key,value in
                (('input_key',user['key']),('response_key',response['key']),('response_end',response['end']))):
            raise ValueError('候选回复没有匹配当前步骤的原生证据')
        by_key = {item['key']:item for item in dialogue}
        ancestor = response.get('parent_key')
        while ancestor in by_key and ancestor!=user['key']:
            ancestor = by_key[ancestor].get('parent_key')
        if ancestor!=user['key']:
            raise ValueError('候选回复没有连接到当前指令的父链')
        # 父链已经恢复原生顺序，不能用字节位置否定异步先落盘的回复。
        later = [item for item in following[following.index(response)+1:] if item['role'] in ('user','assistant')
            and not item['synthetic'] and (item['normal'] or item['tool'])]
        if later:
            raise ValueError('候选回复之后仍存在未交接的会话活动')
        return self._sizes(directory)

    def _verify(self, batch: dict, execution: dict) -> None:
        if not self.control or not execution.get('request_relative'):
            return
        path = self.owner.data/safe_relative(execution['request_relative'])
        self._relative(path)
        if not path.exists():
            return
        request = self._request(path)
        if request.get('phase_seq')!=execution['phase_seq']:
            # 接受事务可能先于决定文件落盘；持久决定可安全重放，不能再次验收旧通知。
            self._decision(execution)
            return
        attempt = self.owner._one('SELECT * FROM project_step_attempts WHERE id=?',(execution['current_attempt_id'],))
        if attempt['ended_at'] is not None:
            self._decision(execution)
            return
        plan = self.owner._one('SELECT * FROM project_execution_plans WHERE id=?',(execution['plan_id'],))
        instance = self.owner._one('SELECT * FROM project_instances WHERE id=?',(plan['instance_id'],))
        frozen = False
        try:
            proof = self.control(execution['run_id'],execution['quota_attempt'],'freeze')
            if not proof.get('frozen') or proof.get('source')!=execution['source']:
                raise ValueError('当前执行完整暂停的证明无效')
            frozen = True
            boundaries = self._evidence(execution,attempt,plan,request)
            snapshot,candidate = self.owner._capture(instance)
            manifest = json.loads(instance['manifest_json'])
            index = instance['next_step_index']
            if index>=len(manifest['steps']) or manifest['steps'][index]['id']!=attempt['step_id']:
                raise ValueError('当前步骤与路线检查点不符')
            cases = list(manifest['baseline_checks'])
            for step in manifest['steps'][:index+1]:
                cases.extend(step['checks'])
            # 验证基础设施本地重试，不消耗模型业务修复次数，且总等待有界。
            report = self.verifier_report(candidate,cases)
            report.update(candidate_digest=snapshot['digest'],step_id=attempt['step_id'],run_id=execution['run_id'])
            self._accept(batch,execution,attempt,plan,instance,request,boundaries,snapshot,report)
            current = self.owner._one('SELECT * FROM project_plan_executions WHERE id=?',(execution['id'],))
            self._decision(current)
        finally:
            if frozen:
                self.control(execution['run_id'],execution['quota_attempt'],'resume')

    def verifier_report(self, candidate: Path, cases: list[dict]) -> dict:
        """独立验证候选，基础设施错误最多重验一次。@param candidate 冻结副本。@param cases 累积用例。@return 验证报告。"""
        report = self.owner.verifier.verify(candidate,cases)
        if report['status']=='error':
            report = self.owner.verifier.verify(candidate,cases)
        return report

    def _accept(self, batch: dict, execution: dict, attempt: dict, plan: dict, instance: dict,
                request: dict, boundaries: dict, snapshot: dict, report: dict) -> None:
        report_path = self.owner.data/'project-artifacts/attempts'/str(attempt['id'])/'report.json'
        write_document(report_path,report)
        passed = report['status']=='passed'
        blocked = report['status']=='error' or (not passed and attempt['attempt_no']>=3)
        next_index = instance['next_step_index']+int(passed)
        complete = passed and next_index==plan['target_index']
        now = time.time()
        with self.owner.write_lock:
            connection = self.owner.database()
            try:
                with connection:
                    parent = connection.execute('SELECT status,generation FROM project_iteration_batches WHERE id=?',(batch['id'],)).fetchone()
                    current = connection.execute('SELECT * FROM project_instances WHERE id=?',(instance['id'],)).fetchone()
                    active = connection.execute('SELECT e.*,r.status AS run_status,r.quota_attempt AS run_epoch FROM project_plan_executions e '
                        'JOIN runs r ON r.id=e.run_id WHERE e.id=?',(execution['id'],)).fetchone()
                    if (parent['status'] not in ('active','pausing','paused') or parent['generation']!=plan['generation']
                            or current['checkpoint_digest']!=attempt['expected_checkpoint_digest']
                            or current['next_step_index']!=instance['next_step_index']
                            or active['source']!=execution['source'] or active['phase_seq']!=execution['phase_seq']
                            or active['run_epoch']!=execution['quota_attempt'] or active['run_status']!='running'
                            or active['current_attempt_id']!=attempt['id'] or active['ended_at'] is not None):
                        return
                    accepted = connection.execute('UPDATE project_step_attempts SET validation_status=?,candidate_digest=?,'
                        'accepted_checkpoint_digest=?,result_digest=?,report_relative=?,native_end_json=?,fenced_at=?,fenced_source=?,ended_at=? '
                        'WHERE id=? AND ended_at IS NULL',
                        ('passed' if passed else 'error' if report['status']=='error' else 'failed',snapshot['digest'],
                            snapshot['digest'] if passed else None,digest_json(report),self._relative(report_path),
                            canonical_json(boundaries).decode(),now,execution['source'],now,attempt['id']))
                    if accepted.rowcount!=1:
                        return
                    if passed:
                        connection.execute('UPDATE project_instances SET next_step_index=?,checkpoint_digest=?,visit_completed=visit_completed+1,'
                            'error=NULL,updated_at=? WHERE id=?',(next_index,snapshot['digest'],now,instance['id']))
                        connection.execute('UPDATE project_execution_plans SET completed_steps=completed_steps+1,updated_at=? WHERE id=?',
                            (now,plan['id']))
                    decision = {key:request[key] for key in ('schema','plan_id','run_id','source','generation','phase_seq','step_id','session_id','response_key')}
                    if complete or blocked:
                        decision['action'] = 'complete' if complete else 'failed'
                        connection.execute('UPDATE project_execution_plans SET status=?,error=?,updated_at=? WHERE id=?',
                            ('finalizing' if complete else 'blocked',None if complete else '当前步骤验收失败且修复已用尽或验证环境不可用',now,plan['id']))
                        if blocked:
                            connection.execute("UPDATE project_instances SET status='blocked',error=?,updated_at=? WHERE id=?",
                                ('当前步骤验收失败且修复已用尽或验证环境不可用',now,instance['id']))
                        connection.execute('UPDATE project_plan_executions SET decision_json=? WHERE id=?',
                            (canonical_json(decision).decode(),execution['id']))
                    else:
                        updated = dict(connection.execute('SELECT * FROM project_instances WHERE id=?',(instance['id'],)).fetchone())
                        seq = execution['phase_seq']+1
                        attempt_id,prompt = self._attempt(connection,updated,plan,execution['run_id'],seq,now,None if passed else report)
                        connection.execute('UPDATE project_step_attempts SET native_start_json=? WHERE id=?',
                            (canonical_json(boundaries).decode(),attempt_id))
                        decision.update(action='send',next_phase_seq=seq,next_step_id=json.loads(updated['manifest_json'])['steps'][next_index]['id'],prompt=prompt)
                        connection.execute('UPDATE project_plan_executions SET phase_seq=?,current_attempt_id=?,evidence_start_json=?,decision_json=? WHERE id=?',
                            (seq,attempt_id,canonical_json(boundaries).decode(),canonical_json(decision).decode(),execution['id']))
            finally:
                connection.close()

    def _block(self, execution: dict, message: str) -> None:
        plan = self.owner._one('SELECT instance_id FROM project_execution_plans WHERE id=?',(execution['plan_id'],))
        self._write("UPDATE project_execution_plans SET status='blocked',error=?,updated_at=? WHERE id=?",
            (message,time.time(),execution['plan_id']))
        self.owner._set_instance(plan['instance_id'],status='blocked',error=message,switch_reason='项目阻塞后切换')
        self.owner.stop_run(execution['run_id'])

    def _can_resume_input(self, execution: dict, attempt: dict, plan: dict) -> bool:
        try:
            directory = self.owner.data/safe_relative(execution['native_relative'])
            self._relative(directory)
            path = directory/(plan['session_id']+'.jsonl')
            if path.is_symlink() or not path.is_file():
                return False
            boundaries = json.loads(execution['evidence_start_json'])
            offset = boundaries.get(path.name,0)
            if type(offset) is not int or offset<0:
                return False
            consumed = any(item['role']=='user' and item['normal'] and isinstance(item['text'],str)
                and self.dialogue._matches_input(item['text'],attempt['expected_prompt'])
                for item in self.dialogue.read_dialogue(path,offset=offset))
            if consumed:
                return True
            state_path = (self.owner.data/safe_relative(execution['request_relative'])).with_name('project-plan-state.json')
            self._relative(state_path)
            state = self._request(state_path,maximum=65536)
            # 检查点已接受而 driver 尚未准备下一阶段时，能够证明本步尚未发送，可以接续。
            return (state.get('source')==execution['source'] and state.get('generation')==plan['generation']
                and state.get('session_id')==plan['session_id'] and type(state.get('phase_seq')) is int
                and 0<=state['phase_seq']<execution['phase_seq'] and state.get('delivery')=='sent')
        except (OSError,ValueError,TypeError,KeyError,AttributeError):
            return False

    def _settle(self, batch: dict, execution: dict) -> None:
        if self.owner.is_executing(execution['run_id'],execution['run_epoch']):
            return
        if execution['execution_error']:
            self._block(execution,'原执行未能严格清理：'+execution['execution_error'])
            return
        if not execution['released_at'] or execution['released_quota_attempt']!=execution['run_epoch']:
            if not execution['run_started_at'] and not execution['worker_container']:
                self.execution_released(execution['run_id'],execution['run_epoch'],None)
            return
        plan = self.owner._one('SELECT * FROM project_execution_plans WHERE id=?',(execution['plan_id'],))
        attempt = self.owner._one('SELECT * FROM project_step_attempts WHERE id=?',(execution['current_attempt_id'],))
        instance = self.owner._one('SELECT * FROM project_instances WHERE id=?',(plan['instance_id'],))
        cancelled = batch['generation']!=plan['generation'] or batch['status'] in ('stopping','stopped','blocked') or execution['run_status']=='stopped'
        complete = plan['completed_steps']==plan['target_index']-plan['start_index']
        blocked = plan['status']=='blocked' or execution['run_status']=='auth_failed'
        if attempt['ended_at'] is None:
            uncertain = bool(not cancelled and not blocked and execution['source']
                and not self._can_resume_input(execution,attempt,plan))
            blocked = blocked or uncertain
            # 超时现场属于失败候选而非检查点；原工作目录始终保留，不能回滚成已通过版本。
            self.owner._finish_failure(attempt,{'status':'cancelled' if cancelled else 'failed',
                'message':'本步输入投递结果不确定，缺少原生消费证据，禁止自动重发' if uncertain else
                    execution['run_error'] or 'Execution ended before independent verification.'},block=blocked)
            if execution.get('native_relative'):
                end = self._sizes(self.owner.data/safe_relative(execution['native_relative']))
                self._write('UPDATE project_step_attempts SET native_end_json=? WHERE id=?',(canonical_json(end).decode(),attempt['id']))
            instance = self.owner._one('SELECT * FROM project_instances WHERE id=?',(plan['instance_id'],))
            blocked = blocked or instance['status']=='blocked'
        now = time.time()
        policy = json.loads(batch['policy_json'])
        delay = random.randint(policy['interval_min_sec'],policy['interval_max_sec'])
        with self.owner.write_lock:
            connection = self.owner.database()
            try:
                with connection:
                    changed = connection.execute('UPDATE project_plan_executions SET ended_at=? WHERE id=? AND ended_at IS NULL',(now,execution['id']))
                    if changed.rowcount!=1:
                        return
                    state = 'completed' if complete else 'stopped' if cancelled else 'blocked' if blocked else 'ready'
                    connection.execute('UPDATE project_execution_plans SET status=?,updated_at=?,ended_at=? WHERE id=?',
                        (state,now,now if state!='ready' else None,plan['id']))
                    if complete:
                        finished = instance['next_step_index']==len(json.loads(instance['manifest_json'])['steps'])
                        rotate = instance['visit_completed']>=policy['rotation_steps']
                        order = connection.execute('SELECT COALESCE(MAX(visit_order),0)+1 FROM project_instances WHERE batch_id=?',(batch['id'],)).fetchone()[0]
                        connection.execute('UPDATE project_instances SET status=?,visit_order=?,visit_completed=?,switch_reason=?,updated_at=? WHERE id=?',
                            ('completed' if finished else 'ready',order if rotate else instance['visit_order'],
                                0 if rotate else instance['visit_completed'],'路线完成' if finished else '连续完成后轮换' if rotate else '继续当前轮次',now,instance['id']))
                    connection.execute('UPDATE project_iteration_batches SET next_launch_at=COALESCE(next_launch_at,?),updated_at=? WHERE id=?',
                        (now+delay,now,batch['id']))
            finally:
                connection.close()
        if execution['run_status']=='auth_failed':
            self.owner._batch_error(batch['id'],'账号认证失效，保留全部项目并停止投放')

    def _inspect(self, batch: dict, account: dict | None, execution: dict) -> None:
        status = execution['run_status']
        if status in RUN_TERMINAL:
            self._settle(batch,execution)
            return
        context = self.context(execution['run_id'])
        if status=='quota_wait':
            self._write("UPDATE project_execution_plans SET status='quota_wait' WHERE id=? AND status='running'",(execution['plan_id'],))
            self.owner._set_instance(context['id'],status='quota_wait')
            return
        if status=='running':
            self._write("UPDATE project_execution_plans SET status='running' WHERE id=? AND status='quota_wait'",(execution['plan_id'],))
            self.owner._set_instance(context['id'],status='running')
            if batch['generation']==context['attempt_generation'] and batch['status'] in ('active','pausing','paused'):
                self._decision(execution)
                self._verify(batch,execution)
        elif status=='queued' and account and self.owner.execution_allowed(execution['run_id']):
            self.owner._set_instance(context['id'],status='window_wait' if execution['window_wait_until'] else 'ready')
            if not self.owner.is_executing(execution['run_id'],execution['run_epoch']):
                run = self.owner._one('SELECT r.*,t.prompt,t.timeout_sec FROM runs r JOIN tasks t ON t.id=r.task_id WHERE r.id=?',(execution['run_id'],))
                self.owner.submit(run['id'],account,{'id':run['task_id'],'prompt':run['prompt'],'timeout_sec':run['timeout_sec'],
                    'claude_code_version':run['claude_code_version'],'claude_effort_level':run['claude_effort_level'],
                    'model_override':run['execution_model'],'quota_attempt':run['quota_attempt']})

    def drive(self, batch: dict, account: dict | None) -> None:
        """推进在途握手、收口与有界补位；等待不持有 CLI 许可。@param batch 当前批次。@param account 当前账号。@return None。"""
        executions = self.owner._rows('SELECT e.*,r.status AS run_status,r.quota_attempt AS run_epoch,r.started_at AS run_started_at,'
            'r.worker_container,r.window_wait_until,r.error AS run_error FROM project_plan_executions e '
            'JOIN project_execution_plans p ON p.id=e.plan_id JOIN project_instances i ON i.id=p.instance_id '
            'JOIN runs r ON r.id=e.run_id WHERE i.batch_id=? AND e.ended_at IS NULL ORDER BY e.id',(batch['id'],))
        for execution in executions:
            try:
                self._inspect(batch,account,execution)
            except Exception as error:
                self._block(execution,'计划执行对账失败：'+type(error).__name__+': '+str(error)[:240])
        batch = self.owner._one('SELECT * FROM project_iteration_batches WHERE id=?',(batch['id'],))
        open_count = self.owner._one('SELECT COUNT(*) AS n FROM project_plan_executions e '
            'JOIN project_execution_plans p ON p.id=e.plan_id JOIN project_instances i ON i.id=p.instance_id '
            'WHERE i.batch_id=? AND e.ended_at IS NULL',(batch['id'],))['n']
        if batch['status']=='stopping' and not open_count:
            self._write("UPDATE project_iteration_batches SET status='stopped',updated_at=? WHERE id=? AND status='stopping'",(time.time(),batch['id']))
        if batch['status']=='pausing':
            running = self.owner._one("SELECT 1 FROM project_plan_executions e JOIN project_execution_plans p ON p.id=e.plan_id "
                "JOIN project_instances i ON i.id=p.instance_id JOIN runs r ON r.id=e.run_id "
                "WHERE i.batch_id=? AND e.ended_at IS NULL AND r.status IN ('running','stopping')",(batch['id'],))
            if not running:
                self._write("UPDATE project_iteration_batches SET status='paused',updated_at=? WHERE id=? AND status='pausing'",(time.time(),batch['id']))
        if batch['status']!='active' or self.owner._stop.is_set() or not account:
            return
        policy = json.loads(batch['policy_json'])
        admission = self.admission(account) if self.admission else {'allowed':True}
        if not admission.get('allowed',False):
            self._write('UPDATE project_iteration_batches SET wait_reason=? WHERE id=?',(admission.get('message') or '等待账号门禁',batch['id']))
            return
        instances = self.owner._rows('SELECT * FROM project_instances WHERE batch_id=? ORDER BY visit_order,id',(batch['id'],))
        if all(item['status']=='completed' for item in instances) and not open_count:
            self._write("UPDATE project_iteration_batches SET status='completed',updated_at=? WHERE id=?",(time.time(),batch['id']))
            return
        ready = [item for item in instances if item['status'] in ('ready','not_started')]
        if not ready and not open_count:
            self.owner._batch_error(batch['id'],'剩余项目均已阻塞，已保留现场和最后通过版本')
            return
        self._write("UPDATE project_instances SET in_pool=0 WHERE batch_id=? AND status IN ('completed','blocked','stopped')",(batch['id'],))
        pool = [item for item in instances if item['in_pool'] and item['status'] not in ('completed','blocked','stopped')]
        newcomers = sorted((item for item in ready if not item['in_pool']),key=lambda item:(item['initial_order'],item['id']))
        for item in newcomers[:max(0,policy['active_projects']-len(pool))]:
            self._write('UPDATE project_instances SET in_pool=1 WHERE id=?',(item['id'],))
            item['in_pool'] = 1
            pool.append(item)
        busy_instances = {row['instance_id'] for row in self.owner._rows('SELECT p.instance_id FROM project_plan_executions e '
            'JOIN project_execution_plans p ON p.id=e.plan_id WHERE e.ended_at IS NULL')}
        for item in sorted(pool,key=lambda value:(value['visit_order'],value['id'])):
            if item['id'] in busy_instances or item['status'] not in ('ready','not_started'):
                continue
            current = self.owner._one('SELECT * FROM project_iteration_batches WHERE id=?',(batch['id'],))
            if open_count>=policy['concurrency'] or current['status']!='active':
                break
            if current['launches_started']>=policy['concurrency']:
                if current['next_launch_at'] is None:
                    deadline = time.time()+random.randint(policy['interval_min_sec'],policy['interval_max_sec'])
                    self._write('UPDATE project_iteration_batches SET next_launch_at=? WHERE id=? AND next_launch_at IS NULL',(deadline,batch['id']))
                    current['next_launch_at'] = deadline
                if current['next_launch_at']>time.time():
                    break
            before = current['launches_started']
            try:
                self.reserve(current,item,account)
            except (OSError,ValueError) as error:
                self.owner._set_instance(item['id'],status='blocked',error='计划无法安全启动：'+str(error)[:240])
                self._write("UPDATE project_execution_plans SET status='blocked',error=? WHERE instance_id=? AND status='ready'",
                    ('计划无法安全启动：'+str(error)[:240],item['id']))
            after = self.owner._one('SELECT launches_started FROM project_iteration_batches WHERE id=?',(batch['id'],))
            if after['launches_started']>before:
                open_count += 1
