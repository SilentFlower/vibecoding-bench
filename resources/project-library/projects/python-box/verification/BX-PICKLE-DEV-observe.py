"""在固定候选源码上运行独立业务矩阵，不调用模型或外部服务。"""
import json
import os
from pathlib import Path
root = Path(os.environ['PROJECT_CANDIDATE_ROOT']).resolve()

import box
import pickle
class PrivateConfig(box.Box):
    """私有业务子类。"""
business = True
for frozen in (False, True):
    original = PrivateConfig({'deep': {'child': {'v': 11}}, 'rows': [{'v': 12}]}, frozen_box=frozen,
        default_box=True, conversion_box=False)
    for protocol in (2, 4, pickle.HIGHEST_PROTOCOL):
        result = pickle.loads(pickle.dumps(original, protocol=protocol))
        business &= type(result) is PrivateConfig and type(result.deep.child) is PrivateConfig
        business &= type(result.rows[0]) is PrivateConfig and result == original
        business &= result._box_config['frozen_box'] is frozen and result._box_config['default_box'] is True
        business &= result._box_config['conversion_box'] is False
        business &= '__unpickling' not in result._box_config
        if frozen:
            try:
                result['new'] = 1
            except box.BoxError:
                pass
            else:
                business = False
original = PrivateConfig({'value': {'x': 1}})
dict.__setitem__(original, 'alias', original.value)
restored = pickle.loads(pickle.dumps(original))
business &= restored.value is restored.alias

print(json.dumps({'candidate_import': Path(box.__file__).resolve().is_relative_to(root / 'library'), 'business': bool(business)}))
