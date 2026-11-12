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
from pyrsistent import freeze,CheckedPMap
from pyrsistent.merge import deep_merge,MergeConflict
business=True
left=freeze({'x':{'a':1},'keep':[1,2]})
business &= deep_merge(left,{}) is left
try:deep_merge(left,{'x':{'a':2}},conflict='raise')
except MergeConflict as error:business &= error.path==('x','a')
else:business=False
class Checked(CheckedPMap):
    """合并仍使用真实校验evolver。"""
    __key_type__=str;__value_type__=int
checked=Checked({'n':1});business &= deep_merge(checked,[('n',2)])=={'n':2}
try:deep_merge(checked,{'n':'bad'})
except TypeError:pass
else:business=False
business &= checked=={'n':1} and left['x']['a']==1

print(json.dumps({'candidate_import': Path(pyrsistent.__file__).resolve().is_relative_to(root / 'library'), 'business': bool(business)}))
