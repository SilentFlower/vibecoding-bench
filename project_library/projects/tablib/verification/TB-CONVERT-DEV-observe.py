"""在固定候选源码上运行独立业务矩阵，不调用模型或外部服务。"""
import json
import os
from pathlib import Path
root = Path(os.environ['PROJECT_CANDIDATE_ROOT']).resolve()

import tablib
_candidate_source_root = root
_candidate_import_bound = Path(tablib.__file__).resolve().is_relative_to(_candidate_source_root / 'library')
business = False
try:
    from tablib import Dataset
    from tablib.conversion import convert_columns
    source=Dataset(headers=['value']);source.append(['2'],tags=['active'])
    result=convert_columns(source,{'value':int})
    business=result.dataset[0]==(2,) and result.dataset.filter('active').height==1 and source[0]==('2',)

except Exception:
    business = False

print(json.dumps({'candidate_import': _candidate_import_bound, 'business': bool(business)}))
