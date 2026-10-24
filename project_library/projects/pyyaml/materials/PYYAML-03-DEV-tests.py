"""严格配置重复字段带首次/再次位置，默认兼容仍不变。"""
import unittest
import yaml
from yaml.strict import strict_load
from yaml.constructor import ConstructorError

def test_explicit_duplicates_mark_both_occurrences_and_default_still_overwrites():
    """嵌套字段和Python相等键碰撞均可诊断。@return None。"""
    with unittest.TestCase().assertRaises(ConstructorError) as context:strict_load('a: 1\na: 2')
    assert context.exception.context_mark.line==0 and context.exception.problem_mark.line==1
    assert yaml.safe_load('a: 1\na: 2')=={'a':2}
    with unittest.TestCase().assertRaises(ConstructorError):strict_load('1: first\ntrue: second')

def test_merge_local_override_and_alias_reuse_are_valid():
    """继承键和本地覆盖不是两个显式声明，不误判。@return None。"""
    text='base: &base {x: 1, y: 2}\nfirst: {<<: *base, x: 3}\nsecond: {<<: *base, x: 4}'
    value=strict_load(text)
    assert value['first']=={'x':3,'y':2} and value['second']=={'x':4,'y':2}

