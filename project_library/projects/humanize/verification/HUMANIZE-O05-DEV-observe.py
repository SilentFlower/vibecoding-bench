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
suite = control.SUITES['humanize']
import_root = Path(suite.get('import_root', '.'))
control._bind_source(root / 'library', import_root, cleanup, distribution=suite.get('distribution'))
sys.path.insert(0, str(root / 'library' / import_root))

import humanize
business=False
try:
    from humanize.calendar import calendar_interval
    from datetime import date
    result=calendar_interval(date(2023,1,1),date(2023,1,30))
    reverse=calendar_interval(date(2023,1,30),date(2023,1,1))
    business=(result.months,result.days,result.sign)==(0,29,1) and reverse.days==29 and reverse.sign==-1
except ImportError:business=False

print(json.dumps({'candidate_import': Path(humanize.__file__).resolve().is_relative_to(_bench_candidate_root / 'library'), 'business': bool(business)}))
