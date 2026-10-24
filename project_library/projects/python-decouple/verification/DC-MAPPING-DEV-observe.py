"""在固定候选源码上运行独立业务矩阵，不调用模型或外部服务。"""
import json
import os
from pathlib import Path
root = Path(os.environ['PROJECT_CANDIDATE_ROOT']).resolve()

import decouple
business = False
try:
    parse = decouple.MappingCast(value_cast=int, delimiter=';')
    business = parse('a=0;b=-7') == {'a': 0, 'b': -7} and parse(None) == {}
    business &= decouple.MappingCast()('a=,b=#literal') == {'a': '', 'b': '#literal'}
    business &= decouple.MappingCast(format='json')('{"v": [1,{"n":null}]}') == {'v': [1, {'n': None}]}
    for value in ['{"x":1,"x":2}', 'true', 'null']:
        try:
            decouple.MappingCast(format='json')(value)
        except ValueError:
            pass
        else:
            business = False
    business &= decouple.MappingCast(format='json', duplicate='last')('{"x":1,"x":2}') == {'x': 2}
except (AttributeError, TypeError, ValueError):
    business = False

print(json.dumps({'candidate_import': Path(decouple.__file__).resolve().is_relative_to(root / 'library'), 'business': bool(business)}))
