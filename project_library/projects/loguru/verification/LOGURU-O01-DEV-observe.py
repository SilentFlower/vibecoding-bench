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
logger.remove();log=deepcopy(logger);log.remove();business=hasattr(log,'handler_snapshot')
if business:
    identifier=log.add(lambda message:None,level='ERROR',enqueue=True)
    row=log.handler_snapshot()[0];business=row['id']==identifier and row['level']==40 and row['enqueue'] and row['sink_type']=='CallableSink'
    log.remove()

print(json.dumps({'candidate_import': Path(_bench_candidate_module.__file__).resolve().is_relative_to(_bench_candidate_root / 'library'), 'business': bool(business)}))
