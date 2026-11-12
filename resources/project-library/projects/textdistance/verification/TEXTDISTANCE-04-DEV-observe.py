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
from functools import lru_cache
from itertools import product
from textdistance.weighted import WeightedLevenshtein
business=True
for insertion,deletion,substitution in ((1,1,1),(0,2,0.5),(2,3,8)):
    algorithm=WeightedLevenshtein(insertion,deletion,substitution)
    def oracle(a,b):
        """独立递归穷举编辑路径。@param a 源。@param b 目标。@return 最优成本。"""
        if not a:return len(b)*insertion
        if not b:return len(a)*deletion
        return min(deletion+oracle(a[1:],b),insertion+oracle(a,b[1:]),(0 if a[0]==b[0] else substitution)+oracle(a[1:],b[1:]))
    for a,b in product(('','a','b','ab','ba','aaa'),repeat=2):
        business &= algorithm(a,b)==oracle(a,b)
        if (insertion,deletion,substitution)==(1,1,1):business &= algorithm(a,b)==textdistance.Levenshtein(external=False)(a,b)

print(json.dumps({'candidate_import': Path(textdistance.__file__).resolve().is_relative_to(root / 'library'), 'business': bool(business)}))
