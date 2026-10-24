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
    from jmespath import functions
    class Mutating(functions.Functions):
        @functions.signature({'types':['array']})
        def _func_mutate(self,value):
            value.append('new')
            return value
    query=jmespath.compile('mutate(`[1]`)');options=jmespath.Options(custom_functions=Mutating())
    business=query.search({},options)==[1,'new'] and query.search({},options)==[1,'new']

except Exception:
    business = False

print(json.dumps({'candidate_import': _candidate_import_bound, 'business': bool(business)}))
