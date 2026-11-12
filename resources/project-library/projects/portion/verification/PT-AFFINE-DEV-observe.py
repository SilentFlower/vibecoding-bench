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
    source = portion.openclosed(-4, -1) | portion.closedopen(2, 5)
    result = source.affine(-3, 8)
    business = result == portion.openclosed(-7, 2) | portion.closedopen(11, 20)
    business &= source == portion.openclosed(-4, -1) | portion.closedopen(2, 5)
    business &= portion.open(-portion.inf, portion.inf).affine(0, 9) == portion.singleton(9)
    for value in (float('nan'), float('inf')):
        try:
            source.affine(value)
        except ValueError:
            pass
        else:
            business = False
except AttributeError:
    business = False

print(json.dumps({'candidate_import': Path(portion.__file__).resolve().is_relative_to(root / 'library'), 'business': bool(business)}))
