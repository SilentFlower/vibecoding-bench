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
suite = control.SUITES['icecream']
import_root = Path(suite.get('import_root', '.'))
control._bind_source(root / 'library', import_root, cleanup, distribution=suite.get('distribution'))
sys.path.insert(0, str(root / 'library' / import_root))

import icecream
business=False
try:
    from icecream.logging_adapter import LoggingDebugger
    import logging
    records=[]
    class Handler(logging.Handler):
        """独立捕获真实LogRecord。"""
        def emit(self,record):records.append(record)
    logger=logging.Logger('matrix',logging.INFO);logger.addHandler(Handler());debug=LoggingDebugger(logger,level=logging.INFO)
    result=debug(101,202)
    business=result==(101,202) and len(records)==1 and records[0].name=='matrix' and records[0].levelno==logging.INFO
except ImportError:business=False

print(json.dumps({'candidate_import': Path(icecream.__file__).resolve().is_relative_to(root / 'library'), 'business': bool(business)}))
