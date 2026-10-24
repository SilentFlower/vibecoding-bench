"Public regression tests for XW-SHEET-NAMES-DEV; the complete business contract is in materials/XW-SHEET-NAMES-DEV-contract.md."
from io import BytesIO
from xlsxwriter import Workbook
from xlsxwriter.sheet_names import add_named_worksheet

def test_forbidden_names_and_apostrophes_are_sanitized():
    book=Workbook(BytesIO());sheet=add_named_worksheet(book," 'sales/[west]' ")
    assert sheet.get_name()=='sales__west_' and sheet is book.worksheets()[0];book.close()

def test_case_collisions_allocate_stable_suffixes():
    book=Workbook(BytesIO());book.add_worksheet('Report')
    assert add_named_worksheet(book,'report').get_name()=='report (2)'
    assert add_named_worksheet(book,'REPORT').get_name()=='REPORT (3)';book.close()

def test_long_unicode_names_leave_space_for_suffix():
    book=Workbook(BytesIO());first=add_named_worksheet(book,'中'*40);second=add_named_worksheet(book,'中'*40)
    assert len(first.get_name())==31 and len(second.get_name())==31 and second.get_name().endswith(' (2)');book.close()

def test_empty_and_reserved_names_are_usable():
    book=Workbook(BytesIO());assert add_named_worksheet(book,'  ').get_name()=='Sheet'
    assert add_named_worksheet(book,'History').get_name()=='History_';book.close()
