"""小型合成输入证明节点/深度/别名预算，不制造资源攻击。"""
import unittest
from yaml.limits import load_limited
from yaml import YAMLError

def test_under_limits_and_exact_counts_preserve_values():
    """根序列+两标量共3唯一节点，根深度1。@return None。"""
    assert load_limited('[a,b]',max_nodes=3,max_depth=2,max_chars=5)==['a','b']
    assert load_limited('a: &a [1]\nb: *a',max_aliases=1)['a']==[1]
    assert load_limited('',max_nodes=0,max_depth=0) is None

def test_each_budget_rejects_with_mark_where_available():
    """0别名/不足节点/过深和字符超限均明确YAMLError。@return None。"""
    for text,limits in (('[a,b]',{'max_nodes':2}),('[[a]]',{'max_depth':2}),('a: &a [1]\nb: *a',{'max_aliases':0}),('hello',{'max_chars':4})):
        with unittest.TestCase().assertRaises(YAMLError):load_limited(text,**limits)
    with unittest.TestCase().assertRaises(TypeError):load_limited(b'hello')
    with unittest.TestCase().assertRaises(ValueError):load_limited('hello',max_nodes=True)

