"""在固定候选源码上运行独立业务矩阵，不调用模型或外部服务。"""
import json
import os
from pathlib import Path
root = Path(os.environ['PROJECT_CANDIDATE_ROOT']).resolve()

import babel
_candidate_source_root = root
business = False
try:
    from babel import Locale
    from babel.numbers import format_number_range, format_currency, format_decimal
    business = True
    for locale in ('fr', 'ar_EG', 'ja', 'sv'):
        for currency in (None, 'JPY', 'EUR'):
            options = {'numbering_system':'default'}
            formatter = (lambda value: format_decimal(value, locale=locale, **options)) if currency is None else (lambda value: format_currency(value, currency, locale=locale, **options))
            left, right = formatter(-1234), formatter(5678)
            actual = format_number_range(-1234, 5678, currency=currency, locale=locale, **options)
            expected = Locale.parse(locale).interval_formats[None].replace('{0}', left).replace('{1}', right)
            business = business and actual == expected

except Exception:
    business = False

print(json.dumps({'candidate_import': Path(babel.__file__).resolve().is_relative_to(_candidate_source_root / 'library'), 'business': bool(business)}))
