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
suite = control.SUITES['natsort']
control._bind_source(root / 'library', Path(suite.get('import_root', '.')), cleanup, distribution=suite.get('distribution'))
import natsort
from natsort import natsorted, ns
from natsort.records import FieldSortSpec,multisorted
business=True
rows=[{'a':a,'b':b} for a,b in [('x2','10'),('x10','-3'),('x2','2'),('x1','3'),('x2',None)]]
fields=[FieldSortSpec(lambda row:row['a']),FieldSortSpec(lambda row:row['b'],alg=ns.REAL,reverse=True)]
result=multisorted(rows,fields)
business &= [(row['a'],row['b']) for row in result]==[('x1','3'),('x2','10'),('x2','2'),('x2',None),('x10','-3')]
business &= multisorted([],fields)==[] and multisorted([{'v':'x2'},{'v':'x10'}],[FieldSortSpec(lambda row:row['v'])])==[{'v':'x2'},{'v':'x10'}]

print(json.dumps({'candidate_import': Path(natsort.__file__).resolve().is_relative_to(root / 'library'), 'business': bool(business)}))
