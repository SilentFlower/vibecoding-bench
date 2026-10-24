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
    from ftfy.pipeline import TextRepairPipeline
    pipeline=TextRepairPipeline([('name',)])
    def source():
        yield {'name':'ok'}
        raise RuntimeError('upstream')
    stream=pipeline.run(source(),errors='collect');first=next(stream);failed=False
    try:
        next(stream)
    except RuntimeError:
        failed=True
    business=first.value=={'name':'ok'} and failed

except Exception:
    business = False

print(json.dumps({'candidate_import': _candidate_import_bound, 'business': bool(business)}))
