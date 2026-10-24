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
import pickle
from packaging.display import DisplayVersion
from packaging.version import Version,InvalidVersion
business=True
a,b=DisplayVersion('01.02'),DisplayVersion('1.2.0')
business &= a==b and hash(a)==hash(b) and sorted([DisplayVersion('2'),a])[0] is a
business &= pickle.loads(pickle.dumps(a)).display=='01.02'
business &= DisplayVersion.from_version(Version('1').__replace__(release=(3,))).raw_version is None
try:DisplayVersion('not a version');business=False
except InvalidVersion:pass

print(json.dumps({'candidate_import': Path(packaging.__file__).resolve().is_relative_to(root / 'library'), 'business': bool(business)}))
