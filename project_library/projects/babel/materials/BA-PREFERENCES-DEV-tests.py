"""带权语言偏好公开回归，完整约定见同目录工程合同。"""
import pytest
from babel.core import negotiate_locale_preferences

def test_quality_and_available_spelling_are_preserved():
    """质量排序和可用区域原拼写均须保持。:return: None。"""
    assert negotiate_locale_preferences('en-US;q=0.5, de-DE;q=0.9', ['en_US','de_DE']) == 'de_DE'
    assert negotiate_locale_preferences('de-de', ['de_de']) == 'de_de'

def test_ties_and_iterable_available_are_stable():
    """同权偏好顺序及一次性迭代器可正常使用。:return: None。"""
    assert negotiate_locale_preferences('fr, de', iter(['de','fr'])) == 'fr'

def test_zero_quality_excludes_language_from_wildcard():
    """通配符遵守排除，未明确的显式冲突允许合理解释。:return: None。"""
    assert negotiate_locale_preferences('en;q=0, *;q=0.5', ['en_US','fr']) == 'fr'
    assert negotiate_locale_preferences('*;q=0', ['fr']) is None
    assert negotiate_locale_preferences('en;q=0, en-US;q=1, fr;q=0.1', ['en_US','fr']) in ('en_US','fr')

def test_aliases_and_invalid_headers_have_explicit_behavior():
    """别名兼容，非法参数和超限输入明确拒绝。:return: None。"""
    assert negotiate_locale_preferences('no', ['nb_NO']) == 'nb_NO'
    for value in ('en;q=1.1', 'en;q=0.1234', 'en;bad=1', 'en,' * 100):
        with pytest.raises(ValueError):
            negotiate_locale_preferences(value, ['en'])
