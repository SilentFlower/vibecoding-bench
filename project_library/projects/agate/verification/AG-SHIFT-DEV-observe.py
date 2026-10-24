"""在固定候选源码上运行独立业务矩阵，不调用模型或外部服务。"""
import json
import os
from pathlib import Path
root = Path(os.environ['PROJECT_CANDIDATE_ROOT']).resolve()

import agate
from decimal import Decimal
business = False
try:
    source = agate.Table([('a', 'x', 3), ('b', 'x', 9), ('a', 'y', 5), ('a', 'x', None), ('a', 'x', 7)],
        ['customer', 'kind', 'amount'], [agate.Text(), agate.Text(), agate.Number()])
    result = source.compute([('prior', agate.Lag('amount', partition_by=['customer', 'kind'])),
        ('after', agate.Lead('amount', 2, default=0, partition_by=['customer', 'kind']))])
    empty = agate.Table([], ['v'], [agate.Number()]).compute([('x', agate.Lag('v'))])
    rejected = False
    try:
        agate.Lead('amount', partition_by=['customer', 'customer'])
    except ValueError:
        rejected = True
    business = (result.columns['prior'].values() == (None, None, None, Decimal(3), None)
        and result.columns['after'].values() == (Decimal(7), Decimal(0), Decimal(0), Decimal(0), Decimal(0))
        and len(empty.rows) == 0 and rejected and source.column_names == ('customer', 'kind', 'amount'))
except Exception:
    business = False

print(json.dumps({'candidate_import': Path(agate.__file__).resolve().is_relative_to(root / 'library'), 'business': bool(business)}))
