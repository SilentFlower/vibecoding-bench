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
from constraint import Problem,BacktrackingSolver
from constraint.optimization import optimize
business=True
problem=Problem(BacktrackingSolver());problem.addVariables(['a','b'],[0,1,2]);problem.addConstraint('a != b')
solutions=problem.getSolutions()
for direction in ('min','max'):
    result=optimize(problem,lambda row:row['a']*3-row['b'],direction)
    expected=(min if direction=='min' else max)(row['a']*3-row['b'] for row in solutions)
    business &= result.complete and result.score==expected and result.examined==len(solutions)
calls=[]
result=optimize(problem,lambda row:calls.append(dict(row)) or 1,max_solutions=1)
business &= len(calls)==result.examined==1 and result.complete is False and len(problem.getSolutions())==len(solutions) and not problem._constraints

print(json.dumps({'candidate_import': Path(constraint.__file__).resolve().is_relative_to(root / 'library'), 'business': bool(business)}))
