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
suite = control.SUITES['sortedcontainers']
control._bind_source(root / 'library', Path(suite.get('import_root', '.')), cleanup, distribution=suite.get('distribution'))
import sys
sys.path.insert(0, str(root / 'library' / suite.get('import_root', '.')))
import sortedcontainers
from sortedcontainers import SortedKeyList,SortedList
business=True
values=SortedKeyList([(3,'a'),(2,'b')],key=lambda item:-item[0])
values.add_left((3,'front'));values.add_right((3,'back'));values.add_left((4,'new'))
business &= list(values)==[(4,'new'),(3,'front'),(3,'a'),(3,'back'),(2,'b')]
values._check()
plain=SortedList([1]*30);plain._reset(4);plain.add_left(1);plain._check();business &= len(plain)==31

print(json.dumps({'candidate_import': Path(sortedcontainers.__file__).resolve().is_relative_to(root / 'library'), 'business': bool(business)}))
