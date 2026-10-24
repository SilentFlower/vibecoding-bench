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
suite = control.SUITES['configargparse']
import_root = Path(suite.get('import_root', '.'))
control._bind_source(root / 'library', import_root, cleanup, distribution=suite.get('distribution'))
sys.path.insert(0, str(root / 'library' / import_root))

import configargparse
business=False
try:
    import argparse
    p=configargparse.ArgumentParser();p.add('--count',type=int,default=7)
    result=p.parse_result(['--mystery','z'],env_vars={})
    before=result.sources
    p.set_defaults(count=99);p.parse_args([],env_vars={})
    copied=result.sources
    for items in copied.values():
        for info in items.values():
            info['value']='changed'
    business=result.namespace.count==7 and result.unknown==('--mystery','z') and result.sources==before
except AttributeError:
    business=False

print(json.dumps({'candidate_import': Path(configargparse.__file__).resolve().is_relative_to(root / 'library'), 'business': bool(business)}))
