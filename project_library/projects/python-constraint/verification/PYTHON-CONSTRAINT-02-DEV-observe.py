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
problem=Problem();problem.addVariables(['a','b','c'],[1,2]);problem.addConstraint(lambda a,b,c:a+b==c,['a','b','c'])
solutions=problem.getSolutions()
for order in ([],['a'],['c','a'],['c','b','a']):
    business &= problem.getSolutionsOrderedList(order)==[tuple(item[key] for key in order) for item in solutions]
for order in (['missing'],['a','a']):
    try:problem.getSolutionsOrderedList(order)
    except ValueError:pass
    else:business=False

print(json.dumps({'candidate_import': Path(constraint.__file__).resolve().is_relative_to(root / 'library'), 'business': bool(business)}))
