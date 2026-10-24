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
from pyrsistent import PClass,pvector_field,InvariantException
import operator
import pickle
from functools import partial
business=True
class UnhashablePolicy:
    """可调用但不可hash，缓存必须按身份。"""
    __hash__=None
    def __call__(self,value):return value>0,'positive'
policy=UnhashablePolicy()
a=pvector_field(int,item_invariant=policy);b=pvector_field(int,item_invariant=policy)
business &= a.type==b.type
c=pvector_field(int,item_invariant=lambda value:(value<0,'negative'))
business &= a.type!=c.type and list(c.factory([-2]))==[-2]
try:a.factory([-2])
except InvariantException:pass
else:business=False
default=pvector_field(int).factory([1,-2]);business &= pickle.loads(pickle.dumps(default))==default

print(json.dumps({'candidate_import': Path(pyrsistent.__file__).resolve().is_relative_to(root / 'library'), 'business': bool(business)}))
