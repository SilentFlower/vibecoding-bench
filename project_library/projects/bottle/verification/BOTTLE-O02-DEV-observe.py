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
from tempfile import TemporaryDirectory
business = False
try:
    with TemporaryDirectory() as temporary:
        folder = Path(temporary)
        (folder / 'entry.j2').write_text('J')
        (folder / 'entry.mako').write_text('M')
        business = bottle.Jinja2Template.search('entry', [temporary]).endswith('.j2')
        business &= bottle.MakoTemplate.search('entry', [temporary]).endswith('.mako')
        business &= 'mako' not in bottle.BaseTemplate.extensions and 'jinja2' not in bottle.MakoTemplate.extensions
        one = bottle.SimpleTemplate(source='{{n}}', extensions=['private'])
        two = bottle.SimpleTemplate(source='ok')
        business &= one.render(n=7) == '7' and 'private' not in two.extensions
except (TypeError, AttributeError):
    business = False

print(json.dumps({'candidate_import': Path(bottle.__file__).resolve().is_relative_to(root / 'library'), 'business': bool(business)}))
