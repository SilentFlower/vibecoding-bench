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
from copy import deepcopy
source=configobj.ConfigObj(['x=old','[one]','value=%(x)s','[[two]]','ref=%(x)s'])
clone=deepcopy(source);clone['x']='new'
business=clone['one']['two']['ref']=='new' and source['one']['value']=='old' and clone['one']['two'].main is clone and clone.parent is clone

print(json.dumps({'candidate_import': Path(configobj.__file__).resolve().is_relative_to(root / 'library'), 'business': bool(business)}))
