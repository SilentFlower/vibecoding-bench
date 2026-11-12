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
import math
from webcolors.rgba import RGBA
from webcolors.accessibility import relative_luminance,contrast_ratio,contrast_on,meets_contrast
business=True
for value in (0,1,10,11,32,118,128,254,255):
    encoded=value/255
    expected=encoded/12.92 if encoded<=0.04045 else ((encoded+0.055)/1.055)**2.4
    business &= abs(relative_luminance((value,value,value))-expected)<1e-14
for left,right in [((255,0,0),(0,0,255)),((17,34,51),(255,255,255))]:
    business &= contrast_ratio(left,right)==contrast_ratio(right,left)
business &= contrast_on(RGBA(255,0,0,128),(0,0,255))==contrast_ratio((128,0,127),(0,0,255))
for threshold in (0,22,float('nan'),float('inf'),True):
    try:meets_contrast((0,0,0),(255,255,255),threshold)
    except ValueError:pass
    else:business=False

print(json.dumps({'candidate_import': Path(webcolors.__file__).resolve().is_relative_to(root / 'library'), 'business': bool(business)}))
