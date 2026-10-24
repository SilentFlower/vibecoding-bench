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
suite = control.SUITES['csvkit']
import_root = Path(suite.get('import_root', '.'))
control._bind_source(root / 'library', import_root, cleanup, distribution=suite.get('distribution'))
sys.path.insert(0, str(root / 'library' / import_root))

import csvkit
business=False
try:
    from csvkit.utilities.csvslice import CSVSlice
    from io import StringIO
    import tempfile,csv
    from pathlib import Path
    with tempfile.TemporaryDirectory() as directory:
        path=Path(directory)/'data';path.write_text('a;b\n1;2\n3;4\n5;6\n')
        output=StringIO();CSVSlice(['-d',';','--start','1','--stop','2',str(path)],output_file=output).run()
        business=list(csv.reader(StringIO(output.getvalue())))==[['a','b'],['3','4']]
except ImportError:business=False

print(json.dumps({'candidate_import': Path(csvkit.__file__).resolve().is_relative_to(root / 'library'), 'business': bool(business)}))
