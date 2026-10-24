"""批量更新接受一次性pairs，不重复现成的pmap构造能力。"""
import operator
import unittest
from pyrsistent import pmap,CheckedPMap


def test_mapping_pairs_generators_duplicate_keys_and_merge_order():
    """多输入从左到右，重复pairs也按本轮先后合并。@return None。"""
    original=pmap({'x':1})
    assert original.update([('x',2),('x',3),('y',4)])=={'x':3,'y':4}
    assert original.update_with(operator.add,(item for item in [('x',2),('x',3)]),{'x':4})=={'x':10}
    assert original=={'x':1}


def test_malformed_iteration_or_conflict_failure_leaves_original():
    """持久原对象不因输入中途失败而留下部分更新。@return None。"""
    original=pmap({'x':1})
    def broken():
        """真实一次性输入失败。@return pairs迭代器。"""
        yield 'y',2
        raise RuntimeError('source failed')
    with unittest.TestCase().assertRaises(RuntimeError):original.update(broken())
    with unittest.TestCase().assertRaises(ValueError):original.update([('bad',)])
    assert original=={'x':1}
    class Checked(CheckedPMap):
        """真实类型规则保持。"""
        __key_type__=str;__value_type__=int
    assert Checked({'a':1}).update([('b',2)])=={'a':1,'b':2}
    with unittest.TestCase().assertRaises(TypeError):Checked({'a':1}).update([('b','bad')])

