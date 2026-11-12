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
suite = control.SUITES['bottle']
import_root = Path(suite.get('import_root', '.'))
control._bind_source(root / 'library', import_root, cleanup, distribution=suite.get('distribution'))
sys.path.insert(0, str(root / 'library' / import_root))

import bottle
import io
from tempfile import TemporaryDirectory
business = False
try:
    with TemporaryDirectory() as temporary:
        folder = Path(temporary)
        class Broken(io.BytesIO):
            """在复制中途产生真实读失败。"""
            def read(self, size=-1):
                """第二块读取失败。@param size 大小。@return 数据。"""
                if self.tell() > 0:
                    raise OSError('read failed')
                return super().read(1)
        source = Broken(b'abc')
        upload = bottle.FileUpload(source, 'file', 'x')
        destination = folder / 'keep'
        destination.write_bytes(b'old')
        try:
            upload.save_atomic(destination, overwrite=True, chunk_size=1)
        except OSError:
            business = destination.read_bytes() == b'old' and source.tell() == 0 and not list(folder.glob('.bottle-upload-*'))
        else:
            business = False
        bottle.FileUpload(io.BytesIO(b''), 'file', 'empty').save_atomic(folder)
        business &= (folder / 'empty').read_bytes() == b''
except AttributeError:
    business = False

print(json.dumps({'candidate_import': Path(bottle.__file__).resolve().is_relative_to(root / 'library'), 'business': bool(business)}))
