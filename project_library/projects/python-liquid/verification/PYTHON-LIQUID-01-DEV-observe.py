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
suite = control.SUITES['python-liquid']
control._bind_source(root / 'library', Path(suite.get('import_root', '.')), cleanup, distribution=suite.get('distribution'))
import sys
sys.path.insert(0, str(root / 'library' / suite.get('import_root', '.')))
import liquid
import asyncio
from liquid import Environment,CachingDictLoader
business=True
loader=CachingDictLoader({'x':'{{amount}}'},namespace_key='tenant');env=Environment(loader=loader)
async def run():
    first=await loader.load_async(env,'x',tenant='a')
    second=await loader.load_async(env,'x',tenant='a')
    third=loader.load(env,'x',tenant='b')
    return first is second and first is not third and first.render(amount=4)=='4'
business &= asyncio.run(run())

print(json.dumps({'candidate_import': Path(liquid.__file__).resolve().is_relative_to(root / 'library'), 'business': bool(business)}))
