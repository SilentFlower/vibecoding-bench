"""在固定候选源码上运行独立业务矩阵，不调用模型或外部服务。"""
import json
import os
from pathlib import Path
root = Path(os.environ['PROJECT_CANDIDATE_ROOT']).resolve()
from contextlib import ExitStack
from importlib.util import module_from_spec, spec_from_file_location
spec = spec_from_file_location('frozen_control', Path(__file__).with_name('native_regression.py'))
control = module_from_spec(spec)
spec.loader.exec_module(control)
cleanup = ExitStack()
control._bind_source(root / 'library', Path('.'), cleanup, distribution=control.SUITES['portion']['distribution'])

import portion
business = False
try:
    source = portion.closed(0, 1) | portion.openclosed(3, 4) | portion.closed(9, 10)
    result, gaps = source.coalesce(2, report=True)
    business = result == portion.closed(0, 4) | portion.closed(9, 10)
    business &= portion.Interval(*gaps) == result - source and len(source) == 3
    seen = []
    custom = source.coalesce(1, metric=lambda lower, upper: seen.append((lower, upper)) or (upper - lower) / 2)
    business &= len(custom) == 2 and len(seen) == 2
    business &= portion.empty().coalesce(0).empty
    for invalid in (-1, float('nan')):
        try:
            source.coalesce(invalid)
        except ValueError:
            pass
        else:
            business = False
except AttributeError:
    business = False

print(json.dumps({'candidate_import': Path(portion.__file__).resolve().is_relative_to(root / 'library'), 'business': bool(business)}))
