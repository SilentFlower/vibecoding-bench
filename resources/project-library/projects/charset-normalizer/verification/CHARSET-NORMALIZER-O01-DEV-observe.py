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
business = False
try:
    from charset_normalizer.buffers import from_buffer
    from charset_normalizer.models import CharsetMatch
    source = bytearray(b'private ascii')
    match = CharsetMatch(source, 'ascii', 0.0, False, [])
    source.clear()
    business = match.raw == b'private ascii' and str(match) == 'private ascii'
    view = memoryview(b'bytes')
    result = from_buffer(view)
    business &= result['nbytes'] == 5 and str(result['matches'].best()) == 'bytes' and not view.readonly is False
    view.release()
    business &= from_buffer(b'')['matches'].best() is not None
except ImportError:
    business = False

print(json.dumps({'candidate_import': Path(charset_normalizer.__file__).resolve().is_relative_to(root / 'library'), 'business': bool(business)}))
