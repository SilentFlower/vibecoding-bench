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
import pendulum
business=True
for value in (pendulum.datetime(2025,11,2,12,tz='America/New_York'),pendulum.datetime(2024,4,7,12,tz='Australia/Lord_Howe')):
    business &= value-pendulum.duration(days=1,hours=1)==value.subtract(days=1,hours=1)
value=pendulum.datetime(2024,3,31,8)
business &= value-pendulum.duration(months=1,days=2)==value.subtract(months=1,days=2)

print(json.dumps({'candidate_import': Path(pendulum.__file__).resolve().is_relative_to(root / 'library'), 'business': bool(business)}))
