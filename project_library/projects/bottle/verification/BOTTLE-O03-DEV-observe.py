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
    child, target = bottle.Bottle(), bottle.Bottle()
    callback = lambda number: str(number)
    child.route('/number/<number:int>', callback=callback, name='number')
    target.merge(iter(child.routes), prefix='/service')
    route = target.routes[0]
    business = route.rule == '/service/number/<number:int>' and route.callback is callback and route.app is target
    matched, arguments = target.router.match({'PATH_INFO': '/service/number/12', 'REQUEST_METHOD': 'GET'})
    business &= matched is route and arguments == {'number': 12}
    business &= child.routes[0].app is child and child.routes[0].rule == '/number/<number:int>'
except TypeError:
    business = False

print(json.dumps({'candidate_import': Path(bottle.__file__).resolve().is_relative_to(root / 'library'), 'business': bool(business)}))
