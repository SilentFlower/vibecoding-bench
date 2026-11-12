"""独立安全迭代矩阵，使用真实区间与受控回调计数，不读取时钟。"""
import json
import os
from contextlib import ExitStack
from datetime import date, timedelta
from importlib.util import module_from_spec, spec_from_file_location
from itertools import islice
from pathlib import Path


def observations(P):
    """核对前进、反向、开放端点、无界前缀与不额外求值。@param P 实际候选模块。@return 业务事实。"""
    facts = {'strict_progress': True, 'global_output_limit': True, 'zero_has_no_callbacks': True,
        'invalid_limits': True, 'finite_infinite_prefix': True, 'date_and_base': True,
        'legacy_behavior': True, 'callback_exception': True}
    for interval, step, reverse in ((P.closed(3, 7), 0, False), (P.open(3, 7), lambda x: x, False),
        (P.closed(3, 7), -2, False), (P.open(3, 7), lambda x: x + 1, True)):
        try:
            list(P.iterate(interval, step, checked=True, reverse=reverse, max_items=8))
            facts['strict_progress'] = False
        except ValueError:
            pass
        except TypeError:
            facts['strict_progress'] = False
    try:
        events = P.closed(2, 4) | P.closed(20, 22)
        facts['global_output_limit'] = list(P.iterate(events, 1, checked=True, max_items=5)) == [2, 3, 4, 20, 21]
        facts['global_output_limit'] &= list(P.iterate(events, -1, reverse=True, checked=True, max_items=5)) == [22, 21, 20, 4, 3]
        calls = []
        facts['zero_has_no_callbacks'] = list(P.iterate(P.closed(0, 9), lambda x: calls.append(x),
            base=lambda x: calls.append(x), checked=True, max_items=0)) == [] and not calls
        for limit in (-7, False, 2.5, '3'):
            try:
                list(P.iterate(events, 1, max_items=limit))
                facts['invalid_limits'] = False
            except (ValueError, TypeError):
                pass
        steps = []
        def advance(value):
            """记录步进调用。@param value 当前值。@return 下一值。"""
            steps.append(value)
            return value + 2
        facts['finite_infinite_prefix'] = list(P.iterate(P.closedopen(0, P.inf), advance, checked=True, max_items=3)) == [0, 2, 4] and steps == [0, 2]
        first = date(2026, 3, 1)
        facts['date_and_base'] = list(P.iterate(P.closed(first, first + timedelta(days=4)),
            lambda value: value + timedelta(days=2), checked=True)) == [first, first + timedelta(days=2), first + timedelta(days=4)]
        facts['date_and_base'] &= list(P.iterate(P.open(1, 7), 2, base=lambda value: value + 1, checked=True)) == [2, 4, 6]
        facts['legacy_behavior'] = list(islice(P.iterate(P.closed(2, 4), 0), 3)) == [2, 2, 2]
        facts['legacy_behavior'] &= list(P.iterate(P.empty(), 1, checked=True)) == []
        def fail(_):
            """模拟回调业务异常。@param _ 当前值。@return 不返回。"""
            raise LookupError('private callback')
        try:
            list(P.iterate(P.closed(0, 3), fail, checked=True))
            facts['callback_exception'] = False
        except LookupError:
            pass
    except TypeError:
        for key in ('global_output_limit', 'zero_has_no_callbacks', 'finite_infinite_prefix', 'date_and_base', 'callback_exception'):
            facts[key] = False
    return facts


def main():
    """沿用固定原生绑定入口补元数据，不安装另一份库实现。@return None。"""
    root = Path(os.environ['PROJECT_CANDIDATE_ROOT']).resolve()
    specification = spec_from_file_location('_portion_development_control', Path(__file__).with_name('native_regression.py'))
    control = module_from_spec(specification)
    specification.loader.exec_module(control)
    with ExitStack() as cleanup:
        control._bind_source(root / 'library', Path('.'), cleanup, distribution=control.SUITES['portion']['distribution'])
        import portion as P
        print(json.dumps({'candidate_import': Path(P.__file__).resolve().is_relative_to(root / 'library'), **observations(P)}))


if __name__ == '__main__':
    main()
