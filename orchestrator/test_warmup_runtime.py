"""验证养号独立工作区与共用终端启动、真实原生会话证据。"""
import json
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from warmup_runtime import WarmupTerminal


class WarmupRuntimeTests(unittest.TestCase):
    """使用真实文件和受控 Docker 替身，不启动账号或模型。"""

    def setUp(self):
        """建立一个账号、独立轮次与可信运行时接口。:return: None。"""
        temporary = tempfile.TemporaryDirectory(prefix='warmup-runtime-')
        self.addCleanup(temporary.cleanup)
        self.data = Path(temporary.name)
        self.root = self.data / 'environments/one'
        self.root.mkdir(parents=True)
        self.account = {'id': 1, 'name': 'synthetic-one', 'cc2api_account_id': None}
        self.row = {'account_id': 1, 'environment_id': 'one'}
        self.work = {'id': 'a' * 32, 'account_id': 1, 'generation': 2,
            'session_id': '10000000-0000-4000-8000-000000000001', 'account_identity': 'identity-one',
            'settings_json': json.dumps({'claude_code_version': '2.1.293', 'claude_effort_level': 'high'}),
            'remaining_sec': 123, 'runtime_json': None, 'created_at': 1, 'started_at': None}
        self.job = {'shared_cli': True, 'token': 'owned-token', 'row': self.row, 'account': self.account,
            'source': 'warmup:' + self.work['id'] + ':2'}
        self.container = SimpleNamespace(id='synthetic-cli')
        self.api = SimpleNamespace(exec_create=Mock(return_value={'Id': 'execution-id'}), exec_start=Mock())
        self.runtime = SimpleNamespace(data=self.data, client=SimpleNamespace(api=self.api),
            _root=lambda row: self.root, sync_credentials=Mock(), _save_execution=Mock(),
            execution_flows=lambda account, source, path: path, _install_cli_quota=Mock(),
            _network_runtime=lambda row: self.root / 'runtime/network', _configure_network_context=Mock(),
            execution_environment=lambda row: {'SYNTHETIC_RUNTIME': '1'},
            _attach_process=lambda job, path: job.update(process={'pid': 123}), cleanup=Mock(),
            job_for_container=lambda token: self.job if token == 'owned-token' else None)
        self.setup_calls = []

        @contextmanager
        def setup(account, source, version, **options):
            """替代原子租约入口并记录调用。:param account: 账号。:param source: 来源。:param version: 版本。:param options: 门禁选项。:return: 隔离环境句柄。"""
            self.setup_calls.append((account, source, version, options))
            self.job['source'] = source
            yield self.row, self.container, self.job

        self.runtime._cli_setup = setup
        self.quota = Mock(return_value={'QUOTA_IDENTITY': 'identity-one'})
        self.release = Mock()
        self.terminal = WarmupTerminal(self.runtime, None, self.quota, self.release)
        chown = patch('pi_terminal.os.chown')
        chown.start()
        self.addCleanup(chown.stop)

    def prepare(self, **overrides):
        """准备当前轮次的真实工作区。:param overrides: 冻结字段变化。:return: 工作区。"""
        return self.terminal._prepare_execution(self.root, self.row, self.account, {**self.work, **overrides})[0]

    def test_start_uses_common_supervision_without_project_assets_or_automatic_business_input(self):
        """养号启动走原租约与监督器，不复制seed或注入初始正文。:return: None。"""
        info = self.terminal.start(self.account, self.work)
        self.assertEqual('warmup:' + self.work['id'] + ':2', info['source'])
        self.assertEqual({'idle_only': True, 'shared_cli': True, 'scenario_resources': False}, self.setup_calls[0][3])
        workspace = self.data / info['workspace']
        self.assertEqual([], list(workspace.iterdir()))
        handle = self.job['handle']
        config = json.loads((self.root / 'runtime/jobs' / handle / 'warmup.json').read_text())
        self.assertEqual(self.work['session_id'], config['session_id'])
        self.assertFalse(config['resume'])
        self.assertEqual(123, config['timeout_sec'])
        self.assertNotIn('prompt', config)
        arguments = self.api.exec_create.call_args
        self.assertIn('--source', arguments.args[1])
        self.assertIn(info['source'], arguments.args[1])
        self.assertNotIn('PYTHONPATH', arguments.kwargs['environment'])
        self.assertEqual('high', arguments.kwargs['environment']['CLAUDE_CODE_EFFORT_LEVEL'])
        self.quota.assert_called_once()
        self.runtime.cleanup.assert_not_called()

    def test_failed_launch_releases_only_its_own_runtime_and_unused_quota_admission(self):
        """监督进程尚未启动时退还本轮许可，原轮次工作区仍可安全重试。:return: None。"""
        self.api.exec_start.side_effect = RuntimeError('合成启动失败')
        with self.assertRaisesRegex(RuntimeError, '合成启动失败'):
            self.terminal.start(self.account, self.work)
        self.runtime.cleanup.assert_called_once_with('owned-token')
        self.release.assert_called_once_with(self.account, self.job['source'], True)
        self.assertTrue(self.prepare().is_dir())

    def test_resume_uses_the_exact_native_session_and_keeps_the_original_workspace(self):
        """恢复必须找到原会话，不能用新会话或空目录替代已开始的轮次。:return: None。"""
        original = self.terminal.start(self.account, self.work)
        workspace = self.data / original['workspace']
        (workspace / 'app.py').write_text('VALUE = 3\n')
        resumed = {**self.work, 'generation': 3, 'resume_required': True, 'started_at': 2}
        with self.assertRaisesRegex(ValueError, '原 Claude 会话缺失'):
            self.terminal.start(self.account, resumed)
        directory = self.data / original['native']
        directory.mkdir(parents=True)
        (directory / (self.work['session_id'] + '.jsonl')).write_text('')
        current = self.terminal.start(self.account, resumed)
        self.assertEqual(original['workspace'], current['workspace'])
        self.assertEqual(original['native'], current['native'])
        config = json.loads((self.root / 'runtime/jobs' / self.job['handle'] / 'warmup.json').read_text())
        self.assertTrue(config['resume'])
        self.assertEqual(self.work['session_id'], config['session_id'])
        self.assertEqual('VALUE = 3\n', (workspace / 'app.py').read_text())

    def test_resume_preserves_files_and_rejects_changed_identity_or_missing_marker(self):
        """恢复保留用户成果，账号身份或原凭据缺失时不另建替代工作区。:return: None。"""
        workspace = self.prepare()
        (workspace / 'app.py').write_text('VALUE = 2\n')
        self.assertEqual(workspace, self.prepare(resume_required=True, started_at=2))
        self.assertEqual('VALUE = 2\n', (workspace / 'app.py').read_text())
        for overrides in ({'account_identity': 'other-identity'}, {'session_id': 'other-session'}):
            with self.subTest(overrides=overrides), self.assertRaisesRegex(ValueError, '证明不符'):
                self.prepare(**overrides)
        marker = self.root / 'runtime/warmup-workspaces' / (self.work['id'] + '.json')
        marker.unlink()
        with self.assertRaisesRegex(ValueError, '凭据缺失'):
            self.prepare(resume_required=True)
        self.assertEqual('VALUE = 2\n', (workspace / 'app.py').read_text())

    def test_round_identifiers_and_workspace_links_cannot_escape_the_account(self):
        """错误轮次或目录链接不能创建越界文件。:return: None。"""
        with self.assertRaisesRegex(ValueError, '标识不合法'):
            self.prepare(id='../outside')
        (self.root / 'projects').symlink_to(self.data)
        with self.assertRaisesRegex(ValueError, '父目录不能是链接'):
            self.prepare()
        self.assertFalse((self.data / ('warmup-' + self.work['id'])).exists())

    def native(self):
        """登记当前执行的真实原生文件路径。:return: 主会话文件。"""
        directory = self.root / 'home/.claude/projects/-home-node-projects-warmup-test'
        directory.mkdir(parents=True)
        self.job['cwd'] = '/home/node/projects/warmup-test'
        self.work['runtime_json'] = json.dumps({'token': self.job['token'], 'source': self.job['source'],
            'native': str(directory.relative_to(self.data))})
        return directory / (self.work['session_id'] + '.jsonl')

    def test_dialogue_reuses_real_parent_chain_and_rejects_synthetic_or_tool_completion(self):
        """正常回复、工具回复和合成错误由真实解析器区分，旁支不会进入完成证据。:return: None。"""
        path = self.native()
        records = [
            {'type': 'user', 'uuid': 'u1', 'sessionId': self.work['session_id'],
                'message': {'role': 'user', 'content': 'Build the supplied local application.'}},
            {'type': 'assistant', 'uuid': 'a1', 'parentUuid': 'u1', 'sessionId': self.work['session_id'],
                'message': {'role': 'assistant', 'content': [{'type': 'text', 'text': 'The requested application is implemented.'}]}},
            {'type': 'assistant', 'uuid': 'error', 'parentUuid': 'a1', 'isApiErrorMessage': True,
                'message': {'role': 'assistant', 'content': 'Synthetic completion claim.'}},
            {'type': 'assistant', 'uuid': 'tool', 'parentUuid': 'a1',
                'message': {'role': 'assistant', 'stop_reason': 'tool_use', 'content': [
                    {'type': 'text', 'text': 'Still working.'}, {'type': 'tool_use', 'name': 'Bash'}]}},
            {'type': 'assistant', 'uuid': 'side', 'parentUuid': 'a1', 'isSidechain': True,
                'message': {'role': 'assistant', 'content': 'Unrelated work completed.'}},
        ]
        path.write_text(''.join(json.dumps(record) + '\n' for record in records))
        dialogue = self.terminal.dialogue(self.work)
        by_id = {item['id']: item for item in dialogue}
        self.assertEqual({'u1', 'a1', 'error', 'tool'}, set(by_id))
        self.assertTrue(by_id['a1']['normal'])
        self.assertEqual(by_id['u1']['key'], by_id['a1']['parent_key'])
        self.assertFalse(by_id['error']['normal'])
        self.assertTrue(by_id['error']['synthetic'])
        self.assertFalse(by_id['tool']['normal'])
        self.assertTrue(by_id['tool']['tool'])
        with self.assertRaisesRegex(ValueError, '账号或执行代次'):
            self.terminal.dialogue({**self.work, 'generation': 3})

    def test_empty_native_session_can_be_observed_before_first_input(self):
        """原生尚未写首题时为空历史，链接或错误执行仍不能作为证据。:return: None。"""
        path = self.native()
        self.work['started_at'] = 1
        self.assertEqual([], self.terminal.dialogue(self.work))
        with self.assertRaisesRegex(ValueError, '账号或执行代次'):
            self.terminal.dialogue({**self.work, 'generation': 3})
        path.symlink_to(path.parent / 'missing-native.jsonl')
        with self.assertRaisesRegex(ValueError, '原生主会话'):
            self.terminal.dialogue(self.work)


if __name__ == '__main__':
    unittest.main()
