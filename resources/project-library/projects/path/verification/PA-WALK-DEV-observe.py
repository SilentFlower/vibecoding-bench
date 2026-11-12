"""在固定候选源码上运行独立业务矩阵，不调用模型或外部服务。"""
import json
import os
from pathlib import Path
root = Path(os.environ['PROJECT_CANDIDATE_ROOT']).resolve()

import path
_candidate_source_root = root
_candidate_import_bound = Path(path.__file__).resolve().is_relative_to(_candidate_source_root / 'library')
business = False
try:
    from path import Path
    from tempfile import TemporaryDirectory
    with TemporaryDirectory() as temporary:
        root=Path(temporary);(root/'keep').mkdir();(root/'keep'/'x.txt').write_text('x');(root/'skip').mkdir();(root/'skip'/'y.txt').write_text('y')
        class Custom(Path):
            pass
        result=list(Custom(root).walk_controlled(exclude=('skip',),stable=True,max_depth=2))
        business=[str(p.relpath(root)) for p in result]==['keep','keep/x.txt'] and all(isinstance(p,Custom) for p in result)

except Exception:
    business = False

print(json.dumps({'candidate_import': _candidate_import_bound, 'business': bool(business)}))
