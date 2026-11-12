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
suite = control.SUITES['funcy']
import_root = Path(suite.get('import_root', '.'))
control._bind_source(root / 'library', import_root, cleanup, distribution=suite.get('distribution'))
sys.path.insert(0, str(root / 'library' / import_root))

import funcy
business=False
try:
    from funcy.async_calc import amemoize
    import asyncio
    async def run():
        calls=[]
        @amemoize(key_func=lambda x, y=0:x+y)
        async def compute(x,y=0):calls.append((x,y));return x+y
        a=await compute(1,y=2);b=await compute(2,y=1);compute.invalidate(3)
        c=await compute(3)
        return a==b==c==3 and len(calls)==2 and compute.cache_info()['pending']==0
    business=asyncio.run(run())
except ImportError:business=False

print(json.dumps({'candidate_import': Path(funcy.__file__).resolve().is_relative_to(root / 'library'), 'business': bool(business)}))
