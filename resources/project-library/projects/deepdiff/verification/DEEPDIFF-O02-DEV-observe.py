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
    from datetime import date,timedelta
    from deepdiff import DeepDiff
    business=bool(DeepDiff({'v':date(2020,1,1)},{'v':date(2020,1,2)},truncate_datetime='second'))
    business=business and bool(DeepDiff(timedelta(seconds=1),timedelta(seconds=2),truncate_datetime='day'))
except TypeError:business=False

print(json.dumps({'candidate_import': Path(deepdiff.__file__).resolve().is_relative_to(root / 'library'), 'business': bool(business)}))
