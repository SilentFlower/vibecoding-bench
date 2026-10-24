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
    from dataset.chunked import ChunkedInsert
    db=dataset.connect('sqlite://');t=db['items'];calls=[]
    writer=ChunkedInsert(t,on_error='discard',callback=lambda rows:calls.append(len(rows)))
    try:
        with writer:writer.insert({'x':1});raise KeyError('original')
    except KeyError:pass
    writer.flush()
    business=not t.exists and calls==[] and writer.queue==[]
    for options in [{'on_error':'unknown'},{'chunksize':0}]:
        try:ChunkedInsert(t,**options)
        except ValueError:pass
        else:business=False
    db.close()
except TypeError:business=False

print(json.dumps({'candidate_import': Path(dataset.__file__).resolve().is_relative_to(root / 'library'), 'business': bool(business)}))
