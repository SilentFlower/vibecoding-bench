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
    import json
    app = bottle.Bottle()
    class Plugin:
        """只公开稳定插件名。"""
        name = 'private-plugin'
    app.route('/v/<path:path>', callback=lambda path: path, apply=[Plugin()], secret='hidden-value')
    before = list(app.routes)
    rows = app.inspect_routes()
    business = rows[0]['plugins'] == ['private-plugin'] and rows[0]['filters'] == ['path']
    business &= rows[0]['owner'] == 'current' and 'hidden-value' not in json.dumps(rows) and app.routes == before
    business &= bottle.Bottle().inspect_routes() == []
    cloned = bottle.Bottle()
    cloned.merge(app, prefix='/clone')
    business &= cloned.inspect_routes()[0]['owner'] == 'current' and cloned.inspect_routes()[0]['rule'] == '/clone/v/<path:path>'
except AttributeError:
    business = False

print(json.dumps({'candidate_import': Path(bottle.__file__).resolve().is_relative_to(root / 'library'), 'business': bool(business)}))
