"""公开UTC实际工作簿回归。"""
from datetime import datetime,timezone,timedelta
from io import BytesIO
from zipfile import ZipFile
import xml.etree.ElementTree as ET
import pytest
from xlsxwriter import Workbook
from xlsxwriter.utc import as_utc,write_utc

def test_offset_conversion_preserves_instant_and_microseconds():
    value=datetime(2026,1,2,3,4,5,6000,tzinfo=timezone(timedelta(hours=8)))
    assert as_utc(value)==datetime(2026,1,1,19,4,5,6000) and value.utcoffset()==timedelta(hours=8)

def test_naive_policy_is_explicit():
    value=datetime(2026,1,1)
    with pytest.raises(ValueError): as_utc(value)
    assert as_utc(value,naive='utc')==value

def test_real_worksheet_value_matches_direct_utc_write():
    output=BytesIO();book=Workbook(output);sheet=book.add_worksheet()
    assert write_utc(sheet,0,0,datetime(2026,1,1,8,tzinfo=timezone(timedelta(hours=8))))==0
    sheet.write_datetime(0,1,datetime(2026,1,1));book.close()
    with ZipFile(output) as archive:
        root=ET.fromstring(archive.read('xl/worksheets/sheet1.xml'))
    values=[node.text for node in root.iter('{http://schemas.openxmlformats.org/spreadsheetml/2006/main}v')]
    assert values[0]==values[1]

def test_native_out_of_bounds_status_is_preserved():
    output=BytesIO();book=Workbook(output);sheet=book.add_worksheet()
    assert write_utc(sheet,1048576,0,datetime(2026,1,1,tzinfo=timezone.utc))==-1
    book.close()
