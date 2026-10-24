"""字符串编译结果属于本次求解，不累积污染模型。"""
from constraint import Problem,BacktrackingSolver,OptimizedBacktrackingSolver


def test_repeated_mixed_constraints_do_not_accumulate():
    """真实求解十次，显式用户约束仍保留而编译列表不长。@return None。"""
    problem=Problem();problem.addVariables(['x','y'],[0,1,2]);problem.addConstraint('x != y')
    problem.addConstraint(lambda x,y:x+y>=2,['x','y'])
    expected={tuple(sorted(item.items())) for item in problem.getSolutions()}
    for index in range(10):
        problem.setSolver(BacktrackingSolver() if index%2 else OptimizedBacktrackingSolver())
        assert {tuple(sorted(item.items())) for item in problem.getSolutions()}==expected
        assert len(problem._constraints)==1 and len(problem._str_constraints)==1


def test_reset_clears_textual_rules_and_model_can_change():
    """reset后旧字符串不能误作用到新变量。@return None。"""
    problem=Problem();problem.addVariables(['a','b'],[1,2]);problem.addConstraint('a < b')
    assert problem.getSolutions()==[{'a':1,'b':2}]
    problem.reset();problem.addVariable('new',[7])
    assert problem.getSolution()=={'new':7} and not problem._str_constraints

