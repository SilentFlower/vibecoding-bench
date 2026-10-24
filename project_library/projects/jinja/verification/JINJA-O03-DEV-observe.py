"""在固定候选源码上运行独立业务矩阵，不调用模型或外部服务。"""
import json
import os
from pathlib import Path
root = Path(os.environ['PROJECT_CANDIDATE_ROOT']).resolve()
_bench_candidate_root = root
import sys
sys.path.insert(0, str(root / 'library' / 'src'))

import jinja2
from jinja2 import Environment
business=all(Environment(optimized=mode).from_string('{{ -2**exponent}}').render(exponent=2)=='4' for mode in (False,True))
business=business and Environment().from_string('{{2**3**n}}').render(n=2)=='64'

print(json.dumps({'candidate_import': Path(jinja2.__file__).resolve().is_relative_to(_bench_candidate_root / 'library'), 'business': bool(business)}))
