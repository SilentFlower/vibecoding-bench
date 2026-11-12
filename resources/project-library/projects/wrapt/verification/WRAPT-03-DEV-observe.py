"""独立业务验收，只读取当前候选，不联网或调用模型。"""
import json
import os
from pathlib import Path
root = Path(os.environ['PROJECT_CANDIDATE_ROOT']).resolve()
from contextlib import ExitStack
from importlib.util import module_from_spec, spec_from_file_location
spec = spec_from_file_location('frozen_native_control', Path(__file__).with_name('native_regression.py'))
control = module_from_spec(spec)
spec.loader.exec_module(control)
cleanup = ExitStack()
suite = control.SUITES['wrapt']
control._bind_source(root / 'library', Path(suite.get('import_root', '.')), cleanup, distribution=suite.get('distribution'))
import sys
sys.path.insert(0, str(root / 'library' / suite.get('import_root', '.')))
import wrapt
import asyncio
from wrapt.async_cache import async_lru_cache
business=True
calls=[]
@async_lru_cache(maxsize=1)
async def f(x):calls.append(x);return x+1
async def run():
    a=await f(1);b=await f(2);c=await f(1)
    return (a,b,c)==(2,3,2) and f.cache_info().currsize==1 and calls==[1,2,1]
business &= asyncio.run(run())

print(json.dumps({'candidate_import': Path(wrapt.__file__).resolve().is_relative_to(root / 'library'), 'business': bool(business)}))
