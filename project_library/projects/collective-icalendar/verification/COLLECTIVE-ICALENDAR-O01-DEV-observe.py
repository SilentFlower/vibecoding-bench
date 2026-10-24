"""在固定候选源码上运行独立业务矩阵，不调用模型或外部服务。"""
import json
import os
from pathlib import Path
root = Path(os.environ['PROJECT_CANDIDATE_ROOT']).resolve()
from contextlib import ExitStack
from importlib.util import module_from_spec, spec_from_file_location
import sys
spec = spec_from_file_location('frozen_control', Path(__file__).with_name('native_regression.py'))
control = module_from_spec(spec)
spec.loader.exec_module(control)
cleanup = ExitStack()
suite = control.SUITES['collective-icalendar']
import_root = Path(suite.get('import_root', '.'))
control._bind_source(root / 'library', import_root, cleanup, distribution=suite.get('distribution'))
sys.path.insert(0, str(root / 'library' / import_root))

import icalendar
from datetime import date, timedelta
from icalendar.cli import view
business = True
for start in [date(2024, 2, 28), date(2026, 12, 31)]:
    event = icalendar.Event()
    event.add('dtstart', start)
    rendered = view(event)
    business &= (start + timedelta(days=1)).strftime('%c') in rendered and str(event.duration) in rendered
event = icalendar.Event(); event.add('dtstart', date(2026, 1, 1)); event.add('dtend', date(2026, 1, 5))
business &= '4 days' in view(event)

print(json.dumps({'candidate_import': Path(icalendar.__file__).resolve().is_relative_to(root / 'library'), 'business': bool(business)}))
