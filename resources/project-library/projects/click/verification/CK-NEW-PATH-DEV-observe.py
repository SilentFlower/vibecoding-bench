"""在固定候选源码上运行独立业务矩阵，不调用模型或外部服务。"""
import json
import os
from pathlib import Path
root = Path(os.environ['PROJECT_CANDIDATE_ROOT']).resolve()

import click
_candidate_source_root = root
business = False
try:
    from click.newpath import NewPath
    from pathlib import Path
    from tempfile import TemporaryDirectory
    with TemporaryDirectory() as temporary:
        path=Path(temporary)/'new';type_=NewPath(resolve_path=True,path_type=Path)
        result=type_.convert(path,None,None)
        path.write_text('arrived')
        rejected=False
        try:
            type_.convert(path,None,None)
        except click.BadParameter:
            rejected=True
        business=result==path.resolve() and rejected and path.read_text()=='arrived'

except Exception:
    business = False

print(json.dumps({'candidate_import': Path(click.__file__).resolve().is_relative_to(_candidate_source_root / 'library'), 'business': bool(business)}))
