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
    from marshmallow.discriminated import DiscriminatedNested
    class Text(Schema):
        value=fields.String(data_key='external',required=True)
    field=DiscriminatedNested('type',{'text':Text()})
    loaded=field.deserialize({'type':'text','external':'ok'})
    business=loaded=={'type':'text','value':'ok'} and field._serialize(loaded,None,None)=={'type':'text','external':'ok'}

except Exception:
    business = False

print(json.dumps({'candidate_import': _candidate_import_bound, 'business': bool(business)}))
