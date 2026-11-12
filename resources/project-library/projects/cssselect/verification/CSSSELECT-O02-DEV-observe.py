"""在固定候选源码上运行独立业务矩阵，不调用模型或外部服务。"""
import json
import os
from pathlib import Path
root = Path(os.environ['PROJECT_CANDIDATE_ROOT']).resolve()
_bench_candidate_root = root
from contextlib import ExitStack
from importlib.util import module_from_spec, spec_from_file_location
import sys
spec = spec_from_file_location('frozen_control', Path(__file__).with_name('native_regression.py'))
control = module_from_spec(spec)
spec.loader.exec_module(control)
cleanup = ExitStack()
suite = control.SUITES['cssselect']
import_root = Path(suite.get('import_root', '.'))
control._bind_source(root / 'library', import_root, cleanup, distribution=suite.get('distribution'))
sys.path.insert(0, str(root / 'library' / import_root))

import cssselect
business=False
try:
    from cssselect.batch import translate_many
    count=[]
    def records():
        for item in [('x',':unknown'),('x','[data-x="a,b"]')]:count.append(item);yield item
    result=translate_many(records());first=next(result)
    business=first['error']['phase']=='translate' and len(count)==1
    second=next(result);business=business and second['ok'] and len(count)==2
except ImportError:business=False

print(json.dumps({'candidate_import': Path(cssselect.__file__).resolve().is_relative_to(_bench_candidate_root / 'library'), 'business': bool(business)}))
