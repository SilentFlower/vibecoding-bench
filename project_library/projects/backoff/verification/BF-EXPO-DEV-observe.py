"""在固定候选源码上运行独立业务矩阵，不调用模型或外部服务。"""
import json
import os
from pathlib import Path
root = Path(os.environ['PROJECT_CANDIDATE_ROOT']).resolve()

import backoff
from itertools import islice
business = True
try:
    for base, factor, cap in [(1e250, 1e-250, 7), (1e180, 1e-280, 1e200)]:
        values = backoff.expo(base=base, factor=factor, max_value=cap)
        business &= next(values) is None
        observed = list(islice(values, 6))
        business &= observed[-1] == cap and all(0 <= v <= cap for v in observed)
        if factor == 1e-280:
            business &= 1e79 < observed[2] < 1e81
    ordinary = backoff.expo(base=3, factor=5, max_value=500)
    next(ordinary)
    business &= list(islice(ordinary, 6)) == [5, 15, 45, 135, 405, 500]
    unbounded = backoff.expo(base=1e308, factor=1e-308)
    next(unbounded); next(unbounded); next(unbounded)
    try:
        next(unbounded)
    except OverflowError:
        pass
    else:
        business = False
except OverflowError:
    business = False

print(json.dumps({'candidate_import': Path(backoff.__file__).resolve().is_relative_to(root / 'library'), 'business': bool(business)}))
