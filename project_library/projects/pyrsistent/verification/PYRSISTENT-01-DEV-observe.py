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
from pyrsistent import PRecord,PClass,CheckedPMap,field,pmap_field,pvector_field
business=True
class Inner(PRecord):
    """更深的记录值。"""
    amount=field(type=int,mandatory=True)
class Group(PClass):
    """向量和映射嵌套。"""
    items=pmap_field(str,Inner,optional=True)
class Groups(CheckedPMap):
    """外层映射。"""
    __key_type__=str
    __value_type__=Group
raw={'g':{'items':{'i':{'amount':3,'extra':'skip'}},'outer_extra':1}}
result=Groups.create(raw,ignore_extra=True)
business &= result['g'].items['i']==Inner(amount=3)
try:Groups.create(raw,ignore_extra=False)
except AttributeError:pass
else:business=False

print(json.dumps({'candidate_import': Path(pyrsistent.__file__).resolve().is_relative_to(root / 'library'), 'business': bool(business)}))
