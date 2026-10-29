"""核月末日历、模糊日期、时间窗口及冻结时区数据的现有能力。"""
from datetime import datetime, timedelta
from importlib.resources import files
import json
import os
from pathlib import Path
import sys

# 业务观察与完整原生集合均使用离线tzdata，避免读取宿主或镜像旧版时区库。
os.environ['PYTHONTZPATH'] = str(files('tzdata').joinpath('zoneinfo'))

import dateutil
from dateutil.parser import parse
from dateutil.relativedelta import relativedelta
from dateutil.rrule import DAILY, MONTHLY, rrule
from dateutil.tz import datetime_ambiguous, datetime_exists, gettz, resolve_imaginary


def main() -> None:
    """只计算本地合成日历，不连接任何在线日历。@return None。"""
    root = Path(os.environ['PROJECT_CANDIDATE_ROOT']).resolve()
    result = {'candidate_import': Path(dateutil.__file__).resolve() == root / 'library/src/dateutil/__init__.py'}
    task = sys.argv[1]
    if task == 'DT-U01':
        start = datetime(2026, 1, 31)
        dates = list(rrule(MONTHLY, count=3, dtstart=start))
        first = start + relativedelta(months=1)
        result['monthly_recurrence_skips_invalid_dates_while_relative_month_arithmetic_clamps'] = (
            dates == [datetime(2026, 1, 31), datetime(2026, 3, 31), datetime(2026, 5, 31)]
            and first == datetime(2026, 2, 28) and first + relativedelta(months=1) == datetime(2026, 3, 28)
            and start + relativedelta(months=2) == datetime(2026, 3, 31))
    elif task == 'DT-U02':
        result['ambiguous_numeric_dates_require_an_explicit_source_convention'] = (
            parse('01/05/2026', dayfirst=False) == datetime(2026, 1, 5)
            and parse('01/05/2026', dayfirst=True) == datetime(2026, 5, 1))
    elif task == 'DT-C01':
        start = datetime(2026, 1, 1)
        rule = rrule(DAILY, count=5, dtstart=start)
        end = datetime(2026, 1, 5)
        result['between_endpoint_inclusion_is_explicit_and_count_is_not_an_output_limit'] = (
            rule.between(start, end, count=1) == [datetime(2026, 1, day) for day in (2, 3, 4)]
            and rule.between(start, end, inc=True, count=1) == [datetime(2026, 1, day) for day in range(1, 6)])
    elif task == 'DT-C02':
        zone = gettz('America/New_York')
        if zone is None:
            raise ValueError('冻结时区数据缺少目标区域')
        gap = datetime(2017, 3, 12, 2, 30, tzinfo=zone)
        resolved = resolve_imaginary(gap)
        repeated = datetime(2017, 11, 5, 1, 30, tzinfo=zone)
        result['existing_gap_and_ambiguity_helpers_support_explicit_appointment_policy'] = (
            not datetime_exists(gap) and resolved.hour == 3 and resolved.minute == 30
            and resolved.utcoffset() == timedelta(hours=-4) and datetime_exists(resolved)
            and datetime_ambiguous(repeated)
            and repeated.replace(fold=0).utcoffset() != repeated.replace(fold=1).utcoffset())
    elif task == 'DT-P01':
        rule = rrule(DAILY, dtstart=datetime(2026, 1, 1))
        stream = rule.xafter(datetime(2026, 1, 2), count=2, inc=True)
        result['existing_xafter_bounds_next_occurrences_without_materializing_the_full_rule'] = (
            iter(stream) is stream and list(stream) == [datetime(2026, 1, 2), datetime(2026, 1, 3)])
    else:
        raise ValueError('未冻结的业务任务')
    print(json.dumps(result))


if __name__ == '__main__':
    main()
