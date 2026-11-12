"""在固定候选源码上运行独立业务矩阵，不调用模型或外部服务。"""
import json
import os
from pathlib import Path
root = Path(os.environ['PROJECT_CANDIDATE_ROOT']).resolve()

import cachetools
_candidate_source_root = root
business = False
try:
    from cachetools.keys import signature_key
    def first(a,/,b=3,*values,c=4,**options):
        raise AssertionError('键生成不得执行业务')
    def second(a,/,b=3,*values,c=4,**options):
        pass
    key=signature_key(first,typed=True)
    before={'z':1,'x':2}
    business=(key(1,b=3,c=4,**before)==key(1,3,c=4,x=2,z=1) and before=={'z':1,'x':2}
        and key(1,3,True)!=key(1,3,1) and key(1,z=True)!=key(1,z=1)
        and signature_key(first,namespace='shared')(1)==signature_key(second,namespace='shared')(1))

except Exception:
    business = False

print(json.dumps({'candidate_import': Path(cachetools.__file__).resolve().is_relative_to(_candidate_source_root / 'library'), 'business': bool(business)}))
