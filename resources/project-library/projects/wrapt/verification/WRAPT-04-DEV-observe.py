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
suite = control.SUITES['wrapt']
control._bind_source(root / 'library', Path(suite.get('import_root', '.')), cleanup, distribution=suite.get('distribution'))
import sys
sys.path.insert(0, str(root / 'library' / suite.get('import_root', '.')))
import wrapt
from wrapt.ttl_cache import ttl_cache
business=True
t=[0];calls=[]
@ttl_cache(3,maxsize=1,clock=lambda:t[0])
def f(x):calls.append(x);return {'x':x}
a=f(1);business &= f(1) is a
t[0]=3;business &= f(1) is not a and calls==[1,1]
f.cache_clear();business &= f.cache_info().currsize==0 and f.cache_info().hits==0

print(json.dumps({'candidate_import': Path(wrapt.__file__).resolve().is_relative_to(root / 'library'), 'business': bool(business)}))
