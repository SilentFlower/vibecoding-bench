"""标题迁移改变真实输出层级，并明示超深层的降级策略。"""
from markdownify import markdownify
import pytest

def test_offset_setext_and_atx_styles_use_mapped_depth():
    """原h1移到h2仍Setext，原h2移h3必须ATX。@return None。"""
    assert markdownify('<h1>A</h1><h2>B</h2>',heading_offset=1)=='A\n-\n\n### B'
    assert markdownify('<h1>A</h1>',heading_offset=2,heading_style='atx_closed')=='### A ###'
    assert markdownify('<h3>A</h3>',heading_offset=-2)=='A\n='

def test_minimum_negative_offset_and_nonstandard_headings():
    """最低级别和负迁移不生成h0，非标准h7也按同一政策。@return None。"""
    assert markdownify('<h1>A</h1><h3>B</h3>',heading_offset=-5,heading_minimum=2)=='A\n-\n\nB\n-'
    assert markdownify('<h7>Deep</h7>')=='###### Deep'
    assert markdownify('<h6>Deep</h6>',heading_offset=2,heading_overflow='bold')=='**Deep**'
    assert markdownify('<h7></h7>',heading_overflow='bold')==''

def test_overflow_errors_validation_and_inline_compatibility():
    """非法策略和深度错误明确，表格内标题仍沿原行内规则。@return None。"""
    with pytest.raises(ValueError):markdownify('<h6>x</h6>',heading_offset=1,heading_overflow='error')
    for options in [dict(heading_offset=True),dict(heading_minimum=0),dict(heading_overflow='guess')]:
        with pytest.raises(ValueError):markdownify('<h1>x</h1>',**options)
    assert '# ' not in markdownify('<table><tr><td><h1>x</h1></td></tr></table>',heading_offset=3)
