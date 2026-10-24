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
from pyrsistent import PRecord,CheckedPMap,CheckedPVector,field
business=True
class Item(PRecord):
    """格式在最深层字段可观测。"""
    value=field(type=int,serializer=lambda format,value:(format,value))
class Items(CheckedPMap):
    """内层映射。"""
    __key_type__=str;__value_type__=Item
class Groups(CheckedPVector):
    """外层向量。"""
    __type__=Items
value=Groups([Items({'a':Item(value=7)})])
for format in (None,'json','wire'):
    business &= value.serialize(format)==[{'a':{'value':(format,7)}}]

print(json.dumps({'candidate_import': Path(pyrsistent.__file__).resolve().is_relative_to(root / 'library'), 'business': bool(business)}))
