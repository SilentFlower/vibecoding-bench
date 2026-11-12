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
a=pendulum.date(2024,2,27);b=pendulum.date(2024,3,2)
value=pendulum.interval(a,b)
business &= list(value.range('days',closed='neither'))==[pendulum.date(2024,2,28),pendulum.date(2024,2,29),pendulum.date(2024,3,1)]
business &= list(value.range('days',amount=2,limit=2))==[a,pendulum.date(2024,2,29)]

print(json.dumps({'candidate_import': Path(pendulum.__file__).resolve().is_relative_to(root / 'library'), 'business': bool(business)}))
