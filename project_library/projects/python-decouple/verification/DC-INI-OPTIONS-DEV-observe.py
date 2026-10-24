"""在固定候选源码上运行独立业务矩阵，不调用模型或外部服务。"""
import json
import os
from pathlib import Path
root = Path(os.environ['PROJECT_CANDIDATE_ROOT']).resolve()

import decouple
from tempfile import TemporaryDirectory
business = False
try:
    with TemporaryDirectory() as temporary:
        path = Path(temporary) / 'private.ini'
        path.write_text('[DEFAULT]\nPREFIX=base\n[worker]\nDSN=a%2Fb%25\n[settings]\nDSN=%(PREFIX)s\n', encoding='utf-8')
        one = decouple.RepositoryIni(str(path), section='worker', interpolation=False)
        two = decouple.RepositoryIni(str(path))
        business = one['DSN'] == 'a%2Fb%25' and two['DSN'] == 'base' and one['PREFIX'] == 'base'
        for option in [{'section': ''}, {'interpolation': 'false'}]:
            try:
                decouple.RepositoryIni(str(path), **option)
            except (ValueError, TypeError):
                pass
            else:
                business = False
except (TypeError, ValueError):
    business = False

print(json.dumps({'candidate_import': Path(decouple.__file__).resolve().is_relative_to(root / 'library'), 'business': bool(business)}))
