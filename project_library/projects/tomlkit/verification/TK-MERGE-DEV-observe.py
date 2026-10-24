"""在固定候选源码上运行独立业务矩阵，不调用模型或外部服务。"""
import json
import os
from pathlib import Path
root = Path(os.environ['PROJECT_CANDIDATE_ROOT']).resolve()

import tomlkit
_candidate_source_root = root
business = False
try:
    from tomlkit.merging import merge_documents
    base=tomlkit.parse('[[workers]]\nname="one"\n')
    overlay=tomlkit.parse('[[workers]]\nname="two"\n')
    before=base.as_string();other=overlay.as_string()
    result=merge_documents(base,overlay,arrays='append')
    parsed=tomlkit.parse(result.as_string()).unwrap()
    business=parsed=={'workers':[{'name':'one'},{'name':'two'}]} and base.as_string()==before and overlay.as_string()==other

except Exception:
    business = False

print(json.dumps({'candidate_import': Path(tomlkit.__file__).resolve().is_relative_to(_candidate_source_root / 'library'), 'business': bool(business)}))
