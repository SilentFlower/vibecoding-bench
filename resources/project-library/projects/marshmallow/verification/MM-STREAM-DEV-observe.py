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
    from marshmallow import Schema,fields,post_load
    class Item(Schema):
        name=fields.String(required=True)
        @post_load
        def build(self,data,**kwargs):
            if data['name']=='crash':
                raise RuntimeError('business')
            return data
    schema=Item();stream=schema.iterload([{}, {'name':'ok'},{'name':'crash'}],errors='collect')
    first=next(stream);second=next(stream);propagated=False
    try:
        next(stream)
    except RuntimeError:
        propagated=True
    business=first.index==0 and first.errors[0].pointer=='/name' and second.data=={'name':'ok'} and propagated

except Exception:
    business = False

print(json.dumps({'candidate_import': _candidate_import_bound, 'business': bool(business)}))
