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
suite = control.SUITES['python-dateutil']
control._bind_source(root / 'library', Path(suite.get('import_root', '.')), cleanup, distribution=suite.get('distribution'))
import sys
sys.path.insert(0, str(root / 'library' / suite.get('import_root', '.')))
import dateutil
from datetime import datetime
from dateutil.rrule import rrule,MONTHLY,TU,SA
business=True
options=dict(freq=MONTHLY,dtstart=datetime(2024,2,1),byweekday=(TU,SA(1)),count=6)
expected=[datetime(2024,2,3),datetime(2024,2,6),datetime(2024,2,13),datetime(2024,2,20),datetime(2024,2,27),datetime(2024,3,2)]
business &= list(rrule(**options))==expected and list(rrule(cache=True,**options))==expected
business &= list(rrule(MONTHLY,dtstart=datetime(2024,2,1),byweekday=SA(1),count=1))==[datetime(2024,2,3)]

print(json.dumps({'candidate_import': Path(dateutil.__file__).resolve().is_relative_to(root / 'library'), 'business': bool(business)}))
