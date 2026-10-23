"""在既有场景执行上推进完整开发任务的外部需求方交流。"""
from __future__ import annotations

import json
import time
from typing import TYPE_CHECKING

from project_library import canonical_json, read_document, safe_relative

if TYPE_CHECKING:
    from project_scenarios import ProjectScenarios


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


class ProjectDevelopment:
    """复用原任务、回答快照与投递证据，不启动第二套模型运行环境。

    :param scenarios: 原场景执行器。
    """

    def __init__(self, scenarios: ProjectScenarios) -> None:
        """注册已有依赖。

        :param scenarios: 具有持久化和原会话能力的执行器。
        :return: None。
        """
        self.states, self.owner = scenarios, scenarios.owner

    @staticmethod
    def handles(task: dict) -> bool:
        """判断任务是否显式声明完整开发周期。

        :param task: 数据库内部任务视图。
        :return: 是否使用新任务循环。
        """
        return json.loads(task['definition_json']).get('development_cycle') in ('feature', 'bug')

    def phase(self, task_id: int) -> str:
        """从已接受的方案确认和验证事实还原业务阶段。

        :param task_id: 完整任务 ID。
        :return: investigating、implementing 或 repairing。
        """
        approved = self.owner._one("SELECT evaluation_job_id FROM project_dialogue_jobs WHERE task_id=? "
            "AND status='applied' AND json_extract(result_json,'$.action')='implement' ORDER BY id DESC LIMIT 1", (task_id,))
        if not approved:
            return 'investigating'
        failed = self.owner._one("SELECT id FROM project_evaluation_jobs WHERE task_id=? AND status='failed' "
            'AND id>? ORDER BY id DESC LIMIT 1', (task_id, approved['evaluation_job_id']))
        return 'repairing' if failed else 'implementing'

    def work(self, task_id: int) -> dict:
        """统计外部请求工作时间和中断后仍需保留的预留。

        :param task_id: 业务任务 ID。
        :return: 已确认、预留和不确定标记。
        """
        rows = self.owner._rows('SELECT work_sec,reserved_sec,status FROM project_dialogue_jobs WHERE task_id=?', (task_id,))
        return {'confirmed_sec': sum(row['work_sec'] for row in rows),
            'reserved_sec': sum(row['reserved_sec'] for row in rows),
            'uncertain': any(row['status'] == 'uncertain' for row in rows)}

    def summary(self, task_id: int) -> dict:
        """返回需求方实际调用和覆盖范围，不混入 Claude 账号用量。

        :param task_id: 完整任务 ID。
        :return: 脱敏模型、用量、调用数与工作时间。
        """
        rows = self.owner._rows('SELECT model,status,attempts_json,result_json,error FROM project_dialogue_jobs WHERE task_id=? ORDER BY id', (task_id,))
        attempts = [attempt for row in rows for attempt in json.loads(row['attempts_json'])]
        fallbacks = [json.loads(row['result_json']).get('fallback_reason') for row in rows if row['result_json']]
        coverage = {field: bool(attempts) and all(isinstance(item.get('usage'), dict) and field in item['usage']
            for item in attempts) for field in ('prompt_tokens', 'completion_tokens', 'cached_tokens')}
        result = {'requests': len(attempts), 'models': sorted({item['model'] for item in attempts}),
            'model': rows[-1]['model'] if rows else None, 'status': rows[-1]['status'] if rows else None,
            'error': rows[-1]['error'] if rows else None, 'work': self.work(task_id),
            'fallback_reason': next((reason for reason in reversed(fallbacks) if reason), None),
            'action': json.loads(rows[-1]['result_json']).get('action') if rows and rows[-1]['result_json'] else None,
            'revisions': self.revisions(task_id),
            'infrastructure_recoveries': sum(row['recoveries'] for row in self.owner._rows(
                'SELECT recoveries FROM project_dialogue_jobs WHERE task_id=?', (task_id,))),
            'coverage': coverage,
            'complete': coverage['prompt_tokens'] and coverage['completion_tokens']
                and not any(row['status'] in ('requesting', 'uncertain') for row in rows)}
        for source, target in (('prompt_tokens', 'input_tokens'), ('completion_tokens', 'output_tokens'),
                ('cached_tokens', 'cache_read_input_tokens')):
            values = [item['usage'][source] for item in attempts
                if isinstance(item.get('usage'), dict) and source in item['usage']]
            result[target] = sum(values) if values else None
        return result

    def _context(self, job: dict, task: dict) -> dict:
        definition = json.loads(task['definition_json'])
        project = self.owner._release(task['catalog_release_id']).projects[task['project_key']]
        evidence = json.loads(job['evidence_json'])
        answer = read_document(self.owner.data / safe_relative(job['answer_relative']))['text']
        materials = {relative: (project.root / safe_relative(relative)).read_text(encoding='utf-8')
            for relative in definition.get('owner_materials', [])}
        approved = self.owner._one("SELECT j.answer_relative,d.result_json FROM project_dialogue_jobs d "
            'JOIN project_evaluation_jobs j ON j.id=d.evaluation_job_id WHERE d.task_id=? '
            "AND d.status='applied' AND json_extract(d.result_json,'$.action')='implement' ORDER BY d.id DESC LIMIT 1", (task['id'],))
        agreement = None if approved is None else {
            'proposal': read_document(self.owner.data / safe_relative(approved['answer_relative']))['text'],
            'agreement': json.loads(approved['result_json'])['message']}
        return {'goal': definition['goal'], 'type': definition['development_cycle'],
            'phase': self.phase(task['id']), 'scope_paths': definition['allowed_paths'],
            'business_materials': materials, 'approved_plan': agreement,
            'conversation': [*evidence['conversation'], {'role': 'assistant', 'content': answer}]}

    def advance(self, job: dict, task: dict) -> bool:
        """生成或复用需求方消息，返回是否已接管本次回答。

        :param job: 已严格释放的冻结回答。
        :param task: 当前完整任务。
        :return: True 表示继续交流或等待；False 表示对本次交付执行原生验收。
        """
        row = self.owner._one('SELECT * FROM project_dialogue_jobs WHERE evaluation_job_id=?', (job['id'],))
        if row is None:
            context = self._context(job, task)
            self.owner.plans._write('INSERT OR IGNORE INTO project_dialogue_jobs(task_id,evaluation_job_id,generation,'
                'phase,request_json,created_at) VALUES(?,?,?,?,?,?)',
                (task['id'], job['id'], job['generation'], context['phase'], canonical_json(context).decode(), time.time()))
            row = self.owner._one('SELECT * FROM project_dialogue_jobs WHERE evaluation_job_id=?', (job['id'],))
        if row['status'] in ('ready', 'applied'):
            return self._apply(row, job, task)
        if row['status'] in ('error', 'uncertain', 'cancelled'):
            return True
        if row['status'] == 'requesting':
            # 跨进程重启时无法证明外部请求是否已计费，不能把未收回的响应盲当作没发送。
            self.owner.plans._write("UPDATE project_dialogue_jobs SET status='uncertain',error=? WHERE id=?",
                ('外部请求中断且结果未知，保留预留与现场待核对', row['id']))
            self.states._block_evaluation(job, '外部需求方请求结果未知，已保留原会话及消息依据')
            return True
        if row['retry_at'] and row['retry_at'] > time.time():
            self.owner.plans._write("UPDATE project_evaluation_jobs SET status='dialogue_wait' WHERE id=?", (job['id'],))
            return True
        parent = self.owner._one('SELECT status,generation FROM project_iteration_batches WHERE id=?', (task['batch_id'],))
        if parent['status'] != 'active' or parent['generation'] != job['generation']:
            return True
        client = self.owner.dialogue
        if client is None:
            self.states._block_evaluation(job, '完整开发周期尚未配置外部需求方服务')
            return True
        budget = self.states.budget(task['id'])
        if budget['uncertain'] or budget['remaining_sec'] < 1:
            self.states._block_evaluation(job, '完整任务预算耗尽或片段未能核实，已保留现场')
            return True
        reserved = min(60, budget['remaining_sec'])
        with self.owner.write_lock:
            connection = self.owner.database()
            try:
                with connection:
                    claimed = connection.execute("UPDATE project_dialogue_jobs SET status='requesting',reserved_sec=? "
                        "WHERE id=? AND status IN ('pending','retry_wait') AND EXISTS(SELECT 1 FROM project_iteration_batches b "
                        "WHERE b.id=? AND b.status='active' AND b.generation=?)", (reserved, row['id'], task['batch_id'], job['generation']))
                    if claimed.rowcount != 1:
                        return True
            finally:
                connection.close()
        previous = self.owner._one("SELECT model,result_json FROM project_dialogue_jobs WHERE task_id=? AND id<=? AND model IS NOT NULL "
            "ORDER BY id DESC LIMIT 1", (task['id'], row['id']))
        preferred = None
        if previous and previous['model'] in client.models:
            prior = json.loads(previous['result_json'] or '{}')
            if prior.get('configuration_revision', 'environment') == client.revision:
                preferred = previous['model']
        try:
            result = client.generate(json.loads(row['request_json']),
                preferred_model=preferred, timeout_sec=reserved)
        except (ValueError, OSError):
            result = {'status': 'error', 'category': 'configuration', 'attempts': [], 'elapsed_sec': 0,
                'error': '需求方配置或公开输入不符合要求'}
        except Exception:
            # 未知异常无法证明请求是否已发出，保留预留且不回显可能携带认证的下游异常。
            self.owner.plans._write("UPDATE project_dialogue_jobs SET status='uncertain',error=? WHERE id=?",
                ('外部调用发生未能核实的内部异常', row['id']))
            self.states._block_evaluation(job, '需求方调用状态未能核实，保留原任务与请求预留')
            return True
        attempts = [*json.loads(row['attempts_json']), *result['attempts']]
        model = result.get('model') or (attempts[-1]['model'] if attempts else None)
        retry = result['status'] != 'ready' and result['category'] in ('quota', 'rate_limit', 'unavailable', 'transport', 'timeout')
        exhausted = row['recoveries'] >= 2
        status = 'ready' if result['status'] == 'ready' else 'retry_wait' if retry and not exhausted else 'error'
        self.owner.plans._write('UPDATE project_dialogue_jobs SET status=?,result_json=?,attempts_json=?,model=?,work_sec=work_sec+?,'
            'reserved_sec=0,recoveries=recoveries+?,retry_at=?,error=?,ended_at=? WHERE id=? AND status=?',
            (status, canonical_json(result).decode(), canonical_json(attempts).decode(), model, result['elapsed_sec'],
                int(result['status'] != 'ready'), time.time() + 60 if status == 'retry_wait' else None,
                result.get('error'), time.time(), row['id'], 'requesting'))
        if status == 'error':
            self.states._block_evaluation(job, '需求方调用未能恢复，已保留任务：' + result.get('category', 'unknown'))
            return True
        if status == 'retry_wait':
            self.owner.plans._write("UPDATE project_evaluation_jobs SET status='dialogue_wait' WHERE id=?", (job['id'],))
            return True
        row = self.owner._one('SELECT * FROM project_dialogue_jobs WHERE id=?', (row['id'],))
        if row['status'] != 'ready':
            return True
        return self._apply(row, job, task)

    def _apply(self, row: dict, job: dict, task: dict) -> bool:
        result = json.loads(row['result_json'])
        action = result['action']
        if row['status'] == 'applied':
            return action != 'verify'
        if action == 'verify' and row['phase'] not in ('implementing', 'repairing'):
            self.owner.plans._write("UPDATE project_dialogue_jobs SET status='error',error=? WHERE id=?",
                ('尚未确认实施方案，不能提前验收', row['id']))
            self.states._block_evaluation(job, '需求方提前请求交付验收，已保留原会话待检查')
            return True
        if action == 'verify' and not self._revision_allowed(job):
            return True
        parent = self.owner._one('SELECT status,generation FROM project_iteration_batches WHERE id=?', (task['batch_id'],))
        if parent['generation'] != row['generation'] or parent['status'] in ('stopping', 'stopped', 'blocked', 'completed'):
            self.owner.plans._write("UPDATE project_dialogue_jobs SET status='cancelled' WHERE id=?", (row['id'],))
            return True
        if parent['status'] != 'active':
            return True
        with self.owner.write_lock:
            connection = self.owner.database()
            try:
                with connection:
                    updated = connection.execute("UPDATE project_dialogue_jobs SET status='applied' WHERE id=? AND status='ready' "
                        "AND EXISTS(SELECT 1 FROM project_iteration_batches b WHERE b.id=? AND b.status='active' AND b.generation=?) "
                        "AND EXISTS(SELECT 1 FROM project_scenario_tasks t JOIN project_evaluation_jobs j ON j.task_id=t.id "
                        "WHERE t.id=? AND t.status='evaluating' AND j.id=? AND j.status IN ('queued','mechanical_running','dialogue_wait') "
                        'AND NOT EXISTS(SELECT 1 FROM project_evaluation_jobs newer WHERE newer.task_id=t.id AND newer.id>j.id))',
                        (row['id'], task['batch_id'], row['generation'], task['id'], job['id']))
                    if updated.rowcount != 1:
                        return True
                    if action != 'verify':
                        phase = 'implementing' if action == 'implement' else row['phase']
                        connection.execute("UPDATE project_evaluation_jobs SET status='dialogue_done',ended_at=? WHERE id=?",
                            (time.time(), job['id']))
                        connection.execute("UPDATE project_scenario_tasks SET status='ready',phase=?,next_reason='clarification',next_prompt=?,"
                            'turn_no=turn_no+1,error=NULL,updated_at=? WHERE id=? AND status=?',
                            (phase, result['message'], time.time(), task['id'], 'evaluating'))
            finally:
                connection.close()
        return action != 'verify'

    def revisions(self, task_id: int, *, before_job: int | None = None, next_digest: str | None = None) -> dict:
        """从冻结交付计数业务修复与同版本复核，交流及基础设施切片不计入。

        :param task_id: 完整任务 ID。
        :param before_job: 可选的当前验收边界，排除自身及后续作业。
        :param next_digest: 可选的待验证代码摘要，用于准入前计算。
        :return: 独立修复／复核计数及同版本程序失败标志。
        """
        history = self.owner._rows('SELECT id,status,candidate_digest,native_result_json FROM project_evaluation_jobs '
            "WHERE task_id=? AND (? IS NULL OR id<?) AND native_result_json IS NOT NULL AND status IN ('passed','failed') ORDER BY id",
            (task_id, before_job, before_job))
        pairs = [(parent, item['candidate_digest']) for parent, item in zip(history, history[1:]) if parent['status'] == 'failed']
        if next_digest is not None and history and history[-1]['status'] == 'failed':
            pairs.append((history[-1], next_digest))
        return {'business_repairs': sum(parent['candidate_digest'] != current for parent, current in pairs),
            'review_appeals': sum(parent['candidate_digest'] == current for parent, current in pairs),
            'same_program_failure': bool(pairs and pairs[-1][0]['candidate_digest'] == pairs[-1][1]
                and json.loads(pairs[-1][0]['native_result_json'])['status'] != 'passed')}

    def _revision_allowed(self, job: dict) -> bool:
        counts = self.revisions(job['task_id'], before_job=job['id'], next_digest=job['candidate_digest'])
        if counts['business_repairs'] > 2 or counts['review_appeals'] > 1 or counts['same_program_failure']:
            self.states._block_evaluation(job, '有限修复或同版本复核已用尽，保留交付与原会话')
            return False
        return True

    @staticmethod
    def _failure_facts(program: dict) -> dict:
        # 大型回归包含完整收集清单和导入证明；反馈保留失败事实，避免大小截断把问题原因一并丢掉。
        result = {key: program[key] for key in ('status', 'returncode', 'timed_out', 'counts', 'feedback_codes') if key in program}
        for key in ('message', 'stderr', 'stdout_tail'):
            if isinstance(program.get(key), str):
                result[key] = program[key].encode()[-2400:].decode('utf-8', errors='ignore')
        for key in ('actual', 'expected'):
            value = program.get(key)
            if isinstance(value, dict):
                failed = [(name, item) for name, item in value.items() if item is False]
                remaining = [(name, item) for name, item in value.items() if item is not False]
                result[key] = dict((failed + remaining)[:40])
            elif value is not None:
                result[key] = value
        for key in ('unauthorized_files', 'collection_errors', 'failures'):
            if isinstance(program.get(key), list):
                result[key] = program[key][:8]
        for key in ('native', 'business', 'regression'):
            if isinstance(program.get(key), dict):
                result[key] = ProjectDevelopment._failure_facts(program[key])
        return result

    @staticmethod
    def failure_feedback(job: dict, result: dict) -> str:
        """整理可操作的交付反馈，避免只给抽象失败码。

        :param job: 当前冻结验证作业。
        :param result: 已校验的判定。
        :return: 回到原会话的英文业务反馈。
        """
        details = {'feedback_codes': result.get('feedback_codes', []),
            'violations': [{'reason': item['reason'].encode()[:600].decode('utf-8', errors='ignore'),
                'evidence': [reference.encode()[:120].decode('utf-8', errors='ignore') for reference in item['evidence'][:4]]}
                for item in result.get('criteria', []) if item['status'] == 'violated'][:4]}
        native = json.loads(job['native_result_json']) if job.get('native_result_json') else None
        if native:
            details['program_result'] = ProjectDevelopment._failure_facts(native)
        encoded = canonical_json(details).decode()
        if len(encoded.encode()) > 12000:
            facts = canonical_json(details.pop('program_result', {}))
            details['program_excerpt_truncated'] = True
            # JSON 字符串可能再转义引号和反斜线，按剩余字节的一半预留最终编码空间。
            available = max(0, (11500 - len(canonical_json(details))) // 2)
            details['program_excerpt'] = facts[:available].decode('utf-8', errors='ignore')
            encoded = canonical_json(details).decode()
        return ('Continue the same agreed task in the original conversation. Investigate the concrete validation feedback '
            'below, repair the demonstrated issues, and deliver the revised implementation. If a semantic review is '
            'mistaken, explain the relevant source or behavioral evidence; do not invent new requirements. '
            'A confirmed program failure must still be fixed. Validation feedback:\n' + encoded)
