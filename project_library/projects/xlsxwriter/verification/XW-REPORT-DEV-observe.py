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
    from pathlib import Path
    from tempfile import TemporaryDirectory
    from xlsxwriter.records import Column
    from xlsxwriter.report import export_report
    with TemporaryDirectory() as directory:
        path=Path(directory)/'report.xlsx';path.write_bytes(b'old')
        def source():
            yield {'v':1}
            raise RuntimeError('source failed')
        failed=False
        try:
            export_report(path,[Column('v','V')],source(),max_rows=2)
        except RuntimeError:
            failed=True
        business=failed and path.read_bytes()==b'old' and len(list(Path(directory).iterdir()))==1

except Exception:
    business = False

print(json.dumps({'candidate_import': _candidate_import_bound, 'business': bool(business)}))
