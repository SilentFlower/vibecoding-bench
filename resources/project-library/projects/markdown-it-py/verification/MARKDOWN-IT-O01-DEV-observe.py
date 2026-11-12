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
from markdown_it import MarkdownIt
md=MarkdownIt().disable('image');before=md.get_active_rules()
try:
    with md.reset_rules():
        md.disable(['emphasis','fence']);md.inline.ruler2.disable('balance_pairs');raise LookupError('expected')
except LookupError:pass
business=md.get_active_rules()==before and '<em>ok</em>' in md.render('*ok*')

print(json.dumps({'candidate_import': Path(_bench_candidate_module.__file__).resolve().is_relative_to(_bench_candidate_root / 'library'), 'business': bool(business)}))
