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
suite = control.SUITES['icecream']
import_root = Path(suite.get('import_root', '.'))
control._bind_source(root / 'library', import_root, cleanup, distribution=suite.get('distribution'))
sys.path.insert(0, str(root / 'library' / import_root))

import icecream
business=False
try:
    output=[];timer=icecream.IceCreamDebugger(outputFunction=output.append).timer
    with timer:
        with timer:pass
    business=len(output)==2 and timer._enter_time is None
    try:timer.__exit__(None,None,None)
    except RuntimeError:pass
    else:business=False
except RuntimeError:business=False

print(json.dumps({'candidate_import': Path(icecream.__file__).resolve().is_relative_to(root / 'library'), 'business': bool(business)}))
