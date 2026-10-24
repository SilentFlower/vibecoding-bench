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
business = False
try:
    from io import StringIO
    import warnings
    parser = configargparse.DefaultConfigFileParser(duplicates='warn')
    with warnings.catch_warnings(record=True) as records:
        warnings.simplefilter('always')
        output = parser.parse(StringIO('x=1\nx=2\nx=3\n'))
    business = output == {'x':'3'} and len(records) == 2 and '第1行与第3行' in str(records[1].message)
    parser = configargparse.ArgumentParser(config_file_parser_class=configargparse.DefaultConfigFileParser(duplicates='error'))
    parser.add('--port', type=int)
    business = business and parser.parse_args(['--port','9'], config_file_contents='port=2', env_vars={}).port == 9
except TypeError:
    business = False

print(json.dumps({'candidate_import': Path(configargparse.__file__).resolve().is_relative_to(root / 'library'), 'business': bool(business)}))
