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
suite = control.SUITES['python-constraint']
control._bind_source(root / 'library', Path(suite.get('import_root', '.')), cleanup, distribution=suite.get('distribution'))
import sys
sys.path.insert(0, str(root / 'library' / suite.get('import_root', '.')))
import constraint
from itertools import product
from constraint import Problem,BacktrackingSolver
from constraint.tables import AllowedTuples,ForbiddenTuples
business=True
rows=[(0,0,1),(0,1,0),(1,1,1)]
for cls in (AllowedTuples,ForbiddenTuples):
    for forward in (True,False):
        problem=Problem(BacktrackingSolver(forwardcheck=forward));problem.addVariables(['a','b','c'],[0,1]);problem.addConstraint(cls(rows),['a','b','c'])
        actual={tuple(item[key] for key in ('a','b','c')) for item in problem.getSolutions()}
        expected={row for row in product([0,1],repeat=3) if (row in rows)==(cls is AllowedTuples)}
        business &= actual==expected
empty=Problem();empty.addVariables(['a','b'],[0,1]);empty.addConstraint(AllowedTuples([]),['a','b']);business &= empty.getSolutions()==[]

print(json.dumps({'candidate_import': Path(constraint.__file__).resolve().is_relative_to(root / 'library'), 'business': bool(business)}))
