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
from decimal import Decimal
business = False
try:
    from cattrs.strategies.decimal import configure_decimal
    from cattrs.preconf.json import make_converter
    converter = make_converter()
    business = configure_decimal(converter) is converter
    for raw in ['19.99', '1E-30', '-0.000']:
        value = converter.structure(raw, Decimal)
        business &= converter.unstructure(value) == str(Decimal(raw))
    try:
        converter.structure(True, Decimal)
    except TypeError:
        pass
    else:
        business = False
except ImportError:
    business = False

print(json.dumps({'candidate_import': Path(cattrs.__file__).resolve().is_relative_to(root / 'library'), 'business': bool(business)}))
