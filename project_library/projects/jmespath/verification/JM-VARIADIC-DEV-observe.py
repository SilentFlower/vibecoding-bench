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
    from jmespath.exceptions import JMESPathTypeError,VariadictArityError
    function=functions.Functions();rejected=False
    try:
        function.call_function('merge',[{}, {}, [], {}])
    except JMESPathTypeError as error:
        rejected=error.function_name=='merge'
    business=rejected and function.call_function('merge',[{'a':1},{'b':2}])=={'a':1,'b':2}

except Exception:
    business = False

print(json.dumps({'candidate_import': _candidate_import_bound, 'business': bool(business)}))
