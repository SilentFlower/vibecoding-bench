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
suite = control.SUITES['pyparsing']
control._bind_source(root / 'library', Path(suite.get('import_root', '.')), cleanup, distribution=suite.get('distribution'))
import sys
sys.path.insert(0, str(root / 'library' / suite.get('import_root', '.')))
import pyparsing
import pyparsing as pp
from pyparsing.byte_input import parse_bytes,ByteParseError
business=True
value=parse_bytes(pp.Word(pp.alphas),b'caf\xe9',encoding='latin1')
business &= value.results.as_list()==['caf'] and value.byte_offsets==(0,1,2,3,4)
try:parse_bytes(pp.Literal('雪')+pp.StringEnd(),'雪\r\n!'.encode(),encoding='utf8',parse_all=True)
except ByteParseError as error:business &= error.byte_offset==5
else:business=False

print(json.dumps({'candidate_import': Path(pyparsing.__file__).resolve().is_relative_to(root / 'library'), 'business': bool(business)}))
