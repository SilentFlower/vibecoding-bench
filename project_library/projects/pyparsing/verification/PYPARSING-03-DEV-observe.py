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
suite = control.SUITES['pyparsing']
control._bind_source(root / 'library', Path(suite.get('import_root', '.')), cleanup, distribution=suite.get('distribution'))
import sys
sys.path.insert(0, str(root / 'library' / suite.get('import_root', '.')))
import pyparsing
from decimal import Decimal
from pyparsing.decimal_input import localized_decimal
business=True
p=localized_decimal(decimal_separator='.',group_separator=',',group_size=3,max_fraction=0)
business &= p.parse_string('+12,345',parse_all=True)[0]==Decimal(12345)
p=localized_decimal(decimal_separator=',',group_separator=' ',group_size=4)
business &= p.parse_string('12 3456,789',parse_all=True)[0]==Decimal('123456.789')

print(json.dumps({'candidate_import': Path(pyparsing.__file__).resolve().is_relative_to(root / 'library'), 'business': bool(business)}))
