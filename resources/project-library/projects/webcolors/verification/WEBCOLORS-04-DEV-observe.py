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
from webcolors.rgba import RGBA
from webcolors.css_rgb import parse_css_rgb,serialize_css_rgb
business=True
for red in (0,1,127,128,254,255):
    for alpha in range(0,256,17):
        expected=RGBA(red,255-red,37,alpha)
        business &= parse_css_rgb(serialize_css_rgb(expected))==expected
business &= parse_css_rgb('rgba(10%,20%,30%,25%)')==RGBA(26,51,77,64)
business &= parse_css_rgb('rgba(1 2 3 / -5)')==RGBA(1,2,3,0)
business &= parse_css_rgb('rgb(1 2 3 / 200%)')==RGBA(1,2,3,255)

print(json.dumps({'candidate_import': Path(webcolors.__file__).resolve().is_relative_to(root / 'library'), 'business': bool(business)}))
