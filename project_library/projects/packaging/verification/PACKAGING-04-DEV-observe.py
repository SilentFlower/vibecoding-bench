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
suite = control.SUITES['packaging']
control._bind_source(root / 'library', Path(suite.get('import_root', '.')), cleanup, distribution=suite.get('distribution'))
import sys
sys.path.insert(0, str(root / 'library' / suite.get('import_root', '.')))
import packaging
import base64,hashlib
from packaging.record import RecordEntry,parse_record,format_record
business=True
digest=base64.urlsafe_b64encode(hashlib.sha512(b'x').digest()).rstrip(b'=').decode()
entries=(RecordEntry('line\nbreak','sha512='+digest,1),RecordEntry('empty',None,0))
business &= parse_record(format_record(iter(entries)))==entries
try:parse_record('x,sha1=aaaa,2\n');business=False
except ValueError:pass

print(json.dumps({'candidate_import': Path(packaging.__file__).resolve().is_relative_to(root / 'library'), 'business': bool(business)}))
