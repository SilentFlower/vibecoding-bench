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
from webcolors.palette import Palette
business=True
a=Palette({'Primary':'#123','other':'#112233'});b=Palette({'primary':'#abc'})
business &= a['PRIMARY']=='#112233' and b['PRIMARY']=='#aabbcc' and a.aliases('#123')==('other','primary')
business &= tuple(a)==('other','primary')
try:a['primary']='#000'
except TypeError:pass
else:business=False
try:a._colors['primary']='#000'
except TypeError:pass
else:business=False
for spec in ('html4','css2','css21','css3'):
    palette=Palette({'brand-color':'#123'},base_spec=spec)
    business &= all(palette[name]==webcolors.name_to_hex(name,spec) for name in webcolors.names(spec))
    business &= len(palette)==len(webcolors.names(spec))+1

print(json.dumps({'candidate_import': Path(webcolors.__file__).resolve().is_relative_to(root / 'library'), 'business': bool(business)}))
