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
        path=Path(temporary)/'out';data=b'\x00\xffbinary\r\n'
        first=path.atomic_write(data);second=path.atomic_write(data,if_changed=True)
        business=first and not second and path.read_bytes()==data and len(list(Path(temporary).iterdir()))==1

except Exception:
    business = False

print(json.dumps({'candidate_import': _candidate_import_bound, 'business': bool(business)}))
