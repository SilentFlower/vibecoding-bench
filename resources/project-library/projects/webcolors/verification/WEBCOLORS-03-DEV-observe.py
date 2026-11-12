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
suite = control.SUITES['webcolors']
control._bind_source(root / 'library', Path(suite.get('import_root', '.')), cleanup, distribution=suite.get('distribution'))
import sys
sys.path.insert(0, str(root / 'library' / suite.get('import_root', '.')))
import webcolors
from dataclasses import FrozenInstanceError
from webcolors.rgba import RGBA,hex_to_rgba,rgba_to_hex,rgba_to_rgb
business=True
for red in (0,1,127,128,254,255):
    for alpha in (0,1,127,128,254,255):
        value=RGBA(red,255-red,17,alpha)
        business &= hex_to_rgba(rgba_to_hex(value))==value
        if alpha<255:
            try:rgba_to_rgb(value)
            except ValueError:pass
            else:business=False
try:RGBA(1,2,3).alpha=0
except FrozenInstanceError:pass
else:business=False
business &= webcolors.normalize_hex('#abc')=='#aabbcc' and webcolors.html5_parse_simple_color('#abcdef')==(171,205,239)

print(json.dumps({'candidate_import': Path(webcolors.__file__).resolve().is_relative_to(root / 'library'), 'business': bool(business)}))
