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
    class Config(injector.Module):
        """独立模块依赖装配。"""
        @injector.inject
        def __init__(self,value:str):self.value=value
        def configure(self,binder):binder.bind(bytes,to=self.value.encode())
    parent=injector.Injector(lambda binder:binder.bind(str,to='from-parent'));child=parent.create_child_injector()
    child.binder.install(Config)
    business=child.get(bytes)==b'from-parent'
except TypeError:business=False

print(json.dumps({'candidate_import': Path(injector.__file__).resolve().is_relative_to(root / 'library'), 'business': bool(business)}))
