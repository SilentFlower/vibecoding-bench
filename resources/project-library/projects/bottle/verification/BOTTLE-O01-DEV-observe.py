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
        upload = bottle.FileUpload(io.BytesIO(b'private'), 'upload', 'document.txt')
        upload.save(folder)
        business = (folder / 'document.txt').read_bytes() == b'private'
        try:
            upload.save(folder)
        except IOError:
            pass
        else:
            business = False
        (folder / 'view.tpl').write_text('ok', encoding='utf-8')
        business &= bottle.SimpleTemplate(name=Path('view'), lookup=[folder]).render() == 'ok'
        resources = bottle.ResourceManager()
        resources.add_path(folder)
        business &= resources.path == [str(folder) + bottle.os.sep]
        bottle.request.bind({'REQUEST_METHOD': 'GET', 'PATH_INFO': '/', 'wsgi.input': io.BytesIO()})
        result = bottle.static_file(Path('document.txt'), folder)
        business &= result.status_code == 200
        result.close()
except (TypeError, AttributeError):
    business = False

print(json.dumps({'candidate_import': Path(bottle.__file__).resolve().is_relative_to(root / 'library'), 'business': bool(business)}))
