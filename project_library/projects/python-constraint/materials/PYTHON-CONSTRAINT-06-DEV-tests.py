"""最优值来自真实可行解，部分搜索绝不标已最优。"""
import unittest
from constraint import Problem,BacktrackingSolver
from constraint.optimization import optimize


def test_min_max_repeat_and_model_preservation():
    """同一字符串排班模型多轮目标变化不累积规则或缩域。@return None。"""
    problem=Problem(BacktrackingSolver());problem.addVariables(['x','y'],(value for value in range(4)));problem.addConstraint('x < y')
    minimum=optimize(problem,lambda row:row['x']+row['y'])
    maximum=optimize(problem,lambda row:row['x']+row['y'],direction='max')
    assert minimum.score==1 and maximum.score==5 and minimum.complete and maximum.complete
    assert minimum.reason==maximum.reason=='optimal'
    assert not problem._constraints and list(problem._variables['x'])==list(range(4))


def test_budget_unsatisfiable_and_invalid_objective():
    """预算没有最优性证明，无解必须完整穷尽。@return None。"""
    problem=Problem(BacktrackingSolver());problem.addVariables(['a','b'],range(5))
    result=optimize(problem,lambda row:row['a'],max_solutions=2)
    assert result.examined==2 and not result.complete and result.reason=='budget'
    assert optimize(problem,lambda row:0,max_solutions=0).examined==0
    impossible=Problem(BacktrackingSolver());impossible.addVariable('a',[1]);impossible.addConstraint(lambda a:False,['a'])
    result=optimize(impossible,lambda row:0)
    assert result.complete and result.reason=='unsatisfiable' and result.solution is None
    with unittest.TestCase().assertRaises(ValueError):optimize(problem,lambda row:float('nan'))

