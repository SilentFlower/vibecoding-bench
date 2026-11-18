"""节点输入代理的真实UNIX通道、未知回执、期限和worker入口回归。"""
from __future__ import annotations

import importlib.util
import json
import os
import re
import socket
import subprocess
import tempfile
import threading
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from cluster_execution_grants import ExecutionScope
from cluster_input import INPUT_LIMIT, NodeInputBroker, WorkerInput
from system_update_contract import strict_json


SOURCE_ROOT = Path(__file__).resolve().parents[2]
CLIENT_PATH = SOURCE_ROOT / 'images/account/node-input.py'


class NodeInputBrokerTests(unittest.TestCase):
    """执行真实root侧socket和账号侧客户端，实际tmux投递使用可观察替身。"""

    def setUp(self) -> None:
        """创建原scope、root控制目录和实际输入替身。:return: None。"""
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.controls = self.root / ('a' * 80) / ('b' * 20)
        self.controls.mkdir(parents=True)
        self.controls.chmod(0o750)
        os.chown(self.controls, 0, 1000)
        self.scope = ExecutionScope(operation_id='1' * 32, node_key='2' * 32, account_id=7,
            environment_id='3' * 32, assignment_revision=1, generation=2, source='run:abcdef123456:0', role='cli')
        self.job = {'row': {'environment_id': self.scope.environment_id}, 'source': self.scope.source}
        self.runtime = SimpleNamespace(job_for_container=Mock(return_value=self.job),
            environment_lock=Mock(return_value=threading.RLock()), authorize_input=Mock())
        self.executor = SimpleNamespace(data=self.root, _locked=Mock(return_value=threading.RLock()))
        self.broker = NodeInputBroker(self.executor, self.runtime, self.scope, 'actual-token', self.controls)
        self.addCleanup(self._close)
        self.sender = patch('cluster_input.send_terminal_input').start()
        self.addCleanup(patch.stopall)
        spec = importlib.util.spec_from_file_location('node_input_client_test', CLIENT_PATH)
        self.client = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.client)

    def _close(self) -> None:
        self.broker.close()
        self.broker.join()

    def _short_socket_path(self) -> str:
        # 客户端本身也有108字节限制，容器里的/controls映射本来很短。
        descriptor = os.open(self.controls, os.O_RDONLY | os.O_DIRECTORY)
        self.addCleanup(os.close, descriptor)
        return f'/proc/self/fd/{descriptor}/' + self.broker.socket_path.name

    def test_real_socket_preserves_text_and_duplicate_reads_original_receipt(self) -> None:
        """root可在长数据根绑定socket，同操作只发送一次且原文只走数据帧。:return: None。"""
        self.broker.start()
        self.assertGreater(len(str(self.broker.socket_path)), 108)
        path = self._short_socket_path()
        text = '原题\n原补充\t保留\r原样'
        result = self.client.send(path, '4' * 32, text, ['Escape'], True)
        self.assertEqual('sent', result['status'])
        self.assertEqual(result, self.client.send(path, '4' * 32, text, ['Escape'], True))
        self.sender.assert_called_once_with(self.runtime, 'actual-token', '4' * 32,
            text, ['Escape'], True, max_bytes=INPUT_LIMIT)
        self.assertEqual(0o660, self.broker.socket_path.stat().st_mode & 0o777)
        self.assertEqual(1000, self.broker.socket_path.stat().st_gid)
        with self.assertRaisesRegex(ValueError, '正文已变化'):
            self.broker.send(WorkerInput(operation_id='4' * 32, text='替换正文'))
        self.assertIsNone(self.broker.state()['pending_input'])
        stored = (self.broker.directory / ('4' * 32 + '.json')).read_text()
        self.assertNotIn(text, stored)

    def test_partial_submission_survives_restart_and_blocks_next_input(self) -> None:
        """部分投递后崩溃保持原操作与unknown，新的输入等待人工核对。:return: None。"""
        self.sender.side_effect = RuntimeError('合成paste后响应丢失')
        request = WorkerInput(operation_id='5' * 32, text='原题', submit=True)
        self.assertEqual('unknown', self.broker.send(request)['status'])
        recovered = NodeInputBroker(self.executor, self.runtime, self.scope, 'actual-token', self.controls)
        self.assertEqual('unknown', recovered.send(request)['status'])
        with self.assertRaisesRegex(ValueError, '等待核对'):
            recovered.send(WorkerInput(operation_id='6' * 32, text='自动重试'))
        self.sender.assert_called_once()
        self.assertEqual('5' * 32, recovered.state()['pending_input'])

    def test_expired_or_changed_job_is_not_sent_and_remains_queryable(self) -> None:
        """发送前期限失效保留not_sent，查询不续期也不调用终端。:return: None。"""
        self.runtime.authorize_input.side_effect = ValueError('合成过期')
        request = WorkerInput(operation_id='7' * 32, text='原题', submit=True)
        result = self.broker.send(request)
        self.assertEqual('not_sent', result['status'])
        self.assertEqual(result, self.broker.receipt(request.operation_id))
        self.sender.assert_not_called()
        self.assertIsNone(self.broker.state()['pending_input'])
        with self.assertRaises(ValueError):
            WorkerInput(operation_id='8' * 32, keys=['未知按键'])
        with self.assertRaises(ValueError):
            WorkerInput(operation_id='8' * 32, text='字' * INPUT_LIMIT)

    def test_lost_response_queries_same_operation_without_second_send(self) -> None:
        """真实服务保存输入后客户端丢弃响应，后续查询返回原sent。:return: None。"""
        self.broker.start()
        path = self._short_socket_path()
        payload = {'action': 'send', **WorkerInput(operation_id='9' * 32, text='原题', submit=True).model_dump()}
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as stream:
            stream.connect(path)
            stream.sendall(json.dumps(payload).encode())
            stream.shutdown(socket.SHUT_RDWR)
        deadline = time.monotonic() + 3
        while not (self.broker.directory / ('9' * 32 + '.json')).exists() and time.monotonic() < deadline:
            time.sleep(0.01)
        result = self.client.exchange(path, {'action': 'query', 'operation_id': '9' * 32})
        self.assertEqual('sent', result['status'])
        self.sender.assert_called_once()
        with patch.object(self.client, 'exchange', side_effect=[OSError('合成丢包'), result]) as exchange:
            self.assertEqual(result, self.client.send(path, '9' * 32, '原题', [], True))
        self.assertEqual({'action': 'query', 'operation_id': '9' * 32}, exchange.call_args.args[1])

    def test_unknown_wire_fields_are_rejected_before_terminal(self) -> None:
        """worker不能覆盖服务端目标或调用任意动作。:return: None。"""
        self.broker.start()
        result = self.client.exchange(self._short_socket_path(), {'action': 'send', 'operation_id': 'a' * 32,
            'text': '原题', 'environment_id': '恶意目标'})
        self.assertEqual('rejected', result['status'])
        self.sender.assert_not_called()

    def test_replaced_job_with_same_compatible_token_never_accepts_late_input(self) -> None:
        """兼容token被同source新句柄复用时，旧代理仍绑定原job对象并拒绝投递。:return: None。"""
        self.runtime.job_for_container.return_value = dict(self.job)
        result = self.broker.send(WorkerInput(operation_id='b' * 32, text='迟到的原输入', submit=True))
        self.assertEqual('not_sent', result['status'])
        self.sender.assert_not_called()
        other = NodeInputBroker(self.executor, self.runtime, self.scope.model_copy(update={'operation_id': 'c' * 32}),
            'actual-token', self.controls)
        self.assertNotEqual(self.broker.socket_path, other.socket_path)


class WorkerNodeInputTests(unittest.TestCase):
    """执行实际worker函数，核对自动后续与中断使用原root端点。"""

    def test_real_worker_functions_route_inputs_and_stop_on_unknown(self) -> None:
        """补充及中断逐次发送，未知回执结束driver并保留原错误状态。:return: None。"""
        source = (SOURCE_ROOT / 'images/worker/entrypoint.sh').read_text()
        definitions = []
        for name in ('node_terminal_input', 'inject_tmux_prompt', 'interrupt_and_inject_tmux_prompt'):
            definitions.append(re.search(rf'^{name}\(\) \{{.*?^\}}$', source, re.M | re.S).group(0))
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            script = '\n'.join(definitions) + '''
SESSION=original
V3_NODE_INPUT_SOCKET=/controls/original/input.sock
log() { :; }
sleep() { :; }
capture_transcript_snapshot() { :; }
tmux() { [ "$1" = has-session ]; }
write_bench_status() { printf '%s' "$*" > "$TEST_ROOT/status"; }
python3() {
  cat >> "$TEST_ROOT/payload"
  printf '%s\\n' "$*" >> "$TEST_ROOT/calls"
  [ "${TEST_FAILURE:-0}" = 0 ]
}
inject_tmux_prompt followup '原题
原补充'
interrupt_and_inject_tmux_prompt api-stall '原收尾'
printf reached > "$TEST_ROOT/reached"
'''
            for failed in ('0', '1'):
                for path in root.iterdir():
                    path.unlink()
                result = subprocess.run(['bash', '-eu', '-c', script], env={**os.environ, 'TEST_ROOT': temporary,
                    'TEST_FAILURE': failed}, capture_output=True, text=True)
                self.assertEqual(45 if failed == '1' else 0, result.returncode, result.stderr)
                if failed == '1':
                    self.assertIn('回执待核对', (root / 'status').read_text())
                    self.assertFalse((root / 'reached').exists())
                else:
                    calls = (root / 'calls').read_text().splitlines()
                    self.assertEqual(3, len(calls))
                    self.assertIn('--submit', calls[0])
                    self.assertIn('--keys C-c', calls[1])
                    self.assertEqual('原题\n原补充原收尾', (root / 'payload').read_text())
