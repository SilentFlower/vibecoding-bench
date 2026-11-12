"Public regression tests for CH-FORMULA-DEV; the complete business contract is in materials/CH-FORMULA-DEV-contract.md."
import pytest
from cli_helpers.tabular_output.preprocessors import spreadsheet_formula_policy
from cli_helpers.tabular_output import TabularOutputFormatter

def test_escape_preserves_original_text_and_numeric_negatives():
    rows,headers=spreadsheet_formula_policy([[' =SUM(A1)',-2,'normal']],['=header','n','s'],formula_policy='escape')
    assert headers==["'=header",'n','s'] and list(rows)==[["' =SUM(A1)",-2,'normal']]

def test_error_reports_location_without_contents():
    rows,headers=spreadsheet_formula_policy([['safe'],['=private()']],['name'],formula_policy='error')
    assert next(rows)==['safe']
    with pytest.raises(ValueError) as caught:
        next(rows)
    assert '行2列1' in str(caught.value) and 'private' not in str(caught.value)

def test_default_and_input_values_are_unchanged():
    data=[['=1','-text',-3]];headers=['name','value','n']
    rows,new_headers=spreadsheet_formula_policy(data,headers)
    assert list(rows)==data and headers==new_headers and data==[['=1','-text',-3]]

def test_real_csv_formatter_does_not_leak_explicit_policy():
    formatter=TabularOutputFormatter('csv');processor=(spreadsheet_formula_policy,)
    first=list(formatter.format_output([['=1']],['value'],preprocessors=processor,formula_policy='escape'))
    second=list(formatter.format_output([['=1']],['value'],preprocessors=processor))
    assert first==['value',"'=1"] and second==['value','=1']
