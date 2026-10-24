"""在固定候选源码上运行独立业务矩阵，不调用模型或外部服务。"""
import json
import os
from pathlib import Path
root = Path(os.environ['PROJECT_CANDIDATE_ROOT']).resolve()

import tinydb
_candidate_source_root = root
business = False
try:
    from tinydb.atomic import AtomicJSONStorage
    from tempfile import TemporaryDirectory
    from pathlib import Path
    with TemporaryDirectory() as temporary:
        path=Path(temporary)/'nested'/'db.json'
        first=AtomicJSONStorage(path,create_dirs=True,ensure_ascii=False)
        first.write({'data':{'雪':'花'}})
        secure=path.stat().st_mode&0o777==0o600
        second=AtomicJSONStorage(path)
        before=second.read()
        first.write({'data':{}})
        reread=second.read()
        first.close()
        failed=False
        try:
            first.write({})
        except ValueError:
            failed=True
        business=secure and before=={'data':{'雪':'花'}} and reread=={'data':{}} and failed

except Exception:
    business = False

print(json.dumps({'candidate_import': Path(tinydb.__file__).resolve().is_relative_to(_candidate_source_root / 'library'), 'business': bool(business)}))
