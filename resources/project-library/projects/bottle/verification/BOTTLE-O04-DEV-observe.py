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
suite = control.SUITES['bottle']
import_root = Path(suite.get('import_root', '.'))
control._bind_source(root / 'library', import_root, cleanup, distribution=suite.get('distribution'))
sys.path.insert(0, str(root / 'library' / import_root))

import bottle
business = False
try:
    value = bottle.BaseResponse(headers={'Content-Type': 'application/json; profile="a;b"; charset="utf-8"; Charset=ascii'})
    value.charset = 'utf-16'
    business = value.charset == 'utf-16' and 'profile=' in value.content_type and 'a;b' in value.content_type
    business &= value.content_type.lower().count('charset=') == 1
    plain = bottle.BaseResponse()
    plain.charset = 'ascii'
    business &= plain.charset == 'ascii'
    before = plain.content_type
    try:
        plain.charset = ''
    except ValueError:
        pass
    else:
        business = False
    business &= plain.content_type == before
except AttributeError:
    business = False

print(json.dumps({'candidate_import': Path(bottle.__file__).resolve().is_relative_to(root / 'library'), 'business': bool(business)}))
