"""在固定候选源码上运行独立业务矩阵，不调用模型或外部服务。"""
import json
import os
from pathlib import Path
root = Path(os.environ['PROJECT_CANDIDATE_ROOT']).resolve()

import arrow
_candidate_source_root = root
from decimal import Decimal, localcontext
business = False
try:
    anchor = arrow.get(2040,12,31,23,59,59,999999)
    with localcontext() as context:
        context.prec = 7
        serial = anchor.to_excel(date_system='1900')
        restored = arrow.Arrow.from_excel(serial, date_system='1900')
    rejected = 0
    for serial in (Decimal(60), Decimal('60.999999'), Decimal('NaN')):
        try:
            arrow.Arrow.from_excel(serial, date_system='1900')
        except ValueError:
            rejected += 1
    business = (restored == anchor and rejected == 3
        and arrow.Arrow.from_excel(Decimal('-0.25'), date_system='1904').format('YYYY-MM-DD HH:mm') == '1903-12-31 18:00'
        and arrow.get(1970,1,1).to_excel(date_system='1900') == Decimal(25569))
except Exception:
    business = False

print(json.dumps({'candidate_import': Path(arrow.__file__).resolve().is_relative_to(_candidate_source_root / 'library'), 'business': bool(business)}))
