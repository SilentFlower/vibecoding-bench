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
from datetime import date, datetime
business = False
try:
    from icalendar.fingerprint import calendar_fingerprint
    event = icalendar.Event(); event.add('UID', 'private'); event.add('DTSTART', date(2026, 1, 1))
    timed = icalendar.Event(); timed.add('UID', 'private'); timed.add('DTSTART', datetime(2026, 1, 1))
    business = calendar_fingerprint(event)['digest'] != calendar_fingerprint(timed)['digest']
    calendar = icalendar.Calendar(); calendar.add_component(event); calendar.add_component(event.copy(recursive=True))
    single = icalendar.Calendar(); single.add_component(event.copy(recursive=True))
    business &= calendar_fingerprint(calendar)['digest'] != calendar_fingerprint(single)['digest']
    before = event.to_ical()
    calendar_fingerprint(event)
    business &= event.to_ical() == before
except ImportError:
    business = False

print(json.dumps({'candidate_import': Path(icalendar.__file__).resolve().is_relative_to(root / 'library'), 'business': bool(business)}))
