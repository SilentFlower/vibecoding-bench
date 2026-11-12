"""在固定候选源码上运行独立业务矩阵，不调用模型或外部服务。"""
import json
import os
from pathlib import Path
root = Path(os.environ['PROJECT_CANDIDATE_ROOT']).resolve()

import agate
from decimal import Decimal
business = False
try:
    data = agate.Table([(-2, 1), (4, 1), (10, 2), (None, 80)], ['v', 'w'], [agate.Number(), agate.Number()])
    grouped = agate.Table([('a', 2, 1), ('a', 8, 2), ('b', 9, 1)], ['g', 'v', 'w'],
        [agate.Text(), agate.Number(), agate.Number()]).group_by('g').aggregate([('weighted', agate.WeightedMean('v', 'w'))])
    rejected = 0
    for rows in ([(None, -3)], [(2, Decimal('Infinity'))]):
        try:
            agate.Table(rows, ['v', 'w'], [agate.Number(), agate.Number()]).aggregate(agate.WeightedMean('v', 'w'))
        except (ValueError, ArithmeticError):
            rejected += 1
    try:
        agate.Table([('x', 1)], ['v', 'w'], [agate.Text(), agate.Number()]).aggregate(agate.WeightedMean('v', 'w'))
    except agate.DataTypeError:
        rejected += 1
    business = (data.aggregate(agate.WeightedMean('v', 'w')) == Decimal('5.5')
        and data.aggregate(agate.WeightedVariance('v', 'w')) == Decimal('24.75')
        and tuple(grouped.columns['weighted'].values()) == (Decimal(6), Decimal(9))
        and rejected == 3 and data.column_names == ('v', 'w'))
except Exception:
    business = False

print(json.dumps({'candidate_import': Path(agate.__file__).resolve().is_relative_to(root / 'library'), 'business': bool(business)}))
