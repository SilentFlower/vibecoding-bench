"""在固定候选源码上运行独立业务矩阵，不调用模型或外部服务。"""
import json
import os
from pathlib import Path
root = Path(os.environ['PROJECT_CANDIDATE_ROOT']).resolve()
from contextlib import ExitStack
from importlib.util import module_from_spec, spec_from_file_location
import sys
spec = spec_from_file_location('frozen_control', Path(__file__).with_name('native_regression.py'))
control = module_from_spec(spec)
spec.loader.exec_module(control)
cleanup = ExitStack()
suite = control.SUITES['cattrs']
import_root = Path(suite.get('import_root', '.'))
control._bind_source(root / 'library', import_root, cleanup, distribution=suite.get('distribution'))
sys.path.insert(0, str(root / 'library' / import_root))

import cattrs
from dataclasses import dataclass, field
business = True
calls = []
def factory():
    """判别期间不可执行工厂。@return 空集合。"""
    calls.append(1)
    return set()
@dataclass
class A:
    """共同字段。"""
    value: int
@dataclass
class B:
    """非必需工厂字段。"""
    value: int
    optional: set = field(default_factory=factory)
for target in (A | B, B | A):
    try:
        cattrs.Converter().structure({'value': 5}, target)
    except TypeError:
        pass
    else:
        business = False
business &= calls == []

print(json.dumps({'candidate_import': Path(cattrs.__file__).resolve().is_relative_to(root / 'library'), 'business': bool(business)}))
