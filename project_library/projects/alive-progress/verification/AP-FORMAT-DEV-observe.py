"""在固定候选源码上运行独立业务矩阵，不调用模型或外部服务。"""
import json
import os
from pathlib import Path
root = Path(os.environ['PROJECT_CANDIDATE_ROOT']).resolve()

import alive_progress
_candidate_source_root = root
_candidate_import_bound = Path(alive_progress.__file__).resolve().is_relative_to(_candidate_source_root / 'library')
business = False
try:
    from alive_progress.core.configuration import _format_input_factory,ERROR,config_handler
    validate=_format_input_factory('rate eta')
    business=validate('{rate:{eta!q}}') is ERROR and validate('{rate:{eta}}')=='{rate:{eta}}'
    rejected=False
    try:
        config_handler(stats='{rate:{unknown}}')
    except ValueError:
        rejected=True
    business=business and rejected

except Exception:
    business = False

print(json.dumps({'candidate_import': _candidate_import_bound, 'business': bool(business)}))
