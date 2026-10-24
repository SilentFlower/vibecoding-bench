"""在固定候选源码上运行独立业务矩阵，不调用模型或外部服务。"""
import json
import os
from pathlib import Path
root = Path(os.environ['PROJECT_CANDIDATE_ROOT']).resolve()

import xlsxwriter
_candidate_source_root = root
_candidate_import_bound = Path(xlsxwriter.__file__).resolve().is_relative_to(_candidate_source_root / 'library')
business = False
try:
    from io import BytesIO
    from xlsxwriter import Workbook
    from xlsxwriter.sheet_names import add_named_worksheet
    book=Workbook(BytesIO());book.add_worksheet('x (2)');book.add_worksheet('x')
    value=add_named_worksheet(book,'x').get_name();book.close()
    business=value=='x (3)'

except Exception:
    business = False

print(json.dumps({'candidate_import': _candidate_import_bound, 'business': bool(business)}))
