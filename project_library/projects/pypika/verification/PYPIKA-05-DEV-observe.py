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
suite = control.SUITES['pypika']
control._bind_source(root / 'library', Path(suite.get('import_root', '.')), cleanup, distribution=suite.get('distribution'))
import sys
sys.path.insert(0, str(root / 'library' / suite.get('import_root', '.')))
import pypika
import sqlite3
from pypika import Query,QmarkParameter
from pypika.terms import Function
from pypika.functions import Coalesce
business=True
parameter=QmarkParameter();query=Query.select(Function('LENGTH',Coalesce(None,'hello')))
sql=query.get_sql(parameter=parameter)
business &= sql=='SELECT LENGTH(COALESCE(null,?))' and parameter.get_parameters()==['hello']
with sqlite3.connect(':memory:') as connection:
    business &= connection.execute(sql,parameter.get_parameters()).fetchone()==(5,)
business &= Query.select(Function('ABS',-4)).get_sql()=='SELECT ABS(-4)'

print(json.dumps({'candidate_import': Path(pypika.__file__).resolve().is_relative_to(root / 'library'), 'business': bool(business)}))
