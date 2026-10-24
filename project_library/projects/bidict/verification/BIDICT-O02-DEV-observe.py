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
    from bidict.select import select
    source = bidict.OrderedBidict([('x', 10), ('y', 20), ('z', 30)])
    calls = []
    output = select(source, values=iter([10, 30]), predicate=lambda key, value: calls.append(key) or True)
    business = list(output) == ['x', 'z'] and calls == ['x', 'z'] and output.inverse[30] == 'z'
    failure = RuntimeError('predicate')
    def fail(key, value):
        """拒绝业务行。@param key 键。@param value 值。@return 不返回。"""
        raise failure
    try:
        select(source, predicate=fail)
    except RuntimeError as error:
        business &= error is failure and len(source) == 3
    else:
        business = False
except ImportError:
    business = False

print(json.dumps({'candidate_import': Path(bidict.__file__).resolve().is_relative_to(root / 'library'), 'business': bool(business)}))
