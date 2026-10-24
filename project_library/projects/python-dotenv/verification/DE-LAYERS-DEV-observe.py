"""在固定候选源码上运行独立业务矩阵，不调用模型或外部服务。"""
import json
import os
from pathlib import Path
root = Path(os.environ['PROJECT_CANDIDATE_ROOT']).resolve()

import dotenv
_candidate_source_root = root
business = False
try:
    from dotenv.layers import load_layers
    import os
    before = dict(os.environ)
    environment = {'SHARED':'outside'}
    result = load_layers([('first','SHARED=inside\nEMPTY\nA=${EMPTY:-fallback}\n'),('next','B=${SHARED}\nC=${MISSING:-yes}\n')], environment=environment, override=False)
    readonly = False
    try:
        result.origins['B'] = ('fake',0)
    except TypeError:
        readonly = True
    business = (dict(result.values)=={'SHARED':'inside','EMPTY':None,'A':'','B':'outside','C':'yes'}
        and result.origins['B']==('next',1) and environment=={'SHARED':'outside'} and dict(os.environ)==before and readonly)

except Exception:
    business = False

print(json.dumps({'candidate_import': Path(dotenv.__file__).resolve().is_relative_to(_candidate_source_root / 'library'), 'business': bool(business)}))
