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
suite = control.SUITES['pendulum']
control._bind_source(root / 'library', Path(suite.get('import_root', '.')), cleanup, distribution=suite.get('distribution'))
import sys
sys.path.insert(0, str(root / 'library' / suite.get('import_root', '.')))
import pendulum
import pickle,copy
import pendulum
from pendulum.duration import Duration
business=True
value=Duration(months=-2,days=4,seconds=5)
for restored in (copy.copy(value),pickle.loads(pickle.dumps(value))):
    business &= restored._signature==value._signature and pendulum.datetime(2025,5,31)+restored==pendulum.datetime(2025,5,31)+value

print(json.dumps({'candidate_import': Path(pendulum.__file__).resolve().is_relative_to(root / 'library'), 'business': bool(business)}))
