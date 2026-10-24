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
suite = control.SUITES['funcy']
import_root = Path(suite.get('import_root', '.'))
control._bind_source(root / 'library', import_root, cleanup, distribution=suite.get('distribution'))
sys.path.insert(0, str(root / 'library' / import_root))

import funcy
class Example:
    """独立核对readonly别名与类访问。"""
    def __init__(self):self.calls=0
    def compute(self):self.calls+=1;return self.calls
    other=funcy.cached_readonly(compute)
obj=Example();business=obj.other==obj.other==1 and callable(obj.compute) and Example.other.fget is Example.compute

print(json.dumps({'candidate_import': Path(funcy.__file__).resolve().is_relative_to(root / 'library'), 'business': bool(business)}))
