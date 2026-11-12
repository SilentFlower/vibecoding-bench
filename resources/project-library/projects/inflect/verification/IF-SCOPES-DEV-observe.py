"""在固定候选源码上运行独立业务矩阵，不调用模型或外部服务。"""
import json
import os
from pathlib import Path
root = Path(os.environ['PROJECT_CANDIDATE_ROOT']).resolve()

import inflect
_candidate_source_root = root
_candidate_import_bound = Path(inflect.__file__).resolve().is_relative_to(_candidate_source_root / 'library')
business = False
try:
    from inflect import engine
    from inflect.scopes import clone,temporary_options
    class Custom(engine):
        pass
    target=Custom();target.num(2);target.gender('feminine');target.defnoun('URL','URLs',case='preserve')
    copy=clone(target)
    with temporary_options(target,gender='masculine',count=1):
        target.defnoun('URL','URLS',case='preserve')
    business=type(copy) is Custom and copy.persistent_count==2 and target.thegender=='feminine' and target.plural_noun('URL')=='URLs'

except Exception:
    business = False

print(json.dumps({'candidate_import': _candidate_import_bound, 'business': bool(business)}))
