"""独立 SQLite 与假 Pi/终端验证完整题库养号，不调用真实账号或模型。"""
import copy
import hashlib
import json
import sqlite3
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from pi_owners import AccountPiOwners
from warmup_pi import GUIDE, WarmupPiService
from warmup_pi_api import warmup_pi_router


class TerminalFixture:
    """只记录真实工具调用，原生输入和正常回复均有独立父链。"""

    def __init__(self, root):
        """初始化隔离会话与投递记录。:return: None。"""
        self.started, self.sent, self.controls, self.messages = [], [], [], {}
        self.unknown, self.normal = False, True
        self.root = root
        root.mkdir()

    def start(self, account, row):
        """记录同轮会话恢复，不自动发送题目。:param account: 账号。:param row: 轮次。:return: 定位。"""
        if row.get('resume_required') and not (self.root / (row['session_id'] + '.jsonl')).is_file():
            raise ValueError('原 Claude 会话缺失，不能用新会话替代已有输入')
        self.started.append(copy.deepcopy(row))
        self.messages.setdefault(row['id'], [])
        return {'token': 'fixture-' + row['id'], 'source': f"warmup:{row['id']}:{row['generation']}"}

    def observe(self, row, cursor=0):
        """返回独立的原生观察摘要。:param row: 轮次。:param cursor: 游标。:return: 屏幕与消息。"""
        messages = self.messages[row['id']]
        return {'screen': 'Claude is ready.', 'events': copy.deepcopy(messages[cursor:]),
            'cursor': len(messages), 'running': True, 'terminal_ready': True, 'quota_paused': False}

    def passive_status(self, row):
        """模拟无新额度错误的被动读取。:param row: 轮次。:return: 空事实。"""
        return {}

    def append(self, row, role, text, *, normal=True, parent=None):
        """加入可追溯原生消息。:param row: 轮次。:param role: 角色。:param text: 正文。:param normal: 是否正常。:param parent: 显式父键。:return: 新消息。"""
        records = self.messages[row['id']]
        identifier = f'{role}-{len(records)}'
        value = {'id': identifier, 'key': row['session_id'] + '.jsonl:' + str(len(records)),
            'parent_key': parent if parent is not None else records[-1]['key'] if records else None,
            'role': role, 'text': text, 'normal': normal, 'synthetic': not normal,
            'tool': False, 'end': len(records) + 1}
        records.append(value)
        return value

    def send(self, row, operation, text, keys, submit):
        """仅工具调用产生原生输入，可模拟投递回执丢失。:param row: 轮次。:param operation: 操作。:param text: 正文。:param keys: 按键。:param submit: 提交。:return: None。"""
        self.sent.append((row['id'], operation, text, keys, submit))
        (self.root / (row['session_id'] + '.jsonl')).write_text('{}\n')
        if text:
            self.append(row, 'user', text)
        if self.unknown:
            raise RuntimeError('已写入终端但回执丢失')
        if text:
            self.append(row, 'assistant', 'The requested local change is ready for review.', normal=self.normal)

    def control(self, row, operation):
        """记录原轮次收口，不改变其它账号。:param row: 轮次。:param operation: 操作。:return: 确认。"""
        self.controls.append((row['id'], operation))
        return {'stopped': operation == 'stop'}

    def dialogue(self, row):
        """返回独立的原生证据，而不是Pi提供的完成标志。:param row: 轮次。:return: 父链记录。"""
        return copy.deepcopy(self.messages[row['id']])

    def usage(self, row):
        """没有采集令牌时保留未知。:param row: 轮次。:return: 统计覆盖信息。"""
        return {'complete': False}


class PiFixture:
    """可持有控制权、返回结构错误或真正调用完整轮次工具的合成Pi。"""

    def __init__(self, mode='hold'):
        """建立隔离信号与调用记录。:param mode: 预设行为。:return: None。"""
        self.mode, self.calls, self.results = mode, [], []
        self.entered = threading.Event()
        self.error = {'type': 'error', 'reason': 'model_unavailable', 'message': '合成临时模型故障'}

    def available(self):
        """声明本地夹具就绪。:return: True。"""
        return True

    def run(self, config, tools, event, stop, timeout_sec):
        """用真实服务工具推进合成原生交流。:param config: 配置。:param tools: 工具。:param event: 事件。:param stop: 取消。:param timeout_sec: 预算。:return: 本轮状态。"""
        self.calls.append((copy.deepcopy(config), timeout_sec))
        path = Path(config['session_file']) if config['session_file'] else Path(config['session_dir']) / 'original.jsonl'
        path.write_text('{}\n')
        event({'type': 'ready', 'session_file': str(path)})
        self.entered.set()
        if self.mode == 'hold':
            stop.wait(5)
            return 'stopped'
        if self.mode == 'error':
            event(self.error)
            return 'error'
        if self.mode == 'declare_only':
            self.results.append(tools('round_finish', {'summary': 'Pi claims completion'}, 'unproven-finish'))
            return 'settled'
        topic = tools('topic_read', {}, 'read-topic')
        self.results.append(tools('claude_start', {}, 'start-claude'))
        for index, text in enumerate([topic['prompt'], *topic['followups']]):
            observation = tools('claude_observe', {}, f'observe-{index}')
            self.results.append(tools('claude_input', {'observation_id': observation['observation_id'], 'text': text}, f'input-{index}'))
        self.results.append(tools('round_finish', {'summary': 'All requested changes were discussed and delivered.'}, 'finish'))
        self.results.append(tools('claude_start', {}, 'late-start'))
        return 'settled'


class WarmupPiTests(unittest.TestCase):
    """使用完整自有表及原账号权威配置验证养号控制生命周期。"""

    def setUp(self):
        """创建隔离账号、旧记录和新服务。:return: None。"""
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.path = self.root / 'db.sqlite'
        connection = self.database()
        connection.executescript('''CREATE TABLE accounts(id INTEGER PRIMARY KEY,enabled INTEGER DEFAULT 1,deleted_at REAL,
          cc2api_account_id INTEGER,warmup_enabled INTEGER DEFAULT 0,warmup_interval_min_hours INTEGER DEFAULT 3,
          warmup_interval_max_hours INTEGER DEFAULT 5,warmup_next_run_at REAL,warmup_last_attempt_at REAL,
          warmup_last_status TEXT DEFAULT 'off',warmup_last_error TEXT,warmup_last_run_id TEXT DEFAULT 'legacy-id');
          INSERT INTO accounts(id) VALUES(1),(2);
          CREATE TABLE runs(id TEXT PRIMARY KEY,status TEXT);INSERT INTO runs VALUES('legacy-id','success');''')
        connection.commit();connection.close()
        self.terminal, self.pi, self.owners = TerminalFixture(self.root / 'native'), PiFixture(), AccountPiOwners()
        self.gate = {'allowed': True, 'retryable': False, 'reason': 'allowed', 'identity': 'private-identity'}
        self.prepared = []
        self.service = self.make_service()
        self.addCleanup(self.service.close)

    def database(self):
        """创建返回命名行的SQLite连接。:return: 连接。"""
        connection = sqlite3.connect(self.path, timeout=5)
        connection.row_factory = sqlite3.Row
        connection.execute('PRAGMA foreign_keys=ON')
        return connection

    def account(self, aid):
        """读取原账号权威设置。:param aid: 账号。:return: 可用账号或None。"""
        connection = self.database()
        try:
            row = connection.execute('SELECT * FROM accounts WHERE id=? AND enabled=1 AND deleted_at IS NULL', (aid,)).fetchone()
            return dict(row) if row else None
        finally:
            connection.close()

    def prepare(self, account):
        """冻结原题库消息、补充与CLI设置。:param account: 账号。:return: 题目DTO。"""
        self.prepared.append(account['id'])
        return {'topic_id': 51, 'topic_no': 51, 'title': 'Local notes board',
            'prompt': 'Build a local notes board with synthetic examples. Inspect and discuss a plan first.',
            'followups': ['Add a filter for completed notes.', 'Provide a local export and verify the complete workflow.'],
            'settings': {'claude_code_version': '2.1.293', 'claude_effort_level': 'high'},
            'timing': {'selected_followups': 2, 'timeout_sec': 1800}}

    def make_service(self):
        """注入本地依赖，不访问Docker或模型。:return: 服务。"""
        return WarmupPiService(self.root, self.database, threading.Lock(), self.terminal, self.account,
            lambda *_: dict(self.gate), lambda: {'base_url': 'https://example.invalid/v1', 'models': ['test'], 'api_key': 'private-provider-key'},
            self.prepare, lambda account: time.time() + 10800, owners=self.owners, pi=self.pi)

    def enable(self, aid=1):
        """模拟用户通过原账号API开启下一轮。:param aid: 账号。:return: None。"""
        self.service._write("UPDATE accounts SET warmup_enabled=1,warmup_next_run_at=?,warmup_last_status='scheduled' WHERE id=?",
            (time.time() - 1, aid))

    def begin(self):
        """真正启动持有控制者并等待就绪。:return: 账号及轮次。"""
        self.enable()
        self.service.start(1)
        self.assertTrue(self.pi.entered.wait(2))
        agent = self.service._one('SELECT * FROM warmup_pi_agents WHERE account_id=1')
        return agent, self.service._round(agent)

    def join(self, aid=1):
        """等合成控制者收口，避免线程污染下一个断言。:param aid: 账号。:return: None。"""
        controller = self.service.controllers.get(aid)
        if controller:
            controller[0].join(3)
            self.assertFalse(controller[0].is_alive())

    def tool(self, name, args=None, call_id='call'):
        """绑定当前服务端代次调用真实工具。:param name: 工具。:param args: 参数。:param call_id: 调用ID。:return: 工具结果。"""
        generation = self.service._one('SELECT generation FROM warmup_pi_agents WHERE account_id=1')['generation']
        return self.service.tool(1, generation, name, args or {}, call_id)

    def test_off_accounts_initialization_configuration_reads_and_recovery_never_enable(self):
        """关闭账户的初始化、指南保存、页面读取与重启不产生计划或模型。:return: None。"""
        before = [self.account(1), self.account(2)]
        self.service.configure(1, '给 Claude 使用英文，并保留业务要求。', 1200)
        self.service.view();self.service.snapshot(1);self.service.event_page(1);self.service.round_page(1)
        self.service.recover();self.service.tick(time.time() + 86400)
        self.assertEqual(before, [self.account(1), self.account(2)])
        self.assertFalse(self.service.has_taken_over(1))
        with self.assertRaisesRegex(ValueError, '先开启'):
            self.service.start(1)
        self.assertEqual([], self.pi.calls)
        self.assertEqual([], self.prepared)

    def test_complete_round_uses_frozen_topic_native_proof_and_original_random_schedule(self):
        """原题库完整交流独立收尾，不创建伪run，保留累计时间及原随机间隔。:return: None。"""
        self.pi.mode = 'complete'
        self.enable()
        self.service.configure(1, '按原业务需求推进，给 Claude 不要带中文。')
        self.service.start(1);self.join()
        agent = self.service.view(1)['agents'][0]
        self.assertEqual('completed', agent['round']['status'])
        self.assertEqual(3, agent['round']['completed_stages'])
        self.assertEqual(3, len(self.terminal.sent))
        self.assertEqual(1, len(self.terminal.started))
        self.assertEqual('completed', self.pi.results[-1]['status'])
        self.assertEqual('success', self.account(1)['warmup_last_status'])
        self.assertAlmostEqual(time.time() + 10800, self.account(1)['warmup_next_run_at'], delta=2)
        self.assertEqual('legacy-id', self.account(1)['warmup_last_run_id'])
        self.assertEqual([{'id': 'legacy-id', 'status': 'success'}], self.service._rows('SELECT * FROM runs'))
        self.assertIsNone(self.owners.owner(1))
        detail = self.service.round_detail(agent['round']['id'])
        self.assertEqual(2, detail['topic']['timing']['selected_followups'])
        self.assertEqual(3, len(detail['evidence']['stages']))

    def test_pi_self_report_without_normal_native_exchange_cannot_complete(self):
        """仅Pi自述完成不产生成功记录或下一轮计划。:return: None。"""
        self.pi.mode = 'declare_only'
        self.enable();self.service.start(1);self.join()
        self.assertEqual('rejected', self.pi.results[0]['status'])
        self.assertEqual('blocked', self.service.view(1)['agents'][0]['round']['status'])
        self.assertIsNone(self.account(1)['warmup_next_run_at'])

    def test_shared_owner_defers_before_model_and_freezing_topic(self):
        """项目Pi即使尚未创建终端也阻止养号模型抢占。:return: None。"""
        self.enable()
        token = self.owners.claim(1, 'projects', 1)
        state = self.service.start(1)['agents'][0]
        self.assertEqual('waiting', state['status'])
        self.assertGreater(self.account(1)['warmup_next_run_at'], time.time() + 58)
        self.assertEqual([], self.prepared)
        self.assertEqual([], self.pi.calls)
        self.assertFalse(self.service.has_taken_over(1))
        self.assertTrue(self.owners.release(1, token))

    def test_fresh_observation_receipts_and_same_call_are_idempotent(self):
        """输入先记意图，旧观察不可用，原调用重放只返回回执。:return: None。"""
        agent, row = self.begin()
        self.tool('claude_start')
        observation = self.tool('claude_observe')
        args = {'observation_id': observation['observation_id'], 'text': json.loads(row['topic_json'])['prompt']}
        self.assertEqual('sent', self.tool('claude_input', args, 'original')['status'])
        self.assertTrue(self.tool('claude_input', args, 'original')['replayed'])
        self.assertEqual('rejected', self.tool('claude_input', {'observation_id': observation['observation_id'], 'text': 'Another request'}, 'stale')['status'])
        fresh = self.tool('claude_observe')
        self.assertTrue(self.tool('claude_input', {**args, 'observation_id': fresh['observation_id']}, 'duplicate-prompt')['replayed'])
        self.assertEqual(1, len(self.terminal.sent))
        self.assertEqual('sent', self.service._one('SELECT status FROM warmup_pi_actions')['status'])

    def test_cross_restart_reuses_round_session_topic_and_confirmed_input(self):
        """暂停后恢复原轮而不重选题，原输入不会因新代次重复发送。:return: None。"""
        _, row = self.begin()
        self.tool('claude_start');observed = self.tool('claude_observe')
        prompt = json.loads(row['topic_json'])['prompt']
        self.tool('claude_input', {'observation_id': observed['observation_id'], 'text': prompt}, 'first')
        self.service.pause(1, disable_schedule=False);self.join()
        self.service.recover()
        self.service.start(1)
        self.assertEqual(1, len(self.prepared))
        self.assertEqual(row['id'], self.service.view(1)['agents'][0]['round']['id'])
        self.tool('claude_start');fresh = self.tool('claude_observe')
        result = self.tool('claude_input', {'observation_id': fresh['observation_id'], 'text': prompt}, 'new-generation')
        self.assertTrue(result['replayed'])
        self.assertEqual(1, len(self.terminal.sent))
        self.assertEqual(row['session_id'], self.terminal.started[-1]['session_id'])
        self.assertTrue(self.terminal.started[-1]['resume_required'])

    def test_partial_progress_only_counts_consumed_requests_with_normal_descendant_replies(self):
        """原生确认初始回复后展示1/3，排队或错误回复不能冒充已确认阶段。:return: None。"""
        _, row = self.begin();self.tool('claude_start')
        first = self.tool('claude_observe')
        self.assertEqual(0, self.service.view(1)['agents'][0]['round']['completed_stages'])
        topic = json.loads(row['topic_json'])
        self.tool('claude_input', {'observation_id': first['observation_id'], 'text': topic['prompt']}, 'initial')
        self.tool('claude_observe')
        state = self.service.view(1)['agents'][0]['round']
        self.assertEqual((1, 3), (state['completed_stages'], state['required_stages']))
        self.assertEqual('rejected', self.tool('round_finish', {'summary': 'Too early'}, 'early')['status'])
        self.terminal.normal = False
        fresh = self.tool('claude_observe')
        self.tool('claude_input', {'observation_id': fresh['observation_id'], 'text': topic['followups'][0]}, 'queued')
        self.tool('claude_observe')
        self.assertEqual(1, self.service.view(1)['agents'][0]['round']['completed_stages'])

    def test_queued_initial_message_has_zero_confirmed_stages(self):
        """只有终端投递及排队记录，初始阶段仍为0/3。:return: None。"""
        _, row = self.begin();self.tool('claude_start')
        self.terminal.normal = False
        observed = self.tool('claude_observe')
        self.tool('claude_input', {'observation_id': observed['observation_id'], 'text': json.loads(row['topic_json'])['prompt']}, 'queued-initial')
        self.tool('claude_observe')
        current = self.service.view(1)['agents'][0]['round']
        self.assertEqual((0, 3), (current['completed_stages'], current['required_stages']))

    def test_unknown_input_blocks_other_inputs_and_scheduled_recovery_until_reconciled(self):
        """未知投递不能切调用ID重发，人工对账也不自动重启计划。:return: None。"""
        _, row = self.begin();self.tool('claude_start');observed = self.tool('claude_observe')
        self.terminal.unknown = True
        result = self.tool('claude_input', {'observation_id': observed['observation_id'], 'text': 'Implement the approved plan.'}, 'uncertain')
        self.assertEqual('unknown', result['status'])
        self.assertEqual('blocked', self.tool('claude_input', {'observation_id': observed['observation_id'], 'text': 'Implement the approved plan.'}, 'different')['status'])
        self.assertEqual(1, len(self.terminal.sent))
        self.service.pause(1);self.join()
        self.service.reconcile(1, result['operation_id'], True)
        self.assertEqual(0, self.account(1)['warmup_enabled'])
        self.assertIsNone(self.account(1)['warmup_next_run_at'])
        self.assertEqual([], self.service.actions(1))

    def test_empty_claude_session_can_reopen_same_round_before_any_input(self):
        """首次发送前JSONL尚未创建也能恢复原空轮次，不能误当已发送会话丢失。:return: None。"""
        _, row = self.begin();self.tool('claude_start');self.tool('claude_observe')
        native = self.terminal.root / (row['session_id'] + '.jsonl')
        self.assertFalse(native.exists())
        self.service.pause(1, disable_schedule=False);self.join()
        self.service.recover();self.service.start(1)
        result = self.tool('claude_start')
        self.assertEqual('running', result['status'])
        self.assertEqual(row['session_id'], result['session_id'])
        self.assertEqual(row['id'], result['round_id'])
        self.assertFalse(self.terminal.started[-1]['resume_required'])
        self.assertEqual(1, len(self.prepared))
        self.assertEqual([], self.terminal.sent)

    def test_missing_native_after_confirmed_input_cannot_create_a_replacement(self):
        """一旦投递过正文，原JSONL缺失仍硬拒绝，不能借空轮恢复重新发送。:return: None。"""
        _, row = self.begin();self.tool('claude_start');observed = self.tool('claude_observe')
        self.tool('claude_input', {'observation_id': observed['observation_id'], 'text': json.loads(row['topic_json'])['prompt']}, 'sent')
        native = self.terminal.root / (row['session_id'] + '.jsonl')
        self.assertTrue(native.is_file());native.unlink()
        self.service.pause(1, disable_schedule=False);self.join()
        self.service.start(1)
        result = self.tool('claude_start')
        self.assertEqual('rejected', result['status'])
        self.assertIn('原 Claude 会话缺失', result['message'])
        self.assertEqual(1, len(self.terminal.started))
        self.assertEqual(1, len(self.terminal.sent))

    def test_reconciling_unknown_input_does_not_revive_a_stopped_round(self):
        """停止的轮次不会被后续人工输入核对复活，重新开启会创建新题目轮次。:return: None。"""
        _, row = self.begin();self.tool('claude_start');observed = self.tool('claude_observe')
        self.terminal.unknown = True
        result = self.tool('claude_input', {'observation_id': observed['observation_id'], 'text': 'Apply the approved change.'}, 'unknown')
        self.service.pause(1, stop_round=True);self.join()
        self.service.reconcile(1, result['operation_id'], False)
        self.assertEqual('stopped', self.service._one('SELECT status FROM warmup_pi_rounds WHERE id=?', (row['id'],))['status'])
        self.terminal.unknown = False;self.enable();self.service.start(1)
        self.assertNotEqual(row['id'], self.service.view(1)['agents'][0]['round']['id'])
        self.assertEqual(2, len(self.prepared))

    def test_queued_synthetic_tool_and_orphan_assistant_are_not_completion(self):
        """排队、错误、工具或旁支回复都不能当成本轮真实完成。:return: None。"""
        _, row = self.begin();self.tool('claude_start')
        self.terminal.normal = False
        topic = json.loads(row['topic_json'])
        for index, text in enumerate([topic['prompt'], *topic['followups']]):
            observed = self.tool('claude_observe')
            self.tool('claude_input', {'observation_id': observed['observation_id'], 'text': text}, 'stage-' + str(index))
        self.assertEqual('rejected', self.tool('round_finish', {'summary': 'Claimed'}, 'finish-synthetic')['status'])
        self.terminal.append(row, 'assistant', 'Unrelated branch response.', parent='other-session:0')
        self.assertEqual('rejected', self.tool('round_finish', {'summary': 'Claimed'}, 'finish-orphan')['status'])
        records = self.terminal.messages[row['id']]
        self.terminal.append(row, 'assistant', 'All supplied requests have been implemented.', parent=records[-2]['key'])
        self.assertEqual('completed', self.tool('round_finish', {'summary': 'Actual final answer'}, 'finish-normal')['status'])

    def test_disabling_next_schedule_does_not_interrupt_claimed_round(self):
        """原账号配置关闭下一轮时当前完整轮仍可完成，不能偷偷再排计划。:return: None。"""
        _, row = self.begin();self.tool('claude_start')
        self.service._write("UPDATE accounts SET warmup_enabled=0,warmup_next_run_at=NULL WHERE id=1")
        topic = json.loads(row['topic_json'])
        for index, text in enumerate([topic['prompt'], *topic['followups']]):
            observed = self.tool('claude_observe')
            self.assertIn('observation_id', observed)
            self.assertEqual('sent', self.tool('claude_input', {'observation_id': observed['observation_id'], 'text': text}, 'off-stage-' + str(index))['status'])
        self.assertEqual('completed', self.tool('round_finish', {'summary': 'Finished the already claimed round'}, 'off-finish')['status'])
        self.assertEqual(0, self.account(1)['warmup_enabled'])
        self.assertIsNone(self.account(1)['warmup_next_run_at'])
        self.assertEqual('success', self.account(1)['warmup_last_status'])

    def test_additional_submitted_clarification_cannot_be_completed_while_only_queued(self):
        """冻结需求已答完也不能丢掉Pi后来提交、尚未实际消费的澄清。:return: None。"""
        _, row = self.begin();self.tool('claude_start')
        topic = json.loads(row['topic_json'])
        for index, text in enumerate([topic['prompt'], *topic['followups']]):
            observed = self.tool('claude_observe')
            self.tool('claude_input', {'observation_id': observed['observation_id'], 'text': text}, f'required-{index}')
        observed = self.tool('claude_observe')
        self.tool('claude_input', {'observation_id': observed['observation_id'], 'text': 'Verify the final export output once more.'}, 'extra')
        self.terminal.messages[row['id']] = self.terminal.messages[row['id']][:-2]
        self.assertEqual('rejected', self.tool('round_finish', {'summary': 'Too early'}, 'pending-extra')['status'])
        self.terminal.append(row, 'user', 'Verify the final export output once more.')
        self.terminal.append(row, 'assistant', 'The final export was verified against the synthetic examples.')
        self.assertEqual('completed', self.tool('round_finish', {'summary': 'Actually complete'}, 'finish-extra')['status'])

    def test_runtime_usage_and_original_business_guide_are_publicly_safe(self):
        """指南原样进入Pi并记录指纹，用量未知不假零，私有字段不进入公开结果。:return: None。"""
        self.enable();instructions = '先调查再实施，给Claude不要带中文。'
        self.service.configure(1, instructions, 1200);self.service.start(1)
        self.assertTrue(self.pi.entered.wait(2))
        config = self.pi.calls[0][0]
        self.assertEqual(GUIDE + '\n用户追加业务指南：\n' + instructions, config['instructions'])
        loaded = self.service.event_page(1)['items'][0]
        self.assertEqual(hashlib.sha256(instructions.encode()).hexdigest(), loaded['payload']['user_guide_sha256'])
        generation = self.service.view(1)['agents'][0]['generation']
        self.service._pi_event(1, generation, {'type': 'assistant', 'message_id': 'unknown-usage', 'usage': None})
        state = self.service.view(1)['agents'][0]
        self.assertIsNone(state['pi_usage']['input_tokens'])
        self.service._pi_event(1, generation, {'type': 'assistant', 'message_id': 'known-usage',
            'usage': {'input': 10, 'output': 4, 'cacheRead': 30, 'cacheWrite': 2}})
        state = self.service.view(1)['agents'][0]
        self.assertEqual(10, state['pi_usage']['input_tokens'])
        self.assertFalse(state['pi_usage']['complete'])
        text = json.dumps(state)
        self.assertNotIn('private-provider-key', text)
        self.assertNotIn('private-identity', text)
        self.assertNotIn('session_file', text)
        self.assertNotIn('settings', self.tool('topic_read'))

    def test_model_recovery_long_wait_low_frequency_and_restart_use_original_round(self):
        """临时模型故障持久等候，长RetryAfter和重启不能缩短原等待或换题。:return: None。"""
        self.pi.mode = 'error';self.enable()
        due = time.time() + 1200
        self.pi.error['retry_at'] = due
        self.service.start(1);self.join()
        state = self.service.view(1)['agents'][0]
        self.assertEqual(('waiting', 1), (state['status'], state['recovery_count']))
        self.assertEqual(due, self.account(1)['warmup_next_run_at'])
        round_id = state['round']['id']
        self.service.recover()
        self.assertEqual(due, self.account(1)['warmup_next_run_at'])
        self.service.tick(due - 1)
        self.assertEqual(1, len(self.pi.calls))
        for attempt in range(2, 5):
            next_at = self.account(1)['warmup_next_run_at']
            with patch('warmup_pi.time.time', return_value=next_at + 0.01):
                self.pi.error.pop('retry_at', None)
                self.service.tick(next_at + 0.01);self.join()
            self.assertEqual(round_id, self.service.view(1)['agents'][0]['round']['id'])
        state = self.service.view(1)['agents'][0]
        self.assertEqual(('waiting', 3, 'exhausted'), (state['status'], state['recovery_count'], state['recovery_phase']))
        self.assertEqual(1, len(self.prepared))
        self.assertGreater(self.account(1)['warmup_next_run_at'], next_at + 10000)
        self.service.pause(1);self.service.recover();self.service.tick(time.time() + 200000)
        self.assertEqual(4, len(self.pi.calls))

    def test_budget_identity_and_hard_errors_never_use_model_recovery(self):
        """预算、身份与明确硬错误不会被临时模型恢复策略解除。:return: None。"""
        self.pi.mode = 'error';self.pi.error['reason'] = 'provider_conflict';self.enable()
        self.service.start(1);self.join()
        state = self.service.view(1)['agents'][0]
        self.assertEqual('blocked', state['status'])
        self.assertIsNone(self.account(1)['warmup_next_run_at'])
        self.assertEqual(0, state['recovery_count'])
        self.service._write('UPDATE warmup_pi_rounds SET work_sec=1800 WHERE id=?', (state['round']['id'],))
        self.service.start(1)
        self.assertEqual(1, len(self.pi.calls))
        self.assertIn('预算', self.service.view(1)['agents'][0]['message'])

    def test_manual_provider_retry_preserves_reason_across_restart_and_keeps_original_round(self):
        """硬模型配置故障只供人工修复后续跑，重启不能抹掉原故障或另选题。:return: None。"""
        self.pi.mode = 'error';self.pi.error['reason'] = 'provider_conflict';self.enable()
        self.service.start(1);self.join()
        first = self.service.view(1)['agents'][0]['round']
        self.service.recover()
        agent = self.service._one('SELECT * FROM warmup_pi_agents WHERE account_id=1')
        self.assertEqual('provider_conflict', agent['last_reason'])
        self.assertIsNone(self.account(1)['warmup_next_run_at'])
        self.assertEqual(1, len(self.pi.calls))
        self.pi.mode = 'hold';self.service.start(1)
        self.assertEqual(first['id'], self.service.view(1)['agents'][0]['round']['id'])
        self.assertEqual(first['session_id'], self.service.view(1)['agents'][0]['round']['session_id'])
        self.assertIn(1, self.service.controllers)
        self.assertEqual([1], self.prepared)

    def test_increased_budget_requires_explicit_resume_without_resetting_original_work(self):
        """累计预算只在人工提高后可显式续跑，关闭自动恢复且不清零已用时间。:return: None。"""
        self.pi.mode = 'error';self.pi.error['reason'] = 'provider_content_filter';self.enable()
        self.service.start(1);self.join()
        first = self.service.view(1)['agents'][0]['round']
        self.service._write('UPDATE warmup_pi_rounds SET work_sec=1800 WHERE id=?', (first['id'],))
        self.service.start(1)
        self.assertEqual('budget', self.service._one('SELECT * FROM warmup_pi_agents WHERE account_id=1')['last_reason'])
        self.service.configure(1, '保留原需求。', 3600)
        self.service.recover();self.service.tick(time.time() + 86400)
        self.assertEqual(1, len(self.pi.calls))
        self.pi.mode = 'hold';self.service.start(1)
        current = self.service.view(1)['agents'][0]['round']
        self.assertEqual(first['id'], current['id'])
        self.assertEqual(first['session_id'], current['session_id'])
        self.assertEqual(1800, current['work_sec'])
        self.assertIn(1, self.service.controllers)

    def test_usage_read_failure_does_not_prevent_manual_native_stop_or_disabling_schedule(self):
        """统计读取失败仍必须停止终端并先关闭未来计划，用量保留未知。:return: None。"""
        _, row = self.begin();self.tool('claude_start')
        with patch.object(self.terminal, 'usage', side_effect=OSError('合成统计读取故障')):
            self.service.pause(1)
        self.join()
        self.assertIn((row['id'], 'stop'), self.terminal.controls)
        self.assertEqual(0, self.account(1)['warmup_enabled'])
        self.assertIsNone(self.account(1)['warmup_next_run_at'])
        current = self.service._one('SELECT * FROM warmup_pi_rounds WHERE id=?', (row['id'],))
        self.assertIsNone(current['runtime_json'])
        self.assertFalse(json.loads(current['claude_usage_json'])['complete'])
        self.assertIsNone(self.owners.owner(1))

    def test_unconfirmed_stop_keeps_native_and_shared_owner_until_explicit_stop_succeeds(self):
        """停止异常不能声称停止或让其它Pi接管；计划先关闭，原定位到重试成功才释放。:return: None。"""
        _, row = self.begin();self.tool('claude_start')
        native = self.service._one('SELECT runtime_json FROM warmup_pi_rounds WHERE id=?', (row['id'],))['runtime_json']
        with patch.object(self.terminal, 'control', side_effect=RuntimeError('合成Docker停止失败')):
            with self.assertRaisesRegex(ValueError, '停止尚未确认'):
                self.service.pause(1, stop_round=True)
            self.join()
        current = self.service._one('SELECT * FROM warmup_pi_rounds WHERE id=?', (row['id'],))
        self.assertEqual('blocked', current['status'])
        self.assertEqual(native, current['runtime_json'])
        self.assertIsNotNone(current['segment_started_at'])
        self.assertEqual(0, self.account(1)['warmup_enabled'])
        self.assertIsNone(self.account(1)['warmup_next_run_at'])
        self.assertEqual('warmup', self.owners.owner(1)['kind'])
        self.assertIsNone(self.owners.claim(1, 'projects', 999))
        self.service.pause(1, stop_round=True)
        current = self.service._one('SELECT * FROM warmup_pi_rounds WHERE id=?', (row['id'],))
        self.assertEqual('stopped', current['status'])
        self.assertIsNone(current['runtime_json'])
        self.assertIsNone(self.owners.owner(1))

    def test_close_isolates_stop_failures_across_accounts_and_preserves_failed_runtime(self):
        """一个账号停止异常不会漏停其余账号，也不丢失失败账号现场或租约。:return: None。"""
        _, first = self.begin();self.tool('claude_start')
        self.enable(2);self.service.start(2)
        agent = self.service._one('SELECT * FROM warmup_pi_agents WHERE account_id=2')
        second = self.service._round(agent)
        self.service.tool(2, agent['generation'], 'claude_start', {}, 'second-start')
        original = self.terminal.control
        attempted = []

        def control(row, operation):
            attempted.append(row['account_id'])
            if row['account_id'] == 1:
                raise RuntimeError('合成单账号停止失败')
            return original(row, operation)

        with patch.object(self.terminal, 'control', side_effect=control):
            self.service.close()
        self.assertIn(2, attempted)
        self.assertIsNotNone(self.service._one('SELECT runtime_json FROM warmup_pi_rounds WHERE id=?', (first['id'],))['runtime_json'])
        self.assertIsNone(self.service._one('SELECT runtime_json FROM warmup_pi_rounds WHERE id=?', (second['id'],))['runtime_json'])
        self.assertEqual('warmup', self.owners.owner(1)['kind'])
        self.assertIsNone(self.owners.owner(2))
        self.assertIsNone(self.account(1)['warmup_next_run_at'])

    def test_split_draft_and_enter_cannot_finish_before_native_consumption(self):
        """文本和Enter分次投递也必须等到正常原生消费，不能把submit=False当作已取消。:return: None。"""
        _, row = self.begin();self.tool('claude_start')
        topic = json.loads(row['topic_json'])
        for index, text in enumerate([topic['prompt'], *topic['followups']]):
            observed = self.tool('claude_observe')
            self.tool('claude_input', {'observation_id': observed['observation_id'], 'text': text}, f'planned-{index}')
        observed = self.tool('claude_observe')
        self.tool('claude_input', {'observation_id': observed['observation_id'], 'text': 'Check one more export case.', 'submit': False}, 'draft')
        self.terminal.messages[row['id']] = self.terminal.messages[row['id']][:-2]
        observed = self.tool('claude_observe')
        self.tool('claude_input', {'observation_id': observed['observation_id'], 'keys': ['Enter'], 'submit': False}, 'enter')
        self.assertEqual('rejected', self.tool('round_finish', {'summary': 'Not consumed yet'}, 'finish-draft')['status'])

    def test_thread_start_failure_leaves_explicit_blocked_state_and_releases_owner(self):
        """线程未启动时不能残留假running或独占账号，原冻结轮可重试。:return: None。"""
        self.enable()
        with patch('warmup_pi.threading.Thread.start', side_effect=RuntimeError('synthetic failure')):
            with self.assertRaisesRegex(ValueError, '线程未能启动'):
                self.service.start(1)
        state = self.service.view(1)['agents'][0]
        self.assertEqual('blocked', state['status'])
        self.assertFalse(state['controller_active'])
        self.assertIsNone(self.owners.owner(1))
        self.assertIsNone(self.account(1)['warmup_next_run_at'])
        self.assertEqual('paused', state['round']['status'])
        self.assertEqual([], self.pi.calls)

    def test_finished_round_does_not_keep_a_hidden_retry_timer_over_the_authoritative_account_plan(self):
        """成功后原账号next为唯一正常计划，用户调整间隔后不会被旧恢复时刻挡住。:return: None。"""
        self.pi.mode = 'complete';self.enable();self.service.start(1);self.join()
        first = self.service.view(1)['agents'][0]['round']['id']
        self.assertIsNone(self.service._one('SELECT retry_at FROM warmup_pi_agents WHERE account_id=1')['retry_at'])
        self.service._write('UPDATE accounts SET warmup_next_run_at=? WHERE id=1', (time.time() - 1,))
        self.service.tick();self.join()
        self.assertEqual(2, len(self.pi.calls))
        self.assertNotEqual(first, self.service.view(1)['agents'][0]['round']['id'])

    def test_identity_changes_and_real_quota_gates_stop_the_same_round_without_resetting_budget(self):
        """真实额度门禁与身份变化停止当前轮，不靠恢复换题或清零预算。:return: None。"""
        _, row = self.begin();self.tool('claude_start')
        self.gate.update(allowed=False, retryable=False, reason='quota', message='实际额度已耗尽')
        result = self.tool('claude_observe')
        self.assertEqual('blocked', result['status'])
        self.assertEqual(1, len(self.terminal.started))
        self.assertEqual(row['id'], self.service.view(1)['agents'][0]['round']['id'])
        self.gate.update(allowed=True, retryable=False)
        self.service._write('UPDATE accounts SET cc2api_account_id=123 WHERE id=1')
        self.assertEqual('rejected', self.tool('topic_read')['status'])
        self.assertEqual([], self.terminal.sent)

    def test_snapshot_transaction_hands_concurrent_new_events_to_incremental_stream(self):
        """快照期间新增记录留在高水位之后，首次订阅无漏读也不重放旧屏幕。:return: None。"""
        _, row = self.begin();self.tool('claude_start');self.tool('claude_observe')
        connection = self.database();connection.execute('PRAGMA journal_mode=WAL');connection.close()
        original = self.service._read_events

        def append_after_watermark(connection, aid, before, limit):
            self.service._event(1, 'pi', {'text': 'New event during snapshot'}, row['id'])
            return original(connection, aid, before, limit)

        with patch.object(self.service, '_read_events', side_effect=append_after_watermark):
            snapshot = self.service.snapshot(1)
        later = self.service.events(1, snapshot['cursor'])
        self.assertEqual(['New event during snapshot'], [item['payload']['text'] for item in later])
        self.assertTrue(all(item['id'] > snapshot['cursor'] for item in later))
        self.assertNotIn(later[0]['id'], [item['id'] for item in snapshot['events']['items']])

    def test_partial_progress_and_elapsed_time_are_cached_public_facts_not_wall_clock_guesses(self):
        """运行进度使用当前segment累计，长暂停和私有路径不会混入公开摘要。:return: None。"""
        _, row = self.begin();self.tool('claude_start')
        now = time.time()
        self.service._write('UPDATE warmup_pi_rounds SET work_sec=15,started_at=?,segment_started_at=? WHERE id=?',
            (now - 7200, now - 30, row['id']))
        with patch('warmup_pi.time.time', return_value=now):
            state = self.service.view(1)['agents'][0]
        self.assertEqual(45, state['round']['work_sec'])
        self.assertEqual(45, state['progress']['elapsed_work_sec'])
        self.assertNotIn('runtime_json', state['round'])
        self.assertNotIn('account_identity', state['round'])
        with self.database() as connection:
            self.assertTrue(self.service.has_taken_over(1, connection=connection))
        self.assertFalse(self.service.has_taken_over(2))

    def test_snapshot_pagination_isolation_and_parameter_validation(self):
        """历史观测不重放，交互分页最新在前且隔离账号，原生状态只读。:return: None。"""
        _, row = self.begin();self.tool('claude_start');self.tool('claude_observe')
        for index in range(450):
            self.service._event(1, 'observation', {'screen': 'old-' + str(index)}, 'previous-round')
        for index in range(27):
            self.service._event(1, 'pi', {'text': 'interaction-' + str(index)}, row['id'])
        self.service._event(1, 'observation', {'screen': 'current-latest'}, row['id'])
        snapshot = self.service.snapshot(1)
        self.assertEqual('current-latest', snapshot['observation']['payload']['screen'])
        self.assertEqual([], self.service.events(1, snapshot['cursor']))
        page = snapshot['events']
        self.assertEqual(20, len(page['items']))
        self.assertEqual('interaction-26', page['items'][0]['payload']['text'])
        following = self.service.event_page(1, page['next_before'])
        self.assertFalse({item['id'] for item in page['items']} & {item['id'] for item in following['items']})
        self.assertEqual([], self.service.event_page(2)['items'])
        with self.assertRaisesRegex(ValueError, '游标不存在'):
            self.service.round_page(2, row['id'])
        application = FastAPI();application.include_router(warmup_pi_router(lambda: self.service))
        with TestClient(application) as client:
            prefix = '/api/accounts/warmup/pi'
            self.assertEqual(200, client.get(prefix + '/rounds/' + row['id']).status_code)
            self.assertEqual(422, client.get(prefix + '/agents/1/events/page?limit=101').status_code)
            self.assertEqual(422, client.get(prefix + '/agents/1/events/page?before=-1').status_code)
            self.assertEqual(422, client.put(prefix + '/agents/1', json={'instructions': '', 'budget_sec': True}).status_code)
            self.assertEqual(404, client.get(prefix + '/agents/2/rounds/page?before=' + row['id']).status_code)


if __name__ == '__main__':
    unittest.main()
