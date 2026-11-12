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
business = True
try:
    for schema, expected in [({'x': {'rename': 'x'}}, {'x': 4}), ({'x': {'rename': 'next', 'rename_handler': lambda name: name + '_end'}}, {'next_end': 4})]:
        validator = cerberus.Validator(schema, allow_unknown=True)
        source = {'x': 4}
        business &= validator.normalized(source) == expected and source == {'x': 4}
    validator = cerberus.Validator({'x': {'rename': 'target'}}, allow_unknown=True)
    business &= validator.normalized({'x': 1, 'target': 2}) == {'target': 1}
except (KeyError, TypeError):
    business = False

print(json.dumps({'candidate_import': Path(cerberus.__file__).resolve().is_relative_to(root / 'library'), 'business': bool(business)}))
