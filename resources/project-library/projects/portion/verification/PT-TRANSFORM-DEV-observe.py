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
    source = portion.IntervalDict([(portion.closed(1, 2), ['a']), (portion.closed(4, 5), ['b'])])
    output = source.transform_values(lambda value: value + ['x'])
    business = output[1] == ['a', 'x'] and source[1] == ['a']
    business &= source.transform_values(lambda value: portion.IntervalDict.DROP).domain().empty
    failure = RuntimeError('transform')
    def fail(value):
        """保留业务异常。@param value 值。@return 不返回。"""
        raise failure
    try:
        source.transform_values(fail)
    except RuntimeError as error:
        business &= error is failure and source[1] == ['a']
    else:
        business = False
except AttributeError:
    business = False

print(json.dumps({'candidate_import': Path(portion.__file__).resolve().is_relative_to(root / 'library'), 'business': bool(business)}))
