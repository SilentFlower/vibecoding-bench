"""由账号 Pi 自主推进原题库养号，记录真实会话、投递意图与完成证据。"""
from __future__ import annotations

import hashlib
import json
import math
import threading
import time
import uuid
from pathlib import Path

from pi_owners import AccountPiOwners
from pi_terminal import KEYS
from projects_pi import ProjectsPi
from topic_library import validate_followups
from warmup_runtime import matches_topic_input


SCHEMA = '''
CREATE TABLE IF NOT EXISTS warmup_pi_agents (
 account_id INTEGER PRIMARY KEY, generation INTEGER NOT NULL DEFAULT 0,
 managed INTEGER NOT NULL DEFAULT 0, status TEXT NOT NULL DEFAULT 'off',
 instructions TEXT NOT NULL DEFAULT '', budget_sec INTEGER NOT NULL DEFAULT 1800,
 current_round_id TEXT, session_file TEXT, message TEXT, last_reason TEXT,
 recovery_count INTEGER NOT NULL DEFAULT 0, recovery_phase TEXT, retry_at REAL,
 updated_at REAL NOT NULL, FOREIGN KEY(account_id) REFERENCES accounts(id)
);
CREATE TABLE IF NOT EXISTS warmup_pi_rounds (
 id TEXT PRIMARY KEY, account_id INTEGER NOT NULL, generation INTEGER NOT NULL,
 topic_id INTEGER NOT NULL, topic_no INTEGER NOT NULL, title TEXT NOT NULL,
 topic_json TEXT NOT NULL, settings_json TEXT NOT NULL, account_identity TEXT NOT NULL,
 status TEXT NOT NULL, session_id TEXT NOT NULL, runtime_json TEXT,
 observation_json TEXT, observation_id TEXT, evidence_json TEXT, claude_usage_json TEXT,
 work_sec REAL NOT NULL DEFAULT 0, created_at REAL NOT NULL, started_at REAL,
 segment_started_at REAL, ended_at REAL, message TEXT,
 FOREIGN KEY(account_id) REFERENCES warmup_pi_agents(account_id)
);
CREATE UNIQUE INDEX IF NOT EXISTS warmup_pi_one_active_round ON warmup_pi_rounds(account_id)
 WHERE status NOT IN ('completed','stopped');
CREATE TABLE IF NOT EXISTS warmup_pi_events (
 id INTEGER PRIMARY KEY AUTOINCREMENT, account_id INTEGER NOT NULL, round_id TEXT,
 kind TEXT NOT NULL, payload_json TEXT NOT NULL, event_key TEXT UNIQUE, created_at REAL NOT NULL,
 FOREIGN KEY(account_id) REFERENCES warmup_pi_agents(account_id)
);
CREATE INDEX IF NOT EXISTS warmup_pi_event_page ON warmup_pi_events(account_id,id);
CREATE TABLE IF NOT EXISTS warmup_pi_actions (
 id TEXT PRIMARY KEY, round_id TEXT NOT NULL, generation INTEGER NOT NULL,
 tool_call_id TEXT NOT NULL, request_json TEXT NOT NULL, status TEXT NOT NULL,
 error TEXT, created_at REAL NOT NULL, ended_at REAL,
 FOREIGN KEY(round_id) REFERENCES warmup_pi_rounds(id)
);
'''

GUIDE = '''你是当前账号的题库养号负责人，由你完整指挥 Claude Code，而不是执行固定关键词或自动输入脚本。
先读取 account_state 和 topic_read，继续已有未完成轮次；每轮只处理冻结题目，不切到工程项目池。
用 claude_start 创建或恢复本轮同一工作区和 Claude 原会话。用 claude_observe 观察终端及真实回复，按实际情况讨论、回答澄清、确认方案、要求实现和修正。
题目的初始需求和选定补充必须完整原文发送，不能删改；其它澄清、确认、收尾由你根据实际对话决定。已投递的内容不要因恢复而重复发送。
每次 claude_input 使用最近 observation_id。投递成功只代表终端已收到，必须继续观察正常回复，排队和错误消息不代表消费。
只有本轮全部冻结需求均在原生主会话中得到后续正常回复，才能 round_finish；不能只凭自己或 Claude 宣称完成。
遇到 unknown 输入立即交接，不重发或更换调用标识；账号、认证、真实额度耗尽、身份、预算、人工暂停门禁都不能自行解除。
只用所给业务工具，不读取凭据、其它账号或宿主系统。中文向用户说明阶段；与 Claude 的自然语言交流及要求其回复均用英文，中文追加指南先理解再准确转述。
没有新变化时通过 claude_observe 的 wait_sec 等待，避免反复消耗模型。不能把只问一次问题当作完成冻结的多项需求。
'''


def _json(value) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def _schema(properties=None, required=None) -> dict:
    return {'type': 'object', 'properties': properties or {}, 'required': required or [], 'additionalProperties': False}


TOOLS = [
    {'name': 'account_state', 'description': '读取本账号真实轮次、预算、门禁和已投递状态。', 'parameters': _schema()},
    {'name': 'topic_read', 'description': '读取本轮冻结的原始题目和选定补充，不重新选题。', 'parameters': _schema()},
    {'name': 'claude_start', 'description': '创建或恢复本轮同一 Claude 原会话。', 'parameters': _schema()},
    {'name': 'claude_observe', 'description': '观察真实终端与原生回复，允许等待新变化。',
        'parameters': _schema({'wait_sec': {'type': 'integer', 'minimum': 0, 'maximum': 30}})},
    {'name': 'claude_input', 'description': '根据最新观察发送文本或菜单按键；未知输入禁止重发。',
        'parameters': _schema({'observation_id': {'type': 'string'}, 'text': {'type': 'string', 'maxLength': 24000},
            'keys': {'type': 'array', 'items': {'type': 'string', 'enum': sorted(KEYS)}, 'maxItems': 16},
            'submit': {'type': 'boolean'}}, ['observation_id'])},
    {'name': 'round_finish', 'description': '依据本轮实际主会话确认全部冻结需求已有正常回复，不接受自述完成。',
        'parameters': _schema({'summary': {'type': 'string', 'minLength': 1, 'maxLength': 12000}}, ['summary'])},
    {'name': 'account_wait', 'description': '有限等待真实变化，不绕过账号或人工门禁。',
        'parameters': _schema({'seconds': {'type': 'integer', 'minimum': 1, 'maximum': 30},
            'reason': {'type': 'string', 'maxLength': 300}}, ['seconds', 'reason'])},
]


class WarmupPiService:
    """管理原题库的独立养号轮次，正常计划仍由既有账号调度器唤醒。"""

    def __init__(self, data: Path, database, write_lock, terminal, account, admission, provider,
                 prepare_topic, next_run_at, *, identity=None, owners=None, pi=None) -> None:
        """登记依赖并只初始化自有表，不启用账号或启动模型。

        :param data: 私有持久数据根。
        :param database: 返回 sqlite3.Row 连接的工厂。
        :param write_lock: 与账号设置共用的写锁。
        :param terminal: WarmupTerminal 或隔离测试适配。
        :param account: 按 ID 读取完整可用账号。
        :param admission: 按账号及原轮次返回 allowed/retryable/retry_at/message。
        :param provider: 只在内存返回 Pi 模型配置。
        :param prepare_topic: 返回冻结 topic_id/topic_no/title/prompt/followups/settings/timing。
        :param next_run_at: 沿原账号随机间隔计算下一次时间。
        :param identity: 稳定账号身份回调。
        :param owners: 项目与养号共享的账号控制权。
        :param pi: 可注入的 Pi 运行时。
        :return: None。
        """
        self.data, self.database, self.write_lock = Path(data), database, write_lock
        self.terminal, self.account, self.admission = terminal, account, admission
        self.provider, self.prepare_topic, self.next_run_at = provider, prepare_topic, next_run_at
        self.identity = identity or (lambda value: _json({'id': value['id'], 'binding': value.get('cc2api_account_id')}))
        self.owners, self.pi = owners or AccountPiOwners(), pi or ProjectsPi()
        self.lock, self.controllers, self.owner_tokens, self.closed = threading.RLock(), {}, {}, False
        connection = database()
        try:
            with write_lock, connection:
                connection.executescript(SCHEMA)
        finally:
            connection.close()

    def _rows(self, sql, parameters=()):
        connection = self.database()
        try:
            return [dict(row) for row in connection.execute(sql, parameters)]
        finally:
            connection.close()

    def _one(self, sql, parameters=()):
        rows = self._rows(sql, parameters)
        return rows[0] if rows else None

    def _write(self, sql, parameters=()):
        with self.write_lock:
            connection = self.database()
            try:
                with connection:
                    return connection.execute(sql, parameters).rowcount
            finally:
                connection.close()

    def _event(self, aid, kind, payload, round_id=None, key=None):
        self._write('INSERT OR IGNORE INTO warmup_pi_events(account_id,round_id,kind,payload_json,event_key,created_at) VALUES(?,?,?,?,?,?)',
            (aid, round_id, kind, _json(payload), key, time.time()))

    def _ensure(self, aid):
        self._write('INSERT OR IGNORE INTO warmup_pi_agents(account_id,updated_at) VALUES(?,?)', (aid, time.time()))
        return self._one('SELECT * FROM warmup_pi_agents WHERE account_id=?', (aid,))

    def _round(self, agent):
        return self._one('SELECT * FROM warmup_pi_rounds WHERE id=? AND account_id=?',
            (agent['current_round_id'], agent['account_id'])) if agent.get('current_round_id') else None

    def _elapsed(self, row):
        return row['work_sec'] + (max(0, time.time() - row['segment_started_at']) if row.get('segment_started_at') else 0)

    def _current(self, aid, generation):
        agent = self._one('SELECT * FROM warmup_pi_agents WHERE account_id=?', (aid,))
        account = self.account(aid)
        controller = self.controllers.get(aid)
        claimed = bool(controller and not controller[1].is_set() and agent and agent['generation'] == generation)
        if (self.closed or not agent or agent['generation'] != generation or not account
                or not account.get('warmup_enabled') and not claimed):
            raise ValueError('养号控制已暂停、账号不可用或代次已失效')
        row = self._round(agent)
        if row and row['account_identity'] != self.identity(account):
            raise ValueError('养号原账号身份已变化，保留原会话等待核对')
        return agent, row

    def _state(self, aid, generation, status, message, next_at, *, reason=None, account_status=None):
        with self.write_lock:
            connection = self.database()
            try:
                with connection:
                    changed = connection.execute('UPDATE warmup_pi_agents SET status=?,message=?,last_reason=?,retry_at=?,updated_at=? '
                        'WHERE account_id=? AND generation=?', (status, message, reason,
                            next_at if status == 'waiting' else None, time.time(), aid, generation)).rowcount
                    if changed:
                        connection.execute('UPDATE accounts SET warmup_next_run_at=CASE WHEN warmup_enabled=1 THEN ? ELSE NULL END,'
                            'warmup_last_status=?,warmup_last_error=? WHERE id=?', (next_at, account_status or status,
                                None if account_status == 'success' else message, aid))
            finally:
                connection.close()

    def has_taken_over(self, account_id: int, *, connection=None) -> bool:
        """仅实际认领过新轮次后屏蔽旧回调，支持调用者已有事务。:param account_id: 账号。:param connection: 已有连接，传入时不另加锁。:return: 是否已切入 Pi。"""
        row = connection.execute('SELECT managed FROM warmup_pi_agents WHERE account_id=?', (account_id,)).fetchone() if connection else self._one(
            'SELECT managed FROM warmup_pi_agents WHERE account_id=?', (account_id,))
        return bool(row and row['managed'])

    def configure(self, account_id: int, instructions: str = '', budget_sec: int = 1800) -> dict:
        """保存追加指南和预算，不修改原养号开关、间隔或下一次时间。:param account_id: 账号。:param instructions: 原文指南。:param budget_sec: 累计预算。:return: 公开状态。"""
        if (not self.account(account_id) or not isinstance(instructions, str) or len(instructions) > 12000
                or type(budget_sec) is not int or not 60 <= budget_sec <= 86400):
            raise ValueError('养号指南或预算配置不合法')
        with self.lock:
            if account_id in self.controllers:
                raise ValueError('请先暂停该账号 Pi，再修改养号指南或预算')
            self._ensure(account_id)
            self._write('UPDATE warmup_pi_agents SET instructions=?,budget_sec=?,updated_at=? WHERE account_id=?',
                (instructions, budget_sec, time.time(), account_id))
        return self.view(account_id)

    def _guard(self, agent, row, *, manual=False):
        account = self.account(agent['account_id'])
        controller = self.controllers.get(agent['account_id'])
        claimed = bool(controller and not controller[1].is_set() and row and row['generation'] == agent['generation'])
        if not account or not account.get('warmup_enabled') and not claimed:
            return {'allowed': False, 'retryable': False, 'reason': 'paused', 'message': '账号养号计划未开启'}
        if self.actions(agent['account_id']):
            return {'allowed': False, 'retryable': False, 'reason': 'unknown_input', 'message': '有未核对的原会话输入，不能重复发送'}
        if row and row['status'] not in ('completed', 'stopped'):
            if row['account_identity'] != self.identity(account):
                return {'allowed': False, 'retryable': False, 'reason': 'identity', 'message': '原轮次账号身份已变化'}
            if self._elapsed(row) >= agent['budget_sec']:
                return {'allowed': False, 'retryable': False, 'reason': 'budget', 'message': '原轮次累计预算已用尽，恢复不会清零'}
            if row['status'] == 'blocked' and not (manual and agent['last_reason'] in
                    ('model_unavailable', 'provider_conflict', 'provider_content_filter', 'budget')):
                return {'allowed': False, 'retryable': False, 'reason': agent['last_reason'] or 'blocked',
                    'message': agent['message'] or row['message'] or '原轮次需要人工核对'}
        return self._admit(account, row)

    def _admit(self, account, row):
        """执行条件暂不可读时只等待，不能借异常放行或泄漏内部错误。"""
        try:
            return self.admission(account, row)
        except Exception:
            return {'allowed': False, 'retryable': True, 'reason': 'admission', 'message': '养号执行条件暂不可核对，保留原轮次等待'}

    def _wait(self, agent, row, gate):
        retryable = bool(gate.get('retryable'))
        if row and row['runtime_json']:
            try:
                self._release(row, 'paused' if retryable else 'blocked')
            except ValueError:
                self._state(agent['account_id'], agent['generation'], 'blocked',
                    '终端停止尚未确认，原会话定位已保留', None, reason='runtime_stop')
                raise
            token = self.owner_tokens.get(agent['account_id'])
            if token:
                self._release_owner(agent['account_id'], token)
        now = time.time()
        next_at = max(now + 60, gate.get('retry_at') or 0, agent.get('retry_at') or 0) if retryable else None
        self._state(agent['account_id'], agent['generation'], 'waiting' if retryable else 'blocked',
            gate.get('message') or '等待养号执行条件', next_at, reason=gate.get('reason'),
            account_status='quota_wait' if gate.get('reason') == 'quota' else None)
        self._event(agent['account_id'], 'gate_wait', {key: gate.get(key) for key in
            ('reason', 'message', 'retryable', 'retry_at')}, row['id'] if row else None)

    def start(self, account_id: int, *, scheduled: bool = False, now: float | None = None) -> dict:
        """认领同账号唯一 Pi；未开启的养号账号不会被隐式启用。:param account_id: 账号。:param scheduled: 是否要求到期。:param now: 调度时刻。:return: 公开状态。"""
        with self.lock:
            if self.closed:
                raise ValueError('养号服务正在退出')
            if account_id in self.controllers:
                return self.view(account_id)
            account = self.account(account_id)
            if not account or not account.get('warmup_enabled'):
                raise ValueError('请先开启该账号的养号计划')
            now = time.time() if now is None else now
            if scheduled and (account.get('warmup_next_run_at') is None or account['warmup_next_run_at'] > now):
                return self.view(account_id)
            agent = self._ensure(account_id)
            row = self._round(agent)
            if scheduled and agent.get('retry_at') and agent['retry_at'] > now:
                self._state(account_id, agent['generation'], 'waiting', agent['message'], agent['retry_at'], reason=agent['last_reason'])
                return self.view(account_id)
            gate = self._guard(agent, row, manual=not scheduled)
            if not gate['allowed']:
                self._wait(agent, row, gate)
                return self.view(account_id)
            configuration = self.provider()
            if not configuration or not self.pi.available():
                raise ValueError('Pi 运行时或模型配置尚未就绪')
            generation = agent['generation'] + 1
            token = self.owners.claim(account_id, 'warmup', generation)
            if token is None:
                self._wait(agent, row, {'allowed': False, 'retryable': True, 'reason': 'busy', 'message': '账号已有其它 Pi 或执行，稍后再检查'})
                return self.view(account_id)
            self.owner_tokens[account_id] = token
            try:
                creating = not row or row['status'] in ('completed', 'stopped')
                if creating:
                    topic = self._validate_topic(self.prepare_topic(account))
                    identifier = uuid.uuid4().hex
                else:
                    identifier = row['id']
                    if row['runtime_json']:
                        raise ValueError('原轮次执行尚未收口，不能启动第二个终端')
                # 冻结轮次、接管标记和账号状态必须一起提交，不能留下没有控制者的半轮次。
                with self.write_lock:
                    connection = self.database()
                    try:
                        with connection:
                            current = connection.execute('SELECT * FROM accounts WHERE id=?', (account_id,)).fetchone()
                            if (not current or not current['enabled'] or current['deleted_at'] is not None
                                    or not current['warmup_enabled'] or self.identity(dict(current)) != self.identity(account)):
                                raise ValueError('账号配置已变化，本轮尚未启动')
                            if creating:
                                connection.execute('INSERT INTO warmup_pi_rounds(id,account_id,generation,topic_id,topic_no,title,topic_json,settings_json,'
                                    'account_identity,status,session_id,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',
                                    (identifier, account_id, generation, topic['topic_id'], topic['topic_no'], topic['title'], _json(topic),
                                        _json(topic['settings']), self.identity(account), 'ready', str(uuid.uuid4()), now))
                            else:
                                connection.execute("UPDATE warmup_pi_rounds SET generation=?,status='paused',message=NULL WHERE id=?",
                                    (generation, identifier))
                            connection.execute("UPDATE warmup_pi_agents SET generation=?,managed=1,status='running',current_round_id=?,message=NULL,"
                                'last_reason=NULL,recovery_count=CASE WHEN ? THEN recovery_count ELSE 0 END,recovery_phase=CASE WHEN ? THEN recovery_phase ELSE NULL END,'
                                'retry_at=NULL,updated_at=? WHERE account_id=?', (generation, identifier, scheduled, scheduled, now, account_id))
                            connection.execute("UPDATE accounts SET warmup_next_run_at=NULL,warmup_last_attempt_at=?,warmup_last_status='running',warmup_last_error=NULL "
                                'WHERE id=?', (now, account_id))
                    finally:
                        connection.close()
                stop = threading.Event()
                thread = threading.Thread(target=self._run, args=(account_id, generation, configuration, stop, token), daemon=True)
                self.controllers[account_id] = (thread, stop, token)
                if row and row['status'] == 'blocked':
                    self._event(account_id, 'manual_retry', {'reason': agent['last_reason'], 'generation': generation}, row['id'])
                try:
                    thread.start()
                except Exception:
                    self.controllers.pop(account_id, None)
                    self._write("UPDATE warmup_pi_rounds SET status='paused' WHERE id=?", (identifier,))
                    self._state(account_id, generation, 'blocked', 'Pi 养号控制线程未能启动，原轮次已保留', None, reason='controller')
                    raise ValueError('Pi 养号控制线程未能启动，原轮次已保留') from None
            except BaseException:
                self.controllers.pop(account_id, None)
                self.owners.release(account_id, token)
                if self.owner_tokens.get(account_id) == token:
                    self.owner_tokens.pop(account_id, None)
                raise
        return self.view(account_id)

    @staticmethod
    def _validate_topic(topic):
        if (not isinstance(topic, dict) or type(topic.get('topic_id')) is not int or type(topic.get('topic_no')) is not int
                or not isinstance(topic.get('title'), str) or not topic['title'].strip()
                or not isinstance(topic.get('prompt'), str) or not topic['prompt'].strip() or len(topic['prompt']) > 24000
                or not isinstance(topic.get('settings'), dict) or not isinstance(topic.get('timing', {}), dict)):
            raise ValueError('冻结题目定义不合法')
        validate_followups(topic.get('followups', []))
        for name in ('claude_code_version', 'claude_effort_level'):
            if not isinstance(topic['settings'].get(name), str) or not topic['settings'][name]:
                raise ValueError('冻结题目缺少实际 Claude 设置')
        return {**topic, 'followups': validate_followups(topic.get('followups', [])), 'timing': topic.get('timing', {})}

    def tick(self, now: float | None = None) -> None:
        """供既有 WarmupScheduler 调用，不创建第二个正常计划线程。:param now: 扫描时刻。:return: None。"""
        now = time.time() if now is None else now
        for row in self._rows('SELECT a.id FROM accounts a JOIN warmup_pi_agents p ON p.account_id=a.id '
                'WHERE p.managed=1 AND a.enabled=1 AND a.deleted_at IS NULL AND a.warmup_enabled=1 '
                'AND a.warmup_next_run_at IS NOT NULL AND a.warmup_next_run_at<=?', (now,)):
            try:
                self.start(row['id'], scheduled=True, now=now)
            except ValueError:
                continue

    def _recover_model(self, agent, row, retry_at):
        gate = self._guard(agent, row)
        if not gate['allowed'] and not gate.get('retryable'):
            self._wait(agent, row, gate)
            return
        account = self.account(agent['account_id'])
        if not account or not account.get('warmup_enabled'):
            self._state(agent['account_id'], agent['generation'], 'paused', '自动计划已关闭，原轮次已保留', None,
                reason='model_unavailable')
            return
        count, now = agent['recovery_count'], time.time()
        if count < 3:
            delay, count, phase = (60, 120, 300)[count], count + 1, 'scheduled'
        else:
            delay, phase = max(900, self.next_run_at(account) - now), 'exhausted'
        due = max(now + delay, retry_at or 0, gate.get('retry_at') or 0)
        message = f'Pi 模型暂不可用，第 {count}/3 轮恢复等待中' if phase == 'scheduled' else 'Pi 模型持续不可用，已按原计划转为低频自动检查'
        self._write('UPDATE warmup_pi_agents SET recovery_count=?,recovery_phase=? WHERE account_id=? AND generation=?',
            (count, phase, agent['account_id'], agent['generation']))
        self._state(agent['account_id'], agent['generation'], 'waiting', message, due, reason='model_unavailable')
        self._event(agent['account_id'], 'recovery', {'phase': phase, 'attempt': count, 'retry_at': due,
            'reason': 'model_unavailable', 'message': message, 'source': 'schedule'}, row['id'])

    def _run(self, aid, generation, configuration, stop, token):
        failure = {}
        outcome = 'error'
        try:
            agent, row = self._current(aid, generation)
            directory = self.data / 'warmup-pi/agents' / str(aid)
            directory.mkdir(parents=True, exist_ok=True, mode=0o700)
            if directory.is_symlink():
                raise ValueError('Pi 养号会话目录不能是链接')
            config = {**configuration, 'session_dir': str(directory), 'session_file': agent['session_file'], 'tools': TOOLS,
                'timeout_sec': max(1, int(agent['budget_sec'] - self._elapsed(row))),
                'instructions': GUIDE + '\n用户追加业务指南：\n' + agent['instructions'],
                'prompt': '继续本账号的冻结题库养号轮次。先读取account_state和topic_read，观察原会话，不能重复已投递需求。'}
            self._event(aid, 'guide_loaded', {'generation': generation,
                'user_guide_sha256': hashlib.sha256(agent['instructions'].encode()).hexdigest(),
                'system_prompt_sha256': hashlib.sha256(config['instructions'].encode()).hexdigest()}, row['id'])

            def receive(value):
                if value.get('type') == 'error':
                    failure.update(value)
                self._pi_event(aid, generation, value)

            outcome = self.pi.run(config, lambda name, args, call_id: self.tool(aid, generation, name, args, call_id, stop),
                receive, stop, config['timeout_sec'])
        except Exception:
            failure = {'message': 'Pi 养号控制器异常，原会话及未确认输入已保留'}
        finally:
            with self.lock:
                try:
                    agent = self._one('SELECT * FROM warmup_pi_agents WHERE account_id=?', (aid,))
                    if agent and agent['generation'] == generation:
                        row = self._round(agent)
                        if row['runtime_json']:
                            self._release(row, 'blocked' if row['status'] == 'blocked' or self.actions(aid) else 'paused')
                        row = self._round(agent)
                        if not self.closed and not stop.is_set() and row['status'] not in ('completed', 'stopped'):
                            reason = failure.get('reason')
                            if outcome == 'error' and reason == 'model_unavailable':
                                retry_at = failure.get('retry_at')
                                valid = type(retry_at) in (int, float) and time.time() < retry_at < time.time() + 86400
                                self._recover_model(agent, row, retry_at if valid else None)
                            else:
                                message = failure.get('message') or ('本轮累计预算已用尽' if outcome == 'timeout' else 'Pi 结束但本轮原生完成证据尚未满足')
                                self._write("UPDATE warmup_pi_rounds SET status='blocked',message=? WHERE id=?", (message[:1000], row['id']))
                                self._state(aid, generation, 'blocked', message[:1000], None,
                                    reason='budget' if outcome == 'timeout' else reason if reason in ('provider_conflict', 'provider_content_filter') else None)
                except Exception:
                    self._state(aid, generation, 'blocked', '养号收尾未确认，保留原现场等待核对', None, reason='runtime_stop')
                finally:
                    current = self.controllers.get(aid)
                    if current and current[2] == token:
                        self.controllers.pop(aid, None)
                    self._release_owner(aid, token)

    def _pi_event(self, aid, generation, value):
        agent, row = self._current(aid, generation)
        kind = value.get('type')
        if kind == 'ready':
            directory = self.data / 'warmup-pi/agents' / str(aid)
            path = Path(value['session_file'])
            if not path.is_absolute() or path.is_symlink() or not path.resolve().is_relative_to(directory.resolve()):
                raise ValueError('Pi 养号会话路径越界')
            self._write('UPDATE warmup_pi_agents SET session_file=? WHERE account_id=? AND generation=?', (str(path), aid, generation))
        elif kind == 'assistant':
            self._event(aid, 'usage', {'model': value.get('model'), 'usage': value.get('usage')}, row['id'],
                'pi:' + str(aid) + ':' + str(value['message_id']))
            if value.get('text'):
                self._event(aid, 'pi', {'text': str(value['text'])[:24000], 'model': value.get('model')}, row['id'])
        elif kind == 'error':
            payload = {'message': str(value.get('message') or 'Pi 模型请求失败')[:1000]}
            if value.get('reason') in ('model_unavailable', 'provider_conflict', 'provider_content_filter'):
                payload.update(reason=value['reason'], generation=generation)
                retry_at = value.get('retry_at')
                now = time.time()
                if value['reason'] == 'model_unavailable' and type(retry_at) in (int, float) and now < retry_at < now + 86400:
                    payload['retry_at'] = retry_at
            self._event(aid, 'error', payload, row['id'])
        elif kind == 'recovery':
            if (value.get('phase') not in ('retry', 'fallback', 'recovered') or value.get('reason') != 'transient'
                    or type(value.get('attempt')) is not int or not 1 <= value['attempt'] <= 8
                    or type(value.get('delay_ms')) is not int or not 0 <= value['delay_ms'] <= 15000
                    or not isinstance(value.get('model'), str) or not 1 <= len(value['model']) <= 200 or not value['model'].isprintable()):
                return
            self._event(aid, 'recovery', {key: value[key] for key in ('phase', 'attempt', 'delay_ms', 'model', 'reason')}, row['id'])

    def tool(self, account_id: int, generation: int, name: str, args: dict, call_id: str, stop=None) -> dict:
        """执行冻结账号的工具，不允许模型自行换账号或绕过操作意图。:param account_id: 绑定账号。:param generation: 绑定代次。:param name: 工具名。:param args: 工具参数。:param call_id: 原工具标识。:param stop: 取消信号。:return: 真实执行结果。"""
        try:
            if not isinstance(args, dict) or not isinstance(call_id, str) or not call_id or len(call_id) > 2000:
                raise ValueError('养号工具调用不合法')
            with self.lock:
                agent, row = self._current(account_id, generation)
                if stop and stop.is_set():
                    raise ValueError('养号控制已取消')
                if name == 'account_state':
                    return self.view(account_id)['agents'][0]
                if name == 'topic_read':
                    topic = json.loads(row['topic_json'])
                    return {key: topic[key] for key in ('topic_id', 'topic_no', 'title', 'prompt', 'followups')} | {'round_id': row['id']}
                if row['status'] in ('completed', 'stopped'):
                    return {'status': row['status'], 'round_id': row['id'], 'message': '本轮已结束，等待原计划下一轮'}
                gate = self._guard(agent, row)
                if not gate['allowed']:
                    self._wait(agent, row, gate)
                    if stop:
                        stop.set()
                    return {'status': 'waiting' if gate.get('retryable') else 'blocked', 'message': gate.get('message')}
                if name == 'claude_start':
                    return self._start_claude(agent, row)
                if name == 'claude_input':
                    return self._input(agent, row, args, call_id)
                if name == 'round_finish':
                    return self._finish(agent, row, args.get('summary'))
                if name not in ('claude_observe', 'account_wait'):
                    raise ValueError('未知养号工具')
            wait = args.get('wait_sec', 0) if name == 'claude_observe' else args.get('seconds', 1)
            if type(wait) is not int or not 0 <= wait <= 30:
                raise ValueError('观察等待须为0到30秒整数')
            if wait and stop:
                stop.wait(wait)
            elif wait:
                time.sleep(wait)
            with self.lock:
                agent, row = self._current(account_id, generation)
                if stop and stop.is_set():
                    raise ValueError('养号控制已取消')
                if name == 'account_wait':
                    return {'status': 'waiting', 'message': '已等待，继续读取真实账号和会话状态'}
                return self._observe(row)
        except (ValueError, OSError, KeyError, TypeError) as error:
            return {'status': 'rejected', 'message': str(error)[:1000]}

    def _start_claude(self, agent, row):
        if row['runtime_json']:
            return {'status': 'running', 'round_id': row['id'], 'session_id': row['session_id'], 'resumed': True}
        remaining = int(agent['budget_sec'] - self._elapsed(row))
        if remaining <= 0:
            raise ValueError('养号轮次累计预算已用尽')
        observed = json.loads(row['observation_json']) if row['observation_json'] else {}
        evidence = json.loads(row['evidence_json']) if row['evidence_json'] else {}
        sent = self._one("SELECT id FROM warmup_pi_actions WHERE round_id=? AND status!='not_sent' LIMIT 1", (row['id'],))
        # 只启动过空 CLI 不代表已有主会话；一旦有输入意图或原生证据，缺少原 JSONL 就必须停。
        required = bool(sent or observed.get('cursor', 0) > 0 or evidence.get('completed_stages', 0) > 0)
        runtime = self.terminal.start(self.account(agent['account_id']), {**row, 'remaining_sec': remaining,
            'resume_required': required})
        now = time.time()
        self._write("UPDATE warmup_pi_rounds SET runtime_json=?,status='running',started_at=COALESCE(started_at,?),segment_started_at=? WHERE id=?",
            (_json(runtime), now, now, row['id']))
        self._event(agent['account_id'], 'started', {'session_id': row['session_id'], 'resumed': bool(row['started_at'])}, row['id'])
        return {'status': 'running', 'round_id': row['id'], 'session_id': row['session_id'], 'resumed': bool(row['started_at'])}

    def _observe(self, row):
        if not row['runtime_json']:
            raise ValueError('请先创建或恢复本轮 Claude 会话')
        previous = json.loads(row['observation_json']) if row['observation_json'] else {}
        self.terminal.passive_status(row)
        observed = self.terminal.observe(row, previous.get('cursor', 0))
        proof = self._proof(row, require_complete=False)
        self._write('UPDATE warmup_pi_rounds SET evidence_json=? WHERE id=?', (_json(proof), row['id']))
        identifier = uuid.uuid4().hex
        self._write('UPDATE warmup_pi_rounds SET observation_json=?,observation_id=? WHERE id=?', (_json(observed), identifier, row['id']))
        self._event(row['account_id'], 'observation', observed, row['id'])
        return {'observation_id': identifier, **observed}

    def _input(self, agent, row, args, call_id):
        operation = hashlib.sha256((row['id'] + ':' + call_id).encode()).hexdigest()
        existing = self._one('SELECT * FROM warmup_pi_actions WHERE id=? AND round_id=?', (operation, row['id']))
        if existing:
            if json.loads(existing['request_json']) != args:
                raise ValueError('同一操作标识的输入内容发生变化')
            return {'status': existing['status'], 'operation_id': operation, 'replayed': True,
                'reconcile_required': existing['status'] in ('intent', 'unknown')}
        if not row['runtime_json'] or args.get('observation_id') != row['observation_id']:
            raise ValueError('终端观察已过期，请重新观察')
        observed = json.loads(row['observation_json'])
        if not observed.get('terminal_ready', True):
            raise ValueError('Claude 终端尚未就绪')
        text, keys = args.get('text', ''), args.get('keys', [])
        submit = args.get('submit', bool(text))
        if (not isinstance(text, str) or len(text.encode()) > 48000 or not isinstance(keys, list) or len(keys) > 16
                or any(not isinstance(key, str) or key not in KEYS for key in keys) or type(submit) is not bool or not text and not keys):
            raise ValueError('养号终端输入参数不合法')
        topic = json.loads(row['topic_json'])
        planned = [topic['prompt'], *topic['followups']]
        for old in self._rows("SELECT * FROM warmup_pi_actions WHERE round_id=? AND status='sent' ORDER BY created_at", (row['id'],)):
            request = json.loads(old['request_json'])
            if text and request.get('text') == text and (old['generation'] != row['generation'] or text in planned):
                return {'status': 'sent', 'operation_id': old['id'], 'replayed': True, 'message': '该内容已投递，请观察消费结果，不重复发送'}
        self._write('INSERT INTO warmup_pi_actions(id,round_id,generation,tool_call_id,request_json,status,created_at) VALUES(?,?,?,?,?,?,?)',
            (operation, row['id'], row['generation'], call_id, _json(args), 'intent', time.time()))
        try:
            self.terminal.send(row, operation, text, keys, submit)
        except Exception:
            self._write("UPDATE warmup_pi_actions SET status='unknown',error=? WHERE id=?", ('原生投递结果未知，禁止自动重发', operation))
            self._write("UPDATE warmup_pi_rounds SET status='blocked',message=? WHERE id=?", ('终端输入未知，需要核对', row['id']))
            self._state(row['account_id'], row['generation'], 'blocked', '终端输入未知，需要核对', None, reason='unknown_input')
            self._event(row['account_id'], 'input_unknown', {'operation_id': operation}, row['id'])
            return {'status': 'unknown', 'operation_id': operation, 'reconcile_required': True}
        self._write("UPDATE warmup_pi_actions SET status='sent',ended_at=? WHERE id=?", (time.time(), operation))
        self._write('UPDATE warmup_pi_rounds SET observation_id=NULL WHERE id=?', (row['id'],))
        self._event(row['account_id'], 'input', {'operation_id': operation, 'text': text, 'keys': keys, 'submit': submit}, row['id'])
        return {'status': 'sent', 'operation_id': operation, 'message': '已投递，请继续观察真实消费与回复'}

    def _proof(self, row, *, require_complete=True):
        if not row['runtime_json']:
            raise ValueError('尚未启动本轮原生会话')
        messages = self.terminal.dialogue(row)
        topic = json.loads(row['topic_json'])
        requests = [json.loads(item['request_json']) for item in self._rows(
            "SELECT request_json FROM warmup_pi_actions WHERE round_id=? AND status='sent' ORDER BY created_at,id", (row['id'],))]
        receipts = [request.get('text', '') for request in requests]
        result, last_index = [], -1
        planned = [topic['prompt'], *topic['followups']]
        for expected in planned:
            if not any(matches_topic_input(text, expected) for text in receipts):
                if require_complete:
                    raise ValueError('仍有冻结需求缺少已确认的输入投递')
                break
            inputs = [(index, item) for index, item in enumerate(messages) if item.get('role') == 'user'
                and item.get('normal') and isinstance(item.get('text'), str) and matches_topic_input(item['text'], expected)]
            if len(inputs) != 1 or inputs[0][0] <= last_index:
                if require_complete:
                    raise ValueError('冻结需求尚未实际消费、重复出现或顺序不符')
                break
            index, sent = inputs[0]
            if not sent.get('id'):
                if require_complete:
                    raise ValueError('原生输入缺少可追溯标识')
                break
            reply = self._reply_after(messages, index)
            if not reply:
                if require_complete:
                    raise ValueError('冻结需求还没有后续正常主会话回复，排队或错误消息不能算完成')
                break
            result.append({'input_id': sent['id'], 'input_key': sent['key'], 'reply_id': reply['id'],
                'reply_key': reply['key'], 'input_sha256': hashlib.sha256(expected.encode()).hexdigest()})
            last_index = index
        meaningful = [item for item in messages if item.get('role') in ('user', 'assistant')]
        if require_complete:
            if (not meaningful or meaningful[-1].get('role') != 'assistant'
                    or not meaningful[-1].get('normal') or not meaningful[-1].get('text')):
                raise ValueError('原生会话仍有未答输入、工具或异常，不能收尾')
            # 除冻结需求外，Pi 自主提交的澄清也必须实际消费；队列回执不能让它提前停止终端。
            previous = -1
            for request in requests:
                text = request.get('text', '')
                if not text:
                    continue
                match = next((index for index in range(previous + 1, len(messages))
                    if messages[index].get('role') == 'user' and messages[index].get('normal')
                    and isinstance(messages[index].get('text'), str) and matches_topic_input(messages[index]['text'], text)), None)
                if match is None or not self._reply_after(messages, match):
                    raise ValueError('已提交的澄清仍未实际消费或没有正常回复，不能提前结束')
                previous = match
        return {'session_id': row['session_id'], 'completed_stages': len(result), 'required_stages': len(planned), 'stages': result}

    @staticmethod
    def _reply_after(messages, index):
        """沿实际父链查找正常文本回复，工具、合成错误和无标识消息不能作答复证据。"""
        descendants, reply = {messages[index]['key']}, None
        for item in messages[index + 1:]:
            if item.get('parent_key') in descendants:
                descendants.add(item['key'])
                if item.get('role') == 'assistant' and item.get('normal') and item.get('text') and item.get('id'):
                    reply = item
        return reply

    def _finish(self, agent, row, summary):
        if not isinstance(summary, str) or not 1 <= len(summary) <= 12000:
            raise ValueError('养号收尾说明不合法')
        proof = self._proof(row)
        self._release(row, 'completed')
        self._write('UPDATE warmup_pi_rounds SET evidence_json=?,message=? WHERE id=?', (_json(proof), summary, row['id']))
        self._write('UPDATE warmup_pi_agents SET recovery_count=0,recovery_phase=NULL WHERE account_id=?', (row['account_id'],))
        account = self.account(row['account_id'])
        due = self.next_run_at(account) if account and account.get('warmup_enabled') else None
        self._state(row['account_id'], row['generation'], 'paused', '本轮题目已完成，按原间隔等待下一轮', due, account_status='success')
        self._event(row['account_id'], 'completed', {'summary': summary, **proof}, row['id'])
        return {'status': 'completed', 'round_id': row['id'], **proof}

    def _release(self, row, status):
        current = self._one('SELECT * FROM warmup_pi_rounds WHERE id=?', (row['id'],))
        usage = json.loads(current['claude_usage_json']) if current['claude_usage_json'] else {}
        if current['runtime_json']:
            try:
                usage = self.terminal.usage(current)
            except Exception:
                # 统计是可缺失的旁路，不能阻止人工停止真实终端。
                usage = {**usage, 'complete': False}
            try:
                result = self.terminal.control(current, 'stop')
                if not isinstance(result, dict) or result.get('stopped') is not True:
                    raise ValueError('终端未确认停止')
            except Exception:
                # 停止结果未知时保留定位和计时段，并继续持有账号租约，禁止第二个 Pi 写入。
                self._write("UPDATE warmup_pi_rounds SET status='blocked',message=?,claude_usage_json=? WHERE id=?",
                    ('终端停止尚未确认，原会话定位已保留', _json({**usage, 'complete': False}), current['id']))
                raise ValueError('终端停止尚未确认，原会话定位已保留') from None
        elapsed = self._elapsed(current)
        self._write('UPDATE warmup_pi_rounds SET status=?,runtime_json=NULL,segment_started_at=NULL,observation_id=NULL,work_sec=?,'
            'claude_usage_json=?,ended_at=? WHERE id=?', (status, elapsed, _json(usage),
                time.time() if status in ('completed', 'stopped') else None, row['id']))

    def _release_owner(self, aid, token):
        """仅控制线程退出且原生终端已确认收口后归还同一账号租约。"""
        try:
            agent = self._one('SELECT * FROM warmup_pi_agents WHERE account_id=?', (aid,))
            row = self._round(agent) if agent else None
            if aid in self.controllers or row and row['runtime_json']:
                return
            self.owners.release(aid, token)
            if self.owner_tokens.get(aid) == token:
                self.owner_tokens.pop(aid, None)
        except Exception:
            # 无法证明已经停止时宁可保留租约，等待下一次显式停止或启动时的运行时对账。
            return

    def pause(self, account_id: int, *, stop_round: bool = False, disable_schedule: bool = True) -> dict:
        """撤销当前控制并保留原会话，人工暂停同时关闭原账号养号计划。:param account_id: 账号。:param stop_round: 是否结束轮次。:param disable_schedule: 是否关闭计划。:return: 公开状态。"""
        with self.lock:
            agent = self._one('SELECT * FROM warmup_pi_agents WHERE account_id=?', (account_id,))
            if not agent:
                if disable_schedule:
                    self._write("UPDATE accounts SET warmup_enabled=0,warmup_next_run_at=NULL,warmup_last_status='paused' WHERE id=?", (account_id,))
                return self.view(account_id)
            controller = self.controllers.get(account_id)
            if controller:
                controller[1].set()
            row = self._round(agent)
            # 先撤销调度和原代次，再执行可能失败的外部停止，避免异常留下未来付费计划。
            with self.write_lock:
                connection = self.database()
                try:
                    with connection:
                        connection.execute("UPDATE warmup_pi_agents SET generation=generation+1,status='paused',message=?,retry_at=NULL,updated_at=? WHERE account_id=?",
                            ('人工暂停，原会话和累计工作已保留', time.time(), account_id))
                        connection.execute('UPDATE accounts SET warmup_enabled=CASE WHEN ? THEN 0 ELSE warmup_enabled END,'
                            "warmup_next_run_at=NULL,warmup_last_status='paused',warmup_last_error=NULL WHERE id=?", (disable_schedule, account_id))
                finally:
                    connection.close()
            try:
                if row and row['status'] not in ('completed', 'stopped'):
                    self._release(row, 'stopped' if stop_round else 'paused')
            except Exception:
                self._state(account_id, agent['generation'] + 1, 'blocked', '终端停止尚未确认，原会话定位已保留', None, reason='runtime_stop')
                raise ValueError('终端停止尚未确认，原会话定位已保留') from None
            token = self.owner_tokens.get(account_id)
            if token:
                self._release_owner(account_id, token)
        return self.view(account_id)

    def recover(self) -> None:
        """在账号运行时已对账后恢复持久等待，不启用任何关闭的养号账号。:return: None。"""
        for agent in self._rows('SELECT * FROM warmup_pi_agents'):
            account = self.account(agent['account_id'])
            row = self._round(agent)
            if row and row['runtime_json']:
                elapsed = min(agent['budget_sec'], self._elapsed(row))
                self._write("UPDATE warmup_pi_rounds SET runtime_json=NULL,segment_started_at=NULL,observation_id=NULL,work_sec=?,status=? WHERE id=?",
                    (elapsed, 'blocked' if self.actions(agent['account_id']) or row['status'] == 'blocked' else 'paused', row['id']))
            self._write('UPDATE warmup_pi_agents SET generation=generation+1,updated_at=? WHERE account_id=?', (time.time(), agent['account_id']))
            updated = self._one('SELECT * FROM warmup_pi_agents WHERE account_id=?', (agent['account_id'],))
            if not account or not account.get('warmup_enabled') or not agent['managed']:
                continue
            row = self._round(updated)
            gate = self._guard(updated, row)
            if not gate['allowed']:
                self._wait(updated, row, gate)
            elif row and row['status'] not in ('completed', 'stopped'):
                due = max(time.time() + 1, agent.get('retry_at') or 0, account.get('warmup_next_run_at') or 0)
                self._state(agent['account_id'], updated['generation'], 'waiting', '服务已恢复，等待继续原养号会话', due,
                    reason=agent['last_reason'])

    def close(self) -> None:
        """停止当前服务的控制进程，保留原账号开关和未完成轮次。:return: None。"""
        self.closed = True
        controllers = list(self.controllers.items())
        for _, (_, stop, _) in controllers:
            stop.set()
        for aid in set(self.owner_tokens) | {aid for aid, _ in controllers}:
            with self.lock:
                try:
                    agent = self._one('SELECT * FROM warmup_pi_agents WHERE account_id=?', (aid,))
                    row = self._round(agent)
                    if row and row['runtime_json']:
                        self._release(row, 'paused')
                    account = self.account(aid)
                    if (account and account.get('warmup_enabled') and row and row['status'] not in ('completed', 'stopped', 'blocked')
                            and agent['status'] != 'blocked' and not self.actions(aid)):
                        self._state(aid, agent['generation'], 'waiting', '服务退出，原养号会话已保留',
                            max(time.time() + 1, agent.get('retry_at') or 0), reason=agent['last_reason'])
                    token = self.owner_tokens.get(aid)
                    if token:
                        self._release_owner(aid, token)
                except Exception:
                    # 单账号的 Docker 或统计故障不能跳过其它账号的停止。
                    try:
                        self._state(aid, agent['generation'], 'blocked', '服务退出时终端停止未确认，原定位已保留', None, reason='runtime_stop')
                    except Exception:
                        continue
        for _, (thread, _, _) in controllers:
            thread.join(timeout=5)

    def actions(self, account_id: int) -> list[dict]:
        """只读返回待对账的投递意图。:param account_id: 账号。:return: 意图列表。"""
        rows = self._rows("SELECT a.* FROM warmup_pi_actions a JOIN warmup_pi_rounds r ON r.id=a.round_id "
            "WHERE r.account_id=? AND a.status IN ('intent','unknown') ORDER BY a.created_at", (account_id,))
        return [{key: value for key, value in row.items() if key != 'request_json'} |
            {'request': json.loads(row['request_json'])} for row in rows]

    def reconcile(self, account_id: int, operation_id: str, sent: bool) -> dict:
        """保存人工核对事实，不自动开启计划或继续模型。:param account_id: 账号。:param operation_id: 原操作。:param sent: 是否已发。:return: 公开状态。"""
        with self.lock:
            agent = self._one('SELECT * FROM warmup_pi_agents WHERE account_id=?', (account_id,))
            current = self._round(agent) if agent else None
            if account_id in self.controllers or current and current['runtime_json'] or type(sent) is not bool:
                raise ValueError('请等待 Pi 收口后核对输入')
            row = self._one("SELECT a.* FROM warmup_pi_actions a JOIN warmup_pi_rounds r ON r.id=a.round_id "
                "WHERE a.id=? AND r.account_id=? AND a.status IN ('intent','unknown')", (operation_id, account_id))
            if not row:
                raise ValueError('待核对输入不存在')
            self._write('UPDATE warmup_pi_actions SET status=?,ended_at=? WHERE id=?', ('sent' if sent else 'not_sent', time.time(), operation_id))
            if not self.actions(account_id):
                self._write("UPDATE warmup_pi_rounds SET status='paused',message=? WHERE id=? AND status NOT IN ('completed','stopped')",
                    ('输入已人工核对，等待显式恢复', row['round_id']))
            self._event(account_id, 'reconciled', {'operation_id': operation_id, 'sent': sent}, row['round_id'])
        return self.view(account_id)

    def _public_round(self, row):
        if not row:
            return None
        result = {key: row[key] for key in ('id', 'topic_id', 'topic_no', 'title', 'status', 'session_id',
            'work_sec', 'created_at', 'started_at', 'ended_at', 'message')}
        result['work_sec'] = self._elapsed(row)
        topic = json.loads(row['topic_json'])
        proof = json.loads(row['evidence_json']) if row['evidence_json'] else {}
        return result | {'completed_stages': proof.get('completed_stages', 0), 'required_stages': 1 + len(topic['followups'])}

    def view(self, account_id: int | None = None) -> dict:
        """读取公开账号现场，不创建配置或触发任何模型。:param account_id: 可选账号。:return: 账号摘要。"""
        identifiers = [account_id] if account_id is not None else [row['id'] for row in self._rows(
            'SELECT id FROM accounts WHERE enabled=1 AND deleted_at IS NULL ORDER BY id')]
        result = []
        for aid in identifiers:
            account = self.account(aid)
            if not account:
                continue
            agent = self._one('SELECT * FROM warmup_pi_agents WHERE account_id=?', (aid,)) or {
                'account_id': aid, 'generation': 0, 'status': 'off', 'instructions': '', 'budget_sec': 1800,
                'current_round_id': None, 'message': None, 'recovery_count': 0, 'recovery_phase': None, 'retry_at': None}
            row = self._round(agent)
            elapsed = self._elapsed(row) if row else 0
            activity = self._one("SELECT kind,payload_json,created_at FROM warmup_pi_events WHERE account_id=? "
                "AND kind NOT IN ('usage','observation') ORDER BY id DESC LIMIT 1", (aid,))
            public = {key: agent[key] for key in ('account_id', 'generation', 'status', 'instructions', 'budget_sec',
                'current_round_id', 'message', 'recovery_count', 'recovery_phase', 'retry_at')}
            round_summary = self._public_round(row)
            public.update(controller_active=aid in self.controllers, owner=self.owners.owner(aid), round=round_summary,
                schedule={'enabled': bool(account.get('warmup_enabled')), 'interval_min_hours': account.get('warmup_interval_min_hours'),
                    'interval_max_hours': account.get('warmup_interval_max_hours'), 'next_run_at': account.get('warmup_next_run_at'),
                    'last_status': account.get('warmup_last_status'), 'last_error': account.get('warmup_last_error')},
                admission=self._public_gate(self._admit(account, row)), activity=None if not activity else {
                    'kind': activity['kind'], 'created_at': activity['created_at'], 'payload': json.loads(activity['payload_json'])},
                progress={'elapsed_work_sec': elapsed, 'remaining_work_sec': max(0, agent['budget_sec'] - elapsed),
                    'completed_stages': round_summary['completed_stages'] if round_summary else 0,
                    'required_stages': round_summary['required_stages'] if round_summary else 0},
                claude_usage=json.loads(row['claude_usage_json']) if row and row['claude_usage_json'] else None,
                pi_usage=self._pi_usage(aid))
            result.append(public)
        return {'agents': result, 'pi_available': self.pi.available(), 'architecture': 'account-warmup-pi'}

    def _pi_usage(self, aid):
        """汇总本域账号的真实模型用量，未知字段保留 None。"""
        values = [json.loads(row['payload_json']).get('usage') for row in self._rows(
            "SELECT payload_json FROM warmup_pi_events WHERE account_id=? AND kind='usage'", (aid,))]
        if not values:
            return None
        result = {'requests': len(values), 'complete': True}
        for source, target in (('input', 'input_tokens'), ('output', 'output_tokens'),
                ('cacheRead', 'cache_read_tokens'), ('cacheWrite', 'cache_write_tokens')):
            collected = [item[source] for item in values if isinstance(item, dict) and type(item.get(source)) in (int, float)
                and math.isfinite(item[source]) and item[source] >= 0]
            result[target] = sum(collected) if collected else None
            result['complete'] &= len(collected) == len(values)
        return result

    @staticmethod
    def _public_gate(gate):
        """仅公开页面所需的执行条件，内部身份及租约来源不进入 API。"""
        value = {key: gate.get(key) for key in ('allowed', 'reason', 'retryable', 'retry_at', 'message')}
        quota = gate.get('quota')
        if isinstance(quota, dict):
            value['quota'] = {key: quota.get(key) for key in ('known', 'source', 'observed_at', 'limits', 'hit')}
            value['quota']['windows'] = {key: {field: window.get(field) for field in
                ('utilization', 'reset_at', 'resets_at', 'exhausted', 'rejected', 'observed_at')}
                for key, window in (quota.get('windows') or {}).items()
                if key in ('five_hour', 'seven_day') and isinstance(window, dict)}
        window = gate.get('window')
        if isinstance(window, dict):
            value['window'] = {key: window.get(key) for key in ('enabled', 'allowed', 'timezone', 'next_open_at', 'next_close_at')}
        return value

    @staticmethod
    def _read_events(connection, aid, before, limit):
        condition, values = ('', [aid]) if before is None else (' AND id<?', [aid, before])
        rows = [dict(row) for row in connection.execute("SELECT id,round_id,kind,payload_json,created_at FROM warmup_pi_events "
            "WHERE account_id=? AND kind NOT IN ('observation','usage')" + condition + ' ORDER BY id DESC LIMIT ?', (*values, limit + 1))]
        items = rows[:limit]
        for item in items:
            item['payload'] = json.loads(item.pop('payload_json'))
        return {'items': items, 'next_before': items[-1]['id'] if len(rows) > limit else None}

    def event_page(self, account_id: int, before: int | None = None, limit: int = 20) -> dict:
        """最新在前分页读取交互，省略屏幕采样和用量。:param account_id: 账号。:param before: 独占事件上界。:param limit: 页大小。:return: 当前页与游标。"""
        if type(limit) is not int or not 1 <= limit <= 100 or before is not None and (type(before) is not int or before < 1):
            raise ValueError('交互分页参数不合法')
        connection = self.database()
        try:
            return self._read_events(connection, account_id, before, limit)
        finally:
            connection.close()

    def snapshot(self, account_id: int) -> dict:
        """一致读取高水位及当前轮最新画面，首次进入不重放历史。:param account_id: 账号。:return: 现场快照。"""
        connection = self.database()
        try:
            connection.execute('BEGIN')
            agent = connection.execute('SELECT current_round_id FROM warmup_pi_agents WHERE account_id=?', (account_id,)).fetchone()
            rid = agent['current_round_id'] if agent else None
            cursor = connection.execute('SELECT COALESCE(MAX(id),0) FROM warmup_pi_events WHERE account_id=?', (account_id,)).fetchone()[0]
            observed = connection.execute("SELECT id,round_id,kind,payload_json,created_at FROM warmup_pi_events "
                "WHERE account_id=? AND round_id=? AND kind='observation' AND id<=? ORDER BY id DESC LIMIT 1", (account_id, rid, cursor)).fetchone()
            observed = dict(observed) if observed else None
            if observed:
                observed['payload'] = json.loads(observed.pop('payload_json'))
            events = self._read_events(connection, account_id, cursor + 1, 20)
        finally:
            connection.close()
        return {'state': self.view(account_id), 'cursor': cursor, 'round_id': rid, 'observation': observed, 'events': events}

    def events(self, account_id: int, after: int = 0) -> list[dict]:
        """按游标读取有界实时增量。:param account_id: 账号。:param after: 已消费ID。:return: 按ID递增的最多200条记录。"""
        rows = self._rows('SELECT id,round_id,kind,payload_json,created_at FROM warmup_pi_events WHERE account_id=? AND id>? ORDER BY id LIMIT 200',
            (account_id, after))
        for row in rows:
            row['payload'] = json.loads(row.pop('payload_json'))
        return rows

    def round_page(self, account_id: int, before: str | None = None, limit: int = 10) -> dict:
        """稳定分页读取全部养号轮次，不伪造旧runs记录。:param account_id: 账号。:param before: 上页末轮ID。:param limit: 页大小。:return: 轮次页。"""
        if type(limit) is not int or not 1 <= limit <= 100 or before is not None and (not isinstance(before, str) or not 1 <= len(before) <= 128):
            raise ValueError('养号分页参数不合法')
        connection = self.database()
        try:
            connection.execute('BEGIN')
            condition, values = '', [account_id]
            if before:
                anchor = connection.execute('SELECT created_at,id FROM warmup_pi_rounds WHERE account_id=? AND id=?', (account_id, before)).fetchone()
                if not anchor:
                    raise ValueError('养号分页游标不存在')
                condition = ' AND (created_at<? OR (created_at=? AND id<?))'
                values.extend((anchor['created_at'], anchor['created_at'], anchor['id']))
            rows = [dict(row) for row in connection.execute('SELECT * FROM warmup_pi_rounds WHERE account_id=?' + condition
                + ' ORDER BY created_at DESC,id DESC LIMIT ?', (*values, limit + 1))]
            items = [self._public_round(row) for row in rows[:limit]]
            return {'items': items, 'next_before': items[-1]['id'] if len(rows) > limit else None}
        finally:
            connection.close()

    def round_detail(self, round_id: str) -> dict:
        """读取冻结题目和真实收尾证据，不公开私有路径或配置。:param round_id: 轮次。:return: 轮次详情。"""
        row = self._one('SELECT * FROM warmup_pi_rounds WHERE id=?', (round_id,))
        if not row:
            raise ValueError('养号轮次不存在')
        topic = json.loads(row['topic_json'])
        return {'round': self._public_round(row), 'topic': {key: topic[key] for key in ('topic_id', 'topic_no', 'title', 'prompt', 'followups')} |
            {'timing': topic.get('timing', {})},
            'evidence': json.loads(row['evidence_json']) if row['evidence_json'] else None}
