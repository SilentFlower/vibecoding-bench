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
suite = control.SUITES['wtforms']
control._bind_source(root / 'library', Path(suite.get('import_root', '.')), cleanup, distribution=suite.get('distribution'))
import sys
sys.path.insert(0, str(root / 'library' / suite.get('import_root', '.')))
import wtforms
from wtforms import Form,StringField,IntegerField
from wtforms.derive import derive_form
business=True
class Base(Form):
    """基础字段与多次构造。"""
    x=StringField();y=StringField()
original=list(Base._unbound_fields or [])
A=derive_form(Base,'A',{'z':IntegerField()});B=derive_form(Base,'B',{},remove=['x'])
for index in range(3):
    business &= [field.short_name for field in A()]==['x','y','z']
    business &= [field.short_name for field in B()]==['y']
    business &= [field.short_name for field in Base()]==['x','y']
business &= A().x is not A().x
try:derive_form(Base,'Bad',{},remove=['unknown'])
except ValueError:pass
else:business=False

print(json.dumps({'candidate_import': Path(wtforms.__file__).resolve().is_relative_to(root / 'library'), 'business': bool(business)}))
