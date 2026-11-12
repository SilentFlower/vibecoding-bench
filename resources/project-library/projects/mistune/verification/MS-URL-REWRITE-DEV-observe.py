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
    seen=[]
    def rewrite(url,kind):
        seen.append(kind)
        return 'https://destination.invalid/path'
    md=mistune.create_markdown(renderer=mistune.HTMLRenderer(url_rewriter=rewrite),plugins=['url'])
    result=md('https://example.invalid ![**alt**](image.png "caption")')
    business=seen==['link','image'] and 'href="https://destination.invalid/path"' in result and 'title="caption"' in result and 'alt="alt"' in result

except Exception:
    business = False

print(json.dumps({'candidate_import': _candidate_import_bound, 'business': bool(business)}))
