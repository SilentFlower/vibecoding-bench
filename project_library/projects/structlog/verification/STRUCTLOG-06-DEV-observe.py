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
suite = control.SUITES['structlog']
control._bind_source(root / 'library', Path(suite.get('import_root', '.')), cleanup, distribution=suite.get('distribution'))
import sys
sys.path.insert(0, str(root / 'library' / suite.get('import_root', '.')))
import structlog
from datetime import datetime,timezone,timedelta
from structlog.processors import ZonedTimeStamper
business=True
value=datetime(2024,2,29,1,2,3,999999,tzinfo=timezone.utc)
stamp=ZonedTimeStamper(timezone(timedelta(hours=-4)),timespec='microseconds',clock=lambda:value)
business &= stamp(None,'event',{})['timestamp']=='2024-02-28T21:02:03.999999-04:00'

print(json.dumps({'candidate_import': Path(structlog.__file__).resolve().is_relative_to(root / 'library'), 'business': bool(business)}))
