"""在固定候选源码上运行独立业务矩阵，不调用模型或外部服务。"""
import json
import os
from pathlib import Path
root = Path(os.environ['PROJECT_CANDIDATE_ROOT']).resolve()
from contextlib import ExitStack
from importlib.util import module_from_spec, spec_from_file_location
import sys
spec = spec_from_file_location('frozen_control', Path(__file__).with_name('native_regression.py'))
control = module_from_spec(spec)
spec.loader.exec_module(control)
cleanup = ExitStack()
suite = control.SUITES['dataset']
import_root = Path(suite.get('import_root', '.'))
control._bind_source(root / 'library', import_root, cleanup, distribution=suite.get('distribution'))
sys.path.insert(0, str(root / 'library' / import_root))

import dataset
business=False
try:
    db=dataset.connect('sqlite://');table=db['items']
    table.insert_many([{'key':'a','x':1,'y':2},{'key':'b','x':3,'y':4}])
    table.update_many([{'key':'a','x':8},{'key':'b','y':9}],['key'],chunk_size=1)
    business=table.find_one(key='a')['y']==2 and table.find_one(key='b')['x']==3
    try:table.update_many([{'key':'a','x':7}],[],chunk_size=1)
    except ValueError:pass
    else:business=False
    db.close()
except Exception as error:
    if type(error).__name__ in ('CompileError','StatementError'):business=False
    else:raise

print(json.dumps({'candidate_import': Path(dataset.__file__).resolve().is_relative_to(root / 'library'), 'business': bool(business)}))
