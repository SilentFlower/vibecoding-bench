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
from mistletoe.block_token import List
business=True
for text,kwargs in [('# title\n',{}),('## ignored\n',{'filter_conds':[lambda value:True]}),('',{})]:
    with TocRenderer(**kwargs) as renderer:
        renderer.render(Document(text))
        business &= isinstance(renderer.toc,List) and renderer.toc.children==[]
        business &= renderer.render(renderer.toc)==renderer.render(renderer.toc)==''
with TocRenderer() as renderer:
    renderer.render(Document('## alpha\n### beta\n'))
    business &= 'alpha' in renderer.render(renderer.toc) and 'beta' in renderer.render(renderer.toc)

print(json.dumps({'candidate_import': Path(mistletoe.__file__).resolve().is_relative_to(root / 'library'), 'business': bool(business)}))
