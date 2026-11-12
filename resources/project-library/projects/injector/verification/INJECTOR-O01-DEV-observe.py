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
    class Result:
        """独立部分预设装配。"""
        @injector.inject
        def __init__(self,name:str,value:int):self.name,self.value=name,value
    container=injector.Injector(lambda binder:binder.bind(str,to='injected'))
    obj=container.get(injector.BoundKey(Result,value=injector.InstanceProvider(31)))
    business=obj.name=='injected' and obj.value==31
except injector.CallError:business=False

print(json.dumps({'candidate_import': Path(injector.__file__).resolve().is_relative_to(root / 'library'), 'business': bool(business)}))
