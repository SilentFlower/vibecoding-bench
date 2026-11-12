"""在固定候选源码上运行独立业务矩阵，不调用模型或外部服务。"""
import json
import os
from pathlib import Path
root = Path(os.environ['PROJECT_CANDIDATE_ROOT']).resolve()

import cli_helpers
_candidate_source_root = root
business = False
try:
    from cli_helpers.tabular_output import TabularOutputFormatter
    formatter=TabularOutputFormatter('csv');seen=[]
    def rows():
        for value in ('a','b'):
            seen.append(value)
            yield [value]
    first=formatter.stream_output(rows(),['name'],column_types=[str],delimiter=';')
    header=next(first);row=next(first)
    second=list(formatter.stream_output([[1,2]],['a','b'],column_types=[int,int]))
    business=header=='name' and row=='a' and seen==['a'] and second==['a,b','1,2']

except Exception:
    business = False

print(json.dumps({'candidate_import': Path(cli_helpers.__file__).resolve().is_relative_to(_candidate_source_root / 'library'), 'business': bool(business)}))
