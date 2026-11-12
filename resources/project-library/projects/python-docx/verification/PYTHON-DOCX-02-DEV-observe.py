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
suite = control.SUITES['python-docx']
control._bind_source(root / 'library', Path(suite.get('import_root', '.')), cleanup, distribution=suite.get('distribution'))
import sys
sys.path.insert(0, str(root / 'library' / suite.get('import_root', '.')))
import docx
from datetime import datetime,timedelta,timezone
from io import BytesIO
from docx import Document
business=True
value=Document();value.core_properties.modified=datetime(2024,1,1,1,tzinfo=timezone(timedelta(hours=9)))
output=BytesIO();value.save(output);output.seek(0)
business &= Document(output).core_properties.modified==datetime(2023,12,31,16,tzinfo=timezone.utc)

print(json.dumps({'candidate_import': Path(docx.__file__).resolve().is_relative_to(root / 'library'), 'business': bool(business)}))
