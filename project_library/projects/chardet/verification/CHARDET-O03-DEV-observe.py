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
suite = control.SUITES['chardet']
import_root = Path(suite.get('import_root', '.'))
control._bind_source(root / 'library', import_root, cleanup, distribution=suite.get('distribution'))
sys.path.insert(0, str(root / 'library' / import_root))

import chardet
import io
business = False
try:
    from chardet.files import detect_file
    class Short(io.BytesIO):
        """每次最多读取一个字节。"""
        def read(self, size=-1):
            """模拟短读。@param size 请求大小。@return 字节。"""
            return super().read(min(size, 1))
    source = Short(b'abcdef')
    result = detect_file(source, chunk_size=10)
    business = result['eof'] and result['read_bytes'] == 6 and source.tell() == 0
    class Broken(io.BytesIO):
        """读取故障流。"""
        def read(self, size=-1):
            """读取失败。@param size 请求大小。@return 不返回。"""
            self.seek(1)
            raise OSError('read')
    broken = Broken(b'abc')
    try:
        detect_file(broken)
    except OSError:
        business &= broken.tell() == 0 and not broken.closed
    else:
        business = False
except ImportError:
    business = False

print(json.dumps({'candidate_import': Path(chardet.__file__).resolve().is_relative_to(root / 'library'), 'business': bool(business)}))
