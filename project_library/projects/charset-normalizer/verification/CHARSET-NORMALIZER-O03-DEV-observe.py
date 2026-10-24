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
suite = control.SUITES['charset-normalizer']
import_root = Path(suite.get('import_root', '.'))
control._bind_source(root / 'library', import_root, cleanup, distribution=suite.get('distribution'))
sys.path.insert(0, str(root / 'library' / import_root))

import charset_normalizer
from charset_normalizer.models import CharsetMatch
business = False
try:
    match = CharsetMatch('café界'.encode('utf-8'), 'utf_8', 0.0, False, [])
    result = match.transcode('latin-1', errors='replace')
    business = result['output'] == b'caf\xe9?' and result['unencodable_codepoints'] == 1
    business &= match.transcode('utf-8')['output'] == 'café界'.encode('utf-8')
    business &= CharsetMatch(b'', 'ascii', 0.0, False, []).transcode()['output'] == b''
    try:
        match.transcode(errors='unknown')
    except ValueError:
        pass
    else:
        business = False
except AttributeError:
    business = False

print(json.dumps({'candidate_import': Path(charset_normalizer.__file__).resolve().is_relative_to(root / 'library'), 'business': bool(business)}))
