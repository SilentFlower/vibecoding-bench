"""表格标题模式保留独立段落关系而不污染表头。"""
from html2text import HTML2Text
import pytest

def convert(text,**options):
    """通过真实转换设置明确选项。@return Markdown。"""
    converter=HTML2Text(bodywidth=0)
    for key,value in options.items():setattr(converter,key,value)
    return converter.handle(text)

def test_caption_is_real_separate_paragraph_before_actual_header():
    """标题不再与首单元格粘连，表格分隔仍正确。@return None。"""
    text='<table><caption>Quarter report</caption><tr><th>Name</th><th>Value</th></tr><tr><td>A</td><td>2</td></tr></table>'
    actual=convert(text,table_caption_mode='paragraph')
    assert 'Quarter report\n\nName| Value' in actual and '---|---' in actual and 'A| 2' in actual

def test_caption_inline_formatting_multiple_and_empty_boundaries():
    """标题仍经过真实强调/链接转换，多标题各一段，空标题不造文本。@return None。"""
    text='<table><caption><strong>First</strong></caption><caption><a href="https://e.test">Second</a></caption><caption></caption><tr><td>Cell</td></tr></table>'
    actual=convert(text,table_caption_mode='paragraph')
    assert '**First**\n\n[Second](https://e.test)\n\nCell' in actual and actual.count('First')==1

def test_default_bypass_ignore_modes_and_invalid_strategy_are_explicit():
    """默认不改，bypass/ignore表仍保留独立标题，错误策略拒绝。@return None。"""
    text='<table><caption>Title</caption><tr><td>Cell</td></tr></table>'
    assert convert(text)==convert(text,table_caption_mode='legacy')
    import re
    assert re.search(r'Title[ \t]*\n[ \t]*\n',convert(text,table_caption_mode='paragraph',bypass_tables=True))
    assert re.search(r'Title[ \t]*\n[ \t]*\nCell',convert(text,table_caption_mode='paragraph',ignore_tables=True))
    with pytest.raises(ValueError):convert(text,table_caption_mode='guess')
