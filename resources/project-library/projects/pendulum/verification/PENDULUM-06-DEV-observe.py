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
from datetime import date
from pendulum.business import BusinessCalendar
import pendulum
business=True
calendar=BusinessCalendar({date(2024,12,31)},weekend={4,5})
start=pendulum.date(2024,12,30)
business &= calendar.add_business_days(start,1)==pendulum.date(2025,1,1)
business &= calendar.next_business_day(pendulum.date(2025,1,1),True)==pendulum.date(2025,1,1)
business &= calendar.count(pendulum.date(2025,1,1),pendulum.date(2025,1,1))==0

print(json.dumps({'candidate_import': Path(pendulum.__file__).resolve().is_relative_to(root / 'library'), 'business': bool(business)}))
