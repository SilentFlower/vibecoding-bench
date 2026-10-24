"""在固定候选源码上运行独立业务矩阵，不调用模型或外部服务。"""
import json
import os
from pathlib import Path
root = Path(os.environ['PROJECT_CANDIDATE_ROOT']).resolve()

import ftfy
_candidate_source_root = root
_candidate_import_bound = Path(ftfy.__file__).resolve().is_relative_to(_candidate_source_root / 'library')
business = False
try:
    import hashlib
    from ftfy import TextFixerConfig
    from ftfy.audit import repair
    source='\ud800';result=repair(source,TextFixerConfig(explain=False))
    business=result.text=='�' and result.changed and result.explanation is None and result.source_sha256==hashlib.sha256(source.encode('utf-8','surrogatepass')).hexdigest()

except Exception:
    business = False

print(json.dumps({'candidate_import': _candidate_import_bound, 'business': bool(business)}))
