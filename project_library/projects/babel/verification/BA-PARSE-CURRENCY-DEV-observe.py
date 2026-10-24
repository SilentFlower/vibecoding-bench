"""在固定候选源码上运行独立业务矩阵，不调用模型或外部服务。"""
import json
import os
from pathlib import Path
root = Path(os.environ['PROJECT_CANDIDATE_ROOT']).resolve()

import babel
_candidate_source_root = root
business = False
try:
    from decimal import Decimal
    from babel.numbers import parse_currency, format_currency, NumberFormatError
    business = True
    for locale, currency in (('ar_EG','EGP'), ('fr_FR','EUR'), ('sv_SE','SEK'), ('en_US','USD')):
        for value in (Decimal('-1234.50'), Decimal('0'), Decimal('99.25')):
            for kind in ('standard','accounting'):
                rendered = format_currency(value, currency, locale=locale, format_type=kind, numbering_system='default')
                business = business and parse_currency(rendered, currency, locale, numbering_system='default') == value
    for text in ('$1$2.00', '$1.00 2.00', '$Infinity', '$-1.00', '$1.00)'):
        try:
            parse_currency(text, 'USD', 'en_US')
            business = False
        except NumberFormatError:
            pass

except Exception:
    business = False

print(json.dumps({'candidate_import': Path(babel.__file__).resolve().is_relative_to(_candidate_source_root / 'library'), 'business': bool(business)}))
