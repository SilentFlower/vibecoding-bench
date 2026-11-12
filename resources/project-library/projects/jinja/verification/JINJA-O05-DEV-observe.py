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
    from jinja2 import Environment,DictLoader
    env=Environment(loader=DictLoader({'m':'{% macro value() %}ok{% endmacro %}'}))
    business=env.from_string('{% from ["none","m"] import value as show %}{{show()}}').render()=='ok'
except TypeError:business=False

print(json.dumps({'candidate_import': Path(jinja2.__file__).resolve().is_relative_to(_bench_candidate_root / 'library'), 'business': bool(business)}))
