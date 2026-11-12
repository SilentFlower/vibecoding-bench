"""在固定候选源码上运行独立业务矩阵，不调用模型或外部服务。"""
import json
import os
from pathlib import Path
root = Path(os.environ['PROJECT_CANDIDATE_ROOT']).resolve()

import marshmallow
_candidate_source_root = root
_candidate_import_bound = Path(marshmallow.__file__).resolve().is_relative_to(_candidate_source_root / 'library')
business = False
try:
    from marshmallow import fields,ValidationError
    from marshmallow.unique import UniqueList
    field=UniqueList(fields.String(),key=lambda value:value.casefold())
    failed=False
    try:
        field.deserialize(['Alpha','beta','ALPHA','BETA'])
    except ValidationError as error:
        failed=set(error.messages)=={2,3}
    business=failed and field.deserialize(['Alpha','beta'])==['Alpha','beta']

except Exception:
    business = False

print(json.dumps({'candidate_import': _candidate_import_bound, 'business': bool(business)}))
