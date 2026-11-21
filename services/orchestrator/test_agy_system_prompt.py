"""以固定参考向量验证系统文本策略的字段边界、快照和敏感保护。"""
import copy
import json
import unittest

from agy_runtime.contract import InputError
from agy_runtime.gemini_contract import decode_request
from agy_runtime.system_prompt import (
    POLICY_SOURCE, REMINDER_SYSTEM_INSTRUCTION, RULE_VERSION, USER_REMINDER_SOURCE,
    decode_policy, default_policy, transform_system,
)


class AgySystemPromptTests(unittest.TestCase):
    """覆盖原生提交前的独立系统段与固定映射合同。"""

    def setUp(self):
        """准备合成账号策略。@return 无。"""
        self.enabled = {**default_policy(), 'enabled': True}

    def test_reference_golden_vectors_and_idempotence(self):
        """固定参考向量防止相似字形误选，并核对全部26字符。@return 无。"""
        source = 'ABCEHJKMNPSTXYZacdeghjpsxy'
        target = 'ΑΒСЕНЈΚΜΝРЅΤХΥΖасԁеɡһјрѕху'
        converted, report = transform_system(source, self.enabled)
        self.assertEqual(converted, target)
        self.assertEqual(report['replaced_codepoints'], 26)
        self.assertEqual(len(source), len(converted))
        self.assertEqual(transform_system(converted, self.enabled)[0], converted)
        self.assertEqual(transform_system('ABC system 中文 {x: 3}', self.enabled)[0], 'ΑΒС ѕуѕtеm 中文 {х: 3}')

    def test_disabled_and_large_unicode_system_keep_explicit_semantics(self):
        """关闭保持原文，Unicode大文本再次经过保持稳定且无新增替换。@return 无。"""
        source = ('ABC system 中文 😀\n' * 65536)
        self.assertEqual(transform_system(source, default_policy())[0], source)
        converted, first = transform_system(source, self.enabled)
        again, second = transform_system(converted, self.enabled)
        self.assertEqual(len(converted), len(source))
        self.assertEqual(again, converted)
        self.assertTrue(first['changed'])
        self.assertFalse(second['changed'])
        self.assertEqual(second['replaced_codepoints'], 0)
        self.assertFalse(transform_system('', self.enabled)[1]['changed'])

    def test_only_system_changes_original_history_tools_and_signatures_survive(self):
        """比较真实Gemini解码，转换后的原生历史及原始入站保持独立。@return 无。"""
        body = {'systemInstruction': {'parts': [{'text': 'ABC system'}, {'text': '中文 😀 {x: 3}'}]},
            'tools': [{'functionDeclarations': [{'name': 'ABC_tool', 'parameters': {'type': 'OBJECT', 'properties': {'x': {'type': 'STRING'}}}}]}],
            'contents': [{'role': 'user', 'parts': [{'text': 'ABC system'}]},
                {'role': 'model', 'parts': [{'functionCall': {'id': 'ABC-id', 'name': 'ABC_tool', 'args': {'x': 'ABC system'}}, 'thoughtSignature': 'c2ln'}]},
                {'role': 'user', 'parts': [{'functionResponse': {'id': 'ABC-id', 'name': 'ABC_tool', 'response': {'ABC': 'ABC system'}}}]}]}
        original = copy.deepcopy(body)
        raw = {'schema_version': 1, 'type': 'gemini_request', 'request_id': 'synthetic',
            'model': 'gemini-synthetic', 'native_model': 'MODEL_PLACEHOLDER_M36', 'body': body}
        before = decode_request(raw)
        after = decode_request({**raw, 'system_prompt_policy': self.enabled})
        self.assertEqual(body, original)
        self.assertEqual(before['gemini_body'], original)
        self.assertEqual(after['gemini_body'], original)
        self.assertEqual(before['native_steps'], after['native_steps'])
        self.assertEqual(before['tools'], after['tools'])
        self.assertNotEqual(before['system'], after['system'])
        self.assertEqual(after['system'], transform_system(before['system'], self.enabled)[0])
        self.assertEqual(after['system_prompt_policy']['rule_version'], RULE_VERSION)
        report = json.dumps(after['system_prompt_policy'])
        self.assertNotIn('ABC system', report)
        self.assertNotIn('ABC-id', report)

    def test_reminder_and_homoglyph_policies_compose_before_native_history(self):
        """核对四种组合、原始历史、工具和回执来源。@return 无。"""
        body = {
            'systemInstruction': {'parts': [{'text': 'ABC system'}, {'text': '中文 {x: 3}'}]},
            'contents': [
                {'role': 'user', 'parts': [{'text': 'ABC user'}, {'text': '<system-reminder>ABC</system-reminder>'}]},
                {'role': 'model', 'parts': [
                    {'functionCall': {'id': 'sample', 'name': 'lookup', 'args': {'x': 'ABC'}}, 'thoughtSignature': 'c2ln'},
                ]},
                {'role': 'user', 'parts': [
                    {'functionResponse': {'id': 'sample', 'name': 'lookup', 'response': {'value': 'ABC'}}},
                ]},
            ],
        }
        original = copy.deepcopy(body)
        raw = {'schema_version': 1, 'type': 'gemini_request', 'request_id': 'synthetic',
            'model': 'gemini-synthetic', 'native_model': 'MODEL_PLACEHOLDER_M36', 'body': body}
        original_steps = decode_request(raw)['native_steps']
        expected = ('ABC system\n中文 {x: 3}', 'ΑΒС ѕуѕtеm\n中文 {х: 3}')
        for glyphs in (False, True):
            for reminder in (False, True):
                with self.subTest(glyphs=glyphs, reminder=reminder):
                    policy = {**default_policy(), 'enabled': glyphs}
                    if reminder:
                        policy['user_reminder_index'] = 0
                    decoded = decode_request({**raw, 'system_prompt_policy': policy})
                    self.assertEqual(body, original)
                    self.assertEqual(decoded['gemini_body'], original)
                    self.assertEqual(decoded['native_steps'][1:], original_steps[1:])
                    self.assertEqual(decoded['system'], REMINDER_SYSTEM_INSTRUCTION if reminder else expected[glyphs])
                    user = decoded['native_steps'][0]['userInput']['userResponse']
                    original_user = original_steps[0]['userInput']['userResponse']
                    self.assertEqual(user, original_user + (
                        f'\n<system-reminder>\n{expected[glyphs]}\n</system-reminder>' if reminder else ''
                    ))
                    report = decoded['system_prompt_policy']
                    self.assertEqual(report['source'], USER_REMINDER_SOURCE if reminder else POLICY_SOURCE)
                    self.assertEqual(report['changed'], glyphs)
                    self.assertNotIn('user_reminder_index', report)

        for index in (1, 2, 3):
            with self.subTest(index=index), self.assertRaisesRegex(InputError, 'invalid_system_reminder_target'):
                decode_request({**raw, 'system_prompt_policy': {**default_policy(), 'user_reminder_index': index}})

    def test_malformed_or_unknown_policy_never_becomes_truthy_configuration(self):
        """未知规则及畸形布尔显式拒绝，缺省仅由调用边界解释。@return 无。"""
        for value in [None, True, {}, {**self.enabled, 'enabled': 'false'}, {**self.enabled, 'schema_version': True},
                {**self.enabled, 'rule_version': 'unknown'}, {**self.enabled, 'source': 'public'},
                {**self.enabled, 'user_reminder_index': True}, {**self.enabled, 'user_reminder_index': -1}]:
            with self.subTest(value=value), self.assertRaises(InputError):
                decode_policy(value)

    def test_public_body_cannot_override_account_policy(self):
        """用户载荷不能把内部策略字段作为公开开关。@return 无。"""
        raw = {'schema_version': 1, 'type': 'gemini_request', 'request_id': 'synthetic',
            'model': 'gemini-synthetic', 'native_model': 'MODEL_PLACEHOLDER_M36', 'body': {'contents': [{'parts': [{'text': 'ABC'}]}],
                'system_prompt_policy': self.enabled}}
        with self.assertRaises(InputError):
            decode_request(raw)


if __name__ == '__main__':
    unittest.main()
