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
from mistletoe.contrib.toc_renderer import TocRenderer
business=True
created=[TocRenderer() for _ in range(4)]
created[0].filter_conds.append(lambda value:True)
business &= all(renderer.filter_conds==[] for renderer in created[1:])
for iterable in ([lambda value:value=='drop'],(lambda value:value=='drop',),(fn for fn in [lambda value:value=='drop'])):
    with TocRenderer(filter_conds=iterable) as renderer:
        renderer.render(Document('## drop\n## keep\n'))
        business &= renderer._headings==[(2,'keep')]

print(json.dumps({'candidate_import': Path(mistletoe.__file__).resolve().is_relative_to(root / 'library'), 'business': bool(business)}))
