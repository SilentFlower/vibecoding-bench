"""在固定候选源码上运行独立业务矩阵，不调用模型或外部服务。"""
import json
import os
from pathlib import Path
root = Path(os.environ['PROJECT_CANDIDATE_ROOT']).resolve()

import decouple
from tempfile import TemporaryDirectory
business = True
try:
    with TemporaryDirectory() as temporary:
        path = Path(temporary) / 'private.env'
        path.write_text('﻿ # heading\n\nX = a=b\nY=\n', encoding='utf-8')
        repository = decouple.RepositoryEnv(str(path), strict=True)
        business &= repository['X'] == 'a=b' and repository['Y'] == ''
        path.write_text('X=secret\nX=second-secret\n', encoding='utf-8')
        try:
            decouple.RepositoryEnv(str(path), strict=True)
        except ValueError as error:
            business &= '2' in str(error) and 'secret' not in str(error)
        else:
            business = False
        business &= decouple.RepositoryEnv(str(path))['X'] == 'second-secret'
except TypeError:
    business = False

print(json.dumps({'candidate_import': Path(decouple.__file__).resolve().is_relative_to(root / 'library'), 'business': bool(business)}))
