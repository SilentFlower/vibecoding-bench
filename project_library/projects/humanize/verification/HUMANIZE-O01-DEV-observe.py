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
suite = control.SUITES['humanize']
import_root = Path(suite.get('import_root', '.'))
control._bind_source(root / 'library', import_root, cleanup, distribution=suite.get('distribution'))
sys.path.insert(0, str(root / 'library' / import_root))

import humanize
def catalog(root,word):
    """构造合成GNU消息目录，供实际gettext读取。@return 根路径。"""
    import struct
    entries={'':'Content-Type: text/plain; charset=UTF-8\nLanguage: xx\nPlural-Forms: nplurals=2; plural=(n != 1);\n','one':word,'%s and %s':'%s et %s'}
    pairs=sorted((key.encode(),value.encode()) for key,value in entries.items());count=len(pairs)
    ids=b'\0'.join(key for key,value in pairs)+b'\0';values=b'\0'.join(value for key,value in pairs)+b'\0'
    head=28;id_start=head+count*16;value_start=id_start+len(ids);out=struct.pack('<7I',0x950412de,0,count,head,head+count*8,0,0)
    offset=0
    for key,value in pairs:out+=struct.pack('<2I',len(key),id_start+offset);offset+=len(key)+1
    offset=0
    for key,value in pairs:out+=struct.pack('<2I',len(value),value_start+offset);offset+=len(value)+1
    target=root/'xx'/'LC_MESSAGES'/'humanize.mo';target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(out+ids+values)
    return root
business=False
try:
    import tempfile
    from pathlib import Path
    from humanize import i18n
    with tempfile.TemporaryDirectory() as directory:
        first=catalog(Path(directory)/'one','first');second=catalog(Path(directory)/'two','second')
        i18n.activate('xx',first);a=humanize.apnumber(1);i18n.activate('xx',second);b=humanize.apnumber(1)
        business=a=='first' and b=='second'
        i18n.deactivate();business=business and humanize.apnumber(1)=='one'
except TypeError:business=False

print(json.dumps({'candidate_import': Path(humanize.__file__).resolve().is_relative_to(_bench_candidate_root / 'library'), 'business': bool(business)}))
