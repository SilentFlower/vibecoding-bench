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
    from bidict.transform import transform_items
    source = bidict.OrderedBidict([('b', 2), ('a', 1)])
    output = transform_items(source, value_fn=lambda value: ('v', value))
    business = list(output) == ['b', 'a'] and output.inverse[('v', 1)] == 'a'
    failure = RuntimeError('business transform')
    def fail(value):
        """失败转换。@param value 输入。@return 不返回。"""
        raise failure
    try:
        transform_items(source, value_fn=fail)
    except RuntimeError as error:
        business &= error is failure and source['b'] == 2
    else:
        business = False
except ImportError:
    business = False

print(json.dumps({'candidate_import': Path(bidict.__file__).resolve().is_relative_to(root / 'library'), 'business': bool(business)}))
