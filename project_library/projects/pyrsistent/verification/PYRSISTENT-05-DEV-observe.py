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
from pyrsistent import pmap
business=True
seen=[]
def pairs():
    """一次性CSV式资料。@return pairs流。"""
    for key,value in [('a',1),('b',2),('a',3)]:seen.append((key,value));yield key,value
old=pmap({'z':0});result=old.update(pairs())
business &= result=={'a':3,'b':2,'z':0} and len(seen)==3 and old=={'z':0}
def conflict(left,right):
    """冲突失败不能修改原持久对象。@param left 旧。@param right 新。@return 不返回。"""
    raise ValueError('conflict')
try:old.update_with(conflict,[('new',1),('z',2)])
except ValueError:pass
else:business=False
business &= old=={'z':0}

print(json.dumps({'candidate_import': Path(pyrsistent.__file__).resolve().is_relative_to(root / 'library'), 'business': bool(business)}))
