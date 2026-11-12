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
from tempfile import TemporaryDirectory
business = False
try:
    from charset_normalizer.atomic import normalize_file_atomic
    with TemporaryDirectory() as temporary:
        folder = Path(temporary)
        source, destination = folder / 'in', folder / 'out'
        source.write_bytes(b'private')
        result = normalize_file_atomic(source, destination)
        business = source.read_bytes() == b'private' and destination.read_bytes() == b'private' and result['written_bytes'] == 7
        try:
            normalize_file_atomic(source, max_input_bytes=2)
        except ValueError:
            pass
        else:
            business = False
        business &= source.read_bytes() == b'private' and not list(folder.glob('.charset-normalize-*'))
except ImportError:
    business = False

print(json.dumps({'candidate_import': Path(charset_normalizer.__file__).resolve().is_relative_to(root / 'library'), 'business': bool(business)}))
