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
suite = control.SUITES['rich']
control._bind_source(root / 'library', Path(suite.get('import_root', '.')), cleanup, distribution=suite.get('distribution'))
import sys
sys.path.insert(0, str(root / 'library' / suite.get('import_root', '.')))
import rich
from rich.traceback import Traceback
from rich.console import Console
from io import StringIO
business=True
a=SyntaxError();a.msg={'reason':'bad input'};a.text='bad';a.offset=1
b=SyntaxError();b.msg=17;b.text='also bad';b.offset=1
a.__cause__=b;b.__cause__=a
trace=Traceback.extract(type(a),a,None)
business &= len(trace.stacks)==2 and all(isinstance(stack.syntax_error.msg,str) for stack in trace.stacks)
out=StringIO();Console(file=out,force_terminal=False).print(Traceback(trace))
business &= 'bad input' in out.getvalue() and '17' in out.getvalue()

print(json.dumps({'candidate_import': Path(rich.__file__).resolve().is_relative_to(root / 'library'), 'business': bool(business)}))
