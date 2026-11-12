"""bench 的不可变初始数据库迁移定义，业务查询与运行时初始化独立。"""
from __future__ import annotations

import re
import sqlite3


SQL_TOKEN = re.compile(r"'(?:(?:'')|[^'])*'|\"(?:(?:\"\")|[^\"])*\"|`(?:(?:``)|[^`])*`|\[[^\]]*\]|--[^\n]*(?:\n|$)|/\*[\s\S]*?\*/|[:@$][A-Za-z_][A-Za-z0-9_]*|[A-Za-z_][A-Za-z0-9_]*")
PROJECTS_IDENTIFIER = re.compile(r'projects_[A-Za-z0-9_]+\Z', re.IGNORECASE)


def _warmup_sql(sql: str) -> str:
    """只映射 SQL 标识，跳过字符串常量及注释。:param sql: 服务端固定SQL。:return: 养号物理表SQL。"""
    def replace(match):
        token = match.group()
        if token.startswith(('\'', '--', '/*', ':', '@', '$')):
            return token
        if token[0] in ('"', '`', '['):
            inner = token[1:-1]
            return token[0] + 'warmup_' + inner + token[-1] if PROJECTS_IDENTIFIER.fullmatch(inner) else token
        return 'warmup_' + token if PROJECTS_IDENTIFIER.fullmatch(token) else token
    return SQL_TOKEN.sub(replace, sql)


class _ProjectsConnection:
    """转发真实 SQLite 连接，仅固定改写服务自身的工程表和索引名称。"""

    def __init__(self, connection):
        """保留原连接的行工厂与事务行为。:param connection: 已建立连接。:return: None。"""
        self.connection = connection

    def execute(self, sql, parameters=()):
        """执行映射后的SQL，绑定值不作转换。:param sql: 受信SQL。:param parameters: 原参数。:return: 原SQLite游标。"""
        return self.connection.execute(_warmup_sql(sql), parameters)

    def executescript(self, sql):
        """初始化隔离表和索引，保留SQLite脚本事务语义。:param sql: 受信schema脚本。:return: 原SQLite游标。"""
        return self.connection.executescript(_warmup_sql(sql))

    def __enter__(self):
        """进入原连接事务上下文。:return: 映射连接自身。"""
        self.connection.__enter__()
        return self

    def __exit__(self, kind, value, traceback):
        """沿用原连接的提交或回滚。:param kind: 异常类型。:param value: 异常值。:param traceback: 栈。:return: 原连接处理结果。"""
        return self.connection.__exit__(kind, value, traceback)

    def close(self):
        """关闭原连接。:return: None。"""
        return self.connection.close()


class ProjectsDatabase:
    """把独立工程空间接入同一SQLite连接工厂，不复制工程服务。

    :param database: 返回真实SQLite连接的工厂。
    :param namespace: 服务端固定的 projects 或 warmup。
    """

    def __init__(self, database, namespace: str = 'projects') -> None:
        """校验固定空间，初始化不访问数据库。:param database: 连接工厂。:param namespace: 固定空间。:return: None。"""
        if namespace not in ('projects', 'warmup'):
            raise ValueError('工程数据库空间不合法')
        self.database, self.namespace = database, namespace

    def __call__(self):
        """建立连接；原空间返回原对象以保留全部旧行为。:return: 原连接或养号SQL隔离连接。"""
        connection = self.database()
        return connection if self.namespace == 'projects' else _ProjectsConnection(connection)


_SCHEMA = """
CREATE TABLE IF NOT EXISTS accounts (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT UNIQUE NOT NULL,
  profile_path TEXT NOT NULL,
  upstream_proxy_scheme TEXT DEFAULT 'socks5',
  upstream_socks5_host TEXT,
  upstream_socks5_port INTEGER,
  upstream_socks5_user TEXT,
  upstream_socks5_pass TEXT,
  timezone TEXT,
  run_window_json TEXT,
  claude_code_version TEXT,
  projects_capture_enabled INTEGER NOT NULL DEFAULT 0,
  warmup_capture_enabled INTEGER NOT NULL DEFAULT 0,
  cc2api_account_id INTEGER,
  warmup_enabled INTEGER DEFAULT 0,
  warmup_interval_min_hours INTEGER DEFAULT 3,
  warmup_interval_max_hours INTEGER DEFAULT 5,
  warmup_quota_5h_limit_percent INTEGER,
  warmup_quota_7d_limit_percent INTEGER,
  warmup_next_run_at REAL,
  warmup_last_attempt_at REAL,
  warmup_last_run_id TEXT,
  warmup_last_status TEXT,
  warmup_last_error TEXT,
  warmup_auth_failures INTEGER DEFAULT 0,
  oauth_refresh_last_attempt_at REAL,
  oauth_refresh_last_status TEXT,
  oauth_refresh_last_error TEXT,
  enabled INTEGER DEFAULT 1,
  deleted_at REAL,
  created_at REAL DEFAULT (julianday('now'))
);

CREATE TABLE IF NOT EXISTS topics (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  no INTEGER UNIQUE NOT NULL,
  title TEXT NOT NULL,
  description TEXT NOT NULL DEFAULT '',
  category TEXT NOT NULL DEFAULT '',
  enabled INTEGER DEFAULT 1,
  deleted_at REAL,
  followups_json TEXT NOT NULL DEFAULT '[]',
  created_at REAL DEFAULT (julianday('now')),
  updated_at REAL DEFAULT (julianday('now'))
);

CREATE TABLE IF NOT EXISTS tasks (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  topic_no INTEGER NOT NULL,
  title TEXT NOT NULL,
  prompt TEXT NOT NULL,
  account_id INTEGER NOT NULL,
  batch_id INTEGER,
  topic_id INTEGER,
  status TEXT DEFAULT 'active',
  deleted_at REAL,
  timeout_sec INTEGER DEFAULT 1800,
  repeat_n INTEGER DEFAULT 1,
  followup_candidates_json TEXT NOT NULL DEFAULT '[]',
  created_at REAL DEFAULT (julianday('now')),
  FOREIGN KEY(account_id) REFERENCES accounts(id)
);

CREATE TABLE IF NOT EXISTS task_batches (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  account_id INTEGER NOT NULL,
  name TEXT NOT NULL,
  concurrency INTEGER DEFAULT 2,
  interval_min_sec INTEGER DEFAULT 0,
  interval_max_sec INTEGER DEFAULT 0,
  timeout_sec INTEGER DEFAULT 1800,
  status TEXT NOT NULL DEFAULT 'active',
  next_launch_at REAL,
  window_wait_until REAL,
  deleted_at REAL,
  created_at REAL DEFAULT (julianday('now')),
  updated_at REAL DEFAULT (julianday('now')),
  FOREIGN KEY(account_id) REFERENCES accounts(id)
);

CREATE TABLE IF NOT EXISTS task_batch_items (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  batch_id INTEGER NOT NULL,
  topic_id INTEGER NOT NULL,
  task_id INTEGER,
  run_id TEXT,
  prompt TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'pending',
  followup_candidates_json TEXT NOT NULL DEFAULT '[]',
  created_at REAL DEFAULT (julianday('now')),
  updated_at REAL DEFAULT (julianday('now')),
  FOREIGN KEY(batch_id) REFERENCES task_batches(id),
  FOREIGN KEY(topic_id) REFERENCES topics(id)
);

CREATE TABLE IF NOT EXISTS app_settings (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL,
  updated_at REAL DEFAULT (julianday('now'))
);

CREATE TABLE IF NOT EXISTS runs (
  id TEXT PRIMARY KEY,
  task_id INTEGER NOT NULL,
  account_id INTEGER NOT NULL,
  batch_id INTEGER,
  topic_id INTEGER,
  status TEXT NOT NULL DEFAULT 'queued',
  exit_code INTEGER,
  worker_container TEXT,
  sidecar_container TEXT,
  workspace_dir TEXT,
  flows_dir TEXT,
  run_kind TEXT DEFAULT 'normal',
  capture_mode TEXT,
  capture_summary_path TEXT,
  capture_model_override TEXT,
  capture_permission_mode TEXT DEFAULT 'bypassPermissions',
  claude_code_version TEXT,
  claude_code_version_source TEXT,
  claude_effort_level TEXT,
  execution_model TEXT,
  quota_attempt INTEGER NOT NULL DEFAULT 0,
  quota_resume_at REAL,
  window_wait_until REAL,
  quota_identity TEXT,
  started_at REAL,
  ended_at REAL,
  stop_requested_at REAL,
  deleted_at REAL,
  error TEXT,
  followup_plan_json TEXT NOT NULL DEFAULT '[]',
  followup_timing_json TEXT,
  created_at REAL DEFAULT (julianday('now'))
);
CREATE INDEX IF NOT EXISTS idx_runs_status  ON runs(status);
CREATE INDEX IF NOT EXISTS idx_runs_account ON runs(account_id);
CREATE INDEX IF NOT EXISTS idx_runs_task    ON runs(task_id);
CREATE INDEX IF NOT EXISTS idx_topics_no    ON topics(no);
CREATE INDEX IF NOT EXISTS idx_batches_account ON task_batches(account_id);
CREATE INDEX IF NOT EXISTS idx_batch_items_batch ON task_batch_items(batch_id);
CREATE TABLE IF NOT EXISTS account_quota_states (
  account_id INTEGER PRIMARY KEY,
  identity TEXT NOT NULL,
  state_json TEXT NOT NULL DEFAULT '{}',
  recovery_source TEXT,
  updated_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS quota_observation_cursors (
  source TEXT PRIMARY KEY,
  account_id INTEGER NOT NULL,
  identity TEXT NOT NULL,
  path TEXT NOT NULL,
  file_identity TEXT,
  byte_offset INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS warmup_quota_admissions (
  account_id INTEGER PRIMARY KEY,
  identity TEXT NOT NULL,
  policy_key TEXT NOT NULL,
  window_key TEXT NOT NULL,
  source TEXT NOT NULL,
  created_at REAL NOT NULL
);
"""


def _ensure_column(conn: sqlite3.Connection, table: str, column: str, ddl: str) -> None:
    """
    幂等补 SQLite 列，兼容已经存在的旧 `data/db.sqlite`。

    :param conn: 当前数据库连接
    :param table: 表名
    :param column: 需要补齐的列名
    :param ddl: `ALTER TABLE ADD COLUMN` 后的列定义
    :return: None
    """
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    if any(r["name"] == column for r in rows):
        return
    conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")


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


PROJECTS_SCHEMA = '''
CREATE TABLE IF NOT EXISTS projects_agents (
  account_id INTEGER PRIMARY KEY, generation INTEGER NOT NULL DEFAULT 0,
  status TEXT NOT NULL DEFAULT 'off', project_keys_json TEXT NOT NULL DEFAULT '[]',
  instructions TEXT NOT NULL DEFAULT '', session_file TEXT, current_work_id TEXT,
  budget_sec INTEGER NOT NULL DEFAULT 3600, message TEXT, updated_at REAL NOT NULL,
  schedule_enabled INTEGER NOT NULL DEFAULT 0, schedule_interval_sec INTEGER NOT NULL DEFAULT 3600,
  schedule_next_at REAL, schedule_last_started_at REAL, schedule_state TEXT NOT NULL DEFAULT 'off',
  schedule_message TEXT, schedule_identity TEXT,
  schedule_interval_max_sec INTEGER, cycle_no INTEGER NOT NULL DEFAULT 1,
  FOREIGN KEY(account_id) REFERENCES accounts(id)
);
CREATE TABLE IF NOT EXISTS projects_work (
  id TEXT PRIMARY KEY, account_id INTEGER NOT NULL, project_key TEXT NOT NULL,
  objective_id TEXT NOT NULL, goal TEXT NOT NULL, definition_json TEXT NOT NULL,
  library_root TEXT NOT NULL, library_digest TEXT NOT NULL, settings_json TEXT NOT NULL,
  generation INTEGER NOT NULL, status TEXT NOT NULL, session_id TEXT NOT NULL,
  runtime_json TEXT, baseline_json TEXT, observation_json TEXT, observation_id TEXT,
  account_identity TEXT, claude_usage_json TEXT NOT NULL DEFAULT '{}',
  started_at REAL, segment_started_at REAL, work_sec REAL NOT NULL DEFAULT 0,
  created_at REAL NOT NULL, ended_at REAL, message TEXT, failure_json TEXT,
  cycle_no INTEGER NOT NULL DEFAULT 1,
  FOREIGN KEY(account_id) REFERENCES projects_agents(account_id)
);
CREATE UNIQUE INDEX IF NOT EXISTS projects_one_work_per_account ON projects_work(account_id)
  WHERE status NOT IN ('passed','stopped','deferred');
CREATE TABLE IF NOT EXISTS projects_actions (
  id TEXT PRIMARY KEY, work_id TEXT NOT NULL, generation INTEGER NOT NULL,
  request_json TEXT NOT NULL, status TEXT NOT NULL, error TEXT,
  created_at REAL NOT NULL, ended_at REAL,
  FOREIGN KEY(work_id) REFERENCES projects_work(id)
);
CREATE TABLE IF NOT EXISTS projects_events (
  id INTEGER PRIMARY KEY AUTOINCREMENT, account_id INTEGER NOT NULL,
  work_id TEXT, kind TEXT NOT NULL, payload_json TEXT NOT NULL,
  event_key TEXT UNIQUE, created_at REAL NOT NULL,
  FOREIGN KEY(account_id) REFERENCES projects_agents(account_id)
);
CREATE TABLE IF NOT EXISTS projects_submissions (
  id TEXT PRIMARY KEY, work_id TEXT NOT NULL, generation INTEGER NOT NULL,
  digest TEXT NOT NULL, status TEXT NOT NULL, report_json TEXT,
  created_at REAL NOT NULL, ended_at REAL,
  FOREIGN KEY(work_id) REFERENCES projects_work(id)
);
CREATE TABLE IF NOT EXISTS projects_verification_holds (
  work_id TEXT PRIMARY KEY, retry_at REAL NOT NULL DEFAULT 0,
  deferrals INTEGER NOT NULL DEFAULT 0, timeout_turns INTEGER NOT NULL DEFAULT 0,
  last_deferred_at REAL NOT NULL DEFAULT 0, reason TEXT,
  FOREIGN KEY(work_id) REFERENCES projects_work(id)
);
'''


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


DEVELOPMENT_SQL = '''
CREATE TABLE IF NOT EXISTS project_dialogue_jobs (
  id INTEGER PRIMARY KEY AUTOINCREMENT, task_id INTEGER NOT NULL,
  evaluation_job_id INTEGER NOT NULL UNIQUE, generation INTEGER NOT NULL,
  status TEXT NOT NULL DEFAULT 'pending', phase TEXT NOT NULL,
  request_json TEXT NOT NULL, result_json TEXT, attempts_json TEXT NOT NULL DEFAULT '[]',
  model TEXT, work_sec REAL NOT NULL DEFAULT 0, reserved_sec REAL NOT NULL DEFAULT 0,
  recoveries INTEGER NOT NULL DEFAULT 0, retry_at REAL, error TEXT,
  created_at REAL NOT NULL, ended_at REAL,
  FOREIGN KEY(task_id) REFERENCES project_scenario_tasks(id),
  FOREIGN KEY(evaluation_job_id) REFERENCES project_evaluation_jobs(id)
);
CREATE INDEX IF NOT EXISTS idx_dialogue_task ON project_dialogue_jobs(task_id,id);
'''


def initialize_account_runtime_schema(connection) -> None:
    """初始化原有持久结构，保留幂等迁移与命名空间。

    :param connection: 已建立连接。
    :return: None。
    """
    connection.execute("""CREATE TABLE IF NOT EXISTS account_environments (
        environment_id TEXT PRIMARY KEY, name TEXT NOT NULL UNIQUE,
        account_id INTEGER UNIQUE, fingerprint_json TEXT NOT NULL,
        generation INTEGER NOT NULL DEFAULT 0, container_id TEXT,
        state TEXT NOT NULL DEFAULT 'stopped')""")
    environment_columns = {row["name"] for row in connection.execute("PRAGMA table_info(account_environments)")}
    for column, kind in (("network_container_id", "TEXT"), ("sender_container_id", "TEXT"),
            ("isolation_version", "INTEGER NOT NULL DEFAULT 0")):
        if column not in environment_columns:
            connection.execute(f"ALTER TABLE account_environments ADD COLUMN {column} {kind}")
    columns = {row["name"] for row in connection.execute("PRAGMA table_info(runs)")}
    if columns:
        for column, kind in (("environment_id", "TEXT"), ("environment_generation", "INTEGER"),
                ("execution_source", "TEXT"), ("runtime_release", "TEXT")):
            if column not in columns:
                connection.execute(f"ALTER TABLE runs ADD COLUMN {column} {kind}")


def initialize_projects_schema(connection, namespace: str = "projects") -> None:
    """初始化原有持久结构，保留幂等迁移与命名空间。

    :param connection: 已建立连接。
    :param namespace: 固定的项目或养号空间。
    :return: None。
    """
    connection.executescript(PROJECTS_SCHEMA)
    index_name = ('warmup_' if namespace == 'warmup' else '') + 'projects_one_work_per_account'
    index = connection.execute("SELECT sql FROM sqlite_master WHERE type='index' AND name=?", (index_name,)).fetchone()
    if index and 'deferred' not in index['sql']:
        # 待复验保留原work，但不能继续占用该账号唯一的活动目标槽位。
        connection.execute('DROP INDEX projects_one_work_per_account')
        connection.execute("CREATE UNIQUE INDEX projects_one_work_per_account ON projects_work(account_id) WHERE status NOT IN ('passed','stopped','deferred')")
    columns = {row['name'] for row in connection.execute('PRAGMA table_info(projects_work)')}
    for name, definition in (('account_identity', 'TEXT'), ('claude_usage_json', "TEXT NOT NULL DEFAULT '{}'"),
            ('failure_json', 'TEXT')):
        if name not in columns:
            connection.execute(f'ALTER TABLE projects_work ADD COLUMN {name} {definition}')
    if 'cycle_no' not in columns:
        connection.execute('ALTER TABLE projects_work ADD COLUMN cycle_no INTEGER NOT NULL DEFAULT 1')
    columns = {row['name'] for row in connection.execute('PRAGMA table_info(projects_agents)')}
    for name, definition in (
            ('schedule_enabled', 'INTEGER NOT NULL DEFAULT 0'),
            ('schedule_interval_sec', 'INTEGER NOT NULL DEFAULT 3600'),
            ('schedule_next_at', 'REAL'), ('schedule_last_started_at', 'REAL'),
            ('schedule_state', "TEXT NOT NULL DEFAULT 'off'"),
            ('schedule_message', 'TEXT'), ('schedule_identity', 'TEXT')):
        if name not in columns:
            connection.execute(f'ALTER TABLE projects_agents ADD COLUMN {name} {definition}')
    for name, definition in (('schedule_interval_max_sec', 'INTEGER'), ('cycle_no', 'INTEGER NOT NULL DEFAULT 1')):
        if name not in columns:
            connection.execute(f'ALTER TABLE projects_agents ADD COLUMN {name} {definition}')


def initialize_ownership_schema(connection) -> None:
    """初始化原有持久结构，保留幂等迁移与命名空间。

    :param connection: 已建立连接。
    :return: None。
    """
    connection.execute("CREATE TABLE IF NOT EXISTS account_credential_ownerships ("
        "account_id INTEGER PRIMARY KEY,record_json TEXT NOT NULL)")
    connection.execute("CREATE TABLE IF NOT EXISTS local_credential_authorizations ("
        "account_id INTEGER PRIMARY KEY,record_json TEXT NOT NULL)")


def initialize_session_schema(conn: sqlite3.Connection) -> None:
    """建立原有管理会话登记，保持认证入口的幂等行为。

    :param conn: 当前数据库连接。
    :return: None。
    """
    conn.execute("CREATE TABLE IF NOT EXISTS v3_management_sessions (token_hash TEXT PRIMARY KEY, expires_at INTEGER NOT NULL)")


def initialize_bench_schema(conn: sqlite3.Connection) -> None:
    """按原依赖顺序建立两类工程和账号结构。

    :param conn: 本部署数据库连接。
    :return: None。
    """
    conn.executescript(_SCHEMA)
    conn.executescript(PROJECT_SCHEMA)
    conn.executescript(PROJECTS_SCHEMA)
    initialize_plan_schema(conn)
    initialize_scenario_schema(conn)
    _ensure_column(conn, "accounts", "upstream_proxy_scheme", "TEXT DEFAULT 'socks5'")
    _ensure_column(conn, "accounts", "timezone", "TEXT")
    _ensure_column(conn, "accounts", "run_window_json", "TEXT")
    _ensure_column(conn, "accounts", "claude_code_version", "TEXT")
    _ensure_column(conn, "accounts", "projects_capture_enabled", "INTEGER NOT NULL DEFAULT 0")
    _ensure_column(conn, "accounts", "warmup_capture_enabled", "INTEGER NOT NULL DEFAULT 0")
    _ensure_column(conn, "runs", "window_wait_until", "REAL")
    _ensure_column(conn, "task_batches", "window_wait_until", "REAL")
    _ensure_column(conn, "accounts", "deleted_at", "REAL")
    _ensure_column(conn, "accounts", "cc2api_account_id", "INTEGER")
    _ensure_column(conn, "accounts", "warmup_enabled", "INTEGER DEFAULT 0")
    _ensure_column(conn, "accounts", "warmup_quota_5h_limit_percent", "INTEGER")
    _ensure_column(conn, "accounts", "warmup_quota_7d_limit_percent", "INTEGER")
    _ensure_column(
        conn, "accounts", "warmup_interval_min_hours", "INTEGER DEFAULT 3"
    )
    _ensure_column(
        conn, "accounts", "warmup_interval_max_hours", "INTEGER DEFAULT 5"
    )
    _ensure_column(conn, "accounts", "warmup_next_run_at", "REAL")
    _ensure_column(conn, "accounts", "warmup_last_attempt_at", "REAL")
    _ensure_column(conn, "accounts", "warmup_last_run_id", "TEXT")
    _ensure_column(conn, "accounts", "warmup_last_status", "TEXT")
    _ensure_column(conn, "accounts", "warmup_last_error", "TEXT")
    _ensure_column(
        conn, "accounts", "warmup_auth_failures", "INTEGER DEFAULT 0"
    )
    _ensure_column(conn, "accounts", "oauth_refresh_last_attempt_at", "REAL")
    _ensure_column(conn, "accounts", "oauth_refresh_last_status", "TEXT")
    _ensure_column(conn, "accounts", "oauth_refresh_last_error", "TEXT")
    _ensure_column(conn, "tasks", "batch_id", "INTEGER")
    _ensure_column(conn, "tasks", "topic_id", "INTEGER")
    _ensure_column(conn, "tasks", "status", "TEXT DEFAULT 'active'")
    _ensure_column(conn, "tasks", "deleted_at", "REAL")
    _ensure_column(conn, "runs", "batch_id", "INTEGER")
    _ensure_column(conn, "runs", "topic_id", "INTEGER")
    _ensure_column(conn, "runs", "stop_requested_at", "REAL")
    _ensure_column(conn, "runs", "deleted_at", "REAL")
    _ensure_column(conn, "runs", "run_kind", "TEXT DEFAULT 'normal'")
    _ensure_column(conn, "runs", "capture_mode", "TEXT")
    _ensure_column(conn, "runs", "capture_summary_path", "TEXT")
    _ensure_column(conn, "runs", "capture_model_override", "TEXT")
    _ensure_column(
        conn,
        "runs",
        "capture_permission_mode",
        "TEXT DEFAULT 'bypassPermissions'",
    )
    _ensure_column(conn, "runs", "claude_code_version", "TEXT")
    _ensure_column(conn, "runs", "claude_code_version_source", "TEXT")
    _ensure_column(conn, "runs", "claude_effort_level", "TEXT")
    _ensure_column(conn, "runs", "execution_model", "TEXT")
    _ensure_column(conn, "runs", "quota_attempt", "INTEGER NOT NULL DEFAULT 0")
    _ensure_column(conn, "runs", "quota_resume_at", "REAL")
    _ensure_column(conn, "runs", "quota_identity", "TEXT")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_runs_batch ON runs(batch_id)")
    conn.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_accounts_cc2api_account_id "
        "ON accounts(cc2api_account_id) WHERE cc2api_account_id IS NOT NULL"
    )
    _ensure_column(conn, "topics", "followups_json", "TEXT NOT NULL DEFAULT '[]'")
    _ensure_column(conn, "tasks", "followup_candidates_json", "TEXT NOT NULL DEFAULT '[]'")
    _ensure_column(conn, "task_batch_items", "followup_candidates_json", "TEXT NOT NULL DEFAULT '[]'")
    _ensure_column(conn, "runs", "followup_plan_json", "TEXT NOT NULL DEFAULT '[]'")
    _ensure_column(conn, "runs", "followup_timing_json", "TEXT")
    initialize_account_runtime_schema(conn)
    initialize_ownership_schema(conn)
    initialize_projects_schema(conn)
    initialize_projects_schema(ProjectsDatabase(lambda: conn, "warmup")(), "warmup")
    initialize_session_schema(conn)
