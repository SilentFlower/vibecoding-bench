"""通过实际生成的XLSX包核数据类型、缓存、行序和公式政策。"""
from io import BytesIO
import json
import os
from pathlib import Path
import sys
import warnings
import xml.etree.ElementTree as ET
from zipfile import BadZipFile, ZipFile

import xlsxwriter
from xlsxwriter import Workbook


NS = {'s': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}


def package(buffer: BytesIO) -> tuple[dict, list[str], list[str]]:
    """独立解析关闭后的包。@param buffer 实际XLSX。@return 单元格、共享文本和部件。"""
    with ZipFile(buffer) as archive:
        names = archive.namelist()
        sheet = ET.fromstring(archive.read('xl/worksheets/sheet1.xml'))
        cells = {cell.attrib['r']: cell for cell in sheet.findall('.//s:c', NS)}
        strings = []
        if 'xl/sharedStrings.xml' in names:
            strings = [''.join(item.itertext()) for item in ET.fromstring(archive.read('xl/sharedStrings.xml'))]
        return cells, strings, names


def formula_controls() -> bool:
    """同时核禁用、默认开启和显式公式API，不能靠全局关闭公式通过。@return 是否符合。"""
    output = BytesIO()
    book = Workbook(output, {'in_memory': True, 'strings_to_formulas': False})
    sheet = book.add_worksheet()
    sheet.write(0, 0, '{=SUM(1,2)}')
    sheet.write(1, 0, '=1+2')
    sheet.write_formula(2, 0, '{=SUM(1,2)}', None, 3)
    sheet.write_string(3, 0, '{=SUM(1,2)}')
    book.close()
    cells, strings, _ = package(output)
    literal = (cells['A1'].find('s:f', NS) is None and cells['A2'].find('s:f', NS) is None
        and strings[int(cells['A1'].findtext('s:v', namespaces=NS))] == '{=SUM(1,2)}'
        and cells['A3'].find('s:f', NS) is not None and cells['A4'].find('s:f', NS) is None)
    control = BytesIO()
    book = Workbook(control, {'in_memory': True})
    sheet = book.add_worksheet()
    sheet.write(0, 0, '{=SUM(1,2)}')
    sheet.write(1, 0, '=1+2')
    sheet.write(2, 0, 5)
    book.close()
    cells, _, _ = package(control)
    return literal and cells['A1'].find('s:f', NS) is not None and cells['A2'].find('s:f', NS) is not None and cells['A3'].findtext('s:v', namespaces=NS) == '5'


def main() -> None:
    """用有界内存工作簿观察候选，不运行Excel或LibreOffice。@return None。"""
    root = Path(os.environ['PROJECT_CANDIDATE_ROOT']).resolve()
    result = {'candidate_import': Path(xlsxwriter.__file__).resolve() == root / 'library/xlsxwriter/__init__.py'}
    task = sys.argv[1]
    if task == 'XW-U01':
        output = BytesIO()
        book = Workbook(output, {'in_memory': True})
        sheet = book.add_worksheet()
        sheet.write_formula(0, 0, '=SUM(3,4)')
        sheet.write_formula(1, 0, '=SUM(3,4)', None, 7)
        book.close()
        cells, _, _ = package(output)
        result['formula_xml_and_cached_values_are_distinct_from_recalculation'] = (
            cells['A1'].findtext('s:f', namespaces=NS) == cells['A2'].findtext('s:f', namespaces=NS) == 'SUM(3,4)'
            and cells['A1'].findtext('s:v', namespaces=NS) == '0' and cells['A2'].findtext('s:v', namespaces=NS) == '7')
    elif task == 'XW-C01':
        outputs = []
        for enabled in (False, True):
            output = BytesIO()
            book = Workbook(output, {'in_memory': True, 'strings_to_numbers': enabled})
            sheet = book.add_worksheet()
            sheet.write(0, 0, '00123')
            sheet.write_string(1, 0, '=1+2')
            book.close()
            outputs.append(package(output))
        plain, converted = outputs
        result['identifier_strings_and_explicit_text_preserve_declared_wire_types'] = (
            plain[0]['A1'].attrib.get('t') == 's' and plain[1][int(plain[0]['A1'].findtext('s:v', namespaces=NS))] == '00123'
            and converted[0]['A1'].attrib.get('t') != 's' and converted[0]['A1'].findtext('s:v', namespaces=NS) == '123'
            and all(cells['A2'].find('s:f', NS) is None for cells, _, _ in outputs))
    elif task == 'XW-U02':
        output = BytesIO()
        book = Workbook(output, {'constant_memory': True})
        sheet = book.add_worksheet()
        codes = [sheet.write(0, 0, 'A'), sheet.write(1, 0, 'B'), sheet.write(0, 1, 'LATE')]
        book.close()
        cells, _, _ = package(output)
        result['constant_memory_requires_forward_row_order'] = codes == [0, 0, -1] and set(cells) == {'A1', 'A2'}
    elif task == 'XW-C02':
        output = BytesIO()
        book = Workbook(output, {'constant_memory': True})
        sheet = book.add_worksheet()
        sheet.write(0, 0, 'header')
        sheet.write(1, 0, 1)
        with warnings.catch_warnings(record=True) as observed:
            warnings.simplefilter('always')
            code = sheet.add_table(0, 0, 1, 0)
        book.close()
        _, _, names = package(output)
        other = Workbook(BytesIO(), {'in_memory': True, 'constant_memory': True})
        disabled = other.constant_memory is False
        other.close()
        result['table_and_in_memory_require_explicit_memory_mode_choices'] = (
            code == -3 and bool(observed) and not any(name.startswith('xl/tables/') for name in names) and disabled)
    elif task == 'XW-P01':
        output = BytesIO()
        book = Workbook(output, {'in_memory': True})
        book.add_worksheet().write(0, 0, 'A')
        before_invalid = False
        try:
            ZipFile(output).close()
        except BadZipFile:
            before_invalid = True
        book.close()
        _, _, names = package(output)
        result['workbook_is_finalized_only_on_close_before_application_publication'] = before_invalid and '[Content_Types].xml' in names
    elif task == 'XW-M01':
        result['formula_opt_out_applies_to_braced_array_strings_without_disabling_explicit_formulas'] = formula_controls()
    else:
        raise ValueError('未冻结的业务任务')
    print(json.dumps(result))


if __name__ == '__main__':
    main()
