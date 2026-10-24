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
    from pathlib import Path
    from tempfile import TemporaryDirectory
    from ftfy.atomic import fix_file_atomic
    with TemporaryDirectory() as directory:
        source=Path(directory)/'source';target=Path(directory)/'target';source.write_bytes(b'')
        result=fix_file_atomic(source,target)
        business=target.read_bytes()==b'' and result.input_chars==0 and result.output_chars==0 and not result.changed

except Exception:
    business = False

print(json.dumps({'candidate_import': _candidate_import_bound, 'business': bool(business)}))
