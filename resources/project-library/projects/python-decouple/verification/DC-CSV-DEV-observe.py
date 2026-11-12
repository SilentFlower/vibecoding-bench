"""在固定候选源码上运行独立业务矩阵，不调用模型或外部服务。"""
import json
import os
from pathlib import Path
root = Path(os.environ['PROJECT_CANDIDATE_ROOT']).resolve()

import decouple
business = False
try:
    calls = []
    parsed = decouple.Csv(cast=lambda x: calls.append(x) or x, post_process=tuple, mode='csv')('left,,"hash#tag",right,')
    business = parsed == ('left', '', 'hash#tag', 'right', '') and len(calls) == 5
    business &= decouple.Csv(mode='csv', delimiter=';')(r'\w+;"a;b";') == [r'\w+', 'a;b', '']
    business &= decouple.Csv(mode='csv', strip='')('" a "') == [' a ']
    for value in ['"bad', 'a,b\nc,d']:
        try:
            decouple.Csv(mode='csv')(value)
        except ValueError:
            pass
        else:
            business = False
    business &= decouple.Csv()('a,,b#ignored') == ['a', 'b']
except (TypeError, ValueError):
    business = False

print(json.dumps({'candidate_import': Path(decouple.__file__).resolve().is_relative_to(root / 'library'), 'business': bool(business)}))
