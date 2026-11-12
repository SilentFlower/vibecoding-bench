"""在固定候选源码上运行独立业务矩阵，不调用模型或外部服务。"""
import json
import os
from pathlib import Path
root = Path(os.environ['PROJECT_CANDIDATE_ROOT']).resolve()

import tinydb
_candidate_source_root = root
business = False
try:
    from tinydb import TinyDB, Query
    from tempfile import TemporaryDirectory
    from pathlib import Path
    with TemporaryDirectory() as temporary:
        with TinyDB(Path(temporary)/'db.json') as db:
            db.insert_multiple([{'n':i} for i in range(7)])
            first,cursor=db.query_page(Query().n.test(lambda value:value%2==0),limit=2)
            db.remove(doc_ids=[1])
            db.insert({'n':8})
            second,final=db.query_page(Query().n.test(lambda value:value%2==0),after=cursor,limit=3)
            business=([d.doc_id for d in first]==[1,3] and cursor==3 and [d.doc_id for d in second]==[5,7,8] and final is None)

except Exception:
    business = False

print(json.dumps({'candidate_import': Path(tinydb.__file__).resolve().is_relative_to(_candidate_source_root / 'library'), 'business': bool(business)}))
