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
from pluggy import PluginManager
from pluggy.scoped import temporary_plugins
business=True
pm=PluginManager('app');a=object();b=object();replacement=object()
with temporary_plugins(pm,[('a',a)]):
    with temporary_plugins(pm,[('b',b)]):business &= pm.get_plugin('a') is a and pm.get_plugin('b') is b
    business &= not pm.has_plugin('b')
    pm.unregister(a);pm.register(replacement,'a')
business &= pm.get_plugin('a') is replacement
pm.set_blocked('blocked')
try:
    with temporary_plugins(pm,[('new',object()),('blocked',object())]):pass
except ValueError:pass
else:business=False
business &= not pm.has_plugin('new') and pm.is_blocked('blocked')

print(json.dumps({'candidate_import': Path(pluggy.__file__).resolve().is_relative_to(root / 'library'), 'business': bool(business)}))
