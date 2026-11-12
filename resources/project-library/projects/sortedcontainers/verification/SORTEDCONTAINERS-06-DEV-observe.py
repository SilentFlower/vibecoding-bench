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
suite = control.SUITES['sortedcontainers']
control._bind_source(root / 'library', Path(suite.get('import_root', '.')), cleanup, distribution=suite.get('distribution'))
import sys
sys.path.insert(0, str(root / 'library' / suite.get('import_root', '.')))
import sortedcontainers
from sortedcontainers import SortedDict
business=True
source=SortedDict({x:x*x for x in range(6)})
business &= list(source.irange_items(None,3,(True,False),True))==[(2,4),(1,1),(0,0)]
business &= list(source.irange_values(4,None))==[16,25]
business &= list(source)==list(range(6))

print(json.dumps({'candidate_import': Path(sortedcontainers.__file__).resolve().is_relative_to(root / 'library'), 'business': bool(business)}))
