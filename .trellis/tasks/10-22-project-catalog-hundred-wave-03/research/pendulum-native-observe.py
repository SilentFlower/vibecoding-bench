"""核月份、时区和精确解析类型；业务路径显式使用实际Python候选。"""
from json import dumps
from os import environ
from pathlib import Path
from sys import argv

environ['PENDULUM_EXTENSIONS'] = '0'
import pendulum
from pendulum import helpers
from pendulum.tz.exceptions import NonExistingTime


def main() -> None:
    """从本地固定时间控制核业务事实，完整Rust及Python集合另存。@return None。"""
    root = Path(environ['PROJECT_CANDIDATE_ROOT']).resolve()
    result = {'candidate_import': Path(pendulum.__file__).resolve() == root / 'library/src/pendulum/__init__.py'
        and helpers.with_extensions is False}
    task = argv[1]
    if task == 'PN-U01':
        start = pendulum.datetime(2025, 1, 31, tz='UTC')
        first = start.add(months=1)
        result['month_clipping_makes_repeated_addition_differ_from_a_single_combined_addition'] = (
            first.to_date_string() == '2025-02-28'
            and first.add(months=1).to_date_string() == '2025-03-28'
            and start.add(months=2).to_date_string() == '2025-03-31'
            and start.to_date_string() == '2025-01-31')
    elif task == 'PN-U02':
        start = pendulum.datetime(2025, 1, 31, tz='UTC')
        duration = pendulum.duration(months=1)
        calendar_end = start.add(months=duration.months)
        seconds_end = start.add(seconds=duration.total_seconds())
        result['calendar_months_and_approximate_duration_seconds_are_not_interchangeable'] = (
            duration.total_seconds() == 30 * 86400
            and calendar_end.to_date_string() == '2025-02-28'
            and (calendar_end - start).total_seconds() == 28 * 86400
            and seconds_end.to_date_string() == '2025-03-02')
    elif task == 'PN-C01':
        start = pendulum.datetime(2026, 1, 1, 12, tz='UTC')
        converted = start.in_timezone('America/New_York')
        relabeled = start.set(tz='America/New_York')
        result['timezone_conversion_preserves_the_instant_while_set_reinterprets_wall_fields'] = (
            converted.hour == 7 and converted.int_timestamp == start.int_timestamp
            and relabeled.hour == 12 and relabeled.int_timestamp - start.int_timestamp == 5 * 3600)
    elif task == 'PN-C02':
        first = pendulum.datetime(2026, 10, 25, 2, 30, tz='Europe/Paris', fold=0)
        second = pendulum.datetime(2026, 10, 25, 2, 30, tz='Europe/Paris', fold=1)
        rejected = False
        try:
            pendulum.datetime(2026, 3, 29, 2, 30, tz='Europe/Paris', raise_on_unknown_times=True)
        except NonExistingTime:
            rejected = True
        result['ambiguous_folds_are_distinct_instants_and_nonexistent_times_can_be_rejected'] = (
            second.int_timestamp - first.int_timestamp == 3600
            and first.hour == second.hour == 2 and rejected)
    elif task == 'PN-P01':
        ordinary = pendulum.parse('2026-10-22')
        exact_date = pendulum.parse('2026-10-22', exact=True)
        exact_time = pendulum.parse('12:30:00', exact=True)
        result['exact_parsing_preserves_date_and_time_types_instead_of_inventing_an_instant'] = (
            type(ordinary) is pendulum.DateTime and ordinary.hour == 0 and ordinary.timezone_name == 'UTC'
            and type(exact_date) is pendulum.Date and type(exact_time) is pendulum.Time
            and exact_date.to_date_string() == '2026-10-22' and exact_time.hour == 12)
    else:
        raise ValueError('未冻结的业务任务')
    print(dumps(result))


if __name__ == '__main__':
    main()
