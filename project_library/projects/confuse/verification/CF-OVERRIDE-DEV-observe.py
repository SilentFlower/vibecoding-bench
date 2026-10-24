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
    from confuse import RootView,ConfigSource
    from confuse.scopes import temporary_override
    old=ConfigSource({'x':1});other=ConfigSource({'x':1});root=RootView([old])
    with temporary_override(root,{'x':2}) as scoped:
        root.sources.remove(old);root.add(other);root.sources.remove(scoped)
    business=len(root.sources)==1 and root.sources[0] is other

except Exception:
    business = False

print(json.dumps({'candidate_import': _candidate_import_bound, 'business': bool(business)}))
