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
from collections import UserDict
import pydash
business=True
source=UserDict({'z':{'amount':4},'a':{'amount':1},'b':{'amount':4}})
result=pydash.sort_dict_by_values(source,key=lambda item:item['amount'])
business &= list(result)==['a','z','b'] and result['z'] is source['z'] and list(source)==['z','a','b']
business &= list(pydash.sort_dict_by_keys(source,reverse=True))==['z','b','a']

print(json.dumps({'candidate_import': Path(pydash.__file__).resolve().is_relative_to(root / 'library'), 'business': bool(business)}))
