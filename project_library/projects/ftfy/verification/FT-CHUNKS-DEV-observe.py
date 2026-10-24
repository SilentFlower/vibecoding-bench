"""在固定候选源码上运行独立业务矩阵，不调用模型或外部服务。"""
import json
import os
from pathlib import Path
root = Path(os.environ['PROJECT_CANDIDATE_ROOT']).resolve()

import ftfy
_candidate_source_root = root
_candidate_import_bound = Path(ftfy.__file__).resolve().is_relative_to(_candidate_source_root / 'library')
business = False
try:
    from io import StringIO
    from ftfy import fix_file,TextFixerConfig
    from ftfy.streaming import fix_chunks
    text='x\r\ncafÃ©\n\nﬁ';config=TextFixerConfig(normalization=None,uncurl_quotes=False)
    business=list(fix_chunks(list(text),config,max_line_length=50))==list(fix_file(StringIO(text),config)) and list(fix_chunks(['','','']))==[]

except Exception:
    business = False

print(json.dumps({'candidate_import': _candidate_import_bound, 'business': bool(business)}))
