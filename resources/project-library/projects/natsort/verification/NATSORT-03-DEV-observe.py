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
from natsort import natsorted, ns
from natsort.topk import natural_topk
business=True
for alg in (ns.DEFAULT,ns.REAL,ns.SIGNED):
    values=['part'+str(i) for i in (30,2,10,1,20,2)]
    for reverse in (False,True):
        for count in (0,1,3,9):
            business &= natural_topk(iter(values),count,alg=alg,reverse=reverse)==natsorted(values,alg=alg,reverse=reverse)[:count]
seen=[]
def rows():
    """记录读取全部输入但不物化选择存储。@return 值流。"""
    for i in range(1000,0,-1):
        seen.append(i)
        yield 'n'+str(i)
business &= natural_topk(rows(),2)==['n1','n2'] and len(seen)==1000

print(json.dumps({'candidate_import': Path(natsort.__file__).resolve().is_relative_to(root / 'library'), 'business': bool(business)}))
