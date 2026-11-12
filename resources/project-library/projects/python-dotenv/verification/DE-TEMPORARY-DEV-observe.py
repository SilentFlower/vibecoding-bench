"""在固定候选源码上运行独立业务矩阵，不调用模型或外部服务。"""
import json
import os
from pathlib import Path
root = Path(os.environ['PROJECT_CANDIDATE_ROOT']).resolve()

import dotenv
_candidate_source_root = root
business = False
try:
    from dotenv.environment import temporary_environment
    import os
    from unittest.mock import patch
    with patch.dict(os.environ, {'DOTENV_SCOPE_HIDDEN':'old'}):
        with temporary_environment({'DOTENV_SCOPE_HIDDEN':'new'}, override=True):
            os.environ['DOTENV_SCOPE_UNRELATED'] = 'keep'
        business = os.environ['DOTENV_SCOPE_HIDDEN']=='old' and os.environ['DOTENV_SCOPE_UNRELATED']=='keep'

except Exception:
    business = False

print(json.dumps({'candidate_import': Path(dotenv.__file__).resolve().is_relative_to(_candidate_source_root / 'library'), 'business': bool(business)}))
