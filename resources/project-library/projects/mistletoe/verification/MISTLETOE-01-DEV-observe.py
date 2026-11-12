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
from mistletoe import Document
from mistletoe.ast_renderer import get_ast
business=True
for count in (2,4,6):
    doc=Document(''.join('#'*(i+1)+' title-'+str(i)+'\n' for i in range(count)))
    expected=['title-'+str(i) for i in range(count)]
    Document('# unrelated\n')
    business &= [h.content for h in doc.children]==expected
    business &= all('content' not in get_ast(h) for h in doc.children)

print(json.dumps({'candidate_import': Path(mistletoe.__file__).resolve().is_relative_to(root / 'library'), 'business': bool(business)}))
