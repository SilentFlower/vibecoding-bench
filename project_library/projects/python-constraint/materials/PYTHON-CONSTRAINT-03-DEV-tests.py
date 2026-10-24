"Public regression tests for PYTHON-CONSTRAINT-03-DEV; the complete business contract is in materials/PYTHON-CONSTRAINT-03-DEV-contract.md."
import unittest
from constraint import Problem,Domain


def test_generator_and_tuple_identity_have_independent_domains():
    "Verify generator and tuple identity have independent domains."
    problem=Problem();problem.addVariables(['a','b'],(value for value in [1,2]))
    assert len(problem.getSolutions())==4 and problem._variables['a'] is not problem._variables['b']
    another=Problem();another.addVariable(('slot',1),(value for value in [1,2]))
    assert len(another.getSolutions())==2


def test_failed_batch_and_query_preprocessing_leave_model_intact():
    "Verify failed batch and query preprocessing leave model intact."
    problem=Problem();problem.addVariable('old',[1])
    for variables,domain in ((['new','old'],[1]),(['x','x'],[1]),(['x'],[])):
        with unittest.TestCase().assertRaises(ValueError):problem.addVariables(variables,domain)
        assert set(problem._variables)=={'old'}
    problem.addVariable('x',Domain([0,1,2]));problem.addConstraint(lambda x:x>0,['x'])
    assert len(problem.getSolutions())==2 and list(problem._variables['x'])==[0,1,2]

