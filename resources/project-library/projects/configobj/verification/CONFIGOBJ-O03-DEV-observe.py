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
suite = control.SUITES['configobj']
import_root = Path(suite.get('import_root', '.'))
control._bind_source(root / 'library', import_root, cleanup, distribution=suite.get('distribution'))
sys.path.insert(0, str(root / 'library' / import_root))

import configobj
business=False
try:
    import tempfile
    from pathlib import Path
    with tempfile.TemporaryDirectory() as directory:
        path=Path(directory)/'app.ini';path.write_text('x=old\n')
        config=configobj.ConfigObj({'x':'new'});config.filename=str(path);config.write_atomic()
        business=configobj.ConfigObj(str(path))['x']=='new' and not list(path.parent.glob('.*.tmp')) and config.filename==str(path)
        config['x']='中文';config.encoding='ascii'
        try:config.write_atomic()
        except UnicodeError:pass
        else:business=False
        business=business and configobj.ConfigObj(str(path))['x']=='new'
except AttributeError:business=False

print(json.dumps({'candidate_import': Path(configobj.__file__).resolve().is_relative_to(root / 'library'), 'business': bool(business)}))
