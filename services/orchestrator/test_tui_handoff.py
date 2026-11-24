"""覆盖真实子进程、流式工具块和持久回执之间的交接。"""

from pathlib import Path
from subprocess import PIPE, Popen
from tempfile import TemporaryDirectory
from unittest import TestCase
import json
import sys

from tui_capacity import TuiCapacity
from tui_handoff import TuiToolHandoff
from tui_process import TuiProcessExecutor
from tui_tool_receipts import ReceiptConflict, ToolReceiptStore, ToolTurn, UnknownToolCall


class TuiHandoffTest(TestCase):
    """验证调用方、原进程代次、实际收件确认及错误恢复。"""

    def setUp(self):
        self.folder = TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.store = ToolReceiptStore(Path(self.folder.name))
        self.capacity = TuiCapacity(3, budget_bytes=1024, fixed_reserve_bytes=256,
                                    per_process_reserve_bytes=256, max_waiters=1)
        self.executor = TuiProcessExecutor(self.capacity, self._spawn)
        self.turn = ToolTurn('account', 'caller', 'session', 'turn')

    def _spawn(self, session_key):
        # 子进程只从自己的私有管道收件，返回实际收到的调用 ID 和原始内容。
        child = Popen([sys.executable, '-I', '-u', '-c',
                       'import sys\nfor line in sys.stdin: print(line, end="", flush=True)'],
                      stdin=PIPE, stdout=PIPE, text=True)
        self.addCleanup(child.stdin.close)
        self.addCleanup(child.stdout.close)
        return child

    def _start(self, turn):
        handoff = TuiToolHandoff.start(turn, self.store, self.executor, timeout=0)
        self.addCleanup(self.executor.close, handoff.handle)
        return handoff

    def test_partial_arguments_result_and_ack_use_the_same_process(self):
        handoff = self._start(self.turn)
        mapping = {'internal_id': 'inside', 'name': 'Read'}
        block = handoff.offer('outside', **mapping, arguments=None)
        self.assertEqual(block, {'type': 'tool_use', 'id': 'outside', 'name': 'Read', 'input': {}})
        result = {'type': 'tool_result', 'tool_use_id': 'outside', 'content': '正文\n第二行'}
        with self.assertRaises(ReceiptConflict):
            self.store.submit(self.turn, result)
        handoff.seal_arguments('outside', **mapping, arguments={'path': 'sample'})
        self.assertTrue(self.store.submit(self.turn, result))

        def send_and_ack(child, message):
            child.stdin.write(json.dumps(message) + '\n')
            child.stdin.flush()
            received = json.loads(child.stdout.readline())
            self.assertEqual(received, {**result, 'tool_use_id': 'inside'})
            return received['tool_use_id']

        self.assertTrue(handoff.deliver('outside', internal_id='inside', send_and_ack=send_and_ack))
        self.assertFalse(handoff.deliver('outside', internal_id='inside', send_and_ack=self.fail))
        self.assertEqual(self.store.read(self.turn, 'outside').state, 'confirmed')
        self.store.close_turn(self.turn)
        self.assertIsNone(self.store.read(self.turn, 'outside').result)

    def test_wrong_worker_ack_keeps_unknown_result_and_cannot_trigger_resend(self):
        handoff = self._start(self.turn)
        handoff.offer('outside', internal_id='inside', name='Edit', arguments={'path': 'sample'})
        self.store.submit(self.turn, {'type': 'tool_result', 'tool_use_id': 'outside', 'is_error': True})
        with self.assertRaisesRegex(ValueError, '回执不匹配'):
            handoff.deliver('outside', internal_id='inside', send_and_ack=lambda child, block: 'wrong')
        reopened = ToolReceiptStore(Path(self.folder.name))
        self.assertEqual(reopened.read(self.turn, 'outside').state, 'result_delivery_unknown')
        self.assertFalse(handoff.deliver('outside', internal_id='inside', send_and_ack=self.fail))
        with self.assertRaises(ReceiptConflict):
            reopened.close_turn(self.turn)

    def test_reused_session_name_isolated_by_principal_and_generation(self):
        first = self._start(self.turn)
        second_turn = ToolTurn(self.turn.account_id, 'other', self.turn.session_id, self.turn.turn_id)
        second = self._start(second_turn)
        first.offer('shared', internal_id='inside', name='Read', arguments={})
        with self.assertRaises(UnknownToolCall):
            second.seal_arguments('shared', internal_id='inside', name='Read', arguments={})
        self.store.submit(self.turn, {'type': 'tool_result', 'tool_use_id': 'shared', 'content': '旧结果'})
        self.executor.close(first.handle)
        replacement = self._start(self.turn)
        self.assertNotEqual(first.handle.generation, replacement.handle.generation)
        with self.assertRaises(UnknownToolCall):
            replacement.deliver('shared', internal_id='inside', send_and_ack=self.fail)
        self.assertEqual(self.store.read(self.turn, 'shared').state, 'received')
