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
import pickle
from datetime import datetime
from dateutil.rrule import rrule,rruleset,DAILY
business=True
rule=rrule(DAILY,dtstart=datetime(2023,5,1),count=12,cache=True)
iterator=iter(rule);next(iterator)
restored=pickle.loads(pickle.dumps(rule))
business &= list(restored)==list(rule) and restored._cache_lock is not rule._cache_lock
values=rruleset(cache=True);values.rrule(rule);values.exrule(rrule(DAILY,dtstart=datetime(2023,5,1),count=2))
business &= list(pickle.loads(pickle.dumps(values)))==list(values)

print(json.dumps({'candidate_import': Path(dateutil.__file__).resolve().is_relative_to(root / 'library'), 'business': bool(business)}))
