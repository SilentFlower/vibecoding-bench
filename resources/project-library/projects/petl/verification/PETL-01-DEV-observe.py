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
tables=([['a','b','a'],[1,2,3]],[['b','a'],[4,5]],[['a','a','a'],[6,7,8]])
business &= list(petl.cat(*tables,duplicate_fields='occurrence',missing=0))==[('a','b','a','a'),(1,2,3,0),(5,4,0,0),(6,0,7,8)]

print(json.dumps({'candidate_import': Path(petl.__file__).resolve().is_relative_to(root / 'library'), 'business': bool(business)}))
