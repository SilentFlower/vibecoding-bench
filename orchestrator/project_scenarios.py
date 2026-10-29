"""场景任务的持久状态、执行归属及跨恢复预算。"""
from __future__ import annotations

import json
import hashlib
import os
import random
import threading
import time
import uuid
from pathlib import Path
from typing import TYPE_CHECKING

from project_library import (canonical_json, digest_json, materialize_snapshot, read_document,
    safe_relative, snapshot_tree, write_document)
from project_evaluation import check_change_scope, load_rubric, parse_review, review_package, review_prompt, source_evidence
from project_scenario_usage import aggregate_usage, observed_model, source_usage
from project_development import DEVELOPMENT_SQL, ProjectDevelopment

if TYPE_CHECKING:
    from project_iteration import ProjectIterationManager


SCENARIO_DEFAULTS = {'schema': 3, 'concurrency': 2, 'active_projects': 3, 'rotation_steps': 5,
    'steps_per_plan': 2, 'timeout_sec': 600, 'task_budget_sec': 1800,
    'review_timeout_sec': 180, 'review_budget_sec': 720,
    'interval_min_sec': 0, 'interval_max_sec': 0, 'repair_limit': 2}
TASK_TERMINAL = frozenset({'passed', 'failed', 'exhausted', 'blocked', 'cancelled'})
SCENARIO_SCHEMA = '''
CREATE TABLE IF NOT EXISTS project_scenario_instances (
  id INTEGER PRIMARY KEY AUTOINCREMENT, instance_id INTEGER NOT NULL, scenario_key TEXT NOT NULL,
  entry_key TEXT NOT NULL, definition_json TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'pending',
  workspace_relative TEXT, session_id TEXT NOT NULL, seed_digest TEXT NOT NULL,
  checkpoint_digest TEXT NOT NULL, execution_json TEXT, error TEXT,
  created_at REAL NOT NULL, updated_at REAL NOT NULL, UNIQUE(instance_id,scenario_key),
  FOREIGN KEY(instance_id) REFERENCES project_instances(id)
);
CREATE TABLE IF NOT EXISTS project_scenario_tasks (
  id INTEGER PRIMARY KEY AUTOINCREMENT, scenario_instance_id INTEGER NOT NULL,
  task_key TEXT NOT NULL, kind TEXT NOT NULL, definition_json TEXT NOT NULL,
  selected INTEGER NOT NULL DEFAULT 0, status TEXT NOT NULL DEFAULT 'pending',
  phase TEXT NOT NULL DEFAULT 'ready', turn_no INTEGER NOT NULL DEFAULT 1,
  attempt_count INTEGER NOT NULL DEFAULT 0, infra_recoveries INTEGER NOT NULL DEFAULT 0,
  next_reason TEXT NOT NULL DEFAULT 'initial', next_prompt TEXT NOT NULL, result_json TEXT, input_checkpoint_digest TEXT,
  accepted_checkpoint_digest TEXT, error TEXT, created_at REAL NOT NULL, updated_at REAL NOT NULL,
  UNIQUE(scenario_instance_id,task_key),
  FOREIGN KEY(scenario_instance_id) REFERENCES project_scenario_instances(id)
);
CREATE TABLE IF NOT EXISTS project_task_attempts (
  id INTEGER PRIMARY KEY AUTOINCREMENT, task_id INTEGER NOT NULL, attempt_no INTEGER NOT NULL,
  reason TEXT NOT NULL, consumed_at REAL NOT NULL, ended_at REAL, result TEXT,
  UNIQUE(task_id,attempt_no), FOREIGN KEY(task_id) REFERENCES project_scenario_tasks(id)
);
CREATE TABLE IF NOT EXISTS project_task_executions (
  id INTEGER PRIMARY KEY AUTOINCREMENT, task_id INTEGER NOT NULL, attempt_id INTEGER,
  plan_id INTEGER,
  run_id TEXT NOT NULL UNIQUE, role TEXT NOT NULL CHECK(role IN ('candidate','review')),
  evaluation_job_id INTEGER, review_attempt INTEGER, turn_no INTEGER NOT NULL,
  generation INTEGER NOT NULL, session_id TEXT NOT NULL, delivery_id INTEGER,
  resume INTEGER NOT NULL DEFAULT 0, result_json TEXT, created_at REAL NOT NULL, ended_at REAL,
  FOREIGN KEY(task_id) REFERENCES project_scenario_tasks(id), FOREIGN KEY(run_id) REFERENCES runs(id)
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_scenario_task_open_candidate
  ON project_task_executions(task_id) WHERE role='candidate' AND ended_at IS NULL;
CREATE TABLE IF NOT EXISTS project_execution_sources (
  id INTEGER PRIMARY KEY AUTOINCREMENT, execution_id INTEGER NOT NULL, quota_attempt INTEGER NOT NULL,
  source TEXT NOT NULL, delivery_id INTEGER, native_relative TEXT, cwd TEXT, request_relative TEXT, decision_relative TEXT,
  evidence_start_json TEXT, evidence_end_json TEXT, work_relative TEXT,
  released_at REAL, execution_error TEXT, start_permitted INTEGER NOT NULL DEFAULT 0, created_at REAL NOT NULL,
  UNIQUE(execution_id,quota_attempt,source), FOREIGN KEY(execution_id) REFERENCES project_task_executions(id)
);
CREATE TABLE IF NOT EXISTS project_task_deliveries (
  id INTEGER PRIMARY KEY AUTOINCREMENT, task_id INTEGER NOT NULL, phase_key TEXT NOT NULL,
  prompt TEXT NOT NULL, input_digest TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'pending',
  input_key TEXT, consumed_source_id INTEGER, created_at REAL NOT NULL, consumed_at REAL,
  UNIQUE(task_id,phase_key), FOREIGN KEY(task_id) REFERENCES project_scenario_tasks(id)
);
CREATE TABLE IF NOT EXISTS project_evaluation_jobs (
  id INTEGER PRIMARY KEY AUTOINCREMENT, task_id INTEGER NOT NULL, source_id INTEGER NOT NULL,
  turn_no INTEGER NOT NULL, generation INTEGER NOT NULL, response_key TEXT NOT NULL,
  response_digest TEXT NOT NULL, input_digest TEXT NOT NULL, basis_digest TEXT NOT NULL,
  candidate_digest TEXT NOT NULL, candidate_relative TEXT NOT NULL, answer_relative TEXT NOT NULL,
  evidence_json TEXT NOT NULL, version INTEGER NOT NULL, status TEXT NOT NULL DEFAULT 'waiting_release',
  native_result_json TEXT, review_result_json TEXT, review_attempt INTEGER NOT NULL DEFAULT 0,
  infra_recoveries INTEGER NOT NULL DEFAULT 0, review_resume INTEGER NOT NULL DEFAULT 0, response_budget_sec INTEGER NOT NULL,
  error TEXT, created_at REAL NOT NULL, ended_at REAL,
  UNIQUE(source_id,response_key,version), FOREIGN KEY(task_id) REFERENCES project_scenario_tasks(id),
  FOREIGN KEY(source_id) REFERENCES project_execution_sources(id)
);
CREATE TABLE IF NOT EXISTS project_work_segments (
  id INTEGER PRIMARY KEY AUTOINCREMENT, source_id INTEGER NOT NULL, segment_seq INTEGER NOT NULL,
  role TEXT NOT NULL CHECK(role IN ('candidate','review')), boot_id TEXT NOT NULL,
  start_mono REAL NOT NULL, reserved_sec REAL NOT NULL CHECK(reserved_sec>0),
  confirmed_sec REAL NOT NULL DEFAULT 0 CHECK(confirmed_sec>=0),
  status TEXT NOT NULL DEFAULT 'reserved' CHECK(status IN ('reserved','active','settled','uncertain')),
  usage_json TEXT, created_at REAL NOT NULL, settled_at REAL,
  UNIQUE(source_id,segment_seq), FOREIGN KEY(source_id) REFERENCES project_execution_sources(id)
);
CREATE INDEX IF NOT EXISTS idx_scenario_task_instance ON project_scenario_tasks(scenario_instance_id,selected,status);
CREATE INDEX IF NOT EXISTS idx_scenario_evaluation_ready ON project_evaluation_jobs(status,created_at);
CREATE TABLE IF NOT EXISTS project_scenario_plans (
  id INTEGER PRIMARY KEY AUTOINCREMENT, scenario_instance_id INTEGER NOT NULL,
  generation INTEGER NOT NULL, task_ids_json TEXT NOT NULL, passed_ids_json TEXT NOT NULL DEFAULT '[]',
  status TEXT NOT NULL DEFAULT 'running', created_at REAL NOT NULL, ended_at REAL,
  FOREIGN KEY(scenario_instance_id) REFERENCES project_scenario_instances(id)
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_scenario_open_plan ON project_scenario_plans(scenario_instance_id)
  WHERE ended_at IS NULL;
'''


def initialize_scenario_schema(connection) -> None:
    """幂等建立新表，不改写旧实例或自增序列。

    :param connection: 已初始化通用与项目基础表的连接。
    :return: None。
    """
    connection.executescript(SCENARIO_SCHEMA + DEVELOPMENT_SQL)


def normalized_scenario_policy(values: dict, project_count: int, account_limit: int) -> dict:
    """解析新内容的策略，保留省略与显式输入的区别。

    :param values: 请求实际提供的字段。
    :param project_count: 本批所选项目数。
    :param account_limit: 共享账号容量。
    :return: 冻结的 policy 3 对象。
    """
    if set(values) - (set(SCENARIO_DEFAULTS) - {'schema', 'repair_limit'}):
        raise ValueError('场景策略包含未知字段')
    policy = {**SCENARIO_DEFAULTS, **values}
    if any(type(value) is not int for value in policy.values()):
        raise ValueError('场景预算与调度参数必须是整数')
    if not 1 <= policy['active_projects'] <= 100:
        raise ValueError('活动项目池须为 1～100')
    capacity = min(2, account_limit, project_count, policy['active_projects'])
    if 'concurrency' not in values:
        policy['concurrency'] = capacity
    if not 1 <= policy['concurrency'] <= capacity:
        raise ValueError('场景并发超过账号或活动池容量')
    for field in ('rotation_steps', 'steps_per_plan'):
        if not 1 <= policy[field] <= 100:
            raise ValueError('每次推进与轮换任务数须为 1～100')
    for field in ('timeout_sec', 'task_budget_sec', 'review_budget_sec'):
        if not 60 <= policy[field] <= 86400:
            raise ValueError('任务及累计评审预算须为 60～86400 秒')
    if not 60 <= policy['review_timeout_sec'] <= 600:
        raise ValueError('单次评审预算须为 60～600 秒')
    if not 0 <= policy['interval_min_sec'] <= policy['interval_max_sec'] <= 86400:
        raise ValueError('随机补位间隔须为 0～86400 秒且上限不小于下限')
    return policy


class ProjectScenarios:
    """管理新场景的持久任务与逐执行片段，复用原管理器及数据库。

    :param owner: 原项目管理器，提供数据库、锁和共享执行能力。
    """

    def __init__(self, owner: ProjectIterationManager) -> None:
        """登记已有依赖，不启动旁路调度。@param owner 原管理器。@return None。"""
        self.owner = owner
        self._evaluating = set()
        self._evaluation_lock = threading.Lock()
        self.development = ProjectDevelopment(self)

    def context(self, run_id: str) -> dict | None:
        """提供原运行器所需的项目归属及独立场景会话。

        :param run_id: 原 Scheduler Run。
        :return: 内部执行视图，普通或旧版本返回 None。
        """
        execution = self.owner._one('SELECT * FROM project_task_executions WHERE run_id=?', (run_id,))
        if execution is None:
            return None
        task = self.task(execution['task_id'])
        return {**task, 'id': task['instance_id'], 'scenario_task_id': task['id'], 'execution_id': execution['id'],
            'attempt_id': execution['attempt_id'], 'attempt_generation': execution['generation'],
            'batch_generation': task['generation'], 'role': execution['role'], 'run_id': run_id,
            'session_id': execution['session_id'], 'scenario_execution': execution}

    def prepare_workspace(self, row: dict, run_id: str, environment_root: Path) -> tuple[str, Path]:
        """首次启动才发布场景独立工作区，后续严格复用现场。

        :param row: 原账号固定环境。
        :param run_id: 已通过共享门禁的候选运行。
        :param environment_root: 原环境的本地数据根。
        :return: 稳定场景别名与路径。
        """
        context = self.context(run_id)
        if not context or context['role'] != 'candidate' or row['account_id'] != context['account_id'] or not self.owner.can_start(run_id):
            raise ValueError('场景工作区账号、角色或父代次不符')
        alias = 'scenario-' + digest_json([row['environment_id'], context['scenario_instance_id']])[:12]
        target = environment_root / 'projects' / alias
        relative = str(target.relative_to(self.owner.data))
        marker = self.owner.data / 'project-artifacts/scenarios' / str(context['scenario_instance_id']) / 'materialized.json'
        expected = {'scenario_id': context['scenario_instance_id'], 'seed_digest': context['seed_digest'], 'workspace_relative': relative}
        if context['workspace_relative']:
            if context['workspace_relative'] != relative or not target.is_dir() or target.is_symlink():
                raise ValueError('原场景工作区缺失或被替换，保留现场')
            if not marker.exists() or read_document(marker) != expected:
                raise ValueError('场景工作区发布证明缺失或冲突')
            return alias, target
        if marker.exists():
            if read_document(marker) != expected or not target.is_dir() or target.is_symlink():
                raise ValueError('场景工作区发布中断，需要核对归属')
        elif target.exists() or target.is_symlink():
            raise ValueError('场景目录存在但归属不明，拒绝覆盖')
        else:
            project = self.owner._release(context['catalog_release_id']).projects[context['project_key']]
            baseline = snapshot_tree(project.root / 'seed', self.owner.objects)
            write_document(self.owner.manifests / (baseline['digest'] + '.json'), baseline)
            staging = self.owner.data / 'project-staging' / uuid.uuid4().hex
            materialize_snapshot(baseline, self.owner.objects, staging)
            try:
                for path in [staging, *staging.rglob('*')]:
                    os.chown(path, 1000, 1000, follow_symlinks=False)
                target.parent.mkdir(parents=True, exist_ok=True)
                os.chown(target.parent, 1000, 1000, follow_symlinks=False)
                write_document(marker, expected)
                if not self.owner.can_start(run_id):
                    marker.unlink(missing_ok=True)
                    raise ValueError('发布前场景父状态已经改变')
                os.rename(staging, target)
            finally:
                if staging.exists():
                    import shutil
                    shutil.rmtree(staging)
        self.owner.plans._write('UPDATE project_scenario_instances SET workspace_relative=?,updated_at=? WHERE id=? AND workspace_relative IS NULL',
            (relative, time.time(), context['scenario_instance_id']))
        self._prepare_inputs(self.task(context['scenario_task_id']))
        return alias, target

    def _prepare_inputs(self, task: dict) -> None:
        definition = json.loads(task['definition_json'])
        self._bind_code_dependencies(task,definition)
        scenario = self.owner._one('SELECT definition_json FROM project_scenario_instances WHERE id=?',(task['scenario_instance_id'],))
        entry = next(item for item in json.loads(scenario['definition_json'])['entries'] if item['id']==task['entry_key'])
        self._materialize_inputs(task,entry.get('setup',[]),
            self.owner.data/'project-artifacts/scenarios'/str(task['scenario_instance_id'])/'entry-inputs.json',
            {'scenario_id':task['scenario_instance_id'],'entry_key':task['entry_key']})
        marker = self.owner.data/'project-artifacts/task-inputs'/str(task['id'])/'prepared.json'
        checksum = self._materialize_inputs(task,definition.get('setup',[]),marker,{'task_id':task['id']})
        disclosures = self.owner._rows("SELECT phase_key FROM project_task_deliveries WHERE task_id=? AND phase_key LIKE 'disclosure:%' ORDER BY id",(task['id'],))
        for delivery in disclosures:
            branch_id = delivery['phase_key'].removeprefix('disclosure:')
            branch = next(item for item in definition.get('branches',[]) if item['id']==branch_id)
            if branch.get('setup'):
                checksum = self._materialize_inputs(task,branch['setup'],marker.with_name('branch-'+branch_id+'.json'),
                    {'task_id':task['id'],'branch_id':branch_id})
        self.owner.plans._checkpoint({'checkpoint_digest':checksum})
        self.owner.plans._write('UPDATE project_scenario_tasks SET input_checkpoint_digest=? WHERE id=?', (checksum,task['id']))

    def _bind_code_dependencies(self, task: dict, definition: dict) -> None:
        marker=self.owner.data/'project-artifacts/task-inputs'/str(task['id'])/'code-dependency.json'
        dependencies=[]
        for dependency in definition['requires']:
            if dependency['artifact']!='code':
                continue
            target=self.owner._one("SELECT id,status,accepted_checkpoint_digest FROM project_scenario_tasks WHERE scenario_instance_id=? AND task_key=?",
                (task['scenario_instance_id'],dependency['task_id']))
            if not target or target['status']!='passed' or not target['accepted_checkpoint_digest']:
                raise ValueError('所需前置代码尚未接受，不能以当前目录替代')
            job=self.owner._one("SELECT id,candidate_digest,evidence_json FROM project_evaluation_jobs WHERE task_id=? AND status='passed' AND candidate_digest=? ORDER BY id DESC LIMIT 1",
                (target['id'],target['accepted_checkpoint_digest']))
            if not job:
                raise ValueError('前置代码缺少固定接受来源')
            dependencies.append(job)
        expected={str(job['id']):job['candidate_digest'] for job in dependencies}
        if marker.exists():
            previous=read_document(marker)
            if previous.get('task_id')!=task['id'] or previous.get('dependencies')!=expected or previous.get('state')!='ready':
                raise ValueError('代码输入交接中断或依赖冲突，保留现场等待对账')
            return
        base=task['checkpoint_digest']
        accepted=self.owner._one("SELECT j.id FROM project_evaluation_jobs j JOIN project_scenario_tasks t ON t.id=j.task_id "
            "WHERE t.scenario_instance_id=? AND t.kind='modify' AND t.status='passed' AND j.status='passed' "
            "AND j.candidate_digest=? ORDER BY j.id DESC LIMIT 1",(task['scenario_instance_id'],base))
        base_job=accepted['id'] if accepted else None
        entry_marker=self.owner.data/'project-artifacts/scenarios'/str(task['scenario_instance_id'])/'entry-inputs.json'
        if base_job is None and entry_marker.exists():
            entry_input=read_document(entry_marker)
            if entry_input.get('scenario_id')!=task['scenario_instance_id'] or entry_input.get('entry_key')!=task['entry_key']:
                raise ValueError('代码输入的入口材料归属冲突')
            base=entry_input['input_checkpoint_digest']
        if dependencies:
            selected=max(dependencies,key=lambda item:item['id'])
            base=selected['candidate_digest']
            base_job=selected['id']
            # 相同字节可能来自回退操作；必须沿接受作业身份走父链，不能按摘要折叠分支。
            parents={row['id']:json.loads(row['evidence_json']).get('parent_code_job_id')
                for row in self.owner._rows("SELECT j.id,j.evidence_json FROM project_evaluation_jobs j JOIN project_scenario_tasks t ON t.id=j.task_id "
                    "WHERE t.scenario_instance_id=? AND t.kind='modify' AND t.status='passed' AND j.status='passed' ORDER BY j.id",(task['scenario_instance_id'],))}
            chain=set()
            current=base_job
            while current and current not in chain:
                chain.add(current)
                current=parents.get(current)
            if any(job['id'] not in chain for job in dependencies):
                raise ValueError('多个代码依赖没有同一已接受继承链，不能猜测合并')
        identity={'task_id':task['id'],'dependencies':expected,'base_checkpoint_digest':base,'base_checkpoint_job_id':base_job}
        workspace=self.owner.data/safe_relative(task['workspace_relative'])
        if snapshot_tree(workspace)['digest']!=base:
            previous=snapshot_tree(workspace,self.owner.objects)
            write_document(self.owner.manifests/(previous['digest']+'.json'),previous)
            self.owner.plans._checkpoint({'checkpoint_digest':base})
            snapshot=read_document(self.owner.manifests/(base+'.json'))
            staging=self.owner.data/'project-staging'/('code-input-'+uuid.uuid4().hex)
            saved=self.owner.data/'project-staging'/('previous-workspace-'+uuid.uuid4().hex)
            materialize_snapshot(snapshot,self.owner.objects,staging)
            for path in [staging,*staging.rglob('*')]:
                os.chown(path,1000,1000,follow_symlinks=False)
            # 交接意图先落盘；崩溃后宁可受阻，也不能把新目录错认成原半成品。
            write_document(marker,{**identity,'state':'replacing','previous_digest':previous['digest'],
                'saved_relative':str(saved.relative_to(self.owner.data)),'staging_relative':str(staging.relative_to(self.owner.data))})
            os.rename(workspace,saved)
            os.rename(staging,workspace)
            identity.update(previous_digest=previous['digest'],saved_relative=str(saved.relative_to(self.owner.data)))
        write_document(marker,{**identity,'state':'ready'})

    def _materialize_inputs(self, task: dict, setup: list[dict], marker: Path, identity: dict) -> str:
        project = self.owner._release(task['catalog_release_id']).projects[task['project_key']]
        workspace = self.owner.data / safe_relative(task['workspace_relative'])
        intended = {**identity,'setup_digest':digest_json(setup)}
        if marker.exists():
            existing = read_document(marker)
            if any(existing.get(key) != value for key,value in intended.items()):
                raise ValueError('业务材料物化归属冲突')
            checksum = existing['input_checkpoint_digest']
        else:
            for item in setup:
                target = workspace / safe_relative(item['target'])
                path = target
                while path != workspace:
                    if path.is_symlink():
                        raise ValueError('业务输入目标包含链接，拒绝覆盖')
                    path = path.parent
                target.parent.mkdir(parents=True,exist_ok=True)
                content = (project.root / safe_relative(item['source'])).read_bytes()
                if target.exists() and target.read_bytes() != content:
                    raise ValueError('业务输入目标已有不同内容，保留现场等待对账')
                target.write_bytes(content)
                os.chown(target,1000,1000)
                target.chmod(0o644)
                os.chown(target.parent,1000,1000)
            snapshot = snapshot_tree(workspace,self.owner.objects)
            checksum = snapshot['digest']
            write_document(self.owner.manifests / (checksum+'.json'),snapshot)
            write_document(marker,{**intended,'input_checkpoint_digest':checksum})
        return checksum

    def execution_configuration(self, run_id: str, source: str, quota_attempt: int, native_directory: Path,
                                request_path: Path, decision_path: Path, cwd: str) -> dict:
        """绑定逐代来源和真实会话，为现有 driver 提供公开交接配置。

        :param run_id: 当前 Run。
        :param source: 原额度来源。
        :param quota_attempt: 当前额度代次。
        :param native_directory: 该场景或私有评审的固定日志目录。
        :param request_path: 候选通知。
        :param decision_path: 控制端只读决定。
        :param cwd: 容器真实目录。
        :return: 不含隐藏评测的候选配置或私有评审配置。
        """
        context = self.context(run_id)
        if not context or not self.owner.execution_allowed(run_id):
            raise ValueError('场景执行已停止或父代次不符')
        execution = context['scenario_execution']
        if execution['role'] == 'candidate':
            self._prepare_inputs(self.task(context['scenario_task_id']))
        native_directory.mkdir(parents=True, exist_ok=True)
        os.chown(native_directory,1000,1000,follow_symlinks=False)
        os.chown(native_directory.parent,1000,1000,follow_symlinks=False)
        native = native_directory / (context['session_id'] + '.jsonl')
        previous_sources = self.owner._rows('SELECT x.* FROM project_execution_sources x JOIN project_task_executions e '
            'ON e.id=x.execution_id WHERE e.session_id=? ORDER BY x.id', (context['session_id'],))
        resume = any(row['start_permitted'] for row in previous_sources)
        if resume:
            required = max((json.loads(row['evidence_end_json'] or row['evidence_start_json'] or '{}').get(native.name, 0)
                for row in previous_sources), default=0)
            if not native.is_file() or native.is_symlink() or native.stat().st_size < required:
                raise ValueError('固定场景会话缺失或被截断，不能新建会话冒充接续')
            if not self.owner.plans.dialogue.read_dialogue(native):
                raise ValueError('场景恢复缺少可核对的原生输入')
        elif native.exists():
            raise ValueError('新场景会话身份已被其他记录占用')
        delivery = self.owner._one('SELECT * FROM project_task_deliveries WHERE id=?', (execution['delivery_id'],))
        if not delivery:
            raise ValueError('场景执行缺少冻结输入')
        sizes = self.owner.plans._sizes(native_directory)
        work_path = request_path.with_name('project-work.json')
        with self.owner.write_lock:
            connection = self.owner.database()
            try:
                with connection:
                    current = connection.execute('SELECT status,quota_attempt FROM runs WHERE id=?', (run_id,)).fetchone()
                    parent = connection.execute('SELECT generation,status FROM project_iteration_batches WHERE id=?', (context['batch_id'],)).fetchone()
                    if (not current or current['status'] != 'running' or current['quota_attempt'] != quota_attempt
                            or parent['generation'] != execution['generation'] or parent['status'] != 'active'):
                        raise ValueError('实际启动前父状态或额度代次已变化')
                    if quota_attempt > 0:
                        prompt = 'Continue the current unfinished task in the original session. Preserve the existing files and completed work, and provide your answer when finished.'
                        cursor = connection.execute('INSERT INTO project_task_deliveries(task_id,phase_key,prompt,input_digest,created_at) VALUES(?,?,?,?,?)',
                            (execution['task_id'], 'quota:' + source, prompt, digest_json(prompt), time.time()))
                        delivery = dict(connection.execute('SELECT * FROM project_task_deliveries WHERE id=?', (cursor.lastrowid,)).fetchone())
                        connection.execute('UPDATE project_task_executions SET delivery_id=? WHERE id=?', (delivery['id'], execution['id']))
                    connection.execute('INSERT INTO project_execution_sources(execution_id,quota_attempt,source,delivery_id,native_relative,cwd,'
                        'request_relative,decision_relative,evidence_start_json,work_relative,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)',
                        (execution['id'], quota_attempt, source, delivery['id'], self.owner.plans._relative(native_directory), cwd,
                            self.owner.plans._relative(request_path), self.owner.plans._relative(decision_path), canonical_json(sizes).decode(),
                            self.owner.plans._relative(work_path), time.time()))
                    source_id = connection.execute('SELECT last_insert_rowid()').fetchone()[0]
                    if execution['role'] == 'candidate':
                        connection.execute("UPDATE project_scenario_tasks SET status='running',phase='executing',updated_at=? WHERE id=?",
                            (time.time(), context['scenario_task_id']))
                    else:
                        connection.execute("UPDATE project_scenario_tasks SET phase='reviewing',updated_at=? WHERE id=? AND status='evaluating'",
                            (time.time(), context['scenario_task_id']))
            finally:
                connection.close()
        segment = self.reserve_segment(source_id, 1, Path('/proc/sys/kernel/random/boot_id').read_text().strip(), time.monotonic())
        request_path.unlink(missing_ok=True)
        work_path.unlink(missing_ok=True)
        payload = {'schema': 1, 'workflow_schema': 3, 'plan_id': context['scenario_instance_id'], 'run_id': run_id,
            'source': source, 'generation': execution['generation'], 'phase_seq': execution['turn_no'],
            'step_id': context['task_key'], 'session_id': execution['session_id'], 'prompt': delivery['prompt'],
            'cwd': cwd, 'resume': resume, 'native_directory': '/home/node/.claude/projects/' + cwd.replace('/', '-'),
            'request_file': f'/run/v3/runs/{run_id}/project-plan-request.json',
            'state_file': f'/run/v3/runs/{run_id}/project-plan-state.json',
            'work_file': f'/run/v3/runs/{run_id}/project-work.json', 'segment_id': segment['id'],
            'segment_boot_id': segment['boot_id'], 'work_limit_sec': segment['reserved_sec'],
            'decision_file': '/controls/' + decision_path.parent.name + '/project-plan-decision.json'}
        if len(canonical_json(payload)) > 65536:
            raise ValueError('场景单次公开输入超过driver上限')
        return payload

    def create_tasks(self, connection, instance_id: int, manifest: dict, now: float,
                     entries: dict[str, str] | None = None) -> None:
        """在创建批次事务内建立场景与任务，不物化工作区。

        :param connection: 外层持有原写锁的事务连接。
        :param instance_id: 项目实例。
        :param manifest: 冻结内容。
        :param now: 本次事务时间。
        :param entries: 该项目显式选择的场景入口，省略使用冻结默认入口。
        :return: None。
        """
        for scenario in manifest['scenarios']:
            selected = (entries or {}).get(scenario['id'],scenario['default_entry'])
            entry = next(item for item in scenario['entries'] if item['id'] == selected)
            cursor = connection.execute('INSERT INTO project_scenario_instances(instance_id,scenario_key,entry_key,'
                'definition_json,session_id,seed_digest,checkpoint_digest,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?)',
                (instance_id, scenario['id'], entry['id'], canonical_json(scenario).decode(), str(uuid.uuid4()),
                    manifest['seed_digest'], manifest['seed_digest'], now, now))
            for task in scenario['tasks']:
                connection.execute('INSERT INTO project_scenario_tasks(scenario_instance_id,task_key,kind,definition_json,'
                    'selected,next_prompt,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)',
                    (cursor.lastrowid, task['id'], task['kind'], canonical_json(task).decode(),
                        int(task['id'] in entry['task_ids']), task['prompt'], now, now))

    def task(self, task_id: int) -> dict:
        """读取含父状态的内部任务事实。

        :param task_id: 数据库任务 ID。
        :return: 内部联合视图；缺失时拒绝猜测。
        """
        result = self.owner._one('SELECT t.*,s.instance_id,s.scenario_key,s.entry_key,s.session_id,s.workspace_relative,'
            's.checkpoint_digest,s.seed_digest,s.execution_json,i.batch_id,i.project_key,i.manifest_json,'
            'b.policy_json,b.account_id,b.account_identity,b.catalog_release_id,b.generation,b.status AS batch_status '
            'FROM project_scenario_tasks t JOIN project_scenario_instances s ON s.id=t.scenario_instance_id '
            'JOIN project_instances i ON i.id=s.instance_id JOIN project_iteration_batches b ON b.id=i.batch_id '
            'WHERE t.id=?', (task_id,))
        if result is None:
            raise ValueError('场景任务不存在')
        return result

    def batch_summary(self, batch: dict) -> dict:
        """按真实 Run 归属返回共享调度状态，不读取隐藏回答。

        :param batch: 批次内部行或已解析策略摘要。
        :return: 页面所需的轻量调度事实。
        """
        policy = batch.get('policy') or json.loads(batch['policy_json'])
        active = self.owner._rows('SELECT r.id,r.status,e.role,s.instance_id FROM project_task_executions e '
            'JOIN project_scenario_tasks t ON t.id=e.task_id JOIN project_scenario_instances s ON s.id=t.scenario_instance_id '
            'JOIN project_instances i ON i.id=s.instance_id JOIN runs r ON r.id=e.run_id '
            'WHERE i.batch_id=? AND e.ended_at IS NULL', (batch['id'],))
        account = self.owner._one('SELECT * FROM accounts WHERE id=?', (batch['account_id'],))
        admission = self.owner.plans.admission(account) if account and self.owner.plans.admission else {'allowed': True}
        reasons = []
        if not admission.get('allowed'):
            reasons.append(admission.get('message') or '等待账号门禁')
        if len(active) >= policy['concurrency']:
            reasons.append('等待执行严格释放')
        return {'account_concurrency_limit': self.owner.plans.limit, 'configured_concurrency': policy['concurrency'],
            'active_runs': active, 'running_count': sum(row['status'] in ('running', 'stopping') for row in active),
            'wait_reasons': reasons, 'admission': admission, 'next_launch_at': batch.get('next_launch_at')}

    def instance_detail(self, instance: dict, result: dict) -> dict:
        """生成场景与任务状态投影，回答和内部证据另按需读取。

        :param instance: 冻结项目实例内部行。
        :param result: 原门面的实例公开基础字段。
        :return: 含预算、代码接受及执行分列的实例详情。
        """
        result['scenarios'] = []
        result['attempts'] = []
        result['plans'] = self.owner._rows('SELECT p.id,p.task_ids_json,p.passed_ids_json,p.status,p.created_at,p.ended_at '
            'FROM project_scenario_plans p JOIN project_scenario_instances s ON s.id=p.scenario_instance_id WHERE s.instance_id=? ORDER BY p.id',(instance['id'],))
        for plan in result['plans']:
            plan['task_ids'] = json.loads(plan.pop('task_ids_json'))
            plan['passed_task_ids'] = json.loads(plan.pop('passed_ids_json'))
        for scenario in self.owner._rows('SELECT * FROM project_scenario_instances WHERE instance_id=? ORDER BY id', (instance['id'],)):
            definition = json.loads(scenario['definition_json'])
            public = {field: scenario[field] for field in ('id', 'scenario_key', 'entry_key', 'status', 'checkpoint_digest', 'error')}
            public.update(title=definition['title'], goal=definition['goal'], tasks=[])
            for task in self.owner._rows('SELECT * FROM project_scenario_tasks WHERE scenario_instance_id=? ORDER BY id', (scenario['id'],)):
                definition = json.loads(task['definition_json'])
                item = {field: task[field] for field in ('id', 'task_key', 'kind', 'selected', 'status', 'phase', 'turn_no',
                    'attempt_count', 'infra_recoveries', 'accepted_checkpoint_digest', 'error')}
                item.update(goal=definition['goal'], requires=definition['requires'],
                    result=json.loads(task['result_json']) if task['result_json'] else None,
                    candidate_budget=self.budget(task['id']),review_budget=self.budget(task['id'],'review'))
                if self.development.handles(task):
                    requester = self.development.summary(task['id'])
                    item.update(development_cycle=definition['development_cycle'],
                        development_phase='accepted' if task['status'] == 'passed' else 'verifying'
                            if task['status'] == 'evaluating' and requester['status'] == 'applied' and requester['action'] == 'verify'
                            else self.development.phase(task['id']), requester=requester)
                item['executions'] = self.owner._rows('SELECT e.id,e.run_id,e.role,e.turn_no,r.status AS execution_status '
                    'FROM project_task_executions e JOIN runs r ON r.id=e.run_id WHERE e.task_id=? ORDER BY e.id', (task['id'],))
                item['evaluation'] = self.owner._one('SELECT id,status,error,created_at,ended_at FROM project_evaluation_jobs '
                    'WHERE task_id=? ORDER BY id DESC LIMIT 1', (task['id'],))
                public['tasks'].append(item)
            public['counts'] = {status: sum(task['selected'] and task['status'] == status for task in public['tasks'])
                for status in sorted({task['status'] for task in public['tasks'] if task['selected']})}
            result['scenarios'].append(public)
        return result

    def require_task(self, instance_id: int, task_id: int) -> dict:
        """校验nested资源的真实归属，不能跨实例猜任务ID。

        :param instance_id: URL项目实例。
        :param task_id: URL任务数据库ID。
        :return: 已核验内部任务。
        """
        task = self.task(task_id)
        if task['instance_id'] != instance_id:
            raise ValueError('场景任务不属于当前项目实例')
        return task

    def attempts(self, instance_id: int, task_id: int) -> dict:
        """读取任务的完整业务尝试与实际Run关联。

        :param instance_id: 项目实例。
        :param task_id: 业务任务。
        :return: 不含会话身份及隐藏输入的记录。
        """
        task = self.require_task(instance_id,task_id)
        result = {'task_id':task_id,'attempts':self.owner._rows('SELECT id,attempt_no,reason,consumed_at,ended_at,result '
            'FROM project_task_attempts WHERE task_id=? ORDER BY attempt_no',(task_id,)),
            'executions':self.owner._rows('SELECT e.id,e.attempt_id,e.run_id,e.role,e.turn_no,e.created_at,e.ended_at,r.status AS execution_status '
                'FROM project_task_executions e JOIN runs r ON r.id=e.run_id WHERE e.task_id=? ORDER BY e.id',(task_id,))}
        if self.development.handles(task):
            result.update(conversation=self._conversation(task_id), requester=self.development.summary(task_id))
        return result

    def artifacts(self, instance_id: int, task_id: int, evaluation_id: int | None = None) -> dict:
        """按冻结回答版本读取答案、独立验收及源码清单。

        :param instance_id: 项目实例。
        :param task_id: 任务。
        :param evaluation_id: 可选固定评测版本，省略读取最新候选。
        :return: 管理端证据；不会作为候选修正提示原样投放。
        """
        task = self.require_task(instance_id,task_id)
        parameters = (task_id,evaluation_id) if evaluation_id is not None else (task_id,)
        job = self.owner._one('SELECT * FROM project_evaluation_jobs WHERE task_id=?'
            +(' AND id=?' if evaluation_id is not None else '')+' ORDER BY id DESC LIMIT 1',parameters)
        if not job:
            return {'task_id':task_id,'evaluation_id':None,'answer':None,'files':[],'report':None}
        snapshot = read_document(self.owner.manifests/(job['candidate_digest']+'.json'))
        if snapshot.get('digest') != job['candidate_digest'] or digest_json(snapshot.get('files')) != job['candidate_digest']:
            raise ValueError('场景候选清单已损坏')
        answer = read_document(self.owner.data/safe_relative(job['answer_relative']))['text']
        if digest_json(answer) != job['response_digest']:
            raise ValueError('冻结回答摘要不符')
        return {'task_id':task_id,'evaluation_id':job['id'],'turn_no':job['turn_no'],'answer':answer,
            'status':job['status'],'response_digest':job['response_digest'],'candidate_digest':job['candidate_digest'],
            'code_accepted':task['accepted_checkpoint_digest'] == job['candidate_digest'],
            'report':{'native':json.loads(job['native_result_json']) if job['native_result_json'] else None,
                'review':json.loads(job['review_result_json']) if job['review_result_json'] else None,'error':job['error']},
            'files':[{'path':name,**value} for name,value in sorted(snapshot['files'].items())]}

    def artifact_file(self, instance_id: int, task_id: int, relative: str, evaluation_id: int | None = None) -> dict:
        """只读取该任务冻结清单内的内容对象，拒绝任意宿主路径。

        :param instance_id: 项目实例。
        :param task_id: 任务。
        :param relative: 清单中的相对路径。
        :param evaluation_id: 固定评测版本。
        :return: 最多65536字节文本预览。
        """
        relative = safe_relative(relative)
        artifact = self.artifacts(instance_id,task_id,evaluation_id)
        item = next((item for item in artifact['files'] if item['path']==relative),None)
        if not item:
            raise ValueError('冻结任务产物没有这个文件')
        path = self.owner.objects/item['digest'][:2]/item['digest']
        if path.is_symlink():
            raise ValueError('场景内容对象不能是链接')
        import hashlib
        content = path.read_bytes()
        if hashlib.sha256(content).hexdigest() != item['digest']:
            raise ValueError('场景内容对象已损坏')
        try:
            text = content[:65536].decode('utf-8')
        except UnicodeDecodeError:
            text = '该文件是二进制内容或包含非UTF-8字节。'
        return {'path':relative,'text':text,'truncated':len(content)>65536}

    def run_usage(self, run_id: str) -> dict:
        """读取一个实际Run全部额度来源的主会话分项用量。

        :param run_id: 实际执行Run。
        :return: 去重用量，不把整个Run分给多个任务。
        """
        sources = self.owner._rows('SELECT x.*,e.session_id FROM project_execution_sources x JOIN project_task_executions e ON e.id=x.execution_id WHERE e.run_id=?',(run_id,))
        return aggregate_usage([source_usage(self.owner.data/safe_relative(row['native_relative']),
            json.loads(row['evidence_start_json']) if row['evidence_start_json'] else None,
            json.loads(row['evidence_end_json']) if row['evidence_end_json'] else None,row['session_id']) for row in sources])

    def usage(self, instance_id: int) -> dict:
        """分任务、类型及候选／评审角色累计完整尝试成本。

        :param instance_id: 项目实例。
        :return: 主会话已有记录、有效时间与统计覆盖；没有虚构金额。
        """
        if not self.owner._one('SELECT id FROM project_instances WHERE id=?',(instance_id,)):
            raise ValueError('项目实例不存在')
        tasks = self.owner._rows('SELECT t.id,t.task_key,t.kind FROM project_scenario_tasks t JOIN project_scenario_instances s '
            'ON s.id=t.scenario_instance_id WHERE s.instance_id=? ORDER BY t.id',(instance_id,))
        result, grouped = [], {}
        for task in tasks:
            item = {**task,'roles':{}}
            for role in ('candidate','review'):
                sources = self.owner._rows('SELECT x.*,e.session_id FROM project_execution_sources x JOIN project_task_executions e ON e.id=x.execution_id WHERE e.task_id=? AND e.role=?',(task['id'],role))
                observations = [source_usage(self.owner.data/safe_relative(row['native_relative']),
                    json.loads(row['evidence_start_json']) if row['evidence_start_json'] else None,
                    json.loads(row['evidence_end_json']) if row['evidence_end_json'] else None,row['session_id']) for row in sources]
                summary = aggregate_usage(observations)
                summary['work'] = self.budget(task['id'],role)
                item['roles'][role] = summary
                grouped.setdefault((task['kind'],role),[]).extend(observations)
            if self.development.handles(self.task(task['id'])):
                item['roles']['requester'] = self.development.summary(task['id'])
            result.append(item)
        return {'instance_id':instance_id,'tasks':result,'by_kind':[{'kind':kind,'role':role,**aggregate_usage(values)}
            for (kind,role),values in sorted(grouped.items())]}

    def refresh_readiness(self, scenario_id: int) -> None:
        """只传播真实依赖，局部失败不阻止独立任务。

        :param scenario_id: 场景实例。
        :return: None。
        """
        with self.owner.write_lock:
            connection = self.owner.database()
            try:
                with connection:
                    tasks = {row['task_key']: dict(row) for row in connection.execute(
                        'SELECT * FROM project_scenario_tasks WHERE scenario_instance_id=?', (scenario_id,))}
                    for task in tasks.values():
                        if not task['selected'] or task['status'] != 'pending':
                            continue
                        dependencies = [tasks[item['task_id']] for item in json.loads(task['definition_json'])['requires']]
                        reason = None
                        if any(item['status'] in TASK_TERMINAL - {'passed'} for item in dependencies):
                            status, reason = 'blocked', '所需前置任务未通过'
                        elif all(item['selected'] and item['status'] == 'passed' for item in dependencies):
                            status = 'ready'
                        else:
                            continue
                        connection.execute('UPDATE project_scenario_tasks SET status=?,error=?,updated_at=? WHERE id=? AND status=?',
                            (status, reason, time.time(), task['id'], 'pending'))
            finally:
                connection.close()

    def consume_delivery(self, execution_id: int, source_id: int, input_key: str) -> int:
        """凭已核对的原生输入认领业务尝试，额度及普通澄清沿用原尝试。

        :param execution_id: 当前候选执行。
        :param source_id: 实际消费输入的来源。
        :param input_key: 固定原生 user 消息身份。
        :return: 业务尝试 ID。
        """
        with self.owner.write_lock:
            connection = self.owner.database()
            try:
                with connection:
                    execution = connection.execute('SELECT e.* FROM project_task_executions e JOIN project_execution_sources x '
                        'ON x.execution_id=e.id WHERE e.id=? AND x.id=?', (execution_id, source_id)).fetchone()
                    if not execution or execution['role'] != 'candidate' or execution['ended_at'] is not None:
                        raise ValueError('输入消费不属于开放候选执行')
                    delivery = connection.execute('SELECT * FROM project_task_deliveries WHERE id=? AND task_id=?',
                        (execution['delivery_id'], execution['task_id'])).fetchone()
                    if not delivery or not input_key:
                        raise ValueError('输入消费缺少冻结投递意图')
                    if delivery['status'] == 'consumed':
                        if delivery['input_key'] != input_key:
                            raise ValueError('已消费输入的原生身份冲突')
                        attempt = connection.execute('SELECT id FROM project_task_attempts WHERE task_id=? ORDER BY attempt_no DESC LIMIT 1',
                            (execution['task_id'],)).fetchone()
                        if not attempt:
                            raise ValueError('已消费输入缺少业务尝试事实')
                        connection.execute('UPDATE project_task_executions SET attempt_id=? WHERE id=?', (attempt['id'], execution_id))
                        return attempt['id']
                    task = connection.execute('SELECT * FROM project_scenario_tasks WHERE id=?', (execution['task_id'],)).fetchone()
                    attempt = connection.execute('SELECT * FROM project_task_attempts WHERE task_id=? ORDER BY attempt_no DESC LIMIT 1',
                        (execution['task_id'],)).fetchone()
                    reason = task['next_reason']
                    definition = json.loads(task['definition_json'])
                    development = definition.get('development_cycle') in ('feature', 'bug')
                    if not attempt or reason in ('initial', 'correction', 'timeout') and not (development and reason == 'timeout'):
                        if not development and task['attempt_count'] >= 3:
                            raise ValueError('任务首次执行及两次继续／修正已经用尽')
                        cursor = connection.execute('INSERT INTO project_task_attempts(task_id,attempt_no,reason,consumed_at) VALUES(?,?,?,?)',
                            (task['id'], task['attempt_count'] + 1, reason, time.time()))
                        attempt_id = cursor.lastrowid
                        connection.execute('UPDATE project_scenario_tasks SET attempt_count=attempt_count+1,next_reason=? WHERE id=?',
                            ('continuation', task['id']))
                    else:
                        attempt_id = attempt['id']
                    connection.execute("UPDATE project_task_deliveries SET status='consumed',input_key=?,consumed_source_id=?,consumed_at=? WHERE id=?",
                        (input_key, source_id, time.time(), delivery['id']))
                    connection.execute('UPDATE project_task_executions SET attempt_id=? WHERE id=?', (attempt_id, execution_id))
                    return attempt_id
            finally:
                connection.close()

    def capture_submission(self, execution: dict, source: dict) -> None:
        """在真实冻结证明下封存回答，先落作业再让driver正常退出。

        :param execution: 开放候选执行行。
        :param source: 当前精确额度来源。
        :return: None；本方法只形成候选，不接受业务结果。
        """
        if not source['request_relative'] or not self.owner.plans.control:
            return
        request_path = self.owner.data / safe_relative(source['request_relative'])
        if not request_path.exists():
            return
        request = self.owner.plans._request(request_path)
        existing=self.owner._one('SELECT evidence_json,response_key FROM project_evaluation_jobs WHERE source_id=? ORDER BY id DESC LIMIT 1',(source['id'],))
        if existing:
            evidence=json.loads(existing['evidence_json'])
            if evidence.get('request') != request:
                raise ValueError('已封存来源出现不同的候选通知')
            self.owner.plans._decision({'source':source['source'],'decision_relative':source['decision_relative'],
                'decision_json':canonical_json(evidence['decision']).decode()})
            return
        task = self.task(execution['task_id'])
        delivery = self.owner._one('SELECT * FROM project_task_deliveries WHERE id=?', (execution['delivery_id'],))
        plan = {'id': task['scenario_instance_id'], 'generation': execution['generation'], 'session_id': execution['session_id']}
        adapted_source = {**source, 'run_id': execution['run_id'], 'phase_seq': execution['turn_no']}
        adapted_attempt = {'step_id': task['task_key'], 'expected_prompt': delivery['prompt']}
        frozen = False
        try:
            proof = self.owner.plans.control(execution['run_id'], source['quota_attempt'], 'freeze')
            if not proof.get('frozen') or proof.get('source') != source['source']:
                raise ValueError('候选完整作业树暂停证明不符')
            frozen = True
            boundaries = self.owner.plans._evidence(adapted_source, adapted_attempt, plan, request)
            path = self.owner.data / safe_relative(source['native_relative']) / (execution['session_id'] + '.jsonl')
            dialogue = self.owner.plans.dialogue.read_dialogue(path)
            response = next(item for item in dialogue if item['key'] == request['response_key'])
            resolved_model=observed_model(path.parent,response,execution['session_id'])
            if not isinstance(response['text'], str) or len(response['text'].encode()) > 1024 * 1024:
                raise ValueError('候选回答缺失或超过封存上限')
            self.consume_delivery(execution['id'], source['id'], request['input_key'])
            conversation = self._conversation(task['id'])
            snapshot, candidate = self.owner._capture(task)
            project = self.owner._release(task['catalog_release_id']).projects[task['project_key']]
            definition = json.loads(task['definition_json'])
            rubric = load_rubric(project.root, definition)
            answer_path = self.owner.data / 'project-artifacts/answers' / (digest_json(response['text']) + '.json')
            write_document(answer_path, {'text': response['text']})
            decision = {key: request[key] for key in ('schema', 'plan_id', 'run_id', 'source', 'generation',
                'session_id', 'phase_seq', 'step_id', 'response_key')}
            decision['action'] = 'complete'
            with self.owner.write_lock:
                connection = self.owner.database()
                try:
                    with connection:
                        parent = connection.execute('SELECT generation,status FROM project_iteration_batches WHERE id=?', (task['batch_id'],)).fetchone()
                        if parent['generation'] != execution['generation'] or parent['status'] not in ('active', 'pausing'):
                            return
                        connection.execute('INSERT OR IGNORE INTO project_evaluation_jobs(task_id,source_id,turn_no,generation,response_key,'
                            'response_digest,input_digest,basis_digest,candidate_digest,candidate_relative,answer_relative,evidence_json,'
                            'version,response_budget_sec,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                            (task['id'], source['id'], execution['turn_no'], execution['generation'], request['response_key'],
                                digest_json(response['text']), digest_json(conversation), digest_json(rubric), snapshot['digest'],
                                str(candidate.relative_to(self.owner.data)), str(answer_path.relative_to(self.owner.data)),
                                canonical_json({'request': request, 'boundaries': boundaries, 'decision': decision,
                                    'resolved_model':resolved_model,
                                    'parent_code_digest':read_document(self.owner.data/'project-artifacts/task-inputs'/str(task['id'])/'code-dependency.json')['base_checkpoint_digest'],
                                    'parent_code_job_id':read_document(self.owner.data/'project-artifacts/task-inputs'/str(task['id'])/'code-dependency.json')['base_checkpoint_job_id'],
                                    'input_checkpoint_digest':task['input_checkpoint_digest'] or task['checkpoint_digest'],
                                    'conversation': conversation}).decode(),
                                definition['evaluation']['version'], 2 * json.loads(task['policy_json'])['review_timeout_sec'], time.time()))
                        connection.execute('UPDATE project_execution_sources SET evidence_end_json=? WHERE id=?',
                            (canonical_json(boundaries).decode(), source['id']))
                        connection.execute("UPDATE project_scenario_tasks SET status='evaluating',phase='waiting_release',updated_at=? WHERE id=?",
                            (time.time(), task['id']))
                finally:
                    connection.close()
            write_document(self.owner.data / safe_relative(source['decision_relative']), decision, mode=0o640, owner=(0, 1000))
        finally:
            if frozen:
                self.owner.plans.control(execution['run_id'], source['quota_attempt'], 'resume')

    def _conversation(self, task_id: int) -> list[dict]:
        events = []
        deliveries = self.owner._rows("SELECT d.* FROM project_task_deliveries d WHERE d.task_id=? AND d.status='consumed' "
            "AND EXISTS(SELECT 1 FROM project_execution_sources x JOIN project_task_executions e ON e.id=x.execution_id "
            "WHERE x.delivery_id=d.id AND e.role='candidate') ORDER BY d.id", (task_id,))
        jobs=self.owner._rows('SELECT j.*,COALESCE(x.delivery_id,e.delivery_id) AS candidate_delivery_id '
            'FROM project_evaluation_jobs j JOIN project_execution_sources x ON x.id=j.source_id '
            "JOIN project_task_executions e ON e.id=x.execution_id WHERE j.task_id=? AND e.task_id=j.task_id AND e.role='candidate' ORDER BY j.id",(task_id,))
        if any(job['candidate_delivery_id'] not in {delivery['id'] for delivery in deliveries} for job in jobs):
            raise ValueError('历史回答缺少对应的已消费业务输入')
        # 投递ID与回答来源形成持久因果顺序；壁钟回拨不能把补充问题移到前一答复之前。
        for delivery in deliveries:
            if digest_json(delivery['prompt']) != delivery['input_digest']:
                raise ValueError('已消费业务输入摘要不符')
            events.append({'role':'user','content':delivery['prompt']})
            for job in jobs:
                if job['candidate_delivery_id']!=delivery['id']:
                    continue
                answer = read_document(self.owner.data / safe_relative(job['answer_relative']))['text']
                if digest_json(answer) != job['response_digest']:
                    raise ValueError('先前业务回答摘要不符')
                events.append({'role':'assistant','content':answer})
        return events

    def execution_released(self, run_id: str, quota_attempt: int, error: str | None) -> None:
        """逐source保存真实释放与计时边界，旧额度回包不能覆盖新代。

        :param run_id: 真实 Run。
        :param quota_attempt: 清理完成的额度代次。
        :param error: 原严格清理失败原因。
        :return: None。
        """
        execution = self.owner._one('SELECT e.*,r.quota_attempt FROM project_task_executions e JOIN runs r ON r.id=e.run_id WHERE e.run_id=?', (run_id,))
        if not execution or execution['quota_attempt'] != quota_attempt:
            return
        source = self.owner._one('SELECT * FROM project_execution_sources WHERE execution_id=? AND quota_attempt=?', (execution['id'], quota_attempt))
        if source is None:
            return
        boundaries = source['evidence_end_json']
        if not error:
            try:
                self._observe_input(execution,source)
                if boundaries is None:
                    boundaries = canonical_json(self.owner.plans._sizes(self.owner.data / safe_relative(source['native_relative']))).decode()
                self._collect_work(source, final=True)
            except (OSError, ValueError, KeyError) as failure:
                error = '执行计时或会话边界未能核实：' + str(failure)[:200]
        self.owner.plans._write('UPDATE project_execution_sources SET released_at=?,execution_error=?,evidence_end_json=COALESCE(evidence_end_json,?) '
            'WHERE id=?', (None if error else time.time(), error, boundaries, source['id']))

    def permit_start(self, run_id: str, source: str) -> None:
        """先持久许可再发布driver ready，未许可来源可证明尚未投递。

        :param run_id: 当前Run。
        :param source: 当前精确来源。
        :return: None；父代次变化则拒绝实际执行。
        """
        context=self.context(run_id)
        if not context or not self.owner.can_start(run_id):
            raise ValueError('发布场景启动许可前父门禁已变化')
        with self.owner.write_lock:
            connection=self.owner.database()
            try:
                with connection:
                    cursor=connection.execute('UPDATE project_execution_sources SET start_permitted=1 WHERE execution_id=? AND source=? AND released_at IS NULL '
                        'AND EXISTS(SELECT 1 FROM project_task_executions e JOIN project_scenario_tasks t ON t.id=e.task_id '
                        'JOIN project_scenario_instances s ON s.id=t.scenario_instance_id JOIN project_instances i ON i.id=s.instance_id '
                        "JOIN project_iteration_batches b ON b.id=i.batch_id JOIN runs r ON r.id=e.run_id WHERE e.id=project_execution_sources.execution_id "
                        "AND b.status='active' AND b.generation=e.generation AND r.status='running' AND r.quota_attempt=project_execution_sources.quota_attempt)",
                        (context['execution_id'],source))
                    if cursor.rowcount!=1:
                        raise ValueError('场景启动许可的父代次或真实Run已变化')
            finally:
                connection.close()

    def recover(self, cleanup) -> None:
        """重启先收口原执行，完整候选只恢复验收，禁止重建工作区。

        :param cleanup: 原Runner严格清理入口。
        :return: None。
        """
        executions = self.owner._rows('SELECT e.*,r.status,r.started_at,r.worker_container,r.quota_attempt '
            'FROM project_task_executions e JOIN runs r ON r.id=e.run_id WHERE e.ended_at IS NULL')
        for execution in executions:
            source = self.owner._one('SELECT released_at,execution_error FROM project_execution_sources WHERE execution_id=? AND quota_attempt=?',
                (execution['id'],execution['quota_attempt']))
            if (execution['status']=='quota_wait' and source and (source['released_at'] or source['execution_error'])
                    or execution['status'] == 'queued' and not execution['started_at'] and not execution['worker_container']):
                continue
            try:
                cleanup(execution['run_id'])
                self.execution_released(execution['run_id'],execution['quota_attempt'],None)
                self.owner.plans._write("UPDATE runs SET status='failed',error='服务重启中断，保留场景候选及未完成现场',ended_at=? "
                    "WHERE id=? AND status IN ('running','stopping')",(time.time(),execution['run_id']))
            except Exception as error:
                self.execution_released(execution['run_id'],execution['quota_attempt'],'恢复严格收口失败：'+type(error).__name__)

    def finish_captured_quota(self, run_id: str) -> bool:
        """完整输出遇额度中断时只收口验收，不再领取新模型代次。

        :param run_id: 原候选或评审运行。
        :return: 是否已有完整输出，调用者应停止额度重启。
        """
        execution = self.owner._one('SELECT e.*,r.status AS run_status,r.quota_attempt FROM project_task_executions e '
            'JOIN runs r ON r.id=e.run_id WHERE e.run_id=? AND e.ended_at IS NULL', (run_id,))
        if not execution or execution['run_status'] != 'quota_wait':
            return False
        source = self.owner._one('SELECT * FROM project_execution_sources WHERE execution_id=? AND quota_attempt=?',
            (execution['id'],execution['quota_attempt']))
        if not source:
            return False
        if source['execution_error']:
            batch = self.owner._one('SELECT * FROM project_iteration_batches WHERE id=?',(self.task(execution['task_id'])['batch_id'],))
            self._settle_execution(batch,execution,source)
            return True
        captured = (self.owner._one('SELECT id FROM project_evaluation_jobs WHERE source_id=?',(source['id'],))
            if execution['role']=='candidate' else json.loads(execution['result_json'] or '{}').get('source_id')==source['id'])
        if not captured:
            return False
        if self.owner.is_executing(run_id,execution['quota_attempt']) or not source['released_at'] and not source['execution_error']:
            return True
        # 真实运行因额度中断而结束；保留中断事实，任务结果由独立验收决定。
        self.owner.plans._write("UPDATE runs SET status='failed',ended_at=?,error='额度中断，完整输出已封存，仅继续独立验收' "
            "WHERE id=? AND status='quota_wait' AND quota_attempt=?", (time.time(),run_id,execution['quota_attempt']))
        return True

    def _collect_work(self, source: dict, *, final: bool = False) -> None:
        segment = self.owner._one('SELECT * FROM project_work_segments WHERE source_id=? ORDER BY segment_seq DESC LIMIT 1', (source['id'],))
        if not segment or segment['status'] == 'settled':
            return
        path = self.owner.data / safe_relative(source['work_relative'])
        if not path.exists():
            if final:
                if not source['start_permitted']:
                    self.update_segment(segment['id'],segment['boot_id'],0,settled=True)
                    return
                self.update_segment(segment['id'], segment['boot_id'], segment['confirmed_sec'], uncertain=True)
                raise ValueError('driver缺少有效工作边界，保留未决预算')
            return
        document = self.owner.plans._request(path, maximum=65536)
        if (document.get('source') != source['source'] or document.get('segment_id') != segment['id']
                or document.get('boot_id') != segment['boot_id']):
            raise ValueError('driver工作片段身份不符')
        settled = document.get('settled') is True
        self.update_segment(segment['id'], document['boot_id'], document['elapsed_sec'],
            settled=settled, uncertain=final and not settled)
        if final and not settled:
            raise ValueError('driver未给出准确退出计时边界')

    def _observe_input(self, execution: dict, source: dict) -> None:
        delivery = self.owner._one('SELECT * FROM project_task_deliveries WHERE id=?', (source['delivery_id'] or execution['delivery_id'],))
        native = self.owner.data / safe_relative(source['native_relative']) / (execution['session_id'] + '.jsonl')
        if not native.is_file():
            return
        offset = json.loads(source['evidence_start_json'] or '{}').get(native.name, 0)
        if native.is_symlink() or native.stat().st_size < offset:
            raise ValueError('输入消费原生会话缺失或被截断')
        dialogue = self.owner.plans.dialogue.read_dialogue(native, offset=offset)
        user = next((item for item in dialogue if item['role'] == 'user' and item['normal'] and isinstance(item['text'], str)
            and self.owner.plans.dialogue._matches_input(item['text'], delivery['prompt'])), None)
        if not user:
            return
        if execution['role'] == 'candidate':
            self.consume_delivery(execution['id'], source['id'], user['key'])
        else:
            self.owner.plans._write('UPDATE project_evaluation_jobs SET review_attempt=MAX(review_attempt,?) WHERE id=?',
                (execution['review_attempt'], execution['evaluation_job_id']))
            self.owner.plans._write("UPDATE project_task_deliveries SET status='consumed',input_key=?,consumed_source_id=?,consumed_at=COALESCE(consumed_at,?) WHERE id=?",
                (user['key'], source['id'], time.time(), delivery['id']))

    def drive(self, batch: dict, account: dict | None) -> None:
        """在原调度tick中推进候选、异步验收与优先评审，不持名额互等。

        :param batch: 当前冻结批次。
        :param account: 原账号身份行。
        :return: None。
        """
        executions = self.owner._rows('SELECT e.*,r.status AS run_status,r.quota_attempt,r.error AS run_error FROM project_task_executions e '
            'JOIN project_scenario_tasks t ON t.id=e.task_id JOIN project_scenario_instances s ON s.id=t.scenario_instance_id '
            'JOIN project_instances i ON i.id=s.instance_id JOIN runs r ON r.id=e.run_id WHERE i.batch_id=? AND e.ended_at IS NULL ORDER BY e.id',
            (batch['id'],))
        for execution in executions:
            if execution['run_status']=='quota_wait' and self.finish_captured_quota(execution['run_id']):
                latest = self.owner._one('SELECT status,error FROM runs WHERE id=?',(execution['run_id'],))
                execution.update(run_status=latest['status'],run_error=latest['error'])
            if batch['status'] in ('stopping', 'blocked') or batch['generation'] != execution['generation']:
                if execution['run_status'] in ('queued', 'running', 'quota_wait'):
                    self.owner.stop_run(execution['run_id'])
            source = self.owner._one('SELECT * FROM project_execution_sources WHERE execution_id=? AND quota_attempt=? ORDER BY id DESC LIMIT 1',
                (execution['id'], execution['quota_attempt']))
            if execution['run_status'] == 'queued' and account and not self.owner.is_executing(execution['run_id'],execution['quota_attempt']):
                run = self.owner._one('SELECT r.*,t.prompt,t.timeout_sec FROM runs r JOIN tasks t ON t.id=r.task_id WHERE r.id=?',(execution['run_id'],))
                self.owner.submit(execution['run_id'],account,{'id':run['task_id'],'prompt':run['prompt'],'timeout_sec':run['timeout_sec'],
                    'quota_attempt':run['quota_attempt'],'claude_code_version':run['claude_code_version'],
                    'claude_effort_level':run['claude_effort_level'],'model_override':run['execution_model']})
            if execution['run_status'] == 'running' and source and batch['status'] in ('active', 'pausing'):
                self._observe_input(execution,source)
                self._collect_work(source)
                if execution['role'] == 'candidate':
                    self.capture_submission(execution, source)
                else:
                    self._capture_review(execution, source)
            elif execution['run_status'] in ('success', 'failed', 'timeout', 'stopped', 'auth_failed'):
                if self.owner.is_executing(execution['run_id'], execution['quota_attempt']):
                    continue
                self._settle_execution(batch, execution, source)
        self._advance_jobs(batch)
        scenarios = self.owner._rows('SELECT s.* FROM project_scenario_instances s JOIN project_instances i ON i.id=s.instance_id '
            'WHERE i.batch_id=? ORDER BY i.visit_order,s.id', (batch['id'],))
        for scenario in scenarios:
            self.refresh_readiness(scenario['id'])
        if batch['status'] in ('stopping', 'pausing'):
            if not self._open_executions(batch['id']):
                status = 'stopped' if batch['status'] == 'stopping' else 'paused'
                self.owner.plans._write('UPDATE project_iteration_batches SET status=?,updated_at=? WHERE id=? AND status=?',
                    (status, time.time(), batch['id'], batch['status']))
            return
        if batch['status'] != 'active' or not account:
            return
        self._close_finished(batch)
        if self.owner._one('SELECT status FROM project_iteration_batches WHERE id=?', (batch['id'],))['status'] != 'active':
            return
        if self.owner.review_refresh and self.owner.review_refresh(account):
            return
        if self.owner.plans.admission and not self.owner.plans.admission(account).get('allowed'):
            return
        policy = json.loads(batch['policy_json'])
        capacity = min(self.owner.plans.limit, policy['concurrency']) - len(self._open_executions(batch['id']))
        if capacity <= 0:
            return
        ready_reviews = self.owner._rows('SELECT j.* FROM project_evaluation_jobs j JOIN project_scenario_tasks t ON t.id=j.task_id '
            'JOIN project_scenario_instances s ON s.id=t.scenario_instance_id JOIN project_instances i ON i.id=s.instance_id '
            "WHERE i.batch_id=? AND j.status='review_ready' ORDER BY j.created_at,j.id", (batch['id'],))
        for job in ready_reviews[:capacity]:
            if self._reserve_review(batch, account, job):
                capacity -= 1
        # 全账号有已就绪评审时先留共享槽位，避免新候选持续插队。
        review_busy = self.owner._one("SELECT e.id FROM project_task_executions e JOIN runs r ON r.id=e.run_id WHERE r.account_id=? AND e.role='review' AND e.ended_at IS NULL",(account['id'],))
        ready_for_account = self.owner._one('SELECT j.id FROM project_evaluation_jobs j JOIN project_scenario_tasks t ON t.id=j.task_id '
            'JOIN project_scenario_instances s ON s.id=t.scenario_instance_id JOIN project_instances i ON i.id=s.instance_id '
            "JOIN project_iteration_batches b ON b.id=i.batch_id WHERE b.account_id=? AND b.status='active' AND b.generation=j.generation AND j.status='review_ready' LIMIT 1",(account['id'],))
        if capacity <= 0 or ready_for_account and not review_busy:
            return
        if batch.get('next_launch_at') and batch['next_launch_at'] > time.time():
            return
        instances = self.owner._rows('SELECT * FROM project_instances WHERE batch_id=? ORDER BY visit_order,id', (batch['id'],))
        pool = [item for item in instances if item['in_pool'] and item['status'] != 'completed']
        for instance in instances:
            if len(pool) >= min(policy['active_projects'], len(instances)):
                break
            if not instance['in_pool'] and instance['status'] != 'completed':
                self.owner.plans._write('UPDATE project_instances SET in_pool=1 WHERE id=?', (instance['id'],))
                pool.append(instance)
        resumable = {item['instance_id'] for item in self.owner._rows('SELECT DISTINCT s.instance_id FROM project_scenario_tasks t '
            'JOIN project_scenario_instances s ON s.id=t.scenario_instance_id JOIN project_instances i ON i.id=s.instance_id '
            "WHERE i.batch_id=? AND t.status='ready' AND (t.turn_no>1 OR t.attempt_count>0) "
            "AND json_extract(t.definition_json,'$.development_cycle') IN ('feature','bug')", (batch['id'],))}
        pool.sort(key=lambda item: item['id'] not in resumable)
        for instance in pool:
            if capacity <= 0:
                break
            busy = self.owner._one('SELECT e.id FROM project_task_executions e JOIN project_scenario_tasks t ON t.id=e.task_id '
                'JOIN project_scenario_instances s ON s.id=t.scenario_instance_id WHERE s.instance_id=? AND e.role=? AND e.ended_at IS NULL',
                (instance['id'], 'candidate'))
            if busy:
                continue
            ready = self.owner._one('SELECT t.id FROM project_scenario_tasks t JOIN project_scenario_instances s ON s.id=t.scenario_instance_id '
                "WHERE s.instance_id=? AND t.selected=1 AND t.status='ready' AND NOT EXISTS(SELECT 1 FROM project_scenario_tasks sibling "
                "WHERE sibling.scenario_instance_id=s.id AND sibling.status IN ('running','evaluating')) "
                "AND NOT EXISTS(SELECT 1 FROM project_scenario_plans p WHERE p.scenario_instance_id=s.id AND p.ended_at IS NULL "
                "AND NOT EXISTS(SELECT 1 FROM json_each(p.task_ids_json) member WHERE member.value=t.id)) ORDER BY t.id LIMIT 1", (instance['id'],))
            if ready and self._reserve_candidate(batch, account, ready['id']):
                capacity -= 1

    def _open_executions(self, batch_id: int) -> list[dict]:
        return self.owner._rows('SELECT e.* FROM project_task_executions e JOIN project_scenario_tasks t ON t.id=e.task_id '
            'JOIN project_scenario_instances s ON s.id=t.scenario_instance_id JOIN project_instances i ON i.id=s.instance_id '
            'WHERE i.batch_id=? AND e.ended_at IS NULL', (batch_id,))

    def _reserve_candidate(self, batch: dict, account: dict, task_id: int) -> bool:
        task = self.task(task_id)
        if self.development.handles(task) and task['turn_no'] == 1 and not task['attempt_count']:
            continuing = self.owner._rows('SELECT t.id FROM project_scenario_tasks t '
                'JOIN project_scenario_instances s ON s.id=t.scenario_instance_id JOIN project_instances i ON i.id=s.instance_id '
                'JOIN project_iteration_batches b ON b.id=i.batch_id '
                "WHERE b.account_id=? AND b.status='active' AND t.selected=1 AND t.id<>? AND (t.turn_no>1 OR t.attempt_count>0) "
                "AND json_extract(t.definition_json,'$.development_cycle') IN ('feature','bug') AND t.status='ready'", (account['id'], task_id))
            # 仅可执行的续做优先；外部服务等待或预算异常不能把整个账号的新任务永久卡住。
            for previous in continuing:
                remaining = self.budget(previous['id'])
                if not remaining['uncertain'] and remaining['slice_sec'] >= 1:
                    return False
        budget = self.budget(task_id)
        if budget['uncertain'] or budget['slice_sec'] < 1:
            self._task_status(task_id, 'blocked' if budget['uncertain'] else 'exhausted', '工作预算待核实' if budget['uncertain'] else '累计工作预算已用尽')
            return False
        if (not self.development.handles(task) and task['next_reason'] in ('initial', 'timeout', 'correction')
                and task['attempt_count'] >= 3):
            self._task_status(task_id, 'exhausted', '首次执行及两次继续／修正已用尽')
            return False
        definition = json.loads(task['definition_json'])
        prompt = task['next_prompt']
        if task['next_reason'] == 'initial':
            project = self.owner._release(task['catalog_release_id']).projects[task['project_key']]
            scenario = self.owner._one('SELECT definition_json FROM project_scenario_instances WHERE id=?',(task['scenario_instance_id'],))
            entry = next(item for item in json.loads(scenario['definition_json'])['entries'] if item['id']==task['entry_key'])
            for relative in [*entry.get('materials', []),*definition.get('materials', [])]:
                content = (project.root / safe_relative(relative)).read_text(encoding='utf-8')
                prompt += '\nBusiness material ' + Path(relative).name + ':\n' + content
        if len(prompt.encode()) > 48 * 1024:
            self._task_status(task_id, 'blocked', '公开业务输入超过driver完整性上限')
            return False
        return self._reserve_run(batch, account, task, 'candidate', prompt)

    def _reserve_run(self, batch: dict, account: dict, task: dict, role: str, prompt: str,
                     job: dict | None = None, review_attempt: int | None = None) -> bool:
        policy, now = json.loads(batch['policy_json']), time.time()
        run_id = uuid.uuid4().hex[:12]
        frozen = json.loads(task['execution_json']) if task['execution_json'] else self.owner.settings(account)
        session = task['session_id'] if role == 'candidate' else str(uuid.uuid4())
        if job and job['review_resume']:
            previous = self.owner._one('SELECT session_id FROM project_task_executions WHERE evaluation_job_id=? ORDER BY id DESC LIMIT 1', (job['id'],))
            if previous:
                session = previous['session_id']
        timeout = policy['timeout_sec'] if role == 'candidate' else policy['review_timeout_sec']
        with self.owner.write_lock:
            connection = self.owner.database()
            try:
                with connection:
                    parent = connection.execute('SELECT status,generation FROM project_iteration_batches WHERE id=?', (batch['id'],)).fetchone()
                    current = connection.execute('SELECT status FROM project_scenario_tasks WHERE id=?', (task['id'],)).fetchone()
                    if parent['status'] != 'active' or parent['generation'] != batch['generation']:
                        return False
                    if role == 'candidate' and current['status'] != 'ready':
                        return False
                    occupied = connection.execute('SELECT COUNT(*) FROM project_task_executions e JOIN runs r ON r.id=e.run_id '
                        'WHERE r.account_id=? AND e.ended_at IS NULL', (account['id'],)).fetchone()[0]
                    if occupied >= min(policy['concurrency'], self.owner.plans.limit):
                        return False
                    if job and connection.execute('SELECT status FROM project_evaluation_jobs WHERE id=?', (job['id'],)).fetchone()['status'] != 'review_ready':
                        return False
                    plan_id = self._plan_for_task(connection,task,policy,batch['generation']) if role=='candidate' else None
                    if role=='candidate' and plan_id is None:
                        return False
                    phase_key = f"{role}:{task['turn_no']}:{run_id}"
                    delivery = connection.execute('INSERT INTO project_task_deliveries(task_id,phase_key,prompt,input_digest,created_at) VALUES(?,?,?,?,?)',
                        (task['id'], phase_key, prompt, digest_json(prompt), now))
                    generic = connection.execute('INSERT INTO tasks(topic_no,title,prompt,account_id,timeout_sec,repeat_n) VALUES(?,?,?,?,?,1)',
                        (1, f"项目场景 / {task['task_key']} / {'回答' if role == 'candidate' else '独立评审'}", prompt, account['id'], timeout))
                    generic_id = generic.lastrowid
                    connection.execute('INSERT INTO runs(id,task_id,account_id,status,run_kind,claude_code_version,claude_code_version_source,claude_effort_level,execution_model,quota_identity) '
                        'VALUES(?,?,?,?,?,?,?,?,?,?)', (run_id, generic_id, account['id'], 'queued',
                            'project_iteration' if role == 'candidate' else 'project_review', frozen['claude_code_version'],frozen.get('claude_code_version_source'),
                            frozen['claude_effort_level'], frozen['execution_model'], batch['account_identity']))
                    connection.execute('INSERT INTO project_task_executions(task_id,plan_id,run_id,role,evaluation_job_id,review_attempt,turn_no,generation,session_id,delivery_id,created_at) '
                        'VALUES(?,?,?,?,?,?,?,?,?,?,?)', (task['id'], plan_id, run_id, role, job['id'] if job else None, review_attempt,
                            task['turn_no'], batch['generation'], session, delivery.lastrowid, now))
                    connection.execute('UPDATE project_scenario_instances SET execution_json=COALESCE(execution_json,?),status=?,updated_at=? WHERE id=?',
                        (canonical_json(frozen).decode(), 'running', now, task['scenario_instance_id']))
                    if role == 'candidate':
                        connection.execute("UPDATE project_scenario_tasks SET status='running',phase='queued',updated_at=? WHERE id=?", (now, task['id']))
                    else:
                        connection.execute("UPDATE project_evaluation_jobs SET status='review_queued',review_result_json=NULL WHERE id=?", (job['id'],))
                    connection.execute('UPDATE project_iteration_batches SET last_launch_at=?,next_launch_at=NULL,updated_at=? WHERE id=?', (now, now, batch['id']))
            finally:
                connection.close()
        payload = {'id': generic_id, 'prompt': prompt, 'timeout_sec': timeout, **frozen, 'model_override': frozen['execution_model']}
        # ACK丢失仍保留已绑定Run，由恢复对账处理，不能删绑定后盲建第二次执行。
        self.owner.submit(run_id, account, payload)
        return True

    def _plan_for_task(self, connection, task: dict, policy: dict, generation: int) -> int | None:
        plan = connection.execute('SELECT * FROM project_scenario_plans WHERE scenario_instance_id=? AND ended_at IS NULL',
            (task['scenario_instance_id'],)).fetchone()
        if plan:
            return plan['id'] if task['id'] in json.loads(plan['task_ids_json']) else None
        available = [dict(row) for row in connection.execute("SELECT * FROM project_scenario_tasks WHERE scenario_instance_id=? AND selected=1 AND status NOT IN ('passed','failed','exhausted','blocked','cancelled') ORDER BY id",(task['scenario_instance_id'],))]
        chosen = [task['id']]
        remaining = max(1,policy['rotation_steps']-self.owner._one('SELECT visit_completed FROM project_instances WHERE id=?',(task['instance_id'],))['visit_completed'])
        limit = min(policy['steps_per_plan'],remaining)
        all_tasks = {item['task_key']:dict(item) for item in connection.execute(
            'SELECT * FROM project_scenario_tasks WHERE scenario_instance_id=?',(task['scenario_instance_id'],))}
        while len(chosen)<limit:
            eligible = next((item for item in available if item['id'] not in chosen and all(
                all_tasks[dependency['task_id']]['status']=='passed' or all_tasks[dependency['task_id']]['id'] in chosen
                for dependency in json.loads(item['definition_json'])['requires'])),None)
            if eligible is None:
                break
            chosen.append(eligible['id'])
        cursor = connection.execute('INSERT INTO project_scenario_plans(scenario_instance_id,generation,task_ids_json,created_at) VALUES(?,?,?,?)',
            (task['scenario_instance_id'],generation,canonical_json(chosen).decode(),time.time()))
        return cursor.lastrowid

    def _task_status(self, task_id: int, status: str, message: str | None = None) -> None:
        self.owner.plans._write('UPDATE project_scenario_tasks SET status=?,error=?,updated_at=? WHERE id=?',
            (status, message, time.time(), task_id))
        if status in TASK_TERMINAL:
            self.owner.plans._write('UPDATE project_task_attempts SET ended_at=?,result=? WHERE task_id=? AND ended_at IS NULL',
                (time.time(),status,task_id))
        if status in ('failed','exhausted','blocked'):
            with self.owner.write_lock:
                connection=self.owner.database()
                try:
                    with connection:
                        self._rotate_instance(connection,self.task(task_id)['instance_id'],'任务局部收口后轮换')
                finally:
                    connection.close()

    def _rotate_instance(self, connection, instance_id: int, reason: str) -> None:
        instance=connection.execute('SELECT batch_id,in_pool FROM project_instances WHERE id=?',(instance_id,)).fetchone()
        if not instance['in_pool']:
            return
        last=connection.execute('SELECT MAX(visit_order) FROM project_instances WHERE batch_id=?',(instance['batch_id'],)).fetchone()[0]
        connection.execute('UPDATE project_instances SET visit_order=?,visit_completed=0,in_pool=0,switch_reason=? WHERE id=? AND in_pool=1',
            (last+1,reason,instance_id))

    def _settle_execution(self, batch: dict, execution: dict, source: dict | None) -> None:
        task = self.task(execution['task_id'])
        if source and not source['released_at'] and not source['execution_error']:
            return
        if source and source['execution_error']:
            self._task_status(task['id'], 'blocked', source['execution_error'])
            if not source['execution_error'].startswith('执行计时或会话边界未能核实：'):
                self.owner._batch_error(batch['id'],'场景执行严格释放失败：'+source['execution_error'])
        elif execution['generation'] != batch['generation'] or batch['status'] in ('stopping', 'blocked'):
            self._task_status(task['id'], 'cancelled', '父批次已停止或代次变化')
        elif execution['run_status'] == 'auth_failed':
            self.owner._batch_error(batch['id'], '账号认证失效，保留场景现场')
        elif execution['role'] == 'review':
            self._settle_review(execution, source)
        elif source and self.owner._one('SELECT id FROM project_evaluation_jobs WHERE source_id=?', (source['id'],)):
            self.owner.plans._write("UPDATE project_evaluation_jobs SET status='queued' WHERE source_id=? AND status='waiting_release'", (source['id'],))
        elif execution['run_status'] == 'timeout' and execution['attempt_id']:
            development = self.development.handles(task)
            if not development:
                self.owner.plans._write("UPDATE project_task_attempts SET ended_at=?,result='timeout' WHERE id=? AND ended_at IS NULL",
                    (time.time(),execution['attempt_id']))
            if self.budget(task['id'])['slice_sec'] < 1 or not development and task['attempt_count'] >= 3:
                self._task_status(task['id'], 'exhausted', '超时后任务累计预算或继续次数已用尽')
            else:
                self.owner.plans._write("UPDATE project_scenario_tasks SET status='ready',phase='timeout_resume',next_reason=?,next_prompt=?,updated_at=? WHERE id=?",
                    ('continuation' if development else 'timeout',
                        'Continue the current unfinished task in the original session. Preserve completed work, the agreed plan, and existing files. Resume the current unfinished phase without starting over.', time.time(), task['id']))
        else:
            if task['infra_recoveries'] >= 2:
                self._task_status(task['id'], 'blocked', '执行基础设施恢复次数已用尽')
            else:
                self.owner.plans._write("UPDATE project_scenario_tasks SET status='ready',phase='infrastructure_resume',infra_recoveries=infra_recoveries+1,"
                    'next_reason=?,next_prompt=?,updated_at=? WHERE id=?',
                    ('continuation' if execution['attempt_id'] else task['next_reason'],
                        'Continue the current unfinished task in the original session. Preserve the existing files and work.' if execution['attempt_id'] else task['next_prompt'], time.time(), task['id']))
        self.owner.plans._write('UPDATE project_task_executions SET ended_at=? WHERE id=? AND ended_at IS NULL', (time.time(), execution['id']))
        policy = json.loads(batch['policy_json'])
        self.owner.plans._write('UPDATE project_iteration_batches SET next_launch_at=COALESCE(next_launch_at,?),updated_at=? WHERE id=?',
            (time.time() + random.randint(policy['interval_min_sec'], policy['interval_max_sec']), time.time(), batch['id']))

    def _close_finished(self, batch: dict) -> None:
        scenarios = self.owner._rows('SELECT s.id,s.instance_id FROM project_scenario_instances s JOIN project_instances i ON i.id=s.instance_id WHERE i.batch_id=?', (batch['id'],))
        for scenario in scenarios:
            tasks = self.owner._rows('SELECT status FROM project_scenario_tasks WHERE scenario_instance_id=? AND selected=1', (scenario['id'],))
            if tasks and all(task['status'] in TASK_TERMINAL for task in tasks):
                with self.owner.write_lock:
                    connection=self.owner.database()
                    try:
                        with connection:
                            changed=connection.execute("UPDATE project_scenario_instances SET status='completed',updated_at=? WHERE id=? AND status!='completed'",
                                (time.time(),scenario['id']))
                            if changed.rowcount:
                                self._rotate_instance(connection,scenario['instance_id'],'场景收口后轮换')
                    finally:
                        connection.close()
        plans = self.owner._rows('SELECT p.* FROM project_scenario_plans p JOIN project_scenario_instances s ON s.id=p.scenario_instance_id '
            'JOIN project_instances i ON i.id=s.instance_id WHERE i.batch_id=? AND p.ended_at IS NULL',(batch['id'],))
        for plan in plans:
            ids = json.loads(plan['task_ids_json'])
            rows = self.owner._rows('SELECT id,status FROM project_scenario_tasks WHERE scenario_instance_id=?',(plan['scenario_instance_id'],))
            selected = [row for row in rows if row['id'] in ids]
            passed = [row['id'] for row in selected if row['status']=='passed']
            ended = len(selected)==len(ids) and all(row['status'] in TASK_TERMINAL for row in selected)
            self.owner.plans._write('UPDATE project_scenario_plans SET passed_ids_json=?,status=?,ended_at=? WHERE id=?',
                (canonical_json(passed).decode(),'completed' if ended else 'running',time.time() if ended else None,plan['id']))
        for instance in self.owner._rows('SELECT id FROM project_instances WHERE batch_id=?', (batch['id'],)):
            if not self.owner._one("SELECT id FROM project_scenario_instances WHERE instance_id=? AND status!='completed'", (instance['id'],)):
                self.owner.plans._write("UPDATE project_instances SET status='completed',in_pool=0,updated_at=? WHERE id=?", (time.time(), instance['id']))
        if not self.owner._one("SELECT id FROM project_instances WHERE batch_id=? AND status!='completed'", (batch['id'],)):
            self.owner.plans._write("UPDATE project_iteration_batches SET status='completed',next_launch_at=NULL,updated_at=? WHERE id=? AND status='active'",
                (time.time(), batch['id']))

    def _advance_jobs(self, batch: dict) -> None:
        jobs = self.owner._rows('SELECT j.* FROM project_evaluation_jobs j JOIN project_scenario_tasks t ON t.id=j.task_id '
            'JOIN project_scenario_instances s ON s.id=t.scenario_instance_id JOIN project_instances i ON i.id=s.instance_id '
            "WHERE i.batch_id=? AND j.status IN ('queued','mechanical_running','dialogue_wait') ORDER BY j.id", (batch['id'],))
        if batch['status'] not in ('active', 'pausing'):
            return
        for job in jobs:
            with self._evaluation_lock:
                if job['id'] in self._evaluating:
                    continue
                self._evaluating.add(job['id'])
            thread = threading.Thread(target=self._mechanical_job, args=(job['id'],),
                name=f"project-evaluation-{job['id']}", daemon=True)
            thread.start()

    def _mechanical_job(self, job_id: int) -> None:
        try:
            job = self.owner._one('SELECT * FROM project_evaluation_jobs WHERE id=?', (job_id,))
            if not job or job['status'] not in ('queued', 'mechanical_running', 'dialogue_wait'):
                return
            task = self.task(job['task_id'])
            definition = json.loads(task['definition_json'])
            library = self.owner._release(task['catalog_release_id'])
            project = library.projects[task['project_key']]
            source = self.owner._one('SELECT * FROM project_execution_sources WHERE id=?', (job['source_id'],))
            if not source['released_at'] or source['execution_error']:
                return
            execution = self.owner._one('SELECT * FROM project_task_executions WHERE id=?', (source['execution_id'],))
            if execution['ended_at'] is None or task['generation'] != job['generation']:
                return
            if self.development.handles(task) and self.development.advance(job, task):
                return
            self.owner.plans._write("UPDATE project_evaluation_jobs SET status='mechanical_running' WHERE id=? AND status IN ('queued','mechanical_running','dialogue_wait')", (job_id,))
            candidate = self.owner.data / safe_relative(job['candidate_relative'])
            snapshot = read_document(self.owner.manifests / (job['candidate_digest'] + '.json'))
            before_digest = json.loads(job['evidence_json'])['input_checkpoint_digest']
            before = read_document(self.owner.manifests / (before_digest + '.json'))
            verified = self.development.handles(task) and job['native_result_json'] is not None
            report = json.loads(job['native_result_json']) if verified else check_change_scope(before, snapshot, definition['allowed_paths'])
            if snapshot_tree(candidate)['digest'] != job['candidate_digest']:
                raise ValueError('冻结候选对象被替换或篡改')
            if not verified and report['status'] == 'passed' and definition['evaluation'].get('native'):
                spec = read_document(project.root / safe_relative(definition['evaluation']['native']))
                profile = library.environments[project.manifest['environment']]
                answer = read_document(self.owner.data / safe_relative(job['answer_relative']))['text']
                native = self.owner.verifier.verify_native(candidate, project.root, spec,
                    library.root / 'environments' / project.manifest['environment'], profile, answer=answer)
                if native['status'] == 'error':
                    native = self.owner.verifier.verify_native(candidate, project.root, spec,
                        library.root / 'environments' / project.manifest['environment'], profile, answer=answer)
                if native['status'] == 'passed' and spec.get('regression'):
                    regression = self.owner.verifier.verify_native(candidate, project.root, spec,
                        library.root / 'environments' / project.manifest['environment'], profile, regression=True)
                    if regression['status'] == 'error':
                        regression = self.owner.verifier.verify_native(candidate, project.root, spec,
                            library.root / 'environments' / project.manifest['environment'], profile, regression=True)
                    native = {'status':regression['status'], 'business':native, 'regression':regression}
                report.update(native=native, status=native['status'])
            self.owner.plans._write('UPDATE project_evaluation_jobs SET native_result_json=? WHERE id=?', (canonical_json(report).decode(), job_id))
            job['native_result_json'] = canonical_json(report).decode()
            if report['status'] == 'error':
                self._block_evaluation(job, '独立原生验收环境不可用')
            elif report['status'] == 'failed':
                self._apply_result(job, {'decision': 'fail', 'outcome': None, 'feedback_codes': report.get('feedback_codes') or ['behavior_mismatch']})
            elif definition['kind'] == 'modify' and not definition['evaluation'].get('semantic', False):
                self._apply_result(job, {'decision': 'pass', 'outcome': definition['outcomes'][0], 'feedback_codes': []})
            else:
                package = self._package(job, task)
                write_document(self._package_path(job_id), package)
                self.owner.plans._write("UPDATE project_evaluation_jobs SET status='review_ready' WHERE id=? AND status='mechanical_running'", (job_id,))
        except Exception as error:
            job = self.owner._one('SELECT * FROM project_evaluation_jobs WHERE id=?', (job_id,))
            if job:
                self._block_evaluation(job, '验收证据或环境未能核实：' + type(error).__name__ + ': ' + str(error)[:200])
        finally:
            with self._evaluation_lock:
                self._evaluating.discard(job_id)

    def _package_path(self, job_id: int) -> Path:
        return self.owner.data / 'project-artifacts/evaluations' / str(job_id) / 'input.json'

    def _package(self, job: dict, task: dict) -> dict:
        definition = json.loads(task['definition_json'])
        project = self.owner._release(task['catalog_release_id']).projects[task['project_key']]
        rubric = load_rubric(project.root, definition)
        answer = read_document(self.owner.data / safe_relative(job['answer_relative']))['text']
        conversation = json.loads(job['evidence_json'])['conversation']
        question = next((item['content'] for item in conversation if item['role']=='user'), None)
        if question is None:
            raise ValueError('评审缺少已消费的原始业务问题')
        package = review_package({**job, 'job_id': job['id'],'resolved_model':json.loads(job['evidence_json'])['resolved_model']}, definition, rubric, answer, question,
            json.loads(job['native_result_json'] or '{}'), source_evidence(project.root, rubric),
            conversation=conversation,candidate_files=self._candidate_files(job))
        disclosed = {row['phase_key'].removeprefix('disclosure:') for row in self.owner._rows(
            "SELECT phase_key FROM project_task_deliveries WHERE task_id=? AND phase_key LIKE 'disclosure:%'", (task['id'],))}
        package['allowed_branches'] = [branch for branch in package['allowed_branches'] if branch['id'] not in disclosed]
        return package

    def _candidate_files(self, job: dict) -> dict:
        result={}
        size=0
        snapshot=read_document(self.owner.manifests/(job['candidate_digest']+'.json'))
        for relative in json.loads(job['native_result_json'])['changed_files']:
            item=snapshot['files'].get(relative)
            if item is None:
                result[relative]={'deleted':True}
                continue
            size+=item['size']+len(relative.encode())+200
            if size>512*1024:
                raise ValueError('实际交付文件超过完整评审输入上限')
            path=self.owner.objects/item['digest'][:2]/item['digest']
            if path.is_symlink():
                raise ValueError('冻结交付对象不能是链接')
            content=path.read_bytes()
            if len(content)!=item['size'] or hashlib.sha256(content).hexdigest()!=item['digest']:
                raise ValueError('评审实际交付文件摘要不符')
            try:
                text=content.decode('utf-8')
            except UnicodeDecodeError:
                text=None
            result[relative]={**item,'text':text,'binary':text is None}
        return result

    def _reserve_review(self, batch: dict, account: dict, job: dict) -> bool:
        task = self.task(job['task_id'])
        if self.owner.review_admission:
            admission=self.owner.review_admission(account)
            if not admission.get('allowed'):
                if admission.get('blocked'):
                    self._block_evaluation(job,admission.get('message') or '评审环境未就绪')
                return False
        if self.owner._one('SELECT e.id FROM project_task_executions e JOIN runs r ON r.id=e.run_id WHERE r.account_id=? '
                "AND e.role='review' AND e.ended_at IS NULL",(account['id'],)):
            return False
        previous = self.owner._one('SELECT review_attempt FROM project_task_executions WHERE evaluation_job_id=? ORDER BY id DESC LIMIT 1',(job['id'],))
        attempt = previous['review_attempt'] if job['review_resume'] and previous else job['review_attempt'] + 1
        if attempt > 2:
            self._block_evaluation(job, '同一冻结回答首次评审及一次错误重评已经用尽')
            return False
        budget = self.budget(task['id'], 'review', job_id=job['id'], review_attempt=attempt)
        if budget['uncertain'] or budget['slice_sec'] < 1:
            self._block_evaluation(job, '评审累计预算耗尽或工作尾段未能核实')
            return False
        package = read_document(self._package_path(job['id']))
        return self._reserve_run(batch, account, task, 'review', review_prompt(package,input_file='/input/package.json'), job, attempt)

    def _capture_review(self, execution: dict, source: dict) -> None:
        path = self.owner.data / safe_relative(source['request_relative'])
        if not path.exists() or not self.owner.plans.control:
            return
        request = self.owner.plans._request(path)
        saved=self.owner._one('SELECT result_json FROM project_task_executions WHERE id=?',(execution['id'],))
        if saved and saved['result_json']:
            previous=json.loads(saved['result_json'])
            if previous.get('source_id')==source['id'] and previous.get('response_key')==request.get('response_key'):
                decision={key:request[key] for key in ('schema','plan_id','run_id','source','generation','session_id','phase_seq','step_id','response_key')}
                self.owner.plans._decision({'source':source['source'],'decision_relative':source['decision_relative'],
                    'decision_json':canonical_json({**decision,'action':'complete'}).decode()})
                return
        task = self.task(execution['task_id'])
        delivery = self.owner._one('SELECT * FROM project_task_deliveries WHERE id=?', (execution['delivery_id'],))
        frozen = False
        try:
            proof = self.owner.plans.control(execution['run_id'], source['quota_attempt'], 'freeze')
            if not proof.get('frozen') or proof.get('source') != source['source']:
                raise ValueError('评审作业完整暂停证明不符')
            frozen = True
            boundaries = self.owner.plans._evidence({**source, 'run_id': execution['run_id'], 'phase_seq': execution['turn_no']},
                {'step_id': task['task_key'], 'expected_prompt': delivery['prompt']},
                {'id': task['scenario_instance_id'], 'generation': execution['generation'], 'session_id': execution['session_id']}, request)
            dialogue = self.owner.plans.dialogue.read_dialogue(self.owner.data / safe_relative(source['native_relative']) / (execution['session_id'] + '.jsonl'))
            response = next(item for item in dialogue if item['key'] == request['response_key'])
            package = read_document(self._package_path(execution['evaluation_job_id']))
            try:
                actual_model=observed_model(self.owner.data/safe_relative(source['native_relative']),response,execution['session_id'])
                if actual_model!=package['resolved_model']:
                    raise ValueError('评审实际模型与该回答冻结模型不一致')
                result = {'decision': parse_review(response['text'], package), 'response_key': request['response_key'],
                    'source_id':source['id'],'observed_model':actual_model}
            except (ValueError, TypeError, KeyError) as error:
                result = {'protocol_error': str(error)[:300], 'response_key': request['response_key'],'source_id':source['id']}
            self.owner.plans._write('UPDATE project_evaluation_jobs SET review_result_json=?,review_attempt=MAX(review_attempt,?),status=? WHERE id=?',
                (canonical_json(result).decode(), execution['review_attempt'], 'waiting_review_release', execution['evaluation_job_id']))
            self.owner.plans._write('UPDATE project_task_executions SET result_json=? WHERE id=?',
                (canonical_json(result).decode(),execution['id']))
            self.owner.plans._write('UPDATE project_execution_sources SET evidence_end_json=? WHERE id=?', (canonical_json(boundaries).decode(), source['id']))
            decision = {key: request[key] for key in ('schema', 'plan_id', 'run_id', 'source', 'generation', 'session_id', 'phase_seq', 'step_id', 'response_key')}
            write_document(self.owner.data / safe_relative(source['decision_relative']), {**decision, 'action': 'complete'}, mode=0o640, owner=(0, 1000))
        finally:
            if frozen:
                self.owner.plans.control(execution['run_id'], source['quota_attempt'], 'resume')

    def _settle_review(self, execution: dict, source: dict | None) -> None:
        job = self.owner._one('SELECT * FROM project_evaluation_jobs WHERE id=?', (execution['evaluation_job_id'],))
        stored = self.owner._one('SELECT result_json FROM project_task_executions WHERE id=?',(execution['id'],))
        result = json.loads(stored['result_json']) if stored and stored['result_json'] else None
        if result and result.get('decision'):
            # 先认领真实释放事实，再执行接受事务；旧Run始终保留其原终态。
            self.owner.plans._write('UPDATE project_task_executions SET ended_at=? WHERE id=?', (time.time(), execution['id']))
            self._apply_result(job, result['decision'])
        elif not result and (execution['run_status'] != 'timeout' or not job['review_attempt']):
            if job['infra_recoveries'] >= 2:
                self._block_evaluation(job, '评审基础设施恢复次数已用尽：' + (execution.get('run_error') or '缺少完整输出')[:200])
            else:
                self.owner.plans._write("UPDATE project_evaluation_jobs SET status='review_ready',review_resume=1,infra_recoveries=infra_recoveries+1,error=? WHERE id=?",
                    ('评审执行基础设施中断，继续原私有会话和逻辑尝试', job['id']))
        elif job['review_attempt'] >= 2:
            self._block_evaluation(job, '独立评审执行或格式错误，有限重评已用尽')
        else:
            self.owner.plans._write("UPDATE project_evaluation_jobs SET status='review_ready',review_resume=0,error=? WHERE id=?",
                ((result or {}).get('protocol_error') or '评审执行未形成完整判定', job['id']))

    def _block_evaluation(self, job: dict, message: str) -> None:
        with self.owner.write_lock:
            connection = self.owner.database()
            try:
                with connection:
                    cursor = connection.execute("UPDATE project_evaluation_jobs SET status='uncertain',error=?,ended_at=? WHERE id=? AND status NOT IN ('passed','failed','cancelled','uncertain')",
                        (message, time.time(), job['id']))
                    if cursor.rowcount:
                        blocked = connection.execute("UPDATE project_scenario_tasks SET status='blocked',error=?,updated_at=? WHERE id=? AND status='evaluating' "
                            'AND NOT EXISTS(SELECT 1 FROM project_evaluation_jobs WHERE task_id=? AND id>?) '
                            "AND EXISTS(SELECT 1 FROM project_scenario_instances s JOIN project_instances i ON i.id=s.instance_id "
                            "JOIN project_iteration_batches b ON b.id=i.batch_id WHERE s.id=project_scenario_tasks.scenario_instance_id AND b.generation=? AND b.status IN ('active','pausing'))",
                            (message, time.time(), job['task_id'], job['task_id'], job['id'], job['generation']))
                        if blocked.rowcount:
                            connection.execute("UPDATE project_task_attempts SET ended_at=?,result='blocked' WHERE task_id=? AND ended_at IS NULL",
                                (time.time(),job['task_id']))
                            self._rotate_instance(connection,self.task(job['task_id'])['instance_id'],'评审受阻后轮换')
            finally:
                connection.close()

    def _apply_result(self, job: dict, result: dict) -> None:
        task = self.task(job['task_id'])
        definition = json.loads(task['definition_json'])
        decision = result['decision']
        if decision == 'uncertain':
            self._block_evaluation(job, '同模型独立评审无法可靠判定，保留候选，不自动重抽')
            return
        branch, prompt = None, None
        if decision == 'disclose':
            branch = next((branch for branch in definition.get('branches', []) if branch['id'] == result['branch_id']), None)
            if not branch:
                raise ValueError('评审披露分支不属于冻结任务')
            project = self.owner._release(task['catalog_release_id']).projects[task['project_key']]
            prompt = 'Here is the additional business material you requested. Continue working on the original task:\n' + '\n'.join(
                (project.root / safe_relative(relative)).read_text(encoding='utf-8') for relative in branch['materials'])
        with self.owner.write_lock:
            connection = self.owner.database()
            try:
                with connection:
                    parent = connection.execute('SELECT status,generation FROM project_iteration_batches WHERE id=?', (task['batch_id'],)).fetchone()
                    current = connection.execute('SELECT * FROM project_scenario_tasks WHERE id=?', (task['id'],)).fetchone()
                    stored = connection.execute('SELECT status FROM project_evaluation_jobs WHERE id=?', (job['id'],)).fetchone()
                    if (parent['generation'] != job['generation'] or parent['status'] not in ('active', 'pausing')
                            or current['status'] != 'evaluating' or stored['status'] in ('passed', 'failed', 'cancelled', 'uncertain')):
                        return
                    if connection.execute('SELECT 1 FROM project_evaluation_jobs WHERE task_id=? AND id>?', (task['id'], job['id'])).fetchone():
                        return
                    if connection.execute('SELECT 1 FROM project_task_executions WHERE evaluation_job_id=? AND ended_at IS NULL', (job['id'],)).fetchone():
                        return
                    checkpoint = None
                    error, status, phase = None, 'passed', 'accepted'
                    if decision == 'pass':
                        if json.loads(job['native_result_json'] or '{}').get('status') != 'passed':
                            raise ValueError('独立程序事实未通过，拒绝接受回答或代码')
                        if definition['kind'] == 'modify':
                            checkpoint = job['candidate_digest']
                            connection.execute('UPDATE project_scenario_instances SET checkpoint_digest=? WHERE id=?', (checkpoint, task['scenario_instance_id']))
                        connection.execute('UPDATE project_instances SET visit_completed=visit_completed+1 WHERE id=?',(task['instance_id'],))
                    elif decision == 'disclose':
                        if current['turn_no'] >= definition.get('max_turns', 4):
                            status, phase, error = 'exhausted', 'turn_limit', '正常答复轮次已经用尽'
                        else:
                            phase_key = 'disclosure:' + branch['id']
                            if connection.execute('SELECT id FROM project_task_deliveries WHERE task_id=? AND phase_key=?', (task['id'], phase_key)).fetchone():
                                raise ValueError('同一冻结材料分支不能重复披露')
                            connection.execute('INSERT INTO project_task_deliveries(task_id,phase_key,prompt,input_digest,created_at) VALUES(?,?,?,?,?)',
                                (task['id'], phase_key, prompt, digest_json(prompt), time.time()))
                            for key in branch.get('activate_tasks', []):
                                connection.execute('UPDATE project_scenario_tasks SET selected=1 WHERE scenario_instance_id=? AND task_key=?',
                                    (task['scenario_instance_id'], key))
                            status, phase = 'ready', 'material_ready'
                    elif decision == 'fail':
                        development = self.development.handles(task)
                        if not development and current['attempt_count'] >= 3:
                            status, phase, error = 'failed', 'attempt_limit', '独立验收未通过且修正次数已用尽'
                        elif not development and current['turn_no'] >= definition.get('max_turns', 4):
                            status, phase, error = 'exhausted', 'turn_limit', '正常答复轮次已经用尽'
                        else:
                            status, phase = 'ready', 'correction_ready'
                            prompt = 'Continue the original task and revise the current answer or authorized code according to this independent validation feedback: ' + ', '.join(result.get('feedback_codes', []))
                            if development:
                                prompt = self.development.failure_feedback(job, result)
                                phase = 'repairing'
                    else:
                        raise ValueError('不能接受未支持的评审动作')
                    public_result = {key: result.get(key) for key in ('decision', 'outcome', 'feedback_codes')}
                    connection.execute('UPDATE project_scenario_tasks SET status=?,phase=?,result_json=?,accepted_checkpoint_digest=?,error=?,updated_at=?,'
                        'next_reason=?,next_prompt=COALESCE(?,next_prompt),turn_no=turn_no+? WHERE id=?',
                        (status, phase, canonical_json(public_result).decode(), checkpoint, error, time.time(),
                            'clarification' if decision == 'disclose' else 'correction' if decision == 'fail' else 'continuation',
                            prompt, int(status == 'ready'), task['id']))
                    connection.execute('UPDATE project_evaluation_jobs SET status=?,ended_at=? WHERE id=?',
                        ('passed' if decision in ('pass', 'disclose') else 'failed', time.time(), job['id']))
                    if decision != 'disclose' or status in TASK_TERMINAL:
                        connection.execute('UPDATE project_task_attempts SET ended_at=?,result=? WHERE task_id=? AND ended_at IS NULL',
                            (time.time(),status if status in TASK_TERMINAL else 'correction',task['id']))
                    visit = connection.execute('SELECT visit_completed FROM project_instances WHERE id=?',(task['instance_id'],)).fetchone()[0]
                    if status in ('failed','exhausted') or visit>=json.loads(task['policy_json'])['rotation_steps']:
                        self._rotate_instance(connection,task['instance_id'],'任务收口后轮换' if status!='passed' else '达到通过任务轮换数')
            finally:
                connection.close()

    def budget(self, task_id: int, role: str = 'candidate', *, job_id: int | None = None,
               review_attempt: int | None = None, connection=None) -> dict:
        """汇总已确认工作和未决预留，评审按三层最小剩余量分配。

        :param task_id: 业务任务 ID。
        :param role: candidate 或 review。
        :param job_id: 评审的冻结回答作业。
        :param review_attempt: 当前逻辑评审尝试。
        :param connection: 预留事务可复用同一连接，避免并发超发。
        :return: 确认耗时、未决预留、剩余量与单次可领取秒数。
        """
        if role not in ('candidate', 'review'):
            raise ValueError('工作预算角色不合法')
        owned = connection is None
        connection = self.owner.database() if owned else connection
        try:
            task = connection.execute('SELECT b.policy_json,t.definition_json FROM project_scenario_tasks t '
                'JOIN project_scenario_instances s ON s.id=t.scenario_instance_id JOIN project_instances i ON i.id=s.instance_id '
                'JOIN project_iteration_batches b ON b.id=i.batch_id WHERE t.id=?', (task_id,)).fetchone()
            if task is None:
                raise ValueError('场景任务不存在')
            policy = json.loads(task['policy_json'])
            development = self.development.handles(task)
            all_rows = [dict(row) for row in connection.execute('SELECT w.*,e.evaluation_job_id,e.review_attempt '
                'FROM project_work_segments w JOIN project_execution_sources x ON x.id=w.source_id '
                'JOIN project_task_executions e ON e.id=x.execution_id WHERE e.task_id=?', (task_id,))]
            rows = [row for row in all_rows if row['role'] == role]
            confirmed = sum(row['confirmed_sec'] for row in rows)
            reserved = sum(max(0, row['reserved_sec'] - row['confirmed_sec']) for row in rows if row['status'] != 'settled')
            remaining = max(0, policy['task_budget_sec' if role == 'candidate' else 'review_budget_sec'] - confirmed - reserved)
            external_uncertain = False
            if development:
                external = connection.execute('SELECT COALESCE(SUM(work_sec),0) AS confirmed,COALESCE(SUM(reserved_sec),0) AS reserved,'
                    "COALESCE(MAX(status='uncertain'),0) AS uncertain FROM project_dialogue_jobs WHERE task_id=?", (task_id,)).fetchone()
                total_confirmed = sum(row['confirmed_sec'] for row in all_rows) + external['confirmed']
                total_reserved = sum(max(0,row['reserved_sec']-row['confirmed_sec']) for row in all_rows if row['status'] != 'settled') + external['reserved']
                total_remaining = max(0, policy['task_budget_sec'] - total_confirmed - total_reserved)
                if role == 'candidate':
                    confirmed, reserved, remaining = total_confirmed, total_reserved, total_remaining
                else:
                    remaining = min(remaining, total_remaining)
                external_uncertain = bool(external['uncertain'])
            available = min(remaining, policy['timeout_sec' if role == 'candidate' else 'review_timeout_sec'])
            if role == 'review' and job_id is not None:
                job = connection.execute('SELECT response_budget_sec FROM project_evaluation_jobs WHERE id=? AND task_id=?',
                    (job_id, task_id)).fetchone()
                if job is None or type(review_attempt) is not int or review_attempt not in (1, 2):
                    raise ValueError('评审预算必须绑定冻结回答及逻辑尝试')
                response_rows = [row for row in rows if row['evaluation_job_id'] == job_id]
                attempt_rows = [row for row in response_rows if row['review_attempt'] == review_attempt]

                def charged(items: list[dict]) -> float:
                    return sum(row['confirmed_sec'] if row['status'] == 'settled'
                        else max(row['confirmed_sec'],row['reserved_sec']) for row in items)

                available = max(0, min(available, job['response_budget_sec'] - charged(response_rows),
                    policy['review_timeout_sec'] - charged(attempt_rows)))
            return {'confirmed_sec': confirmed, 'reserved_sec': reserved, 'remaining_sec': remaining,
                'slice_sec': None if role == 'review' and job_id is None else available,
                'uncertain': external_uncertain or any(row['status'] == 'uncertain' for row in (all_rows if development else rows))}
        finally:
            if owned:
                connection.close()

    def reserve_segment(self, source_id: int, segment_seq: int, boot_id: str, start_mono: float) -> dict:
        """启动前原子预留工作时间，重启与重复请求不重新发放。

        :param source_id: 精确 Run、quota 代次及 source 的记录。
        :param segment_seq: 该来源递增片段序号。
        :param boot_id: 计时主机启动身份。
        :param start_mono: 该主机单调时钟起点。
        :return: 持久片段及其真实剩余预算。
        """
        if type(segment_seq) is not int or segment_seq < 1 or not isinstance(boot_id, str) or not boot_id:
            raise ValueError('工作片段身份不合法')
        with self.owner.write_lock:
            connection = self.owner.database()
            try:
                with connection:
                    existing = connection.execute('SELECT * FROM project_work_segments WHERE source_id=? AND segment_seq=?',
                        (source_id, segment_seq)).fetchone()
                    if existing:
                        if existing['boot_id'] != boot_id or existing['start_mono'] != start_mono:
                            raise ValueError('同一工作片段身份冲突')
                        return dict(existing)
                    execution = connection.execute('SELECT e.*,x.released_at,x.execution_error FROM project_execution_sources x '
                        'JOIN project_task_executions e ON e.id=x.execution_id WHERE x.id=?', (source_id,)).fetchone()
                    if not execution or execution['ended_at'] is not None or execution['released_at'] or execution['execution_error']:
                        raise ValueError('已收口或缺失执行不能领取预算')
                    task = self.task(execution['task_id'])
                    if execution['generation'] != task['generation'] or task['batch_status'] != 'active':
                        raise ValueError('父任务已停止或代次发生变化')
                    if connection.execute('SELECT 1 FROM project_work_segments WHERE source_id=? AND status!=?',
                            (source_id, 'settled')).fetchone():
                        raise ValueError('前一工作片段未结算，不能重复领取')
                    budget = self.budget(execution['task_id'], execution['role'], job_id=execution['evaluation_job_id'],
                        review_attempt=execution['review_attempt'], connection=connection)
                    if budget['uncertain'] or budget['slice_sec'] <= 0:
                        raise ValueError('累计工作预算耗尽或尾段预留尚未核实')
                    cursor = connection.execute('INSERT INTO project_work_segments(source_id,segment_seq,role,boot_id,start_mono,'
                        'reserved_sec,created_at) VALUES(?,?,?,?,?,?,?)',
                        (source_id, segment_seq, execution['role'], boot_id, start_mono, budget['slice_sec'], time.time()))
                    return dict(connection.execute('SELECT * FROM project_work_segments WHERE id=?', (cursor.lastrowid,)).fetchone())
            finally:
                connection.close()

    def update_segment(self, segment_id: int, boot_id: str, elapsed_sec: float, *, settled: bool = False,
                       uncertain: bool = False, usage: dict | None = None) -> dict:
        """按单调高水位幂等结算，未知尾段保留预留而不伪造耗时。

        :param segment_id: 已预留片段。
        :param boot_id: 原计时主机启动身份。
        :param elapsed_sec: 已证明的有效工作秒数。
        :param settled: 是否已有准确退出或暂停边界。
        :param uncertain: 是否丢失末尾边界。
        :param usage: 逐原生边界统计，可缺失，不能补零。
        :return: 更新后的持久片段。
        """
        if type(elapsed_sec) not in (int, float) or not 0 <= elapsed_sec < float('inf') or settled and uncertain:
            raise ValueError('工作片段耗时或结算状态不合法')
        with self.owner.write_lock:
            connection = self.owner.database()
            try:
                with connection:
                    row = connection.execute('SELECT * FROM project_work_segments WHERE id=?', (segment_id,)).fetchone()
                    if row is None or row['boot_id'] != boot_id or elapsed_sec > row['reserved_sec'] + 3:
                        raise ValueError('工作片段启动身份或预算边界不符')
                    if row['status'] == 'settled':
                        if abs(row['confirmed_sec'] - elapsed_sec) > 0.001 or not settled:
                            raise ValueError('已结算工作片段不能改写')
                        return dict(row)
                    if elapsed_sec < row['confirmed_sec']:
                        return dict(row)
                    status = 'settled' if settled else 'uncertain' if uncertain else 'active'
                    connection.execute('UPDATE project_work_segments SET confirmed_sec=?,status=?,usage_json=COALESCE(?,usage_json),'
                        'settled_at=? WHERE id=?', (elapsed_sec, status, canonical_json(usage).decode() if usage is not None else None,
                            time.time() if settled else None, segment_id))
                    return dict(connection.execute('SELECT * FROM project_work_segments WHERE id=?', (segment_id,)).fetchone())
            finally:
                connection.close()
