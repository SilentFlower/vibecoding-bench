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
suite = control.SUITES['tqdm']
control._bind_source(root / 'library', Path(suite.get('import_root', '.')), cleanup, distribution=suite.get('distribution'))
import sys
sys.path.insert(0, str(root / 'library' / suite.get('import_root', '.')))
import tqdm
import io
from tqdm.cli import posix_pipe
business=True
for delimiter in (b'<>',b'XYZ','分'.encode()):
    for tail in (b'',b'end',delimiter[:1]):
        raw=delimiter.join([b'one',b'two',b''])+tail
        for size in (1,2,3,5):
            output=io.BytesIO();actual=[]
            posix_pipe(io.BytesIO(raw),output,delim=delimiter,buf_size=size,callback=actual.append,callback_len=False)
            expected=raw.split(delimiter)
            if expected and expected[-1]==b'':expected.pop()
            business &= output.getvalue()==raw and actual==expected

print(json.dumps({'candidate_import': Path(tqdm.__file__).resolve().is_relative_to(root / 'library'), 'business': bool(business)}))
