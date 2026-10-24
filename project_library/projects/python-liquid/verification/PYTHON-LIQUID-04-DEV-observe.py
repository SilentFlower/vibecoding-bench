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
from liquid.record_rendering import render_records,render_records_async
business=True
t=Environment().from_string('{% cycle "a", "b" %}:{{n}}')
rows=((str(n),{'n':n}) for n in range(3));values=list(render_records(t,rows))
business &= [v.output for v in values]==['a:0','a:1','a:2']
async def run():return [v.output async for v in render_records_async(t,[('x',{'n':7})])]==['a:7']
business &= asyncio.run(run())

print(json.dumps({'candidate_import': Path(liquid.__file__).resolve().is_relative_to(root / 'library'), 'business': bool(business)}))
