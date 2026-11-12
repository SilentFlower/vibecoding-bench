"""在固定候选源码上运行独立业务矩阵，不调用模型或外部服务。"""
import json
import os
from pathlib import Path
root = Path(os.environ['PROJECT_CANDIDATE_ROOT']).resolve()

import cli_helpers
_candidate_source_root = root
business = False
try:
    from cli_helpers.tabular_output.json_output_adapter import adapter
    import json
    headers=['x','x','x_2','x_3','x','']
    rows=[list(range(6)),list(range(6,12))]
    result=[json.loads(row) for row in adapter(rows,iter(headers),duplicate_headers='suffix')]
    business=list(result[0])==['x','x_4','x_2','x_3','x_5',''] and list(result[1].values())==list(range(6,12))

except Exception:
    business = False

print(json.dumps({'candidate_import': Path(cli_helpers.__file__).resolve().is_relative_to(_candidate_source_root / 'library'), 'business': bool(business)}))
