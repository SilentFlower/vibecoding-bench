"""在固定候选源码上运行独立业务矩阵，不调用模型或外部服务。"""
import json
import os
from pathlib import Path
root = Path(os.environ['PROJECT_CANDIDATE_ROOT']).resolve()

import tomlkit
_candidate_source_root = root
business = False
try:
    from tomlkit.items import StringType
    business=True
    for literal,multiline,value in [(False,False,'a\\b"c'),(True,False,'path\\name'),(False,True,'\nfirst\r\nlast'),(True,True,'\n雪\n花')]:
        old=tomlkit.string('old',literal=literal,multiline=multiline)
        new=old.replace_value(value)
        business=business and new.type==old.type and tomlkit.parse('a='+new.as_string())['a']==value and str(old)=='old'

except Exception:
    business = False

print(json.dumps({'candidate_import': Path(tomlkit.__file__).resolve().is_relative_to(_candidate_source_root / 'library'), 'business': bool(business)}))
