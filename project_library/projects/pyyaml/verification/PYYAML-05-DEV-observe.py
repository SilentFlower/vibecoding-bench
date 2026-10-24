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
suite = control.SUITES['pyyaml']
control._bind_source(root / 'library', Path(suite.get('import_root', '.')), cleanup, distribution=suite.get('distribution'))
import sys
sys.path.insert(0, str(root / 'library' / suite.get('import_root', '.')))
import yaml
from yaml.limits import load_limited
from yaml import YAMLError
business=True
value=load_limited('a: &a [x]\nb: *a\nc: *a',max_aliases=2,max_depth=3,max_nodes=7)
business &= value['a'] is value['b'] is value['c']
try:load_limited('[1]',max_nodes=0);business=False
except YAMLError:pass

print(json.dumps({'candidate_import': Path(yaml.__file__).resolve().is_relative_to(root / 'library'), 'business': bool(business)}))
