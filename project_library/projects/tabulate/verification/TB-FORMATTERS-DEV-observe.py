"""在固定候选源码上运行独立业务矩阵，不调用模型或外部服务。"""
import json
import os
from pathlib import Path
root = Path(os.environ['PROJECT_CANDIDATE_ROOT']).resolve()

import tabulate
_candidate_source_root = root
business = False
try:
    from tabulate.formatters import tabulate_with_formatters
    from dataclasses import dataclass
    @dataclass
    class Record:
        code:int
        amount:int
    records=[Record(1,2),Record(3,4)]
    result=tabulate_with_formatters(records,headers='keys',formatters=[None,lambda value,row,col:f'USD {value:.2f}'],tablefmt='plain')
    business='amount' in result and 'USD 2.00' in result and 'USD 4.00' in result and records[0].amount==2

except Exception:
    business = False

print(json.dumps({'candidate_import': Path(tabulate.__file__).resolve().is_relative_to(_candidate_source_root / 'library'), 'business': bool(business)}))
