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
source={'~1':{'/':[{'x':0}]}}
business &= pydash.pointer_tokens('/~01/~1/0/x')==('~1','/','0','x')
business &= pydash.set_pointer(source,'/~01/~1/0/x',False) is source and pydash.get_pointer(source,'/~01/~1/0/x') is False
try:pydash.get_pointer(object(),'/__class__');business=False
except TypeError:pass

print(json.dumps({'candidate_import': Path(pydash.__file__).resolve().is_relative_to(root / 'library'), 'business': bool(business)}))
