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
suite = control.SUITES['bidict']
import_root = Path(suite.get('import_root', '.'))
control._bind_source(root / 'library', import_root, cleanup, distribution=suite.get('distribution'))
sys.path.insert(0, str(root / 'library' / import_root))

import bidict
business = False
try:
    from bidict.records import to_records, from_records
    source = bidict.frozenbidict({None: 0, 'x': 2})
    document = to_records(source, encode_key=lambda key: key, encode_value=lambda value: value, codec='local')
    output = from_records(document, decode_key=lambda key: key, decode_value=lambda value: value, codec='local', cls=bidict.frozenbidict)
    business = isinstance(output, bidict.frozenbidict) and output.inverse[0] is None
    for pairs in [[['x']], [['x', 1], ['y', 1]]]:
        try:
            from_records({'schema': 1, 'codec': 'local', 'pairs': pairs}, decode_key=str, decode_value=int, codec='local')
        except ValueError:
            pass
        else:
            business = False
except ImportError:
    business = False

print(json.dumps({'candidate_import': Path(bidict.__file__).resolve().is_relative_to(root / 'library'), 'business': bool(business)}))
