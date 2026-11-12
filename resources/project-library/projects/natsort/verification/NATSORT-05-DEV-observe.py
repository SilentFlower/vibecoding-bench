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
from natsort.search import NaturalSortedIndex
business=True
for reverse in (False,True):
    values=['n1','n2','n02','n4','n9','n10']
    if reverse:values.reverse()
    index=NaturalSortedIndex(iter(values),reverse=reverse)
    selected=index.between('n2','n9',include_stop=False)
    expected=['n2','n02','n4']
    if reverse:expected.reverse()
    business &= selected==expected and index.count('n2')==2
    business &= list(index)==values and index.between()==values

print(json.dumps({'candidate_import': Path(natsort.__file__).resolve().is_relative_to(root / 'library'), 'business': bool(business)}))
