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
from constraint import Problem
business=True
problem=Problem();problem.addVariables(['x','y'],[0,1]);problem.addConstraint(['x != y','x+y==1'])
for index in range(10):
    business &= len(problem.getSolutions())==2 and len(problem._constraints)==0 and len(problem._str_constraints)==2
problem.addVariable('z',[9,10]);business &= len(problem.getSolutions())==4 and not problem._constraints
problem.reset();problem.addVariable('z',[3]);business &= problem.getSolutions()==[{'z':3}]

print(json.dumps({'candidate_import': Path(constraint.__file__).resolve().is_relative_to(root / 'library'), 'business': bool(business)}))
