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
    from datetime import timedelta
    from babel.dates import format_duration, format_timedelta
    from babel.units import format_unit
    from babel.lists import format_list
    business = True
    for locale in ('zh','ru','ar','de'):
        for length, style in (('long','unit'),('short','unit-short'),('narrow','unit-narrow')):
            pieces = [format_unit(2,'duration-day',length,locale=locale), format_unit(1,'duration-hour',length,locale=locale), format_unit(Decimal('2.5'),'duration-second',length,locale=locale)]
            actual = format_duration(timedelta(days=2,hours=1,seconds=2,microseconds=500000), length=length, locale=locale)
            try:
                expected = format_list(pieces, style, locale)
            except KeyError:
                expected = format_list(pieces, 'standard', locale)
            business = business and actual == expected
    business = business and format_timedelta(timedelta(days=60), locale='en') == '2 months'

except Exception:
    business = False

print(json.dumps({'candidate_import': Path(babel.__file__).resolve().is_relative_to(_candidate_source_root / 'library'), 'business': bool(business)}))
