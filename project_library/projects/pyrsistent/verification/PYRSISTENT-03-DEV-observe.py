"""独立业务验收，只读取当前候选，不联网或调用模型。"""
import json
import os
from pathlib import Path
root = Path(os.environ['PROJECT_CANDIDATE_ROOT']).resolve()
from contextlib import ExitStack
from importlib.util import module_from_spec, spec_from_file_location
spec = spec_from_file_location('frozen_native_control', Path(__file__).with_name('native_regression.py'))
control = module_from_spec(spec)
spec.loader.exec_module(control)
cleanup = ExitStack()
suite = control.SUITES['pyrsistent']
control._bind_source(root / 'library', Path(suite.get('import_root', '.')), cleanup, distribution=suite.get('distribution'))
import sys
sys.path.insert(0, str(root / 'library' / suite.get('import_root', '.')))
import pyrsistent
from pyrsistent import pdeque
business=True
for length in range(6):
    values=list(range(length));queue=pdeque(values,maxlen=8)
    for start in (None,-20,-3,0,2,20):
        for stop in (None,-20,-1,0,3,20):
            for step in (None,1,2,-1,-2):
                selected=slice(start,stop,step);result=queue[selected]
                business &= list(result)==values[selected] and result.maxlen==8
zero=pdeque((value for value in range(10)),maxlen=0)
business &= len(zero.append(1).appendleft(2).extend(range(3)).extendleft(range(3)))==0

print(json.dumps({'candidate_import': Path(pyrsistent.__file__).resolve().is_relative_to(root / 'library'), 'business': bool(business)}))
