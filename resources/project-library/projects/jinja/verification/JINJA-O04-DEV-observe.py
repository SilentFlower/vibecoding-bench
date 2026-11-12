"""在固定候选源码上运行独立业务矩阵，不调用模型或外部服务。"""
import json
import os
from pathlib import Path
root = Path(os.environ['PROJECT_CANDIDATE_ROOT']).resolve()
_bench_candidate_root = root
import sys
sys.path.insert(0, str(root / 'library' / 'src'))

import jinja2
business=False
try:
    import tempfile
    from pathlib import Path
    from jinja2 import Environment
    with tempfile.TemporaryDirectory() as directory:
        path=Path(directory)/'report.txt';Environment().from_string('a{{x}}b').stream(x='中').dump(path)
        business=path.read_bytes()=='a中b'.encode('utf8')
except AttributeError:business=False

print(json.dumps({'candidate_import': Path(jinja2.__file__).resolve().is_relative_to(_bench_candidate_root / 'library'), 'business': bool(business)}))
