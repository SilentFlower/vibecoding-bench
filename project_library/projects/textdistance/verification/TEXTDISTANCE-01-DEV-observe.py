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
suite = control.SUITES['textdistance']
control._bind_source(root / 'library', Path(suite.get('import_root', '.')), cleanup, distribution=suite.get('distribution'))
import sys
sys.path.insert(0, str(root / 'library' / suite.get('import_root', '.')))
import textdistance
from itertools import product
business=True
same=lambda *items:len({item.casefold() for item in items})==1
algorithm=textdistance.LCSSeq(test_func=same,external=False)
def oracle(a,b):
    """独立穷举首输入子序列长度。@param a 首输入。@param b 次输入。@return 最优长度。"""
    best=0
    for mask in range(1<<len(a)):
        selected=''.join(value for index,value in enumerate(a) if mask>>index&1)
        cursor=iter(b)
        if all(any(same(item,other) for other in cursor) for item in selected):best=max(best,len(selected))
    return best
for a,b in product(('','a','A','bA','AbC','AaB'),repeat=2):
    result=algorithm(a,b)
    business &= len(result)==oracle(a,b)
business &= algorithm('Aa','aA','AA')=='Aa'

print(json.dumps({'candidate_import': Path(textdistance.__file__).resolve().is_relative_to(root / 'library'), 'business': bool(business)}))
