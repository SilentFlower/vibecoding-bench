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
suite = control.SUITES['tqdm']
control._bind_source(root / 'library', Path(suite.get('import_root', '.')), cleanup, distribution=suite.get('distribution'))
import sys
sys.path.insert(0, str(root / 'library' / suite.get('import_root', '.')))
import tqdm
from tqdm.utils import CallbackIOWrapper
import io
business=True
class Stream:
    """异常返回值业务矩阵。"""
    def __init__(self,value):self.value=value
    def write(self,data):return self.value
for value in (-1,4,True,0.5):
    seen=[]
    try:CallbackIOWrapper(seen.append,Stream(value),method='write').write(b'abc')
    except (TypeError,ValueError):pass
    else:business=False
    business &= seen==[]
seen=[];read=CallbackIOWrapper(seen.append,io.BytesIO(b'abcdef'));business &= read.read(2)==b'ab' and seen==[2]

print(json.dumps({'candidate_import': Path(tqdm.__file__).resolve().is_relative_to(root / 'library'), 'business': bool(business)}))
