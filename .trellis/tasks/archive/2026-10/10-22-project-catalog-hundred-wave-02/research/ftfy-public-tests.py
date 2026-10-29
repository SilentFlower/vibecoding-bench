"""解释开关只能影响解释输出，不能改写调用方选择的修整政策。"""
import unittest

from ftfy import TextFixerConfig, apply_plan, fix_and_explain, fix_text, fix_text_segment


class ExplanationConfigurationTests(unittest.TestCase):
    """公开回归覆盖真实禁用配置、组合选项和默认兼容。"""

    def test_decode_opt_out_survives_explanation_disable(self) -> None:
        """混合语言输入不因关闭解释而启用被禁用的修整。@return None。"""
        result = fix_and_explain('中文 cafÃ©', TextFixerConfig(decode_inconsistent_utf8=False, explain=False))
        self.assertEqual(result.text, '中文 cafÃ©')
        self.assertIsNone(result.explanation)

    def test_compound_encoding_options_are_forwarded_together(self) -> None:
        """不能只转交一个开关而丢掉其余配置。@return None。"""
        config = TextFixerConfig(decode_inconsistent_utf8=False, restore_byte_a0=False, explain=False)
        self.assertEqual(fix_and_explain('voilÃ le travail', config).text, 'voilÃ le travail')

    def test_keyword_and_nonexplaining_entrypoints_respect_options(self) -> None:
        """对象和关键字两种配置入口及便利函数都保持原政策。@return None。"""
        for function in (fix_text, fix_text_segment):
            with self.subTest(function=function.__name__):
                self.assertEqual(function('中文 cafÃ©', decode_inconsistent_utf8=False), '中文 cafÃ©')
        self.assertEqual(fix_and_explain('中文 cafÃ©', explain=False, decode_inconsistent_utf8=False).text, '中文 cafÃ©')

    def test_default_and_encoding_disabled_controls(self) -> None:
        """默认修整和全编码禁用两种既有语义不变。@return None。"""
        self.assertEqual(fix_text('schÃ¶n'), 'schön')
        self.assertEqual(fix_and_explain('schÃ¶n', TextFixerConfig(explain=False)).text, 'schön')
        self.assertEqual(fix_text('schÃ¶n', fix_encoding=False), 'schÃ¶n')

    def test_explanation_is_replayable_and_only_absent_when_disabled(self) -> None:
        """开启解释仍可重放，关闭后保留相同正确文本。@return None。"""
        source = 'schÃ¶n'
        enabled = fix_and_explain(source)
        disabled = fix_and_explain(source, explain=False)
        self.assertIsInstance(enabled.explanation, list)
        self.assertEqual(apply_plan(source, enabled.explanation), 'schön')
        self.assertEqual(enabled.text, disabled.text)
        self.assertIsNone(disabled.explanation)


if __name__ == '__main__':
    unittest.main()
