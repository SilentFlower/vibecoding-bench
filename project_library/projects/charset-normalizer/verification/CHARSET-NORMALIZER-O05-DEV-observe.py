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
import hashlib
from charset_normalizer.models import CharsetMatch
business = False
try:
    match = CharsetMatch(b'private\r\ntext', 'ascii', 0.0, False, [])
    business = match.stable_digest(mode='raw', algorithm='sha512') == hashlib.sha512(b'private\r\ntext').hexdigest()
    business &= match.stable_digest() != CharsetMatch(b'private\ntext', 'ascii', 0.0, False, []).stable_digest()
    try:
        match.stable_digest(mode='raw', normalization='NFC')
    except ValueError:
        pass
    else:
        business = False
except AttributeError:
    business = False

print(json.dumps({'candidate_import': Path(charset_normalizer.__file__).resolve().is_relative_to(root / 'library'), 'business': bool(business)}))
