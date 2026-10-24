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
    from cattrs.strategies.base64 import configure_base64
    from cattrs.preconf.json import make_converter
    converter = configure_base64(make_converter())
    for value in (b'', bytes(range(256))):
        business = converter.structure(converter.unstructure(value), bytes) == value
        if not business:
            break
    converter.register_structure_hook(bytes, lambda value, target: b'user')
    business &= converter.structure('ignored', bytes) == b'user'
except ImportError:
    business = False

print(json.dumps({'candidate_import': Path(cattrs.__file__).resolve().is_relative_to(root / 'library'), 'business': bool(business)}))
