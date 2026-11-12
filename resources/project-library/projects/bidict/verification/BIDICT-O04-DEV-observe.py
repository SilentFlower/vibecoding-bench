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
suite = control.SUITES['bidict']
import_root = Path(suite.get('import_root', '.'))
control._bind_source(root / 'library', import_root, cleanup, distribution=suite.get('distribution'))
sys.path.insert(0, str(root / 'library' / import_root))

import bidict
business = False
try:
    from bidict.relation_patch import relation_diff, apply_relation_patch
    source = bidict.OrderedBidict([('x', 1), ('y', 2), ('z', 3)])
    desired = bidict.OrderedBidict([('z', 1), ('y', 3), ('x', 2)])
    patch = relation_diff(source, desired)
    output = apply_relation_patch(source, patch)
    business = list(output.items()) == list(desired.items()) and output.inverse[1] == 'z'
    business &= list(apply_relation_patch(output, patch, reverse=True).items()) == list(source.items())
    bad = dict(patch, after=(('a', 1), ('b', 1)))
    try:
        apply_relation_patch(source, bad)
    except ValueError:
        pass
    else:
        business = False
except ImportError:
    business = False

print(json.dumps({'candidate_import': Path(bidict.__file__).resolve().is_relative_to(root / 'library'), 'business': bool(business)}))
