"""在固定候选源码上运行独立业务矩阵，不调用模型或外部服务。"""
import json
import os
from pathlib import Path
root = Path(os.environ['PROJECT_CANDIDATE_ROOT']).resolve()

import tinydb
_candidate_source_root = root
business = False
try:
    from tinydb.operations import set_path, delete_path
    from tinydb import TinyDB
    from tinydb.storages import MemoryStorage
    from copy import deepcopy
    with TinyDB(storage=MemoryStorage) as db:
        db.insert_multiple([{'a':{'b':1,'keep':[]}},{'a':{'b':2,'keep':[]}}])
        db.update(set_path(('a','b'),{'x':[]}))
        db.update(delete_path(('a','keep')))
        rows=db.all()
        rows[0]['a']['b']['x'].append(1)
        doc={'a':{'b':2}}
        before=deepcopy(doc)
        failed=False
        try:
            delete_path(('a','b','c'))(doc)
        except TypeError:
            failed=True
        business=rows[1]['a']['b']=={'x':[]} and all('keep' not in row['a'] for row in rows) and failed and doc==before

except Exception:
    business = False

print(json.dumps({'candidate_import': Path(tinydb.__file__).resolve().is_relative_to(_candidate_source_root / 'library'), 'business': bool(business)}))
