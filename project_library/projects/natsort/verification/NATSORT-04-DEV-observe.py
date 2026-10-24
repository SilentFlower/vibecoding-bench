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
suite = control.SUITES['natsort']
control._bind_source(root / 'library', Path(suite.get('import_root', '.')), cleanup, distribution=suite.get('distribution'))
import natsort
from natsort import natsorted
from natsort.merge import merge_sorted
business=True
streams=[['p1','p4','p10'],['p2','p5','p20'],[],['p3','p6']]
business &= list(merge_sorted(*map(iter,streams)))==natsorted([item for stream in streams for item in stream])
for reverse in (False,True):
    ordered=[natsorted(stream,reverse=reverse) for stream in streams]
    business &= list(merge_sorted(*ordered,reverse=reverse))==natsorted([item for stream in ordered for item in stream],reverse=reverse)
try:list(merge_sorted(['a1','a3','a2']))
except ValueError:pass
else:business=False

print(json.dumps({'candidate_import': Path(natsort.__file__).resolve().is_relative_to(root / 'library'), 'business': bool(business)}))
