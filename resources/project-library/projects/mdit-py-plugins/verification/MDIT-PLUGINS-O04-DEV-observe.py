"""在固定候选源码上运行独立业务矩阵，不调用模型或外部服务。"""
import json
import os
from pathlib import Path
root = Path(os.environ['PROJECT_CANDIDATE_ROOT']).resolve()
_bench_candidate_root = root
from contextlib import ExitStack
from importlib.util import module_from_spec, spec_from_file_location
import sys
spec = spec_from_file_location('frozen_control', Path(__file__).with_name('native_regression.py'))
control = module_from_spec(spec)
spec.loader.exec_module(control)
cleanup = ExitStack()
suite = control.SUITES['mdit-py-plugins']
import_root = Path(suite.get('import_root', '.'))
control._bind_source(root / 'library', import_root, cleanup, distribution=suite.get('distribution'))
sys.path.insert(0, str(root / 'library' / import_root))

import mdit_py_plugins
_bench_candidate_module = mdit_py_plugins
from markdown_it import MarkdownIt
from mdit_py_plugins.tasklists import tasklists_plugin
business=False
try:
    md=MarkdownIt().use(tasklists_plugin,enabled=True,gfm_whitespace=True)
    html=md.render('- [X]\tdone\n- [ ]\fwaiting')
    business=html.count('type="checkbox"')==2 and html.count('checked="checked"')==1 and 'disabled=' not in html and '[X]' not in html
except TypeError:pass

print(json.dumps({'candidate_import': Path(_bench_candidate_module.__file__).resolve().is_relative_to(_bench_candidate_root / 'library'), 'business': bool(business)}))
