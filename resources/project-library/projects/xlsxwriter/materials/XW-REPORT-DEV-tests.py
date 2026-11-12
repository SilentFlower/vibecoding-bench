"Public regression tests for XW-REPORT-DEV; the complete business contract is in materials/XW-REPORT-DEV-contract.md."
from zipfile import ZipFile
import xml.etree.ElementTree as ET
import pytest
from xlsxwriter.records import Column
from xlsxwriter.report import export_report

def test_real_report_splits_rows_and_repeats_headers(tmp_path):
    path=tmp_path/'report.xlsx';result=export_report(path,[Column('v','Value')],({'v':i} for i in range(5)),max_rows=3)
    assert result.row_count==5 and result.sheets==('Report','Report (2)','Report (3)')
    with ZipFile(path) as archive:
        counts=[len(list(ET.fromstring(archive.read('xl/worksheets/sheet'+str(i)+'.xml')).iter('{http://schemas.openxmlformats.org/spreadsheetml/2006/main}row'))) for i in (1,2,3)]
    assert counts==[3,3,2]

def test_empty_input_creates_one_usable_header_sheet(tmp_path):
    result=export_report(tmp_path/'empty.xlsx',[Column('v','Value')],[])
    assert result.row_count==0 and result.sheets==('Report',)

def test_late_bad_record_preserves_old_report(tmp_path):
    path=tmp_path/'report.xlsx';path.write_bytes(b'previous')
    with pytest.raises(ValueError): export_report(path,[Column('v','Value','number')],[{'v':1},{'v':'bad'}],max_rows=2)
    assert path.read_bytes()==b'previous' and len(list(tmp_path.iterdir()))==1

def test_constant_memory_and_sanitized_names_are_supported(tmp_path):
    result=export_report(tmp_path/'report.xlsx',[Column('v','V')],[{'v':'=1+1'},{'v':'x'}],sheet='a/b',max_rows=2,workbook_options={'constant_memory':True})
    assert result.sheets==('a_b','a_b (2)') and result.row_count==2
