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
import io
import tempfile
from pathlib import Path
from unittest.mock import patch
from markdown.documents import convert_file
business=True
source=io.StringIO('# One');output=io.StringIO();result=convert_file(source,output,extensions=['markdown.extensions.toc'])
business &= result.toc_tokens[0]['name']=='One' and output.getvalue()==result.html and not source.closed and not output.closed
with tempfile.TemporaryDirectory() as temporary:
    path=Path(temporary)/'out.html';path.write_bytes(b'old')
    with patch('markdown.documents.os.replace',side_effect=OSError('replace failure')):
        try:convert_file(io.StringIO('new'),path)
        except OSError:pass
        else:business=False
    business &= path.read_bytes()==b'old' and len(list(path.parent.iterdir()))==1
stream=io.BytesIO(b'\xff')
try:convert_file(stream,close_input=False)
except UnicodeDecodeError:pass
else:business=False
business &= not stream.closed

print(json.dumps({'candidate_import': Path(markdown.__file__).resolve().is_relative_to(root / 'library'), 'business': bool(business)}))
