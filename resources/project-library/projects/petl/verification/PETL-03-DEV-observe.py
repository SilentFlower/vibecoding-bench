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
suite = control.SUITES['petl']
control._bind_source(root / 'library', Path(suite.get('import_root', '.')), cleanup, distribution=suite.get('distribution'))
import sys
sys.path.insert(0, str(root / 'library' / suite.get('import_root', '.')))
import petl
import petl
business=True
source=[('country','city','month','value'),('x','a','jan',4),('x','a','feb',5),('x','b','feb',6)]
result=list(petl.pivot(source,['country','city'],'month','value',max,missing=-1))
business &= result==[('country','city','feb','jan'),('x','a',5,4),('x','b',6,-1)]

print(json.dumps({'candidate_import': Path(petl.__file__).resolve().is_relative_to(root / 'library'), 'business': bool(business)}))
