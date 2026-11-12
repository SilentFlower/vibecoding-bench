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
import contextlib
import io
from sqlparse.cli import create_parser
business=True
parser=create_parser()
for field in ('compact','comma_first'):
    flag='--'+field
    business &= getattr(parser.parse_args(['a.sql',flag,'FALSE']),field) is False
    business &= getattr(parser.parse_args(['a.sql',flag,'true']),field) is True
    business &= getattr(parser.parse_args(['a.sql',flag,'true',flag,'false']),field) is False
    for invalid in ('','yes','no','2'):
        with contextlib.redirect_stderr(io.StringIO()):
            try:parser.parse_args(['a.sql',flag,invalid])
            except SystemExit as error:business &= error.code==2
            else:business=False

print(json.dumps({'candidate_import': Path(sqlparse.__file__).resolve().is_relative_to(root / 'library'), 'business': bool(business)}))
