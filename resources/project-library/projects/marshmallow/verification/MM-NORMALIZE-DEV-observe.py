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
    from marshmallow import Schema,fields
    from marshmallow.normalized import NormalizedString
    class Record(Schema):
        key=NormalizedString(form='NFKC',casefold=True)
        raw=fields.String()
    result=Record().load({'key':'  Ａ  ','raw':'  Ａ  '})
    business=result=={'key':'a','raw':'  Ａ  '} and NormalizedString(strip=False,form=None).deserialize(' A ')==' A '

except Exception:
    business = False

print(json.dumps({'candidate_import': _candidate_import_bound, 'business': bool(business)}))
