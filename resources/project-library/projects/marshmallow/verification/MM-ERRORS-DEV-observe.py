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
    from marshmallow import Schema,fields,ValidationError
    from marshmallow.error_paths import problem
    class Item(Schema):
        values=fields.List(fields.Integer(),required=True)
    try:
        Item().load({'values':['bad',2,'bad']})
    except ValidationError as error:
        result=problem(error)
        business=[row['pointer'] for row in result['errors']]==['/values/0','/values/2'] and error.data=={'values':['bad',2,'bad']}

except Exception:
    business = False

print(json.dumps({'candidate_import': _candidate_import_bound, 'business': bool(business)}))
