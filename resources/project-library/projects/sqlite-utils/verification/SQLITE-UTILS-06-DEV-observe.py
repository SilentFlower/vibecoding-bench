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
import io,csv
from sqlite_utils import Database
business=True
db=Database(memory=True);table=db['a"b'].insert_all([{'x"y':'one','v':1},{'x"y':'two','v':2}]);out=io.StringIO()
business &= table.export_csv(out,columns=['x"y'],where='v > ?',where_args=[1])==1
business &= list(csv.reader(io.StringIO(out.getvalue())))==[['x"y'],['two']] and not out.closed
db.close()

print(json.dumps({'candidate_import': Path(sqlite_utils.__file__).resolve().is_relative_to(root / 'library'), 'business': bool(business)}))
