"""在固定候选源码上运行独立业务矩阵，不调用模型或外部服务。"""
import json
import os
from pathlib import Path
root = Path(os.environ['PROJECT_CANDIDATE_ROOT']).resolve()

import dotenv
_candidate_source_root = root
business = False
try:
    from dotenv.validation import parse_config, ConfigValidationError
    from dotenv import dotenv_values
    from io import StringIO
    import os
    before = dict(os.environ)
    result = parse_config("\ufeff# note\r\nexport A='secret'\r\nA=two\r\n", duplicates='last')
    issues = ()
    try:
        parse_config('X\nX=private\n', required=('X','Y','Y'))
    except ConfigValidationError as error:
        issues = error.issues
    business = (dict(result.values) == {'A':'two'} and result.lines['A'] == 3
        and issues == (('duplicate','X',2),('required','Y',None))
        and dict(os.environ) == before and dotenv_values(stream=StringIO('A=1\nA=2\n'))['A']=='2')

except Exception:
    business = False

print(json.dumps({'candidate_import': Path(dotenv.__file__).resolve().is_relative_to(_candidate_source_root / 'library'), 'business': bool(business)}))
