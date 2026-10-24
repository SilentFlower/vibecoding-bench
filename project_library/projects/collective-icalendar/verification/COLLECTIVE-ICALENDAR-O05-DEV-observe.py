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
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
business = False
try:
    from icalendar.schedule_shift import shift_schedule
    event = icalendar.Event(); event.add('UID', 'private'); event.add('DTSTART', datetime(2026, 3, 7, 2, 30, tzinfo=ZoneInfo('America/New_York')))
    try:
        shift_schedule(event, timedelta(days=1))
    except ValueError:
        business = event.decoded('DTSTART').day == 7
    else:
        business = False
    floating = icalendar.Event(); floating.add('DTSTART', datetime(2026, 1, 1, 9))
    business &= shift_schedule(floating, timedelta(days=1)).decoded('DTSTART') == datetime(2026, 1, 2, 9)
    try:
        shift_schedule(floating, timedelta(days=1), mode='absolute')
    except ValueError:
        pass
    else:
        business = False
except ImportError:
    business = False

print(json.dumps({'candidate_import': Path(icalendar.__file__).resolve().is_relative_to(root / 'library'), 'business': bool(business)}))
