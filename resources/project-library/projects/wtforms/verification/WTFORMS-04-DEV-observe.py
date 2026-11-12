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
from wtforms import Form,StringField
from wtforms.validators import Length,ValidationError
from wtforms.partial import validate_fields
business=True
class Product(Form):
    """真实两字段掩码。"""
    a=StringField(validators=[Length(min=2)]);b=StringField(validators=[Length(min=3)])
form=Product(data={'a':'x','b':'long'});form.b.errors=['untouched']
result=validate_fields(form,[('a',)])
business &= not result.valid and result.errors[0]['path']==('a',) and form.b.errors==['untouched']
result.errors[0]['errors'].append('outside')
business &= 'outside' not in form.a.errors
empty=validate_fields(form,[]);business &= empty.valid and empty.validated==() and form.b.errors==['untouched']

print(json.dumps({'candidate_import': Path(wtforms.__file__).resolve().is_relative_to(root / 'library'), 'business': bool(business)}))
