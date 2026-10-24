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
from natsort.cached import cached_natsort_keygen
from natsort import natsort_keygen, ns
business=True
for alg in (ns.DEFAULT,ns.SIGNED,ns.REAL,ns.PATH):
    factory=cached_natsort_keygen(alg=alg,maxsize=3);gold=natsort_keygen(alg=alg)
    values=['file12','file2','file01','-2.5','x/2']
    business &= all(factory(value)==gold(value) for value in values*2)
    business &= factory.cache_info().currsize<=3
zero=cached_natsort_keygen(maxsize=0)
zero('same');zero('same')
business &= zero.cache_info().hits==0 and zero.cache_info().currsize==0

print(json.dumps({'candidate_import': Path(natsort.__file__).resolve().is_relative_to(root / 'library'), 'business': bool(business)}))
