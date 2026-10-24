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
    from chardet.validated import detect_validated
    result = detect_validated(b'private record')
    business = result['validated_whole'] and result['selected']['confidence'] == chardet.detect(b'private record')['confidence']
    denied = detect_validated(b'private record', validator=lambda text, candidate: False)
    business &= denied['selected'] is None and all(item['status'] == 'business-rejected' for item in denied['candidates'])
    empty = detect_validated(b'')
    business &= empty['selected'] is None and not empty['validated_whole']
except ImportError:
    business = False

print(json.dumps({'candidate_import': Path(chardet.__file__).resolve().is_relative_to(root / 'library'), 'business': bool(business)}))
