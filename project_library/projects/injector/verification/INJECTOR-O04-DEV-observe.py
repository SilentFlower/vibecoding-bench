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
suite = control.SUITES['injector']
import_root = Path(suite.get('import_root', '.'))
control._bind_source(root / 'library', import_root, cleanup, distribution=suite.get('distribution'))
sys.path.insert(0, str(root / 'library' / import_root))

import injector
business=False
try:
    class Item:
        """独立活动域实例。"""
    scope_type=injector.ContextScope
    container=injector.Injector(lambda binder:binder.bind(Item,scope=scope_type));scope=container.get(scope_type)
    with scope.enter():
        first=container.get(Item);business=container.get(Item) is first
    with scope.enter():business=business and container.get(Item) is not first
except AttributeError:business=False

print(json.dumps({'candidate_import': Path(injector.__file__).resolve().is_relative_to(root / 'library'), 'business': bool(business)}))
