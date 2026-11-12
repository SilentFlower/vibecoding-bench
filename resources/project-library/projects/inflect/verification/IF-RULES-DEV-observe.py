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
    from inflect.rules import define_nouns
    target=engine();target.gender('feminine');target.defadj('thisish','theseish')
    count=define_nouns(target,iter([{'singular':'testwidget','plural':'testwidgeten'}]))
    failed=False
    try:
        define_nouns(target,[{'singular':'a','plural':'b','unexpected':1}])
    except ValueError:
        failed=True
    business=count==1 and failed and target.thegender=='feminine' and target.plural_adj('thisish')=='theseish' and target.plural_noun('testwidget')=='testwidgeten'

except Exception:
    business = False

print(json.dumps({'candidate_import': _candidate_import_bound, 'business': bool(business)}))
