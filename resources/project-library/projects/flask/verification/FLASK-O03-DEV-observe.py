"""在固定候选源码上运行独立业务矩阵，不调用模型或外部服务。"""
import json
import os
from pathlib import Path
root = Path(os.environ['PROJECT_CANDIDATE_ROOT']).resolve()
_bench_candidate_root = root
from contextlib import ExitStack
from importlib.util import module_from_spec, spec_from_file_location
import sys
spec = spec_from_file_location('frozen_control', Path(__file__).with_name('native_regression.py'))
control = module_from_spec(spec)
spec.loader.exec_module(control)
cleanup = ExitStack()
suite = control.SUITES['flask']
import_root = Path(suite.get('import_root', '.'))
control._bind_source(root / 'library', import_root, cleanup, distribution=suite.get('distribution'))
sys.path.insert(0, str(root / 'library' / import_root))

import flask
_bench_candidate_module = flask
from flask import Flask
app=Flask(__name__);app.config.update(PAGE_SIZE='secret-value',FLAGS={'ENABLED':1});business=hasattr(app.config,'validate')
if business:
    rows=app.config.validate({'PAGE_SIZE':{'type':int},'FLAGS':{'properties':{'ENABLED':{'type':bool}}}})
    business=rows==[{'path':['PAGE_SIZE'],'code':'type'},{'path':['FLAGS','ENABLED'],'code':'type'}] and app.config['PAGE_SIZE']=='secret-value'

print(json.dumps({'candidate_import': Path(_bench_candidate_module.__file__).resolve().is_relative_to(_bench_candidate_root / 'library'), 'business': bool(business)}))
