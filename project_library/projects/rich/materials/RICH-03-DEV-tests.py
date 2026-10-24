"Public regression tests for RICH-03-DEV; the complete business contract is in materials/RICH-03-DEV-contract.md."
import unittest
from rich.text import Text,Span


def test_negative_index_preserves_overlapping_spans_and_base_style():
    "Verify negative index preserves overlapping spans and base style."
    text=Text('hello',style='bold',spans=[Span(1,5,'red'),Span(3,5,'underline')])
    negative=text[-1];positive=text[4]
    assert negative.plain==positive.plain=='o' and negative.spans==positive.spans
    assert negative.style==positive.style==text.style
    assert len(negative.spans)==2 and all(span.start==0 and span.end==1 for span in negative.spans)


def test_boundaries_unicode_and_source_not_modified():
    "Verify boundaries unicode and source not modified."
    text=Text('中文',style='italic');before=text.copy()
    assert text[-2].plain=='中' and text[-1].plain=='文'
    for offset in (-3,2):
        with unittest.TestCase().assertRaises(IndexError):text[offset]
    with unittest.TestCase().assertRaises(IndexError):Text('')[-1]
    assert text.plain==before.plain and text.spans==before.spans and text.style==before.style

