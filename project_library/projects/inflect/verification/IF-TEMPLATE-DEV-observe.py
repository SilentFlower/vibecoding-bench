"""在固定候选源码上运行独立业务矩阵，不调用模型或外部服务。"""
import json
import os
from pathlib import Path
root = Path(os.environ['PROJECT_CANDIDATE_ROOT']).resolve()

import inflect
_candidate_source_root = root
_candidate_import_bound = Path(inflect.__file__).resolve().is_relative_to(_candidate_source_root / 'library')
business = False
try:
    from inflect import engine
    from inflect.templates import ReportTemplate
    target=engine();template=ReportTemplate('{n:words} {n:ordinal}')
    first=template.render(target,{'n':12});failed=False
    try:
        ReportTemplate('{x} {missing}').render(target,{'x':'ok'})
    except KeyError as error:
        failed=error.args==('missing',)
    business=first=='twelve 12th' and failed and target._number_args is None

except Exception:
    business = False

print(json.dumps({'candidate_import': _candidate_import_bound, 'business': bool(business)}))
