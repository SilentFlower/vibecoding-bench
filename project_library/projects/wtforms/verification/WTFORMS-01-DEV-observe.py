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
business=True
seen=[]
class Product(Form):
    """本地表单重复处理和验证。"""
    a=StringField();b=StringField()
    def filter_a(self,value):
        """记录过滤器顺序。@param value 数据。@return 原值。"""
        seen.append('filter');return value
    def validate_a(self,field):
        """记录inline。@param field 字段。@return None。"""
        seen.append('inline')
def explicit(form,field):
    """显式规则身份不变。@param form 表单。@param field 字段。@return None。"""
    seen.append('extra')
filters={'a':[],'b':()};validators={'a':[explicit]}
for index in range(3):
    form=Product(data={'a':'a','b':'b'},extra_filters=filters)
    for repeat in range(2):business &= form.validate(extra_validators=validators)
business &= filters=={'a':[],'b':()} and validators=={'a':[explicit]} and seen.count('filter')==3 and seen.count('inline')==seen.count('extra')==6

print(json.dumps({'candidate_import': Path(wtforms.__file__).resolve().is_relative_to(root / 'library'), 'business': bool(business)}))
