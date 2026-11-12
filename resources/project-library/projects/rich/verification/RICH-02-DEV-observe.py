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
business=True
class NoHash(Exception):
    """不可hash异常矩阵。"""
    __hash__=None
a=NoHash('A');b=NoHash('B');c=NoHash('C')
a.__context__=b;b.__cause__=c;c.__context__=a
result=Traceback.extract(type(a),a,None)
business &= len(result.stacks)==3
a.__suppress_context__=True
business &= len(Traceback.extract(type(a),a,None).stacks)==1
group=ExceptionGroup('shared',[b,c,b]);trace=Traceback.extract(type(group),group,None)
business &= sum(len(item.stacks) for item in trace.stacks[0].exceptions)<=3 and trace.stacks[0].is_group

print(json.dumps({'candidate_import': Path(rich.__file__).resolve().is_relative_to(root / 'library'), 'business': bool(business)}))
