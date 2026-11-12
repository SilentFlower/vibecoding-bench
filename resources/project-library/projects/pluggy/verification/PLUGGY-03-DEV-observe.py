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
suite = control.SUITES['pluggy']
control._bind_source(root / 'library', Path(suite.get('import_root', '.')), cleanup, distribution=suite.get('distribution'))
import sys
sys.path.insert(0, str(root / 'library' / suite.get('import_root', '.')))
import pluggy
from pluggy import PluginManager,HookspecMarker,HookimplMarker
business=True
spec=HookspecMarker('app');impl=HookimplMarker('app')
class Specs:
    @spec
    def value(self):pass
class Plugin:
    __hash__=None
    def __eq__(self,other):raise RuntimeError('eq must not run')
    @impl
    def value(self):return id(self)
pm=PluginManager('app');pm.add_hookspecs(Specs);a,b=Plugin(),Plugin()
pm.register(a,'a');pm.register(b,'b')
business &= pm.is_registered(a) and pm.get_name(Plugin()) is None and pm.subset_hook_caller('value',[a])()==[id(b)]
pm.unregister(name='b');business &= pm.hook.value()==[id(a)]
pm.set_blocked('blocked');business &= not pm.is_registered(None) and pm.get_name(None) is None

print(json.dumps({'candidate_import': Path(pluggy.__file__).resolve().is_relative_to(root / 'library'), 'business': bool(business)}))
