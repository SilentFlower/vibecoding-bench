"""实际终端缓冲、逐次准入及专属评审目标的回归。"""
from __future__ import annotations

import threading
import unittest
from types import SimpleNamespace
from unittest.mock import Mock

from runtime_terminal_input import send_terminal_input


class RuntimeTerminalInputTests(unittest.TestCase):
    """使用原Docker exec接口替身，区分缓冲、paste与Enter边界。"""

    def setUp(self) -> None:
        """建立原作业、可观察的socket与两类真实目标接口。:return: None。"""
        self.job = {'row': {'environment_id': 'a' * 32}, 'source': 'run:original:0',
            'tmux': 'claude-original', 'tmux_socket': '/run/v3/jobs/original/tmux-1000/default'}
        self.container = SimpleNamespace(id='account-cli', exec_run=Mock(return_value=SimpleNamespace(exit_code=0)))
        self.review = SimpleNamespace(id='private-review', exec_run=Mock(return_value=SimpleNamespace(exit_code=0)))
        self.raw = Mock()
        self.raw.recv.return_value = b''
        self.stream = SimpleNamespace(_sock=self.raw, close=Mock())
        api = Mock()
        api.exec_create.return_value = {'Id': 'original-buffer-exec'}
        api.exec_start.return_value = self.stream
        api.exec_inspect.return_value = {'ExitCode': 0}
        self.runtime = SimpleNamespace(job_for_container=Mock(return_value=self.job),
            environment_lock=Mock(return_value=threading.RLock()), authorize_input=Mock(),
            _container=Mock(return_value=self.container), client=SimpleNamespace(api=api),
            reviews=SimpleNamespace(container=Mock(return_value=self.review)))

    def test_original_multiline_bytes_are_buffered_and_each_actual_send_checks_admission(self) -> None:
        """原正文只走stdin，缓冲后及Enter前分别核对原许可。:return: None。"""
        text = '第一行\n第二行\t原样字符'
        send_terminal_input(self.runtime, 'original-token', '1' * 32, text, [], True)
        self.raw.sendall.assert_called_once_with(text.encode())
        self.assertEqual(3, self.runtime.authorize_input.call_count)
        commands = [call.args[0] for call in self.container.exec_run.call_args_list]
        self.assertEqual(['paste-buffer', 'send-keys', 'delete-buffer'], [command[3] for command in commands])
        self.assertEqual('Enter', commands[1][-1])
        self.assertNotIn(text, str(self.runtime.client.api.exec_create.call_args))
        self.stream.close.assert_called_once()

    def test_expiration_after_buffer_or_paste_keeps_unknown_and_prevents_next_submission(self) -> None:
        """过期发生在缓冲或paste之后时，后续投递步骤保持关闭。:return: None。"""
        for checks, expected in (([None, ValueError('合成过期')], ['delete-buffer']),
                ([None, None, ValueError('合成过期')], ['paste-buffer', 'delete-buffer'])):
            with self.subTest(expected=expected):
                self.container.exec_run.reset_mock()
                self.runtime.authorize_input.side_effect = checks
                with self.assertRaisesRegex(RuntimeError, '结果未知'):
                    send_terminal_input(self.runtime, 'original-token', '2' * 32, '原输入', [], True)
                commands = [call.args[0][3] for call in self.container.exec_run.call_args_list]
                self.assertEqual(expected, commands)

    def test_review_uses_original_private_container_and_invalid_keys_are_before_send(self) -> None:
        """评审沿原专属容器，额外按键在Docker调用前拒绝。:return: None。"""
        with self.assertRaises(ValueError):
            send_terminal_input(self.runtime, 'original-token', '3' * 32, '', ['untrusted-command'], False)
        self.runtime.client.api.exec_create.assert_not_called()
        self.job['execution_role'] = 'project-review'
        send_terminal_input(self.runtime, 'original-token', '4' * 32, '评审输入', [], True)
        self.assertEqual('private-review', self.runtime.client.api.exec_create.call_args.args[0])
        self.runtime.reviews.container.assert_called_once_with(self.job)
        self.runtime._container.assert_not_called()
