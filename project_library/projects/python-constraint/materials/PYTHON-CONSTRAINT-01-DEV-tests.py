"Public regression tests for PYTHON-CONSTRAINT-01-DEV; the complete business contract is in materials/PYTHON-CONSTRAINT-01-DEV-contract.md."
from constraint import Problem,BacktrackingSolver,OptimizedBacktrackingSolver


def test_repeated_mixed_constraints_do_not_accumulate():
    "Verify repeated mixed constraints do not accumulate."
    problem=Problem();problem.addVariables(['x','y'],[0,1,2]);problem.addConstraint('x != y')
    problem.addConstraint(lambda x,y:x+y>=2,['x','y'])
    expected={tuple(sorted(item.items())) for item in problem.getSolutions()}
    for index in range(10):
        problem.setSolver(BacktrackingSolver() if index%2 else OptimizedBacktrackingSolver())
        assert {tuple(sorted(item.items())) for item in problem.getSolutions()}==expected
        assert len(problem._constraints)==1 and len(problem._str_constraints)==1


def test_reset_clears_textual_rules_and_model_can_change():
    "Verify reset clears textual rules and model can change."
    problem=Problem();problem.addVariables(['a','b'],[1,2]);problem.addConstraint('a < b')
    assert problem.getSolutions()==[{'a':1,'b':2}]
    problem.reset();problem.addVariable('new',[7])
    assert problem.getSolution()=={'new':7} and not problem._str_constraints

