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
suite = control.SUITES['tqdm']
control._bind_source(root / 'library', Path(suite.get('import_root', '.')), cleanup, distribution=suite.get('distribution'))
import sys
sys.path.insert(0, str(root / 'library' / suite.get('import_root', '.')))
import tqdm
import os
from typing import Optional
from unittest.mock import patch
from tqdm.utils import envwrap
business=True
for raw,expected in [(' false ',False),('NO',False),('On',True)]:
    with patch.dict(os.environ,{'BUSINESS_FLAG':raw,'BUSINESS_UNUSED':'ignored'}):
        @envwrap('business')
        def function(flag:Optional[bool]=None):return flag
        business &= function() is expected
for raw in ('','2','enable'):
    with patch.dict(os.environ,{'BUSINESS_FLAG':raw}):
        try:envwrap('business')(lambda flag=True:flag)
        except ValueError:pass
        else:business=False

print(json.dumps({'candidate_import': Path(tqdm.__file__).resolve().is_relative_to(root / 'library'), 'business': bool(business)}))
