"""在固定候选源码上运行独立业务矩阵，不调用模型或外部服务。"""
import json
import os
from pathlib import Path
root = Path(os.environ['PROJECT_CANDIDATE_ROOT']).resolve()

import cli_helpers
_candidate_source_root = root
business = False
try:
    from cli_helpers.tabular_output.json_output_adapter import adapter
    from decimal import Decimal
    import json
    value=Decimal('-0.00000000000000000100')
    first=next(adapter([[value,'雪']],['amount','name'],table_format='jsonl_escaped',decimal_policy='string',strict_json=True))
    second=next(adapter([[value]],['amount']))
    business=json.loads(first)=={'amount':str(value),'name':'雪'} and isinstance(json.loads(second)['amount'],float) and value==Decimal('-0.00000000000000000100')

except Exception:
    business = False

print(json.dumps({'candidate_import': Path(cli_helpers.__file__).resolve().is_relative_to(_candidate_source_root / 'library'), 'business': bool(business)}))
