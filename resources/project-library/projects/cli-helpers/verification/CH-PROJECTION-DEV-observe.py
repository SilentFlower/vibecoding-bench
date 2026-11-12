"""在固定候选源码上运行独立业务矩阵，不调用模型或外部服务。"""
import json
import os
from pathlib import Path
root = Path(os.environ['PROJECT_CANDIDATE_ROOT']).resolve()

import cli_helpers
_candidate_source_root = root
business = False
try:
    from cli_helpers.tabular_output.projection import select_columns
    from cli_helpers.tabular_output import TabularOutputFormatter
    rows,headers=select_columns(iter([[1,'001',None],[2,'002','x']]),iter(['id','code','note']),iter(['code',2]))
    result=list(TabularOutputFormatter('csv').format_output(rows,headers))
    business=result==['code,note','001,','002,x']

except Exception:
    business = False

print(json.dumps({'candidate_import': Path(cli_helpers.__file__).resolve().is_relative_to(_candidate_source_root / 'library'), 'business': bool(business)}))
