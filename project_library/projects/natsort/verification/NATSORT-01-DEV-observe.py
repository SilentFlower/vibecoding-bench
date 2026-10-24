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
suite = control.SUITES['natsort']
control._bind_source(root / 'library', Path(suite.get('import_root', '.')), cleanup, distribution=suite.get('distribution'))
import natsort
import contextlib
import io
from natsort.__main__ import main

def run(*args):
    """执行真实CLI筛选。@param args 参数。@return 结果列表。"""
    out=io.StringIO()
    with contextlib.redirect_stdout(out):main(*args)
    return out.getvalue().splitlines()

business=True
for number in (2**53,10**22):
    entries=['n'+str(number+i) for i in range(4)]
    business &= run('--exclude',str(number+1),*entries)==[entries[i] for i in (0,2,3)]
    business &= run('--reverse-filter',str(number+1),str(number+2),*entries)==[entries[i] for i in (0,3)]
business &= run('--number-type','real','--exclude','-1.5','n-1.5','n0')==['n0']

print(json.dumps({'candidate_import': Path(natsort.__file__).resolve().is_relative_to(root / 'library'), 'business': bool(business)}))
