"""在固定候选源码上运行独立业务矩阵，不调用模型或外部服务。"""
import json
import os
from pathlib import Path
root = Path(os.environ['PROJECT_CANDIDATE_ROOT']).resolve()

import arrow
_candidate_source_root = root
from arrow.parser import DateTimeParser, ParserError
business = False
try:
    parser = DateTimeParser(cache_size=2)
    valid = parser.parse_strict('2026/3/4 5:6:7', 'YYYY/M/D H:m:s', exact_width=True)
    rejected = 0
    for text, fmt in [('2026/03/4', 'YYYY/M/D'), ('2026-03-04 trailing','YYYY-MM-DD'), ('2026-366','YYYY-DDD'), ('at','[at]'), ('2026-03-04+03:99','YYYY-MM-DDZZ')]:
        try:
            parser.parse_strict(text, fmt, exact_width=True)
        except ParserError:
            rejected += 1
    legacy = parser.parse('2026/03/4', 'YYYY/M/D')
    business = (valid.year == 2026 and valid.hour == 5 and legacy.month == 3 and rejected == 5
        and arrow.get('2026-03-04+03:30', 'YYYY-MM-DDZZ', strict=True).utcoffset().total_seconds() == 12600)
except Exception:
    business = False

print(json.dumps({'candidate_import': Path(arrow.__file__).resolve().is_relative_to(_candidate_source_root / 'library'), 'business': bool(business)}))
