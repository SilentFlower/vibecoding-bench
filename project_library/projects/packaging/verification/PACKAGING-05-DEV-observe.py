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
from packaging.tags import Tag
from packaging.utils import build_wheel_filename,parse_wheel_filename,build_sdist_filename,parse_sdist_filename
from packaging.version import Version
business=True
tags={Tag('cp312','abi3','manylinux_2_17_x86_64')}
filename=build_wheel_filename('A-B','2!1.0rc1',iter(tags))
business &= parse_wheel_filename(filename)==('a-b',Version('2!1.0rc1'),(),tags)
business &= build_sdist_filename('A-B','01.0','.zip')=='a_b-1.0.zip'

print(json.dumps({'candidate_import': Path(packaging.__file__).resolve().is_relative_to(root / 'library'), 'business': bool(business)}))
