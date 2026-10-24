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
suite = control.SUITES['pydash']
control._bind_source(root / 'library', Path(suite.get('import_root', '.')), cleanup, distribution=suite.get('distribution'))
import sys
sys.path.insert(0, str(root / 'library' / suite.get('import_root', '.')))
import pydash
import pydash
business=True
seen=[]
class Callback:
    def __len__(self):return 0
    def __call__(self):seen.append('notice')
count=[0]
@pydash.retry(attempts=3,delay=0,on_exception=Callback())
def work():
    count[0]+=1
    if count[0]<3:raise ValueError('retry')
    return 'done'
business &= work()=='done' and seen==['notice','notice'] and count==[3]

print(json.dumps({'candidate_import': Path(pydash.__file__).resolve().is_relative_to(root / 'library'), 'business': bool(business)}))
