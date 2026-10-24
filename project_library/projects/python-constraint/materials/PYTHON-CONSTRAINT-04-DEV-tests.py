"Public regression tests for PYTHON-CONSTRAINT-04-DEV; the complete business contract is in materials/PYTHON-CONSTRAINT-04-DEV-contract.md."
import unittest
from constraint import Problem
from constraint.tables import AllowedTuples,ForbiddenTuples


def test_allowed_table_snapshot_and_forbidden_complement():
    "Verify allowed table snapshot and forbidden complement."
    rows=[('A',1),('B',2)]
    allowed=AllowedTuples(rows);rows.append(('A',2))
    problem=Problem();problem.addVariable('course',['A','B']);problem.addVariable('room',[1,2]);problem.addConstraint(allowed,['course','room'])
    assert {(row['course'],row['room']) for row in problem.getSolutions()}=={('A',1),('B',2)}
    other=Problem();other.addVariable('course',['A','B']);other.addVariable('room',[1,2]);other.addConstraint(ForbiddenTuples([('A',1)]),['course','room'])
    assert {(row['course'],row['room']) for row in other.getSolutions()}=={('A',2),('B',1),('B',2)}


def test_unary_preprocessing_and_bad_shape_do_not_mutate_model():
    "Verify unary preprocessing and bad shape do not mutate model."
    problem=Problem();problem.addVariable('x',[1,2,3]);problem.addConstraint(AllowedTuples([(2,)]),['x'])
    assert problem.getSolutions()==[{'x':2}] and list(problem._variables['x'])==[1,2,3]
    with unittest.TestCase().assertRaises(ValueError):AllowedTuples([(1,2),(3,)])
    with unittest.TestCase().assertRaises(ValueError):AllowedTuples([(1,),(2,)],max_rows=1)

