"""在固定候选源码上运行独立业务矩阵，不调用模型或外部服务。"""
import json
import os
from pathlib import Path
root = Path(os.environ['PROJECT_CANDIDATE_ROOT']).resolve()
_bench_candidate_root = root
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
_bench_candidate_module = icalendar
business = callable(getattr(icalendar.Calendar, 'from_ical_strict', None))
if business:
    for calendar_type in [icalendar.Calendar, icalendar.LazyCalendar]:
        valid = 'BEGIN:VCALENDAR\r\nBEGIN:X-PRIVATE\r\nX-VALUE:1\r\nEND:x-private\r\nEND:vcalendar\r\n'
        business &= calendar_type.from_ical_strict(valid).name == 'VCALENDAR'
        business &= len(calendar_type.from_ical_strict(valid.encode() * 2, multiple=True)) == 2
        for raw in [
            'BEGIN:VCALENDAR\r\nBEGIN:VEVENT\r\nUID:private\r\nEND:X-OTHER\r\nEND:VCALENDAR\r\n',
            'BEGIN:VCALENDAR\r\nBEGIN:X-PRIVATE\r\nEND:VCALENDAR\r\nEND:X-PRIVATE\r\n',
            'END:VTODO\r\n', 'BEGIN:VCALENDAR\r\nBEGIN:VTODO\r\nEND:VTODO\r\n',
            valid + 'BEGIN:X-UNFINISHED\r\n']:
            try:
                calendar_type.from_ical_strict(raw)
            except ValueError:
                pass
            else:
                business = False
    legacy = 'BEGIN:VCALENDAR\r\nEND:VCALENDARD\r\n'
    business &= icalendar.Calendar.from_ical(legacy).name == 'VCALENDAR'

print(json.dumps({'candidate_import': Path(_bench_candidate_module.__file__).resolve().is_relative_to(_bench_candidate_root / 'library'), 'business': bool(business)}))
