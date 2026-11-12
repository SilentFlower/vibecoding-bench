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
from constraint.cardinality import GlobalCardinality
business=True
for bounds in ({'A':(1,2),'B':(1,1)},{'A':(0,0),'B':(2,3)},{'A':(3,3),'B':(0,0)}):
    for closed in (True,False):
        for forward in (True,False):
            problem=Problem(BacktrackingSolver(forwardcheck=forward));problem.addVariables(['x','y','z'],['A','B','C']);problem.addConstraint(GlobalCardinality(bounds,closed),['x','y','z'])
            actual={tuple(row[key] for key in ('x','y','z')) for row in problem.getSolutions()}
            expected={row for row in product(['A','B','C'],repeat=3) if (not closed or set(row)<=set(bounds)) and all(low<=row.count(value)<=high for value,(low,high) in bounds.items())}
            business &= actual==expected

print(json.dumps({'candidate_import': Path(constraint.__file__).resolve().is_relative_to(root / 'library'), 'business': bool(business)}))
