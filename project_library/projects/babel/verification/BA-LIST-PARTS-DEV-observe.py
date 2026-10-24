"""在固定候选源码上运行独立业务矩阵，不调用模型或外部服务。"""
import json
import os
from pathlib import Path
root = Path(os.environ['PROJECT_CANDIDATE_ROOT']).resolve()

import babel
_candidate_source_root = root
business = False
try:
    from babel.lists import format_list, format_list_to_parts
    business = True
    for locale in ('ja', 'de', 'ar', 'he', 'es'):
        for values in ([''], ['x', 'x'], ['{1}', '', 'A\u2063', '尾', '尾']):
            for style in ('standard', 'or-short', 'unit'):
                try:
                    expected = format_list(values, style, locale)
                except (KeyError, ValueError) as original_error:
                    try:
                        format_list_to_parts(values, style, locale)
                        business = False
                    except type(original_error):
                        pass
                    continue
                parts = format_list_to_parts(values, style, locale)
                business = business and ''.join(p['value'] for p in parts) == expected
                elements = [p for p in parts if p['type']=='element']
                business = business and all(p['value'] == values[p['index']] for p in elements) and {p['index'] for p in elements} == set(range(len(values)))

except Exception:
    business = False

print(json.dumps({'candidate_import': Path(babel.__file__).resolve().is_relative_to(_candidate_source_root / 'library'), 'business': bool(business)}))
