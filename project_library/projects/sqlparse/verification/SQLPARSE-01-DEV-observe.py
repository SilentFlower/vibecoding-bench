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
suite = control.SUITES['sqlparse']
control._bind_source(root / 'library', Path(suite.get('import_root', '.')), cleanup, distribution=suite.get('distribution'))
import sys
sys.path.insert(0, str(root / 'library' / suite.get('import_root', '.')))
import sqlparse
import contextlib
import io
import tempfile
from pathlib import Path
from unittest.mock import patch
from sqlparse.cli import main
business=True
with tempfile.TemporaryDirectory() as temporary:
    a=Path(temporary)/'a.sql';b=Path(temporary)/'b.sql';a.write_bytes(b'select 1;');b.write_bytes(b'select 2;')
    with patch('sqlparse.cli.sqlparse.format',side_effect=RuntimeError('formatter failed')),contextlib.redirect_stderr(io.StringIO()):
        business &= main([str(a),'--in-place'])==1
    business &= a.read_bytes()==b'select 1;'
    with contextlib.redirect_stderr(io.StringIO()):
        code=main([str(a),str(Path(temporary)/'missing.sql'),str(b),'--in-place','-k','upper'])
    business &= code==1 and a.read_text()=='SELECT 1;' and b.read_text()=='SELECT 2;'
    link=Path(temporary)/'link.sql';link.symlink_to(a)
    with contextlib.redirect_stderr(io.StringIO()):business &= main([str(link),'--in-place'])==1
    business &= link.is_symlink() and len(list(Path(temporary).iterdir()))==3

print(json.dumps({'candidate_import': Path(sqlparse.__file__).resolve().is_relative_to(root / 'library'), 'business': bool(business)}))
