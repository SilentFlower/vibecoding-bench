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
from dateutil.parser import isoparse
business=True
for year in (2014,2016,2019,2022):
    try:isoparse(str(year)+'-W53-4');business=False
    except ValueError:pass
business &= isoparse('2009W537').isocalendar()==(2009,53,7)
business &= isoparse('2019-W01-1').year==2018

print(json.dumps({'candidate_import': Path(dateutil.__file__).resolve().is_relative_to(root / 'library'), 'business': bool(business)}))
