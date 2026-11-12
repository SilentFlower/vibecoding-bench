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
suite = control.SUITES['wrapt']
control._bind_source(root / 'library', Path(suite.get('import_root', '.')), cleanup, distribution=suite.get('distribution'))
import sys
sys.path.insert(0, str(root / 'library' / suite.get('import_root', '.')))
import wrapt
import gc,weakref
from wrapt.weak_cache import weak_method_cache
business=True
class Item:
    __slots__=('__weakref__',)
    @weak_method_cache(maxsize=1)
    def value(self,x):return x*2
a=Item();business &= a.value(3)==6 and Item.value.cache_count()==1
r=weakref.ref(a);del a;gc.collect();business &= r() is None and Item.value.cache_count()==0

print(json.dumps({'candidate_import': Path(wrapt.__file__).resolve().is_relative_to(root / 'library'), 'business': bool(business)}))
