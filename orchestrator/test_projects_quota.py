"""通过真实会话文件验证 Projects 原生额度与认证补证，不连接任何账号。"""
import json
import tempfile
import time
import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

from projects_runtime import ProjectsTerminal


class ProjectsPassiveQuotaTests(unittest.TestCase):
    """核对结构化证据、账号绑定、原生会话边界和持久去重。"""

    def setUp(self):
        """创建两个隔离账号及真实 JSONL 文件目录。:return: None。"""
        temporary = tempfile.TemporaryDirectory(prefix='projects-passive-quota-')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.jobs, self.observations = {}, []
        self.runtime = SimpleNamespace(data=self.root,
            job_for_container=lambda token: self.jobs[token],
            _root=lambda row: self.root / 'environments' / row['environment_id'])
        self.terminal = self.new_terminal()
        self.work, self.native = self.account(1)
        self.other, self.other_native = self.account(2)

    def new_terminal(self):
        """构造只读适配器，补证回调仅记录本地对象。:return: 终端适配器。"""
        return ProjectsTerminal(self.runtime, None, None, None,
            quota_observation=lambda account, source, facts: self.observations.append((account['id'], source, facts)))

    def account(self, account_id):
        """登记精确账号、工作与原生目录。:param account_id: 合成账号。:return: 工作和会话文件。"""
        identifier = str(account_id) * 32
        session = f'00000000-0000-4000-8000-{account_id:012d}'
        source = f'projects:{identifier}:1'
        row = {'environment_id': identifier, 'account_id': account_id}
        directory = self.root / 'environments' / identifier / 'home/.claude/projects/-home-node-projects-example'
        directory.mkdir(parents=True)
        token = 'account-' + str(account_id)
        self.jobs[token] = {'row': row, 'account': {'id': account_id}, 'source': source,
            'cwd': '/home/node/projects/example'}
        work = {'id': identifier, 'account_id': account_id, 'generation': 1, 'session_id': session,
            'created_at': time.time() - 120, 'started_at': time.time() - 60,
            'segment_started_at': time.time() - 30,
            'runtime_json': json.dumps({'token': token, 'source': source, 'native': str(directory.relative_to(self.root))})}
        return work, directory / (session + '.jsonl')

    def event(self, error='rate_limit', **fields):
        """生成与官方错误记录相同的结构。:param error: 原生错误类别。:param fields: 覆盖元数据。:return: 错误对象。"""
        return {'type': 'assistant', 'uuid': 'native-error-1', 'sessionId': self.work['session_id'],
            'timestamp': datetime.fromtimestamp(time.time() - 1, timezone.utc).isoformat(),
            'isApiErrorMessage': True, 'error': error,
            'message': {'role': 'assistant', 'model': '<synthetic>', 'content': '不解析这个普通文本字段'}, **fields}

    def append(self, *events, path=None):
        """向真实 JSONL 追加完整记录。:param events: 记录。:param path: 可选第二账号文件。:return: None。"""
        with (path or self.native).open('a') as output:
            for event in events:
                output.write(json.dumps(event) + '\n')

    def test_structured_rejected_window_keeps_trusted_reset_and_owner(self):
        """官方 rejected 元数据提供可信窗口与重置，回调精确绑定原账号和来源。:return: None。"""
        reset = time.time() + 3600
        self.append(self.event(quotaLimits={'status': 'rejected', 'rateLimitType': 'five_hour', 'resetsAt': reset}))
        facts = self.terminal.passive_status(self.work)
        self.assertTrue(facts['quota_limited'])
        self.assertEqual('five_hour', facts['window'])
        self.assertEqual(reset, facts['retry_at'])
        self.assertIsNone(facts['account_error'])
        self.assertEqual((1, 'projects:' + self.work['id'] + ':1', facts), self.observations[0])

    def test_structured_api_error_parameters_are_supported(self):
        """官方 usage_limit_reached 的结构化参数也可提供可信恢复时间。:return: None。"""
        reset = time.time() + 86400
        self.append(self.event(apiError='usage_limit_reached', apiErrorParams={
            'rate_limit_info': {'status': 'rejected', 'rateLimitType': 'seven_day', 'resetsAt': reset}}))
        facts = self.terminal.passive_status(self.work)
        self.assertEqual('seven_day', facts['window'])
        self.assertEqual(reset, facts['retry_at'])

    def test_limit_without_trusted_reset_stays_unknown(self):
        """不从错误正文猜测时区或重置时间，无结构化 reset 时维持未知。:return: None。"""
        value = self.event()
        value['message']['content'] = "You've hit your limit · resets 9am; invalid_grant"
        self.append(value)
        facts = self.terminal.passive_status(self.work)
        self.assertTrue(facts['quota_limited'])
        self.assertEqual('unknown', facts['window'])
        self.assertIsNone(facts['retry_at'])
        self.assertIsNone(facts['account_error'])

    def test_expired_or_invalid_reset_never_manufactures_future_budget(self):
        """过期、布尔和异常遥远的 reset 不能成为自动恢复承诺。:return: None。"""
        for index, reset in enumerate((True, time.time() - 2, time.time() + 10 * 86400)):
            self.append(self.event(uuid=f'invalid-reset-{index}', quotaLimits={
                'status': 'rejected', 'rateLimitType': 'five_hour', 'resetsAt': reset}))
            self.assertIsNone(self.terminal.passive_status(self.work)['retry_at'])

    def test_ordinary_assistant_user_and_sidechain_never_set_account_gate(self):
        """普通讨论中的限额和认证字样、用户伪造文本及旁支均不能变成账号事实。:return: None。"""
        ordinary = self.event(isApiErrorMessage=False)
        ordinary['message'] = {'role': 'assistant', 'model': 'claude',
            'content': '请检查rate_limit、invalid_grant、account_on_hold与额度100%'}
        user = self.event(uuid='user-record')
        user['message']['role'] = 'user'
        self.append(ordinary, user, self.event(uuid='sidechain', isSidechain=True),
            self.event(uuid='foreign-session', sessionId=self.other['session_id']))
        facts = self.terminal.passive_status(self.work)
        self.assertFalse(facts['quota_limited'])
        self.assertIsNone(facts['account_error'])
        self.assertEqual([], self.observations)

    def test_explicit_transient_429_is_not_claimed_as_account_exhaustion(self):
        """官方明确标记暂时容量错误时，不把它写成账号额度耗尽。:return: None。"""
        self.append(self.event(apiErrorIsTransient=True))
        self.assertFalse(self.terminal.passive_status(self.work)['quota_limited'])
        self.assertEqual([], self.observations)

    def test_authentication_errors_map_only_structured_native_types(self):
        """认证门禁只接受官方错误类型，authentication_failed 与既有 guard 分类兼容。:return: None。"""
        for index, (native, expected) in enumerate((('account_on_hold', 'account_on_hold'),
                ('invalid_grant', 'invalid_grant'), ('authentication_failed', 'invalid_grant'))):
            self.append(self.event(error=native, uuid=f'auth-{index}'))
            facts = self.terminal.passive_status(self.work)
            self.assertEqual(expected, facts['account_error'])
            self.assertEqual(native, facts['native_error'])
            self.assertFalse(facts['quota_limited'])

    def test_repeat_read_and_recreated_adapter_do_not_replay_evidence(self):
        """字节游标与已见键持久保存，重复读取或重建适配器不重复发布。:return: None。"""
        value = self.event()
        self.append(value, value)
        first = self.terminal.passive_status(self.work)
        self.assertIsNotNone(first['evidence_key'])
        self.assertIsNone(self.terminal.passive_status(self.work)['evidence_key'])
        self.assertIsNone(self.new_terminal().passive_status(self.work)['evidence_key'])
        self.assertEqual(1, len(self.observations))

    def test_callback_failure_keeps_evidence_available_for_idempotent_retry(self):
        """账号事实写入失败时不能推进游标而丢掉唯一限额补证。:return: None。"""
        self.append(self.event())

        def fail(account, source, facts):
            """模拟数据库暂时不可写。:param account: 账号。:param source: 来源。:param facts: 补证。:return: 不返回。"""
            raise RuntimeError('合成提交故障')

        self.terminal.quota_observation = fail
        with self.assertRaises(RuntimeError):
            self.terminal.passive_status(self.work)
        self.assertTrue(self.new_terminal().passive_status(self.work)['quota_limited'])
        self.assertEqual(1, len(self.observations))

    def test_partial_line_is_consumed_only_after_atomic_record_completes(self):
        """不完整的落盘记录留给后续观察，不提前确认或跳过。:return: None。"""
        raw = json.dumps(self.event())
        self.native.write_text(raw[:60])
        self.assertIsNone(self.terminal.passive_status(self.work)['evidence_key'])
        with self.native.open('a') as output:
            output.write(raw[60:] + '\n')
        self.assertTrue(self.terminal.passive_status(self.work)['quota_limited'])

    def test_old_error_before_current_segment_does_not_pause_resumed_work(self):
        """恢复原会话不能再次消费上一执行段留下的错误。:return: None。"""
        old = datetime.fromtimestamp(self.work['segment_started_at'] - 1, timezone.utc).isoformat()
        self.append(self.event(timestamp=old), self.event(uuid='current-error'))
        facts = self.terminal.passive_status(self.work)
        self.assertTrue(facts['quota_limited'])
        self.assertEqual(1, len(self.observations))

    def test_account_and_source_mismatch_are_rejected_before_reading(self):
        """工作不能借用另一账号 token 或其它控制代次的原生证据。:return: None。"""
        for field, value in (('account_id', 2), ('generation', 2)):
            wrong = {**self.work, field: value}
            with self.assertRaises(ValueError):
                self.terminal.passive_status(wrong)
        self.assertEqual([], self.observations)

    def test_second_account_and_exact_native_file_remain_isolated(self):
        """第二账号文件不会串到第一账号，替换路径或文件链接也会被拒绝。:return: None。"""
        value = self.event(sessionId=self.other['session_id'])
        self.append(value, path=self.other_native)
        self.assertFalse(self.terminal.passive_status(self.work)['quota_limited'])
        self.assertTrue(self.terminal.passive_status(self.other)['quota_limited'])
        self.assertEqual(2, self.observations[0][0])
        self.native.symlink_to(self.other_native)
        with self.assertRaises(ValueError):
            self.terminal.passive_status(self.work)

    def test_oversized_normal_line_does_not_hide_next_native_error(self):
        """大段普通输出分片跳过，不把截断尾部当 JSON，也不永久挡住后续错误。:return: None。"""
        with self.native.open('w') as output:
            output.write('x' * (2 * 1024 * 1024 + 100) + '\n')
            output.write(json.dumps(self.event()) + '\n')
        self.assertFalse(self.terminal.passive_status(self.work)['quota_limited'])
        self.assertTrue(self.terminal.passive_status(self.work)['quota_limited'])


if __name__ == '__main__':
    unittest.main()
