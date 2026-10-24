"""在固定候选源码上运行独立业务矩阵，不调用模型或外部服务。"""
import json
import os
from pathlib import Path
root = Path(os.environ['PROJECT_CANDIDATE_ROOT']).resolve()

import mistune
_candidate_source_root = root
_candidate_import_bound = Path(mistune.__file__).resolve().is_relative_to(_candidate_source_root / 'library')
business = False
try:
    from mistune.toc import add_toc_hook
    md=mistune.create_markdown(renderer='ast',plugins=['footnotes']);add_toc_hook(md,include_nested=True)
    tokens,state=md.parse('# Top[^x]\n\n> ## Nested\n\n[^x]: note\n')
    business=[item[2] for item in state.env['toc_items']]==['Top[1]','Nested'] and state.env['footnotes']==['X']

except Exception:
    business = False

print(json.dumps({'candidate_import': _candidate_import_bound, 'business': bool(business)}))
