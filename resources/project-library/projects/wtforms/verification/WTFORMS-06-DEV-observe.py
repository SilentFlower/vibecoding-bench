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
from wtforms import Form,IntegerField
from wtforms.validators import NumberRange
from wtforms.batch import validate_records
business=True
class Product(Form):
    """逐条真实整数范围。"""
    amount=IntegerField(validators=[NumberRange(min=0,max=2)])
rows=list(validate_records(Product,[(index,{'amount':index}) for index in range(4)]))
business &= [row.valid for row in rows]==[True,True,True,False] and [row.record_id for row in rows]==list(range(4))
iterator=validate_records(Product,[(1,{'amount':1}),(2,{'amount':2})],max_records=1)
business &= next(iterator).valid
try:next(iterator)
except ValueError:pass
else:business=False
business &= rows[3].data=={'amount':3} and bool(rows[3].errors['amount'])

print(json.dumps({'candidate_import': Path(wtforms.__file__).resolve().is_relative_to(root / 'library'), 'business': bool(business)}))
