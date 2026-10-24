"Public regression tests for TB-CONVERT-DEV; the complete business contract is in materials/TB-CONVERT-DEV-contract.md."
from decimal import Decimal
import pytest
from tablib import Dataset
from tablib.conversion import convert_columns

def test_real_decimal_and_integer_conversion_preserve_original():
    data=Dataset(['1','1.2300'],headers=['qty','price']);result=convert_columns(data,{'qty':int,'price':Decimal})
    assert result.dataset[0]==(1,Decimal('1.2300')) and result.errors==() and data[0]==('1','1.2300')

def test_collect_keeps_original_bad_cell_and_all_errors_in_header_order():
    data=Dataset(['bad','also-bad'],['2','3'],headers=['a','b']);result=convert_columns(data,{'b':int,'a':int},errors='collect')
    assert [(error.row,error.column) for error in result.errors]==[(0,'a'),(0,'b')]
    assert list(result.dataset)==[('bad','also-bad'),(2,3)]

def test_mutating_converter_cannot_change_input_on_failure():
    data=Dataset([[1]],headers=['value'])
    def convert(value): value.append(2);raise ValueError('bad')
    result=convert_columns(data,{'value':convert},errors='collect')
    assert data[0][0]==[1] and result.dataset[0][0]==[1]

def test_raise_context_and_programming_exceptions_are_preserved():
    data=Dataset(['bad'],headers=['value'])
    with pytest.raises(ValueError,match='value'): convert_columns(data,{'value':int})
    with pytest.raises(RuntimeError): convert_columns(data,{'value':lambda value:(_ for _ in ()).throw(RuntimeError('bug'))},errors='collect')
