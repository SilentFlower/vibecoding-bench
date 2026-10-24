"""新 Projects 的真实 SQLite、控制权、未知输入和验收竞争回归。"""
import json
import sqlite3
import tempfile
import threading
import time
import unittest
from pathlib import Path
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from projects import ProjectsService
from projects_api import projects_router
from project_library import materialize_snapshot, read_document


class CatalogFixture:
    """提供两个账号可共享的只读工程合同。"""

    def __init__(self, root):
        """创建测试资产定位。:param root: 临时目录。:return: None。"""
        self.library = SimpleNamespace(root=root, digest='frozen-contract')
        self.definition = {'id': 'feature', 'goal': '修复实际行为', 'development_cycle': 'feature',
            'allowed_paths': ['library/app.py'], 'evaluation': {'native': 'private.json'}}

    def project(self, key, detail=True):
        """返回公开材料。:param key: 项目。:param detail: 详细标记。:return: 公开对象。"""
        if key not in ('example', 'other'):
            raise ValueError('项目不存在')
        return {'project_key': key, 'ready': True, 'objectives': [{'id': 'feature', 'goal': '修复实际行为'}]}

    def objective(self, key, objective_id):
        """返回冻结合同。:param key: 项目。:param objective_id: 目标。:return: 项目和目标。"""
        self.project(key)
        if objective_id != 'feature':
            raise ValueError('目标不存在')
        return SimpleNamespace(root=self.library.root), self.definition

    def listing(self):
        """列出项目。:return: 公开目录。"""
        return {'projects': [self.project('example'), self.project('other')]}

    def for_work(self, work):
        """核对夹具版本。:param work: 原工作。:return: 冻结目录。"""
        if work['library_digest'] != self.library.digest:
            raise ValueError('冻结版本不符')
        return self


class TerminalFixture:
    """模拟真实终端的菜单、文件和不确定投递结果。"""

    def __init__(self, root):
        """登记控制及发送证据。:param root: 临时根。:return: None。"""
        self.root, self.started, self.sent, self.controls = root, [], [], []
        self.unknown, self.running, self.screen = False, True, '请选择：\n> 调查\n  实施'

    def settings(self):
        """返回合法冻结配置。:return: CLI 配置。"""
        return {'claude_code_version': '2.1.293', 'claude_effort_level': 'high', 'execution_model': None}

    def start(self, account, work):
        """创建保留修改的物理目录。:param account: 账号。:param work: 工作。:return: 定位。"""
        self.started.append((account['id'], dict(work)))
        path = self.root / str(account['id']) / work['project_key'] / 'library'
        path.mkdir(parents=True, exist_ok=True)
        if not (path / 'app.py').exists():
            (path / 'app.py').write_text('VALUE = 1\n')
        return {'token': str(account['id']), 'source': f"projects:{work['id']}:{work['generation']}"}

    def workspace(self, work):
        """读取精确账号目录。:param work: 当前工作。:return: 工作目录。"""
        return self.root / str(work['account_id']) / work['project_key']

    def observe(self, work, cursor=0):
        """提供终端画面。:param work: 工作。:param cursor: 游标。:return: 实际画面。"""
        return {'screen': self.screen, 'events': [], 'cursor': cursor, 'running': self.running, 'quota_paused': False}

    def send(self, work, operation_id, text, keys, submit):
        """发送后可模拟丢失回执。:param work: 工作。:param operation_id: 操作。:param text: 文本。:param keys: 按键。:param submit: 提交。:return: None。"""
        self.sent.append((work['account_id'], operation_id, text, keys, submit))
        if self.unknown:
            raise RuntimeError('已发送但回执丢失')

    def control(self, work, operation):
        """记录定向控制。:param work: 工作。:param operation: 动作。:return: 实际结果。"""
        self.controls.append((work['id'], operation))
        return {'stopped': operation == 'stop'}

    def usage(self, work):
        """返回尚未提供的真实统计。:param work: 当前工作。:return: 未知用量。"""
        return {'complete': False}


class PiFixture:
    """等待取消的控制者，用于验证同账号启动与停止竞态。"""

    def __init__(self):
        """初始化同步信号。:return: None。"""
        self.entered = threading.Event()

    def available(self):
        """声明隔离夹具就绪。:return: True。"""
        return True

    def run(self, configuration, tools, event, stop, timeout_sec):
        """持有控制权至取消。:param configuration: 配置。:param tools: 工具。:param event: 事件。:param stop: 取消。:param timeout_sec: 时限。:return: stopped。"""
        self.entered.set()
        stop.wait(5)
        return 'stopped'


class ErrorPiFixture:
    """仅发出合成错误的 Pi，不访问模型或执行工具。"""

    def __init__(self, events):
        """保存合成事件和调用证据。:param events: 本轮事件。:return: None。"""
        self.events, self.calls = events, []

    def available(self):
        """声明隔离夹具就绪。:return: True。"""
        return True

    def run(self, configuration, tools, event, stop, timeout_sec):
        """发出失败并结束本轮。:param configuration: 配置。:param tools: 工具。:param event: 事件。:param stop: 取消。:param timeout_sec: 时限。:return: error。"""
        self.calls.append((configuration, timeout_sec))
        for value in self.events:
            event(value)
        return 'error'


class ResumingPiFixture(PiFixture):
    """只恢复一次原 Claude 工作，再等待人工停止的隔离控制者。"""

    def __init__(self):
        """创建恢复结果和调用记录。:return: None。"""
        super().__init__()
        self.calls, self.result = [], None

    def run(self, configuration, tools, event, stop, timeout_sec):
        """恢复原工作并等待取消。:param configuration: 配置。:param tools: 工具。:param event: 事件。:param stop: 取消。:param timeout_sec: 时限。:return: stopped。"""
        self.calls.append((configuration, timeout_sec))
        self.result = tools('claude_start', {'project_key': 'example', 'objective_id': 'feature'}, 'resume-original')
        return super().run(configuration, tools, event, stop, timeout_sec)


class ProjectsAgentTests(unittest.TestCase):
    """验证新架构独立于旧阶段脚本的业务及恢复行为。"""

    def setUp(self):
        """创建独立 SQLite 与物理工作区。:return: None。"""
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.path = self.root / 'db.sqlite'
        connection = self.database()
        connection.executescript('CREATE TABLE accounts(id INTEGER PRIMARY KEY); INSERT INTO accounts VALUES(1),(2);')
        connection.close()
        self.catalog, self.terminal, self.pi = CatalogFixture(self.root), TerminalFixture(self.root / 'work'), PiFixture()
        self.allowed = True
        self.verification = {'status': 'failed', 'feedback': ['实际行为不符合要求']}
        self.service = ProjectsService(self.root, self.database, threading.Lock(), self.catalog, self.terminal,
            lambda account_id: {'id': account_id, 'name': str(account_id)} if account_id in (1, 2) else None,
            lambda *_: {'allowed': self.allowed, 'message': '等待额度'},
            lambda: {'models': ['test'], 'base_url': 'https://example.invalid/v1', 'api_key': 'test-key'},
            lambda *_: self.verification, self.pi)
        self.addCleanup(self.service.close)

    def database(self):
        """返回独立 SQLite 连接。:return: 使用字典行的连接。"""
        connection = sqlite3.connect(self.path, timeout=5)
        connection.row_factory = sqlite3.Row
        connection.execute('PRAGMA foreign_keys=ON')
        return connection

    def activate(self, account_id=1, keys=None):
        """直接赋予夹具控制代次。:param account_id: 账号。:param keys: 授权池。:return: 当前代次。"""
        self.service.configure(account_id, keys or ['example'])
        self.service._write("UPDATE projects_agents SET generation=generation+1,status='running' WHERE account_id=?", (account_id,))
        return self.service._one('SELECT generation FROM projects_agents WHERE account_id=?', (account_id,))['generation']

    def tool(self, name, args=None, call_id='call', account_id=1, generation=1):
        """调用真实工具边界。:param name: 工具。:param args: 参数。:param call_id: 调用标识。:param account_id: 账号。:param generation: 代次。:return: 结果。"""
        return self.service.tool(account_id, generation, name, args or {}, call_id)

    def start_work(self, account_id=1):
        """开启夹具工程。:param account_id: 账号。:return: 工具结果。"""
        return self.tool('claude_start', {'project_key': 'example', 'objective_id': 'feature'}, account_id=account_id)

    def prepare_filter_blocked(self, account_id=1, operator=False):
        """保留原会话和已耗预算，构造已确认过滤的现场。:param account_id: 账号。:param operator: 是否为旧事件的人工诊断。:return: 原工作、故障事件和 Pi 会话路径。"""
        generation = self.activate(account_id)
        self.service.configure(account_id, ['example'], budget_sec=1800)
        result = self.start_work(account_id)
        work = self.service._one('SELECT * FROM projects_work WHERE id=?', (result['work_id'],))
        self.service._release(work, 'blocked')
        self.service._write('UPDATE projects_work SET work_sec=? WHERE id=?', (165.04067087173462, work['id']))
        session_file = self.root / 'projects/agents' / str(account_id) / 'original.jsonl'
        session_file.parent.mkdir(parents=True)
        session_file.write_text('{}\n')
        self.service._pi_event(account_id, generation, {'type': 'ready', 'session_file': str(session_file)})
        if operator:
            self.service._event(account_id, 'error', {'message': '旧版通用模型错误'}, work['id'])
            original_id = self.service.events(account_id)[-1]['id']
            self.service._event(account_id, 'error', {'reason': 'provider_content_filter', 'source': 'operator_diagnosis',
                'diagnostic_of_event_id': original_id}, work['id'], f'operator-diagnosis:provider-content-filter:event-{original_id}')
            # 部署和 recover 只递增控制代次，原工作的执行代次与已核实错误仍保持绑定。
            self.service._write('UPDATE projects_agents SET generation=generation+2 WHERE account_id=?', (account_id,))
        else:
            self.service._pi_event(account_id, generation, {'type': 'error', 'reason': 'provider_content_filter', 'message': '模型过滤'})
        self.service.configure_schedule(account_id, True)
        self.service._write("UPDATE projects_agents SET status='blocked',schedule_state='blocked',schedule_next_at=NULL WHERE account_id=?", (account_id,))
        return self.service._one('SELECT * FROM projects_work WHERE id=?', (work['id'],)), self.service.events(account_id)[-2], session_file

    def test_menu_and_multiline_input_use_actual_observation_and_never_replay(self):
        """菜单与中段粘贴正文无需固定回复匹配；重复调用不会重复发送。:return: None。"""
        self.activate(); self.start_work()
        observed = self.tool('claude_observe')
        menu = self.tool('claude_input', {'observation_id': observed['observation_id'], 'keys': ['Down', 'Enter'], 'submit': False}, 'menu')
        self.assertEqual('sent', menu['status'])
        self.assertEqual(1, len(self.terminal.sent))
        self.assertEqual('rejected', self.tool('claude_input', {'observation_id': observed['observation_id'], 'text': '旧画面'}, 'stale')['status'])
        observed = self.tool('claude_observe')
        text = '先核对源码。\n<pasted_content id="a">\n完整业务正文\n</pasted_content id="a">\n保留兼容性。'
        args = {'observation_id': observed['observation_id'], 'text': text}
        sent = self.tool('claude_input', args, 'exact-text')
        replay = self.tool('claude_input', args, 'exact-text')
        self.assertEqual(sent['operation_id'], replay['operation_id'])
        self.assertTrue(replay['replayed'])
        self.assertEqual(2, len(self.terminal.sent))
        self.assertEqual(text, self.terminal.sent[-1][2])

    def test_account_state_lists_all_remaining_objectives_after_one_project_passes(self):
        """完整目标索引排除已完成项，Pi 不需要抽查研究来猜测整个授权池。

        :return: None。
        """
        self.activate(keys=['example', 'other'])
        self.start_work()
        self.verification = {'status': 'passed', 'feedback': []}
        self.tool('project_submit', {'summary': '已通过第一个工程目标'})
        agent = self.tool('account_state')['agents'][0]
        self.assertEqual([{'project_key': 'other', 'objective_id': 'feature', 'goal': '修复实际行为'}],
            agent['available_objectives'])
        self.assertEqual('example', agent['passed'][0]['project_key'])

    def test_six_hundred_objectives_keep_a_complete_model_index_without_duplicate_payload(self):
        """600项保持完整可启动索引，未完成总数不再携带重复正文。:return: None。"""
        self.activate()
        objectives = [{'id': f'goal-{index}', 'goal': f'独立完整工程交付{index}'} for index in range(600)]
        self.catalog.project = lambda key, detail=False: {'project_key': key, 'ready': True,
            'objectives': objectives}
        full = self.service.state(1)['agents'][0]
        model = self.tool('account_state')['agents'][0]
        self.assertEqual(600, model['remaining_objective_count'])
        self.assertEqual({item['id'] for item in objectives},
            {item['objective_id'] for item in model['available_objectives']})
        self.assertEqual([], model['waiting_objectives'])
        self.assertNotIn('remaining_objectives', model)
        self.assertLess(len(json.dumps(model, ensure_ascii=False)), len(json.dumps(full, ensure_ascii=False)) * 0.6)

    def test_two_accounts_are_isolated_and_pool_cannot_be_extended_by_model(self):
        """同目标的两账号使用不同工作目录、会话与工具归属。:return: None。"""
        self.activate(1); self.activate(2)
        one, two = self.start_work(1), self.start_work(2)
        self.assertNotEqual(one['session_id'], two['session_id'])
        self.assertEqual('rejected', self.tool('project_read', {'project_key': 'other'})['status'])
        for account_id in (1, 2):
            observation = self.tool('claude_observe', account_id=account_id)
            self.tool('claude_input', {'observation_id': observation['observation_id'], 'text': str(account_id)},
                account_id=account_id)
        self.assertEqual([1, 2], [item[0] for item in self.terminal.sent])

    def test_unknown_input_blocks_other_actions_and_requires_manual_reconciliation(self):
        """已发送但回执丢失时保留原意图，不能换调用ID重发或自行解锁。:return: None。"""
        self.activate(); self.start_work(); self.terminal.unknown = True
        observation = self.tool('claude_observe')
        result = self.tool('claude_input', {'observation_id': observation['observation_id'], 'text': '实施'}, 'uncertain')
        self.assertEqual('unknown', result['status'])
        self.assertEqual('rejected', self.tool('claude_input', {'observation_id': observation['observation_id'], 'text': '实施'}, 'other')['status'])
        with self.assertRaisesRegex(ValueError, '未对账'):
            self.service.start(1)
        self.service.pause(1)
        self.service.reconcile(1, result['operation_id'], True)
        self.assertEqual([], self.service.actions(1))
        self.assertEqual(1, len(self.terminal.sent))

    def test_pause_rejects_old_generation_before_any_terminal_write(self):
        """人工暂停优先于迟到的模型输入。:return: None。"""
        self.activate(); self.start_work(); observation = self.tool('claude_observe')
        self.service.pause(1)
        result = self.tool('claude_input', {'observation_id': observation['observation_id'], 'text': '不得发送'})
        self.assertEqual('rejected', result['status']); self.assertEqual([], self.terminal.sent)

    def test_quota_release_and_resume_keep_original_session_files_and_budget(self):
        """额度等待释放执行，恢复保留半成品、原会话和累计工作时间。:return: None。"""
        self.activate(); original = self.start_work()
        work = self.service._one('SELECT * FROM projects_work WHERE id=?', (original['work_id'],))
        (self.terminal.workspace(work) / 'library/app.py').write_text('VALUE = 2\n')
        self.service._write('UPDATE projects_work SET segment_started_at=? WHERE id=?', (time.time() - 12, work['id']))
        self.allowed = False
        self.assertEqual('waiting', self.tool('claude_observe')['status'])
        self.allowed = True
        resumed = self.start_work()
        self.assertEqual(original['session_id'], resumed['session_id'])
        self.assertLess(self.terminal.started[-1][1]['remaining_sec'], 3600)
        self.assertEqual('VALUE = 2\n', (self.terminal.workspace(work) / 'library/app.py').read_text())

    def test_actual_verification_failure_does_not_finish_work(self):
        """模型的完成说明不能覆盖独立失败，原会话可以返工再提交。:return: None。"""
        self.activate(); result = self.start_work()
        failed = self.tool('project_submit', {'summary': '已经全部完成'})
        self.assertEqual('failed', failed['status'])
        self.assertEqual('running', self.service.state(1)['agents'][0]['work']['status'])
        self.verification = {'status': 'passed', 'feedback': ['独立验证通过']}
        passed = self.tool('project_submit', {'summary': '实际修复后再次交付'})
        self.assertEqual('passed', passed['status'])
        self.assertEqual(1, len(self.service.state(1)['agents'][0]['passed']))
        self.assertEqual('rejected', self.start_work()['status'])

    def test_stop_during_verification_cannot_accept_or_resume_old_process(self):
        """验收期间停止优先，迟到通过不能增加完成数或恢复已停止进程。:return: None。"""
        self.activate(); self.start_work()
        def finish(*_):
            self.service.pause(1, stop_work=True)
            return {'status': 'passed'}
        self.service.verifier = finish
        result = self.tool('project_submit', {'summary': '交付'})
        self.assertEqual('rejected', result['status'])
        self.assertEqual([], self.service.state(1)['agents'][0]['passed'])
        self.assertNotIn('resume', [operation for _, operation in self.terminal.controls])

    def test_restart_reserves_elapsed_work_and_preserves_unknown_input(self):
        """重启不能重置累计预算，未确认输入仍需对账。:return: None。"""
        self.activate(); result = self.start_work()
        self.service._write('UPDATE projects_work SET segment_started_at=? WHERE id=?', (time.time() - 25, result['work_id']))
        self.service._write("INSERT INTO projects_actions(id,work_id,generation,request_json,status,created_at) VALUES(?,?,?,?,?,?)",
            ('pending', result['work_id'], 1, '{}', 'intent', time.time()))
        self.service.recover()
        state = self.service.state(1)['agents'][0]
        self.assertEqual('blocked', state['work']['status'])
        self.assertGreaterEqual(state['work']['work_sec'], 25)
        self.assertEqual('blocked', state['status'])
        with self.assertRaises(ValueError): self.service.start(1)

    def test_same_account_start_is_idempotent_until_process_has_stopped(self):
        """重复启动和暂停并发时，同账号始终只有一个控制者。:return: None。"""
        self.service.configure(1, ['example'])
        self.service.start(1); self.assertTrue(self.pi.entered.wait(2))
        generation = self.service.state(1)['agents'][0]['generation']
        self.service.start(1)
        self.assertEqual(generation, self.service.state(1)['agents'][0]['generation'])
        thread = self.service.controllers[1][0]
        self.service.pause(1); thread.join(timeout=3)
        self.assertFalse(thread.is_alive()); self.assertNotIn(1, self.service.controllers)

    def test_pi_error_event_only_exposes_known_reason(self):
        """错误事件只公开定义过的类别，其他上游字段不能透传。:return: None。"""
        generation = self.activate()
        for reason in ('provider_content_filter', 'unknown-provider-detail', None):
            with self.subTest(reason=reason):
                self.service._pi_event(1, generation, {'type': 'error', 'message': '模型请求失败',
                    'reason': reason, 'raw': '不应公开的上游正文'})
                expected = {'message': '模型请求失败'}
                if reason == 'provider_content_filter':
                    expected['reason'] = reason
                    expected['generation'] = generation
                self.assertEqual(expected, self.service.events(1)[-1]['payload'])

    def test_content_filter_blocks_run_and_schedule_without_reset_or_restart(self):
        """内容过滤保留原工作与预算，定时扫描和重启恢复都不能自动重试。:return: None。"""
        generation = self.activate()
        self.service.configure(1, ['example'], budget_sec=1800)
        original = self.start_work()
        work = self.service._one('SELECT * FROM projects_work WHERE id=?', (original['work_id'],))
        self.service._release(work, 'paused')
        self.service._write('UPDATE projects_work SET work_sec=? WHERE id=?', (165.04067087173462, work['id']))
        session_file = self.root / 'projects/agents/1/original.jsonl'
        session_file.parent.mkdir(parents=True)
        session_file.write_text('{}\n')
        self.service._pi_event(1, generation, {'type': 'ready', 'session_file': str(session_file)})
        self.service.configure_schedule(1, True)
        message = 'Pi 上游模型返回内容过滤，原工作已保留，需人工核对后恢复'
        pi = ErrorPiFixture([{'type': 'error', 'reason': 'provider_content_filter', 'message': message}])
        self.service.pi = pi

        self.service._run(1, generation, {'models': ['primary', 'backup']}, threading.Event())

        agent = self.service._one('SELECT * FROM projects_agents WHERE account_id=1')
        saved = self.service._one('SELECT * FROM projects_work WHERE id=?', (work['id'],))
        self.assertEqual(('blocked', message, 'blocked', message, None),
            tuple(agent[key] for key in ('status', 'message', 'schedule_state', 'schedule_message', 'schedule_next_at')))
        self.assertEqual(1, agent['schedule_enabled'])
        self.assertEqual(1800, agent['budget_sec'])
        self.assertEqual(str(session_file), agent['session_file'])
        self.assertEqual(work['id'], agent['current_work_id'])
        self.assertEqual(work['session_id'], saved['session_id'])
        self.assertEqual('blocked', saved['status'])
        self.assertEqual(165.04067087173462, saved['work_sec'])
        self.assertIsNone(saved['runtime_json'])
        self.assertIsNone(saved['segment_started_at'])
        self.assertEqual(1800, pi.calls[0][1])
        self.assertEqual(str(session_file), pi.calls[0][0]['session_file'])
        self.assertEqual({'message': message, 'reason': 'provider_content_filter', 'generation': generation},
            self.service.events(1)[-1]['payload'])

        self.service.tick(time.time() + 86400)
        self.service.recover()
        self.service.tick(time.time() + 172800)
        self.assertEqual(1, len(pi.calls))
        self.assertEqual(1, len(self.terminal.started))
        self.assertEqual([], self.terminal.sent)
        self.assertEqual([], self.service.actions(1))
        restored = self.service._one('SELECT * FROM projects_work WHERE id=?', (work['id'],))
        self.assertEqual(('blocked', 165.04067087173462), (restored['status'], restored['work_sec']))

    def test_unknown_pi_reason_does_not_inherit_content_filter_from_previous_events(self):
        """旧过滤事件与本轮任意类别不能改变当前通用失败说明。:return: None。"""
        generation = self.activate()
        self.service.configure_schedule(1, True)
        self.service._pi_event(1, generation, {'type': 'error', 'reason': 'provider_content_filter', 'message': '旧轮错误'})
        self.service.pi = ErrorPiFixture([{'type': 'error', 'reason': 'untrusted-provider-detail', 'message': '模型请求失败'}])

        self.service._run(1, generation, {}, threading.Event())

        agent = self.service._one('SELECT * FROM projects_agents WHERE account_id=1')
        self.assertEqual('blocked', agent['status'])
        self.assertEqual('Pi 运行失败，请查看事件并检查模型工具调用兼容性', agent['message'])
        self.assertEqual('Pi 运行异常，等待人工核对后重新启用或启动', agent['schedule_message'])
        self.assertEqual('blocked', agent['schedule_state'])
        self.assertIsNone(agent['schedule_next_at'])
        self.assertEqual({'message': '模型请求失败'}, self.service.events(1)[-1]['payload'])

    def test_manual_start_retries_only_original_model_and_sessions_once(self):
        """明确人工启动可恢复已核实故障，旧诊断跨服务代次仍使用原会话与累计预算。:return: None。"""
        for account_id, operator in ((1, False), (2, True)):
            with self.subTest(operator_diagnosis=operator):
                work, error, session_file = self.prepare_filter_blocked(account_id, operator)
                pi = ResumingPiFixture()
                self.service.pi = pi
                self.service.start(account_id)
                self.assertTrue(pi.entered.wait(2))
                self.service.start(account_id)
                agent = self.service._one('SELECT * FROM projects_agents WHERE account_id=?', (account_id,))
                resumed = self.service._one('SELECT * FROM projects_work WHERE id=?', (work['id'],))
                self.assertEqual('running', agent['status'])
                self.assertEqual('running', pi.result['status'])
                self.assertEqual(work['id'], pi.result['work_id'])
                self.assertEqual(work['session_id'], pi.result['session_id'])
                self.assertEqual(work['work_sec'], resumed['work_sec'])
                self.assertEqual(1800, agent['budget_sec'])
                self.assertEqual(1634, self.terminal.started[-1][1]['remaining_sec'])
                self.assertEqual(str(session_file), pi.calls[0][0]['session_file'])
                self.assertEqual(['test'], pi.calls[0][0]['models'])
                self.assertEqual(1, len(pi.calls))
                audit = [item for item in self.service.events(account_id) if item['kind'] == 'manual_retry']
                self.assertEqual(1, len(audit))
                self.assertEqual(error['id'], audit[0]['payload']['error_event_id'])
                self.assertEqual([], self.terminal.sent)
                controller = self.service.controllers[account_id][0]
                self.service.pause(account_id)
                controller.join(2)

    def test_scheduled_start_cannot_release_a_confirmed_filter_block(self):
        """开启计划和到点扫描都不能代替人工决定重试已过滤的原任务。:return: None。"""
        work, _, _ = self.prepare_filter_blocked()
        self.service.configure_schedule(1, True)
        self.service.start(1, scheduled=True, now=time.time() + 1)
        self.service.tick(time.time() + 86400)
        self.assertFalse(self.pi.entered.is_set())
        self.assertEqual('blocked', self.service._one('SELECT status FROM projects_work WHERE id=?', (work['id'],))['status'])
        self.assertEqual([], [item for item in self.service.events(1) if item['kind'] == 'manual_retry'])

    def test_manual_retry_does_not_bypass_other_blocking_facts(self):
        """人工重试不解除未知输入、身份变化、预算耗尽、合同变化或更新故障。:return: None。"""
        work, error, _ = self.prepare_filter_blocked()
        original_account = self.service.account
        original_payload = self.service._one('SELECT payload_json FROM projects_events WHERE id=?', (error['id'],))['payload_json']
        last_event_id = self.service.events(1)[-1]['id']
        for condition in ('unknown', 'identity', 'budget', 'contract', 'other_error', 'stale_generation', 'untrusted_diagnosis', 'newer_start'):
            with self.subTest(condition=condition):
                if condition == 'unknown':
                    self.service._write("INSERT INTO projects_actions(id,work_id,generation,request_json,status,created_at) VALUES(?,?,?,?,?,?)",
                        ('pending', work['id'], work['generation'], '{}', 'unknown', time.time()))
                elif condition == 'identity':
                    self.service.account = lambda account_id: {'id': account_id, 'cc2api_account_id': 99}
                elif condition == 'budget':
                    self.service._write('UPDATE projects_work SET work_sec=1800 WHERE id=?', (work['id'],))
                elif condition == 'contract':
                    self.service._write("UPDATE projects_work SET definition_json='{}' WHERE id=?", (work['id'],))
                elif condition == 'other_error':
                    self.service._event(1, 'error', {'message': '执行收口未确认'}, work['id'])
                elif condition == 'stale_generation':
                    payload = json.loads(original_payload)
                    payload['generation'] += 1
                    self.service._write('UPDATE projects_events SET payload_json=? WHERE id=?', (json.dumps(payload), error['id']))
                elif condition == 'untrusted_diagnosis':
                    self.service._event(1, 'error', {'reason': 'provider_content_filter', 'source': 'operator_diagnosis',
                        'diagnostic_of_event_id': error['id']}, work['id'])
                else:
                    self.service._event(1, 'started', {'session_id': work['session_id']}, work['id'])
                before = self.service._one('SELECT * FROM projects_work WHERE id=?', (work['id'],))
                with self.assertRaises(ValueError):
                    self.service.start(1)
                self.assertEqual(before, self.service._one('SELECT * FROM projects_work WHERE id=?', (work['id'],)))
                self.assertFalse(self.pi.entered.is_set())
                self.assertEqual([], [item for item in self.service.events(1) if item['kind'] == 'manual_retry'])
                self.service.account = original_account
                self.service._write('DELETE FROM projects_actions WHERE id=?', ('pending',))
                self.service._write('DELETE FROM projects_events WHERE id>?', (last_event_id,))
                self.service._write('UPDATE projects_events SET payload_json=? WHERE id=?', (original_payload, error['id']))
                self.service._write('UPDATE projects_work SET work_sec=?,definition_json=? WHERE id=?',
                    (work['work_sec'], work['definition_json'], work['id']))

    def test_failed_manual_retry_admission_and_provider_leave_work_blocked(self):
        """准入或模型配置不可用时不能提前修改原工作或发布重试审计。:return: None。"""
        work, _, _ = self.prepare_filter_blocked()
        self.allowed = False
        self.service.start(1)
        self.assertEqual(work, self.service._one('SELECT * FROM projects_work WHERE id=?', (work['id'],)))
        self.assertIsNone(self.service._one('SELECT schedule_next_at FROM projects_agents WHERE account_id=1')['schedule_next_at'])
        self.allowed = True
        self.service.provider = lambda: None
        with self.assertRaisesRegex(ValueError, '尚未就绪'):
            self.service.start(1)
        self.assertEqual(work, self.service._one('SELECT * FROM projects_work WHERE id=?', (work['id'],)))
        self.assertEqual([], [item for item in self.service.events(1) if item['kind'] == 'manual_retry'])
        self.assertFalse(self.pi.entered.is_set())

    def test_api_uses_strict_types_and_manual_reconcile_route_is_reachable(self):
        """接口拒绝布尔账号字段与未知字段，人工对账不会被动作路由遮挡。:return: None。"""
        app = FastAPI(); app.include_router(projects_router(lambda: self.service))
        with TestClient(app) as client:
            self.assertEqual(422, client.put('/api/projects/agents/1', json={'project_keys': ['example'], 'budget_sec': True}).status_code)
            self.assertEqual(200, client.put('/api/projects/agents/1', json={'project_keys': ['example']}).status_code)
            self.assertEqual(409, client.post('/api/projects/agents/1/reconcile', json={'operation_id': 'unknown', 'sent': False}).status_code)
            self.assertEqual(422, client.get('/api/projects/agents/1/events?after=-1').status_code)

    def test_stop_while_preparing_cannot_publish_a_late_running_work(self):
        """环境准备期间停止后，迟到的启动结果必须收口，不能重写为运行中。:return: None。"""
        self.activate()
        original = self.terminal.start
        def delayed(account, work):
            result = original(account, work)
            self.service.pause(1, stop_work=True)
            return result
        self.terminal.start = delayed
        result = self.start_work()
        self.assertEqual('rejected', result['status'])
        state = self.service.state(1)['agents'][0]
        self.assertEqual('stopped', state['work']['status'])
        self.assertEqual('paused', state['status'])
        self.assertEqual(1, len(self.terminal.controls))

    def test_stop_before_reservation_leaves_no_invisible_active_work(self):
        """创建目标前停止时，不留下无法从控制者找到的唯一索引占用。:return: None。"""
        self.activate()
        settings = self.terminal.settings
        def stop_before_creation():
            self.service.pause(1)
            return settings()
        self.terminal.settings = stop_before_creation
        self.assertEqual('rejected', self.start_work()['status'])
        self.assertEqual([], self.service.history(1))

    def test_duplicate_release_does_not_double_charge_elapsed_work(self):
        """暂停与额度收口竞争时，同一片段只结算一次且只停止一次。:return: None。"""
        self.activate(); result = self.start_work()
        self.service._write('UPDATE projects_work SET segment_started_at=? WHERE id=?', (time.time() - 12, result['work_id']))
        work = self.service._one('SELECT * FROM projects_work WHERE id=?', (result['work_id'],))
        self.service._release(work, 'paused'); self.service._release(work, 'paused')
        charged = self.service.state(1)['agents'][0]['work']['work_sec']
        self.assertGreaterEqual(charged, 12); self.assertLess(charged, 15)
        self.assertEqual(1, len(self.terminal.controls))

    def test_service_restart_restores_enabled_control_but_manual_pause_stays_paused(self):
        """服务关闭保留恢复意图；人工暂停不会被重启重新启用。:return: None。"""
        self.service.configure(1, ['example']); self.service.start(1)
        self.assertTrue(self.pi.entered.wait(2)); self.service.close()
        self.assertEqual('interrupted', self.service.state(1)['agents'][0]['status'])
        pi = PiFixture()
        recovered = ProjectsService(self.root, self.database, threading.Lock(), self.catalog, self.terminal,
            self.service.account, self.service.admission, self.service.provider, self.service.verifier, pi)
        self.addCleanup(recovered.close)
        recovered.recover(); self.assertTrue(pi.entered.wait(2))
        self.assertEqual('running', recovered.state(1)['agents'][0]['status'])
        thread = recovered.controllers[1][0]
        recovered.pause(1); thread.join(timeout=2); recovered.close()
        self.assertEqual('paused', recovered.state(1)['agents'][0]['status'])

    def test_delivery_preview_reads_only_verified_frozen_candidate_files(self):
        """交付预览按冻结清单和摘要读取，拒绝私有材料、越界和后续篡改。:return: None。"""
        self.activate(); started = self.start_work()
        work = self.service._one('SELECT * FROM projects_work WHERE id=?', (started['work_id'],))
        (self.terminal.workspace(work) / 'library/app.py').write_text('VALUE = 2\n')
        result = self.tool('project_submit', {'summary': '提供可审查交付'})
        submission = result['submission_id']
        directory = self.root / 'projects/submissions' / submission
        materialize_snapshot(read_document(directory / 'snapshot.json'), self.root / 'projects/objects', directory / 'candidate')
        self.assertEqual('VALUE = 2\n', self.service.submission(submission, 'library/app.py')['text'])
        self.assertEqual('library/app.py', self.service.submission(submission)['files'][0]['path'])
        for path in ('../private-review.json', 'private-review.json', '/etc/passwd'):
            with self.assertRaises(ValueError): self.service.submission(submission, path)
        (directory / 'candidate/library/app.py').write_text('VALUE = 9\n')
        with self.assertRaises(ValueError): self.service.submission(submission, 'library/app.py')


if __name__ == '__main__':
    unittest.main()
