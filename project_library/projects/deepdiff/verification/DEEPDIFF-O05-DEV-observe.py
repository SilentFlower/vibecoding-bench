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
suite = control.SUITES['deepdiff']
import_root = Path(suite.get('import_root', '.'))
control._bind_source(root / 'library', import_root, cleanup, distribution=suite.get('distribution'))
sys.path.insert(0, str(root / 'library' / import_root))

import deepdiff
business=False
try:
    from deepdiff.merge3 import merge3
    base={'a':{'x':1,'y':1},'keep':0};left={'a':{'x':2,'y':1},'keep':0};right={'a':{'x':1,'y':3},'keep':0}
    result=merge3(base,left,right)
    business=result.complete and result.value=={'a':{'x':2,'y':3},'keep':0} and base['a']['x']==1
    conflict=merge3(True,False,1)
    business=business and not conflict.complete and conflict.conflicts[0]['path']==[] and conflict.value is True
except ImportError:business=False

print(json.dumps({'candidate_import': Path(deepdiff.__file__).resolve().is_relative_to(root / 'library'), 'business': bool(business)}))
