"""独立业务验收，只读取当前候选，不联网或调用模型。"""
import json
import os
from pathlib import Path
root = Path(os.environ['PROJECT_CANDIDATE_ROOT']).resolve()
from contextlib import ExitStack
from importlib.util import module_from_spec, spec_from_file_location
spec = spec_from_file_location('frozen_native_control', Path(__file__).with_name('native_regression.py'))
control = module_from_spec(spec)
spec.loader.exec_module(control)
cleanup = ExitStack()
suite = control.SUITES['petl']
control._bind_source(root / 'library', Path(suite.get('import_root', '.')), cleanup, distribution=suite.get('distribution'))
import sys
sys.path.insert(0, str(root / 'library' / suite.get('import_root', '.')))
import petl
import petl
business=True
source=iter([('a','b'),('4','bad'),('no','7')])
table,issues=petl.convert_report(source,{'a':int,'b':int},errorvalue=-1)
business &= table==(('a','b'),(4,-1),(-1,7))
business &= issues==(('row','field','error_type'),(1,'b','ValueError'),(2,'a','ValueError'))

print(json.dumps({'candidate_import': Path(petl.__file__).resolve().is_relative_to(root / 'library'), 'business': bool(business)}))
