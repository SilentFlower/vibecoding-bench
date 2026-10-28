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
from liquid import Environment
from liquid.versioned_loader import VersionedDictLoader
business=True
loader=VersionedDictLoader({'x':'old','y':'y'},capacity=1);env=Environment(loader=loader)
snapshot=loader.snapshot();first=env.get_template('x');env.get_template('y')
business &= len(loader._cache)==1
loader.update('x','new');business &= snapshot['x']=='old' and first.render()=='old'
async def run():return (await env.get_template_async('x')).render()=='new'
business &= asyncio.run(run())

print(json.dumps({'candidate_import': Path(liquid.__file__).resolve().is_relative_to(root / 'library'), 'business': bool(business)}))
