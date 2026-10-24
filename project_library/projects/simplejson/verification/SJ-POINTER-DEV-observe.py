"""在固定候选源码上运行独立业务矩阵，不调用模型或外部服务。"""
import json
import os
from pathlib import Path
root = Path(os.environ['PROJECT_CANDIDATE_ROOT']).resolve()

import simplejson
_candidate_source_root = root
_candidate_import_bound = Path(simplejson.__file__).resolve().is_relative_to(_candidate_source_root / 'library')
business = False
try:
    from simplejson.pointer import tokens,resolve,index
    value={'~1':{'a/b':['x','y']}};failed=False
    try:
        resolve({'x':None},'/x/key')
    except TypeError:
        failed=True
    business=failed and resolve(value,'/~01/a~1b/1')=='y' and index('2',2,append=True)==2

except Exception:
    business = False

print(json.dumps({'candidate_import': _candidate_import_bound, 'business': bool(business)}))
