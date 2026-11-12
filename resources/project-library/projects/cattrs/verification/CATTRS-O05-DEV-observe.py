"""在固定候选源码上运行独立业务矩阵，不调用模型或外部服务。"""
import json
import os
from pathlib import Path
root = Path(os.environ['PROJECT_CANDIDATE_ROOT']).resolve()
from contextlib import ExitStack
from importlib.util import module_from_spec, spec_from_file_location
import sys
spec = spec_from_file_location('frozen_control', Path(__file__).with_name('native_regression.py'))
control = module_from_spec(spec)
spec.loader.exec_module(control)
cleanup = ExitStack()
suite = control.SUITES['cattrs']
import_root = Path(suite.get('import_root', '.'))
control._bind_source(root / 'library', import_root, cleanup, distribution=suite.get('distribution'))
sys.path.insert(0, str(root / 'library' / import_root))

import cattrs
from os import PathLike
from pathlib import PurePosixPath
business = False
try:
    from cattrs.strategies.pathlike import configure_pathlike
    converter = configure_pathlike(cattrs.Converter(), factory=PurePosixPath)
    business = converter.structure('', PathLike[str]) == PurePosixPath('.')
    class BytesPath:
        """不允许自动解码的路径。"""
        def __fspath__(self):
            """返回bytes。@return bytes。"""
            return b'/virtual/raw'
    try:
        converter.unstructure(BytesPath(), unstructure_as=PathLike[str])
    except TypeError:
        pass
    else:
        business = False
except ImportError:
    business = False

print(json.dumps({'candidate_import': Path(cattrs.__file__).resolve().is_relative_to(root / 'library'), 'business': bool(business)}))
