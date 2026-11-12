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
    from chardet.transcode import transcode_bytes
    value = 'Zażółć'.encode('utf-16')
    result = transcode_bytes(value, 'utf-8')
    business = result['output'].decode('utf-8') == 'Zażółć' and result['validated_source_bytes'] == len(value)
    business &= transcode_bytes(b'', 'utf-8', source_encoding='ascii')['output'] == b''
    try:
        transcode_bytes(b'', 'utf-8')
    except ValueError:
        pass
    else:
        business = False
except ImportError:
    business = False

print(json.dumps({'candidate_import': Path(chardet.__file__).resolve().is_relative_to(root / 'library'), 'business': bool(business)}))
