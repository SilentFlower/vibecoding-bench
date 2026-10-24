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
suite = control.SUITES['tqdm']
control._bind_source(root / 'library', Path(suite.get('import_root', '.')), cleanup, distribution=suite.get('distribution'))
import sys
sys.path.insert(0, str(root / 'library' / suite.get('import_root', '.')))
import tqdm
import asyncio
from tqdm.asyncio import tqdm_asyncio
business=True
async def run():
    """真实未知长度任务与gather兼容矩阵。@return bool。"""
    async def work(value):await asyncio.sleep(0);return value*2
    values=[await item for item in tqdm_asyncio.as_completed((asyncio.create_task(work(value)) for value in range(5)),disable=True)]
    ordered=await tqdm_asyncio.gather(*(work(value) for value in range(3)),disable=True)
    return sorted(values)==[0,2,4,6,8] and ordered==[0,2,4]
business &= asyncio.run(run())

print(json.dumps({'candidate_import': Path(tqdm.__file__).resolve().is_relative_to(root / 'library'), 'business': bool(business)}))
