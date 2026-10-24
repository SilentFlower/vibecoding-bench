"""公开XML读取预算回归。"""
import pytest
import xmltodict

def test_depth_and_element_boundaries_are_exact():
    assert xmltodict.parse('<a><b/></a>',max_depth=2,max_elements=2)=={'a':{'b':None}}
    for options in ({'max_depth':1},{'max_elements':1}):
        with pytest.raises(xmltodict.XMLLimitError):
            xmltodict.parse('<a><b/></a>',**options)

def test_decoded_text_counts_unicode_and_whitespace():
    assert xmltodict.parse('<a>雪 花</a>',max_text_chars=3)=={'a':'雪 花'}
    with pytest.raises(xmltodict.XMLLimitError):
        xmltodict.parse('<a>雪 花</a>',max_text_chars=2)

def test_streaming_mode_cannot_reset_whole_document_budget():
    seen=[]
    with pytest.raises(xmltodict.XMLLimitError):
        xmltodict.parse('<r><a>1</a><a>2</a></r>',item_depth=2,item_callback=lambda path,item:not seen.append(item),max_elements=2)
    assert seen==['1']

def test_invalid_limit_does_not_consume_input():
    def input_data():
        raise AssertionError('不应读取')
        yield b''
    for value in (-1,True,1.5):
        with pytest.raises(ValueError):
            xmltodict.parse(input_data(),max_depth=value)
