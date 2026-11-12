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
suite = control.SUITES['loguru']
import_root = Path(suite.get('import_root', '.'))
control._bind_source(root / 'library', import_root, cleanup, distribution=suite.get('distribution'))
sys.path.insert(0, str(root / 'library' / import_root))

import loguru
_bench_candidate_module = loguru
from copy import deepcopy
from loguru import logger
business=False
try:
    from loguru import LazyValue
    logger.remove();log=deepcopy(logger);log.remove();out=[];calls=[];log.add(out.append,format='{message}')
    value=LazyValue(lambda:calls.append('used') or 6)
    log.info('{v:02d}/{v}',v=value,unused=LazyValue(lambda:calls.append('unused')))
    business=''.join(out)=='06/6\n' and calls==['used'];log.remove()
except ImportError:pass

print(json.dumps({'candidate_import': Path(_bench_candidate_module.__file__).resolve().is_relative_to(_bench_candidate_root / 'library'), 'business': bool(business)}))
