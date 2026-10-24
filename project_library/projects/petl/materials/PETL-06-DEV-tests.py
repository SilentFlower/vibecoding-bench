"Public regression tests for PETL-06-DEV; the complete business contract is in materials/PETL-06-DEV-contract.md."
from petl import MemorySource
from xml.etree import ElementTree
import unittest
import petl

def test_builtin_tag_name_attribute_preserve_text_and_quotes():
    "Verify builtin tag name attribute preserve text and quotes."
    value='A&B <tag> "quote" \'single\' 中文'
    for style in ('tag','name','attribute'):
        output=MemorySource();petl.toxml([['value'],[value]],output,root='root',rows='rows/row/col' if style=='tag' else 'rows/row',style=style)
        root=ElementTree.fromstring(output.getvalue())
        assert (root.find('.//row').attrib['value'] if style=='attribute' else root.find('.//value').text if style=='name' else root.find('.//col').text)==value

def test_header_escape_invalid_names_controls_and_raw_template():
    "Verify header escape invalid names controls and raw template."
    output=MemorySource();petl.toxml([['A&B'],['x']],output)
    assert ElementTree.fromstring(output.getvalue()).find('.//th').text=='A&B'
    with unittest.TestCase().assertRaises(ValueError):petl.toxml([['bad name'],['x']],MemorySource(),rows='rows/row',style='name')
    with unittest.TestCase().assertRaises(ValueError):petl.toxml([['value'],['bad\x01']],MemorySource())
    output=MemorySource();petl.toxml([['value'],['<ok/>']],output,root='root',rows='rows/row',style='<item>{value}</item>')
    assert b'<item><ok/></item>' in output.getvalue()

