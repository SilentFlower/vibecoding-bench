"""在固定候选源码上运行独立业务矩阵，不调用模型或外部服务。"""
import json
import os
from pathlib import Path
root = Path(os.environ['PROJECT_CANDIDATE_ROOT']).resolve()

import cli_helpers
_candidate_source_root = root
business = False
try:
    from cli_helpers.tabular_output.preprocessors import spreadsheet_formula_policy
    values=['\t=1','+cmd','-text','@name','plain',-4,None]
    rows,headers=spreadsheet_formula_policy([values],['a']*len(values),formula_policy='escape')
    actual=next(rows)
    business=actual[:4]==["'"+value for value in values[:4]] and actual[4:]==['plain',-4,None] and values[0]=='\t=1'

except Exception:
    business = False

print(json.dumps({'candidate_import': Path(cli_helpers.__file__).resolve().is_relative_to(_candidate_source_root / 'library'), 'business': bool(business)}))
