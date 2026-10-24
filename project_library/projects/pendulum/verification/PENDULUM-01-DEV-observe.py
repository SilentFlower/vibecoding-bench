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
from datetime import timedelta
import pendulum
business=True
for days in (-4,0,8):
    a=pendulum.datetime(2023,3,1);value=pendulum.interval(a,a.add(days=days))
    delta=timedelta(days=days)
    business &= value==delta and delta==value and hash(value)==hash(delta)

print(json.dumps({'candidate_import': Path(pendulum.__file__).resolve().is_relative_to(root / 'library'), 'business': bool(business)}))
