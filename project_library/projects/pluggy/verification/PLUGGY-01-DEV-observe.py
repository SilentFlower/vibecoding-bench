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
    """无默认参数历史。"""
    @spec(historic=True)
    def event(self,value):pass
pm=PluginManager('app');pm.add_hookspecs(Specs);original={'value':'one'}
pm.hook.event.call_historic(kwargs=original);original.clear();original['value']='two'
seen=[]
class Plugin:
    @impl
    def event(self,value):seen.append(value)
pm.register(Plugin())
business &= seen==['one'] and pm.hook.event._call_history[0][0] is not original

print(json.dumps({'candidate_import': Path(pluggy.__file__).resolve().is_relative_to(root / 'library'), 'business': bool(business)}))
