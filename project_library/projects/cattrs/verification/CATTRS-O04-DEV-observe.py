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
suite = control.SUITES['cattrs']
import_root = Path(suite.get('import_root', '.'))
control._bind_source(root / 'library', import_root, cleanup, distribution=suite.get('distribution'))
sys.path.insert(0, str(root / 'library' / import_root))

import cattrs
business = False
try:
    from cattrs.strategies.strict import configure_strict_primitives
    converter = configure_strict_primitives(cattrs.Converter())
    business = converter.structure([1, 2], list[int]) == [1, 2]
    try:
        converter.structure([1, True], list[int])
    except Exception:
        pass
    else:
        business = False
    try:
        converter.structure(1, float)
    except TypeError:
        pass
    else:
        business = False
    permissive = configure_strict_primitives(cattrs.Converter(), finite_float=False)
    business &= permissive.structure(float('inf'), float) == float('inf')
except ImportError:
    business = False

print(json.dumps({'candidate_import': Path(cattrs.__file__).resolve().is_relative_to(root / 'library'), 'business': bool(business)}))
