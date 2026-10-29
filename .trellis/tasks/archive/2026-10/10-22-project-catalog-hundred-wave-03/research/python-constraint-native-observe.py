"""观察有限域模型、投影、启发式返回与普通排班建模。"""
from itertools import product
from json import dumps
from os import environ
from pathlib import Path
from sys import argv

import constraint
import constraint.problem
from constraint import AllDifferentConstraint, ExactSumConstraint, MinConflictsSolver, Problem


def main() -> None:
    """业务取实际候选Python实现；完整基线另构建五个Cython模块。@return None。"""
    root = Path(environ['PROJECT_CANDIDATE_ROOT']).resolve()
    result = {'candidate_import': Path(constraint.__file__).resolve() == root / 'library/constraint/__init__.py'
        and Path(constraint.problem.__file__).resolve() == root / 'library/constraint/problem.py'}
    task = argv[1]
    if task == 'PC-U01':
        problem = Problem()
        problem.addVariables(['tea', 'review'], [9, 10, 11])
        problem.addConstraint(AllDifferentConstraint(), ['tea', 'review'])
        problem.addConstraint(lambda tea, review: review > tea, ['tea', 'review'])
        actual = {(row['tea'], row['review']) for row in problem.getSolutions()}
        result['finite_schedule_solutions_are_sets_without_a_ranking_contract'] = (
            actual == {(9, 10), (9, 11), (10, 11)})
    elif task == 'PC-U02':
        problem = Problem()
        problem.addVariable('a', [1])
        problem.addVariable('b', [2])
        single = problem.getSolutionsOrderedList(['a'])
        ordered = problem.getSolutionsOrderedList(['b', 'a'])
        result['single_name_order_does_not_project_the_solution_in_this_revision'] = (
            len(single) == 1 and len(single[0]) == 2 and set(single[0]) == {1, 2}
            and ordered == [(2, 1)])
    elif task == 'PC-C01':
        bounded, exhaustive = Problem(MinConflictsSolver(steps=0)), Problem()
        bounded.addVariable('x', [1])
        exhaustive.addVariable('x', [1])
        result['heuristic_none_is_not_a_certificate_of_unsatisfiability'] = (
            bounded.getSolution() is None and exhaustive.getSolution() == {'x': 1})
    elif task == 'PC-C02':
        problem = Problem()
        failure = None
        try:
            problem.addVariables(['a', 'b'], (value for value in [1, 2]))
        except ValueError as error:
            failure = str(error)
        reusable = Problem()
        reusable.addVariables(['a', 'b'], [1, 2])
        result['multi_variable_domains_must_be_reusable_instead_of_a_shared_single_pass_generator'] = (
            failure == 'Domain is empty' and len(reusable.getSolutions()) == 4)
    elif task == 'PC-P01':
        problem = Problem()
        problem.addVariables(['a', 'b'], [9, 10, 11])
        problem.addConstraint(lambda a, b: a + 2 <= b or b + 1 <= a, ['a', 'b'])
        actual = {(row['a'], row['b']) for row in problem.getSolutions()}
        brute = {(a, b) for a, b in product([9, 10, 11], repeat=2) if a + 2 <= b or b + 1 <= a}
        result['duration_aware_half_open_nonoverlap_differs_from_all_different_start_times'] = (
            actual == brute == {(9, 11), (10, 9), (11, 9), (11, 10)}
            and (9, 10) not in actual and (9, 11) in actual)
    elif task == 'PC-D01':
        problem = Problem()
        problem.addVariables(['x', 'y'], [1, 2])
        problem.addConstraint(ExactSumConstraint(0, [1, -1]), ['x', 'y'])
        actual = sorted((row['x'], row['y']) for row in problem.getSolutions())
        brute = [(x, y) for x, y in product([1, 2], repeat=2) if x - y == 0]
        result.update(weighted_solutions=actual, brute_force_solutions=brute)
    else:
        raise ValueError('未冻结的业务任务')
    print(dumps(result))


if __name__ == '__main__':
    main()
