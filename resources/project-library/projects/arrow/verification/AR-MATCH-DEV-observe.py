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
    parser = DateTimeParser()
    text = 'α  2028-02-29\n\t12:34 tail 2030-01-01'
    result = parser.parse_match(text, ['YYYY-MM-DD HH:mm', 'YYYY-MM-DD'], True)
    no_literal = False
    try:
        parser.parse_match('word', '[word]')
    except ParserError:
        no_literal = True
    business = (result.value.year == 2028 and result.value.hour == 12
        and result.matched == '2028-02-29\n\t12:34' and result.prefix == 'α  '
        and result.suffix == ' tail 2030-01-01' and text[slice(*result.span)] == result.matched
        and no_literal and result.format == 'YYYY-MM-DD HH:mm')
except Exception:
    business = False

print(json.dumps({'candidate_import': Path(arrow.__file__).resolve().is_relative_to(_candidate_source_root / 'library'), 'business': bool(business)}))
