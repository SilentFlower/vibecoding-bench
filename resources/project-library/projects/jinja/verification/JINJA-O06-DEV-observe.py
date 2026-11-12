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
    from jinja2.loaders import ResourcesLoader
    from jinja2 import Environment
    import tempfile
    from pathlib import Path
    with tempfile.TemporaryDirectory() as directory:
        root=Path(directory);(root/'a').write_text('A{{x}}')
        env=Environment(loader=ResourcesLoader(root));business=env.get_template('a').render(x='x')=='Ax'
        (root/'a').write_text('B{{x}}');business=business and env.get_template('a').render(x='y')=='By'
except ImportError:business=False

print(json.dumps({'candidate_import': Path(jinja2.__file__).resolve().is_relative_to(_bench_candidate_root / 'library'), 'business': bool(business)}))
