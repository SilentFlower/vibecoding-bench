"""在固定候选源码上运行独立业务矩阵，不调用模型或外部服务。"""
import json
import os
from pathlib import Path
root = Path(os.environ['PROJECT_CANDIDATE_ROOT']).resolve()

import babel
_candidate_source_root = root
business = False
try:
    from babel.core import negotiate_locale_preferences, negotiate_locale
    business = (negotiate_locale_preferences('zh-TW;q=0.7,en;q=0.8', ['zh_TW','en_US']) == 'en_US'
        and negotiate_locale_preferences('fr-CA;q=0.8,de;q=0.8', ['de','fr']) == 'fr'
        and negotiate_locale_preferences('en-US;q=0, *', ['en_US','de_DE']) == 'de_DE'
        and negotiate_locale_preferences('en;q=0, en-US;q=1, fr;q=0.1', ['en_US','fr']) == 'fr'
        and negotiate_locale_preferences('', ['en']) is None
        and negotiate_locale(['de_DE'], ['de']) == 'de')

except Exception:
    business = False

print(json.dumps({'candidate_import': Path(babel.__file__).resolve().is_relative_to(_candidate_source_root / 'library'), 'business': bool(business)}))
