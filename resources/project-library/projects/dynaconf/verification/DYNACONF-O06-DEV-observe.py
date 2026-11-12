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
suite = control.SUITES['dynaconf']
import_root = Path(suite.get('import_root', '.'))
control._bind_source(root / 'library', import_root, cleanup, distribution=suite.get('distribution'))
sys.path.insert(0, str(root / 'library' / import_root))

import dynaconf
_bench_candidate_module = dynaconf
from dynaconf import Dynaconf
from dynaconf.vendor.click.testing import CliRunner
from unittest.mock import patch
import dynaconf.cli as cli
import json
settings=Dynaconf(environments=False,FIRST_A=1,SECOND_B=2,EXCLUDED=3)
with patch.object(cli,'settings',settings,create=True):result=CliRunner().invoke(cli._list,['--json','--match','FIRST_*','--match','SECOND_*'])
business=result.exit_code==0 and json.loads(result.output)=={'FIRST_A':1,'SECOND_B':2}

print(json.dumps({'candidate_import': Path(_bench_candidate_module.__file__).resolve().is_relative_to(_bench_candidate_root / 'library'), 'business': bool(business)}))
