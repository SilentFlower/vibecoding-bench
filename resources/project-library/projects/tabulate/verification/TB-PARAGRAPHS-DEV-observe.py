"""在固定候选源码上运行独立业务矩阵，不调用模型或外部服务。"""
import json
import os
from pathlib import Path
root = Path(os.environ['PROJECT_CANDIDATE_ROOT']).resolve()

import tabulate
_candidate_source_root = root
business = False
try:
    business=True
    for text in ('a\n\nb','\n\na','a\n\n','a\n \nb'):
        actual=tabulate._wrap_text_to_colwidths([[text]],[50],numparses=[False])[0][0]
        expected='\n'.join('' if not line.strip() else line for line in text.splitlines())
        business=business and actual==expected

except Exception:
    business = False

print(json.dumps({'candidate_import': Path(tabulate.__file__).resolve().is_relative_to(_candidate_source_root / 'library'), 'business': bool(business)}))
