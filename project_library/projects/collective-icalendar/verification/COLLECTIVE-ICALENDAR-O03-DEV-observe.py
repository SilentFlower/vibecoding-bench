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
business = False
try:
    from icalendar.attendee_update import upsert_attendee, remove_attendee
    from icalendar.prop.cal_address import vCalAddress
    event = icalendar.Event()
    event.attendees = [vCalAddress('urn:person:1', params={'DELEGATED-TO': ['mailto:a@x', 'mailto:b@x']})]
    result = upsert_attendee(event, 'urn:person:1', parameters={'ROLE': 'CHAIR'})
    business = result.attendees[0].params['DELEGATED-TO'] == ['mailto:a@x', 'mailto:b@x'] and 'ROLE' not in event.attendees[0].params
    untouched = remove_attendee(event, 'urn:missing')
    business &= untouched == event and untouched is not event
    try:
        remove_attendee(event, 'urn:missing', strict=True)
    except ValueError:
        pass
    else:
        business = False
except ImportError:
    business = False

print(json.dumps({'candidate_import': Path(icalendar.__file__).resolve().is_relative_to(root / 'library'), 'business': bool(business)}))
