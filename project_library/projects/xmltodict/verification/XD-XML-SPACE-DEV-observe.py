"""在固定候选源码上运行独立业务矩阵，不调用模型或外部服务。"""
import json
import os
from pathlib import Path
root = Path(os.environ['PROJECT_CANDIDATE_ROOT']).resolve()

import xmltodict
_candidate_source_root = root
business = False
try:
    text='<r xml:space="preserve"><a xml:space="unknown">  x  </a><b xml:space="default"><c> y </c></b><d> z </d></r>'
    result=xmltodict.parse(text,respect_xml_space=True,process_namespaces=True,namespace_separator='|')['r']
    business=result['a']['#text']=='  x  ' and result['b']['c']=='y' and result['d']==' z '

except Exception:
    business = False

print(json.dumps({'candidate_import': Path(xmltodict.__file__).resolve().is_relative_to(_candidate_source_root / 'library'), 'business': bool(business)}))
