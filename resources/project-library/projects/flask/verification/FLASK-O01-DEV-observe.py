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
from flask.cli import cli
import json
app=Flask(__name__,static_folder=None);app.add_url_rule('/actual','probe',lambda:'ok',methods=['POST'])
result=app.test_cli_runner().invoke(cli,args=['routes','--format','json']);business=False
if result.exit_code==0:
    document=json.loads(result.output);row=document['routes'][0]
    business=document['schema']==1 and row['rule']=='/actual' and row['methods']==['OPTIONS','POST'] and row['automatic_options']

print(json.dumps({'candidate_import': Path(_bench_candidate_module.__file__).resolve().is_relative_to(_bench_candidate_root / 'library'), 'business': bool(business)}))
