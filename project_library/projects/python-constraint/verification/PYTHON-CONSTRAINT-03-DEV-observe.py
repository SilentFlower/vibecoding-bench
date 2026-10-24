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
from constraint import Problem,Domain
business=True
class MarkedDomain(Domain):
    """业务Domain子类必须保留。"""
problem=Problem();problem.addVariables([('a',1),('b',2)],MarkedDomain([1,2]))
business &= all(isinstance(domain,MarkedDomain) for domain in problem._variables.values()) and len(problem.getSolutions())==4
def broken():
    """模拟一次性数据源中途失败。@return 迭代器。"""
    yield 1
    raise RuntimeError('source failed')
before=set(problem._variables)
try:problem.addVariables(['x','y'],broken())
except RuntimeError:pass
else:business=False
business &= set(problem._variables)==before
problem.addConstraint(lambda a:a==1,[('a',1)])
for index in range(3):business &= len(problem.getSolutions())==2 and list(problem._variables[('a',1)])==[1,2]

print(json.dumps({'candidate_import': Path(constraint.__file__).resolve().is_relative_to(root / 'library'), 'business': bool(business)}))
