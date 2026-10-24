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
from sqlparse.exceptions import SQLParseError
business=True
for options in ({'keyword_case':'upper'},{'reindent':True,'indent_width':4},{'strip_comments':True},{'compact':True,'comma_first':False}):
    business &= sqlparse.format('select a,b from t -- c',strict_options=True,**options)==sqlparse.format('select a,b from t -- c',**options)
for options in ({'keywrod_case':'upper'},{'unknown':None,'keyword_cases':'upper'}):
    try:sqlparse.format('select 1',strict_options=True,**options)
    except SQLParseError as error:business &= all(key in str(error) for key in options)
    else:business=False
business &= sqlparse.formatter.validate_options({'keyword_case':'upper'},strict=True)['keyword_case']=='upper'

print(json.dumps({'candidate_import': Path(sqlparse.__file__).resolve().is_relative_to(root / 'library'), 'business': bool(business)}))
