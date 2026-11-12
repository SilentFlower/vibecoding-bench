"Public regression tests for PYTHON-CONSTRAINT-02-DEV; the complete business contract is in materials/PYTHON-CONSTRAINT-02-DEV-contract.md."
import unittest
from constraint import Problem


def test_one_column_reorder_and_empty_projection():
    "Verify one column reorder and empty projection."
    problem=Problem();problem.addVariable('a',[1]);problem.addVariable('b',[2,3])
    assert set(problem.getSolutionsOrderedList(['a']))=={(1,)}
    assert set(problem.getSolutionsOrderedList(['b','a']))=={(2,1),(3,1)}
    assert problem.getSolutionsOrderedList([])==[(),()]
    with unittest.TestCase().assertRaises(ValueError):problem.getSolutionsAsListDict(['a'])
    assert problem.getSolutionsAsListDict(['a'],validate=False)[2]==2


def test_non_string_identifiers_and_validation_before_solving():
    "Verify non string identifiers and validation before solving."
    problem=Problem();problem.addVariable(('slot',1),[4]);problem.addVariable(7,[5])
    assert problem.getSolutionsOrderedList([7,('slot',1)])==[(5,4)]
    for order in ([7,7],['missing'],'abc'):
        with unittest.TestCase().assertRaises(ValueError):problem.getSolutionsOrderedList(order)
    assert len(problem.getSolutionsOrderedList(None)[0])==2

