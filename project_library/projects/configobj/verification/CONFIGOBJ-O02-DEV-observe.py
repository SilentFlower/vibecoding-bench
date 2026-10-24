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
    source=configobj.ConfigObj(['base=old','# child','[c]','v=%(base)s'])
    target=configobj.ConfigObj(['base=target']);target.merge(source,comments='incoming')
    source.comments['c'].append('changed');source['c']['v']='source only';target['base']='accepted'
    business=target['c']['v']=='accepted' and target.comments['c']==['# child'] and target['c'].main is target
except TypeError:business=False

print(json.dumps({'candidate_import': Path(configobj.__file__).resolve().is_relative_to(root / 'library'), 'business': bool(business)}))
