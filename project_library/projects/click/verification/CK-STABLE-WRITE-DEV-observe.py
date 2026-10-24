"""在固定候选源码上运行独立业务矩阵，不调用模型或外部服务。"""
import json
import os
from pathlib import Path
root = Path(os.environ['PROJECT_CANDIDATE_ROOT']).resolve()

import click
_candidate_source_root = root
business = False
try:
    from click.writing import write_if_changed
    from tempfile import TemporaryDirectory
    from pathlib import Path
    with TemporaryDirectory() as temporary:
        path=Path(temporary)/'out';path.write_bytes(b'old\r\n');path.chmod(0o644)
        changed=write_if_changed(path,b'new\r\n')
        link=Path(temporary)/'link';link.symlink_to(path)
        refused=False
        try:
            write_if_changed(link,b'bad')
        except ValueError:
            refused=True
        business=changed and refused and path.read_bytes()==b'new\r\n' and path.stat().st_mode&0o777==0o644

except Exception:
    business = False

print(json.dumps({'candidate_import': Path(click.__file__).resolve().is_relative_to(_candidate_source_root / 'library'), 'business': bool(business)}))
