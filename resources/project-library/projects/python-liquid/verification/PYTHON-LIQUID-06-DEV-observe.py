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
suite = control.SUITES['python-liquid']
control._bind_source(root / 'library', Path(suite.get('import_root', '.')), cleanup, distribution=suite.get('distribution'))
import sys
sys.path.insert(0, str(root / 'library' / suite.get('import_root', '.')))
import liquid
import json,tempfile
from pathlib import Path
from liquid.project_cli import main
business=True
with tempfile.TemporaryDirectory() as directory:
    base=Path(directory);rootpath=base/'t';rootpath.mkdir();(rootpath/'x').write_text('{{n | times: 2}}')
    data=base/'input.json';data.write_text('{"n":6}');out=base/'out'
    args=['--root',str(rootpath),'--template','x','--data',str(data),'--output',str(out)]
    business &= main(args)==0 and out.read_text()=='12' and data.read_text()=='{"n":6}'
    data.write_text('{bad');business &= main(args)==2 and out.read_text()=='12'

print(json.dumps({'candidate_import': Path(liquid.__file__).resolve().is_relative_to(root / 'library'), 'business': bool(business)}))
