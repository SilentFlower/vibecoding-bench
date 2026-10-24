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
suite = control.SUITES['python-markdown']
control._bind_source(root / 'library', Path(suite.get('import_root', '.')), cleanup, distribution=suite.get('distribution'))
import sys
sys.path.insert(0, str(root / 'library' / suite.get('import_root', '.')))
import markdown
from markdown.extensions import Extension
business=True
callback=lambda value:value
class Local(Extension):
    """类级嵌套默认配置。"""
    config={'name':['base','说明'],'data':[{'a':[[1]],'callback':callback},'容器'],'flag':[None,'可空']}
a=Local(name='first');b=Local()
a.getConfig('data')['a'][0].append(2)
business &= b.getConfig('name')=='base' and b.getConfig('data')['a']==[[1]] and Local.config['data'][0]['a']==[[1]]
business &= b.getConfig('data')['callback'] is callback and Local(flag='false').getConfig('flag') is False
cycle=[];cycle.append(cycle)
try:Local(data=cycle)
except ValueError:pass
else:business=False

print(json.dumps({'candidate_import': Path(markdown.__file__).resolve().is_relative_to(root / 'library'), 'business': bool(business)}))
