"""核惰性处理、假值、去重、分流及重试副作用。"""
from json import dumps
from operator import itemgetter
from os import environ
from pathlib import Path
from sys import argv

import funcy


def main() -> None:
    """以小型确定输入核真实候选，避免时间和外部服务依赖。@return None。"""
    root = Path(environ['PROJECT_CANDIDATE_ROOT']).resolve()
    result = {'candidate_import': Path(funcy.__file__).resolve() == root / 'library/funcy/__init__.py'}
    task = argv[1]
    if task == 'FU-U01':
        calls = []

        def convert(value):
            """记录真正执行的时点。@param value 输入。@return 两倍值。"""
            calls.append(value)
            return value * 2

        lazy = funcy.map(convert, [1, 2, 3])
        before = list(calls)
        first = next(lazy)
        after = list(calls)
        rest = list(lazy)
        eager_calls = len(calls)
        eager = funcy.lmap(convert, [4, 5])
        result['map_defers_work_and_is_consumed_while_lmap_eagerly_materializes'] = (
            before == [] and first == 2 and after == [1] and rest == [4, 6]
            and list(lazy) == [] and eager_calls == 3 and eager == [8, 10] and calls == [1, 2, 3, 4, 5])
    elif task == 'FU-U02':
        result['keep_discards_all_falsey_values_including_valid_zero_and_false'] = (
            list(funcy.keep([None, 0, False, '', 2, 'ok'])) == [2, 'ok']
            and list(funcy.filter(lambda value: value is not None, [None, 0, False, ''])) == [0, False, ''])
    elif task == 'FU-C01':
        rows = [{'id': 2, 'value': 'first'}, {'id': 1, 'value': 'x'}, {'id': 2, 'value': 'last'}]
        result['distinct_retains_the_first_record_per_explicit_hashable_key'] = (
            list(funcy.distinct(rows, key=itemgetter('id'))) == rows[:2] and len(rows) == 3)
    elif task == 'FU-C02':
        events = []

        def source():
            """记录共享输入被哪次消费推进。@return 有限输入。"""
            for value in range(4):
                events.append(value)
                yield value

        passed, failed = funcy.split(lambda value: value % 2 == 0, source())
        first, visited = list(passed), list(events)
        result['lazy_split_shares_input_and_buffers_the_unconsumed_branch'] = (
            first == [0, 2] and visited == [0, 1, 2, 3] and list(failed) == [1, 3])
    elif task == 'FU-P01':
        events = []

        @funcy.retry(3, errors=ValueError, timeout=0)
        def send():
            """用本地计数模拟提交后失败，不接触外部数据。@return 第三次结果。"""
            events.append('effect')
            if len(events) < 3:
                raise ValueError('transient response')
            return len(events)

        result['retry_repeats_prior_side_effects_and_counts_total_attempts'] = send() == 3 and events == ['effect'] * 3
    else:
        raise ValueError('未冻结的业务任务')
    print(dumps(result))


if __name__ == '__main__':
    main()
