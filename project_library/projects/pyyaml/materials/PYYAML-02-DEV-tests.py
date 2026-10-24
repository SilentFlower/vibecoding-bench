"""坏显式标量统一为YAMLError带位置，不泄漏裸内部转换错误。"""
import unittest
import yaml
from yaml.constructor import ConstructorError

def test_invalid_bool_int_float_timestamp_and_ranges_are_marked():
    """四类非法标签及真实日期范围错误都能用YAMLError捕获。@return None。"""
    for source in ('!!bool maybe','!!int nope','!!float nope','!!timestamp nope','!!int ""','!!float "+"','!!timestamp 2024-02-30'):
        with unittest.TestCase().assertRaises(ConstructorError) as context:yaml.safe_load('value: '+source)
        assert isinstance(context.exception,yaml.YAMLError) and context.exception.problem_mark.line==0
        assert context.exception.problem_mark.column==7

def test_legal_values_and_nested_position_keep_types():
    """合法显式值不改，不吞未知自定义构造器程序错误。@return None。"""
    result=yaml.safe_load('a: !!bool yes\nb: !!int 0x10\nc: !!float 1.25\nd: !!timestamp 2024-01-02')
    assert result['a'] is True and result['b']==16 and result['c']==1.25 and result['d'].year==2024
    with unittest.TestCase().assertRaises(ConstructorError) as context:yaml.safe_load('a:\n  b: !!int nope')
    assert context.exception.problem_mark.line==1 and isinstance(context.exception.__cause__,ValueError)

