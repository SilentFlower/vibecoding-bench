"""结果导出真正投影所选变量，包括单列与零列。"""
import unittest
from constraint import Problem


def test_one_column_reorder_and_empty_projection():
    """单列必须是一元tuple，不能偷用全部values。@return None。"""
    problem=Problem();problem.addVariable('a',[1]);problem.addVariable('b',[2,3])
    assert set(problem.getSolutionsOrderedList(['a']))=={(1,)}
    assert set(problem.getSolutionsOrderedList(['b','a']))=={(2,1),(3,1)}
    assert problem.getSolutionsOrderedList([])==[(),()]
    with unittest.TestCase().assertRaises(ValueError):problem.getSolutionsAsListDict(['a'])
    assert problem.getSolutionsAsListDict(['a'],validate=False)[2]==2


def test_non_string_identifiers_and_validation_before_solving():
    """任意hashable身份保持；未知、重复与含糊order明确拒绝。@return None。"""
    problem=Problem();problem.addVariable(('slot',1),[4]);problem.addVariable(7,[5])
    assert problem.getSolutionsOrderedList([7,('slot',1)])==[(5,4)]
    for order in ([7,7],['missing'],'abc'):
        with unittest.TestCase().assertRaises(ValueError):problem.getSolutionsOrderedList(order)
    assert len(problem.getSolutionsOrderedList(None)[0])==2

