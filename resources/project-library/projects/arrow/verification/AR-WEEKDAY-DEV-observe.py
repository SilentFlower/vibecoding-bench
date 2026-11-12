"""在固定候选源码上运行独立业务矩阵，不调用模型或外部服务。"""
import json
import os
from pathlib import Path
root = Path(os.environ['PROJECT_CANDIDATE_ROOT']).resolve()

import arrow
_candidate_source_root = root
from arrow.parser import DateTimeParser, ParserMatchError
business = False
try:
    parser = DateTimeParser(locale='en_us')
    numeric = [parser.parse(str(day), 'd').isoweekday() for day in range(1, 8)]
    contexts = [parser.parse('2025 03 ' + str(day), 'YYYY MM d') for day in range(1, 8)]
    rejected = False
    try:
        parser._parse_token('d', '8', {})
    except ParserMatchError:
        rejected = True
    business = numeric == list(range(1,8)) and all(value.month == 3 and value.year == 2025 for value in contexts) and rejected
except Exception:
    business = False

print(json.dumps({'candidate_import': Path(arrow.__file__).resolve().is_relative_to(_candidate_source_root / 'library'), 'business': bool(business)}))
