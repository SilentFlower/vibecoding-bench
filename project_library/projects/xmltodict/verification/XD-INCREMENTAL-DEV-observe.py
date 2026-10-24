"""在固定候选源码上运行独立业务矩阵，不调用模型或外部服务。"""
import json
import os
from pathlib import Path
root = Path(os.environ['PROJECT_CANDIDATE_ROOT']).resolve()

import xmltodict
_candidate_source_root = root
business = False
try:
    seen=[]
    parser=xmltodict.IncrementalParser(process_namespaces=True,process_comments=True,max_text_chars=4,item_depth=2,item_callback=lambda path,item:not seen.append((path[-1][0],item)))
    parser.feed('<r xmlns="urn:x"><a>雪</a>');parser.feed('<a>花</a></r>')
    result=parser.close()
    business=result is None and seen==[('urn:x:a','雪'),('urn:x:a','花')]

except Exception:
    business = False

print(json.dumps({'candidate_import': Path(xmltodict.__file__).resolve().is_relative_to(_candidate_source_root / 'library'), 'business': bool(business)}))
