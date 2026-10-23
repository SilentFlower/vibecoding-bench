"""外接需求方请求、有限降级和凭据边界的行为回归。"""
import json
import unittest
from io import BytesIO
from unittest.mock import Mock
from urllib.error import HTTPError, URLError

from project_dialogue import MAX_DIALOGUE_INPUT, ProjectDialogueClient, parse_dialogue


def _response(action='reply', message='Please explain the error path.', **extra):
    payload = {'model': 'provider-model', 'choices': [{'finish_reason': 'stop',
        'message': {'role': 'assistant', 'content': json.dumps({'action': action, 'message': message})}}],
        'usage': {'prompt_tokens': 11, 'completion_tokens': 5, 'total_tokens': 16,
            'prompt_tokens_details': {'cached_tokens': 7}}}
    payload.update(extra)
    response = Mock()
    response.status = 200
    response.read.return_value = json.dumps(payload).encode()
    response.__enter__ = Mock(return_value=response)
    response.__exit__ = Mock(return_value=False)
    return response


def _http_error(status, code='', secret=''):
    body = json.dumps({'error': {'code': code, 'message': 'private detail ' + secret}}).encode()
    return HTTPError('https://provider.example/v1/chat/completions', status, 'private error', {}, BytesIO(body))


class DialogueClientTests(unittest.TestCase):
    """一轮只生成一条有效消息，故障和配置问题不能变成业务失败。"""

    def setUp(self) -> None:
        """配置受控发送器与不含敏感内容的业务输入。@return None。"""
        self.opener = Mock()
        self.key = 'dummy-private-key-123'
        self.client = ProjectDialogueClient('https://provider.example/v1', self.key, 'primary', 'secondary', opener=self.opener)
        self.context = {'goal': 'Handle a real bug.', 'phase': 'planning',
            'conversation': [{'role': 'assistant', 'content': 'The entry path is understood.'}]}

    def test_valid_message_uses_chat_protocol_and_preserves_usage(self) -> None:
        """正文使用实际上下文，认证只在头部，记录实际用量。@return None。"""
        self.opener.open.return_value = _response()
        result = self.client.generate(self.context)
        request = self.opener.open.call_args.args[0]
        body = json.loads(request.data)
        self.assertEqual('https://provider.example/v1/chat/completions', request.full_url)
        self.assertEqual('Bearer ' + self.key, request.get_header('Authorization'))
        self.assertNotIn(self.key, request.data.decode())
        self.assertEqual(('primary', False), (body['model'], body['stream']))
        self.assertEqual(self.context, json.loads(body['messages'][1]['content']))
        self.assertEqual(('ready', 'reply', 7), (result['status'], result['action'], result['usage']['cached_tokens']))
        self.assertEqual('provider-model', result['response_model'])
        self.assertEqual(1, len(result['attempts']))

    def test_quota_rate_limit_and_service_failure_switch_once(self) -> None:
        """额度不足或暂时故障只切一次备用，返回一条消息。@return None。"""
        for status, code, category in ((402, '', 'quota'), (429, '', 'rate_limit'),
                (500, '', 'unavailable'), (502, '', 'unavailable'), (503, '', 'unavailable'), (504, '', 'unavailable'),
                (200, 'insufficient_quota', 'quota')):
            with self.subTest(status=status):
                if status == 200:
                    failed = _response(error={'code': code})
                else:
                    failed = _http_error(status)
                self.opener.reset_mock()
                self.opener.open.side_effect = [failed, _response('implement', 'Please implement this plan.')]
                result = self.client.generate(self.context)
                self.assertEqual(('ready', 'secondary', category),
                    (result['status'], result['model'], result['fallback_reason']))
                self.assertEqual(['primary', 'secondary'],
                    [json.loads(call.args[0].data)['model'] for call in self.opener.open.call_args_list])

    def test_authentication_and_bad_arguments_do_not_hide_configuration_failure(self) -> None:
        """认证和参数错误直接保留故障，错误原文不会进入公开结果。@return None。"""
        for status in (400, 401, 403, 404):
            with self.subTest(status=status):
                self.opener.reset_mock()
                self.opener.open.side_effect = _http_error(status, secret=self.key)
                result = self.client.generate(self.context)
                self.assertEqual('error', result['status'])
                self.assertEqual(1, self.opener.open.call_count)
                self.assertNotIn(self.key, json.dumps(result))
                self.assertNotIn('private detail', json.dumps(result))

    def test_both_models_fail_without_a_message_or_retry_loop(self) -> None:
        """主备均失败时只有两次调用，不能发送空问题或声明任务完成。@return None。"""
        self.opener.open.side_effect = [_http_error(429), URLError('connection failed')]
        result = self.client.generate(self.context)
        self.assertEqual(('error', 2), (result['status'], self.opener.open.call_count))
        self.assertNotIn('message', result)
        self.assertNotIn('action', result)

    def test_restored_fallback_does_not_retry_exhausted_primary(self) -> None:
        """任务已降级时继续用备用，避免每轮重复请求耗尽主模型。@return None。"""
        self.opener.open.return_value = _response()
        self.client.generate(self.context, preferred_model='secondary')
        self.assertEqual('secondary', json.loads(self.opener.open.call_args.args[0].data)['model'])
        self.assertEqual(1, self.opener.open.call_count)
        with self.assertRaises(ValueError):
            self.client.generate(self.context, preferred_model='unconfigured')

    def test_incomplete_tool_or_refused_answers_never_become_user_messages(self) -> None:
        """截断、工具调用和拒绝回复不投递，也不靠换模型掩盖。@return None。"""
        for choice in (
            {'finish_reason': 'length', 'message': {'role': 'assistant', 'content': '{}'}},
            {'finish_reason': 'stop', 'message': {'role': 'assistant', 'content': '{}', 'tool_calls': [{}]}},
            {'finish_reason': 'stop', 'message': {'role': 'assistant', 'content': '{}', 'refusal': 'No'}},
            {'finish_reason': 'stop', 'message': {'role': 'assistant', 'content': self.key}},
        ):
            with self.subTest(choice=choice['finish_reason']):
                self.opener.reset_mock()
                self.opener.open.return_value = _response(choices=[choice])
                result = self.client.generate(self.context)
                self.assertEqual(('error', 'invalid_response', 1),
                    (result['status'], result['category'], self.opener.open.call_count))
                self.assertNotIn(self.key, json.dumps(result))

    def test_configuration_and_public_input_are_checked_before_sending(self) -> None:
        """未启用兼容旧功能，部分配置和不安全输入不能发出请求。@return None。"""
        self.assertIsNone(ProjectDialogueClient.from_environment({}))
        for base in ('http://provider.example/v1', 'https://name:secret@provider.example/v1',
                'https://provider.example/v1?key=secret'):
            with self.subTest(base=base), self.assertRaises(ValueError):
                ProjectDialogueClient(base, self.key, 'primary')
        with self.assertRaises(ValueError):
            ProjectDialogueClient.from_environment({'PROJECT_REQUESTER_MODEL': 'primary'})
        for context in ({'text': self.key}, {'text': 'x' * MAX_DIALOGUE_INPUT}):
            with self.assertRaises(ValueError):
                self.client.generate(context)
        self.opener.open.assert_not_called()

    def test_same_primary_and_fallback_are_not_called_twice(self) -> None:
        """配置相同模型时故障不重复消费同一路径。@return None。"""
        client = ProjectDialogueClient('https://provider.example/v1', self.key, 'primary', 'primary', opener=self.opener)
        self.opener.open.side_effect = _http_error(429)
        result = client.generate(self.context)
        self.assertEqual(('error', 1), (result['status'], self.opener.open.call_count))

    def test_escaped_secret_and_model_metadata_are_never_returned(self) -> None:
        """解析后的密钥及异常模型元数据都不能进入持久结果。@return None。"""
        encoded = json.dumps({'action': 'reply', 'message': self.key}).replace('dummy', '\\u0064ummy')
        self.opener.open.return_value = _response(model=self.key, choices=[{'finish_reason': 'stop',
            'message': {'role': 'assistant', 'content': encoded}}])
        result = self.client.generate(self.context)
        self.assertEqual('error', result['status'])
        self.assertNotIn(self.key, json.dumps(result))

    def test_remaining_budget_limits_network_timeout(self) -> None:
        """接续使用剩余片段上限，不能重新领取完整网络时限。@return None。"""
        self.opener.open.return_value = _response()
        self.client.generate(self.context, timeout_sec=0.5)
        self.assertLessEqual(self.opener.open.call_args.kwargs['timeout'], 0.5)
        with self.assertRaises(ValueError):
            self.client.generate(self.context, timeout_sec=0)


class DialogueProtocolTests(unittest.TestCase):
    """需求方返回的动作不能模糊、重复或被包装文本替代。"""

    def test_only_valid_actions_and_complete_json_are_accepted(self) -> None:
        """额外字段、重复字段、评分结论和空问题均拒绝。@return None。"""
        self.assertEqual({'action': 'verify', 'message': ''}, parse_dialogue('{"action":"verify","message":""}'))
        for raw in ('{"action":"pass","message":"done"}', '{"action":"reply","message":" "}',
                '{"action":"reply","message":"Question","score":1}',
                '{"action":"reply","action":"verify","message":"Question"}',
                '```json\n{"action":"reply","message":"Question"}\n```'):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                parse_dialogue(raw)


if __name__ == '__main__':
    unittest.main()
