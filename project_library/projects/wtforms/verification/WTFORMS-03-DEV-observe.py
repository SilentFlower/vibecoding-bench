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
from wtforms import Form,FieldList,FormField,StringField,IntegerField
from wtforms.validators import InputRequired
from wtforms.jsondata import JSONFormData
business=True
class Inner(Form):
    """真正的嵌套业务字段。"""
    sku=StringField(validators=[InputRequired()]);quantity=IntegerField()
class Outer(Form):
    """真正的数组表单。"""
    rows=FieldList(FormField(Inner))
form=Outer(JSONFormData({'rows':[{'sku':'','quantity':'bad'},{'sku':'ok','quantity':2}]}))
business &= not form.validate() and len(form.rows.entries)==2 and bool(form.rows.entries[0].form.sku.errors) and bool(form.rows.entries[0].form.quantity.errors)
data=JSONFormData({'x':'中文','flag':True});values=data.getlist('x');values.append('external')
business &= data.getlist('x')==['中文'] and data.getlist('flag')==['true']
try:JSONFormData({'x':{'y':{'z':1}}},max_depth=2)
except ValueError:pass
else:business=False

print(json.dumps({'candidate_import': Path(wtforms.__file__).resolve().is_relative_to(root / 'library'), 'business': bool(business)}))
