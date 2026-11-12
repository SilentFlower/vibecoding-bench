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
from textdistance.utils import words_combinations
business=True
f=textdistance.Levenshtein(external=False)
business &= words_combinations(lambda *items:sum(f(items[0],other) for other in items[1:]),'a b c','c b a','b c a',max_permutations=216)==0
seen=[]
try:words_combinations(lambda *items:seen.append(items) or 0,'a b','c d',max_permutations=3)
except ValueError:pass
else:business=False
business &= not seen
for value in (float('nan'),float('inf'),True):
    try:words_combinations(lambda *items:value,'a','b')
    except ValueError:pass
    else:business=False
business &= words_combinations(f,' '.join(['a']*15),'a',max_permutations=1)==28

print(json.dumps({'candidate_import': Path(textdistance.__file__).resolve().is_relative_to(root / 'library'), 'business': bool(business)}))
