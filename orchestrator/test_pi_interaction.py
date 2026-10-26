"""验证作业级 CLI 通知只唤醒 Pi，保持既有权限、钩子与来源隔离。"""
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from pi_terminal import PiTerminal


DRIVER = Path(__file__).resolve().parents[1] / 'images/account/projects_cli.py'


class PiInteractionTests(unittest.TestCase):
    """用真实通知子进程和普通文件校验安全的交互提示边界。"""

    def setUp(self):
        """建立单作业设置、真实标记路径及读取端。:return: None。"""
        temporary = tempfile.TemporaryDirectory(prefix='pi-interaction-')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.job_root = self.root / 'environment/runtime/jobs/owned'
        self.job_root.mkdir(parents=True)
        self.config = self.job_root / 'project config.json'
        self.signal = self.job_root / 'interaction.json'
        self.work = {'id': 'a' * 32, 'generation': 2, 'session_id': 'session-original'}
        self.source = f"projects:{self.work['id']}:2"
        self.values = {'source': self.source, 'session_id': self.work['session_id'],
            'interaction_signal': str(self.signal), 'settings': str(self.job_root / 'settings.json')}
        self.config.write_text(json.dumps(self.values))
        self.original = {'env': {'UNCHANGED': 'yes'}, 'hooks': {'Stop': [{'matcher': '',
            'hooks': [{'type': 'command', 'command': 'printf original'}]}]}}
        Path(self.values['settings']).write_text(json.dumps(self.original))
        runtime = SimpleNamespace(data=self.root, _root=lambda row: self.root / 'environment')
        self.terminal = PiTerminal(runtime, None, None, namespace='projects')
        self.info = {'source': self.source, 'interaction_signal': str(self.signal.relative_to(self.root))}
        self.job = {'row': {}, 'source': self.source, 'handle': 'owned'}

    def notify(self, event):
        """调用真实脚本的通知入口。:param event: 合成钩子输入。:return: 子进程回执。"""
        return subprocess.run([sys.executable, '-I', str(DRIVER), '--config', str(self.config), '--notify'],
            input=json.dumps(event).encode(), capture_output=True, timeout=5)

    def test_hook_install_preserves_existing_settings_and_is_idempotent(self):
        """只追加本作业通知，原权限策略与用户钩子原样保留。:return: None。"""
        spec = importlib.util.spec_from_file_location('pi_driver_for_test', DRIVER)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        module._install_notifications(self.config, self.values)
        first = json.loads(Path(self.values['settings']).read_text())
        module._install_notifications(self.config, self.values)
        self.assertEqual(first, json.loads(Path(self.values['settings']).read_text()))
        self.assertEqual(self.original['hooks']['Stop'][0], first['hooks']['Stop'][0])
        self.assertEqual(self.original['env'], first['env'])
        self.assertEqual({'PermissionRequest', 'PreToolUse', 'Stop'}, set(first['hooks']))
        self.assertIn('AskUserQuestion|ExitPlanMode', first['hooks']['PreToolUse'][0]['matcher'])
        self.assertFalse(self.signal.exists())

    def test_native_notification_has_no_permission_decision_or_private_arguments(self):
        """权限请求仅产生去参数提示，不输出 allow 或修改权限。:return: None。"""
        result = self.notify({'session_id': self.work['session_id'], 'hook_event_name': 'PermissionRequest',
            'tool_name': 'Bash', 'tool_input': {'command': 'private-ticket-secret'}})
        self.assertEqual(0, result.returncode)
        self.assertEqual(b'', result.stdout)
        self.assertEqual(b'', result.stderr)
        value = self.terminal._interaction(self.work, self.info, self.job)
        self.assertEqual(self.source, value['source'])
        self.assertEqual('Bash', value['tool'])
        self.assertNotIn('private-ticket-secret', self.signal.read_text())
        self.assertNotIn('permissionDecision', self.signal.read_text())
        self.assertEqual(self.original, json.loads(Path(self.values['settings']).read_text()))

    def test_question_and_stop_are_hints_but_other_tool_or_session_is_ignored(self):
        """提问/结束信号可唤醒，普通工具和旧会话不能制造新提示。:return: None。"""
        for kind, tool in [('PreToolUse', 'AskUserQuestion'), ('PreToolUse', 'ExitPlanMode'), ('Stop', None)]:
            self.notify({'session_id': self.work['session_id'], 'hook_event_name': kind, 'tool_name': tool})
            self.assertEqual(kind, self.terminal._interaction(self.work, self.info, self.job)['event'])
        previous = self.signal.read_bytes()
        for event in [{'session_id': 'old-session', 'hook_event_name': 'PermissionRequest'},
                {'session_id': self.work['session_id'], 'hook_event_name': 'PreToolUse', 'tool_name': 'Bash'},
                {'session_id': self.work['session_id'], 'hook_event_name': 'Unknown'}]:
            self.notify(event)
            self.assertEqual(previous, self.signal.read_bytes())

    def test_reader_rejects_other_owner_corrupt_oversized_and_linked_markers(self):
        """坏标记保持保守，不能读链接、FIFO 或借用其他执行的事件。:return: None。"""
        self.notify({'session_id': self.work['session_id'], 'hook_event_name': 'Stop'})
        valid = json.loads(self.signal.read_text())
        for change in ({'source': 'other'}, {'session_id': 'other'}, {'schema': True}, {'observed_at': float('nan')},
                {'id': 'not-an-event'}, {'unexpected': 'private'}):
            self.signal.write_text(json.dumps({**valid, **change}))
            self.assertIsNone(self.terminal._interaction(self.work, self.info, self.job))
        self.signal.write_bytes(b'x' * 4097)
        self.assertIsNone(self.terminal._interaction(self.work, self.info, self.job))
        self.signal.unlink()
        target = self.root / 'unrelated.json'
        target.write_text(json.dumps(valid))
        self.signal.symlink_to(target)
        self.assertIsNone(self.terminal._interaction(self.work, self.info, self.job))
        self.assertEqual(valid, json.loads(target.read_text()))
        self.signal.unlink()
        os.mkfifo(self.signal)
        self.assertIsNone(self.terminal._interaction(self.work, self.info, self.job))

    def test_old_runtime_without_signal_remains_supported(self):
        """旧工作没有新增定位时继续走原生记录与画面。:return: None。"""
        self.assertIsNone(self.terminal._interaction(self.work, {'source': self.source}, self.job))

    def test_project_and_warmup_markers_cannot_cross_namespaces(self):
        """两空间各自接收提示，同账号和同会话也不能借用另一空间来源。:return: None。"""
        for namespace in ('projects', 'warmup'):
            source = f"{namespace}:{self.work['id']}:2"
            self.config.write_text(json.dumps({**self.values, 'source': source}))
            self.notify({'session_id': self.work['session_id'], 'hook_event_name': 'Stop'})
            info, job = {**self.info, 'source': source}, {**self.job, 'source': source}
            terminal = PiTerminal(self.terminal.runtime, None, None, namespace=namespace)
            self.assertEqual(source, terminal._interaction(self.work, info, job)['source'])
            other = PiTerminal(self.terminal.runtime, None, None,
                namespace='warmup' if namespace == 'projects' else 'projects')
            with self.assertRaisesRegex(ValueError, '归属'):
                other._interaction(self.work, info, job)

    def test_native_question_tool_wakes_without_text_or_notification(self):
        """原生提问不依赖文本或通知延迟，普通工具不误报交互。:return: None。"""
        directory = self.root / 'environment/home/.claude/projects/owned'
        directory.mkdir(parents=True)
        path = directory / (self.work['session_id'] + '.jsonl')
        content = [{'type': 'tool_use', 'id': 'question', 'name': 'AskUserQuestion', 'input': {'questions': []}},
            {'type': 'tool_use', 'id': 'command', 'name': 'Bash', 'input': {}}]
        path.write_text(json.dumps({'message': {'role': 'assistant', 'content': content}}) + '\n')
        self.job.update(exec='owned-exec', tmux_socket='fixture.sock', tmux='owned')
        runtime = self.terminal.runtime
        runtime.job_for_container = lambda token: self.job
        runtime._container = lambda row: SimpleNamespace(exec_run=lambda args: SimpleNamespace(exit_code=0, output=b'menu'))
        runtime.client = SimpleNamespace(api=SimpleNamespace(exec_inspect=lambda identifier: {'Running': True}))
        info = {**self.info, 'token': 'owned-token', 'native': str(directory.relative_to(self.root)), 'quota_signal': 'pause.json'}
        work = {**self.work, 'runtime_json': json.dumps(info)}
        observed = self.terminal.observe(work)
        self.assertEqual([], observed['events'])
        self.assertEqual([{'id': 'question', 'tool': 'AskUserQuestion'}], observed['interactions'])
        self.assertEqual([], self.terminal.observe(work, observed['cursor'])['interactions'])
