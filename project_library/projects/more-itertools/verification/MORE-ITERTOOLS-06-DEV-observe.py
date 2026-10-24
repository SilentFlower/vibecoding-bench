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
suite = control.SUITES['more-itertools']
control._bind_source(root / 'library', Path(suite.get('import_root', '.')), cleanup, distribution=suite.get('distribution'))
import sys
sys.path.insert(0, str(root / 'library' / suite.get('import_root', '.')))
import more_itertools
from more_itertools import sized_iterator
business=True
value=sized_iterator([3,4],3,strict=True)
business &= next(value)==3 and next(value)==4 and len(value)==3
try:next(value);business=False
except ValueError:pass
business &= list(value)==[]

print(json.dumps({'candidate_import': Path(more_itertools.__file__).resolve().is_relative_to(root / 'library'), 'business': bool(business)}))
