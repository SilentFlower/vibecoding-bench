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
suite = control.SUITES['tqdm']
control._bind_source(root / 'library', Path(suite.get('import_root', '.')), cleanup, distribution=suite.get('distribution'))
import sys
sys.path.insert(0, str(root / 'library' / suite.get('import_root', '.')))
import tqdm
from tqdm.contrib.concurrent import ensure_lock
business=True
class Local:
    """原无锁状态，模拟真实get/set接口。"""
    @classmethod
    def get_lock(cls):
        """创建类自有锁。@return 锁对象。"""
        if not hasattr(cls,'_lock'):cls._lock=object()
        return cls._lock
    @classmethod
    def set_lock(cls,lock):
        """安装锁。@param lock 对象。@return None。"""
        cls._lock=lock
try:
    with ensure_lock(Local):raise OSError('body')
except OSError:pass
business &= '_lock' not in Local.__dict__
Local._lock=None
try:
    with ensure_lock(Local):raise OSError('body')
except OSError:pass
business &= '_lock' in Local.__dict__ and Local._lock is None

print(json.dumps({'candidate_import': Path(tqdm.__file__).resolve().is_relative_to(root / 'library'), 'business': bool(business)}))
