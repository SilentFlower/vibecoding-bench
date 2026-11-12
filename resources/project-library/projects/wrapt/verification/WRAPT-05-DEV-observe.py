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
from wrapt.canonical_cache import canonical_cache
business=True
calls=[]
@canonical_cache()
def f(x,/,*values,flag=False,**options):calls.append(1);return (x,values,flag,options)
a=f(1,2,z=4,a=3);b=f(1,2,flag=False,a=3,z=4)
business &= a is b and len(calls)==1 and f.cache_info().hits==1

print(json.dumps({'candidate_import': Path(wrapt.__file__).resolve().is_relative_to(root / 'library'), 'business': bool(business)}))
