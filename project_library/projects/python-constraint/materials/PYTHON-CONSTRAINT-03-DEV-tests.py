"""一次性域完整接入所有变量，每轮求解独立持有Domain状态。"""
import unittest
from constraint import Problem,Domain


def test_generator_and_tuple_identity_have_independent_domains():
    """生成器只物化一次，tuple身份不误走domain类型检查。@return None。"""
    problem=Problem();problem.addVariables(['a','b'],(value for value in [1,2]))
    assert len(problem.getSolutions())==4 and problem._variables['a'] is not problem._variables['b']
    another=Problem();another.addVariable(('slot',1),(value for value in [1,2]))
    assert len(another.getSolutions())==2


def test_failed_batch_and_query_preprocessing_leave_model_intact():
    """重复、空域和迭代异常不留下半批，预处理不永久删原域。@return None。"""
    problem=Problem();problem.addVariable('old',[1])
    for variables,domain in ((['new','old'],[1]),(['x','x'],[1]),(['x'],[])):
        with unittest.TestCase().assertRaises(ValueError):problem.addVariables(variables,domain)
        assert set(problem._variables)=={'old'}
    problem.addVariable('x',Domain([0,1,2]));problem.addConstraint(lambda x:x>0,['x'])
    assert len(problem.getSolutions())==2 and list(problem._variables['x'])==[0,1,2]

