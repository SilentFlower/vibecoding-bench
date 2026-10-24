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
    from csvkit.utilities.csvfind import find_columns
    visited=[]
    def rows():
        for index in range(7):visited.append(index);yield ['x' if index%2==0 else 'other']
    result=find_columns(rows(),['value'],[0],value='x',sample_size=2)
    business=visited==list(range(7)) and result['columns']==[{'index':0,'name':'value','count':4,'sample_rows':[1,3]}]
except ImportError:business=False

print(json.dumps({'candidate_import': Path(csvkit.__file__).resolve().is_relative_to(root / 'library'), 'business': bool(business)}))
