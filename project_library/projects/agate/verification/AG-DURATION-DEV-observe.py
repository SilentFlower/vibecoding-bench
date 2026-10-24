"""在固定候选源码上运行独立业务矩阵，不调用模型或外部服务。"""
import json
import os
from pathlib import Path
root = Path(os.environ['PROJECT_CANDIDATE_ROOT']).resolve()

import agate
from datetime import timedelta
from decimal import Decimal
import warnings
business = False
try:
    def durations(values):
        return agate.Table([(v,) for v in values], ['latency'], [agate.TimeDelta()])
    low, high = timedelta.min, timedelta.max
    total = ((low.days + high.days) * 86400 + low.seconds + high.seconds) * 1000000 + low.microseconds + high.microseconds
    quotient, remainder = divmod(total, 2)
    midpoint = timedelta(microseconds=quotient + (quotient % 2 if remainder else 0))
    mixed = durations([low, high])
    result = mixed.aggregate(agate.Percentiles('latency'))
    grouped = agate.Table([('a', timedelta(seconds=6)), ('a', timedelta(seconds=14)), ('b', timedelta(seconds=-4))],
        ['team', 'latency'], [agate.Text(), agate.TimeDelta()]).group_by('team').aggregate([('median', agate.Median('latency'))])
    with warnings.catch_warnings():
        warnings.simplefilter('ignore')
        empty = list(durations([None, None]).aggregate(agate.Percentiles('latency')))
    business = (result[0] == low and result[50] == midpoint and result[100] == high
        and len(result) == 101 and empty == [None] * 101
        and isinstance(grouped.columns['median'].data_type, agate.TimeDelta)
        and tuple(grouped.columns['median'].values()) == (timedelta(seconds=10), timedelta(seconds=-4))
        and durations([timedelta(microseconds=-2), timedelta(microseconds=-1)]).aggregate(agate.Median('latency')) == timedelta(microseconds=-2))
except Exception:
    business = False

print(json.dumps({'candidate_import': Path(agate.__file__).resolve().is_relative_to(root / 'library'), 'business': bool(business)}))
