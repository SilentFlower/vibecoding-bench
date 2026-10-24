"""在固定候选源码上运行独立业务矩阵，不调用模型或外部服务。"""
import json
import os
from pathlib import Path
root = Path(os.environ['PROJECT_CANDIDATE_ROOT']).resolve()

import box
business = False
try:
    config = box.ConfigBox(on='on', off='off', unknown='', integer='12', fraction=1.2, floating='2.5', rows=[1, 2])
    business = config.getboolean('on', strict=True) is True and config.bool('off', strict=True) is False
    business &= config.int('integer', strict=True) == 12 and config.getfloat('floating', strict=True) == 2.5
    business &= config.list('rows', mod=lambda value: value * 2, strict=True) == [2, 4]
    business &= config.getint('missing', default=None, strict=True) is None
    for function, key in [(config.bool, 'unknown'), (config.int, 'fraction')]:
        try:
            function(key, strict=True)
        except ValueError:
            pass
        else:
            business = False
except TypeError:
    business = False

print(json.dumps({'candidate_import': Path(box.__file__).resolve().is_relative_to(root / 'library'), 'business': bool(business)}))
