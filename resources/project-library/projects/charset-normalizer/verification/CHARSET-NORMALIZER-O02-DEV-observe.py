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
suite = control.SUITES['charset-normalizer']
import_root = Path(suite.get('import_root', '.'))
control._bind_source(root / 'library', import_root, cleanup, distribution=suite.get('distribution'))
sys.path.insert(0, str(root / 'library' / import_root))

import charset_normalizer
import io
business = False
try:
    from charset_normalizer.streams import from_stream
    source = io.BytesIO(b'private text')
    result = from_stream(source, max_bytes=100, read_size=2, preserve_position=False)
    business = result['eof'] and result['read_bytes'] == 12 and str(result['matches'].best()) == 'private text' and source.tell() == 12
    class Nonseek:
        """不支持位置恢复的流。"""
        def read(self, size):
            """空输入。@param size 大小。@return 空字节。"""
            return b''
    try:
        from_stream(Nonseek(), max_bytes=4)
    except ValueError:
        pass
    else:
        business = False
    business &= from_stream(Nonseek(), max_bytes=4, preserve_position=False)['eof']
except ImportError:
    business = False

print(json.dumps({'candidate_import': Path(charset_normalizer.__file__).resolve().is_relative_to(root / 'library'), 'business': bool(business)}))
