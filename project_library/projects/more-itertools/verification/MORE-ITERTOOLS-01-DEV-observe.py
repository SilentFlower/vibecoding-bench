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
suite = control.SUITES['more-itertools']
control._bind_source(root / 'library', Path(suite.get('import_root', '.')), cleanup, distribution=suite.get('distribution'))
import sys
sys.path.insert(0, str(root / 'library' / suite.get('import_root', '.')))
import more_itertools
from more_itertools import map_except,filter_except
business=True
seen=[]
result=list(map_except(lambda value:10//value,[2,0,5],ZeroDivisionError,on_error=lambda index,item,error:seen.append((index,item))))
business &= result==[5,2] and seen==[(1,0)]
seen=[]
business &= list(filter_except(lambda value:10//value,[0,1,0],ZeroDivisionError,on_error=lambda index,item,error:seen.append(index)))==[1] and seen==[0,2]

print(json.dumps({'candidate_import': Path(more_itertools.__file__).resolve().is_relative_to(root / 'library'), 'business': bool(business)}))
