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
business=True
for schemes,expected in [(['urn'],'urn:example:one'),(['ssh'],'ssh://host/path')]:
    md=markdown.Markdown(extensions=['markdown.extensions.uri_autolink'],extension_configs={'markdown.extensions.uri_autolink':{'schemes':schemes}})
    output=md.convert('<urn:example:one> <ssh://host/path>')
    business &= 'href="'+expected+'"' in output
    other='ssh://host/path' if schemes==['urn'] else 'urn:example:one'
    business &= 'href="'+other+'"' not in output
business &= '<a href="http://example.com">' in markdown.markdown('<http://example.com>',extensions=['markdown.extensions.uri_autolink'])
business &= '<code>' in markdown.markdown('    <ssh://host>',extensions=['markdown.extensions.uri_autolink'])

print(json.dumps({'candidate_import': Path(markdown.__file__).resolve().is_relative_to(root / 'library'), 'business': bool(business)}))
