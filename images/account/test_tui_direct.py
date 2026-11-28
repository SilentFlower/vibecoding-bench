"""验证正式直发的许可、代理归属和同一步公开事件。"""

import json
from threading import Condition, Event
from time import time_ns
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock, patch

from tui_direct import DirectModel, DirectRejected, MODEL_PATHS
from tui_messages import ModelResponseError, WireStep


class DirectModelTests(TestCase):
    """用正式模块测试准入和投影。挂起时观察客户端已可读的分片。"""

    def setUp(self):
        """装配同账号同代预留。@return 无。"""
        future = time_ns() // 1_000_000 + 90_000
        self.events = []
        self.claim = SimpleNamespace(account_token='test-only', expires_at=future, kind='new',
                                     direct_options={},
                                     reservation={'account_id': 12, 'environment_id': 'a' * 32, 'generation': 2,
                                                  'reservation_id': 'fixture-reservation',
                                                  'deadline_unix_ms': future})
        self.step = WireStep([])
        self.step.native = ('turn', 2)
        self.step.native_model = 'claude-sonnet-4-6'
        launcher = SimpleNamespace(direct_proxy=Mock(return_value='socks5h://192.0.2.8:1090'))
        self.actor = SimpleNamespace(claim=self.claim, step=self.step, oauth_file=True, dead=Event(),
                                     changed=Condition(), driver=SimpleNamespace(lock=Condition(), launcher=launcher),
                                     agent_offer=None, process=None, _main_request=Mock(return_value=True),
                                     _publish=self.publish, _observe=lambda step, frame: step.observe(frame), abort=Mock())
        self.direct = DirectModel(self.actor)
        self.offer = {'url': MODEL_PATHS[0], 'body': '{"stream":true}'}
        self.scope = {'turn': 'turn', 'step': 2}
        self.usage = {'input_tokens': 37, 'output_tokens': 19}

    def publish(self, batch):
        """记录客户端此刻可读的实际帧。@param batch 单事件数据。@return 无。"""
        self.events.extend(json.loads(frame.split(b'\ndata: ', 1)[1]) for frame in batch)

    def _start(self):
        self.direct.started.set()
        ticket = self.direct.permit(self.offer)['ticket']
        self.direct.response({'ticket': ticket, 'status': 200, 'streaming': True})
        return ticket

    def _text(self, value):
        self.direct.observe({**self.scope, 'chunk': {'kind': 'text', 'index': 0, 'text': value}})

    def test_permit_cannot_be_reused_or_moved_and_rejects_unbound_connect(self):
        """绑定确认前拒绝。每个实际模型步骤只认领一次。@return 无。"""
        with self.assertRaises(DirectRejected):
            self.direct.permit(self.offer)
        self.direct.started.set()
        with self.assertRaises(DirectRejected):
            self.direct.permit({**self.offer, 'url': 'https://wrong.invalid/v1/messages'})
        self.actor._main_request.return_value = False
        with self.assertRaises(DirectRejected):
            self.direct.permit(self.offer)
        self.actor._main_request.return_value = True
        ticket = self.direct.permit(self.offer)['ticket']
        self.actor.driver.launcher.direct_proxy.assert_called_once_with(self.claim.reservation)
        with self.assertRaises(DirectRejected):
            self.direct.permit(self.offer)
        with self.assertRaises(DirectRejected):
            self.direct.response({'ticket': 'other-round', 'status': 200})
        connection = SimpleNamespace(path='api.anthropic.com:443', client_address=('127.0.0.1', 8042),
                                     send_error=Mock())
        self.direct.connect(connection)
        connection.send_error.assert_called_once_with(403)
        self.direct.response({'ticket': ticket, 'status': 200, 'streaming': True})
        with self.assertRaises(DirectRejected):
            self.direct.response({'ticket': ticket, 'status': 200})

    def test_only_effective_options_can_receive_egress_permit(self):
        """真实引擎应保留本轮参数。错误参数不消耗步骤或打开代理。@return 无。"""
        schema = {"type": "json_schema", "schema": {"additionalProperties": False, "type": "object"}}
        self.claim.direct_options = {"output_config": {"format": schema}, "temperature": 0.4}
        self.direct.started.set()
        for options in (
            {"output_config": {"effort": "low"}, "temperature": 0.4},
            {"output_config": {"format": schema}, "temperature": 0.5},
            {"output_config": {"format": {**schema, "schema": {"additionalProperties": 0, "type": "object"}}},
             "temperature": 0.4},
        ):
            with self.subTest(options=options), self.assertRaises(DirectRejected):
                self.direct.permit({**self.offer, "body": json.dumps({"stream": True, **options})})
        self.assertFalse(self.step.claimed)
        self.actor.driver.launcher.direct_proxy.assert_not_called()
        body = json.dumps({"stream": True, "output_config": {"effort": "low", "format": schema}, "temperature": 0.4})
        self.direct.permit({**self.offer, "body": body})
        self.assertTrue(self.step.claimed)

    def test_same_account_proxy_receives_direct_tunnel_once(self):
        """连接只使用认领时的原代理。连接重试不再次打开隧道。@return 无。"""
        self.direct.started.set()
        self.direct.permit(self.offer)
        connection = SimpleNamespace(path='api.anthropic.com:443', send_error=Mock())
        with patch('tui_direct._cli_peer', return_value=True), patch('tui_direct._relay') as relay:
            self.direct.connect(connection)
            self.direct.connect(connection)
        relay.assert_awaited_once()
        self.assertEqual(relay.await_args.args[1].host, '192.0.2.8')
        connection.send_error.assert_called_once_with(403)

    def test_text_reaches_client_before_terminal_and_complete_usage(self):
        """首段在终态前发布。完整状态和累计用量按同一步关联。@return 无。"""
        self._start()
        self._text('A')
        self.assertEqual(self.events[-1]['delta']['text'], 'A')
        self.assertTrue(self.claim.opening_usage_placeholder)
        with self.assertRaises(DirectRejected):
            self.direct.observe({**self.scope, 'step': 1, 'chunk': {'kind': 'text', 'index': 0, 'text': 'wrong'}})
        self._text('B')
        self.direct.observe({**self.scope, 'chunk': {'kind': 'stop', 'stopReason': 'end_turn', 'usage': self.usage}})
        self.direct.close_response({**self.scope, 'answer': 'AB', 'reason': 'end_turn',
                                    'serverTools': 0, 'usage': self.usage})
        self.assertEqual(self.events[-1]['usage'], self.usage)
        self.assertIn(b'message_stop', self.step.final[0])

    def test_cut_and_empty_refusal_do_not_gain_content_or_terminal(self):
        """保留实际已交付分片。缺少完整来源时拒绝伪造末帧或计数。@return 无。"""
        self._start()
        with self.assertRaises(ModelResponseError):
            self.direct.close_response({**self.scope, 'answer': '', 'reason': 'refusal', 'serverTools': 0, 'usage': None})
        self.assertEqual(self.events, [])
        self._text('A')
        with self.assertRaises(ModelResponseError):
            self.direct.close_response({**self.scope, 'answer': 'A', 'reason': 'end_turn',
                                        'serverTools': 0, 'usage': self.usage})
        self.assertEqual([event['type'] for event in self.events],
                         ['message_start', 'content_block_start', 'content_block_delta'])
        self.assertIsNone(self.step.final)

    def test_actual_signed_thinking_uses_public_signature_delta(self):
        """公开开块和增量可还原原版同一步签名。@return 无。"""
        self._start()
        source = {"type": "thinking", "thinking": "实收思考", "signature": "tui-fixture-signature"}
        self.direct.observe({**self.scope, "blocks": [source]}, signed=True)
        self.assertEqual(self.events[1]["content_block"], {"type": "thinking", "thinking": "", "signature": ""})
        self.assertEqual([frame["delta"] for frame in self.events[2:4]],
                         [{"type": "thinking_delta", "thinking": source["thinking"]},
                          {"type": "signature_delta", "signature": source["signature"]}])
        self.assertEqual(self.events[4], {"type": "content_block_stop", "index": 0})
