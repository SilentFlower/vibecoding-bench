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
from markdown.results import convert_document
business=True
for title in ('中文','One','Two'):
    result=convert_document('title: '+title+'\n\n# '+title,extensions=['markdown.extensions.meta','markdown.extensions.toc'])
    business &= result.metadata=={'title':[title]} and result.toc_tokens[0]['name']==title
    result.metadata['title'].append('external')
    again=convert_document('title: '+title+'\n\n# '+title,extensions=['markdown.extensions.meta','markdown.extensions.toc'])
    business &= again.metadata=={'title':[title]}
plain=convert_document('[missing]')
business &= plain.references=={} and '[missing]' in plain.html

print(json.dumps({'candidate_import': Path(markdown.__file__).resolve().is_relative_to(root / 'library'), 'business': bool(business)}))
