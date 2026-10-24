"""在固定候选源码上运行独立业务矩阵，不调用模型或外部服务。"""
import json
import os
from pathlib import Path
root = Path(os.environ['PROJECT_CANDIDATE_ROOT']).resolve()

import xmltodict
_candidate_source_root = root
business = False
try:
    from io import StringIO
    value={'r':{'@xmlns':{'z':'urn:z','a':'urn:a'},'@z:k':'2','@a:k':'1','c':None}}
    text=xmltodict.unparse(value,sort_attributes=True,full_document=False,pretty=True)
    business=text.index('a:k=')<text.index('xmlns:a=')<text.index('xmlns:z=')<text.index('z:k=') and '<c></c>' in text

except Exception:
    business = False

print(json.dumps({'candidate_import': Path(xmltodict.__file__).resolve().is_relative_to(_candidate_source_root / 'library'), 'business': bool(business)}))
