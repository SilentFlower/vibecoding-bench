"""独立业务验收，只读取当前候选，不联网或调用模型。"""
import json
import os
from pathlib import Path
root = Path(os.environ['PROJECT_CANDIDATE_ROOT']).resolve()
from contextlib import ExitStack
from importlib.util import module_from_spec, spec_from_file_location
spec = spec_from_file_location('frozen_native_control', Path(__file__).with_name('native_regression.py'))
control = module_from_spec(spec)
spec.loader.exec_module(control)
cleanup = ExitStack()
suite = control.SUITES['packaging']
control._bind_source(root / 'library', Path(suite.get('import_root', '.')), cleanup, distribution=suite.get('distribution'))
import sys
sys.path.insert(0, str(root / 'library' / suite.get('import_root', '.')))
import packaging
from packaging.utils import parse_legacy_sdist_filename
from packaging.version import Version
business=True
business &= parse_legacy_sdist_filename('alpha_beta-2.1-3.zip','alpha-beta')==('alpha-beta',Version('2.1.post3'))
candidates=parse_legacy_sdist_filename('alpha-beta-3.tar.gz')
business &= candidates==(('alpha-beta',Version('3')),)

print(json.dumps({'candidate_import': Path(packaging.__file__).resolve().is_relative_to(root / 'library'), 'business': bool(business)}))
