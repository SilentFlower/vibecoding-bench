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
suite = control.SUITES['sqlite-utils']
control._bind_source(root / 'library', Path(suite.get('import_root', '.')), cleanup)
import sys
sys.path.insert(0, str(root / 'library' / suite.get('import_root', '.')))
import sqlite_utils
import io
from sqlite_utils.utils import rows_from_file
business=True
for text in ('value\nxxx\nyyy\n','address\nhttps://abc.test:8443/home\nhttps://xyz.test:9443/end\n'):
    rows,_=rows_from_file(io.BytesIO(text.encode()));values=list(rows)
    business &= len(values)==2 and all(len(row)==1 for row in values)

print(json.dumps({'candidate_import': Path(sqlite_utils.__file__).resolve().is_relative_to(root / 'library'), 'business': bool(business)}))
