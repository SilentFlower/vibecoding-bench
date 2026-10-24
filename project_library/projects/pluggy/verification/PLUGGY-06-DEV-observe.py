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
from types import SimpleNamespace
from unittest.mock import patch
from pluggy import PluginManager
from pluggy.discovery import discover_entrypoints,load_entrypoint
business=True
calls=[]
entry=SimpleNamespace(group='app',name='x',value='pkg:x',load=lambda:calls.append('load') or None)
dist=SimpleNamespace(metadata={'Name':'package'},version='1',entry_points=[entry])
pm=PluginManager('app')
with patch('importlib.metadata.distributions',return_value=[dist]):
    candidate=discover_entrypoints('app').candidates[0]
    business &= not calls and load_entrypoint(pm,candidate) is None and pm.list_plugin_distributions()==[]
with patch('importlib.metadata.distributions',return_value=[dist,dist]):
    try:load_entrypoint(pm,candidate)
    except ValueError:pass
    else:business=False
business &= calls==['load']

print(json.dumps({'candidate_import': Path(pluggy.__file__).resolve().is_relative_to(root / 'library'), 'business': bool(business)}))
