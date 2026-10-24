"""公开类型记录实际XLSX回归。"""
from io import BytesIO
from zipfile import ZipFile
import xml.etree.ElementTree as ET
import pytest
from xlsxwriter import Workbook
from xlsxwriter.records import Column,write_records

NS='{http://schemas.openxmlformats.org/spreadsheetml/2006/main}'

def test_text_is_literal_and_only_explicit_formula_creates_formula_cell():
    output=BytesIO();book=Workbook(output);sheet=book.add_worksheet()
    columns=[Column('text','Text'),Column('formula','Formula','formula')]
    assert write_records(sheet,0,columns,[{'text':'=1+1','formula':'=1+1'}])==1;book.close()
    with ZipFile(output) as archive: root=ET.fromstring(archive.read('xl/worksheets/sheet1.xml'))
    cells={node.attrib['r']:node for node in root.iter(NS+'c')}
    assert cells['A2'].find(NS+'f') is None and cells['B2'].find(NS+'f').text=='1+1'

def test_bad_late_cell_is_rejected_before_any_cell_in_that_row():
    book=Workbook(BytesIO());sheet=book.add_worksheet();columns=[Column('a','A','text'),Column('n','N','number')]
    with pytest.raises(ValueError): write_records(sheet,5,columns,[{'a':'ok','n':True}],headers=False)
    assert 5 not in sheet.table;book.close()

def test_missing_values_and_bool_number_separation_are_explicit():
    book=Workbook(BytesIO());sheet=book.add_worksheet()
    with pytest.raises(KeyError): write_records(sheet,0,[Column('v','V')],[{}],headers=False,missing='raise')
    assert write_records(sheet,0,[Column('v','V')],[{}, {'v':False}],headers=False)==2;book.close()

def test_duplicate_columns_and_oversize_strings_fail():
    book=Workbook(BytesIO());sheet=book.add_worksheet()
    with pytest.raises(ValueError): write_records(sheet,0,[Column('x','A'),Column('x','B')],[])
    with pytest.raises(ValueError): write_records(sheet,0,[Column('x','X')],[{'x':'x'*32768}],headers=False)
    book.close()
