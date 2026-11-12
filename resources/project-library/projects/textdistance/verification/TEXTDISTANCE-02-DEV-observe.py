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
business=True
for cls in (textdistance.LCSSeq,textdistance.LCSStr):
    for size in (0,1,20,199,200,205):
        left='x'*size+'abcd';right='yabcd'
        expected=[('a','b'),('b','c'),('c','d')]
        business &= cls(qval=2,external=False)(left,right)==expected
        business &= cls(qval=2,external=False).similarity(left,right)==3
    business &= cls(qval=None,external=False)('a b','a b','a x b')==(['a','b'] if cls is textdistance.LCSSeq else ['a'])
    business &= cls(qval=2,external=False)('abc')==[('a','b'),('b','c')]
business &= textdistance.LCSSeq(qval=None,external=False)('a a b','a b','a b')==['a','b']

print(json.dumps({'candidate_import': Path(textdistance.__file__).resolve().is_relative_to(root / 'library'), 'business': bool(business)}))
