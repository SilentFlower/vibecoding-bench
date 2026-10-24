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
suite = control.SUITES['transitions']
control._bind_source(root / 'library', Path(suite.get('import_root', '.')), cleanup, distribution=suite.get('distribution'))
import sys
sys.path.insert(0, str(root / 'library' / suite.get('import_root', '.')))
import transitions
from transitions import Machine
business=True
machine=Machine(states=['x','y'],initial='x',auto_transitions=False)
machine.add_transition('move','*','y',unless='never_evaluated')
report=machine.preview_event(machine,'move')
business &= len(report['candidates'])==1 and report['candidates'][0]['source']=='x'
business &= report['candidates'][0]['conditions'][0]['target'] is False and machine.state=='x'

print(json.dumps({'candidate_import': Path(transitions.__file__).resolve().is_relative_to(root / 'library'), 'business': bool(business)}))
