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
    from datetime import datetime,timezone,timedelta
    from io import BytesIO
    from zipfile import ZipFile
    import xml.etree.ElementTree as ET
    from xlsxwriter import Workbook
    from xlsxwriter.records import Column,write_records
    output=BytesIO();book=Workbook(output,{'constant_memory':True});sheet=book.add_worksheet()
    count=write_records(sheet,0,[Column('at','At','datetime_utc'),Column('ok','Ok','boolean')],iter([{'at':datetime(2026,1,1,8,tzinfo=timezone(timedelta(hours=8))),'ok':False}]))
    book.close()
    with ZipFile(output) as archive:
        root=ET.fromstring(archive.read('xl/worksheets/sheet1.xml'))
        cells={cell.attrib['r']:cell for cell in root.iter('{http://schemas.openxmlformats.org/spreadsheetml/2006/main}c')}
    business=count==1 and cells['B2'].attrib['t']=='b' and cells['B2'].find('{http://schemas.openxmlformats.org/spreadsheetml/2006/main}v').text=='0'

except Exception:
    business = False

print(json.dumps({'candidate_import': _candidate_import_bound, 'business': bool(business)}))
