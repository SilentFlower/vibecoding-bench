"""持久项目实例、阶段轮换与独立业务验收的自动推进器。"""
from __future__ import annotations

import hashlib
import json
import os
import random
import shutil
import threading
import time
import uuid
from pathlib import Path
from typing import Callable

from project_library import (ProjectLibrary, canonical_json, digest_json, materialize_snapshot,
    read_document, safe_relative, snapshot_tree, write_document)
from project_plans import PLAN_DEFAULTS, ProjectPlans, initialize_plan_schema, normalized_policy
from project_scenarios import ProjectScenarios, SCENARIO_DEFAULTS, normalized_scenario_policy


PROJECT_RUN_KIND = 'project_iteration'
PROJECT_REVIEW_KIND = 'project_review'
PROJECT_RUN_KINDS = frozenset({PROJECT_RUN_KIND, PROJECT_REVIEW_KIND})
PROJECT_SCHEMA = '''
CREATE TABLE IF NOT EXISTS project_catalog_releases (
  id INTEGER PRIMARY KEY AUTOINCREMENT, version TEXT NOT NULL, digest TEXT NOT NULL UNIQUE,
  relative_path TEXT NOT NULL, created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS project_iteration_batches (
  id INTEGER PRIMARY KEY AUTOINCREMENT, account_id INTEGER NOT NULL, account_identity TEXT NOT NULL,
  name TEXT NOT NULL, catalog_release_id INTEGER NOT NULL, status TEXT NOT NULL DEFAULT 'paused',
  policy_json TEXT NOT NULL, active_instance_id INTEGER, generation INTEGER NOT NULL DEFAULT 1,
  stop_requested_at REAL, next_launch_at REAL, error TEXT, created_at REAL NOT NULL, updated_at REAL NOT NULL,
  FOREIGN KEY(account_id) REFERENCES accounts(id),
  FOREIGN KEY(catalog_release_id) REFERENCES project_catalog_releases(id)
);
CREATE TABLE IF NOT EXISTS project_instances (
  id INTEGER PRIMARY KEY AUTOINCREMENT, batch_id INTEGER NOT NULL, project_key TEXT NOT NULL,
  manifest_json TEXT NOT NULL, seed_digest TEXT NOT NULL, roadmap_digest TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'not_started', next_step_index INTEGER NOT NULL DEFAULT 0,
  workspace_relative TEXT, started_at REAL, checkpoint_digest TEXT NOT NULL,
  visit_order INTEGER NOT NULL DEFAULT 0, switch_reason TEXT, error TEXT,
  created_at REAL NOT NULL, updated_at REAL NOT NULL, UNIQUE(batch_id,project_key),
  FOREIGN KEY(batch_id) REFERENCES project_iteration_batches(id)
);
CREATE TABLE IF NOT EXISTS project_step_attempts (
  id INTEGER PRIMARY KEY AUTOINCREMENT, instance_id INTEGER NOT NULL, step_id TEXT NOT NULL,
  attempt_no INTEGER NOT NULL, generation INTEGER NOT NULL, run_id TEXT NOT NULL UNIQUE,
  expected_checkpoint_digest TEXT NOT NULL, execution_released_at REAL, released_quota_attempt INTEGER,
  execution_error TEXT, validation_status TEXT NOT NULL DEFAULT 'pending', verification_errors INTEGER NOT NULL DEFAULT 0,
  result_digest TEXT, report_relative TEXT, candidate_digest TEXT, accepted_checkpoint_digest TEXT,
  created_at REAL NOT NULL, ended_at REAL, UNIQUE(instance_id,step_id,attempt_no),
  FOREIGN KEY(instance_id) REFERENCES project_instances(id), FOREIGN KEY(run_id) REFERENCES runs(id)
);
CREATE INDEX IF NOT EXISTS idx_project_batches_account ON project_iteration_batches(account_id,status);
CREATE INDEX IF NOT EXISTS idx_project_instances_batch ON project_instances(batch_id,status);
CREATE INDEX IF NOT EXISTS idx_project_attempts_instance ON project_step_attempts(instance_id,ended_at);
CREATE UNIQUE INDEX IF NOT EXISTS idx_project_step_accepted ON project_step_attempts(instance_id,step_id)
  WHERE validation_status='passed';
'''
DEFAULT_POLICY = {'active_projects': 3, 'repair_limit': 2, 'timeout_sec': 1800}
TERMINAL_RUNS = {'success', 'failed', 'timeout', 'stopped', 'auth_failed'}


class ProjectIterationManager:
    """管理账号批次中的持久工作副本与业务步骤。

    :param data: 调度器数据根。
    :param library: 已校验的预置内容。
    :param database: 返回 SQLite 连接的函数。
    :param write_lock: 与原调度器共用的写锁。
    :param submit: 既有 Scheduler.submit。
    :param settings: 获取本次执行设置快照的函数。
    :param identity: 既有账号身份函数。
    :param stop_run: 既有停止运行入口。
    :param verifier: 独立容器业务验证器。
    :param is_executing: 检查原调度器是否仍持有执行资源。
    :param admission: 环境准备后重新检查公共门禁的可选函数。
    :param execution_control: 按运行代次控制独立进程树的回调。
    :param schedule_admission: 创建新计划前的只读账号门禁。
    :param concurrency_limit: 实际账号 CLI 容量。
    """

    def __init__(self, data: Path, library: ProjectLibrary | None, database: Callable, write_lock,
                 submit: Callable, settings: Callable, identity: Callable, stop_run: Callable,
                 verifier, is_executing: Callable, admission: Callable | None = None,
                 execution_control: Callable | None = None, schedule_admission: Callable | None = None,
                 concurrency_limit: int = 2) -> None:
        """注册内容版本并初始化推进依赖；参数契约见类说明。@return None。"""
        self.data, self.database, self.write_lock = data, database, write_lock
        self.submit, self.settings, self.identity, self.stop_run = submit, settings, identity, stop_run
        self.verifier, self.is_executing = verifier, is_executing
        self.admission = admission
        self.review_admission = None
        self.review_refresh = None
        self.library = library.install(data) if library is not None else None
        self.objects = data/'project-artifacts/objects'
        self.manifests = data/'project-artifacts/manifests'
        self._stop = threading.Event()
        self._tick_lock = threading.Lock()
        self._thread = None
        self._libraries = {}
        now = time.time()
        self.release_id = None
        with self.write_lock:
            connection = self.database()
            try:
                with connection:
                    if self.library is not None:
                        connection.execute('INSERT OR IGNORE INTO project_catalog_releases(version,digest,relative_path,created_at) VALUES(?,?,?,?)',
                            (self.library.version,self.library.digest,str(self.library.root.relative_to(data)),now))
                        self.release_id = connection.execute('SELECT id FROM project_catalog_releases WHERE digest=?',
                            (self.library.digest,)).fetchone()['id']
            finally:
                connection.close()
        if self.library is not None:
            self._libraries[self.release_id] = self.library
        self.plans = ProjectPlans(self,execution_control,schedule_admission,concurrency_limit)
        self.scenarios = ProjectScenarios(self)

    def _rows(self, sql: str, parameters=()) -> list[dict]:
        connection = self.database()
        try:
            return [dict(row) for row in connection.execute(sql,parameters)]
        finally:
            connection.close()

    def _one(self, sql: str, parameters=()) -> dict | None:
        rows = self._rows(sql,parameters)
        return rows[0] if rows else None

    def catalog(self) -> dict:
        """返回项目库公开摘要。

        :return: 固定内容版本和项目列表，不包含私有参考实现。
        """
        if self.library is None:
            raise ValueError('当前项目内容库不可用，历史批次仍可读取')
        defaults = SCENARIO_DEFAULTS if self.library.schema == 2 else PLAN_DEFAULTS
        return {'content_schema':self.library.schema,'version':self.library.version,'digest':self.library.digest,
            'scheduling_defaults':{**defaults,'concurrency':self.plans.limit},
            'projects':[project.summary() for project in self.library.projects.values()]}

    def create_batch(self, account_id: int, name: str, project_keys: list[str] | None = None,
                     policy: dict | None = None, scenario_entries: dict[str,dict[str,str]] | None = None) -> dict:
        """建立暂停批次；这里只写记录，不创建项目工作目录。

        :param account_id: 可用账号 ID。
        :param name: 用户可见的批次名称。
        :param project_keys: 选中项目；None 表示完整项目库。
        :param policy: 新调度策略；内部历史调用省略时保留旧单步语义。
        :param scenario_entries: 新内容的显式场景入口选择，省略使用各自默认值。
        :return: 新批次详情。
        """
        if self.library is None:
            raise ValueError('当前项目内容库不可用，不能新建批次')
        keys = list(self.library.projects) if project_keys is None else list(project_keys)
        if (not keys or len(keys)>100 or len(set(keys))!=len(keys)
                or any(key not in self.library.projects for key in keys)):
            raise ValueError('项目选择为空、重复或不属于当前内容版本')
        if not isinstance(name,str) or not 1 <= len(name.strip()) <= 120:
            raise ValueError('项目批次名称须为 1～120 个字符')
        if scenario_entries:
            if self.library.schema != 2 or any(key not in keys for key in scenario_entries):
                raise ValueError('场景入口只能引用本次选中的新内容项目')
            for key,selections in scenario_entries.items():
                scenarios = {item['id']:item for item in self.library.projects[key].manifest['scenarios']}
                if not isinstance(selections,dict) or any(scene not in scenarios for scene in selections):
                    raise ValueError('场景入口所属场景不存在')
                for scene,entry in selections.items():
                    if entry not in {item['id'] for item in scenarios[scene]['entries']}:
                        raise ValueError('所选场景入口不存在')
        account = self._one('SELECT * FROM accounts WHERE id=? AND enabled=1 AND deleted_at IS NULL',(account_id,))
        if account is None:
            raise ValueError('账号不存在或已停用')
        selected_policy = DEFAULT_POLICY
        if self.library.schema == 2:
            selected_policy = normalized_scenario_policy(policy or {}, len(keys), self.plans.limit)
            random.shuffle(keys)
        elif policy is not None:
            maximum = max(len(self.library.projects[key].manifest['steps']) for key in keys)
            selected_policy = normalized_policy(policy,len(keys),maximum,self.plans.limit)
            random.shuffle(keys)
        identity, now = self.identity(account), time.time()
        with self.write_lock:
            connection = self.database()
            try:
                with connection:
                    if not connection.execute('SELECT id FROM accounts WHERE id=? AND enabled=1 AND deleted_at IS NULL',(account_id,)).fetchone():
                        raise ValueError('账号不存在或已停用')
                    cursor = connection.execute('INSERT INTO project_iteration_batches(account_id,account_identity,name,catalog_release_id,policy_json,created_at,updated_at) VALUES(?,?,?,?,?,?,?)',
                        (account_id,identity,name.strip(),self.release_id,canonical_json(selected_policy).decode(),now,now))
                    batch_id = cursor.lastrowid
                    for order,key in enumerate(keys):
                        manifest = self.library.projects[key].manifest
                        cursor = connection.execute('INSERT INTO project_instances(batch_id,project_key,manifest_json,seed_digest,roadmap_digest,checkpoint_digest,visit_order,initial_order,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?)',
                            (batch_id,key,canonical_json(manifest).decode(),manifest['seed_digest'],digest_json(manifest.get('steps',manifest.get('scenarios'))),
                            manifest['seed_digest'],order,order,now,now))
                        if self.library.schema == 2:
                            self.scenarios.create_tasks(connection,cursor.lastrowid,manifest,now,(scenario_entries or {}).get(key))
            finally:
                connection.close()
        return self.batch(batch_id)

    def batches(self) -> list[dict]:
        """返回不含内部账号身份的批次摘要。

        :return: 批次列表及项目状态计数。
        """
        result = self._rows('SELECT * FROM project_iteration_batches ORDER BY id DESC')
        for item in result:
            item.pop('account_identity',None)
            item['policy'] = json.loads(item.pop('policy_json'))
            item['counts'] = {row['status']:row['count'] for row in self._rows(
                'SELECT status,COUNT(*) AS count FROM project_instances WHERE batch_id=? GROUP BY status',(item['id'],))}
            if item['policy'].get('schema')==2:
                item['scheduling'] = self.plans.batch_summary(item)
            elif item['policy'].get('schema')==3:
                item['scheduling'] = self.scenarios.batch_summary(item)
        return result

    def batch(self, batch_id: int) -> dict:
        """读取一个批次的实例列表。

        :param batch_id: 项目批次 ID。
        :return: 批次和轻量实例摘要。
        """
        result = next((item for item in self.batches() if item['id']==batch_id),None)
        if result is None:
            raise ValueError('项目批次不存在')
        result['instances'] = [self._public_instance(item,False) for item in self._rows(
            'SELECT * FROM project_instances WHERE batch_id=? ORDER BY id',(batch_id,))]
        return result

    def instance(self, instance_id: int) -> dict:
        """返回项目路线和逐次执行记录。

        :param instance_id: 实例 ID。
        :return: 公开实例详情。
        """
        item = self._one('SELECT * FROM project_instances WHERE id=?',(instance_id,))
        if item is None:
            raise ValueError('项目实例不存在')
        result = self._public_instance(item,True)
        if json.loads(item['manifest_json'])['schema'] == 2:
            return self.scenarios.instance_detail(item,result)
        result['attempts'] = self._rows('SELECT a.id,a.step_id,a.attempt_no,a.run_id,a.plan_id,a.validation_status,a.execution_released_at,'
            'a.candidate_digest,a.accepted_checkpoint_digest,a.created_at,a.ended_at,r.status AS execution_status,'
            'r.error AS execution_error,r.window_wait_until FROM project_step_attempts a LEFT JOIN runs r ON r.id=a.run_id '
            'WHERE a.instance_id=? ORDER BY a.id',(instance_id,))
        result['plans'] = self.plans.summaries(instance_id)
        return result

    def _public_instance(self, item: dict, include_steps: bool) -> dict:
        manifest = json.loads(item['manifest_json'])
        result = {key:value for key,value in item.items() if key not in ('manifest_json','workspace_relative')}
        if manifest['schema'] == 2:
            counts = {row['status']:row['count'] for row in self._rows('SELECT t.status,COUNT(*) AS count FROM project_scenario_tasks t '
                'JOIN project_scenario_instances s ON s.id=t.scenario_instance_id WHERE s.instance_id=? AND t.selected=1 GROUP BY t.status',(item['id'],))}
            result.update(content_schema=2,title=manifest['title'],scenario_count=len(manifest['scenarios']),
                task_count=sum(len(scenario['tasks']) for scenario in manifest['scenarios']),workspace_path=None,
                task_counts=counts,selected_task_count=sum(counts.values()))
            return result
        result['content_schema'] = 1
        result['title'],result['step_count'] = manifest['title'],len(manifest['steps'])
        result['workspace_path'] = '/home/node/projects/'+Path(item['workspace_relative']).name if item['workspace_relative'] else None
        if include_steps:
            result['steps'] = [{key:step[key] for key in ('id','goal','milestone','requires')} for step in manifest['steps']]
            result['milestones'] = manifest['milestones']
        return result

    def transition(self, batch_id: int, action: str) -> dict:
        """启动、暂停或停止项目批次，停止意图先于外部清理落盘。

        :param batch_id: 目标批次。
        :param action: start、pause 或 stop。
        :return: 更新后的批次详情。
        """
        batch = self._one('SELECT * FROM project_iteration_batches WHERE id=?',(batch_id,))
        if batch is None:
            raise ValueError('项目批次不存在')
        if action not in ('start','pause','stop'):
            raise ValueError('项目批次动作不合法')
        account = self._one('SELECT * FROM accounts WHERE id=? AND enabled=1 AND deleted_at IS NULL',(batch['account_id'],))
        if action=='start' and (account is None or self.identity(account)!=batch['account_identity']):
            raise ValueError('账号不可用或身份已变化，不能恢复原项目批次')
        if action=='start' and batch['status'] not in ('paused','pausing','active'):
            raise ValueError('已停止、阻塞或完成的批次不能自动重新开始，请建立新批次')
        now = time.time()
        with self.write_lock:
            connection = self.database()
            try:
                with connection:
                    if action=='start':
                        connection.execute("UPDATE project_iteration_batches SET status='active',error=NULL,updated_at=? WHERE id=? AND generation=? AND status IN ('paused','pausing','active') AND stop_requested_at IS NULL",
                            (now,batch_id,batch['generation']))
                    elif action=='pause':
                        connection.execute("UPDATE project_iteration_batches SET status='pausing',updated_at=? WHERE id=? AND status='active'",(now,batch_id))
                    else:
                        connection.execute("UPDATE project_iteration_batches SET status='stopping',generation=generation+1,stop_requested_at=?,updated_at=? WHERE id=? AND status NOT IN ('completed','stopped','stopping')",(now,now,batch_id))
            finally:
                connection.close()
        if action=='stop':
            for run in self._rows("SELECT DISTINCT r.id FROM runs r JOIN project_step_attempts a ON a.run_id=r.id JOIN project_instances i ON i.id=a.instance_id WHERE i.batch_id=? AND r.status IN ('queued','running','stopping','quota_wait')",(batch_id,)):
                self.stop_run(run['id'])
            for run in self.scenarios._open_executions(batch_id):
                self.stop_run(run['run_id'])
        return self.batch(batch_id)

    def run_context(self, run_id: str) -> dict | None:
        """查询 run 的固定项目归属，供运行器和恢复门禁共用。

        :param run_id: 原运行 ID。
        :return: 尝试、实例和批次的内部联合视图，普通运行返回 None。
        """
        scenario = self.scenarios.context(run_id)
        if scenario is not None:
            return scenario
        planned = self.plans.context(run_id)
        if planned is not None:
            return planned
        return self._one('SELECT a.id AS attempt_id,a.generation AS attempt_generation,a.step_id,a.attempt_no,'
            'i.*,b.account_id,b.account_identity,b.catalog_release_id,b.status AS batch_status,b.generation AS batch_generation '
            'FROM project_step_attempts a JOIN project_instances i ON i.id=a.instance_id '
            'JOIN project_iteration_batches b ON b.id=i.batch_id WHERE a.run_id=?',(run_id,))

    def execution_allowed(self, run_id: str, *, started: bool = False) -> bool:
        """重读父状态和代次，避免暂停或停止后继续投放。

        :param run_id: 项目运行 ID。
        :param started: 是否仅允许已有在途执行收尾。
        :return: 本代是否仍有执行权限。
        """
        context = self.run_context(run_id)
        if context and context.get('scenario_execution'):
            execution = context['scenario_execution']
            return bool(execution['ended_at'] is None and execution['generation'] == context['batch_generation']
                and (context['batch_status'] == 'active' or started and context['batch_status'] == 'pausing'))
        if context and context.get('plan_id') and (context['not_before']>time.time()
                or context['plan_status'] not in ('running','quota_wait')):
            return False
        return bool(context and context['attempt_generation']==context['batch_generation']
            and (context['batch_status']=='active' or started and context['batch_status']=='pausing'))

    def prepare_workspace(self, row: dict, run_id: str, environment_root: Path) -> tuple[str,Path] | None:
        """在实际启动门禁内首次发布实例工作目录。

        :param row: 当前固定账号环境行。
        :param run_id: 当前运行。
        :param environment_root: 当前环境的宿主数据根。
        :return: 稳定别名和物理目录；普通运行返回 None。
        """
        context = self.run_context(run_id)
        if context is None:
            return None
        if context.get('scenario_execution'):
            return self.scenarios.prepare_workspace(row,run_id,environment_root)
        if row.get('account_id')!=context['account_id'] or not self.can_start(run_id):
            raise ValueError('项目实例账号、代次或启动状态不符')
        alias = 'project-'+hashlib.sha256(f"{row['environment_id']}:instance:{context['id']}".encode()).hexdigest()[:12]
        target = environment_root/'projects'/alias
        relative = str(target.relative_to(self.data))
        marker = self.data/'project-artifacts/instances'/str(context['id'])/'materialized.json'
        if context['workspace_relative']:
            if context['workspace_relative']!=relative or not target.is_dir() or target.is_symlink():
                raise ValueError('已开始项目的工作目录缺失或被替换')
            return alias,target
        if marker.exists():
            previous = read_document(marker)
            if previous!={'instance_id':context['id'],'seed_digest':context['seed_digest'],'workspace_relative':relative}:
                raise ValueError('项目发布标记不一致')
            if not target.is_dir() or target.is_symlink():
                raise ValueError('项目发布后目录缺失')
        elif target.exists() or target.is_symlink():
            raise ValueError('项目目录已存在但没有可核对的发布标记')
        else:
            library = self._release(context['catalog_release_id'])
            project = library.projects[context['project_key']]
            baseline = snapshot_tree(project.root/'seed',self.objects)
            write_document(self.manifests/(baseline['digest']+'.json'),baseline)
            staging = self.data/'project-staging'/uuid.uuid4().hex
            materialize_snapshot(baseline,self.objects,staging)
            try:
                for path in [staging,*staging.rglob('*')]:
                    os.chown(path,1000,1000,follow_symlinks=False)
                    path.chmod(0o755 if path.is_dir() else 0o644)
                target.parent.mkdir(parents=True,exist_ok=True)
                os.chown(target.parent,1000,1000,follow_symlinks=False)
                # 先持久化归属，发布中断时恢复也不能凭未知目录覆盖数据。
                write_document(marker,{'instance_id':context['id'],'seed_digest':context['seed_digest'],'workspace_relative':relative})
                if not self.can_start(run_id):
                    marker.unlink(missing_ok=True)
                    raise ValueError('项目发布前批次已暂停或停止')
                os.rename(staging,target)
            finally:
                if staging.exists():
                    shutil.rmtree(staging)
        now = time.time()
        with self.write_lock:
            connection = self.database()
            try:
                with connection:
                    connection.execute('UPDATE project_instances SET workspace_relative=?,started_at=COALESCE(started_at,?),updated_at=? WHERE id=? AND workspace_relative IS NULL',
                        (relative,now,now,context['id']))
            finally:
                connection.close()
        return alias,target

    def can_start(self, run_id: str) -> bool:
        """在耗时环境准备后复核账号、父状态和共同门禁。

        :param run_id: 当前运行。
        :return: 是否仍允许开始本次执行。
        """
        context = self.run_context(run_id)
        if context is None or not self.execution_allowed(run_id):
            return False
        account = self._one('SELECT * FROM accounts WHERE id=? AND enabled=1 AND deleted_at IS NULL',(context['account_id'],))
        return bool(account and self.identity(account)==context['account_identity']
            and (self.admission is None or self.admission(account,run_id)))

    def workspace_alias(self, row: dict, run_id: str) -> str | None:
        """只读解析已开始实例的别名，不隐式初始化目录。

        :param row: 固定账号环境。
        :param run_id: 原运行。
        :return: 已发布项目别名或 None。
        """
        context = self.run_context(run_id)
        if context is None:
            return None
        if row.get('account_id')!=context['account_id'] or not context['workspace_relative']:
            raise ValueError('项目实例尚未开始或不属于当前账号')
        return Path(context['workspace_relative']).name

    def _release(self, release_id: int) -> ProjectLibrary:
        if release_id not in self._libraries:
            row = self._one('SELECT * FROM project_catalog_releases WHERE id=?',(release_id,))
            if row is None:
                raise ValueError('原项目内容版本缺失')
            library = ProjectLibrary(self.data/safe_relative(row['relative_path']))
            if library.digest!=row['digest']:
                raise ValueError('原项目内容版本已损坏')
            self._libraries[release_id] = library
        return self._libraries[release_id]

    def execution_released(self, run_id: str, quota_attempt: int, error: str | None = None) -> None:
        """在原执行严格收口后保存证据，旧额度代次不能覆盖新执行。

        :param run_id: 运行 ID。
        :param quota_attempt: 已清理的执行代次。
        :param error: 严格清理失败原因。
        :return: None。
        """
        if self.scenarios.context(run_id):
            self.scenarios.execution_released(run_id,quota_attempt,error)
            return
        if self.plans.context(run_id):
            self.plans.execution_released(run_id,quota_attempt,error)
            return
        with self.write_lock:
            connection = self.database()
            try:
                with connection:
                    connection.execute('UPDATE project_step_attempts SET execution_released_at=?,released_quota_attempt=?,execution_error=? '
                        'WHERE run_id=? AND ended_at IS NULL AND EXISTS(SELECT 1 FROM runs WHERE id=? AND quota_attempt=?)',
                        (None if error else time.time(),quota_attempt,error,run_id,run_id,quota_attempt))
            finally:
                connection.close()

    def record_native_start(self, run_id: str, directory: Path) -> None:
        """冻结本轮主会话字节起点，额度恢复不能覆盖首次起点。

        :param run_id: 当前运行。
        :param directory: 该项目的原生主会话目录。
        :return: None。
        """
        path = self.data/'project-artifacts/runs'/run_id/'native-start.json'
        if not path.exists():
            write_document(path,{p.name:p.stat().st_size for p in directory.glob('*.jsonl') if p.is_file() and not p.is_symlink()})

    def record_native_end(self, run_id: str, directory: Path) -> None:
        """在执行释放后封存字节终点，避免未来步骤污染历史用量。

        :param run_id: 已收口运行。
        :param directory: 原生主会话目录。
        :return: None。
        """
        write_document(self.data/'project-artifacts/runs'/run_id/'native-end.json',
            {p.name:p.stat().st_size for p in directory.glob('*.jsonl') if p.is_file() and not p.is_symlink()})

    def latest_native_session(self, run_id: str, directory: Path) -> str | None:
        """从本轮新增主日志定位恢复会话，缺起点时不猜上一轮。

        :param run_id: 原运行。
        :param directory: 原生主会话目录。
        :return: 本轮会话 ID 或 None。
        """
        context = self.plans.context(run_id)
        if context:
            path = directory/(context['session_id']+'.jsonl')
            return context['session_id'] if path.is_file() and not path.is_symlink() else None
        try:
            start = read_document(self.data/'project-artifacts/runs'/run_id/'native-start.json')
            files = [path for path in directory.glob('*.jsonl') if path.is_file() and not path.is_symlink()
                and path.stat().st_size>int(start.get(path.name,0))]
            return max(files,key=lambda path:path.stat().st_mtime).stem if files else None
        except (OSError,ValueError,TypeError,AttributeError):
            return None

    def native_usage(self, run_id: str, directory: Path, input_counter: Callable, *, boundaries: tuple | None = None) -> dict:
        """仅统计本轮字节区间中的去重主响应。

        :param run_id: 项目运行。
        :param directory: 稳定项目会话目录。
        :param input_counter: 既有输入及缓存用量归一函数。
        :param boundaries: 单步骤自己的字节起止；省略时统计整个 Run。
        :return: 用量与可用性；证据缺失时不会回退为整个项目的历史。
        """
        if boundaries is None and self.scenarios.context(run_id):
            usage = self.scenarios.run_usage(run_id)
            known = [usage[key] for key in ('input_tokens','cache_read_input_tokens','cache_creation_input_tokens') if usage[key] is not None]
            return {**usage,'tokens_in':sum(known) if known else 0,'tokens_out':usage['output_tokens'] or 0,
                'requests':usage['requests'] or 0,'usage_available':bool(known or usage['output_tokens'] is not None)}
        empty = {'tokens_in':0,'tokens_out':0,'requests':0,'usage_available':False}
        root = self.data/'project-artifacts/runs'/run_id
        try:
            start = boundaries[0] if boundaries else read_document(root/'native-start.json')
            run = self._one('SELECT status FROM runs WHERE id=?',(run_id,))
            if boundaries and boundaries[1] is not None:
                end = boundaries[1]
            elif (root/'native-end.json').exists() and run and run['status'] in TERMINAL_RUNS | {'quota_wait'}:
                end = read_document(root/'native-end.json')
            else:
                end = {p.name:p.stat().st_size for p in directory.glob('*.jsonl') if p.is_file() and not p.is_symlink()}
            responses = {}
            scanned = 0
            for name,limit in end.items():
                if Path(name).name!=name or not name.endswith('.jsonl') or type(limit) is not int:
                    return empty
                offset = start.get(name,0)
                path = directory/name
                if type(offset) is not int or offset<0 or limit<offset or path.is_symlink() or path.stat().st_size<limit:
                    return empty
                if limit==offset:
                    continue
                with path.open('rb') as stream:
                    stream.seek(offset)
                    while stream.tell()<limit:
                        position = stream.tell()
                        line = stream.readline(min(8*1024*1024,limit-position)+1)
                        scanned += len(line)
                        if scanned>64*1024*1024 or stream.tell()>limit or not line.endswith(b'\n'):
                            return empty
                        try:
                            record = json.loads(line)
                        except ValueError:
                            continue
                        message = record.get('message')
                        if (record.get('isSidechain') or record.get('isMeta') or record.get('type')!='assistant'
                                or not isinstance(message,dict) or message.get('role')!='assistant'
                                or not isinstance(message.get('usage'),dict)):
                            continue
                        usage = message['usage']
                        key = message.get('id') or record.get('requestId') or f'{name}:{position}'
                        if key not in responses or int(usage.get('output_tokens') or 0)>=int(responses[key].get('output_tokens') or 0):
                            responses[key] = usage
            return {'tokens_in':sum(input_counter(value) for value in responses.values()),
                'tokens_out':sum(int(value.get('output_tokens') or 0) for value in responses.values()),
                'requests':len(responses),'usage_available':bool(responses)}
        except (OSError,ValueError,TypeError,KeyError,AttributeError):
            return empty

    def step_usage(self, attempt_id: int, input_counter: Callable) -> dict:
        """按步骤的独立字节边界汇总用量，不复制共享 Run 的总数。

        :param attempt_id: 尝试 ID。
        :param input_counter: 原输入统计函数。
        :return: 该尝试的用量；缺少证据返回未知。
        """
        empty = {'usage_available':False}
        attempt = self._one('SELECT * FROM project_step_attempts WHERE id=?',(attempt_id,))
        if not attempt or not attempt['plan_id'] or not attempt['native_start_json']:
            return empty
        execution = self._one('SELECT native_relative FROM project_plan_executions WHERE run_id=?',(attempt['run_id'],))
        if not execution or not execution['native_relative'] or attempt['ended_at'] is not None and not attempt['native_end_json']:
            return empty
        return self.native_usage(attempt['run_id'],self.data/safe_relative(execution['native_relative']),input_counter,
            boundaries=(json.loads(attempt['native_start_json']),json.loads(attempt['native_end_json']) if attempt['native_end_json'] else None))

    def start(self) -> None:
        """启动自动推进线程。

        :return: None。
        """
        self._thread = threading.Thread(target=self._loop,name='project-iterations',daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """停止新投放，保留所有项目及持久进度。

        :return: None。
        """
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=5)

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                self.tick()
            except Exception:
                # 单个轮询故障不重置工作区；对应尝试与错误仍由下一轮对账。
                pass
            self._stop.wait(2)

    def recover(self, cleanup: Callable) -> None:
        """重启时严格收口旧执行，不把未验收终态当作业务通过。

        :param cleanup: Runner.cleanup_quota_run。
        :return: None。
        """
        self.plans.recover(cleanup)
        self.scenarios.recover(cleanup)
        attempts = self._rows('SELECT a.run_id,r.status,r.started_at,r.worker_container,r.quota_attempt '
            'FROM project_step_attempts a JOIN runs r ON r.id=a.run_id WHERE a.ended_at IS NULL AND a.plan_id IS NULL')
        for item in attempts:
            if item['status']=='quota_wait' or item['status']=='queued' and not item['started_at'] and not item['worker_container']:
                continue
            try:
                cleanup(item['run_id'])
                self.execution_released(item['run_id'],int(item['quota_attempt']))
                if item['status'] not in TERMINAL_RUNS:
                    with self.write_lock:
                        connection = self.database()
                        try:
                            with connection:
                                connection.execute("UPDATE runs SET status='failed',error='服务重启中断，保留项目现场',ended_at=? WHERE id=? AND status IN ('running','stopping')",(time.time(),item['run_id']))
                        finally:
                            connection.close()
            except Exception as error:
                self.execution_released(item['run_id'],int(item['quota_attempt']),str(error)[:500])

    def tick(self) -> None:
        """推进一次有界调度，不在等待期占用执行资源。

        :return: None。
        """
        if self._stop.is_set() or not self._tick_lock.acquire(blocking=False):
            return
        try:
            for batch in self._rows("SELECT * FROM project_iteration_batches WHERE status IN ('active','pausing','stopping','paused','blocked') ORDER BY COALESCE(last_launch_at,0),id"):
                try:
                    self._drive_batch(batch)
                except Exception as error:
                    self._batch_error(batch['id'],'项目对账失败：'+type(error).__name__+': '+str(error)[:300])
        finally:
            self._tick_lock.release()

    def _batch_error(self, batch_id: int, message: str) -> None:
        with self.write_lock:
            connection = self.database()
            try:
                with connection:
                    connection.execute("UPDATE project_iteration_batches SET status='blocked',generation=generation+1,error=?,updated_at=? WHERE id=? AND status NOT IN ('stopped','completed','stopping','blocked')",
                        (message,time.time(),batch_id))
            finally:
                connection.close()
        for run in self._rows("SELECT DISTINCT r.id FROM runs r JOIN project_step_attempts a ON a.run_id=r.id JOIN project_instances i ON i.id=a.instance_id WHERE i.batch_id=? AND r.status IN ('queued','running','stopping','quota_wait')",(batch_id,)):
            self.stop_run(run['id'])
        for execution in self.scenarios._open_executions(batch_id):
            self.stop_run(execution['run_id'])

    def _drive_batch(self, batch: dict) -> None:
        account = self._one('SELECT * FROM accounts WHERE id=? AND enabled=1 AND deleted_at IS NULL',(batch['account_id'],))
        if batch['status'] not in ('paused','stopping','blocked') and (account is None or self.identity(account)!=batch['account_identity']):
            self._batch_error(batch['id'],'账号已停用、删除或身份已改变')
            return
        if json.loads(batch['policy_json']).get('schema')==3:
            self.scenarios.drive(batch,account)
            return
        if json.loads(batch['policy_json']).get('schema')==2:
            self.plans.drive(batch,account)
            return
        attempts = self._rows('SELECT a.*,i.batch_id,r.status AS run_status,r.quota_attempt,r.started_at AS run_started_at,'
            'r.window_wait_until,r.error AS run_error,r.worker_container FROM project_step_attempts a '
            'JOIN project_instances i ON i.id=a.instance_id JOIN runs r ON r.id=a.run_id '
            'WHERE i.batch_id=? AND a.ended_at IS NULL ORDER BY a.id',(batch['id'],))
        for attempt in attempts:
            self._inspect_attempt(batch,account,attempt)
        batch = self._one('SELECT * FROM project_iteration_batches WHERE id=?',(batch['id'],))
        if batch['status']=='stopping':
            outstanding = self._one('SELECT a.id FROM project_step_attempts a JOIN project_instances i ON i.id=a.instance_id WHERE i.batch_id=? AND a.ended_at IS NULL',(batch['id'],))
            if outstanding is None:
                with self.write_lock:
                    connection = self.database()
                    try:
                        with connection:
                            connection.execute("UPDATE project_iteration_batches SET status='stopped',updated_at=? WHERE id=? AND status='stopping'",(time.time(),batch['id']))
                    finally:
                        connection.close()
            return
        if batch['status']=='pausing':
            running = self._one("SELECT a.id FROM project_step_attempts a JOIN project_instances i ON i.id=a.instance_id JOIN runs r ON r.id=a.run_id WHERE i.batch_id=? AND a.ended_at IS NULL AND r.status IN ('running','stopping')",(batch['id'],))
            if not running:
                with self.write_lock:
                    connection = self.database()
                    try:
                        with connection:
                            connection.execute("UPDATE project_iteration_batches SET status='paused',updated_at=? WHERE id=? AND status='pausing'",(time.time(),batch['id']))
                    finally:
                        connection.close()
            return
        if batch['status']!='active' or self._stop.is_set():
            return
        if self._one('SELECT a.id FROM project_step_attempts a JOIN project_instances i ON i.id=a.instance_id '
                'JOIN project_iteration_batches b ON b.id=i.batch_id WHERE b.account_id=? AND a.ended_at IS NULL',(batch['account_id'],)):
            return
        instances = self._rows('SELECT * FROM project_instances WHERE batch_id=? ORDER BY visit_order,id',(batch['id'],))
        if all(item['status']=='completed' for item in instances):
            with self.write_lock:
                connection = self.database()
                try:
                    with connection:
                        connection.execute("UPDATE project_iteration_batches SET status='completed',active_instance_id=NULL,updated_at=? WHERE id=? AND status='active'",(time.time(),batch['id']))
                finally:
                    connection.close()
            return
        ready = [item for item in instances if item['status'] in ('ready','not_started')]
        if not ready:
            self._batch_error(batch['id'],'剩余项目均已阻塞，已保留现场和最后通过版本')
            return
        current = next((item for item in ready if item['id']==batch['active_instance_id']),None)
        if current is None:
            active = [item for item in ready if item['started_at'] is not None]
            unstarted = [item for item in ready if item['started_at'] is None]
            policy = json.loads(batch['policy_json'])
            current = unstarted[0] if unstarted and len(active)<policy['active_projects'] else (active or unstarted)[0]
        self._reserve(batch,current,account)

    def _reserve(self, batch: dict, instance: dict, account: dict) -> None:
        manifest = json.loads(instance['manifest_json'])
        step = manifest['steps'][instance['next_step_index']]
        previous = self._one('SELECT attempt_no,report_relative FROM project_step_attempts WHERE instance_id=? AND step_id=? ORDER BY attempt_no DESC LIMIT 1',
            (instance['id'],step['id']))
        attempt_no = previous['attempt_no']+1 if previous else 1
        policy = json.loads(batch['policy_json'])
        if attempt_no>1+policy['repair_limit']:
            self._set_instance(instance['id'],status='blocked',switch_reason='修复次数已用尽')
            self._clear_current(batch['id'],instance['id'])
            return
        sample = step['checks'][0]
        # 旧批次继续使用冻结的中文路线，摘要必须同时识别新旧分隔符。
        recent = [item['goal'].split('Interface contract:',1)[0].split('接口契约：',1)[0].strip() for item in
            manifest['steps'][max(0,instance['next_step_index']-3):instance['next_step_index']]]
        prompt = ('Implement one change in the existing project. Do not recreate the project. Preserve the existing code and data.\n'
            f"Project: {manifest['title']}\nStep: {step['id']}\nGoal: {step['goal']}\n"
            f"Accepted steps: {instance['next_step_index']}. Recent results: "+('; '.join(recent) or 'None yet.')+'\n'
            'Runtime contract: python3 app.py reads one JSON request from standard input per line and writes one JSON result per line. Use only the existing runtime and standard library.\n'
            'Example verification input: '+canonical_json(sample['input']).decode()+'\n'
            'Expected example result: '+canonical_json(sample['expected']).decode()+'\n'
            'Complete the requested change and necessary checks, then give a brief summary. Do not implement future roadmap steps.')
        if previous and previous['report_relative']:
            report = read_document(self.data/safe_relative(previous['report_relative']))
            prompt += '\nPrevious attempt failure evidence: '+canonical_json(report).decode()[:12000]
        execution = self.settings()
        run_id,now = uuid.uuid4().hex[:12],time.time()
        with self.write_lock:
            connection = self.database()
            try:
                with connection:
                    current = connection.execute('SELECT status,generation FROM project_iteration_batches WHERE id=?',(batch['id'],)).fetchone()
                    if not current or current['status']!='active' or current['generation']!=batch['generation']:
                        return
                    if connection.execute('SELECT a.id FROM project_step_attempts a JOIN project_instances i ON i.id=a.instance_id JOIN project_iteration_batches b ON b.id=i.batch_id WHERE b.account_id=? AND a.ended_at IS NULL',(batch['account_id'],)).fetchone():
                        return
                    task = connection.execute('INSERT INTO tasks(topic_no,title,prompt,account_id,timeout_sec,repeat_n) VALUES(?,?,?,?,?,1)',
                        (manifest['source_topic_no'],f"[Project iteration] {manifest['title']} / {step['id']}",prompt,batch['account_id'],policy['timeout_sec']))
                    task_id = task.lastrowid
                    connection.execute('INSERT INTO runs(id,task_id,account_id,status,run_kind,claude_code_version,claude_effort_level,execution_model,quota_identity) VALUES(?,?,?,?,?,?,?,?,?)',
                        (run_id,task_id,batch['account_id'],'queued',PROJECT_RUN_KIND,execution['claude_code_version'],execution['claude_effort_level'],execution['execution_model'],batch['account_identity']))
                    connection.execute('INSERT INTO project_step_attempts(instance_id,step_id,attempt_no,generation,run_id,expected_checkpoint_digest,created_at) VALUES(?,?,?,?,?,?,?)',
                        (instance['id'],step['id'],attempt_no,batch['generation'],run_id,instance['checkpoint_digest'],now))
                    connection.execute("UPDATE project_instances SET status='ready',error=NULL,updated_at=? WHERE id=?",(now,instance['id']))
                    connection.execute('UPDATE project_iteration_batches SET active_instance_id=?,updated_at=? WHERE id=?',(instance['id'],now,batch['id']))
            finally:
                connection.close()
        self.submit(run_id,account,{'id':task_id,'prompt':prompt,'timeout_sec':policy['timeout_sec'],**execution})

    def _set_instance(self, instance_id: int, **fields) -> None:
        allowed = {'status','error','switch_reason'}
        if not fields or not set(fields).issubset(allowed):
            raise ValueError('项目状态更新字段不合法')
        with self.write_lock:
            connection = self.database()
            try:
                with connection:
                    connection.execute('UPDATE project_instances SET '+','.join(key+'=?' for key in fields)+',updated_at=? WHERE id=?',
                        (*fields.values(),time.time(),instance_id))
            finally:
                connection.close()

    def _clear_current(self, batch_id: int, instance_id: int) -> None:
        with self.write_lock:
            connection = self.database()
            try:
                with connection:
                    connection.execute('UPDATE project_iteration_batches SET active_instance_id=NULL,updated_at=? WHERE id=? AND active_instance_id=?',(time.time(),batch_id,instance_id))
            finally:
                connection.close()

    def _inspect_attempt(self, batch: dict, account: dict | None, attempt: dict) -> None:
        run_id,status = attempt['run_id'],attempt['run_status']
        if status not in TERMINAL_RUNS:
            desired = 'window_wait' if status=='queued' and attempt['window_wait_until'] is not None else ('ready' if status=='queued' else status)
            instance = self._one('SELECT * FROM project_instances WHERE id=?',(attempt['instance_id'],))
            if instance['status']!=desired:
                self._set_instance(instance['id'],status=desired)
            if status=='queued' and account and self.execution_allowed(run_id) and not self.is_executing(run_id,int(attempt['quota_attempt'])):
                run = self._one('SELECT r.*,t.prompt,t.timeout_sec FROM runs r JOIN tasks t ON t.id=r.task_id WHERE r.id=?',(run_id,))
                self.submit(run_id,account,{'id':run['task_id'],'prompt':run['prompt'],'timeout_sec':run['timeout_sec'],
                    'claude_code_version':run['claude_code_version'],'claude_effort_level':run['claude_effort_level'],
                    'model_override':run['execution_model'],'quota_attempt':run['quota_attempt']})
            return
        if self.is_executing(run_id,int(attempt['quota_attempt'])):
            return
        if attempt['execution_error']:
            self._set_instance(attempt['instance_id'],status='blocked',error=attempt['execution_error'],switch_reason='执行未能严格清理')
            self._batch_error(batch['id'],'原执行清理失败，禁止验收和再次投放')
            return
        if not attempt['execution_released_at'] or attempt['released_quota_attempt']!=attempt['quota_attempt']:
            # 从未启动的取消没有进程可清理；其它终态必须等待原 runner 的释放证据。
            if status=='stopped' and not attempt['run_started_at'] and not attempt['worker_container']:
                self.execution_released(run_id,int(attempt['quota_attempt']))
            return
        if status=='auth_failed':
            self._finish_failure(attempt,{'status':'error','message':attempt['run_error'] or 'Account authentication failed.'},block=True)
            self._batch_error(batch['id'],'账号认证失效，保留全部项目并停止投放')
            return
        if status!='success' or attempt['generation']!=batch['generation'] or batch['status'] in ('stopping','stopped'):
            cancelled = status=='stopped' or batch['status'] in ('stopping','stopped')
            self._finish_failure(attempt,{'status':'cancelled' if cancelled else 'failed','message':attempt['run_error'] or 'Execution stopped or did not complete successfully.'},
                block=status=='stopped' or batch['status'] in ('stopping','stopped'))
            return
        self._verify_attempt(batch,attempt)

    def _capture(self, instance: dict) -> tuple[dict,Path]:
        if not instance['workspace_relative']:
            raise ValueError('项目没有已发布的工作目录')
        workspace = self.data/safe_relative(instance['workspace_relative'])
        snapshot = snapshot_tree(workspace,self.objects)
        write_document(self.manifests/(snapshot['digest']+'.json'),snapshot)
        candidate = self.data/'project-verification'/snapshot['digest']
        if candidate.exists():
            if snapshot_tree(candidate)['digest']!=snapshot['digest']:
                raise ValueError('候选快照内容已改变')
        else:
            materialize_snapshot(snapshot,self.objects,candidate)
        return snapshot,candidate

    def _verify_attempt(self, batch: dict, attempt: dict) -> None:
        instance = self._one('SELECT * FROM project_instances WHERE id=?',(attempt['instance_id'],))
        manifest = json.loads(instance['manifest_json'])
        index = instance['next_step_index']
        if index>=len(manifest['steps']) or manifest['steps'][index]['id']!=attempt['step_id']:
            raise ValueError('尝试与当前路线步骤不一致')
        try:
            snapshot,candidate = self._capture(instance)
        except (OSError,ValueError) as error:
            self._finish_failure(attempt,{'status':'error','message':'候选版本无法安全封存：'+str(error)[:300]},block=True,capture=False)
            return
        cases = list(manifest['baseline_checks'])
        for step in manifest['steps'][:index+1]:
            cases.extend(step['checks'])
        with self.write_lock:
            connection = self.database()
            try:
                with connection:
                    connection.execute("UPDATE project_step_attempts SET validation_status='running',candidate_digest=? WHERE id=? AND ended_at IS NULL",(snapshot['digest'],attempt['id']))
            finally:
                connection.close()
        report = self.verifier.verify(candidate,cases)
        report.update({'candidate_digest':snapshot['digest'],'step_id':attempt['step_id'],'run_id':attempt['run_id']})
        if report['status']=='error':
            count = int(attempt['verification_errors'])+1
            with self.write_lock:
                connection = self.database()
                try:
                    with connection:
                        connection.execute("UPDATE project_step_attempts SET validation_status='error',verification_errors=? WHERE id=? AND ended_at IS NULL",(count,attempt['id']))
                finally:
                    connection.close()
            if count>=2:
                self._finish_failure(attempt,report,block=True)
            return
        if report['status']!='passed':
            self._finish_failure(attempt,report)
            return
        path = self.data/'project-artifacts/attempts'/str(attempt['id'])/'report.json'
        write_document(path,report)
        now = time.time()
        next_index = index+1
        finished = next_index==len(manifest['steps'])
        milestone_end = finished or manifest['steps'][next_index]['milestone']!=manifest['steps'][index]['milestone']
        with self.write_lock:
            connection = self.database()
            try:
                with connection:
                    parent = connection.execute('SELECT status,generation FROM project_iteration_batches WHERE id=?',(batch['id'],)).fetchone()
                    current = connection.execute('SELECT checkpoint_digest,next_step_index FROM project_instances WHERE id=?',(instance['id'],)).fetchone()
                    if (not parent or parent['status'] not in ('active','pausing','paused') or parent['generation']!=attempt['generation']
                            or current['checkpoint_digest']!=attempt['expected_checkpoint_digest'] or current['next_step_index']!=index):
                        return
                    accepted = connection.execute("UPDATE project_step_attempts SET validation_status='passed',result_digest=?,report_relative=?,accepted_checkpoint_digest=?,ended_at=? WHERE id=? AND ended_at IS NULL",
                        (digest_json(report),str(path.relative_to(self.data)),snapshot['digest'],now,attempt['id']))
                    if accepted.rowcount!=1:
                        return
                    order = connection.execute('SELECT MAX(visit_order) FROM project_instances WHERE batch_id=?',(batch['id'],)).fetchone()[0]+1
                    connection.execute('UPDATE project_instances SET checkpoint_digest=?,next_step_index=?,status=?,visit_order=?,switch_reason=?,error=NULL,updated_at=? WHERE id=?',
                        (snapshot['digest'],next_index,'completed' if finished else 'ready',order if milestone_end else instance['visit_order'],
                        '路线完成' if finished else '阶段完成后轮换' if milestone_end else '继续当前阶段',now,instance['id']))
                    if milestone_end:
                        connection.execute('UPDATE project_iteration_batches SET active_instance_id=NULL,updated_at=? WHERE id=?',(now,batch['id']))
            finally:
                connection.close()

    def _finish_failure(self, attempt: dict, report: dict, *, block: bool = False, capture: bool = True) -> None:
        instance = self._one('SELECT * FROM project_instances WHERE id=?',(attempt['instance_id'],))
        candidate_digest = attempt.get('candidate_digest')
        if capture and instance['workspace_relative']:
            try:
                snapshot,_ = self._capture(instance)
                candidate_digest = snapshot['digest']
                report['candidate_digest'] = candidate_digest
            except (OSError,ValueError) as error:
                report['snapshot_error'] = str(error)[:300]
                block = True
        path = self.data/'project-artifacts/attempts'/str(attempt['id'])/'report.json'
        write_document(path,report)
        blocked = block or attempt['attempt_no']>=1+DEFAULT_POLICY['repair_limit']
        cancelled = report['status']=='cancelled'
        now = time.time()
        with self.write_lock:
            connection = self.database()
            try:
                with connection:
                    changed = connection.execute('UPDATE project_step_attempts SET validation_status=?,result_digest=?,report_relative=?,candidate_digest=?,ended_at=? WHERE id=? AND ended_at IS NULL',
                        (report['status'] if report['status'] in ('error','cancelled') else 'failed',digest_json(report),str(path.relative_to(self.data)),candidate_digest,now,attempt['id']))
                    if changed.rowcount:
                        connection.execute('UPDATE project_instances SET status=?,error=?,switch_reason=?,updated_at=? WHERE id=?',
                            ('stopped' if cancelled else 'blocked' if blocked else 'ready',str(report.get('message') or '业务验收失败'),
                            '执行已停止' if cancelled else '项目阻塞后切换' if blocked else '在原项目中修复',now,instance['id']))
                        if blocked:
                            connection.execute('UPDATE project_iteration_batches SET active_instance_id=NULL WHERE id=? AND active_instance_id=?',(instance['batch_id'],instance['id']))
            finally:
                connection.close()

    def artifacts(self, attempt_id: int) -> dict:
        """读取控制端保存的历史验收与代码版本。

        :param attempt_id: 步骤尝试 ID。
        :return: 报告和不可变文件清单；不读取当前工作区冒充历史。
        """
        attempt = self._one('SELECT * FROM project_step_attempts WHERE id=?',(attempt_id,))
        if attempt is None:
            raise ValueError('步骤尝试不存在')
        result = {'attempt_id':attempt_id,'validation_status':attempt['validation_status'],'report':None,'files':[]}
        if attempt['report_relative']:
            result['report'] = read_document(self.data/safe_relative(attempt['report_relative']))
        checksum = attempt['accepted_checkpoint_digest'] or attempt['candidate_digest']
        if checksum:
            snapshot = read_document(self.manifests/(checksum+'.json'))
            if snapshot.get('digest')!=checksum or digest_json(snapshot.get('files'))!=checksum:
                raise ValueError('历史版本清单已损坏')
            result['digest'] = checksum
            result['files'] = [{'path':name,**value} for name,value in sorted(snapshot['files'].items())]
            previous_path = self.manifests/(attempt['expected_checkpoint_digest']+'.json')
            if previous_path.exists():
                previous = read_document(previous_path)['files']
                current = snapshot['files']
                result['changes'] = {'added':sorted(set(current)-set(previous)),
                    'removed':sorted(set(previous)-set(current)),
                    'modified':sorted(name for name in current.keys() & previous.keys() if current[name]!=previous[name])}
        return result

    def artifact_file(self, attempt_id: int, relative: str) -> dict:
        """读取版本清单内的固定内容，不跟随当前工作副本。

        :param attempt_id: 尝试 ID。
        :param relative: 清单内的文件相对路径。
        :return: 有界 UTF-8 预览或二进制提示。
        """
        relative = safe_relative(relative)
        artifact = self.artifacts(attempt_id)
        item = next((value for value in artifact['files'] if value['path']==relative),None)
        if item is None:
            raise ValueError('该轮历史版本没有此文件')
        source = self.objects/item['digest'][:2]/item['digest']
        if source.is_symlink():
            raise ValueError('历史内容对象类型不合法')
        content = source.read_bytes()
        if hashlib.sha256(content).hexdigest()!=item['digest']:
            raise ValueError('历史文件内容已损坏')
        try:
            text = content[:65536].decode('utf-8')
        except UnicodeDecodeError:
            text = '该文件为二进制内容或包含非 UTF-8 字节。'
        return {'path':relative,'text':text,'truncated':len(content)>65536}
