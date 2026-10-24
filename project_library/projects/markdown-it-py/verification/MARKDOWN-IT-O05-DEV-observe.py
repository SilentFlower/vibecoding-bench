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
suite = control.SUITES['markdown-it-py']
import_root = Path(suite.get('import_root', '.'))
control._bind_source(root / 'library', import_root, cleanup, distribution=suite.get('distribution'))
sys.path.insert(0, str(root / 'library' / import_root))

import markdown_it
_bench_candidate_module = markdown_it
from markdown_it.token import Token
token=Token('inline','',0,children=[Token('text','',0,content='source')],map=[1,2],meta={'nested':[1]})
business=hasattr(token,'deep_copy')
if business:
    clone=token.deep_copy();clone.children[0].content='changed';clone.meta['nested'].append(2);clone.map[0]=99
    business=token.children[0].content=='source' and token.meta['nested']==[1] and token.map==[1,2] and clone is not token

print(json.dumps({'candidate_import': Path(_bench_candidate_module.__file__).resolve().is_relative_to(_bench_candidate_root / 'library'), 'business': bool(business)}))
