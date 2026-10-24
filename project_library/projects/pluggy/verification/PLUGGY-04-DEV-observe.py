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
    @spec(historic=True)
    def event(self,value):pass
pm=PluginManager('app');pm.add_hookspecs(Specs)
for value in range(6):pm.hook.event.call_historic(kwargs={'value':value})
business &= pm.hook.event.clear_history(lambda kwargs:kwargs['value']%2==0)==3
seen=[]
class Plugin:
    @impl
    def event(self,value):seen.append(value)
pm.register(Plugin());business &= seen==[1,3,5]
pm.hook.event.set_history_limit(1)
business &= len(pm.hook.event._call_history)==1 and pm.hook.event._call_history[0][0]['value']==5
for value in (-1,True,0.5):
    try:pm.hook.event.set_history_limit(value)
    except ValueError:pass
    else:business=False

print(json.dumps({'candidate_import': Path(pluggy.__file__).resolve().is_relative_to(root / 'library'), 'business': bool(business)}))
