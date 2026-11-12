"Public regression tests for HTML2TEXT-O02-DEV; the complete business contract is in materials/HTML2TEXT-O02-DEV-contract.md."
from html2text import HTML2Text
import pytest

def convert(text,**options):
    "Support the public regression through convert."
    converter=HTML2Text(bodywidth=0)
    for key,value in options.items():setattr(converter,key,value)
    return converter.handle(text)

def test_caption_is_real_separate_paragraph_before_actual_header():
    "Verify caption is real separate paragraph before actual header."
    text='<table><caption>Quarter report</caption><tr><th>Name</th><th>Value</th></tr><tr><td>A</td><td>2</td></tr></table>'
    actual=convert(text,table_caption_mode='paragraph')
    assert 'Quarter report\n\nName| Value' in actual and '---|---' in actual and 'A| 2' in actual

def test_caption_inline_formatting_multiple_and_empty_boundaries():
    "Verify caption inline formatting multiple and empty boundaries."
    text='<table><caption><strong>First</strong></caption><caption><a href="https://e.test">Second</a></caption><caption></caption><tr><td>Cell</td></tr></table>'
    actual=convert(text,table_caption_mode='paragraph')
    assert '**First**\n\n[Second](https://e.test)\n\nCell' in actual and actual.count('First')==1

def test_default_bypass_ignore_modes_and_invalid_strategy_are_explicit():
    "Verify default bypass ignore modes and invalid strategy are explicit."
    text='<table><caption>Title</caption><tr><td>Cell</td></tr></table>'
    assert convert(text)==convert(text,table_caption_mode='legacy')
    import re
    assert re.search(r'Title[ \t]*\n[ \t]*\n',convert(text,table_caption_mode='paragraph',bypass_tables=True))
    assert re.search(r'Title[ \t]*\n[ \t]*\nCell',convert(text,table_caption_mode='paragraph',ignore_tables=True))
    with pytest.raises(ValueError):convert(text,table_caption_mode='guess')
