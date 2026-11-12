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
from io import StringIO
from datetime import datetime,timedelta
from dateutil.tz import tzical
business=True
text='BEGIN:VTIMEZONE\nTZID:Fixed\nX-URL:https://never-open.invalid\nBEGIN:STANDARD\nDTSTART:20210101T000000\nTZOFFSETFROM:-0430\nTZOFFSETTO:-0430\nX-ANY:opaque\nEND:STANDARD\nEND:VTIMEZONE'
zone=tzical(StringIO(text)).get('Fixed')
business &= datetime(2025,1,1,tzinfo=zone).utcoffset()==timedelta(hours=-4,minutes=-30)

print(json.dumps({'candidate_import': Path(dateutil.__file__).resolve().is_relative_to(root / 'library'), 'business': bool(business)}))
