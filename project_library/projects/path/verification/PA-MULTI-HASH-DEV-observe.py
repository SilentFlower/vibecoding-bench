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
    import hashlib
    with TemporaryDirectory() as temporary:
        path=Path(temporary)/'data';data=b'zero\x00binary\xff'*100;path.write_bytes(data)
        result=path.read_hashes(iter(['sha256','sha512']),chunk_size=1,hex=False)
        business=result=={'sha256':hashlib.sha256(data).digest(),'sha512':hashlib.sha512(data).digest()} and path.read_bytes()==data

except Exception:
    business = False

print(json.dumps({'candidate_import': _candidate_import_bound, 'business': bool(business)}))
