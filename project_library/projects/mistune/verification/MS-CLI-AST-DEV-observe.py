"""在固定候选源码上运行独立业务矩阵，不调用模型或外部服务。"""
import json
import os
from pathlib import Path
root = Path(os.environ['PROJECT_CANDIDATE_ROOT']).resolve()

import mistune
_candidate_source_root = root
_candidate_import_bound = Path(mistune.__file__).resolve().is_relative_to(_candidate_source_root / 'library')
business = False
try:
    import subprocess,sys,json,tempfile
    from pathlib import Path
    with tempfile.TemporaryDirectory() as temporary:
        source=Path(temporary)/'source.md';source.write_text('from file')
        result=subprocess.run([sys.executable,'-m','mistune','-r','ast','-m','','-f',str(source)],input='',text=True,capture_output=True,timeout=8)
        business=result.returncode==0 and json.loads(result.stdout)==[] and result.stderr==''

except Exception:
    business = False

print(json.dumps({'candidate_import': _candidate_import_bound, 'business': bool(business)}))
