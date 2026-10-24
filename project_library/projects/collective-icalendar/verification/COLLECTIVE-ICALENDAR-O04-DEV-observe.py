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
from datetime import datetime, timezone
business = False
try:
    from icalendar.todo_transition import transition_todo
    source = icalendar.Todo(); source.add('UID', 'private'); source.add('SEQUENCE', 5)
    first = transition_todo(source, 'complete', completed_at=datetime(2030, 1, 1, tzinfo=timezone.utc))
    reopened = transition_todo(first, 'reopen')
    business = str(reopened['STATUS']) == 'NEEDS-ACTION' and int(reopened['PERCENT-COMPLETE']) == 0 and 'COMPLETED' not in reopened
    business &= int(first['SEQUENCE']) == 5 and int(source['SEQUENCE']) == 5 and str(reopened['UID']) == 'private'
    business &= icalendar.Todo.from_ical(first.to_ical()).decoded('COMPLETED') == datetime(2030, 1, 1, tzinfo=timezone.utc)
except ImportError:
    business = False

print(json.dumps({'candidate_import': Path(icalendar.__file__).resolve().is_relative_to(root / 'library'), 'business': bool(business)}))
