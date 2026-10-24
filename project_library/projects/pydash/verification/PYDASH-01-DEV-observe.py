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
suite = control.SUITES['pydash']
control._bind_source(root / 'library', Path(suite.get('import_root', '.')), cleanup, distribution=suite.get('distribution'))
import sys
sys.path.insert(0, str(root / 'library' / suite.get('import_root', '.')))
import pydash
from unittest.mock import patch
import pydash
business=True
for args,kwargs,expected in [((11,),{},(0,11)),((0,),{},(0,0)),((-9,),{},(-9,0)),((),{'stop':4},(0,4)),((3,0),{},(0,3))]:
    with patch('pydash.utilities.randint',return_value=2) as draw:
        business &= pydash.random(*args,**kwargs)==2 and draw.call_args.args==expected
with patch('pydash.utilities.uniform',return_value=0.1) as draw:
    pydash.random(-0.25);business &= draw.call_args.args==(-0.25,0)

print(json.dumps({'candidate_import': Path(pydash.__file__).resolve().is_relative_to(root / 'library'), 'business': bool(business)}))
