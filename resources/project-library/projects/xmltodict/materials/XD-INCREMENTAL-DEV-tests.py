"Public regression tests for XD-INCREMENTAL-DEV; the complete business contract is in materials/XD-INCREMENTAL-DEV-contract.md."
import pytest
import xmltodict
from xml.parsers.expat import ExpatError

def test_every_utf8_byte_boundary_matches_parse():
    text='<r><a>雪</a><a>花</a></r>';parser=xmltodict.IncrementalParser()
    for value in text.encode():
        parser.feed(bytes([value]))
    assert parser.close()==xmltodict.parse(text) and parser.close()==xmltodict.parse(text)

def test_closed_and_failed_parsers_cannot_be_reused():
    parser=xmltodict.IncrementalParser();parser.feed('<r/>');parser.close()
    with pytest.raises(RuntimeError):
        parser.feed('')
    broken=xmltodict.IncrementalParser();broken.feed('<r>')
    with pytest.raises(ExpatError):
        broken.close()
    with pytest.raises(RuntimeError):
        broken.close()

def test_chunk_types_and_resource_budget_are_enforced():
    parser=xmltodict.IncrementalParser();parser.feed('<r>')
    with pytest.raises(TypeError):
        parser.feed(b'</r>')
    parser=xmltodict.IncrementalParser(max_elements=1)
    with pytest.raises(xmltodict.XMLLimitError):
        parser.feed('<r><a/></r>')

def test_entities_are_blocked_and_streamed_items_do_not_accumulate():
    parser=xmltodict.IncrementalParser()
    with pytest.raises(ValueError):
        parser.feed('<!DOCTYPE r [<!ENTITY x "secret">]><r>&x;</r>')
    seen=[];parser=xmltodict.IncrementalParser(item_depth=2,item_callback=lambda path,item:not seen.append(item))
    parser.feed('<r><a>one</a>');parser.feed('<a>two</a></r>')
    assert parser.close() is None and seen==['one','two']
