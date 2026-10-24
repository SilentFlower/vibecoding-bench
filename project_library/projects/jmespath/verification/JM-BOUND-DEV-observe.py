"""在固定候选源码上运行独立业务矩阵，不调用模型或外部服务。"""
import json
import os
from pathlib import Path
root = Path(os.environ['PROJECT_CANDIDATE_ROOT']).resolve()

import jmespath
_candidate_source_root = root
_candidate_import_bound = Path(jmespath.__file__).resolve().is_relative_to(_candidate_source_root / 'library')
business = False
try:
    from jmespath.bound import BoundExpression
    from jmespath import Options,functions
    class Custom(functions.Functions):
        def __init__(self):
            self.calls=0
        @functions.signature({'types':['number']})
        def _func_double(self,value):
            self.calls+=1
            return value*2
    custom=Custom();options=Options(custom_functions=custom);query=BoundExpression('double(value)',options)
    options.custom_functions=None
    business=query.search({'value':3})==6 and query.search({'value':4})==8 and custom.calls==2

except Exception:
    business = False

print(json.dumps({'candidate_import': _candidate_import_bound, 'business': bool(business)}))
