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
suite = control.SUITES['csvkit']
import_root = Path(suite.get('import_root', '.'))
control._bind_source(root / 'library', import_root, cleanup, distribution=suite.get('distribution'))
sys.path.insert(0, str(root / 'library' / import_root))

import csvkit
business=False
try:
    from csvkit.headers import rename_columns
    names=['1','with space','with space_2']
    business=rename_columns(names,{'1':'with space'},collision='suffix')==['with space','with space_3','with space_2']
    try:rename_columns(['x'],{'x':None})
    except ValueError:pass
    else:business=False
except ImportError:business=False

print(json.dumps({'candidate_import': Path(csvkit.__file__).resolve().is_relative_to(root / 'library'), 'business': bool(business)}))
