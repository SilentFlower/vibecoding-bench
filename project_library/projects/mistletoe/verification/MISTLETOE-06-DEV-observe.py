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
suite = control.SUITES['mistletoe']
control._bind_source(root / 'library', Path(suite.get('import_root', '.')), cleanup, distribution=suite.get('distribution'))
import mistletoe
from mistletoe.latex_renderer import LaTeXRenderer
from mistletoe.span_token import RawText
business=True
with LaTeXRenderer() as renderer:
    business &= renderer.render_raw_text(RawText(r'a\b~c'))==r'a\textbackslash{}b\textasciitilde{}c'
    business &= renderer.render_raw_text(RawText('中文 & #'))==r'中文 \& \#'
    business &= renderer.render_raw_text(RawText(r'\begin{a}~'),False)==r'\begin{a}~'

print(json.dumps({'candidate_import': Path(mistletoe.__file__).resolve().is_relative_to(root / 'library'), 'business': bool(business)}))
