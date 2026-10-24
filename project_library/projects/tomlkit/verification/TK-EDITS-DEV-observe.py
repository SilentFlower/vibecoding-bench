"""在固定候选源码上运行独立业务矩阵，不调用模型或外部服务。"""
import json
import os
from pathlib import Path
root = Path(os.environ['PROJECT_CANDIDATE_ROOT']).resolve()

import tomlkit
_candidate_source_root = root
business = False
try:
    from tomlkit.editing import apply_edits
    document=tomlkit.parse('# keep\n[a]\n"x.y"=true\nvalues=[1,2]\n')
    before=document.as_string()
    result=apply_edits(document,iter([{'op':'test','path':['a','x.y'],'value':True},{'op':'set','path':['a','values',0],'value':9},{'op':'delete','path':['a','x.y']}]))
    rejected=False
    try:
        apply_edits(document,[{'op':'test','path':['a','x.y'],'value':1}])
    except ValueError:
        rejected=True
    business=result.unwrap()=={'a':{'values':[9,2]}} and document.as_string()==before and rejected

except Exception:
    business = False

print(json.dumps({'candidate_import': Path(tomlkit.__file__).resolve().is_relative_to(_candidate_source_root / 'library'), 'business': bool(business)}))
