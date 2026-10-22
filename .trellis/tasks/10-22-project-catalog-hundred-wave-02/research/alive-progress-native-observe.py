"""独立观察真实进度计数、迭代生命周期、显示和回调，不读取账号数据。"""
from io import StringIO
import json
import os
from pathlib import Path
import sys

import alive_progress
from alive_progress import alive_bar, alive_it, config_handler
from alive_progress.core.progress import __alive_bar


def options() -> dict:
    """为每次观察创建隔离的非终端显示。@return 当前独占选项。"""
    return {'file': StringIO(), 'force_tty': False, 'enrich_print': False, 'receipt': False}


class Finalizer:
    """记录假值可调用对象的真实调用，不更改库控制。"""

    def __init__(self) -> None:
        """初始化实际调用序列。@return None。"""
        self.calls = []

    def __bool__(self) -> bool:
        """模拟业务对象合法的假值状态。@return False。"""
        return False

    def __call__(self, bar) -> None:
        """收集真正传入的进度句柄。@param bar 真实句柄。@return None。"""
        self.calls.append(bar.current)


def observe(identifier: str) -> dict:
    """只运行当前任务的真实控制组。@param identifier 稳定任务码。@return 机械事实。"""
    if identifier == 'AP-U01':
        # 上游原生采样入口保留同一计数实现，避免用不稳定耗时反推processed。
        with __alive_bar(config_handler(**options()), total=5, _sampling=True) as state:
            state['bar_handle'](2)
            state['bar_handle'](1, skipped=True)
            count, processed = state['run'].count, state['run'].processed
        return {'skipped_counts_as_position_but_not_processed': count == 3 and processed == 2}
    if identifier == 'AP-U02':
        with alive_bar(10, manual=True, **options()) as bar:
            bar(.5)
            first = bar.current
            bar(.2)
            second = bar.current
            bar(-.1)
            lower = bar.current
            bar(1.2)
            above = bar.current
        with alive_bar(manual=True, **options()) as fraction:
            fraction(.2)
            percent = fraction.current
        return {'manual_updates_are_absolute_and_not_upper_bounded':
            (first, second, lower, above, percent) == (5, 2, 0, 12, .2)}
    if identifier == 'AP-U03':
        adapter = alive_it(['A', 'B'], **options())
        try:
            adapter.current
            before = False
        except UserWarning:
            before = True
        iterator = iter(adapter)
        first, count_first = next(iterator), adapter.current
        second, count_second = next(iterator), adapter.current
        try:
            next(iterator)
        except StopIteration:
            pass
        count_end, again = adapter.current, list(adapter)
        try:
            adapter()
            automatic = False
        except UserWarning:
            automatic = True
        with alive_bar(2, **options()) as bar:
            bar(2)
        bar(10)
        return {'iterator_counts_after_resumption_and_is_single_use':
            before and (first, second, count_first, count_second, count_end, again) == ('A', 'B', 0, 1, 2, [])
            and automatic and bar.current == 2}
    if identifier == 'AP-C01':
        shown, hidden, silent = StringIO(), StringIO(), StringIO()
        for stream, disable, receipt in [(shown, False, True), (hidden, True, True), (silent, False, False)]:
            with alive_bar(2, file=stream, force_tty=False, enrich_print=False,
                    disable=disable, receipt=receipt, title='Local shipment') as bar:
                bar(2)
            if bar.current != 2:
                return {'non_tty_receipt_is_distinct_from_disabled_display': False}
        return {'non_tty_receipt_is_distinct_from_disabled_display':
            'Local shipment' in shown.getvalue() and '2/2' in shown.getvalue()
            and hidden.getvalue() == silent.getvalue() == ''}
    if identifier == 'AP-P01':
        events = ['A', 'B', 'A', 'C', 'B']
        with alive_bar(3, **options()) as raw:
            for _ in events:
                raw()
        with alive_bar(3, **options()) as owned:
            seen = set()
            for item in events:
                if item not in seen:
                    seen.add(item)
                    owned()
        return {'bar_does_not_deduplicate_application_events': raw.current == 5 and owned.current == 3}
    if identifier == 'AP-M01':
        try:
            for items in ([1, 2], []):
                ending = Finalizer()
                actual = list(alive_it(items, finalize=ending, **options()))
                if actual != items or ending.calls != [len(items)]:
                    return {'falsey_finalizer_runs_once_with_compatibility_controls': False}
            normal = []
            list(alive_it([1], finalize=lambda bar: normal.append(bar.current), **options()))
            unchanged = list(alive_it([1], finalize=None, **options())) == [1]
            interrupted = Finalizer()
            iterator = iter(alive_it([1, 2], finalize=interrupted, **options()))
            next(iterator)
            iterator.close()
            return {'falsey_finalizer_runs_once_with_compatibility_controls':
                normal == [1] and unchanged and interrupted.calls == []}
        except Exception:
            return {'falsey_finalizer_runs_once_with_compatibility_controls': False}
    raise ValueError('未知进度任务：' + identifier)


def main() -> None:
    """输出严格事实JSON，不把原生观察称为模型完成。@return None。"""
    root = Path(os.environ['PROJECT_CANDIDATE_ROOT']).resolve()
    print(json.dumps({'candidate_import': Path(alive_progress.__file__).resolve() == root / 'library/alive_progress/__init__.py',
        **observe(sys.argv[1])}, ensure_ascii=False))


if __name__ == '__main__':
    main()
