"Public regression tests for MARKDOWNIFY-O05-DEV; the complete business contract is in materials/MARKDOWNIFY-O05-DEV-contract.md."
from markdownify import markdownify
import pytest

def test_offset_setext_and_atx_styles_use_mapped_depth():
    "Verify offset setext and atx styles use mapped depth."
    assert markdownify('<h1>A</h1><h2>B</h2>',heading_offset=1)=='A\n-\n\n### B'
    assert markdownify('<h1>A</h1>',heading_offset=2,heading_style='atx_closed')=='### A ###'
    assert markdownify('<h3>A</h3>',heading_offset=-2)=='A\n='

def test_minimum_negative_offset_and_nonstandard_headings():
    "Verify minimum negative offset and nonstandard headings."
    assert markdownify('<h1>A</h1><h3>B</h3>',heading_offset=-5,heading_minimum=2)=='A\n-\n\nB\n-'
    assert markdownify('<h7>Deep</h7>')=='###### Deep'
    assert markdownify('<h6>Deep</h6>',heading_offset=2,heading_overflow='bold')=='**Deep**'
    assert markdownify('<h7></h7>',heading_overflow='bold')==''

def test_overflow_errors_validation_and_inline_compatibility():
    "Verify overflow errors validation and inline compatibility."
    with pytest.raises(ValueError):markdownify('<h6>x</h6>',heading_offset=1,heading_overflow='error')
    for options in [dict(heading_offset=True),dict(heading_minimum=0),dict(heading_overflow='guess')]:
        with pytest.raises(ValueError):markdownify('<h1>x</h1>',**options)
    assert '# ' not in markdownify('<table><tr><td><h1>x</h1></td></tr></table>',heading_offset=3)
