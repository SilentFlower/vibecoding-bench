"""在固定候选源码上运行独立业务矩阵，不调用模型或外部服务。"""
import json
import os
from pathlib import Path
root = Path(os.environ['PROJECT_CANDIDATE_ROOT']).resolve()

import decouple
business = False
try:
    config = decouple.Config(decouple.RepositoryEmpty())
    failure = RuntimeError('factory')
    def broken():
        """后备失败。@return 不返回。"""
        raise failure
    try:
        config('PRIVATE_FACTORY', default_factory=broken)
    except RuntimeError as error:
        business = error is failure
    business &= config('PRIVATE_FACTORY', default_factory=lambda: 'yes', cast=bool) is True
    class Repository:
        """存在合法空值的仓库。"""
        def __contains__(self, key):
            """所有键存在。@param key 键。@return True。"""
            return True
        def __getitem__(self, key):
            """返回空值。@param key 键。@return 空字符串。"""
            return ''
    business &= decouple.Config(Repository())('PRIVATE_FACTORY', default_factory=broken) == ''
    try:
        config('PRIVATE_FACTORY', default_factory=3)
    except TypeError:
        pass
    else:
        business = False
except TypeError:
    business = False

print(json.dumps({'candidate_import': Path(decouple.__file__).resolve().is_relative_to(root / 'library'), 'business': bool(business)}))
