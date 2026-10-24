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
suite = control.SUITES['configobj']
import_root = Path(suite.get('import_root', '.'))
control._bind_source(root / 'library', import_root, cleanup, distribution=suite.get('distribution'))
sys.path.insert(0, str(root / 'library' / import_root))

import configobj
business=False
try:
    from configobj.validate import Validator, VdtListItemError
    v=Validator();source=['true','no']
    business=v.check('typed_list(boolean)',source)==[True,False] and source==['true','no']
    try:v.check('typed_list(integer)',['2','bad'])
    except VdtListItemError as error:business=business and error.index==1
    else:business=False
except (ImportError,configobj.ConfigObjError):business=False
except Exception as error:
    if type(error).__name__=='VdtUnknownCheckError':business=False
    else:raise

print(json.dumps({'candidate_import': Path(configobj.__file__).resolve().is_relative_to(root / 'library'), 'business': bool(business)}))
