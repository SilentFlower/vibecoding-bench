"Public regression tests for PYTHON-CONSTRAINT-05-DEV; the complete business contract is in materials/PYTHON-CONSTRAINT-05-DEV-contract.md."
import unittest
from constraint import Problem
from constraint.cardinality import GlobalCardinality


def test_per_value_bounds_and_unknown_value_policy():
    "Verify per value bounds and unknown value policy."
    problem=Problem();problem.addVariables(['x','y','z'],['A','B','C']);problem.addConstraint(GlobalCardinality({'A':(2,2),'B':(1,2)}),['x','y','z'])
    result=problem.getSolutions()
    assert len(result)==3 and all(list(item.values()).count('A')==2 and list(item.values()).count('B')==1 for item in result)
    open_problem=Problem();open_problem.addVariable('x',['A','C']);open_problem.addConstraint(GlobalCardinality({'A':(0,0)},closed=False),['x'])
    assert open_problem.getSolutions()==[{'x':'C'}] and list(open_problem._variables['x'])==['A','C']


def test_impossible_bounds_and_bad_ranges():
    "Verify impossible bounds and bad ranges."
    problem=Problem();problem.addVariables(['a','b'],['A','B']);problem.addConstraint(GlobalCardinality({'A':(3,3),'B':(0,2)}),['a','b'])
    assert problem.getSolutions()==[]
    for bounds in ({'A':(-1,2)},{'A':(2,1)},{'A':(True,2)}):
        with unittest.TestCase().assertRaises(ValueError):GlobalCardinality(bounds)

