"""页码规范化公开回归，完整约定见同目录工程合同。"""
from bibtexparser import Library
from bibtexparser.model import Entry, Field

def test_numeric_ranges():
    """数字及区间正确归一，允许首尾空白保留或移除。:return: None。"""
    from bibtexparser.pages import NormalizePages
    source = Library([Entry('article', 'x', [Field('pages', '12-19, 23–24'), Field('title', 'a-b')])])
    result = NormalizePages().transform(source)
    assert result.entries[0]['pages'] == '12--19, 23--24'
    assert result.entries[0]['title'] == 'a-b' and source.entries[0]['pages'] == '12-19, 23–24'
    spaced = Library([Entry('article', 'spaced', [Field('pages', ' 001 - 009 ')])])
    assert NormalizePages().transform(spaced).entries[0]['pages'].strip() == '001--009'
    assert spaced.entries[0]['pages'] == ' 001 - 009 '

def test_unknown_and_descending_preserved():
    """未知格式和倒序页码整体保持。:return: None。"""
    from bibtexparser.pages import NormalizePages
    for pages in ('e123', 'iv-v', '9-2', '', '12.5-13.5'):
        assert NormalizePages().transform(Library([Entry('article', 'x', [Field('pages', pages)])])).entries[0]['pages'] == pages

def test_idempotent_and_original():
    """重复变换不改变首次原值。:return: None。"""
    from bibtexparser.pages import NormalizePages
    result = NormalizePages().transform(Library([Entry('article', 'x', [Field('pages', '1—3')])]))
    again = NormalizePages().transform(result)
    assert again.entries[0]['pages'] == '1--3'
    assert again.entries[0].parser_metadata['original_pages'] == '1—3'
