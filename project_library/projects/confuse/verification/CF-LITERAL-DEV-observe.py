"""在固定候选源码上运行独立业务矩阵，不调用模型或外部服务。"""
import json
import os
from pathlib import Path
root = Path(os.environ['PROJECT_CANDIDATE_ROOT']).resolve()

import confuse
_candidate_source_root = root
_candidate_import_bound = Path(confuse.__file__).resolve().is_relative_to(_candidate_source_root / 'library')
business = False
try:
    from confuse import RootView,ConfigSource,ConfigValueError
    from confuse.literal import Literal
    view=RootView([ConfigSource({'v':{True:('x',)}})])
    rejected=False
    try:
        view['v'].get(Literal({1:('x',)}))
    except ConfigValueError as error:
        rejected='v' in str(error)
    business=rejected and view['v'].get(Literal({True:('x',)}))=={True:('x',)}

except Exception:
    business = False

print(json.dumps({'candidate_import': _candidate_import_bound, 'business': bool(business)}))
