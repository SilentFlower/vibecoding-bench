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
sources=([('x',),(1,),(2,)],[('x',),(3,)],[('x',),(4,),(5,)])
rows=list(petl.crossjoin(*sources,prefixes=('left_','middle_','right_')))
business &= rows[0]==('left_x','middle_x','right_x') and rows[1:]==[(1,3,4),(1,3,5),(2,3,4),(2,3,5)]

print(json.dumps({'candidate_import': Path(petl.__file__).resolve().is_relative_to(root / 'library'), 'business': bool(business)}))
