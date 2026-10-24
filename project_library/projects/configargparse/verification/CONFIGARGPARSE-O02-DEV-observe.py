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
    from io import StringIO
    import warnings
    cls=configargparse.JSONConfigFileParser
    with warnings.catch_warnings(record=True) as records:
        warnings.simplefilter('always')
        output=cls(duplicates='warn').parse(StringIO('{"x":0,"x":false,"empty":[]}'))
    business=output=={'x':'false','empty':[]} and len(records)==1
    for bad in ['{', '{"x":[null]}','{"x":Infinity}']:
        try: cls().parse(StringIO(bad))
        except configargparse.ConfigFileParserException: pass
        else: business=False
except AttributeError:
    business=False

print(json.dumps({'candidate_import': Path(configargparse.__file__).resolve().is_relative_to(root / 'library'), 'business': bool(business)}))
