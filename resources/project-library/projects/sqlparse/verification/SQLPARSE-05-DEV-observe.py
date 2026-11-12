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
from sqlparse.sql import Token
from sqlparse import tokens as T
business=True
for kind,value in ((T.Name,'Products'),(T.Keyword,'select'),(T.Literal.String.Symbol,'"Name"')):
    token=Token(kind,value);before=(token.value,token.normalized)
    business &= token.match(kind,value,case_sensitive=True)
    business &= token.match(kind,value.swapcase(),case_sensitive=False)
    business &= token.match(kind,None,case_sensitive=True)
    business &= not token.match(T.Error,value,case_sensitive=False)
    business &= (token.value,token.normalized)==before
business &= Token(T.Keyword,'select').match(T.Keyword,'SELECT')
business &= not Token(T.Name,'Products').match(T.Name,'products')

print(json.dumps({'candidate_import': Path(sqlparse.__file__).resolve().is_relative_to(root / 'library'), 'business': bool(business)}))
