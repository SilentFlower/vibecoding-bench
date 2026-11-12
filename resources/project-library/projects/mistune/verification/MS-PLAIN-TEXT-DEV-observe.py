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
    from mistune.renderers.text import PlainTextRenderer
    md=mistune.create_markdown(renderer=PlainTextRenderer(),plugins=['task_lists'])
    first=md('- [x] done\n- [ ] later\n\n```\n<tag>&amp;\n```')
    second=md('next')
    business='- [x] done' in first and '- [ ] later' in first and '<tag>&amp;' in first and second=='next\n'

except Exception:
    business = False

print(json.dumps({'candidate_import': _candidate_import_bound, 'business': bool(business)}))
