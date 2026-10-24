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
import codecs
business = True
for bom in (codecs.BOM_UTF8, codecs.BOM_UTF16_LE, codecs.BOM_UTF16_BE, codecs.BOM_UTF32_LE, codecs.BOM_UTF32_BE, b'\xfe\xff\x00\x00', b'\x00\x00\xff\xfe'):
    payload = bom + b'a\x00b\x00'
    expected = chardet.detect(payload)['encoding']
    for cut in range(1, len(bom) + 1):
        detector = chardet.UniversalDetector()
        detector.feed(payload[:cut]); detector.feed(payload[cut:])
        business &= detector.close()['encoding'] == expected
detector = chardet.UniversalDetector()
for part in (b'\xff', b'\xfe'): detector.feed(part)
business &= detector.close()['encoding'] == 'UTF-16'
detector.reset(); detector.feed(b'abc')
business &= detector.close()['encoding'] == 'ascii'

print(json.dumps({'candidate_import': Path(chardet.__file__).resolve().is_relative_to(root / 'library'), 'business': bool(business)}))
