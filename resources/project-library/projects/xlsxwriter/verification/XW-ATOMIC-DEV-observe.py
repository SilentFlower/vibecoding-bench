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
    from tempfile import TemporaryDirectory
    from pathlib import Path
    from xlsxwriter.atomic import atomic_workbook
    with TemporaryDirectory() as directory:
        path=Path(directory)/'new.xlsx'
        try:
            with atomic_workbook(path) as book:
                book.add_worksheet();raise ValueError('stop')
        except ValueError:
            pass
        business=not path.exists() and not list(Path(directory).iterdir())

except Exception:
    business = False

print(json.dumps({'candidate_import': _candidate_import_bound, 'business': bool(business)}))
