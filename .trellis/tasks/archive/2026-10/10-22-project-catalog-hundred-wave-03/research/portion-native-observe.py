"""观察区间集合、覆盖映射、缺口与有限迭代边界。"""
from itertools import islice
from contextlib import ExitStack
from importlib.util import module_from_spec, spec_from_file_location
from json import dumps
from os import environ
from pathlib import Path
from sys import argv

def main() -> None:
    """所有时间为合成整数，不操作真实日程。@return None。"""
    root = Path(environ['PROJECT_CANDIDATE_ROOT']).resolve()
    result = {'candidate_import': Path(intervals.__file__).resolve() == root / 'library/portion/__init__.py'}
    task = argv[1]
    if task == 'PT-U01':
        separate = intervals.closedopen(9, 10) | intervals.openclosed(10, 11)
        merged = intervals.closedopen(9, 10) | intervals.closedopen(10, 11)
        result['interval_components_and_endpoint_membership_are_not_durations'] = (
            10 not in separate and len(separate) == 2
            and 10 in merged and len(merged) == 1 and merged == intervals.closedopen(9, 11)
            and len(intervals.closed(0, 100)) == 1)
    elif task == 'PT-U02':
        mapping = intervals.IntervalDict()
        mapping[intervals.closedopen(9, 12)] = 'open'
        mapping[intervals.closedopen(10, 11)] = 'meeting'
        result['overlapping_interval_assignment_replaces_values_on_the_overlap'] = (
            [mapping[value] for value in (9, 10, 11)] == ['open', 'meeting', 'open']
            and mapping.find('open') == intervals.closedopen(9, 10) | intervals.closedopen(11, 12)
            and len(mapping) == 2)
    elif task == 'PT-C01':
        mapping = intervals.IntervalDict({intervals.closedopen(9, 10): 'open'})
        subset = mapping[intervals.closedopen(9, 12)]
        filled = mapping.get(intervals.closedopen(9, 12), 'missing')
        result['range_get_fills_gaps_without_mutating_the_original_mapping'] = (
            subset.domain() == intervals.closedopen(9, 10)
            and filled[9] == 'open' and filled[11] == 'missing'
            and 11 not in mapping and mapping.domain() == intervals.closedopen(9, 10))
    elif task == 'PT-C02':
        zero = list(islice(intervals.iterate(intervals.closedopen(9, 12), step=0), 3))
        normal = list(intervals.iterate(intervals.closedopen(9, 12), step=1))
        result['iteration_step_and_direction_need_an_application_progress_contract'] = (
            zero == [9, 9, 9] and normal == [9, 10, 11]
            and list(intervals.iterate(intervals.closed(9, 11), step=-1, reverse=True)) == [11, 10, 9])
    elif task == 'PT-P01':
        day = intervals.closedopen(9, 17)
        busy = intervals.closedopen(9, 11) | intervals.closedopen(13, 14)
        free = day - busy
        result['free_schedule_is_the_declared_window_minus_busy_intervals'] = (
            free == intervals.closedopen(11, 13) | intervals.closedopen(14, 17)
            and not (free & busy) and free | (busy & day) == day
            and 11 in free and 13 not in free and 17 not in free)
    else:
        raise ValueError('未冻结的业务任务')
    print(dumps(result))


if __name__ == '__main__':
    # 原生业务使用同一个可信绑定入口，只补固定源码元数据，不另装库实现。
    specification = spec_from_file_location('_portion_private_control', Path(__file__).with_name('native_regression.py'))
    if specification is None or specification.loader is None:
        raise ValueError('缺少已冻结可信绑定入口')
    control = module_from_spec(specification)
    specification.loader.exec_module(control)
    with ExitStack() as cleanup:
        control._bind_source(Path(environ['PROJECT_CANDIDATE_ROOT']) / 'library', Path('.'), cleanup,
            distribution=control.SUITES['portion']['distribution'])
        import portion as intervals
        main()
