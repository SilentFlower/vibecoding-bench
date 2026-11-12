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
suite = control.SUITES['bidict']
import_root = Path(suite.get('import_root', '.'))
control._bind_source(root / 'library', import_root, cleanup, distribution=suite.get('distribution'))
sys.path.insert(0, str(root / 'library' / import_root))

import bidict
business = False
try:
    from bidict.readonly import ReadOnlyBidictProxy
    source = bidict.bidict({None: 0, 'x': 1})
    proxy = ReadOnlyBidictProxy(source)
    inverse = proxy.inverse
    source.inverse[2] = 'y'
    business = proxy['y'] == 2 and inverse[2] == 'y' and inverse.inverse is proxy
    business &= not hasattr(proxy, 'put') and not hasattr(inverse, 'forceput')
    snapshot = proxy.copy()
    del source['x']
    business &= 'x' not in proxy and snapshot['x'] == 1
except ImportError:
    business = False

print(json.dumps({'candidate_import': Path(bidict.__file__).resolve().is_relative_to(root / 'library'), 'business': bool(business)}))
