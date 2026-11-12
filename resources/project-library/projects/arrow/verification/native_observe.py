"""核真实日期移动、区间端点、月锚点及冻结时区下的业务边界。"""
from importlib.resources import files
from json import dumps
from os import environ
from pathlib import Path
from sys import argv
from zoneinfo import ZoneInfo

import arrow
from arrow import Arrow


def paris() -> ZoneInfo:
    """只读冻结离线tzdata中的巴黎规则，避免依赖宿主时区库。@return 独立时区对象。"""
    with files('tzdata').joinpath('zoneinfo/Europe/Paris').open('rb') as source:
        return ZoneInfo.from_file(source, key='Europe/Paris')


def main() -> None:
    """以固定日期验证真实候选，不读取当前时钟或连接外部日历。@return None。"""
    root = Path(environ['PROJECT_CANDIDATE_ROOT']).resolve()
    result = {'candidate_import': Path(arrow.__file__).resolve() == root / 'library/arrow/__init__.py'}
    task = argv[1]
    if task == 'AR-U01':
        original = Arrow(2026, 1, 31, 9)
        shifted = original.shift(months=1)
        errors = []
        for operation in [lambda: original.replace(month=2), lambda: original.shift(month=1)]:
            try:
                operation()
            except ValueError:
                errors.append('ValueError')
        result['relative_month_shift_clamps_but_absolute_replacement_validates'] = (
            original.date().isoformat() == '2026-01-31' and shifted.date().isoformat() == '2026-02-28'
            and errors == ['ValueError', 'ValueError'])
    elif task == 'AR-U02':
        original = Arrow(2026, 10, 22, 10, 15)
        start, last = original.span('day')
        inclusive_start, next_midnight = original.span('day', bounds='[]')
        result['span_bounds_choose_microsecond_end_or_next_midnight'] = (
            start.isoformat() == inclusive_start.isoformat() == '2026-10-22T00:00:00+00:00'
            and last.isoformat() == '2026-10-22T23:59:59.999999+00:00'
            and next_midnight.isoformat() == '2026-10-23T00:00:00+00:00')
    elif task == 'AR-C01':
        start = Arrow(2026, 1, 31, 9)
        anchored = [value.date().isoformat() for value in Arrow.range('month', start, limit=4)]
        iterative, current = [], start
        for _ in range(4):
            iterative.append(current.date().isoformat())
            current = current.shift(months=1)
        result['monthly_range_preserves_the_original_day_anchor'] = (
            anchored == ['2026-01-31', '2026-02-28', '2026-03-31', '2026-04-30']
            and iterative == ['2026-01-31', '2026-02-28', '2026-03-28', '2026-04-28'])
    elif task == 'AR-C02':
        original = Arrow(2026, 10, 22, 12)
        converted, relabeled = original.to('+02:00'), original.replace(tzinfo='+02:00')
        result['timezone_conversion_and_relabeling_have_different_instants'] = (
            converted.isoformat() == '2026-10-22T14:00:00+02:00'
            and relabeled.isoformat() == '2026-10-22T12:00:00+02:00'
            and converted.timestamp() == original.timestamp()
            and relabeled.timestamp() == original.timestamp() - 7200)
    elif task == 'AR-P01':
        zone = paris()
        boundaries = [Arrow(2026, month, day, 12, tzinfo=zone).span('day', bounds='[]')
            for month, day in [(3, 29), (10, 25)]]
        # 同时区datetime减法可能呈墙钟时长；分区物理跨度按真实UTC时间戳核对。
        hours = [(end.timestamp() - start.timestamp()) / 3600 for start, end in boundaries]
        result['civil_day_partition_durations_follow_the_pinned_timezone_rules'] = (
            hours == [23, 25] and all(end.date().day == start.date().day + 1 for start, end in boundaries))
    elif task == 'AR-D01':
        first = Arrow(2026, 10, 25, 2, 30, tzinfo=paris())
        second = first.replace(fold=1)
        result.update(first=first.isoformat(), second=second.isoformat(), ambiguous=first.ambiguous,
            first_fold=first.fold, second_fold=second.fold, utc_first=first.to('UTC').isoformat(),
            utc_second=second.to('UTC').isoformat(), difference_sec=second.timestamp() - first.timestamp())
    else:
        raise ValueError('未冻结的业务任务')
    print(dumps(result))


if __name__ == '__main__':
    main()
