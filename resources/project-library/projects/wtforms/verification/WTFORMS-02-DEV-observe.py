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
from wtforms import Form,IntegerField,BooleanField
from wtforms.validators import NumberRange,ValidationError
from wtforms.data_optional import DataOptional
business=True
seen=[]
def record(form,field):
    """记录非空False也必须执行后续规则。@param form 表单。@param field 字段。@return None。"""
    seen.append(field.data)
class Product(Form):
    """非空假值与转换失败矩阵。"""
    quantity=IntegerField(validators=[DataOptional(),NumberRange(min=0,max=2)])
    flag=BooleanField(validators=[DataOptional(),record])
business &= Product(data={'quantity':0,'flag':False}).validate() and seen==[False]
business &= not Product(data={'quantity':3}).validate()
business &= not Product(data={'quantity':'wrong'}).validate()
class FormData:
    """最小真实getlist请求协议。"""
    def __contains__(self,key):return key=='quantity'
    def getlist(self,key):return [''] if key=='quantity' else []
form=Product(FormData());business &= form.validate() and form.quantity.errors==[]

print(json.dumps({'candidate_import': Path(wtforms.__file__).resolve().is_relative_to(root / 'library'), 'business': bool(business)}))
