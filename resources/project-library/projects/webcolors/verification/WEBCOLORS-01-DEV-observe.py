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
business=True
for spec in ('html4','css2','css21','css3','css4'):
    for name in webcolors.names(spec):
        color=webcolors.name_to_hex(name,spec)
        business &= webcolors.name_to_hex(webcolors.hex_to_name(color,spec),spec)==color
business &= webcolors.CSS4=='css4' and 'rebeccapurple' in webcolors.names() and webcolors.name_to_rgb('REBECCAPURPLE')==(102,51,153)
business &= webcolors.html5_parse_legacy_color('rebeccapurple')==(102,51,153)
for unknown in ('CSS4','none',''):
    try:webcolors.names(unknown)
    except ValueError:pass
    else:business=False

print(json.dumps({'candidate_import': Path(webcolors.__file__).resolve().is_relative_to(root / 'library'), 'business': bool(business)}))
