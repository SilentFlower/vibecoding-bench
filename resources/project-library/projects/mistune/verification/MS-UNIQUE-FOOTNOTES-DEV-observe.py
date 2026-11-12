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
    from mistune.plugins.footnotes import footnotes
    md=mistune.create_markdown(plugins=[lambda md:footnotes(md,unique_refs=True)])
    result=md('a[^first] b[^second] c[^first]\n\n[^first]: one\n[^second]: two')
    business='id="fnref-1-2"' in result and 'href="#fnref-1-2"' in result and 'id="fnref-2"' in result and result.count('<li id=')==2

except Exception:
    business = False

print(json.dumps({'candidate_import': _candidate_import_bound, 'business': bool(business)}))
