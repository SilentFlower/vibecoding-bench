"""在固定候选源码上运行独立业务矩阵，不调用模型或外部服务。"""
import json
import os
from pathlib import Path
root = Path(os.environ['PROJECT_CANDIDATE_ROOT']).resolve()

import tabulate
_candidate_source_root = root
business = False
try:
    rows=[tabulate.SEPARATING_LINE,['001'],tabulate.SEPARATING_LINE,['002'],tabulate.SEPARATING_LINE]
    first=tabulate.tabulate(rows,showindex=('A','B'),tablefmt='grid',disable_numparse=True)
    second=tabulate.tabulate(rows,showindex=iter(['A','B']),tablefmt='grid',disable_numparse=True)
    business=first==second and '001' in first and '002' in first and rows[1]==['001']

except Exception:
    business = False

print(json.dumps({'candidate_import': Path(tabulate.__file__).resolve().is_relative_to(_candidate_source_root / 'library'), 'business': bool(business)}))
