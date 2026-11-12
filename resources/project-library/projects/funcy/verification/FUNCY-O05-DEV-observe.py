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
business=False
try:
    from funcy.relations import join_by
    left=[{'id':None},{'id':0}];right=[{'key':None},{'key':None},{'key':9}]
    rows=list(join_by(iter(left),iter(right),'id','key',how='full'))
    business=len(rows)==4 and rows[0].left is left[0] and rows[1].right is right[1] and not rows[2].right_present and not rows[3].left_present
except ImportError:business=False

print(json.dumps({'candidate_import': Path(funcy.__file__).resolve().is_relative_to(root / 'library'), 'business': bool(business)}))
