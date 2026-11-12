"""核实际进度计数、输出政策和有界异步业务。"""
import asyncio
from io import StringIO
import json
import os
from pathlib import Path
import sys

import tqdm
from tqdm import tqdm as Progress
from tqdm.asyncio import tqdm_asyncio


async def gather_controls() -> bool:
    """以事件控制完成顺序，核输入顺序和显式异常值。@return 是否符合。"""
    gate, events = asyncio.Event(), []

    async def first():
        """等待第二项后返回第一项。@return A。"""
        await gate.wait()
        events.append('A')
        return 'A'

    async def second():
        """先完成并放行另一项。@return B。"""
        events.append('B')
        gate.set()
        return 'B'

    async def invalid():
        """制造合成业务异常。@return 不返回。"""
        raise ValueError('SYNTHETIC')

    async def valid():
        """提供异常收集的独立正常对照。@return OK。"""
        return 'OK'

    ordered = await tqdm_asyncio.gather(first(), second(), file=StringIO(), mininterval=0)
    mixed = await tqdm_asyncio.gather(invalid(), valid(), return_exceptions=True, file=StringIO())
    return ordered == ['A', 'B'] and events == ['B', 'A'] and isinstance(mixed[0], ValueError) and mixed[1] == 'OK'


def main() -> None:
    """只输出独立布尔事实，不把显示完成计为业务成功。@return None。"""
    root = Path(os.environ['PROJECT_CANDIDATE_ROOT']).resolve()
    result = {'candidate_import': Path(tqdm.__file__).resolve() == root / 'library/tqdm/__init__.py'}
    task = sys.argv[1]
    if task == 'TQ-U01':
        bar = Progress(['A', 'B'], file=StringIO(), mininterval=0, miniters=1)
        iterator = iter(bar)
        first = next(iterator), bar.n
        second = next(iterator), bar.n
        exhausted = False
        try:
            next(iterator)
        except StopIteration:
            exhausted = True
        completed = bar.n
        bar.update(4)
        quiet = Progress(['A', 'B'], file=StringIO(), disable=True)
        values = list(quiet)
        result['iteration_updates_after_yield_and_disabled_counter_stays_initial'] = (
            first == ('A', 0) and second == ('B', 1) and exhausted and completed == bar.n == 2
            and values == ['A', 'B'] and quiet.n == 0)
    elif task == 'TQ-U02':
        naive = Progress(total=10, file=StringIO())
        naive.update(5)
        naive.update(8)
        proper = Progress(total=10, file=StringIO())
        proper.update(5)
        proper.update(8 - 5)
        over = Progress(total=10, file=StringIO())
        over.update(12)
        result['updates_are_deltas_and_total_does_not_cap_the_counter'] = (
            naive.n == 13 and proper.n == 8 and over.n == 12 and over.total == 10)
        for bar in (naive, proper, over):
            bar.close()
    elif task == 'TQ-C01':
        visible, automatic, explicit = StringIO(), StringIO(), StringIO()
        normal = Progress([1, 2], file=visible, mininterval=0)
        auto = Progress([1, 2], file=automatic, disable=None)
        quiet = Progress([1, 2], file=explicit, disable=True)
        for bar in (normal, auto, quiet):
            list(bar)
        result['non_tty_output_and_disable_counter_policy_are_explicit'] = (
            bool(visible.getvalue()) and normal.n == 2 and automatic.getvalue() == explicit.getvalue() == ''
            and auto.n == quiet.n == 0)
    elif task == 'TQ-C02':
        diagnostic, structured = StringIO(), StringIO()
        with Progress(total=1, file=diagnostic, mininterval=0) as bar:
            Progress.write('LOCAL_LOG', file=diagnostic)
            bar.update(1)
            structured.write('{"accepted":true}\n')
        disabled = StringIO()
        with Progress(total=1, file=disabled, disable=True):
            Progress.write('EXPLICIT_LOG', file=disabled)
        result['explicit_write_coordinates_display_but_is_not_disabled_with_the_bar'] = (
            'LOCAL_LOG\n' in diagnostic.getvalue() and structured.getvalue() == '{"accepted":true}\n'
            and disabled.getvalue() == 'EXPLICIT_LOG\n')
    elif task == 'TQ-U03':
        result['gather_restores_input_order_and_explicitly_returns_exception_values'] = asyncio.run(gather_controls())
    elif task == 'TQ-P01':
        accepted = 0
        bar = Progress([True, False], file=StringIO(), mininterval=0)
        for business_result in bar:
            accepted += int(business_result)
        result['traversal_completion_is_not_business_acceptance'] = bar.n == 2 and accepted == 1
    else:
        raise ValueError('未冻结的业务任务')
    print(json.dumps(result))


if __name__ == '__main__':
    main()
