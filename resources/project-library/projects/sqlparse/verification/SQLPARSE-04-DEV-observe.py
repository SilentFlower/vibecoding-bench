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
suite = control.SUITES['sqlparse']
control._bind_source(root / 'library', Path(suite.get('import_root', '.')), cleanup, distribution=suite.get('distribution'))
import sys
sys.path.insert(0, str(root / 'library' / suite.get('import_root', '.')))
import sqlparse
import hashlib
from sqlparse.fingerprint import fingerprint
business=True
queries=[("select x from t where a=1 and b='v'","SELECT x FROM t WHERE a=2 and b='z'"),("select x from t where a in (1,2)","select x from t where a IN (3,4)")]
for left,right in queries:
    business &= fingerprint(left)==fingerprint(right)
    business &= fingerprint(left,digest=True)==hashlib.sha256(fingerprint(left).encode()).hexdigest()
business &= fingerprint('select "a.b", :x from t')=='SELECT "a.b" , :x FROM t'
business &= fingerprint('-- only comment\n')==''

print(json.dumps({'candidate_import': Path(sqlparse.__file__).resolve().is_relative_to(root / 'library'), 'business': bool(business)}))
