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
suite = control.SUITES['funcy']
import_root = Path(suite.get('import_root', '.'))
control._bind_source(root / 'library', import_root, cleanup, distribution=suite.get('distribution'))
sys.path.insert(0, str(root / 'library' / import_root))

import funcy
business=False
try:
    from funcy.pipeline import Pipeline,Stage,PipelineStageError
    p=Pipeline([Stage('select',1),Stage('transform',lambda x:x+2)])
    report=p.run([0,5],report=True)
    business=report.ok and report.value==7 and len(report.events)==2
    def bad(x):raise LookupError('output')
    try:Pipeline([Stage('stage',lambda x:x,output_adapter=bad)])(1)
    except PipelineStageError as error:business=business and error.phase=='output' and isinstance(error.__cause__,LookupError)
    else:business=False
except ImportError:business=False

print(json.dumps({'candidate_import': Path(funcy.__file__).resolve().is_relative_to(root / 'library'), 'business': bool(business)}))
