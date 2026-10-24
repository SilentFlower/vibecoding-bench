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
from datetime import date
business = False
try:
    source = portion.openclosed(-5, 0) | portion.closedopen(4, 9)
    for ownership in ('left', 'right'):
        parts = source.split(iter([-9, -2, 0, 6, 6, 99]), ownership=ownership)
        business = portion.Interval(*parts) == source and len(parts) == 4
        business &= all((left & right).empty for index, left in enumerate(parts) for right in parts[index + 1:])
        if not business:
            break
    dated = portion.closedopen(date(2026, 1, 1), date(2026, 1, 5))
    business &= len(dated.split([date(2026, 1, 3)])) == 2
    try:
        source.split([], ownership='both')
    except ValueError:
        pass
    else:
        business = False
except AttributeError:
    business = False

print(json.dumps({'candidate_import': Path(portion.__file__).resolve().is_relative_to(root / 'library'), 'business': bool(business)}))
