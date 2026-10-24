"""日期/日期时间对解析溢出使用原声明错误政策。"""
import unittest
from sqlite_utils import recipes

def test_both_recipes_ignore_or_null_overflow_without_changing_defaults():
    """真实超大年份引发溢出，不能仅mock异常冒充业务。@return None。"""
    value='999999999999999999999-01-01'
    for function in (recipes.parsedate,recipes.parsedatetime):
        assert function(value,errors=recipes.IGNORE)==value
        assert function(value,errors=recipes.SET_NULL) is None
        with unittest.TestCase().assertRaises((OverflowError,ValueError)):function(value)

def test_normal_dates_parser_errors_empty_and_falsey_values_keep_policy():
    """合法日期、普通无效输入、None/空字符串原语义保持。@return None。"""
    assert recipes.parsedate('2024-02-29')=='2024-02-29'
    assert recipes.parsedatetime('2024-02-29 13:45:00')=='2024-02-29T13:45:00'
    for function in (recipes.parsedate,recipes.parsedatetime):
        assert function('',errors=recipes.SET_NULL)=='' and function(None) is None
        assert function('not-a-date',errors=recipes.IGNORE)=='not-a-date'
        assert function('not-a-date',errors=recipes.SET_NULL) is None

