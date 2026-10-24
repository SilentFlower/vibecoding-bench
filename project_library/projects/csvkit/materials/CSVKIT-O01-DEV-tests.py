"Public regression tests for CSVKIT-O01-DEV; the complete business contract is in materials/CSVKIT-O01-DEV-contract.md."
from io import StringIO
import pytest

def test_real_fixes_and_error_contract():
    "Verify real fixes and error contract."
    from csvkit.cleaning import clean_file
    result=clean_file(StringIO(' a ,b\n1\n2,3,4\n'),header_normalize_space=True,fill_short_rows=True,length_mismatch=True)
    assert result.schema==1 and result.header==('a','b') and result.rows==(('1',None),('2','3','4'))
    assert len(result.errors)==1 and result.errors[0].code=='length_mismatch' and not hasattr(result.errors[0],'row')

def test_remove_late_empty_column_and_stream_ownership():
    "Verify remove late empty column and stream ownership."
    from csvkit.cleaning import clean_file
    stream=StringIO('a,b,c\n1,,3\n2,,4\n')
    result=clean_file(stream,remove_empty_columns=True,empty_columns=True)
    assert result.header==('a','c') and result.rows==(('1','3'),('2','4')) and not stream.closed
    assert result.errors[0].code=='empty_columns'

def test_empty_limits_and_io_failure():
    "Verify empty limits and io failure."
    from csvkit.cleaning import clean_file,CleanLimitError
    assert clean_file(StringIO('')).header==()
    with pytest.raises(CleanLimitError):clean_file(StringIO('a\n1\n2\n'),max_rows=1)
    class Broken(StringIO):
        def __next__(self):raise OSError('read failure')
    with pytest.raises(OSError):clean_file(Broken('a\n'))
