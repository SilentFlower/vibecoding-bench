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
from textdistance.retrieval import extract
business=True
choices=[(index,value) for index,value in enumerate(['ab','a','ba','','abc','ab'])]
scorer=textdistance.Levenshtein(external=False)
for k in (0,1,2,20):
    result=extract('ab',iter(choices),scorer,k=k)
    expected=sorted(choices,key=lambda item:(scorer('ab',item[1]),item[0]))[:k]
    business &= [(match.id,match.value) for match in result]==expected
for threshold in (0,1,2):
    result=extract('ab',choices,scorer,k=20,threshold=threshold)
    business &= all(match.score<=threshold for match in result)
    business &= len(result)==sum(scorer('ab',value)<=threshold for _,value in choices)

print(json.dumps({'candidate_import': Path(textdistance.__file__).resolve().is_relative_to(root / 'library'), 'business': bool(business)}))
