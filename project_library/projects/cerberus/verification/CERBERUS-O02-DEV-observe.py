"""在固定候选源码上运行独立业务矩阵，不调用模型或外部服务。"""
import json
import os
from pathlib import Path
root = Path(os.environ['PROJECT_CANDIDATE_ROOT']).resolve()
from contextlib import ExitStack
from importlib.util import module_from_spec, spec_from_file_location
import sys
spec = spec_from_file_location('frozen_control', Path(__file__).with_name('native_regression.py'))
control = module_from_spec(spec)
spec.loader.exec_module(control)
cleanup = ExitStack()
suite = control.SUITES['cerberus']
import_root = Path(suite.get('import_root', '.'))
control._bind_source(root / 'library', import_root, cleanup, distribution=suite.get('distribution'))
sys.path.insert(0, str(root / 'library' / import_root))

import cerberus
from decimal import Decimal
business = False
try:
    validator = cerberus.Validator({'x': {'finite': True}})
    business = validator.validate({'x': Decimal('-0')}) and validator.validate({'x': 3.5})
    business &= not validator.validate({'x': Decimal('Infinity')}) and not validator.validate({'x': 'string'})
    nested = cerberus.Validator({'rows': {'type': 'list', 'schema': {'type': 'dict', 'schema': {'v': {'finite': True}}}}})
    business &= not nested.validate({'rows': [{'v': float('nan')}]}) and bool(nested.errors)
except cerberus.SchemaError:
    business = False

print(json.dumps({'candidate_import': Path(cerberus.__file__).resolve().is_relative_to(root / 'library'), 'business': bool(business)}))
