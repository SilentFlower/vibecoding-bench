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
suite = control.SUITES['configargparse']
import_root = Path(suite.get('import_root', '.'))
control._bind_source(root / 'library', import_root, cleanup, distribution=suite.get('distribution'))
sys.path.insert(0, str(root / 'library' / import_root))

import configargparse
business=False
try:
    import tempfile
    from pathlib import Path
    class Provider:
        def __call__(self):raise AssertionError('called')
        def __repr__(self):raise AssertionError('repr')
    with tempfile.TemporaryDirectory() as directory:
        path=Path(directory)/'exists';path.write_text('x=1')
        p=configargparse.ArgumentParser(default_config_files=[path,Provider()]);p.add('--x')
        p.parse_args(['--help'],env_vars={}) if False else None
        rows=p.discover_config_files();rows[0]['path']='caller mutation'
        again=p.discover_config_files()
        business=again[0]['path']==str(path) and again[1]=={'kind':'provider','index':1,'executed':False} and not hasattr(p,'_source_to_settings')
except AttributeError:
    business=False

print(json.dumps({'candidate_import': Path(configargparse.__file__).resolve().is_relative_to(root / 'library'), 'business': bool(business)}))
