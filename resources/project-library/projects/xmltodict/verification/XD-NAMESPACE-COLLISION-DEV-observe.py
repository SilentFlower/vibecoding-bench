"""在固定候选源码上运行独立业务矩阵，不调用模型或外部服务。"""
import json
import os
from pathlib import Path
root = Path(os.environ['PROJECT_CANDIDATE_ROOT']).resolve()

import xmltodict
_candidate_source_root = root
business = False
try:
    text='<r xmlns:a="urn:a" xmlns:b="urn:b"><a:x>1</a:x><b:x>2</b:x></r>'
    seen=[];rejected=False
    try:
        xmltodict.parse(text,process_namespaces=True,namespaces={'urn:a':'same','urn:b':'same'},namespace_collision='error',item_depth=2,item_callback=lambda path,item:not seen.append(item))
    except ValueError:
        rejected=True
    business=rejected and seen==['1'] and xmltodict.parse('<r><x>1</x><x>2</x></r>',namespace_collision='error')['r']['x']==['1','2']

except Exception:
    business = False

print(json.dumps({'candidate_import': Path(xmltodict.__file__).resolve().is_relative_to(_candidate_source_root / 'library'), 'business': bool(business)}))
