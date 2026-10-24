"""同时约束多个班次人数，不是把SomeInSet改名。"""
import unittest
from constraint import Problem
from constraint.cardinality import GlobalCardinality


def test_per_value_bounds_and_unknown_value_policy():
    """A恰好两人、B一至两人，未列值按显式政策。@return None。"""
    problem=Problem();problem.addVariables(['x','y','z'],['A','B','C']);problem.addConstraint(GlobalCardinality({'A':(2,2),'B':(1,2)}),['x','y','z'])
    result=problem.getSolutions()
    assert len(result)==3 and all(list(item.values()).count('A')==2 and list(item.values()).count('B')==1 for item in result)
    open_problem=Problem();open_problem.addVariable('x',['A','C']);open_problem.addConstraint(GlobalCardinality({'A':(0,0)},closed=False),['x'])
    assert open_problem.getSolutions()==[{'x':'C'}] and list(open_problem._variables['x'])==['A','C']


def test_impossible_bounds_and_bad_ranges():
    """逻辑无解与声明范围错误有明确区别。@return None。"""
    problem=Problem();problem.addVariables(['a','b'],['A','B']);problem.addConstraint(GlobalCardinality({'A':(3,3),'B':(0,2)}),['a','b'])
    assert problem.getSolutions()==[]
    for bounds in ({'A':(-1,2)},{'A':(2,1)},{'A':(True,2)}):
        with unittest.TestCase().assertRaises(ValueError):GlobalCardinality(bounds)

