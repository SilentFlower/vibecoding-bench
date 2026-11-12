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
    from jmespath.streaming import iter_search
    from jmespath import Options
    from collections import OrderedDict
    documents=iter([{'a':1},{'a':2}]);options=Options(dict_cls=OrderedDict)
    results=iter_search('{value:a}',documents,options=options)
    first=next(results);options.dict_cls=dict;second=next(results)
    business=type(first) is OrderedDict and type(second) is OrderedDict and list(first.items())==[('value',1)] and list(second.items())==[('value',2)]

except Exception:
    business = False

print(json.dumps({'candidate_import': _candidate_import_bound, 'business': bool(business)}))
