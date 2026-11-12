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
from mdit_py_plugins.anchors import anchors_plugin
records=[]
try:
    md=MarkdownIt().use(anchors_plugin,callback=records.append,permalink=True)
    html=md.render('## Same\n\n## Same')
    business=[row['slug'] for row in records]==['same','same-1'] and [row['map'] for row in records]==[[0,1],[2,3]] and records[0]['title']=='Same' and 'id="same-1"' in html
except TypeError:business=False

print(json.dumps({'candidate_import': Path(_bench_candidate_module.__file__).resolve().is_relative_to(_bench_candidate_root / 'library'), 'business': bool(business)}))
