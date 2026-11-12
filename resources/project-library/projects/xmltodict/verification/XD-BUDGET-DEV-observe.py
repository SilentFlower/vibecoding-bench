"""在固定候选源码上运行独立业务矩阵，不调用模型或外部服务。"""
import json
import os
from pathlib import Path
root = Path(os.environ['PROJECT_CANDIDATE_ROOT']).resolve()

import xmltodict
_candidate_source_root = root
business = False
try:
    from xml.parsers.expat import ExpatError
    limits=[]
    for option in ('max_depth','max_elements','max_text_chars'):
        try:
            xmltodict.parse('<a>x</a>',**{option:0})
            limits.append(False)
        except xmltodict.XMLLimitError:
            limits.append(True)
    pieces=(part for part in (b'<a>', '雪'.encode('utf-8'), b'</a>'))
    business=all(limits) and xmltodict.parse(pieces,max_depth=1,max_elements=1,max_text_chars=1)=={'a':'雪'}

except Exception:
    business = False

print(json.dumps({'candidate_import': Path(xmltodict.__file__).resolve().is_relative_to(_candidate_source_root / 'library'), 'business': bool(business)}))
