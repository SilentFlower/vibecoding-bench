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
import wrapt
business=True
for reverse in (False,True):
    calls=[]
    def compute(cls,token):calls.append((cls,token));return cls,token
    decorated=classmethod(wrapt.lru_cache(maxsize=4)(compute)) if reverse else wrapt.lru_cache(maxsize=4)(classmethod(compute))
    class Base:value=decorated
    class Child(Base):pass
    class Grandchild(Child):pass
    business &= Base.value('x')==(Base,'x') and Child.value('x')==(Child,'x')
    business &= Grandchild.value('x')==(Grandchild,'x') and Child().value('x')==(Child,'x')
    business &= calls==[(Base,'x'),(Child,'x'),(Grandchild,'x')] and Child.value.cache_info().hits>=1

print(json.dumps({'candidate_import': Path(wrapt.__file__).resolve().is_relative_to(root / 'library'), 'business': bool(business)}))
