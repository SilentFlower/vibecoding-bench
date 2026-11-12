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
suite = control.SUITES['chardet']
import_root = Path(suite.get('import_root', '.'))
control._bind_source(root / 'library', import_root, cleanup, distribution=suite.get('distribution'))
sys.path.insert(0, str(root / 'library' / import_root))

import chardet
business = False
try:
    from chardet.batch import detect_many
    seen = []
    def records():
        """按需产生真实记录。@return 迭代器。"""
        for index in range(3):
            seen.append(index)
            yield index, b'private'
    stream = detect_many(records())
    first = next(stream)
    business = first['id'] == 0 and first['index'] == 1 and seen == [0]
    stream.close()
    business &= seen == [0]
    rows = list(detect_many([('bad-shape',), ('empty', b'')]))
    business &= rows[0]['error'] == 'TypeError' and rows[1]['result']['encoding'] is None
except ImportError:
    business = False

print(json.dumps({'candidate_import': Path(chardet.__file__).resolve().is_relative_to(root / 'library'), 'business': bool(business)}))
