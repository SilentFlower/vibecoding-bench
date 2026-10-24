"Public regression tests for XD-ATTR-SORT-DEV; the complete business contract is in materials/XD-ATTR-SORT-DEV-contract.md."
from io import StringIO
import pytest
import xmltodict

def test_attributes_sort_at_all_depths_and_default_order_is_retained():
    value={'r':{'@z':'2','@a':'1','c':{'@y':'4','@b':'3'}}}
    assert xmltodict.unparse(value,sort_attributes=True,full_document=False)=='<r a="1" z="2"><c b="3" y="4"></c></r>'
    assert xmltodict.unparse(value,full_document=False).startswith('<r z="2" a="1">')

def test_child_order_and_input_order_are_not_mutated():
    value={'r':{'@z':'x','@a':'y','second':'2','first':'1'}};before=list(value['r'])
    result=xmltodict.unparse(value,sort_attributes=True)
    assert result.index('<second>')<result.index('<first>') and list(value['r'])==before

def test_output_stream_escaping_and_short_empty_elements():
    stream=StringIO();value={'r':{'@z':'<&','@a':'"','empty':None}}
    xmltodict.unparse(value,stream,sort_attributes=True,short_empty_elements=True)
    assert xmltodict.parse(stream.getvalue())==value

def test_invalid_option_does_not_write_partial_document():
    stream=StringIO()
    with pytest.raises(TypeError):
        xmltodict.unparse({'r':None},stream,sort_attributes='yes')
    assert stream.getvalue()==''
