"""在固定候选源码上运行独立业务矩阵，不调用模型或外部服务。"""
import json
import os
from pathlib import Path
root = Path(os.environ['PROJECT_CANDIDATE_ROOT']).resolve()

import tinydb
_candidate_source_root = root
business = False
try:
    from tinydb import Query
    state={'key':'left'}
    condition=Query().map(lambda doc:doc[state['key']]).at_path(('value',))==2
    first=condition({'left':{'value':2},'right':{'value':3}})
    state['key']='right'
    business=(first and not condition({'left':{'value':2},'right':{'value':3}})
        and not condition.is_cacheable() and not (Query().at_path(('missing','child'))==1)({})
        and (Query().at_path(('x',))==2)==(Query().x==2))

except Exception:
    business = False

print(json.dumps({'candidate_import': Path(tinydb.__file__).resolve().is_relative_to(_candidate_source_root / 'library'), 'business': bool(business)}))
